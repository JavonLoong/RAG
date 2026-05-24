"""
FastAPI 后端 — 合并两版

项目2: 工厂模式 create_app() + Pydantic 校验 + benchmark API
项目1: 分步 API (上传→处理→统计→检索) + 前端静态文件挂载
新增: 上传状态清单、按勾选处理、已处理文件批量删除
新增: 导出 Chroma DB（整库打包 / 单集合 JSON）
"""
from __future__ import annotations

import io
import re
import shutil
import tempfile
import time
import zipfile
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import orjson
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .benchmark import run_synthetic_benchmark
from .observability import OperationLogger
from .parsing import get_source_kind, is_supported_source, supported_source_extensions
from .pipeline import (
    DEFAULT_PERSIST_DIR,
    DEFAULT_UPLOAD_DIR,
    get_all_stats,
    get_collection_stats,
    ingest_source_payloads,
    query_collection,
)
from .public_books_json import ingest_latest_snapshot_to_chroma, write_ingest_summary

PACKAGE_FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"
CONSOLE_FRONTEND_DIR = Path(__file__).resolve().parents[3] / "frontend"
REPO_FRONTEND_DIR = Path(__file__).resolve().parents[5] / "frontend_app" / "current_console"
FRONTEND_DIR = next(
    path
    for path in (REPO_FRONTEND_DIR, CONSOLE_FRONTEND_DIR, PACKAGE_FRONTEND_DIR)
    if path.exists()
)
SUPPORTED_EXTENSIONS_LABEL = ", ".join(supported_source_extensions())
UPLOAD_MANIFEST_NAME = ".upload-manifest.json"
WINDOWS_INVALID_UPLOAD_CHARS = set('<>:"/\\|?*')
DEFAULT_LOG_DIR = DEFAULT_UPLOAD_DIR.parent / "logs"
LOG_FILENAME_PATTERN = re.compile(r"^[0-9A-Za-z._-]+\.log$")


def _safe_upload_name(raw_name: str) -> str:
    clean = normalize_upload_name(raw_name)
    return clean[:220] if len(clean) > 220 else clean


def _sanitize_upload_part(part: str) -> str:
    cleaned = "".join(
        "_" if char in WINDOWS_INVALID_UPLOAD_CHARS or ord(char) < 32 else char
        for char in str(part)
    )
    cleaned = cleaned.strip().strip(".")
    return cleaned or "item"


def normalize_upload_name(raw_name: str) -> str:
    raw = str(raw_name or "").replace("\x00", "")
    parts = [
        _sanitize_upload_part(part.strip())
        for part in Path(raw).parts
        if part not in {"", ".", ".."}
    ]
    if not parts:
        return f"upload-{int(time.time())}.bin"
    return "__".join(parts)


def _manifest_path(upload_dir: Path) -> Path:
    return Path(upload_dir) / UPLOAD_MANIFEST_NAME


def _read_upload_manifest(upload_dir: Path) -> dict[str, dict]:
    manifest_path = _manifest_path(upload_dir)
    if not manifest_path.exists():
        return {}
    try:
        payload = orjson.loads(manifest_path.read_bytes())
    except Exception:
        return {}

    if isinstance(payload, dict):
        files = payload.get("files", payload)
        if isinstance(files, dict):
            return {
                str(filename): entry
                for filename, entry in files.items()
                if isinstance(filename, str) and isinstance(entry, dict)
            }
    return {}


def _write_upload_manifest(upload_dir: Path, entries: dict[str, dict]) -> None:
    manifest_path = _manifest_path(upload_dir)
    manifest_path.write_bytes(
        orjson.dumps(
            {"files": entries},
            option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS,
        )
    )


def _supported_upload_paths(upload_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in Path(upload_dir).iterdir()
        if path.is_file() and path.name != UPLOAD_MANIFEST_NAME and is_supported_source(path.name)
    )


def _guess_display_name(filename: str) -> str:
    return filename.replace("__", "/")


def _collect_upload_entries(upload_dir: Path) -> list[dict]:
    upload_dir = Path(upload_dir)
    manifest = _read_upload_manifest(upload_dir)
    synced: dict[str, dict] = {}

    for file_path in _supported_upload_paths(upload_dir):
        stat = file_path.stat()
        existing = manifest.get(file_path.name, {})
        status = str(existing.get("status") or "uploaded")
        if status not in {"uploaded", "processed"}:
            status = "uploaded"

        entry = {
            "filename": file_path.name,
            "display_name": str(existing.get("display_name") or _guess_display_name(file_path.name)),
            "size_kb": round(stat.st_size / 1024, 1),
            "modified": stat.st_mtime,
            "uploaded_at": float(existing.get("uploaded_at") or stat.st_mtime),
            "processed_at": existing.get("processed_at"),
            "status": status,
            "source_kind": str(existing.get("source_kind") or get_source_kind(file_path.name)),
            "last_collection": existing.get("last_collection"),
            "last_records": int(existing.get("last_records") or 0),
            "last_chunks": int(existing.get("last_chunks") or 0),
            "last_error": existing.get("last_error"),
            "last_log_file": existing.get("last_log_file"),
        }
        synced[file_path.name] = entry

    _write_upload_manifest(upload_dir, synced)

    return sorted(
        synced.values(),
        key=lambda item: (
            0 if item.get("status") != "processed" else 1,
            str(item.get("display_name") or item.get("filename") or "").lower(),
        ),
    )


