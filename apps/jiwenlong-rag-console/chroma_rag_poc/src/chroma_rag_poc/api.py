"""
FastAPI 后端 — 合并两版

项目2: 工厂模式 create_app() + Pydantic 校验 + benchmark API
项目1: 分步 API (上传→处理→统计→检索) + 前端静态文件挂载
新增: /api/hybrid-search 混合检索 + /api/health 健康检查
"""
from __future__ import annotations

import os
import time
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .parsing import get_source_kind, is_supported_source, supported_source_extensions
from .benchmark import run_synthetic_benchmark
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


def _safe_upload_name(raw_name: str) -> str:
    clean = normalize_upload_name(raw_name)
    return clean[:220] if len(clean) > 220 else clean


def normalize_upload_name(raw_name: str) -> str:
    parts = [part.strip() for part in Path(raw_name).parts if part not in {"", ".", ".."}]
    if not parts:
        return f"upload-{int(time.time())}.bin"
    flat = "__".join(parts)
    return flat.replace("/", "__").replace("\\", "__")


# ============================================================
# Pydantic 请求模型（来自项目2）
# ============================================================


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


# ============================================================
# App 工厂（来自项目2 + 项目1 API 扩展）
# ============================================================


def create_app(
    persist_dir: Path = DEFAULT_PERSIST_DIR,
    upload_dir: Path = DEFAULT_UPLOAD_DIR,
) -> FastAPI:
    """创建 FastAPI 应用（工厂模式）"""
    app = FastAPI(
        title="动力装备知识库管理系统",
        description="文件上传、向量化、ChromaDB 管理、混合检索、RAG 问答",
        version="2.0.0",
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

    # ----------------------------------------------------------
    # 前端入口
    # ----------------------------------------------------------

    @app.get("/")
    async def index():
        index_path = FRONTEND_DIR / "index.html"
        if index_path.exists():
            return FileResponse(index_path, media_type="text/html; charset=utf-8")
        return JSONResponse({"message": "前端文件未找到，请检查 frontend/index.html"}, status_code=404)

    # ----------------------------------------------------------
    # 健康检查（来自项目2）
    # ----------------------------------------------------------

    @app.get("/api/health")
    async def health():
        return {"status": "ok", "version": "2.0.0"}

    # ----------------------------------------------------------
    # 文件上传（来自项目1）
    # ----------------------------------------------------------

    @app.post("/api/upload")
    async def upload_file(
        request: Request,
        file: UploadFile = File(...),
        relative_path: str | None = Form(default=None),
    ):
        """上传单个文档到待处理队列。"""
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

        return {
            "status": "ok",
            "filename": stored_name,
            "display_name": display_name,
            "size_kb": round(len(content) / 1024, 1),
            "source_kind": get_source_kind(source_name),
        }

    @app.get("/api/uploads")
    async def list_uploads(request: Request):
        """列出已上传的文件"""
        files = []
        for f in sorted(path for path in request.app.state.upload_dir.iterdir() if path.is_file()):
            stat = f.stat()
            files.append({
                "filename": f.name,
                "size_kb": round(stat.st_size / 1024, 1),
                "modified": stat.st_mtime,
                "source_kind": get_source_kind(f.name),
            })
        return {"files": files, "count": len(files)}

    @app.delete("/api/uploads/{filename}")
    async def delete_upload(request: Request, filename: str):
        """删除已上传的文件"""
        fpath = request.app.state.upload_dir / filename
        if not fpath.exists():
            raise HTTPException(status_code=404, detail="文件不存在")
        fpath.unlink()
        return {"status": "ok", "deleted": filename}

    # ----------------------------------------------------------
    # 处理流程（来自项目1 + 项目2 合并）
    # ----------------------------------------------------------

    @app.post("/api/process")
    async def process_files(request: Request, mode: str = "replace"):
        """处理所有已上传文件：解析→清洗→分块→向量化→存入 ChromaDB"""
        upload_files = [path for path in request.app.state.upload_dir.iterdir() if path.is_file()]
        if not upload_files:
            raise HTTPException(status_code=400, detail="没有已上传的可处理文件")

        t0 = time.time()
        try:
            payloads = [(f.name, f.read_bytes()) for f in upload_files]

            result = ingest_source_payloads(
                payloads=payloads,
                persist_dir=request.app.state.persist_dir,
                collection_name="power_equipment",
            )
            result["elapsed_s"] = round(time.time() - t0, 1)
            return result

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"处理失败: {e}")

    # ----------------------------------------------------------
    # 一步式入库（来自项目2）
    # ----------------------------------------------------------

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
        """上传并一步入库（来自项目2）"""
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

        result["saved_files"] = saved_files
        return result

    # ----------------------------------------------------------
    # 统计信息
    # ----------------------------------------------------------

    @app.get("/api/stats")
    async def stats(request: Request, collection: str | None = None):
        """获取 ChromaDB 统计信息"""
        if collection:
            return get_collection_stats(
                persist_dir=request.app.state.persist_dir,
                collection_name=collection,
            )
        return get_all_stats(persist_dir=request.app.state.persist_dir)

    # ----------------------------------------------------------
    # 检索
    # ----------------------------------------------------------

    @app.get("/api/search")
    async def search_get(request: Request, q: str = "", top_k: int = 5, collection: str = ""):
        """语义检索 (GET) — 自动检测有数据的集合"""
        if not q.strip():
            raise HTTPException(status_code=400, detail="查询不能为空")

        t0 = time.time()

        # 自动检测集合：优先用指定的，否则找第一个有数据的集合
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

    # ----------------------------------------------------------
    # 性能基准测试（来自项目2）
    # ----------------------------------------------------------

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

    # ----------------------------------------------------------
    # 集合管理
    # ----------------------------------------------------------

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

    # ----------------------------------------------------------
    # 挂载前端静态文件
    # ----------------------------------------------------------

    if FRONTEND_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    return app


# 默认应用实例
app = create_app()
