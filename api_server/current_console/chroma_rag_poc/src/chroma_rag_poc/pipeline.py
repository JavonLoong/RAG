"""
流程编排 — 合并项目2的规范管理 + 项目1的质量报告

项目2: ChromaDB client 管理、资源释放、telemetry 关闭、upsert
项目1: 数据质量报告、clean_blocks 步骤
"""
from __future__ import annotations

import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Sequence

import chromadb
try:
    from chromadb.errors import InvalidCollectionException as CollectionMissingError
except ImportError:
    from chromadb.errors import NotFoundError as CollectionMissingError
from chromadb.config import Settings

from .chunking import chunk_records
from .cleaning import clean_records
from .embeddings import ResolvedEmbeddingBackend, create_embedding_backend
from .observability import NullOperationLogger
from .parsing import (
    SourceRecord,
    get_source_kind,
    load_json_directory,
    load_json_file,
    load_source_directory,
    load_source_payload,
)
from .text_utils import format_megabytes, get_directory_size, safe_collection_name

PROJECT_ROOT = Path(__file__).resolve().parents[5]


def contains_non_ascii_path(path: str | Path) -> bool:
    return any(ord(char) > 127 for char in str(path))


def resolve_default_runtime_dir(project_root: str | Path = PROJECT_ROOT) -> Path:
    explicit = os.environ.get("POWER_RAG_RUNTIME_DIR")
    if explicit:
        return Path(explicit)

    repo_runtime_dir = Path(project_root) / "storage_layer" / "runtime" / "current_console"
    if os.name == "nt" and contains_non_ascii_path(repo_runtime_dir):
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data and not contains_non_ascii_path(local_app_data):
            return Path(local_app_data) / "PowerRAG" / "current_console"

    return repo_runtime_dir


DEFAULT_RUNTIME_DIR = resolve_default_runtime_dir()
DEFAULT_PERSIST_DIR = DEFAULT_RUNTIME_DIR / "chroma"
DEFAULT_UPLOAD_DIR = DEFAULT_RUNTIME_DIR / "uploads"
DEFAULT_HNSW_BATCH_SIZE = 100
DEFAULT_HNSW_SYNC_THRESHOLD = 100


# ============================================================
# 核心入库流程
# ============================================================