def _update_upload_entry(upload_dir: Path, filename: str, **updates) -> dict:
    upload_dir = Path(upload_dir)
    manifest = _read_upload_manifest(upload_dir)
    current = dict(manifest.get(filename, {}))
    current.update({key: value for key, value in updates.items() if value is not None})
    manifest[filename] = current
    _write_upload_manifest(upload_dir, manifest)
    return current


def _remove_upload_entries(upload_dir: Path, filenames: list[str]) -> None:
    upload_dir = Path(upload_dir)
    manifest = _read_upload_manifest(upload_dir)
    for filename in filenames:
        manifest.pop(filename, None)
    _write_upload_manifest(upload_dir, manifest)


def _mark_process_result(
    upload_dir: Path,
    result: dict,
    collection_name: str,
    log_file: str | None = None,
) -> None:
    upload_dir = Path(upload_dir)
    manifest = _read_upload_manifest(upload_dir)
    now = time.time()

    for item in result.get("file_summaries", []):
        filename = str(item.get("source_file") or "").strip()
        if not filename:
            continue
        current = dict(manifest.get(filename, {}))
        current["status"] = "processed" if item.get("status") == "ok" else "uploaded"
        current["processed_at"] = now if item.get("status") == "ok" else current.get("processed_at")
        current["last_collection"] = collection_name
        current["last_records"] = int(item.get("records_extracted") or 0)
        current["last_chunks"] = int(result.get("chunks_written") or 0) if item.get("status") == "ok" else 0
        current["last_error"] = None if item.get("status") == "ok" else item.get("error")
        current["last_log_file"] = log_file or current.get("last_log_file")
        manifest[filename] = current

    _write_upload_manifest(upload_dir, manifest)


def _operation_log_payload(logger: OperationLogger) -> dict[str, str]:
    return {"log_file": logger.file_name}


def _list_operation_logs(log_dir: Path, limit: int = 50) -> list[dict]:
    log_dir = Path(log_dir)
    if not log_dir.exists():
        return []

    items: list[dict] = []
    for path in sorted(log_dir.glob("*.log"), key=lambda item: item.stat().st_mtime, reverse=True):
        stat = path.stat()
        items.append(
            {
                "filename": path.name,
                "size_kb": round(stat.st_size / 1024, 1),
                "modified": stat.st_mtime,
            }
        )
        if len(items) >= limit:
            break
    return items


def _resolve_log_path(log_dir: Path, filename: str) -> Path:
    clean_name = str(filename or "").strip()
    if not LOG_FILENAME_PATTERN.fullmatch(clean_name):
        raise HTTPException(status_code=400, detail="日志文件名不合法")
    log_root = Path(log_dir).resolve()
    log_path = (log_root / clean_name).resolve()
    try:
        log_path.relative_to(log_root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="日志文件名不合法") from exc
    if not log_path.exists() or not log_path.is_file():
        raise HTTPException(status_code=404, detail="日志文件不存在")
    return log_path


def _enforce_log_same_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    host = request.headers.get("host")
    if not origin or not host:
        return
    if urlparse(origin).netloc != host:
        raise HTTPException(status_code=403, detail="日志只允许同源访问")


def _resolve_upload_path(upload_dir: Path, filename: str) -> tuple[str, Path]:
    stored_name = str(filename or "").strip()
    if (
        not stored_name
        or stored_name == UPLOAD_MANIFEST_NAME
        or _safe_upload_name(stored_name) != stored_name
    ):
        raise HTTPException(status_code=400, detail="上传文件名不合法")

    upload_root = Path(upload_dir).resolve()
    file_path = (upload_root / stored_name).resolve()
    try:
        file_path.relative_to(upload_root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="上传文件名不合法") from exc
    return stored_name, file_path


