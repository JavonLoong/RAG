"""
FastAPI 后端 — 合并两版

项目2: 工厂模式 create_app() + Pydantic 校验 + benchmark API
项目1: 分步 API (上传→处理→统计→检索) + 前端静态文件挂载
新增: 上传状态清单、按勾选处理、已处理文件批量删除
"""
from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

import orjson
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .benchmark import run_synthetic_benchmark
from .parsing import get_source_kind, is_supported_source, supported_source_extensions
from .pipeline import (
    DEFAULT_PERSIST_DIR,
    DEFAULT_UPLOAD_DIR,
    get_all_stats,
    get_collection_stats,
    ingest_source_payloads,
    query_collection,
)

PACKAGE_FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"
WORKSPACE_FRONTEND_DIR = Path(__file__).resolve().parents[3] / "frontend"
FRONTEND_DIR = WORKSPACE_FRONTEND_DIR if WORKSPACE_FRONTEND_DIR.exists() else PACKAGE_FRONTEND_DIR
SUPPORTED_EXTENSIONS_LABEL = ", ".join(supported_source_extensions())
UPLOAD_MANIFEST_NAME = ".upload-manifest.json"


def _safe_upload_name(raw_name: str) -> str:
    clean = normalize_upload_name(raw_name)
    return clean[:220] if len(clean) > 220 else clean


def normalize_upload_name(raw_name: str) -> str:
    parts = [part.strip() for part in Path(raw_name).parts if part not in {"", ".", ".."}]
    if not parts:
        return f"upload-{int(time.time())}.bin"
    flat = "__".join(parts)
    return flat.replace("/", "__").replace("\\", "__")


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


def _mark_process_result(upload_dir: Path, result: dict, collection_name: str) -> None:
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
        manifest[filename] = current

    _write_upload_manifest(upload_dir, manifest)


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


class DeleteUploadsRequest(BaseModel):
    filenames: list[str] = Field(default_factory=list)
    purge_vectors: bool = False