def ingest_source_payloads(
    payloads: Sequence[tuple[str, bytes]],
    persist_dir: Path = DEFAULT_PERSIST_DIR,
    collection_name: str = "power_equipment",
    chunk_size: int = 500,
    overlap: int = 50,
    backend: str | None = None,
    model_name: str | None = None,
    clean: bool = True,
    operation_logger=None,
) -> dict:
    """
    完整入库流程：解析 → 清洗 → 分块 → 向量化 → 存储

    支持 JSON / PDF / DOCX / TXT / Markdown / CSV / TSV。
    单个文件解析失败时会记录到摘要中，但不会阻断整批处理。
    """
    log = operation_logger or NullOperationLogger()
    log.info(
        "ingest_start",
        file_count=len(payloads),
        collection_name=collection_name,
        chunk_size=chunk_size,
        overlap=overlap,
        backend=backend,
        model_name=model_name,
        clean=clean,
    )

    source_records: list[SourceRecord] = []
    file_summaries: list[dict] = []

    for source_name, raw_bytes in payloads:
        source_kind = get_source_kind(source_name)
        try:
            with log.stage(
                "parse_file",
                source_file=source_name,
                source_kind=source_kind,
                size_bytes=len(raw_bytes),
                size_mb=round(len(raw_bytes) / (1024 * 1024), 3),
            ):
                records = load_source_payload(raw_bytes, source_name=source_name)
            block_count = sum(len(record.blocks) for record in records)
            char_count = sum(len(record.text) for record in records)
            log.info(
                "parse_file_summary",
                source_file=source_name,
                records_extracted=len(records),
                blocks_extracted=block_count,
                chars_extracted=char_count,
            )
            source_records.extend(records)
            file_summaries.append(
                {
                    "source_file": source_name,
                    "source_kind": source_kind,
                    "status": "ok",
                    "records_extracted": len(records),
                }
            )
        except Exception as exc:
            log.exception(
                "parse_file_failed",
                exc,
                source_file=source_name,
                source_kind=source_kind,
                size_bytes=len(raw_bytes),
            )
            file_summaries.append(
                {
                    "source_file": source_name,
                    "source_kind": source_kind,
                    "status": "error",
                    "records_extracted": 0,
                    "error": str(exc),
                }
            )

    if not source_records:
        error_summary = "; ".join(
            f"{item['source_file']}: {item.get('error', '未提取到可用内容')}"
            for item in file_summaries
        )
        log.error("ingest_no_source_records", file_summaries=file_summaries, error_summary=error_summary)
        raise ValueError(f"所有文件解析失败：{error_summary}")

    if clean:
        with log.stage("clean_records", record_count=len(source_records)):
            before_blocks = sum(len(r.blocks) for r in source_records)
            source_records = clean_records(source_records)
            after_blocks = sum(len(r.blocks) for r in source_records)
        cleaning_summary = {
            "blocks_before": before_blocks,
            "blocks_after": after_blocks,
            "fragments_merged": before_blocks - after_blocks,
        }
        log.info("cleaning_summary", **cleaning_summary)
    else:
        cleaning_summary = None

    with log.stage("chunk_records", record_count=len(source_records), chunk_size=chunk_size, overlap=overlap):
        chunks = chunk_records(source_records, chunk_size=chunk_size, overlap=overlap)
    log.info(
        "chunk_summary",
        chunks_written=len(chunks),
        estimated_tokens=sum(int(chunk.metadata.get("estimated_tokens") or 0) for chunk in chunks),
        chars=sum(int(chunk.metadata.get("char_count") or 0) for chunk in chunks),
    )

    with log.stage("quality_report", record_count=len(source_records), chunk_count=len(chunks)):
        quality = quality_report(source_records, chunks)
    log.info("quality_summary", issue_count=quality.get("issue_count"), issues=quality.get("issues"))

    resolved_backend: ResolvedEmbeddingBackend | None = None
    if chunks:
        with log.stage("open_collection", persist_dir=persist_dir, collection_name=collection_name):
            client, collection, resolved_backend = get_collection_handle(
                persist_dir=persist_dir,
                collection_name=collection_name,
                backend=backend,
                model_name=model_name,
            )
        log.info(
            "embedding_backend_resolved",
            backend=resolved_backend.name,
            model_name=resolved_backend.model_name,
            dimension=resolved_backend.dimension,
            warning=resolved_backend.warning,
        )
        try:
            # 分批 upsert（避免内存溢出）
            BATCH_SIZE = 100
            for i in range(0, len(chunks), BATCH_SIZE):
                batch = chunks[i:i + BATCH_SIZE]
                batch_no = i // BATCH_SIZE + 1
                with log.stage(
                    "upsert_batch",
                    batch_no=batch_no,
                    batch_size=len(batch),
                    start_index=i,
                    end_index=i + len(batch),
                ):
                    collection.upsert(
                        ids=[chunk.chunk_id for chunk in batch],
                        documents=[chunk.text for chunk in batch],
                        metadatas=[chunk.metadata for chunk in batch],
                    )
        finally:
            with log.stage("close_collection_client"):
                _close_client(client)

    with log.stage("collection_stats", persist_dir=persist_dir, collection_name=collection_name):
        stats = get_collection_stats(persist_dir=persist_dir, collection_name=collection_name)
    if resolved_backend is None:
        with log.stage("resolve_embedding_backend", backend=backend, model_name=model_name):
            resolved_backend = create_embedding_backend(backend=backend, model_name=model_name)

    result = {
        "collection": safe_collection_name(collection_name),
        "files_processed": len(payloads),
        "files_succeeded": sum(1 for item in file_summaries if item["status"] == "ok"),
        "files_failed": sum(1 for item in file_summaries if item["status"] == "error"),
        "records_processed": len(source_records),
        "chunks_written": len(chunks),
        "chunk_size": chunk_size,
        "overlap": overlap,
        "embedding_backend": resolved_backend.name,
        "embedding_model": resolved_backend.model_name,
        "embedding_warning": resolved_backend.warning,
        "file_summaries": file_summaries,
        "stats": stats,
        "quality_report": quality,
    }
    if cleaning_summary:
        result["cleaning"] = cleaning_summary

    log.info(
        "ingest_result",
        files_processed=result["files_processed"],
        files_succeeded=result["files_succeeded"],
        files_failed=result["files_failed"],
        records_processed=result["records_processed"],
        chunks_written=result["chunks_written"],
    )
    return result