def _purge_vectors_by_source_files(persist_dir: Path, filenames: list[str]) -> dict:
    import chromadb
    from chromadb.config import Settings

    requested = [str(name).strip() for name in filenames if str(name).strip()]
    if not requested:
        return {"chunks_deleted": 0, "collections": {}}

    client = chromadb.PersistentClient(
        path=str(persist_dir),
        settings=Settings(anonymized_telemetry=False, is_persistent=True),
    )
    deleted_total = 0
    deleted_by_collection: dict[str, int] = {}

    try:
        for coll in client.list_collections():
            collection = client.get_collection(name=coll.name)
            collection_deleted = 0
            for filename in requested:
                try:
                    payload = collection.get(where={"source_file": filename})
                except Exception:
                    payload = {"ids": []}
                ids = payload.get("ids") or []
                if ids:
                    collection.delete(ids=ids)
                    collection_deleted += len(ids)
            if collection_deleted:
                deleted_by_collection[coll.name] = collection_deleted
                deleted_total += collection_deleted
    finally:
        try:
            client._system.stop()
        except Exception:
            pass

    return {"chunks_deleted": deleted_total, "collections": deleted_by_collection}


class SearchRequest(BaseModel):
    collection: str = "power_equipment"
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)


class BenchmarkRequest(BaseModel):
    collection: str = "benchmark_power_equipment"
    document_count: int = Field(default=500, ge=50, le=5000)
    batch_size: int = Field(default=100, ge=10, le=1000)
    query_count: int = Field(default=50, ge=10, le=1000)
    top_k: int = Field(default=5, ge=1, le=20)
    backend: str = "hashing"
    model_name: str | None = None
    cleanup: bool = True


class ProcessRequest(BaseModel):
    filenames: list[str] = Field(default_factory=list)
    collection: str = "power_equipment"


class PublicBooksJsonIngestRequest(BaseModel):
    input_dir: str = Field(min_length=1)
    collection: str = "public_books_labelstudio"
    mode: str = Field(default="append", pattern="^(create|append)$")
    chunk_size: int = Field(default=900, ge=100, le=4000)
    overlap: int = Field(default=120, ge=0, le=1000)


class DeleteUploadsRequest(BaseModel):
    filenames: list[str] = Field(default_factory=list)
    purge_vectors: bool = False