def create_app(
    persist_dir: Path = DEFAULT_PERSIST_DIR,
    upload_dir: Path = DEFAULT_UPLOAD_DIR,
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
    app.state.persist_dir.mkdir(parents=True, exist_ok=True)
    app.state.upload_dir.mkdir(parents=True, exist_ok=True)

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
        if not is_supported_source(source_name):
            raise HTTPException(
                status_code=400,
                detail=f"暂不支持该文件类型。当前支持: {SUPPORTED_EXTENSIONS_LABEL}",
            )

        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="上传文件为空")

        display_name = relative_path.strip() if relative_path else source_name
        stored_name = _safe_upload_name(relative_path or source_name)
        save_path = request.app.state.upload_dir / stored_name
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
        )

        return {
            "status": "ok",
            "filename": stored_name,
            "display_name": display_name,
            "size_kb": round(len(content) / 1024, 1),
            "source_kind": get_source_kind(source_name),
        }

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

    @app.delete("/api/uploads/{filename}")
    async def delete_upload(request: Request, filename: str, purge_vectors: bool = False):
        """删除单个上传文件；如需要可同步删库。"""
        fpath = request.app.state.upload_dir / filename
        manifest = _read_upload_manifest(request.app.state.upload_dir)
        if not fpath.exists() and filename not in manifest:
            raise HTTPException(status_code=404, detail="文件不存在")

        purge_result = {"chunks_deleted": 0, "collections": {}}
        if purge_vectors:
            purge_result = _purge_vectors_by_source_files(request.app.state.persist_dir, [filename])

        if fpath.exists():
            fpath.unlink()
        _remove_upload_entries(request.app.state.upload_dir, [filename])
        return {"status": "ok", "deleted": filename, **purge_result}

    @app.post("/api/uploads/delete")
    async def delete_uploads(request: Request, payload: DeleteUploadsRequest):
        filenames = [str(name).strip() for name in payload.filenames if str(name).strip()]
        if not filenames:
            raise HTTPException(status_code=400, detail="没有选中的文件")

        purge_result = {"chunks_deleted": 0, "collections": {}}
        if payload.purge_vectors:
            purge_result = _purge_vectors_by_source_files(request.app.state.persist_dir, filenames)

        deleted: list[str] = []
        for filename in filenames:
            fpath = request.app.state.upload_dir / filename
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

        upload_files = [
            request.app.state.upload_dir / entry["filename"]
            for entry in selected_entries
            if (request.app.state.upload_dir / entry["filename"]).exists()
        ]
        if not upload_files:
            raise HTTPException(status_code=400, detail="没有可处理的待处理文件")

        t0 = time.time()
        try:
            payloads = [(f.name, f.read_bytes()) for f in upload_files]
            collection_name = (payload.collection if payload else "power_equipment").strip() or "power_equipment"

            result = ingest_source_payloads(
                payloads=payloads,
                persist_dir=request.app.state.persist_dir,
                collection_name=collection_name,
            )
            _mark_process_result(
                request.app.state.upload_dir,
                result=result,
                collection_name=collection_name,
            )
            result["elapsed_s"] = round(time.time() - t0, 1)
            result["requested_filenames"] = [f.name for f in upload_files]
            result["skipped_already_processed"] = skipped_processed
            return result

        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"处理失败: {exc}") from exc

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
        if not files:
            raise HTTPException(status_code=400, detail="No files uploaded")

        payloads: list[tuple[str, bytes]] = []
        saved_files: list[str] = []
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

        for index, upload in enumerate(files):
            raw_bytes = await upload.read()
            if not raw_bytes:
                continue
            source_name = Path(upload.filename or f"upload-{index}.bin").name
            if not is_supported_source(source_name):
                raise HTTPException(
                    status_code=400,
                    detail=f"{source_name} 类型不受支持。当前支持: {SUPPORTED_EXTENSIONS_LABEL}",
                )
            payloads.append((source_name, raw_bytes))
            saved_name = f"{timestamp}-{index}-{_safe_upload_name(source_name)}"
            target = request.app.state.upload_dir / saved_name
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
            )
            saved_files.append(str(target))

        if not payloads:
            raise HTTPException(status_code=400, detail="上传文件为空")

        try:
            result = ingest_source_payloads(
                payloads=payloads,
                persist_dir=request.app.state.persist_dir,
                collection_name=collection,
                chunk_size=chunk_size,
                overlap=overlap,
                backend=backend,
                model_name=model_name,
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        _mark_process_result(
            request.app.state.upload_dir,
            result=result,
            collection_name=collection,
        )
        result["saved_files"] = saved_files
        return result

    @app.get("/api/stats")
    async def stats(request: Request, collection: str | None = None):
        """获取 ChromaDB 统计信息"""
        if collection:
            return get_collection_stats(
                persist_dir=request.app.state.persist_dir,
                collection_name=collection,
            )
        return get_all_stats(persist_dir=request.app.state.persist_dir)

    @app.get("/api/search")
    async def search_get(request: Request, q: str = "", top_k: int = 5, collection: str = ""):
        """语义检索 (GET) — 自动检测有数据的集合"""
        if not q.strip():
            raise HTTPException(status_code=400, detail="查询不能为空")

        t0 = time.time()
        search_collection = collection.strip() if collection.strip() else None
        if not search_collection:
            all_stats = get_all_stats(persist_dir=request.app.state.persist_dir)
            for coll in all_stats.get("collections", []):
                if coll["count"] > 0:
                    search_collection = coll["name"]
                    break
            if not search_collection:
                return {"results": [], "query": q, "message": "数据库为空，请先上传并处理数据"}

        result = query_collection(
            query_text=q,
            persist_dir=request.app.state.persist_dir,
            collection_name=search_collection,
            top_k=top_k,
        )
        result["latency_ms"] = round((time.time() - t0) * 1000, 1)
        result["total_in_db"] = sum(
            c["count"] for c in get_all_stats(persist_dir=request.app.state.persist_dir).get("collections", [])
        )
        return result

    @app.post("/api/search")
    async def search_post(request: Request, payload: SearchRequest):
        """语义检索 (POST + Pydantic 校验)"""
        t0 = time.time()
        try:
            result = query_collection(
                query_text=payload.query,
                persist_dir=request.app.state.persist_dir,
                collection_name=payload.collection,
                top_k=payload.top_k,
            )
            result["latency_ms"] = round((time.time() - t0) * 1000, 1)
            return result
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/benchmark")
    async def benchmark(request: Request, payload: BenchmarkRequest):
        """运行合成性能基准测试"""
        try:
            return run_synthetic_benchmark(
                persist_dir=request.app.state.persist_dir,
                collection_name=payload.collection,
                document_count=payload.document_count,
                batch_size=payload.batch_size,
                query_count=payload.query_count,
                top_k=payload.top_k,
                backend=payload.backend,
                model_name=payload.model_name,
                cleanup=payload.cleanup,
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

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

    if FRONTEND_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    return app


app = create_app()