def ingest_json_payloads(
    payloads: Sequence[tuple[str, bytes]],
    persist_dir: Path = DEFAULT_PERSIST_DIR,
    collection_name: str = "power_equipment",
    chunk_size: int = 500,
    overlap: int = 50,
    backend: str | None = None,
    model_name: str | None = None,
    clean: bool = True,
) -> dict:
    return ingest_source_payloads(
        payloads=payloads,
        persist_dir=persist_dir,
        collection_name=collection_name,
        chunk_size=chunk_size,
        overlap=overlap,
        backend=backend,
        model_name=model_name,
        clean=clean,
    )


def ingest_from_directory(
    json_dir: str | Path,
    persist_dir: Path = DEFAULT_PERSIST_DIR,
    collection_name: str = "power_equipment",
    chunk_size: int = 500,
    overlap: int = 50,
    backend: str | None = None,
    model_name: str | None = None,
    clean: bool = True,
) -> dict:
    """从目录批量入库，自动识别支持的文件类型。"""
    source_dir = Path(json_dir)
    payloads: list[tuple[str, bytes]] = []
    for source_path in sorted(source_dir.rglob("*")):
        if source_path.is_file() and get_source_kind(source_path.name) != "Other":
            payloads.append((source_path.name, source_path.read_bytes()))

    return ingest_source_payloads(
        payloads=payloads,
        persist_dir=persist_dir,
        collection_name=collection_name,
        chunk_size=chunk_size,
        overlap=overlap,
        backend=backend,
        model_name=model_name,
        clean=clean,
    )


# ============================================================
# 查询
# ============================================================


def query_collection(
    query_text: str,
    persist_dir: Path = DEFAULT_PERSIST_DIR,
    collection_name: str = "power_equipment",
    top_k: int = 5,
    backend: str | None = None,
    model_name: str | None = None,
) -> dict:
    """语义检索（来自项目2）"""
    client, collection, resolved_backend = get_collection_handle(
        persist_dir=persist_dir,
        collection_name=collection_name,
        backend=backend,
        model_name=model_name,
    )
    try:
        if collection.count() == 0:
            return {
                "collection": safe_collection_name(collection_name),
                "query": query_text,
                "top_k": top_k,
                "results": [],
                "embedding_backend": resolved_backend.name,
                "embedding_model": resolved_backend.model_name,
                "embedding_warning": resolved_backend.warning,
            }

        raw_results = collection.query(
            query_texts=[query_text],
            n_results=min(top_k, collection.count()),
            include=["documents", "metadatas", "distances"],
        )
        documents = raw_results.get("documents", [[]])[0]
        metadatas = raw_results.get("metadatas", [[]])[0]
        distances = raw_results.get("distances", [[]])[0]

        results = []
        for document, metadata, distance in zip(documents, metadatas, distances):
            results.append({
                "text": document,
                "distance": distance,
                "score": round(1 / (1 + max(distance, 0)), 6),
                "similarity": round(1 - distance, 4),
                "metadata": metadata,
            })

        return {
            "collection": safe_collection_name(collection_name),
            "query": query_text,
            "top_k": top_k,
            "results": results,
            "embedding_backend": resolved_backend.name,
            "embedding_model": resolved_backend.model_name,
            "embedding_warning": resolved_backend.warning,
        }
    finally:
        _close_client(client)


# ============================================================
# ChromaDB 统计
# ============================================================