def create_app(
    persist_dir: Path = DEFAULT_PERSIST_DIR,
    upload_dir: Path = DEFAULT_UPLOAD_DIR,
    log_dir: Path | None = None,
) -> FastAPI:
    """创建 FastAPI 应用（工厂模式）"""
    app = FastAPI(
        title="动力装备知识库管理系统",
        description="文件上传、向量化、ChromaDB 管理、混合检索、RAG 问答",
        version="2.1.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.persist_dir = Path(persist_dir)
    app.state.upload_dir = Path(upload_dir)
    app.state.log_dir = Path(log_dir) if log_dir else (
        DEFAULT_LOG_DIR if Path(upload_dir) == DEFAULT_UPLOAD_DIR else Path(upload_dir).parent / "logs"
    )
    app.state.persist_dir.mkdir(parents=True, exist_ok=True)
    app.state.upload_dir.mkdir(parents=True, exist_ok=True)
    app.state.log_dir.mkdir(parents=True, exist_ok=True)

    @app.get("/")
    async def index():
        index_path = FRONTEND_DIR / "index.html"
        if index_path.exists():
            return FileResponse(index_path, media_type="text/html; charset=utf-8")
        return JSONResponse({"message": "前端文件未找到，请检查 frontend/index.html"}, status_code=404)

    @app.get("/api/health")
    async def health():
        return {"status": "ok", "version": "2.1.0"}

    @app.post("/api/upload")
    async def upload_file(
        request: Request,
        file: UploadFile = File(...),
        relative_path: str | None = Form(default=None),
    ):
        """上传单个文档到上传目录。"""
        source_name = Path(file.filename or "upload.bin").name
        logger = OperationLogger(
            request.app.state.log_dir,
            "upload",
            source_file=source_name,
            relative_path=relative_path,
        )
        try:
            if not is_supported_source(source_name):
                logger.warning(
                    "upload_unsupported_type",
                    source_file=source_name,
                    supported_extensions=SUPPORTED_EXTENSIONS_LABEL,
                )
                raise HTTPException(
                    status_code=400,
                    detail=f"暂不支持该文件类型。当前支持: {SUPPORTED_EXTENSIONS_LABEL}；详细日志: {logger.file_name}",
                )

            with logger.stage("read_upload_stream", source_file=source_name):
                content = await file.read()
            if not content:
                logger.warning("upload_empty_file", source_file=source_name)
                raise HTTPException(status_code=400, detail=f"上传文件为空；详细日志: {logger.file_name}")

            display_name = relative_path.strip() if relative_path else source_name
            stored_name = _safe_upload_name(relative_path or source_name)
            save_path = request.app.state.upload_dir / stored_name
            with logger.stage(
                "save_upload_file",
                source_file=source_name,
                stored_name=stored_name,
                size_bytes=len(content),
                size_mb=round(len(content) / (1024 * 1024), 3),
            ):
                save_path.write_bytes(content)
            _update_upload_entry(
                request.app.state.upload_dir,
                stored_name,
                display_name=display_name,
                status="uploaded",
                uploaded_at=time.time(),
                processed_at=None,
                source_kind=get_source_kind(source_name),
                last_collection=None,
                last_records=0,
                last_chunks=0,
                last_error=None,
                last_log_file=logger.file_name,
            )

            response = {
                "status": "ok",
                "filename": stored_name,
                "display_name": display_name,
                "size_kb": round(len(content) / 1024, 1),
                "source_kind": get_source_kind(source_name),
                **_operation_log_payload(logger),
            }
            logger.close(status="ok", stored_name=stored_name, size_bytes=len(content))
            return response
        except HTTPException as exc:
            logger.error("upload_rejected", status_code=exc.status_code, detail=exc.detail)
            logger.close(status="error", status_code=exc.status_code, detail=exc.detail)
            raise
        except Exception as exc:
            logger.exception("upload_failed", exc, source_file=source_name)
            logger.close(status="error", error=str(exc))
            raise HTTPException(status_code=500, detail=f"上传失败: {exc}；详细日志: {logger.file_name}") from exc

    @app.get("/api/uploads")
    async def list_uploads(request: Request):
        """列出上传目录与已处理状态。"""
        files = _collect_upload_entries(request.app.state.upload_dir)
        pending = [item for item in files if item.get("status") != "processed"]
        processed = [item for item in files if item.get("status") == "processed"]
        return {
            "files": files,
            "pending": pending,
            "processed": processed,
            "count": len(files),
            "pending_count": len(pending),
            "processed_count": len(processed),
        }

    @app.get("/api/logs")
    async def list_logs(request: Request, limit: int = 50):
        """列出最近的后端处理日志。"""
        _enforce_log_same_origin(request)
        limit = max(1, min(int(limit), 200))
        return {"logs": _list_operation_logs(request.app.state.log_dir, limit=limit)}

    @app.get("/api/logs/{filename}")
    async def read_log(request: Request, filename: str):
        """读取单个后端处理日志。"""
        _enforce_log_same_origin(request)
        log_path = _resolve_log_path(request.app.state.log_dir, filename)
        return FileResponse(log_path, media_type="text/plain; charset=utf-8")

    @app.delete("/api/uploads/{filename}")
    async def delete_upload(request: Request, filename: str, purge_vectors: bool = False):
        """删除单个上传文件；如需要可同步删库。"""
        stored_name, fpath = _resolve_upload_path(request.app.state.upload_dir, filename)
        manifest = _read_upload_manifest(request.app.state.upload_dir)
        if not fpath.exists() and stored_name not in manifest:
            raise HTTPException(status_code=404, detail="文件不存在")

        purge_result = {"chunks_deleted": 0, "collections": {}}
        if purge_vectors:
            purge_result = _purge_vectors_by_source_files(request.app.state.persist_dir, [stored_name])

        if fpath.exists():
            fpath.unlink()
        _remove_upload_entries(request.app.state.upload_dir, [stored_name])
        return {"status": "ok", "deleted": stored_name, **purge_result}

    @app.post("/api/uploads/delete")
    async def delete_uploads(request: Request, payload: DeleteUploadsRequest):
        resolved = [
            _resolve_upload_path(request.app.state.upload_dir, name)
            for name in payload.filenames
            if str(name).strip()
        ]
        if not resolved:
            raise HTTPException(status_code=400, detail="没有选中的文件")
        filenames = [name for name, _ in resolved]

        purge_result = {"chunks_deleted": 0, "collections": {}}
        if payload.purge_vectors:
            purge_result = _purge_vectors_by_source_files(request.app.state.persist_dir, filenames)

        deleted: list[str] = []
        for filename, fpath in resolved:
            if fpath.exists():
                fpath.unlink()
            deleted.append(filename)

        _remove_upload_entries(request.app.state.upload_dir, deleted)
        return {"status": "ok", "deleted": deleted, **purge_result}

    @app.post("/api/process")
    async def process_files(
        request: Request,
        payload: ProcessRequest | None = None,
        mode: str = "replace",
    ):
        """处理选中的未处理文件；默认只处理未处理文件，不会重复扫已处理文件。"""
        del mode  # 保留兼容参数，当前不再依赖 replace/append 模式

        entries = _collect_upload_entries(request.app.state.upload_dir)
        by_name = {entry["filename"]: entry for entry in entries}
        requested = [str(name).strip() for name in (payload.filenames if payload else []) if str(name).strip()]
        collection_name = (payload.collection if payload else "power_equipment").strip() or "power_equipment"

        if requested:
            selected_entries = [
                by_name[name]
                for name in requested
                if name in by_name and by_name[name].get("status") != "processed"
            ]
            skipped_processed = [
                name
                for name in requested
                if name in by_name and by_name[name].get("status") == "processed"
            ]
        else:
            selected_entries = [entry for entry in entries if entry.get("status") != "processed"]
            skipped_processed = []

        logger = OperationLogger(
            request.app.state.log_dir,
            "process",
            collection_name=collection_name,
            requested_filenames=requested,
        )
        t0 = time.time()
        try:
            selected_names = [str(entry["filename"]) for entry in selected_entries]
            upload_files = [
                request.app.state.upload_dir / entry["filename"]
                for entry in selected_entries
                if (request.app.state.upload_dir / entry["filename"]).exists()
            ]
            missing_files = [
                name
                for name in selected_names
                if not (request.app.state.upload_dir / name).exists()
            ]
            logger.info(
                "process_selection",
                upload_count=len(entries),
                selected_count=len(selected_entries),
                selected_filenames=selected_names,
                skipped_already_processed=skipped_processed,
                missing_files=missing_files,
            )
            if not upload_files:
                logger.warning("process_no_files", selected_count=len(selected_entries), missing_files=missing_files)
                raise HTTPException(status_code=400, detail=f"没有可处理的待处理文件；详细日志: {logger.file_name}")

            payloads: list[tuple[str, bytes]] = []
            with logger.stage("read_upload_files", file_count=len(upload_files)):
                for file_path in upload_files:
                    size_bytes = file_path.stat().st_size
                    with logger.stage(
                        "read_upload_file",
                        source_file=file_path.name,
                        size_bytes=size_bytes,
                        size_mb=round(size_bytes / (1024 * 1024), 3),
                    ):
                        payloads.append((file_path.name, file_path.read_bytes()))

            result = ingest_source_payloads(
                payloads=payloads,
                persist_dir=request.app.state.persist_dir,
                collection_name=collection_name,
                operation_logger=logger,
            )
            _mark_process_result(
                request.app.state.upload_dir,
                result=result,
                collection_name=collection_name,
                log_file=logger.file_name,
            )
            result["elapsed_s"] = round(time.time() - t0, 1)
            result["requested_filenames"] = [f.name for f in upload_files]
            result["skipped_already_processed"] = skipped_processed
            result.update(_operation_log_payload(logger))
            logger.close(
                status="ok",
                elapsed_s=result["elapsed_s"],
                files_succeeded=result.get("files_succeeded"),
                files_failed=result.get("files_failed"),
            )
            return result

        except HTTPException as exc:
            logger.error("process_rejected", status_code=exc.status_code, detail=exc.detail)
            logger.close(status="error", status_code=exc.status_code, detail=exc.detail)
            raise
        except Exception as exc:
            logger.exception("process_failed", exc, selected_filenames=[entry["filename"] for entry in selected_entries])
            for entry in selected_entries:
                _update_upload_entry(
                    request.app.state.upload_dir,
                    entry["filename"],
                    status="uploaded",
                    last_error=str(exc),
                    last_log_file=logger.file_name,
                )
            logger.close(status="error", error=str(exc))
            raise HTTPException(status_code=500, detail=f"处理失败: {exc}；详细日志: {logger.file_name}") from exc

    @app.post("/api/public-books-json/ingest")
    async def ingest_public_books_json(request: Request, payload: PublicBooksJsonIngestRequest):
        """Run the public-books Label Studio JSON screening pipeline and write chunks to ChromaDB."""
        input_dir = Path(payload.input_dir).expanduser()
        collection_name = payload.collection.strip() or "public_books_labelstudio"
        logger = OperationLogger(
            request.app.state.log_dir,
            "public_books_json_ingest",
            input_dir=str(input_dir),
            collection_name=collection_name,
            mode=payload.mode,
            chunk_size=payload.chunk_size,
            overlap=payload.overlap,
        )
        try:
            if not input_dir.exists():
                logger.warning("json_input_missing", input_dir=str(input_dir))
                raise HTTPException(status_code=400, detail=f"JSON 目录不存在：{input_dir}；详细日志: {logger.file_name}")

            with logger.stage("public_books_json_ingest_run"):
                result = ingest_latest_snapshot_to_chroma(
                    input_root=input_dir,
                    persist_dir=request.app.state.persist_dir,
                    collection_name=collection_name,
                    mode=payload.mode,
                    chunk_size=payload.chunk_size,
                    overlap=payload.overlap,
                )

            reports_dir = Path(__file__).resolve().parents[5] / "data_pipeline" / "reports"
            with logger.stage("write_public_books_json_ingest_summary", reports_dir=str(reports_dir)):
                result["summary_files"] = write_ingest_summary(result, reports_dir)
            result.update(_operation_log_payload(logger))
            logger.close(
                status="ok",
                collection=result.get("collection"),
                chunks_written=result.get("chunks_written"),
                records_written=result.get("records_written"),
            )
            return result
        except HTTPException as exc:
            logger.error("public_books_json_ingest_rejected", status_code=exc.status_code, detail=exc.detail)
            logger.close(status="error", status_code=exc.status_code, detail=exc.detail)
            raise
        except Exception as exc:
            logger.exception("public_books_json_ingest_failed", exc)
            logger.close(status="error", error=str(exc))
            raise HTTPException(status_code=500, detail=f"JSON 入库失败: {exc}；详细日志: {logger.file_name}") from exc

    @app.post("/api/ingest")
    async def ingest(
        request: Request,
        files: list[UploadFile] = File(...),
        collection: str = Form("power_equipment"),
        chunk_size: int = Form(500),
        overlap: int = Form(50),
        backend: str = Form("hashing"),
        model_name: str = Form("BAAI/bge-m3"),
    ):
        """上传并一步入库（保留项目2接口）。"""
        collection_name = collection.strip() or "power_equipment"
        logger = OperationLogger(
            request.app.state.log_dir,
            "ingest",
            collection_name=collection_name,
            upload_count=len(files),
            chunk_size=chunk_size,
            overlap=overlap,
            backend=backend,
            model_name=model_name,
        )
        payloads: list[tuple[str, bytes]] = []
        saved_files: list[str] = []
        manifest_marked = False
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

        try:
            if not files:
                logger.warning("ingest_no_uploads")
                raise HTTPException(status_code=400, detail=f"No files uploaded；详细日志: {logger.file_name}")

            for index, upload in enumerate(files):
                source_name = Path(upload.filename or f"upload-{index}.bin").name
                with logger.stage("read_ingest_upload", source_file=source_name, index=index):
                    raw_bytes = await upload.read()
                if not raw_bytes:
                    logger.warning("ingest_empty_upload_skipped", source_file=source_name, index=index)
                    continue
                if not is_supported_source(source_name):
                    logger.warning(
                        "ingest_unsupported_type",
                        source_file=source_name,
                        supported_extensions=SUPPORTED_EXTENSIONS_LABEL,
                    )
                    raise HTTPException(
                        status_code=400,
                        detail=f"{source_name} 类型不受支持。当前支持: {SUPPORTED_EXTENSIONS_LABEL}；详细日志: {logger.file_name}",
                    )
                saved_name = f"{timestamp}-{index}-{_safe_upload_name(source_name)}"
                target = request.app.state.upload_dir / saved_name
                with logger.stage(
                    "save_ingest_upload",
                    source_file=source_name,
                    stored_name=saved_name,
                    size_bytes=len(raw_bytes),
                    size_mb=round(len(raw_bytes) / (1024 * 1024), 3),
                ):
                    target.write_bytes(raw_bytes)
                _update_upload_entry(
                    request.app.state.upload_dir,
                    saved_name,
                    display_name=source_name,
                    status="uploaded",
                    uploaded_at=time.time(),
                    processed_at=None,
                    source_kind=get_source_kind(source_name),
                    last_collection=None,
                    last_records=0,
                    last_chunks=0,
                    last_error=None,
                    last_log_file=logger.file_name,
                )
                payloads.append((saved_name, raw_bytes))
                saved_files.append(str(target))

            if not payloads:
                logger.warning("ingest_no_readable_payloads", upload_count=len(files))
                raise HTTPException(status_code=400, detail=f"上传文件为空；详细日志: {logger.file_name}")

            result = ingest_source_payloads(
                payloads=payloads,
                persist_dir=request.app.state.persist_dir,
                collection_name=collection_name,
                chunk_size=chunk_size,
                overlap=overlap,
                backend=backend,
                model_name=model_name,
                operation_logger=logger,
            )

            _mark_process_result(
                request.app.state.upload_dir,
                result=result,
                collection_name=collection_name,
                log_file=logger.file_name,
            )
            manifest_marked = True
            result["saved_files"] = saved_files
            result.update(_operation_log_payload(logger))
            logger.close(
                status="ok",
                files_succeeded=result.get("files_succeeded"),
                files_failed=result.get("files_failed"),
            )
            return result
        except HTTPException as exc:
            logger.error("ingest_rejected", status_code=exc.status_code, detail=exc.detail)
            logger.close(status="error", status_code=exc.status_code, detail=exc.detail)
            raise
        except Exception as exc:
            logger.exception("ingest_failed", exc)
            if not manifest_marked:
                for saved_name, _ in payloads:
                    _update_upload_entry(
                        request.app.state.upload_dir,
                        saved_name,
                        status="uploaded",
                        last_error=str(exc),
                        last_log_file=logger.file_name,
                    )
            logger.close(status="error", error=str(exc))
            raise HTTPException(status_code=400, detail=f"{exc}；详细日志: {logger.file_name}") from exc

    @app.get("/api/stats")
    async def stats(request: Request, collection: str | None = None):
        """获取 ChromaDB 统计信息"""
        logger = OperationLogger(request.app.state.log_dir, "stats", collection=collection)
        try:
            if collection:
                with logger.stage("collection_stats", collection_name=collection):
                    result = get_collection_stats(
                        persist_dir=request.app.state.persist_dir,
                        collection_name=collection,
                    )
            else:
                with logger.stage("all_stats"):
                    result = get_all_stats(persist_dir=request.app.state.persist_dir)
                if result.get("status") == "error":
                    logger.warning("all_stats_reported_error", error=result.get("error"))
            result.update(_operation_log_payload(logger))
            logger.close(status="ok", collection=collection)
            return result
        except HTTPException as exc:
            logger.error("stats_rejected", status_code=exc.status_code, detail=exc.detail)
            logger.close(status="error", status_code=exc.status_code, detail=exc.detail)
            raise
        except Exception as exc:
            logger.exception("stats_failed", exc, collection=collection)
            logger.close(status="error", error=str(exc))
            raise HTTPException(status_code=500, detail=f"统计失败: {exc}；详细日志: {logger.file_name}") from exc

    @app.get("/api/search")
    async def search_get(request: Request, q: str = "", top_k: int = 5, collection: str = ""):
        """语义检索 (GET) — 自动检测有数据的集合"""
        logger = OperationLogger(
            request.app.state.log_dir,
            "search",
            method="GET",
            query=q,
            top_k=top_k,
            requested_collection=collection,
        )
        t0 = time.time()
        try:
            if not q.strip():
                logger.warning("search_empty_query")
                raise HTTPException(status_code=400, detail=f"查询不能为空；详细日志: {logger.file_name}")

            search_collection = collection.strip() if collection.strip() else None
            if not search_collection:
                with logger.stage("resolve_search_collection"):
                    all_stats = get_all_stats(persist_dir=request.app.state.persist_dir)
                    for coll in all_stats.get("collections", []):
                        if coll["count"] > 0:
                            search_collection = coll["name"]
                            break
                if not search_collection:
                    logger.info("search_no_collection")
                    result = {
                        "results": [],
                        "query": q,
                        "message": "数据库为空，请先上传并处理数据",
                        **_operation_log_payload(logger),
                    }
                    logger.close(status="ok", result_count=0, reason="empty_database")
                    return result

            with logger.stage("query_collection", collection_name=search_collection, top_k=top_k):
                result = query_collection(
                    query_text=q,
                    persist_dir=request.app.state.persist_dir,
                    collection_name=search_collection,
                    top_k=top_k,
                )
            result["latency_ms"] = round((time.time() - t0) * 1000, 1)
            with logger.stage("search_total_stats"):
                result["total_in_db"] = sum(
                    c["count"] for c in get_all_stats(persist_dir=request.app.state.persist_dir).get("collections", [])
                )
            result.update(_operation_log_payload(logger))
            logger.close(status="ok", result_count=len(result.get("results") or []))
            return result
        except HTTPException as exc:
            logger.error("search_rejected", status_code=exc.status_code, detail=exc.detail)
            logger.close(status="error", status_code=exc.status_code, detail=exc.detail)
            raise
        except Exception as exc:
            logger.exception("search_failed", exc, query=q, collection=collection)
            logger.close(status="error", error=str(exc))
            raise HTTPException(status_code=400, detail=f"检索失败: {exc}；详细日志: {logger.file_name}") from exc

    @app.post("/api/search")
    async def search_post(request: Request, payload: SearchRequest):
        """语义检索 (POST + Pydantic 校验)"""
        logger = OperationLogger(
            request.app.state.log_dir,
            "search",
            method="POST",
            query=payload.query,
            top_k=payload.top_k,
            requested_collection=payload.collection,
        )
        t0 = time.time()
        try:
            with logger.stage("query_collection", collection_name=payload.collection, top_k=payload.top_k):
                result = query_collection(
                    query_text=payload.query,
                    persist_dir=request.app.state.persist_dir,
                    collection_name=payload.collection,
                    top_k=payload.top_k,
                )
            result["latency_ms"] = round((time.time() - t0) * 1000, 1)
            result.update(_operation_log_payload(logger))
            logger.close(status="ok", result_count=len(result.get("results") or []))
            return result
        except Exception as exc:
            logger.exception("search_failed", exc, query=payload.query, collection=payload.collection)
            logger.close(status="error", error=str(exc))
            raise HTTPException(status_code=400, detail=f"检索失败: {exc}；详细日志: {logger.file_name}") from exc

    @app.post("/api/benchmark")
    async def benchmark(request: Request, payload: BenchmarkRequest):
        """运行合成性能基准测试"""
        logger = OperationLogger(
            request.app.state.log_dir,
            "benchmark",
            collection_name=payload.collection,
            document_count=payload.document_count,
            batch_size=payload.batch_size,
            query_count=payload.query_count,
            top_k=payload.top_k,
            backend=payload.backend,
            model_name=payload.model_name,
            cleanup=payload.cleanup,
        )
        try:
            result = run_synthetic_benchmark(
                persist_dir=request.app.state.persist_dir,
                collection_name=payload.collection,
                document_count=payload.document_count,
                batch_size=payload.batch_size,
                query_count=payload.query_count,
                top_k=payload.top_k,
                backend=payload.backend,
                model_name=payload.model_name,
                cleanup=payload.cleanup,
                operation_logger=logger,
            )
            result.update(_operation_log_payload(logger))
            logger.close(
                status="ok",
                insert_docs_per_second=result.get("insert_docs_per_second"),
                query_qps=result.get("query_qps"),
            )
            return result
        except Exception as exc:
            logger.exception("benchmark_failed", exc)
            logger.close(status="error", error=str(exc))
            raise HTTPException(status_code=400, detail=f"压测失败: {exc}；详细日志: {logger.file_name}") from exc

    @app.delete("/api/collections/{name}")
    async def delete_collection(request: Request, name: str):
        """删除指定集合"""
        import chromadb
        from chromadb.config import Settings

        persist_dir = request.app.state.persist_dir
        client = chromadb.PersistentClient(
            path=str(persist_dir),
            settings=Settings(anonymized_telemetry=False, is_persistent=True),
        )
        try:
            client.delete_collection(name=name)
            return {"status": "ok", "deleted": name}
        except Exception as exc:
            raise HTTPException(status_code=404, detail=f"集合 '{name}' 不存在") from exc
        finally:
            try:
                client._system.stop()
            except Exception:
                pass

    @app.get("/api/export")
    async def export_all(request: Request):
        """将整个 ChromaDB 持久化目录打包为 ZIP 下载。"""
        persist_dir = request.app.state.persist_dir
        if not persist_dir.exists() or not persist_dir.is_dir():
            raise HTTPException(status_code=404, detail="向量库目录不存在")

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_path in persist_dir.rglob("*"):
                if file_path.is_file():
                    arcname = file_path.relative_to(persist_dir)
                    zf.write(file_path, arcname)
        buffer.seek(0)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"chroma_db_export_{timestamp}.zip"
        return StreamingResponse(
            buffer,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.get("/api/chroma/export")
    async def export_chroma_db(request: Request):
        """Alias used by the console UI for downloading the full ChromaDB directory."""
        return await export_all(request)

    @app.get("/api/export/{collection_name}")
    async def export_collection(request: Request, collection_name: str):
        """导出单个集合的全部文档和元数据为 JSON。"""
        import chromadb
        from chromadb.config import Settings

        persist_dir = request.app.state.persist_dir
        client = chromadb.PersistentClient(
            path=str(persist_dir),
            settings=Settings(anonymized_telemetry=False, is_persistent=True),
        )
        try:
            collection = client.get_collection(name=collection_name)
            count = collection.count()
            if count == 0:
                data = {"collection": collection_name, "count": 0, "ids": [], "documents": [], "metadatas": []}
            else:
                result = collection.get(
                    include=["documents", "metadatas"],
                    limit=count,
                )
                data = {
                    "collection": collection_name,
                    "count": count,
                    "ids": result.get("ids", []),
                    "documents": result.get("documents", []),
                    "metadatas": result.get("metadatas", []),
                }
        except Exception as exc:
            raise HTTPException(status_code=404, detail=f"集合 '{collection_name}' 不存在或读取失败: {exc}") from exc
        finally:
            try:
                client._system.stop()
            except Exception:
                pass

        json_bytes = orjson.dumps(data, option=orjson.OPT_INDENT_2)
        buffer = io.BytesIO(json_bytes)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{collection_name}_{timestamp}.json"
        return StreamingResponse(
            buffer,
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    if FRONTEND_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    return app


app = create_app()