def get_collection_stats(
    persist_dir: Path = DEFAULT_PERSIST_DIR,
    collection_name: str = "power_equipment",
) -> dict:
    """获取 ChromaDB 集合统计信息（合并两版）"""
    persist_dir = Path(persist_dir)
    persist_dir.mkdir(parents=True, exist_ok=True)
    safe_name = safe_collection_name(collection_name)
    try:
        client = _create_client(persist_dir)
    except Exception as exc:
        stats = _empty_stats(collection_name=safe_name, persist_dir=persist_dir)
        stats["status"] = "error"
        stats["error"] = str(exc)
        return stats

    try:
        collection = client.get_collection(name=safe_name)
    except (CollectionMissingError, ValueError):
        _close_client(client)
        return _empty_stats(collection_name=safe_name, persist_dir=persist_dir)

    try:
        total_count = collection.count()
        if total_count == 0:
            return _empty_stats(
                collection_name=safe_name,
                persist_dir=persist_dir,
                metadata=collection.metadata or {},
            )

        payload = collection.get(limit=min(total_count, 500), include=["metadatas"])
        metadatas = payload.get("metadatas") or []

        source_files = {meta.get("source_file") for meta in metadatas if meta.get("source_file")}
        record_ids = {meta.get("record_id") for meta in metadatas if meta.get("record_id")}
        total_chars = sum(int(meta.get("char_count") or 0) for meta in metadatas)
        total_tokens = sum(int(meta.get("estimated_tokens") or 0) for meta in metadatas)
        total_blocks = sum(int(meta.get("block_count") or 0) for meta in metadatas)
        storage_bytes = get_directory_size(persist_dir)
        metadata = collection.metadata or {}

        # 获取文档来源文件名列表
        filenames = sorted({meta.get("filename") for meta in metadatas if meta.get("filename")})

        return {
            "collection": safe_name,
            "chunk_count": total_count,
            "record_count": len(record_ids),
            "source_file_count": len(source_files),
            "block_count": total_blocks,
            "char_count": total_chars,
            "estimated_token_count": total_tokens,
            "persist_dir": str(persist_dir),
            "persist_dir_storage_bytes": storage_bytes,
            "persist_dir_storage_mb": format_megabytes(storage_bytes),
            "embedding_backend": metadata.get("embedding_backend", "unknown"),
            "embedding_model": metadata.get("embedding_model", "unknown"),
            "filenames": filenames,
        }
    finally:
        _close_client(client)


def get_all_stats(persist_dir: Path = DEFAULT_PERSIST_DIR) -> dict:
    """获取所有集合的统计信息（用于前端展示）"""
    persist_dir = Path(persist_dir)
    if not persist_dir.exists():
        return {
            "status": "empty",
            "collections": [],
            "total_documents": 0,
            "total_tokens_estimate": 0,
            "storage_size_mb": 0,
            "source_type_breakdown": {},
        }

    client = None
    try:
        client = _create_client(persist_dir)
        try:
            collections = client.list_collections()

            total_docs = 0
            total_chars = 0
            collection_details = []
            source_type_breakdown: dict[str, int] = {}

            for coll in collections:
                count = coll.count()
                total_docs += count

                coll_chars = 0
                sources = []
                type_counts: dict[str, int] = {}
                if count > 0:
                    sample_size = min(count, 100)
                    sample = coll.peek(limit=sample_size)
                    if sample["documents"]:
                        avg_len = sum(len(d) for d in sample["documents"]) / len(sample["documents"])
                        coll_chars = int(avg_len * count)
                        total_chars += coll_chars
                    if sample["metadatas"]:
                        sources = sorted({
                            meta.get("filename") or meta.get("source_file", "")
                            for meta in sample["metadatas"]
                            if meta
                        } - {""})
                        sample_count = max(len(sample["metadatas"]), 1)
                        scale = count / sample_count
                        for meta in sample["metadatas"]:
                            if not meta:
                                continue
                            source_name = meta.get("filename") or meta.get("source_file", "")
                            kind = str(meta.get("source_kind") or get_source_kind(source_name))
                            type_counts[kind] = type_counts.get(kind, 0) + 1
                        type_counts = {
                            kind: max(1, int(round(value * scale)))
                            for kind, value in type_counts.items()
                        }
                        for kind, value in type_counts.items():
                            source_type_breakdown[kind] = source_type_breakdown.get(kind, 0) + value

                collection_details.append({
                    "name": coll.name,
                    "count": count,
                    "estimated_chars": coll_chars,
                    "estimated_tokens": int(coll_chars * 0.6),
                    "sources": sources,
                    "source_type_counts": type_counts,
                })

            storage_bytes = get_directory_size(persist_dir)

            return {
                "status": "ok",
                "collections": collection_details,
                "total_documents": total_docs,
                "total_chars": total_chars,
                "total_tokens_estimate": int(total_chars * 0.6),
                "storage_size_mb": round(storage_bytes / (1024 * 1024), 2),
                "storage_size_bytes": storage_bytes,
                "embedding_dim": 1024,
                "source_type_breakdown": source_type_breakdown,
            }
        except Exception as exc:
            storage_bytes = get_directory_size(persist_dir)
            return {
                "status": "error",
                "collections": [],
                "total_documents": 0,
                "total_chars": 0,
                "total_tokens_estimate": 0,
                "storage_size_mb": round(storage_bytes / (1024 * 1024), 2),
                "storage_size_bytes": storage_bytes,
                "embedding_dim": 1024,
                "source_type_breakdown": {},
                "error": str(exc),
            }
    except Exception as exc:
        storage_bytes = get_directory_size(persist_dir)
        return {
            "status": "error",
            "collections": [],
            "total_documents": 0,
            "total_chars": 0,
            "total_tokens_estimate": 0,
            "storage_size_mb": round(storage_bytes / (1024 * 1024), 2),
            "storage_size_bytes": storage_bytes,
            "embedding_dim": 1024,
            "source_type_breakdown": {},
            "error": str(exc),
        }
    finally:
        if client is not None:
            _close_client(client)


# ============================================================
# 数据质量报告（来自项目1）
# ============================================================


def quality_report(records: list[SourceRecord], chunks: list) -> dict:
    """自动检测数据质量问题（来自项目1）"""
    issues = []
    doc_summaries = []

    # 按 doc_id 分组
    docs: dict[int, list[SourceRecord]] = {}
    for r in records:
        docs.setdefault(r.doc_id, []).append(r)

    for doc_id, doc_records in docs.items():
        all_blocks = []
        for r in doc_records:
            all_blocks.extend(r.blocks)

        label_counts: dict[str, int] = {}
        for b in all_blocks:
            label_counts[b.block_type] = label_counts.get(b.block_type, 0) + 1

        short_blocks = [b for b in all_blocks if len(b.text) < 5]
        if short_blocks:
            issues.append(f"doc{doc_id}: {len(short_blocks)} 个极短文本块（<5字符）")

        filenames = {r.filename for r in doc_records}
        doc_summaries.append({
            "doc_id": doc_id,
            "filenames": sorted(filenames),
            "block_count": len(all_blocks),
            "label_distribution": label_counts,
            "short_blocks": len(short_blocks),
        })

    # chunk 统计
    chunk_lengths = [len(c.text) if hasattr(c, 'text') else 0 for c in chunks]
    chunk_stats = {}
    if chunk_lengths:
        chunk_stats = {
            "total_chunks": len(chunks),
            "avg_length": round(sum(chunk_lengths) / len(chunk_lengths)),
            "min_length": min(chunk_lengths),
            "max_length": max(chunk_lengths),
        }

    return {
        "documents": doc_summaries,
        "chunks": chunk_stats,
        "issues": issues,
        "issue_count": len(issues),
    }


# ============================================================
# ChromaDB 客户端管理（来自项目2）
# ============================================================


def get_collection_handle(
    persist_dir: Path,
    collection_name: str,
    backend: str | None = None,
    model_name: str | None = None,
) -> tuple[chromadb.PersistentClient, object, ResolvedEmbeddingBackend]:
    """获取 ChromaDB 集合句柄"""
    persist_dir = Path(persist_dir)
    persist_dir.mkdir(parents=True, exist_ok=True)
    client = _create_client(persist_dir)
    safe_name = safe_collection_name(collection_name)

    existing_metadata: dict = {}
    try:
        existing = client.get_collection(name=safe_name)
        existing_metadata = existing.metadata or {}
        collection_exists = True
    except (CollectionMissingError, ValueError):
        collection_exists = False

    resolved_backend = create_embedding_backend(
        backend=backend or existing_metadata.get("embedding_backend"),
        model_name=model_name or existing_metadata.get("embedding_model"),
    )

    if collection_exists:
        collection = client.get_collection(
            name=safe_name, embedding_function=resolved_backend.function
        )
    else:
        metadata = {
            "hnsw:space": "cosine",
            "hnsw:batch_size": DEFAULT_HNSW_BATCH_SIZE,
            "hnsw:sync_threshold": DEFAULT_HNSW_SYNC_THRESHOLD,
            "embedding_backend": resolved_backend.name,
            "embedding_model": resolved_backend.model_name,
        }
        collection = client.create_collection(
            name=safe_name,
            embedding_function=resolved_backend.function,
            metadata=metadata,
        )

    return client, collection, resolved_backend


def _create_client(persist_dir: Path) -> chromadb.PersistentClient:
    """创建 ChromaDB 客户端（关闭 telemetry 解决报错）"""
    persist_dir = Path(persist_dir)
    persist_dir.mkdir(parents=True, exist_ok=True)
    try:
        return _open_chroma_client(persist_dir)
    except Exception as exc:
        if not _should_recover_chroma_store(persist_dir, exc):
            raise
        backup_dir = _quarantine_chroma_store(persist_dir, exc)
        persist_dir.mkdir(parents=True, exist_ok=True)
        print(f"Recovered unusable Chroma store by moving it to {backup_dir}")
        return _open_chroma_client(persist_dir)


def _open_chroma_client(persist_dir: Path) -> chromadb.PersistentClient:
    return chromadb.PersistentClient(
        path=str(persist_dir),
        settings=Settings(anonymized_telemetry=False, is_persistent=True),
    )


def _should_recover_chroma_store(persist_dir: Path, exc: Exception) -> bool:
    if not persist_dir.exists() or not persist_dir.is_dir():
        return False
    has_chroma_artifacts = any(
        (persist_dir / name).exists()
        for name in ("chroma.sqlite3", "index", "chroma-collections.parquet", "chroma-embeddings.parquet")
    )
    if not has_chroma_artifacts:
        try:
            has_chroma_artifacts = any(persist_dir.iterdir())
        except OSError:
            return False
    if not has_chroma_artifacts:
        return False

    message = str(exc).lower()
    recoverable_markers = (
        "default_tenant",
        "could not connect to tenant",
        "no such table",
        "file is not a database",
        "database disk image is malformed",
        "sqlite",
        "migration",
        "tenant",
    )
    return any(marker in message for marker in recoverable_markers)


def _quarantine_chroma_store(persist_dir: Path, exc: Exception) -> Path:
    parent = persist_dir.parent
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = parent / f"{persist_dir.name}_broken_{timestamp}"
    counter = 1
    while backup_dir.exists():
        backup_dir = parent / f"{persist_dir.name}_broken_{timestamp}_{counter}"
        counter += 1

    shutil.move(str(persist_dir), str(backup_dir))
    notice = {
        "reason": str(exc),
        "original_dir": str(persist_dir),
        "recovered_at": datetime.now().isoformat(timespec="seconds"),
        "note": "This Chroma store could not be opened and was moved aside so a clean store could be created.",
    }
    try:
        (backup_dir / "RECOVERY_NOTICE.json").write_text(
            json.dumps(notice, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        pass
    return backup_dir


def _close_client(client: chromadb.PersistentClient) -> None:
    """安全关闭 ChromaDB 客户端（释放资源）"""
    try:
        client._system.stop()
    except Exception:
        pass
    try:
        client.clear_system_cache()
    except Exception:
        pass


def _empty_stats(collection_name: str, persist_dir: Path, metadata: dict | None = None) -> dict:
    metadata = metadata or {}
    storage_bytes = get_directory_size(persist_dir)
    return {
        "collection": collection_name,
        "chunk_count": 0,
        "record_count": 0,
        "source_file_count": 0,
        "block_count": 0,
        "char_count": 0,
        "estimated_token_count": 0,
        "persist_dir": str(persist_dir),
        "persist_dir_storage_bytes": storage_bytes,
        "persist_dir_storage_mb": format_megabytes(storage_bytes),
        "embedding_backend": metadata.get("embedding_backend", "unknown"),
        "embedding_model": metadata.get("embedding_model", "unknown"),
        "filenames": [],
    }
