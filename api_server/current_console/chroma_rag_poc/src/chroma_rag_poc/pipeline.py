"""
流程编排 — 合并项目2的规范管理 + 项目1的质量报告

项目2: ChromaDB client 管理、资源释放、telemetry 关闭、upsert
项目1: 数据质量报告、clean_blocks 步骤
"""
from __future__ import annotations

import json
import hashlib
import hmac
import os
import re
import shutil
import smtplib
import sqlite3
from collections.abc import Mapping, Sequence as ABCSequence
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Sequence
from urllib.error import HTTPError

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
RETRIEVAL_POLICY_FILENAME = "retrieval_policies.json"
_KEYWORD_RETRIEVER_CACHE: dict[tuple[str, str, int, int], Any] = {}
_KEYWORD_RETRIEVER_CACHE_MAX = 4
_SEARCH_RERANKER_CACHE: dict[str, Any] = {}


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
    parser_backend: str = "auto",
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
        parser_backend=parser_backend,
    )

    source_records: list[SourceRecord] = []
    intake_chunks: list[Any] = []
    file_summaries: list[dict] = []
    try:
        from data_pipeline import DocumentIntakeOptions, run_document_intake
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("data_pipeline.document_intake is required for source ingestion") from exc
    intake_options = DocumentIntakeOptions(parser_backend=parser_backend)

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
                intake_result = run_document_intake(
                    source_name,
                    raw_bytes,
                    chunk_size=chunk_size,
                    overlap=overlap,
                    clean=clean,
                    allow_partial=True,
                    options=intake_options,
                )
            intake_payload = intake_result.to_dict()
            profile = intake_payload.get("profile", {})
            processing_plan = intake_payload.get("processing_plan", {})
            intake_status = str(intake_payload.get("status") or intake_result.status)
            records = intake_result.records
            chunks_for_file = intake_result.chunks
            block_count = sum(len(record.blocks) for record in records)
            char_count = sum(len(record.text) for record in records)
            log.info(
                "parse_file_summary",
                source_file=source_name,
                intake_status=intake_status,
                parser_route=profile.get("parser_route"),
                records_extracted=len(records),
                blocks_extracted=block_count,
                chars_extracted=char_count,
            )
            if intake_status == "parsed":
                source_records.extend(records)
                intake_chunks.extend(chunks_for_file)
            file_summaries.append(
                {
                    "source_file": source_name,
                    "source_kind": profile.get("source_kind") or source_kind,
                    "status": "ok" if intake_status == "parsed" else intake_status,
                    "intake_status": intake_status,
                    "parser_route": profile.get("parser_route"),
                    "processing_plan": processing_plan,
                    "page_diagnostics": intake_payload.get("page_diagnostics", []),
                    "chunk_preview": intake_payload.get("chunk_preview", []),
                    "warnings": intake_payload.get("warnings", []),
                    "errors": intake_payload.get("errors", []),
                    "records_extracted": len(records),
                    "chunks_extracted": len(chunks_for_file),
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
                    "intake_status": "failed",
                    "parser_route": None,
                    "processing_plan": {},
                    "page_diagnostics": [],
                    "chunk_preview": [],
                    "warnings": [],
                    "errors": [str(exc)],
                    "records_extracted": 0,
                    "chunks_extracted": 0,
                    "error": str(exc),
                }
            )

    if not source_records:
        files_needing_ocr = sum(1 for item in file_summaries if item.get("intake_status") == "needs_ocr")
        if files_needing_ocr:
            result = {
                "collection": safe_collection_name(collection_name),
                "files_processed": len(payloads),
                "files_succeeded": 0,
                "files_failed": sum(1 for item in file_summaries if item["status"] == "error"),
                "files_needing_ocr": files_needing_ocr,
                "records_processed": 0,
                "chunks_written": 0,
                "chunk_size": chunk_size,
                "overlap": overlap,
                "embedding_backend": backend or "not_required",
                "embedding_model": model_name,
                "embedding_warning": None,
                "parser_backend": parser_backend,
                "document_intake": {
                    "files_parsed": 0,
                    "files_failed": sum(1 for item in file_summaries if item["status"] == "error"),
                    "files_needing_ocr": files_needing_ocr,
                    "parser_backends": sorted(
                        {
                            str((item.get("processing_plan") or {}).get("parser_backend"))
                            for item in file_summaries
                            if (item.get("processing_plan") or {}).get("parser_backend")
                        }
                    ),
                },
                "file_summaries": file_summaries,
                "stats": {},
                "quality_report": {"issue_count": 0, "issues": [], "status": "needs_ocr"},
            }
            log.info(
                "ingest_result",
                files_processed=result["files_processed"],
                files_succeeded=result["files_succeeded"],
                files_failed=result["files_failed"],
                files_needing_ocr=result["files_needing_ocr"],
                records_processed=0,
                chunks_written=0,
            )
            return result
        error_summary = "; ".join(
            f"{item['source_file']}: {item.get('error', '未提取到可用内容')}"
            for item in file_summaries
        )
        log.error("ingest_no_source_records", file_summaries=file_summaries, error_summary=error_summary)
        raise ValueError(f"所有文件解析失败：{error_summary}")

    if clean:
        with log.stage("clean_records", record_count=len(source_records), source="document_intake"):
            before_blocks = sum(len(r.blocks) for r in source_records)
            after_blocks = before_blocks
        cleaning_summary = {
            "blocks_before": before_blocks,
            "blocks_after": after_blocks,
            "fragments_merged": before_blocks - after_blocks,
            "source": "document_intake",
        }
        log.info("cleaning_summary", **cleaning_summary)
    else:
        cleaning_summary = None

    with log.stage("chunk_records", record_count=len(source_records), chunk_size=chunk_size, overlap=overlap):
        chunks = list(intake_chunks) if intake_chunks else chunk_records(source_records, chunk_size=chunk_size, overlap=overlap)
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
        "files_needing_ocr": sum(1 for item in file_summaries if item.get("intake_status") == "needs_ocr"),
        "records_processed": len(source_records),
        "chunks_written": len(chunks),
        "chunk_size": chunk_size,
        "overlap": overlap,
        "embedding_backend": resolved_backend.name,
        "embedding_model": resolved_backend.model_name,
        "embedding_warning": resolved_backend.warning,
        "parser_backend": parser_backend,
        "document_intake": {
            "files_parsed": sum(1 for item in file_summaries if item.get("intake_status") == "parsed"),
            "files_failed": sum(1 for item in file_summaries if item["status"] == "error"),
            "files_needing_ocr": sum(1 for item in file_summaries if item.get("intake_status") == "needs_ocr"),
            "parser_backends": sorted(
                {
                    str((item.get("processing_plan") or {}).get("parser_backend"))
                    for item in file_summaries
                    if (item.get("processing_plan") or {}).get("parser_backend")
                }
            ),
        },
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
        files_needing_ocr=result["files_needing_ocr"],
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
# Retrieval policy persistence
# ============================================================


def _utc_now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _policy_path(persist_dir: Path) -> Path:
    return Path(persist_dir) / RETRIEVAL_POLICY_FILENAME


def _empty_policy_payload() -> dict[str, Any]:
    return {
        "version": 1,
        "collections": {},
        "proposals": {},
        "audit": [],
        "role_registry": {},
        "notification_recipient_registry": {},
        "notifications": [],
        "identity_provider": {},
    }


def _read_retrieval_policy_payload(persist_dir: Path) -> dict[str, Any]:
    path = _policy_path(persist_dir)
    if not path.exists():
        return _empty_policy_payload()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    base = _empty_policy_payload()
    base.update(payload)
    for key, fallback in _empty_policy_payload().items():
        if not isinstance(base.get(key), type(fallback)):
            base[key] = fallback
    return base


def _write_retrieval_policy_payload(persist_dir: Path, payload: dict[str, Any]) -> None:
    path = _policy_path(persist_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _collection_key(collection_name: str) -> str:
    return safe_collection_name(collection_name or "power_equipment")


def _collection_retrieval_policy_settings(persist_dir: Path, collection_name: str) -> dict[str, Any]:
    payload = _read_retrieval_policy_payload(persist_dir)
    settings = payload.get("collections", {}).get(_collection_key(collection_name), {})
    return dict(settings) if isinstance(settings, Mapping) else {}


def _clean_policy_settings(settings: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(settings, Mapping):
        return {}
    return {str(key): value for key, value in dict(settings).items()}


def _append_policy_audit(payload: dict[str, Any], entry: dict[str, Any]) -> dict[str, Any]:
    audit = payload.setdefault("audit", [])
    enriched = {"id": f"audit-{len(audit) + 1}", "created_at": _utc_now_iso(), **entry}
    audit.append(enriched)
    return enriched


def _policy_diff(before: Mapping[str, Any] | None, after: Mapping[str, Any] | None) -> dict[str, Any]:
    before = dict(before or {})
    after = dict(after or {})
    return {
        "added": {key: after[key] for key in after.keys() - before.keys()},
        "removed": {key: before[key] for key in before.keys() - after.keys()},
        "changed": {
            key: {"from": before[key], "to": after[key]}
            for key in before.keys() & after.keys()
            if before[key] != after[key]
        },
    }


def _applied_policy_audit_entries(payload: Mapping[str, Any], collection: str) -> list[dict[str, Any]]:
    return [
        dict(entry)
        for entry in payload.get("audit", [])
        if isinstance(entry, Mapping)
        and entry.get("collection") == collection
        and entry.get("action") in {"promote", "approve", "rollback"}
        and isinstance(entry.get("settings"), Mapping)
    ]


def promote_collection_retrieval_policy(
    persist_dir: Path,
    collection_name: str,
    settings: Mapping[str, Any],
    *,
    reviewer: str = "",
    review_note: str = "",
    source_report: str = "",
) -> dict[str, Any]:
    collection = _collection_key(collection_name)
    payload = _read_retrieval_policy_payload(persist_dir)
    cleaned = _clean_policy_settings(settings)
    previous = dict(payload.get("collections", {}).get(collection, {}))
    payload.setdefault("collections", {})[collection] = cleaned
    audit_entry = _append_policy_audit(
        payload,
        {
            "action": "promote",
            "collection": collection,
            "settings": cleaned,
            "previous_settings": previous,
            "reviewer": str(reviewer or ""),
            "review_note": str(review_note or ""),
            "source_report": str(source_report or ""),
        },
    )
    _write_retrieval_policy_payload(persist_dir, payload)
    return {"collection": collection, "settings": cleaned, "policy_file": RETRIEVAL_POLICY_FILENAME, "audit_entry": audit_entry}


def rollback_collection_retrieval_policy(
    persist_dir: Path,
    collection_name: str,
    *,
    reviewer: str = "",
    review_note: str = "",
) -> dict[str, Any]:
    collection = _collection_key(collection_name)
    payload = _read_retrieval_policy_payload(persist_dir)
    applied = _applied_policy_audit_entries(payload, collection)
    if len(applied) < 2:
        raise ValueError(f"No previous retrieval policy exists for collection: {collection}")
    current = dict(payload.get("collections", {}).get(collection, {}))
    target = dict(applied[-2].get("settings") or {})
    payload.setdefault("collections", {})[collection] = target
    audit_entry = _append_policy_audit(
        payload,
        {
            "action": "rollback",
            "collection": collection,
            "settings": target,
            "previous_settings": current,
            "reviewer": str(reviewer or ""),
            "review_note": str(review_note or ""),
            "rolled_back_from_audit_id": applied[-1].get("id"),
            "rolled_back_to_audit_id": applied[-2].get("id"),
        },
    )
    _write_retrieval_policy_payload(persist_dir, payload)
    return {"collection": collection, "settings": target, "policy_file": RETRIEVAL_POLICY_FILENAME, "audit_entry": audit_entry}


def get_collection_retrieval_policy_history(persist_dir: Path, collection_name: str) -> dict[str, Any]:
    collection = _collection_key(collection_name)
    payload = _read_retrieval_policy_payload(persist_dir)
    history = _applied_policy_audit_entries(payload, collection)
    pending = [
        dict(proposal)
        for proposal in payload.get("proposals", {}).values()
        if isinstance(proposal, Mapping) and proposal.get("collection") == collection and proposal.get("status") == "pending"
    ]
    if len(history) >= 2:
        latest_diff = _policy_diff(history[-2].get("settings"), history[-1].get("settings"))
    elif history:
        latest_diff = _policy_diff({}, history[-1].get("settings"))
    else:
        latest_diff = {"added": {}, "removed": {}, "changed": {}}
    return {
        "collection": collection,
        "policy_file": RETRIEVAL_POLICY_FILENAME,
        "current_policy": dict(payload.get("collections", {}).get(collection, {})),
        "history": history,
        "pending_proposals": pending,
        "latest_diff": latest_diff,
    }


def _role_registry_entry(payload: Mapping[str, Any], subject: str) -> dict[str, Any] | None:
    entry = payload.get("role_registry", {}).get(subject)
    return dict(entry) if isinstance(entry, Mapping) else None


def _resolve_policy_role(payload: Mapping[str, Any], *, subject: str, requested_role: str, collection: str) -> tuple[str, str]:
    entry = _role_registry_entry(payload, subject)
    if entry:
        if entry.get("active", True) is not True:
            raise ValueError(f"Subject {subject} is inactive in the retrieval policy role registry")
        assigned = [str(item) for item in entry.get("assigned_collections", [])]
        if assigned and "*" not in assigned and collection not in assigned:
            raise ValueError(f"Subject {subject} is not assigned to collection {collection}")
        roles = [str(role) for role in entry.get("roles", [])]
        role = next((role for role in ("owner", "admin", "approver", "reviewer") if role in roles), "")
        return role, "role_registry"
    return str(requested_role or ""), "request"


def _require_policy_approval_role(role: str) -> None:
    if role not in {"approver", "admin", "owner"}:
        raise ValueError("retrieval policy approval requires approver, admin, or owner role")


def propose_collection_retrieval_policy(
    persist_dir: Path,
    collection_name: str,
    settings: Mapping[str, Any],
    *,
    reviewer: str = "",
    reviewer_role: str = "",
    review_note: str = "",
    source_report: str = "",
    assigned_to: str = "",
    due_at: str = "",
) -> dict[str, Any]:
    collection = _collection_key(collection_name)
    payload = _read_retrieval_policy_payload(persist_dir)
    proposal_id = f"proposal-{datetime.utcnow():%Y%m%d%H%M%S}-{len(payload.get('proposals', {})) + 1}"
    proposal = {
        "proposal_id": proposal_id,
        "collection": collection,
        "settings": _clean_policy_settings(settings),
        "status": "pending",
        "reviewer": str(reviewer or ""),
        "reviewer_role": str(reviewer_role or ""),
        "review_note": str(review_note or ""),
        "source_report": str(source_report or ""),
        "assigned_to": str(assigned_to or ""),
        "due_at": str(due_at or ""),
        "created_at": _utc_now_iso(),
    }
    payload.setdefault("proposals", {})[proposal_id] = proposal
    audit_entry = _append_policy_audit(
        payload,
        {
            "action": "propose",
            "collection": collection,
            "proposal_id": proposal_id,
            "reviewer": proposal["reviewer"],
            "reviewer_role": proposal["reviewer_role"],
            "review_note": proposal["review_note"],
            "source_report": proposal["source_report"],
        },
    )
    assignment_notification = None
    if proposal["assigned_to"]:
        assignment_notification = {
            "notification_id": f"notification-{len(payload.setdefault('notifications', [])) + 1}",
            "proposal_id": proposal_id,
            "collection": collection,
            "recipient": proposal["assigned_to"],
            "status": "pending",
            "due_at": proposal["due_at"],
            "created_at": _utc_now_iso(),
            "message": f"Retrieval policy proposal {proposal_id} is awaiting review.",
        }
        payload.setdefault("notifications", []).append(assignment_notification)
    _write_retrieval_policy_payload(persist_dir, payload)
    return {
        "collection": collection,
        "proposal_id": proposal_id,
        "status": "pending",
        "proposal": proposal,
        "assignment_notification": assignment_notification,
        "audit_entry": audit_entry,
        "policy_file": RETRIEVAL_POLICY_FILENAME,
    }


def approve_collection_retrieval_policy_proposal(
    persist_dir: Path,
    proposal_id: str,
    *,
    approver: str = "",
    approver_role: str = "",
    approval_note: str = "",
    identity_source: str = "request",
) -> dict[str, Any]:
    payload = _read_retrieval_policy_payload(persist_dir)
    proposal = payload.get("proposals", {}).get(proposal_id)
    if not isinstance(proposal, dict):
        raise ValueError(f"Retrieval policy proposal not found: {proposal_id}")
    if proposal.get("status") != "pending":
        raise ValueError(f"Retrieval policy proposal is not pending: {proposal_id}")
    collection = str(proposal.get("collection") or "")
    approver_subject = str(approver or "").strip()
    if not approver_subject:
        raise ValueError("retrieval policy approval requires an approver")
    if approver_subject == str(proposal.get("reviewer") or ""):
        raise ValueError("retrieval policy reviewer cannot approve their own proposal")
    resolved_role, role_source = _resolve_policy_role(payload, subject=approver_subject, requested_role=approver_role, collection=collection)
    _require_policy_approval_role(resolved_role)
    settings = dict(proposal.get("settings") or {})
    previous = dict(payload.get("collections", {}).get(collection, {}))
    payload.setdefault("collections", {})[collection] = settings
    proposal.update({"status": "approved", "approver": approver_subject, "approver_role": resolved_role, "approval_note": str(approval_note or ""), "approved_at": _utc_now_iso()})
    audit_entry = _append_policy_audit(
        payload,
        {
            "action": "approve",
            "collection": collection,
            "proposal_id": proposal_id,
            "settings": settings,
            "previous_settings": previous,
            "approver": approver_subject,
            "approver_role": resolved_role,
            "role_source": role_source,
            "identity_source": str(identity_source or "request"),
            "approval_note": str(approval_note or ""),
        },
    )
    _write_retrieval_policy_payload(persist_dir, payload)
    return {"collection": collection, "proposal_id": proposal_id, "status": "approved", "settings": settings, "proposal": proposal, "audit_entry": audit_entry, "policy_file": RETRIEVAL_POLICY_FILENAME}


def reject_collection_retrieval_policy_proposal(
    persist_dir: Path,
    proposal_id: str,
    *,
    approver: str = "",
    approver_role: str = "",
    rejection_note: str = "",
    identity_source: str = "request",
) -> dict[str, Any]:
    payload = _read_retrieval_policy_payload(persist_dir)
    proposal = payload.get("proposals", {}).get(proposal_id)
    if not isinstance(proposal, dict):
        raise ValueError(f"Retrieval policy proposal not found: {proposal_id}")
    if proposal.get("status") != "pending":
        raise ValueError(f"Retrieval policy proposal is not pending: {proposal_id}")
    collection = str(proposal.get("collection") or "")
    resolved_role, role_source = _resolve_policy_role(payload, subject=str(approver or "").strip(), requested_role=approver_role, collection=collection)
    _require_policy_approval_role(resolved_role)
    proposal.update({"status": "rejected", "approver": str(approver or ""), "approver_role": resolved_role, "rejection_note": str(rejection_note or ""), "rejected_at": _utc_now_iso()})
    audit_entry = _append_policy_audit(
        payload,
        {
            "action": "reject",
            "collection": collection,
            "proposal_id": proposal_id,
            "approver": str(approver or ""),
            "approver_role": resolved_role,
            "role_source": role_source,
            "identity_source": str(identity_source or "request"),
            "rejection_note": str(rejection_note or ""),
        },
    )
    _write_retrieval_policy_payload(persist_dir, payload)
    return {"collection": collection, "proposal_id": proposal_id, "status": "rejected", "proposal": proposal, "audit_entry": audit_entry, "policy_file": RETRIEVAL_POLICY_FILENAME}


def upsert_retrieval_policy_role(
    persist_dir: Path,
    subject: str,
    roles: Sequence[str],
    *,
    assigned_collections: Sequence[str] | None = None,
    updated_by: str = "",
    note: str = "",
) -> dict[str, Any]:
    subject = str(subject or "").strip()
    if not subject:
        raise ValueError("retrieval policy role subject is required")
    payload = _read_retrieval_policy_payload(persist_dir)
    entry = {
        "subject": subject,
        "roles": sorted({str(role).strip() for role in roles if str(role).strip()}),
        "assigned_collections": sorted({_collection_key(item) for item in (assigned_collections or []) if str(item).strip()}),
        "active": True,
        "updated_by": str(updated_by or ""),
        "note": str(note or ""),
        "updated_at": _utc_now_iso(),
    }
    payload.setdefault("role_registry", {})[subject] = entry
    audit_entry = _append_policy_audit(payload, {"action": "role_upsert", "subject": subject, "roles": entry["roles"], "updated_by": entry["updated_by"]})
    _write_retrieval_policy_payload(persist_dir, payload)
    return {**entry, "audit_entry": audit_entry, "policy_file": RETRIEVAL_POLICY_FILENAME}


def upsert_retrieval_policy_notification_recipient(
    persist_dir: Path,
    subject: str,
    *,
    email: str = "",
    webhook_url: str = "",
    webhook_template: str = "",
    webhook_signing_secret_env: str = "",
    webhook_routing_key_env: str = "",
    webhook_auth_header_name: str = "",
    webhook_auth_token_env: str = "",
    webhook_auth_scheme: str = "",
    preferred_delivery_mode: str = "",
    updated_by: str = "",
    note: str = "",
) -> dict[str, Any]:
    subject = str(subject or "").strip()
    if not subject:
        raise ValueError("retrieval policy notification recipient subject is required")
    payload = _read_retrieval_policy_payload(persist_dir)
    entry = {
        "subject": subject,
        "email": str(email or ""),
        "webhook_url": str(webhook_url or ""),
        "webhook_template": str(webhook_template or ""),
        "webhook_signing_secret_env": str(webhook_signing_secret_env or ""),
        "webhook_routing_key_env": str(webhook_routing_key_env or ""),
        "webhook_auth_header_name": str(webhook_auth_header_name or ""),
        "webhook_auth_token_env": str(webhook_auth_token_env or ""),
        "webhook_auth_scheme": str(webhook_auth_scheme or ""),
        "preferred_delivery_mode": str(preferred_delivery_mode or ""),
        "updated_by": str(updated_by or ""),
        "note": str(note or ""),
        "updated_at": _utc_now_iso(),
    }
    payload.setdefault("notification_recipient_registry", {})[subject] = entry
    audit_entry = _append_policy_audit(payload, {"action": "notification_recipient_upsert", "subject": subject, "updated_by": entry["updated_by"]})
    _write_retrieval_policy_payload(persist_dir, payload)
    return {**entry, "audit_entry": audit_entry, "policy_file": RETRIEVAL_POLICY_FILENAME}


def list_retrieval_policy_notification_recipients(persist_dir: Path) -> dict[str, Any]:
    payload = _read_retrieval_policy_payload(persist_dir)
    recipients = list(payload.get("notification_recipient_registry", {}).values())
    return {"recipients": recipients, "recipient_count": len(recipients), "policy_file": RETRIEVAL_POLICY_FILENAME}


def list_retrieval_policy_notifications(persist_dir: Path, *, recipient: str = "", status: str = "") -> dict[str, Any]:
    payload = _read_retrieval_policy_payload(persist_dir)
    recipient = str(recipient or "").strip()
    status = str(status or "").strip()
    notifications = [
        dict(item)
        for item in payload.get("notifications", [])
        if isinstance(item, Mapping) and (not recipient or item.get("recipient") == recipient) and (not status or item.get("status") == status)
    ]
    return {"notifications": notifications, "notification_count": len(notifications), "policy_file": RETRIEVAL_POLICY_FILENAME}


def _write_notification_outbox(persist_dir: Path, outbox_path: str, events: Sequence[Mapping[str, Any]]) -> Path:
    base = Path(persist_dir).resolve()
    target = Path(outbox_path).resolve() if outbox_path else base / "policy_notification_outbox.jsonl"
    if base not in [target, *target.parents]:
        raise ValueError("notification outbox_path must stay inside the Chroma persist directory")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(dict(event), ensure_ascii=False) + "\n")
    return target


def _notification_text(event: Mapping[str, Any]) -> str:
    return (
        f"Retrieval policy proposal {event.get('proposal_id')} for {event.get('collection')} "
        f"is awaiting review by {event.get('recipient')}."
    )


def _render_webhook_notification_payload(
    template: str,
    event: Mapping[str, Any],
    *,
    routing_key_env: str = "",
) -> dict[str, Any]:
    template = str(template or "generic").strip() or "generic"
    text = _notification_text(event)
    if template == "lark_text":
        return {"msg_type": "text", "content": {"text": text}}
    if template in {"dingtalk_text", "wecom_text"}:
        return {"msgtype": "text", "text": {"content": text}}
    if template == "pagerduty_event_v2":
        routing_key = os.getenv(str(routing_key_env or ""), "")
        return {
            "routing_key": routing_key,
            "event_action": "trigger",
            "payload": {
                "summary": text,
                "severity": "warning",
                "source": "PowerRAG retrieval policy",
                "custom_details": dict(event),
            },
        }
    if template == "opsgenie_alert":
        return {
            "message": text,
            "description": text,
            "priority": "P3",
            "details": dict(event),
        }
    return dict(event)


def _signed_webhook_headers(body: bytes, signing_secret_env: str) -> tuple[dict[str, str], bool]:
    secret = os.getenv(str(signing_secret_env or ""), "")
    if not secret:
        return {}, False
    timestamp = str(int(datetime.utcnow().timestamp()))
    signature = hmac.new(
        secret.encode("utf-8"),
        f"{timestamp}.".encode("utf-8") + body,
        hashlib.sha256,
    ).hexdigest()
    return {
        "X-RAG-Notification-Timestamp": timestamp,
        "X-RAG-Notification-Signature": signature,
        "X-RAG-Notification-Signature-Alg": "hmac-sha256",
    }, True


def _post_webhook_notification(url: str, body: bytes, timeout_seconds: float, *, headers: Mapping[str, str] | None = None) -> dict[str, Any]:
    from urllib.parse import urlparse
    from urllib.request import Request as UrlRequest, urlopen

    parsed = urlparse(url)
    if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost"}):
        raise ValueError("webhook delivery requires https, except loopback http for local tests")
    request_headers = {"Content-Type": "application/json", **dict(headers or {})}
    request = UrlRequest(url, data=body, headers=request_headers, method="POST")
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            response_body = response.read(4096).decode("utf-8", errors="replace")
            status_code = int(response.status)
            return {"status_code": status_code, "body": response_body, "failed": status_code >= 400}
    except HTTPError as exc:
        response_body = exc.read(4096).decode("utf-8", errors="replace")
        return {"status_code": int(exc.code), "body": response_body, "failed": True}


def _send_smtp_notification(
    event: Mapping[str, Any],
    *,
    host: str,
    port: int,
    mail_from: str,
    mail_to: str,
    subject: str,
    timeout_seconds: float,
    use_tls: bool,
    username_env: str,
    password_env: str,
) -> dict[str, Any]:
    if not host:
        raise ValueError("smtp_host is required for SMTP delivery")
    if not mail_from:
        raise ValueError("smtp_from is required for SMTP delivery")
    if not mail_to:
        raise ValueError("smtp_to or recipient email is required for SMTP delivery")
    message = EmailMessage()
    message["From"] = mail_from
    message["To"] = mail_to
    message["Subject"] = subject or "RAG policy approval needed"
    message.set_content(_notification_text(event))
    username = os.getenv(str(username_env or ""), "")
    password = os.getenv(str(password_env or ""), "")
    with smtplib.SMTP(host, int(port), timeout=float(timeout_seconds)) as smtp:
        smtp.ehlo()
        if use_tls:
            smtp.starttls()
            smtp.ehlo()
        authenticated = bool(username or password)
        if authenticated:
            smtp.login(username, password)
        smtp.send_message(message)
    return {"status_code": 250, "body": "queued", "failed": False, "authenticated": bool(username or password)}


def dispatch_retrieval_policy_notifications(
    persist_dir: Path,
    *,
    recipient: str = "",
    status: str = "pending",
    delivery_mode: str = "outbox_file",
    outbox_path: str | None = None,
    webhook_url: str = "",
    webhook_timeout_seconds: float = 5.0,
    webhook_template: str = "generic",
    webhook_signing_secret_env: str = "",
    webhook_routing_key_env: str = "",
    webhook_auth_header_name: str = "",
    webhook_auth_token_env: str = "",
    webhook_auth_scheme: str = "",
    smtp_host: str = "",
    smtp_port: int = 25,
    smtp_from: str = "",
    smtp_to: str = "",
    smtp_subject: str = "",
    smtp_timeout_seconds: float = 10.0,
    smtp_use_tls: bool = True,
    smtp_username_env: str = "",
    smtp_password_env: str = "",
    dispatched_by: str = "",
) -> dict[str, Any]:
    payload = _read_retrieval_policy_payload(persist_dir)
    recipient_registry = payload.get("notification_recipient_registry", {})
    recipient_registry = recipient_registry if isinstance(recipient_registry, Mapping) else {}
    recipient = str(recipient or "").strip()
    status = str(status or "pending").strip()
    matched = [
        item
        for item in payload.setdefault("notifications", [])
        if isinstance(item, dict) and (not recipient or item.get("recipient") == recipient) and (not status or item.get("status") == status)
    ]
    delivered_events: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    recipient_source = "request"
    for item in matched:
        registry_entry = recipient_registry.get(str(item.get("recipient") or ""))
        registry_entry = dict(registry_entry) if isinstance(registry_entry, Mapping) else {}
        effective_webhook_url = str(webhook_url or registry_entry.get("webhook_url") or "")
        effective_template = str(
            (webhook_template if webhook_template and webhook_template != "generic" else registry_entry.get("webhook_template"))
            or webhook_template
            or "generic"
        )
        effective_signing_secret_env = str(webhook_signing_secret_env or registry_entry.get("webhook_signing_secret_env") or "")
        effective_routing_key_env = str(webhook_routing_key_env or registry_entry.get("webhook_routing_key_env") or "")
        effective_auth_header_name = str(webhook_auth_header_name or registry_entry.get("webhook_auth_header_name") or "")
        effective_auth_scheme = str(webhook_auth_scheme or registry_entry.get("webhook_auth_scheme") or "")
        effective_auth_token_env = str(webhook_auth_token_env or registry_entry.get("webhook_auth_token_env") or "")
        effective_smtp_to = str(smtp_to or registry_entry.get("email") or item.get("recipient") or "")
        item_recipient_source = "notification_recipient_registry" if registry_entry and (
            (delivery_mode == "webhook" and not webhook_url and effective_webhook_url)
            or (delivery_mode == "smtp" and not smtp_to and effective_smtp_to)
            or (webhook_template == "generic" and registry_entry.get("webhook_template"))
        ) else "request"
        if item_recipient_source == "notification_recipient_registry":
            recipient_source = item_recipient_source
        event = {
            "notification_id": item.get("notification_id"),
            "proposal_id": item.get("proposal_id"),
            "collection": item.get("collection"),
            "recipient": item.get("recipient"),
            "due_at": item.get("due_at"),
            "message": item.get("message"),
            "dispatched_at": _utc_now_iso(),
            "dispatched_by": str(dispatched_by or ""),
        }
        try:
            delivery: dict[str, Any] = {"mode": delivery_mode, "recipient_source": item_recipient_source}
            if delivery_mode == "outbox_file":
                delivered_events.append(event)
                delivery["target"] = str(outbox_path or Path(persist_dir) / "policy_notification_outbox.jsonl")
            elif delivery_mode == "webhook":
                target = effective_webhook_url
                if not target:
                    raise ValueError("webhook_url is required for webhook delivery")
                webhook_payload = _render_webhook_notification_payload(
                    effective_template,
                    event,
                    routing_key_env=effective_routing_key_env,
                )
                body = json.dumps(webhook_payload, ensure_ascii=False).encode("utf-8")
                headers, signed = _signed_webhook_headers(body, effective_signing_secret_env)
                if effective_auth_header_name and effective_auth_token_env:
                    token = os.getenv(effective_auth_token_env, "")
                    if token:
                        headers[effective_auth_header_name] = f"{effective_auth_scheme} {token}".strip()
                response = _post_webhook_notification(target, body, float(webhook_timeout_seconds), headers=headers)
                delivery.update(
                    {
                        "target": target,
                        "template": effective_template,
                        "signed": signed,
                        "response": response,
                    }
                )
                if response.get("failed"):
                    item["status"] = "failed"
                    item["delivery"] = delivery
                    failed.append({"notification_id": item.get("notification_id"), "error": f"webhook returned {response.get('status_code')}"})
                    continue
            elif delivery_mode == "smtp":
                response = _send_smtp_notification(
                    event,
                    host=str(smtp_host or ""),
                    port=int(smtp_port),
                    mail_from=str(smtp_from or ""),
                    mail_to=effective_smtp_to,
                    subject=str(smtp_subject or ""),
                    timeout_seconds=float(smtp_timeout_seconds),
                    use_tls=bool(smtp_use_tls),
                    username_env=str(smtp_username_env or ""),
                    password_env=str(smtp_password_env or ""),
                )
                delivery.update(
                    {
                        "target": effective_smtp_to,
                        "smtp_to": effective_smtp_to,
                        "authenticated": bool(response.get("authenticated")),
                        "response": response,
                    }
                )
            else:
                raise ValueError(f"Unsupported notification delivery mode: {delivery_mode}")
            item["status"] = "delivered"
            item["delivery"] = delivery
            item["delivered_at"] = _utc_now_iso()
        except Exception as exc:
            item["status"] = "failed"
            item["delivery"] = {"mode": delivery_mode, "error": str(exc)}
            failed.append({"notification_id": item.get("notification_id"), "error": str(exc)})
    if delivered_events:
        target = _write_notification_outbox(persist_dir, outbox_path or "", delivered_events)
        for item in matched:
            if item.get("delivery", {}).get("mode") == "outbox_file":
                item["delivery"]["target"] = str(target)
    audit_entry = _append_policy_audit(
        payload,
        {
            "action": "dispatch_notification",
            "recipient": recipient,
            "status": status,
            "delivery_mode": delivery_mode,
            "attempted_count": len(matched),
            "dispatched_count": len(matched) - len(failed),
            "failed_count": len(failed),
            "dispatched_by": str(dispatched_by or ""),
            "recipient_source": recipient_source,
        },
    )
    _write_retrieval_policy_payload(persist_dir, payload)
    delivered = [dict(item) for item in matched if item.get("status") == "delivered"]
    return {
        "delivery_mode": delivery_mode,
        "attempted_count": len(matched),
        "dispatched_count": len(delivered),
        "failed_count": len(failed),
        "notifications": [dict(item) for item in matched],
        "failed": failed,
        "audit_entry": audit_entry,
        "policy_file": RETRIEVAL_POLICY_FILENAME,
    }


def get_retrieval_policy_identity_provider_config(persist_dir: Path) -> dict[str, Any]:
    payload = _read_retrieval_policy_payload(persist_dir)
    identity_provider = payload.get("identity_provider", {})
    if not isinstance(identity_provider, Mapping):
        identity_provider = {}
    oidc = identity_provider.get("oidc")
    if isinstance(oidc, Mapping):
        return {
            "identity_provider": dict(oidc),
            "identity_providers": dict(identity_provider),
            "policy_file": RETRIEVAL_POLICY_FILENAME,
        }
    return {"identity_provider": dict(identity_provider), "policy_file": RETRIEVAL_POLICY_FILENAME}


def upsert_retrieval_policy_identity_provider_config(
    persist_dir: Path,
    *,
    provider: str = "oidc",
    enabled: bool = False,
    issuer: str = "",
    audience: str = "",
    jwks_url: str = "",
    authorization_endpoint: str = "",
    token_endpoint: str = "",
    client_id: str = "",
    client_secret_env: str = "",
    redirect_uri: str = "",
    scopes: Sequence[str] | None = None,
    subject_claim: str = "email",
    groups_claim: str = "groups",
    algorithms: Sequence[str] | None = None,
    updated_by: str = "",
    note: str = "",
) -> dict[str, Any]:
    if provider != "oidc":
        raise ValueError("Only oidc identity provider is supported")
    payload = _read_retrieval_policy_payload(persist_dir)
    config = {
        "provider": "oidc",
        "enabled": bool(enabled),
        "issuer": str(issuer or ""),
        "audience": str(audience or ""),
        "jwks_url": str(jwks_url or ""),
        "authorization_endpoint": str(authorization_endpoint or ""),
        "token_endpoint": str(token_endpoint or ""),
        "client_id": str(client_id or ""),
        "client_secret_env": str(client_secret_env or ""),
        "redirect_uri": str(redirect_uri or ""),
        "scopes": [str(scope) for scope in (scopes or ["openid", "email", "profile"]) if str(scope).strip()],
        "subject_claim": str(subject_claim or "email"),
        "groups_claim": str(groups_claim or "groups"),
        "algorithms": [str(item) for item in (algorithms or ["RS256"]) if str(item).strip()],
        "updated_by": str(updated_by or ""),
        "note": str(note or ""),
        "updated_at": _utc_now_iso(),
    }
    payload.setdefault("identity_provider", {})["oidc"] = config
    audit_entry = _append_policy_audit(payload, {"action": "identity_provider_upsert", "provider": "oidc", "enabled": config["enabled"], "updated_by": config["updated_by"], "note": config["note"]})
    _write_retrieval_policy_payload(persist_dir, payload)
    return {"identity_provider": config, "audit_entry": audit_entry, "policy_file": RETRIEVAL_POLICY_FILENAME}


def sync_retrieval_policy_identity_directory(
    persist_dir: Path,
    *,
    source_type: str = "scim",
    users: Sequence[Mapping[str, Any]] | None = None,
    groups: Sequence[Mapping[str, Any]] | None = None,
    role_group_mappings: Mapping[str, Any] | None = None,
    recipient_defaults: Mapping[str, Any] | None = None,
    updated_by: str = "",
    note: str = "",
    dry_run: bool = False,
) -> dict[str, Any]:
    payload = _read_retrieval_policy_payload(persist_dir)
    role_registry = payload.setdefault("role_registry", {})
    recipient_registry = payload.setdefault("notification_recipient_registry", {})
    role_upserts = 0
    recipient_upserts = 0
    active_user_count = 0
    disabled_user_count = 0
    disabled_subjects: list[str] = []
    users = users or []
    groups = groups or []
    role_group_mappings = dict(role_group_mappings or {})
    recipient_defaults = dict(recipient_defaults or {})

    def scim_email(user: Mapping[str, Any]) -> str:
        if user.get("email"):
            return str(user.get("email") or "").strip()
        emails = user.get("emails")
        if isinstance(emails, ABCSequence) and not isinstance(emails, str | bytes):
            fallback = ""
            for item in emails:
                if not isinstance(item, Mapping):
                    continue
                value = str(item.get("value") or "").strip()
                if not value:
                    continue
                fallback = fallback or value
                if item.get("primary") is True:
                    return value
            return fallback
        return ""

    group_names_by_member: dict[str, set[str]] = {}
    for group in groups:
        if not isinstance(group, Mapping):
            continue
        group_name = str(group.get("displayName") or group.get("name") or group.get("id") or "").strip()
        if not group_name:
            continue
        members = group.get("members") or []
        if not isinstance(members, ABCSequence) or isinstance(members, str | bytes):
            continue
        for member in members:
            if isinstance(member, Mapping):
                member_id = str(member.get("value") or member.get("display") or "").strip()
            else:
                member_id = str(member or "").strip()
            if member_id:
                group_names_by_member.setdefault(member_id, set()).add(group_name)

    for user in users:
        if not isinstance(user, Mapping):
            continue
        email = scim_email(user)
        subject = str(email or user.get("userName") or user.get("id") or "").strip()
        if not subject:
            continue
        identifiers = {
            str(user.get("id") or "").strip(),
            str(user.get("userName") or "").strip(),
            email,
            subject,
        }
        groups_for_user = {str(item) for item in user.get("groups", []) if str(item).strip()}
        for identifier in identifiers:
            if identifier:
                groups_for_user.update(group_names_by_member.get(identifier, set()))
        roles: set[str] = set()
        assigned_collections: set[str] = {
            _collection_key(item)
            for item in user.get("assigned_collections", [])
            if str(item).strip()
        }
        for group in groups_for_user:
            mapped = role_group_mappings.get(group, [])
            if isinstance(mapped, str):
                roles.add(mapped)
            elif isinstance(mapped, Mapping):
                roles.update(str(role).strip() for role in mapped.get("roles", []) if str(role).strip())
                assigned_collections.update(
                    _collection_key(item)
                    for item in mapped.get("assigned_collections", [])
                    if str(item).strip()
                )
            else:
                roles.update(str(role).strip() for role in mapped if str(role).strip())
        active = bool(user.get("active", True))
        if active:
            active_user_count += 1
        else:
            disabled_user_count += 1
            disabled_subjects.append(subject)
            roles.clear()
            assigned_collections.clear()
        if not dry_run:
            role_registry[subject] = {
                "subject": subject,
                "roles": sorted(roles),
                "assigned_collections": sorted(assigned_collections),
                "active": active,
                "updated_by": str(updated_by or ""),
                "note": str(note or ""),
                "updated_at": _utc_now_iso(),
            }
        if active:
            role_upserts += 1
        if active and email:
            if not dry_run:
                recipient_registry[subject] = {
                    "subject": subject,
                    "email": email,
                    "preferred_delivery_mode": str(recipient_defaults.get("preferred_delivery_mode") or "smtp"),
                    "updated_by": str(updated_by or ""),
                    "note": str(note or ""),
                    "updated_at": _utc_now_iso(),
                }
            recipient_upserts += 1
    audit_entry = _append_policy_audit(
        payload,
        {
            "action": "directory_sync",
            "source_type": str(source_type or ""),
            "synced_user_count": len(users),
            "active_user_count": active_user_count,
            "disabled_user_count": disabled_user_count,
            "disabled_subjects": disabled_subjects,
            "role_upsert_count": role_upserts,
            "recipient_upsert_count": recipient_upserts,
            "updated_by": str(updated_by or ""),
            "dry_run": bool(dry_run),
        },
    )
    if not dry_run:
        _write_retrieval_policy_payload(persist_dir, payload)
    return {
        "source_type": source_type,
        "synced_user_count": len(users),
        "active_user_count": active_user_count,
        "disabled_user_count": disabled_user_count,
        "disabled_subjects": disabled_subjects,
        "role_upsert_count": role_upserts,
        "recipient_upsert_count": recipient_upserts,
        "dry_run": bool(dry_run),
        "audit_entry": audit_entry,
        "policy_file": RETRIEVAL_POLICY_FILENAME,
    }


def build_empty_hybrid_retrieval_diagnostics(
    query_text: str,
    *,
    collection_count: int = 0,
    no_answer_reason: str = "empty_database",
) -> dict[str, Any]:
    return {
        "original_query": query_text,
        "rewritten_queries": [query_text],
        "retrieval_path": "hybrid",
        "fusion_mode": "rrf",
        "raw_candidate_count": 0,
        "filtered_candidate_count": 0,
        "final_candidate_count": 0,
        "candidate_pool_count": int(collection_count),
        "filters_applied": False,
        "reranker_name": None,
        "reranker_error": None,
        "no_answer": True,
        "no_answer_reason": no_answer_reason,
        "retrievers": [],
        "retrieval_policy": {"applied": False},
    }


# ============================================================
# 查询
# ============================================================


def _first_chroma_batch(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list) and value and isinstance(value[0], list):
        return value[0]
    if isinstance(value, list):
        return value
    return []


def _distance_to_score(distance: Any) -> float:
    if distance is None:
        return 0.0
    try:
        numeric = float(distance)
    except (TypeError, ValueError):
        return 0.0
    if numeric < 0:
        return 1.0
    return 1.0 / (1.0 + numeric)


def _chroma_metadata_field(field: str) -> str:
    return field.removeprefix("meta.").removeprefix("metadata.")


def _chroma_filter_value_list(value: Any) -> list[Any]:
    if isinstance(value, ABCSequence) and not isinstance(value, str | bytes):
        return list(value)
    return [value]


def _chroma_leaf_where(filters: Mapping[str, Any]) -> dict[str, Any] | None:
    if "field" not in filters:
        if not filters:
            return None
        return {_chroma_metadata_field(str(key)): value for key, value in filters.items()}

    field = _chroma_metadata_field(str(filters.get("field") or ""))
    if not field:
        return None
    operator = str(filters.get("operator") or "==").lower()
    value = filters.get("value")
    if operator in {"==", "=", "eq"}:
        return {field: value}
    if operator in {"!=", "ne"}:
        return {field: {"$ne": value}}
    if operator == "in":
        return {field: {"$in": _chroma_filter_value_list(value)}}
    if operator in {"not in", "nin"}:
        return {field: {"$nin": _chroma_filter_value_list(value)}}
    if operator == ">":
        return {field: {"$gt": value}}
    if operator == ">=":
        return {field: {"$gte": value}}
    if operator == "<":
        return {field: {"$lt": value}}
    if operator == "<=":
        return {field: {"$lte": value}}
    return None


def _chroma_where_from_filters(filters: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not filters:
        return None
    if "conditions" not in filters:
        return _chroma_leaf_where(filters)

    operator = str(filters.get("operator") or "AND").upper()
    clauses = [
        clause
        for condition in filters.get("conditions") or []
        if isinstance(condition, Mapping)
        for clause in [_chroma_where_from_filters(condition)]
        if clause
    ]
    if not clauses:
        return None
    if operator == "OR":
        return clauses[0] if len(clauses) == 1 else {"$or": clauses}
    if operator == "AND":
        return clauses[0] if len(clauses) == 1 else {"$and": clauses}
    return None


class _ChromaCollectionRetriever:
    name = "chroma_vector"

    def __init__(self, collection: Any) -> None:
        self.collection = collection
        self.candidate_count = 0

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        *,
        filters: Mapping[str, Any] | None = None,
    ) -> list[Any]:
        from retrieval_engine.core import DocumentChunk, RetrievalResult

        if top_k <= 0 or not query.strip():
            return []
        query_kwargs: dict[str, Any] = {
            "query_texts": [query],
            "n_results": top_k,
            "include": ["documents", "metadatas", "distances"],
        }
        where = _chroma_where_from_filters(filters)
        if where:
            query_kwargs["where"] = where
        raw = self.collection.query(**query_kwargs)
        ids = _first_chroma_batch(raw.get("ids"))
        documents = _first_chroma_batch(raw.get("documents"))
        metadatas = _first_chroma_batch(raw.get("metadatas"))
        distances = _first_chroma_batch(raw.get("distances"))

        results: list[Any] = []
        for index, doc_id in enumerate(ids):
            document = documents[index] if index < len(documents) else ""
            metadata_value = metadatas[index] if index < len(metadatas) else {}
            metadata = dict(metadata_value) if isinstance(metadata_value, dict) else {}
            if doc_id is not None:
                metadata.setdefault("chroma_id", str(doc_id))
                metadata.setdefault("chunk_id", str(doc_id))
            distance = distances[index] if index < len(distances) else None
            if distance is not None:
                metadata["_chroma_distance"] = float(distance)
            chunk = DocumentChunk.from_text(str(document or ""), metadata=metadata, chunk_id=str(doc_id))
            results.append(RetrievalResult(chunk=chunk, score=_distance_to_score(distance), retriever_name=self.name))
        self.candidate_count += len(results)
        return results


_SENTENCE_ID_PATTERN = re.compile(r"SENTENCE_ID:\s*([^\s]+)")
_ORDERED_SENTENCE_ID_PATTERN = re.compile(r"^(\d+)([A-Za-z]+)$")


def _extract_sentence_id_from_text(text: str) -> str:
    match = _SENTENCE_ID_PATTERN.search(text)
    return match.group(1).strip() if match else ""


def _result_sentence_id(result: Any) -> str:
    metadata = getattr(result, "metadata", {}) or {}
    sentence_id = str(metadata.get("sentence_id") or "").strip()
    if sentence_id:
        return sentence_id
    return _extract_sentence_id_from_text(str(getattr(result, "text", "") or ""))


def _sentence_sort_key(sentence_id: str, fallback_index: int) -> tuple[int, int, int]:
    match = _ORDERED_SENTENCE_ID_PATTERN.match(sentence_id)
    if not match:
        return (10**9, fallback_index, 0)
    family = int(match.group(1))
    letters = match.group(2).lower()
    ordinal = 0
    for char in letters:
        ordinal = ordinal * 26 + (ord(char) - ord("a") + 1)
    return (family, ordinal, fallback_index)


def _sentence_family(sentence_id: str) -> str:
    match = _ORDERED_SENTENCE_ID_PATTERN.match(sentence_id)
    return match.group(1) if match else ""


def _source_file_filter_value(filters: Mapping[str, Any] | None) -> str:
    if not filters:
        return ""
    if "conditions" in filters:
        operator = str(filters.get("operator") or "AND").upper()
        if operator != "AND":
            return ""
        for condition in filters.get("conditions") or []:
            if isinstance(condition, Mapping):
                value = _source_file_filter_value(condition)
                if value:
                    return value
        return ""
    field = str(filters.get("field") or "") if "field" in filters else ""
    operator = str(filters.get("operator") or "==").lower()
    if field.removeprefix("meta.").removeprefix("metadata.") != "source_file":
        return ""
    if operator not in {"==", "=", "eq"}:
        return ""
    return str(filters.get("value") or "").strip()


_SOURCE_TYPE_FILTERS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("markdown", "md"), ".md"),
    (("pdf",), ".pdf"),
    (("text", "txt"), ".txt"),
    (("docx", "word"), ".docx"),
    (("csv",), ".csv"),
    (("json",), ".json"),
)
_SOURCE_FILENAME_PATTERN = re.compile(r"(?i)\b([\w.-]+\.(?:md|markdown|txt|pdf|docx?|csv|json))\b")
_DATE_RANGE_PATTERN = re.compile(r"(?i)\bfrom\s+(\d{4})-(\d{2})-(\d{2})\s+to\s+(\d{4})-(\d{2})-(\d{2})")
_BUSINESS_FIELD_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("meta.author", re.compile(r"(?i)\bauthor:\s*([^\s]+)")),
    ("meta.department", re.compile(r"(?i)\bdepartment:\s*([^\s]+)")),
    ("meta.product", re.compile(r"(?i)\bproduct:\s*([^\s]+)")),
)


def _date_int(year: str, month: str, day: str) -> int:
    return int(f"{int(year):04d}{int(month):02d}{int(day):02d}")


def _auto_filters_from_query(query_text: str) -> list[dict[str, Any]]:
    text = str(query_text or "")
    filters: list[dict[str, Any]] = []

    for aliases, extension in _SOURCE_TYPE_FILTERS:
        if any(re.search(rf"(?i)\b{re.escape(alias)}\b", text) for alias in aliases):
            filters.append({"field": "meta.source_ext", "operator": "==", "value": extension})
            break

    for match in _SOURCE_FILENAME_PATTERN.finditer(text):
        filename = match.group(1)
        if filename.casefold() in {"markdown", "text"}:
            continue
        normalized = ".md" if filename.casefold().endswith(".markdown") else filename
        filters.append({"field": "meta.source_file", "operator": "contains", "value": normalized})
        break

    date_match = _DATE_RANGE_PATTERN.search(text)
    if date_match:
        start_year, start_month, start_day, end_year, end_month, end_day = date_match.groups()
        filters.append(
            {
                "field": "meta.source_date",
                "operator": ">=",
                "value": _date_int(start_year, start_month, start_day),
            }
        )
        filters.append(
            {
                "field": "meta.source_date",
                "operator": "<=",
                "value": _date_int(end_year, end_month, end_day),
            }
        )
    else:
        year_match = re.search(r"(?i)\bonly\s+search\s+(20\d{2})\b", text)
        if year_match:
            filters.append({"field": "meta.source_file", "operator": "contains", "value": year_match.group(1)})

    for field, pattern in _BUSINESS_FIELD_PATTERNS:
        match = pattern.search(text)
        if match:
            filters.append({"field": field, "operator": "contains", "value": match.group(1).strip(" ,;")})

    # Avoid duplicate filter leaves while preserving their audit order.
    unique: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in filters:
        key = (str(item.get("field") or ""), str(item.get("operator") or ""), str(item.get("value") or ""))
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _filter_leaf_list(filters: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if not filters:
        return []
    if "conditions" in filters:
        leaves: list[dict[str, Any]] = []
        for condition in filters.get("conditions") or []:
            if isinstance(condition, Mapping):
                leaves.extend(_filter_leaf_list(condition))
        return leaves
    return [dict(filters)]


def _combine_filter_conditions(filters: Sequence[Mapping[str, Any] | None]) -> dict[str, Any] | None:
    conditions = [dict(item) for item in filters if isinstance(item, Mapping) and item]
    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return {"operator": "AND", "conditions": conditions}


def _apply_metadata_field_aliases(filters: Mapping[str, Any] | None, aliases: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not filters:
        return None
    aliases = {str(key): str(value) for key, value in dict(aliases or {}).items() if str(value)}
    if "conditions" in filters:
        return {
            **dict(filters),
            "conditions": [
                mapped
                for condition in filters.get("conditions") or []
                if isinstance(condition, Mapping)
                for mapped in [_apply_metadata_field_aliases(condition, aliases)]
                if mapped
            ],
        }
    mapped = dict(filters)
    field = str(mapped.get("field") or "")
    if field in aliases:
        mapped["field"] = aliases[field]
    return mapped


def _source_chunks_from_collection(
    collection: Any,
    *,
    source_file: str,
    collection_count: int,
) -> list[Any]:
    from retrieval_engine.core import DocumentChunk, RetrievalResult

    if not source_file:
        return []
    limit = min(collection_count, _positive_int_env("RAG_SOURCE_SCOPE_EXPANSION_LIMIT", 2000))
    try:
        payload = collection.get(
            where={"source_file": source_file},
            limit=limit,
            include=["documents", "metadatas"],
        )
    except Exception:  # noqa: BLE001
        return []

    ids = _first_chroma_batch(payload.get("ids"))
    documents = _first_chroma_batch(payload.get("documents"))
    metadatas = _first_chroma_batch(payload.get("metadatas"))
    results: list[Any] = []
    for index, document in enumerate(documents):
        metadata_value = metadatas[index] if index < len(metadatas) else {}
        metadata = dict(metadata_value) if isinstance(metadata_value, dict) else {}
        doc_id = ids[index] if index < len(ids) else metadata.get("chunk_id")
        if doc_id is not None:
            metadata.setdefault("chunk_id", str(doc_id))
            metadata.setdefault("chroma_id", str(doc_id))
        sentence_id = str(metadata.get("sentence_id") or "").strip() or _extract_sentence_id_from_text(str(document or ""))
        if sentence_id:
            metadata.setdefault("sentence_id", sentence_id)
        chunk = DocumentChunk.from_text(str(document or ""), metadata=metadata, chunk_id=str(doc_id) if doc_id else None)
        results.append(
            RetrievalResult(
                chunk=chunk,
                score=0.0,
                retriever_name="source_neighbor",
                component_scores={"source_neighbor": 0.0},
            )
        )
    return results


def _neighbor_candidates_for_anchor(
    source_results: list[Any],
    *,
    anchor_sentence_id: str,
    before: int,
    after: int,
) -> list[Any]:
    if not anchor_sentence_id:
        return []
    family = _sentence_family(anchor_sentence_id)
    ordered = sorted(
        [
            (index, result, _result_sentence_id(result))
            for index, result in enumerate(source_results)
            if _result_sentence_id(result)
        ],
        key=lambda item: _sentence_sort_key(item[2], item[0]),
    )
    anchor_indexes = [index for index, (_fallback, _result, sentence_id) in enumerate(ordered) if sentence_id == anchor_sentence_id]
    if not anchor_indexes:
        return []
    anchor_index = anchor_indexes[0]
    neighbors: list[Any] = []
    start = max(0, anchor_index - before)
    stop = min(len(ordered), anchor_index + after + 1)
    for index in range(start, stop):
        if index == anchor_index:
            continue
        _fallback, result, sentence_id = ordered[index]
        if family and _sentence_family(sentence_id) != family:
            continue
        neighbors.append(result)
    return neighbors


def _expand_source_local_neighbors(
    collection: Any,
    results: Sequence[Any],
    *,
    source_file: str,
    collection_count: int,
    top_k: int,
) -> list[Any]:
    from retrieval_engine.core import RetrievalResult

    if not results or top_k <= 0 or not source_file:
        return list(results)
    source_results = _source_chunks_from_collection(
        collection,
        source_file=source_file,
        collection_count=collection_count,
    )
    if not source_results:
        return list(results)

    max_anchors = _positive_int_env("RAG_SOURCE_NEIGHBOR_ANCHORS", 8)
    before = _positive_int_env("RAG_SOURCE_NEIGHBOR_BEFORE", 1)
    after = _positive_int_env("RAG_SOURCE_NEIGHBOR_AFTER", 2)
    selected: list[Any] = []
    seen: set[tuple[str, str]] = set()

    def add(result: Any) -> None:
        key = getattr(getattr(result, "chunk", None), "identity_key", None)
        if key is None:
            key = ("text", str(getattr(result, "text", "") or ""))
        if key in seen:
            return
        seen.add(key)
        selected.append(result)

    for anchor_index, result in enumerate(results):
        add(result)
        if anchor_index >= max_anchors:
            continue
        anchor_sentence_id = _result_sentence_id(result)
        for neighbor in _neighbor_candidates_for_anchor(
            source_results,
            anchor_sentence_id=anchor_sentence_id,
            before=before,
            after=after,
        ):
            neighbor_score = max(float(getattr(result, "score", 0.0)) * 0.98, 0.000001)
            add(
                RetrievalResult(
                    chunk=neighbor.chunk,
                    score=neighbor_score,
                    retriever_name=getattr(result, "retriever_name", None) or "source_neighbor",
                    component_scores={
                        **getattr(neighbor, "component_scores", {}),
                        "source_neighbor": neighbor_score,
                    },
                )
            )
            if len(selected) >= top_k:
                break
        if len(selected) >= top_k:
            break

    for result in results:
        if len(selected) >= top_k:
            break
        add(result)
    return selected[:top_k]


def _nonnegative_int_env(name: str, default: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError:
        return default
    return value if value >= 0 else default


def _backfill_source_local_neighbors(
    collection: Any,
    results: Sequence[Any],
    *,
    source_file: str,
    collection_count: int,
    top_k: int,
    reserved_neighbor_slots: int | None = None,
) -> list[Any]:
    from retrieval_engine.core import RetrievalResult

    if not results or top_k <= 0 or not source_file:
        return list(results)[:top_k]
    slots = (
        _nonnegative_int_env("RAG_SOURCE_NEIGHBOR_BACKFILL_SLOTS", 2)
        if reserved_neighbor_slots is None
        else max(0, reserved_neighbor_slots)
    )
    if slots <= 0:
        return list(results)[:top_k]

    source_results = _source_chunks_from_collection(
        collection,
        source_file=source_file,
        collection_count=collection_count,
    )
    if not source_results:
        return list(results)[:top_k]

    before = _positive_int_env("RAG_SOURCE_NEIGHBOR_BACKFILL_BEFORE", 1)
    after = _positive_int_env("RAG_SOURCE_NEIGHBOR_BACKFILL_AFTER", 1)
    base = list(results)[:top_k]
    protected_count = max(0, top_k - slots)
    selected: list[Any] = []
    seen: set[tuple[str, str]] = set()

    def add(result: Any) -> bool:
        key = getattr(getattr(result, "chunk", None), "identity_key", None)
        if key is None:
            key = ("text", str(getattr(result, "text", "") or ""))
        if key in seen:
            return False
        seen.add(key)
        selected.append(result)
        return True

    for result in base[:protected_count]:
        add(result)

    added_neighbors = 0
    for result in base:
        if added_neighbors >= slots:
            break
        anchor_sentence_id = _result_sentence_id(result)
        for neighbor in _neighbor_candidates_for_anchor(
            source_results,
            anchor_sentence_id=anchor_sentence_id,
            before=before,
            after=after,
        ):
            neighbor_score = max(float(getattr(result, "score", 0.0)) * 0.98, 0.000001)
            added = add(
                RetrievalResult(
                    chunk=neighbor.chunk,
                    score=neighbor_score,
                    retriever_name=getattr(result, "retriever_name", None) or "source_neighbor",
                    component_scores={
                        **getattr(neighbor, "component_scores", {}),
                        "source_neighbor_backfill": neighbor_score,
                    },
                )
            )
            if added:
                added_neighbors += 1
                if added_neighbors >= slots:
                    break

    for result in base[protected_count:]:
        if len(selected) >= top_k:
            break
        add(result)
    return selected[:top_k]


class _TemplateQueryRewriter:
    name = "template_query_rewriter"

    _ALIASES: dict[str, tuple[str, ...]] = {
        "status monitoring": ("condition monitoring", "health monitoring", "状态监测"),
        "condition monitoring": ("status monitoring", "health monitoring", "状态监测"),
        "fault diagnosis": ("failure diagnosis", "故障诊断"),
        "maintenance": ("inspection", "preventive maintenance", "维护 检查"),
        "selected as a juror": ("excusing jurors impartiality accused", "jury panel excuse juror"),
        "close friends": ("excusing jurors impartiality accused",),
        "expert knowledge": ("jury room experiments present condition object experimented",),
        "lockpicking": ("jury room experiments present condition object experimented",),
        "physical evidence": ("jury room experiments object condition evidence",),
        "news stories": ("pre-trial publicity jurors prejudice directions",),
        "news story": ("pre-trial publicity jurors prejudice directions",),
        "prior to the trial": ("pre-trial publicity jurors prejudice directions",),
        "petrol canister": ("independent inquiry notify judge juror irregularity",),
        "texts them": ("independent inquiry notify judge juror irregularity",),
        "beyond reasonable doubt": ("standard of proof beyond reasonable doubt prosecution facts",),
        "standard of proof": ("standard of proof beyond reasonable doubt prosecution facts",),
        "every claim": (
            "jury does not need to be satisfied each and every fact relied upon prove element disprove defence",
        ),
        "fully convinced": (
            "jury does not need to be satisfied each and every fact relied upon prove element disprove defence",
        ),
        "standard sentence": ("irrelevance of sentence penalty prescribed consequences verdict",),
        "30 years imprisonment": ("irrelevance of sentence penalty prescribed consequences verdict",),
        "penalty prescribed": ("irrelevance of sentence penalty prescribed consequences verdict",),
        "court travels": ("view inspection demonstration experiment court location",),
        "location relevant": ("view inspection demonstration experiment court location",),
        "eyewitness testimony": ("VARE procedure audio audiovisual recording witness violent offence",),
        "plays a recording": ("VARE procedure audio audiovisual recording witness violent offence",),
        "legal privilege": ("privilege against self-incrimination section 128 witness",),
        "self-incrimination": ("privilege against self-incrimination section 128 witness",),
        "circumstantial evidence": ("circumstantial evidence unacceptable suspect inference",),
        "alibi": ("circumstantial evidence inferences alibi",),
        "across town": ("directions about alibi evidence prosecution disprove burden guilt elsewhere",),
        "dinner with friends": ("directions about alibi evidence prosecution disprove burden guilt elsewhere",),
        "exact time": ("directions about alibi evidence prosecution disprove burden guilt elsewhere",),
        "real chance": ("directions about alibi evidence prosecution disprove burden guilt elsewhere",),
        "committed for trial": ("alibi notice leave court evidence another place alleged offence",),
        "notice has been filed": ("alibi notice leave court evidence another place alleged offence",),
        "double jeopardy": ("taking verdicts alternative charges punished more than once",),
        "uncertain of their verdict": (
            "perseverance directions extended period without reaching verdict continue deliberating",
            "majority verdict directions unanimous verdict",
        ),
        "uncertain of the verdict": (
            "perseverance directions extended period without reaching verdict continue deliberating",
            "majority verdict directions unanimous verdict",
        ),
        "continue deliberating": ("perseverance directions extended period without reaching verdict continue deliberating",),
        "gives evidence": ("accused as a witness tailored evidence warning defence witnesses",),
        "defence witnesses": ("accused as a witness tailored evidence warning",),
        "consciousness of guilt": ("post-offence lies false exculpatory statements common law",),
        "false exculpatory": ("post-offence lies consciousness of guilt",),
        "psychiatrist": ("failure to call a witness prosecution obligation material witnesses",),
        "mental impairment": ("failure to call a witness prosecution obligation material witnesses",),
        "government authority": ("silence in response equal parties right to silence",),
        "right to silence": ("no adverse inference may be drawn failure to answer questions person in authority",),
        "solely on common law": ("no adverse inference may be drawn failure to answer questions person in authority",),
        "stays silent": ("silence in response equal parties right to silence", "other post-offence behaviour silence"),
        "no comment": ("no adverse inference selective silence right to silence",),
        "selective silence": ("no adverse inference selective silence right to silence",),
        "name and age": ("no adverse inference answered some questions did not answer others right of silence",),
        "other questions": ("no adverse inference answered some questions did not answer others right of silence",),
        "answers some questions": ("no adverse inference answered some questions did not answer others right of silence",),
        "did not answer others": ("no adverse inference answered some questions did not answer others right of silence",),
        "family dinner": ("other post-offence behaviour silence implied admission",),
        "blank, expressionless stare": ("other post-offence behaviour demeanour implied admission unreliable",),
        "expressionless stare": ("other post-offence behaviour demeanour implied admission unreliable",),
        "displacement effect": ("photographic identification displacement effect section 115 direction",),
        "daytime photo": ("photographic identification displacement effect section 115 direction",),
        "police showed": ("photographic identification displacement effect section 115 direction",),
        "image used for recognising": ("photographic identification section 115 direction criminal record inference",),
        "images of the accused": ("photographic identification section 115 direction criminal record inference",),
        "shop assistant": ("identification evidence jury directions purposes recognition evidence previously known person",),
        "served the accused": ("identification evidence jury directions purposes recognition evidence previously known person",),
        "still images": ("identification evidence jury directions purposes recognition evidence previously known person",),
        "identifies him": ("identification evidence jury directions purposes recognition evidence previously known person",),
        "dna samples": (
            "jury role determining possible contributor to the forensic sample accuracy reliability expert evidence",
            "dna evidence jury directions mitochondrial y-str nuclear identical twins",
        ),
        "nuclear dna": (
            "jury role determining possible contributor to the forensic sample accuracy reliability expert evidence",
            "dna evidence jury directions mitochondrial y-str nuclear identical twins",
        ),
        "mitochondrial dna": (
            "jury role determining possible contributor to the forensic sample accuracy reliability expert evidence",
            "dna evidence jury directions mitochondrial y-str nuclear identical twins",
        ),
        "y-str": (
            "jury role determining possible contributor to the forensic sample accuracy reliability expert evidence",
            "dna evidence jury directions mitochondrial y-str nuclear identical twins",
        ),
        "forensic sample": ("jury role determining possible contributor to the forensic sample accuracy reliability expert evidence",),
        "full siblings": ("jury role determining possible contributor to the forensic sample accuracy reliability expert evidence",),
        "fails to challenge": ("browne v dunn remedies breaching rule challenge evidence unfairness",),
        "prosecution witness": ("browne v dunn remedies breaching rule challenge evidence unfairness",),
        "child witness": ("prohibited statements directions children unreliable witnesses more careful scrutiny",),
        "12 years old": ("prohibited statements directions children unreliable witnesses more careful scrutiny",),
        "good character evidence": ("evidence of good character two purposes credible less likely committed offence",),
        "accused is innocent": ("evidence of good character two purposes credible less likely committed offence",),
        "mechanic": ("admissibility opinion evidence expert specialised knowledge training study experience opinion rule",),
        "15 years": ("admissibility opinion evidence expert specialised knowledge training study experience opinion rule",),
        "expert's evidence admissible": ("admissibility opinion evidence common knowledge ultimate issue not inadmissible",),
        "expert evidence admissible": ("admissibility opinion evidence common knowledge ultimate issue not inadmissible",),
        "violent homes": ("admissibility opinion evidence common knowledge ultimate issue not inadmissible",),
        "cultural stigma": ("admissibility opinion evidence common knowledge ultimate issue not inadmissible",),
        "cool burn": ("admissibility opinion evidence traditional laws customs section 78a",),
        "first nations": ("admissibility opinion evidence traditional laws customs section 78a",),
        "poisonous mushroom": ("coincidence evidence inferential reasoning similarities improbable",),
        "mushrooms": ("coincidence evidence inferential reasoning similarities improbable",),
        "highly improbable": ("coincidence evidence improbability events occurring coincidentally inferential reasoning",),
        "coincidental": ("coincidence evidence improbability events occurring coincidentally inferential reasoning",),
        "inferential reasoning": ("coincidence evidence improbability events occurring coincidentally inferential reasoning",),
        "standalone defence": ("accident no standalone defence elements offence",),
        "an accident": ("accident no standalone defence elements offence",),
        "unexpected convulsion": ("involuntary acts involuntary muscular movements spasms convulsions",),
        "convulsion": ("involuntary acts involuntary muscular movements spasms convulsions",),
        "seizing": ("voluntary acts evidentiary presumption voluntariness inferred circumstances unconscious seizing sleepwalking",),
        "sleepwalking": ("voluntary acts evidentiary presumption voluntariness inferred circumstances unconscious seizing sleepwalking",),
        "voluntary": ("voluntary acts evidentiary presumption voluntariness inferred circumstances unconscious seizing sleepwalking",),
        "innocent agent": ("innocent agent principal offender physical elements offence",),
        "sealed package": ("innocent agent principal offender physical elements offence",),
        "only the prosecution": ("prohibited comments prosecution only version before court no defence evidence",),
        "only version": ("prohibited comments prosecution only version before court no defence evidence",),
        "involved in the commission": ("statutory complicity assists encourages directs commission offence",),
        "secondary party": ("statutory complicity assists encourages directs commission offence",),
        "party pill": ("accused mental state agreement state of mind required commission offence controlled drug",),
        "controlled drug": ("accused mental state agreement state of mind required commission offence controlled drug",),
        "substance was illegal": ("accused mental state agreement state of mind required commission offence controlled drug",),
        "commonwealth conspiracy": ("defences inconsistency criminal code conspiracy acquitted inconsistent",),
        "already been acquitted": ("defences inconsistency criminal code conspiracy acquitted inconsistent",),
        "other parties": ("defences inconsistency criminal code conspiracy acquitted inconsistent",),
        "as an admission": ("using an admission made by accused substance truthful",),
        "treated as an admission": ("using an admission made by accused substance truthful",),
        "i murdered": ("using an admission made by accused substance truthful",),
        "text from": ("using an admission made by accused substance truthful",),
        "christmas party": ("admissibility accused presence opportunity to respond silence admitted truth statement",),
        "loud": ("admissibility accused presence opportunity to respond silence admitted truth statement",),
        "not your car": ("admissibility accused presence opportunity to respond silence admitted truth statement",),
        "news story about a drive-by": ("admissibility accused presence opportunity to respond silence admitted truth statement",),
        "opportunity to respond": ("admissibility accused presence opportunity to respond silence admitted truth statement",),
        "people could get hurt": ("recklessness acted knowledge harmful consequence would probably result conduct",),
        "criminal culpability": ("recklessness acted knowledge harmful consequence would probably result conduct",),
    }

    def rewrite(self, query: str) -> list[str]:
        normalized = " ".join(str(query or "").split())
        lowered = normalized.casefold()
        rewrites: list[str] = []
        matches = [
            (phrase, replacements)
            for phrase, replacements in self._ALIASES.items()
            if phrase in lowered
        ]
        matches.sort(key=lambda item: len(item[0]), reverse=True)
        for _phrase, replacements in matches:
            rewrites.extend(replacements)
        return _unique_nonempty(rewrites)[:4]


def _unique_nonempty(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        output.append(text)
    return output


def _keyword_chunks_from_collection(collection: Any, *, collection_count: int) -> list[dict[str, Any]]:
    sample_limit = max(1, int(os.environ.get("RAG_SEARCH_KEYWORD_CORPUS_LIMIT", "10000")))
    payload = collection.get(limit=min(collection_count, sample_limit), include=["documents", "metadatas"])
    ids = payload.get("ids") or []
    documents = payload.get("documents") or []
    metadatas = payload.get("metadatas") or []
    chunks: list[dict[str, Any]] = []
    for index, document in enumerate(documents):
        metadata_value = metadatas[index] if index < len(metadatas) else {}
        metadata = dict(metadata_value) if isinstance(metadata_value, dict) else {}
        doc_id = ids[index] if index < len(ids) else metadata.get("chunk_id")
        if doc_id is not None:
            metadata.setdefault("chunk_id", str(doc_id))
            metadata.setdefault("chroma_id", str(doc_id))
        chunks.append({"text": str(document or ""), "metadata": metadata})
    return chunks


def _keyword_retriever_for_collection(
    collection: Any,
    *,
    persist_dir: Path,
    collection_name: str,
    collection_count: int,
) -> Any:
    from retrieval_engine.keyword import KeywordRetriever

    db_path = Path(persist_dir) / "chroma.sqlite3"
    try:
        mtime_ns = db_path.stat().st_mtime_ns
    except OSError:
        mtime_ns = 0
    key = (str(Path(persist_dir).resolve()), safe_collection_name(collection_name), int(collection_count), int(mtime_ns))
    cached = _KEYWORD_RETRIEVER_CACHE.get(key)
    if cached is not None:
        return cached
    retriever = KeywordRetriever(_keyword_chunks_from_collection(collection, collection_count=collection_count))
    if len(_KEYWORD_RETRIEVER_CACHE) >= _KEYWORD_RETRIEVER_CACHE_MAX:
        _KEYWORD_RETRIEVER_CACHE.pop(next(iter(_KEYWORD_RETRIEVER_CACHE)))
    _KEYWORD_RETRIEVER_CACHE[key] = retriever
    return retriever


def _hybrid_result_to_api_result(result: Any) -> dict[str, Any]:
    metadata = dict(result.metadata or {})
    component_scores = {key: round(float(value), 6) for key, value in result.component_scores.items()}
    distance = metadata.pop("_chroma_distance", None)
    if component_scores:
        metadata["component_scores"] = component_scores
    if result.retriever_name:
        metadata["retriever_name"] = result.retriever_name
    return {
        "text": result.text,
        "distance": distance,
        "score": round(float(result.score), 6),
        "similarity": round(1 - float(distance), 4) if distance is not None else round(float(result.score), 4),
        "metadata": metadata,
    }


def _positive_int_env(name: str, default: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError:
        return default
    return value if value > 0 else default


def _candidate_pool_size(top_k: int) -> int:
    multiplier = _positive_int_env("RAG_RETRIEVAL_CANDIDATE_MULTIPLIER", 16)
    minimum = _positive_int_env("RAG_RETRIEVAL_CANDIDATE_MIN", 100)
    maximum = _positive_int_env("RAG_RETRIEVAL_CANDIDATE_MAX", 300)
    return min(max(top_k * multiplier, minimum), maximum)


def _default_search_reranker() -> str | None:
    configured = os.environ.get("RAG_DEFAULT_RERANKER", "").strip().lower().replace("-", "_")
    if configured:
        if configured not in {"none", "noop", "cross_encoder"}:
            raise ValueError("RAG_DEFAULT_RERANKER must be one of: none, noop, cross_encoder")
        return None if configured == "none" else configured
    return "cross_encoder" if _cross_encoder_reranker_available() else None


def _cross_encoder_reranker_available() -> bool:
    try:
        from model_adapters.local_models import (
            DEFAULT_RERANKER_MODEL,
            is_existing_model_path,
            online_model_loading_allowed,
            resolve_local_model_path,
        )
    except Exception:  # noqa: BLE001
        return False
    resolved = resolve_local_model_path(
        DEFAULT_RERANKER_MODEL,
        env_var="RAG_RERANKER_MODEL_PATH",
        default_model=DEFAULT_RERANKER_MODEL,
    )
    return is_existing_model_path(resolved) or online_model_loading_allowed()


def _build_search_reranker(reranker: str | None) -> Any | None:
    normalized = (reranker or "none").strip().lower().replace("-", "_")
    if normalized in {"", "none"}:
        return None
    if normalized == "noop":
        from model_adapters.reranker import NoOpReranker

        return NoOpReranker()
    if normalized == "cross_encoder":
        cached = _SEARCH_RERANKER_CACHE.get(normalized)
        if cached is not None:
            return cached
        try:
            from model_adapters.reranker import CrossEncoderReranker

            reranker = CrossEncoderReranker()
            _SEARCH_RERANKER_CACHE[normalized] = reranker
            return reranker
        except Exception as exc:  # noqa: BLE001
            return _UnavailableReranker(name="cross_encoder", error=f"{exc.__class__.__name__}: {exc}")
    raise ValueError("reranker must be one of: none, noop, cross_encoder")


class _UnavailableReranker:
    def __init__(self, *, name: str, error: str) -> None:
        self.name = name
        self.error = error

    def rerank(self, query: str, documents: list[str], *, top_k: int | None = None) -> list[tuple[int, float]]:
        raise RuntimeError(self.error)


def _rerank_candidate_pool_size(top_k: int, reranker: str | None) -> int:
    if top_k <= 0:
        return 0
    normalized = (reranker or "none").strip().lower().replace("-", "_")
    if normalized in {"", "none", "noop"}:
        return top_k
    multiplier = _positive_int_env("RAG_RERANK_CANDIDATE_MULTIPLIER", 10)
    minimum = _positive_int_env("RAG_RERANK_CANDIDATE_MIN", 50)
    maximum = _positive_int_env("RAG_RERANK_CANDIDATE_MAX", 200)
    return min(max(top_k * multiplier, minimum), maximum)


def _retrieval_weights(backend_name: str | None) -> dict[str, float]:
    return {"chroma_vector": 0.5, "keyword": 1.6} if str(backend_name or "").lower() == "hashing" else {
        "chroma_vector": 1.0,
        "keyword": 1.25,
    }


def _limit_results_per_boundary(results: Sequence[Any], *, top_k: int, max_per_boundary: int = 2) -> list[Any]:
    selected: list[Any] = []
    deferred: list[Any] = []
    counts: dict[str, int] = {}
    for result in results:
        metadata = getattr(result, "metadata", {}) or {}
        boundary = str(
            metadata.get("passage_id")
            or metadata.get("sentence_id")
            or metadata.get("section_id")
            or metadata.get("boundary_id")
            or getattr(result, "chunk_id", "")
            or ""
        )
        if boundary and counts.get(boundary, 0) >= max_per_boundary:
            deferred.append(result)
            continue
        selected.append(result)
        if boundary:
            counts[boundary] = counts.get(boundary, 0) + 1
        if len(selected) >= top_k:
            return selected
    for result in deferred:
        selected.append(result)
        if len(selected) >= top_k:
            break
    return selected[:top_k]


def query_collection(
    query_text: str,
    persist_dir: Path = DEFAULT_PERSIST_DIR,
    collection_name: str = "power_equipment",
    top_k: int = 5,
    backend: str | None = None,
    model_name: str | None = None,
    query_rewrite: bool | None = None,
    reranker: str | None = None,
    graph_retriever: Any | None = None,
    filters: dict[str, Any] | None = None,
    no_answer_min_score: float | None = None,
    no_answer_min_results: int | None = None,
) -> dict:
    """Hybrid retrieval: Chroma vector recall + metadata-aware keyword recall + RRF."""
    policy_settings = _collection_retrieval_policy_settings(persist_dir, collection_name)
    policy_applied = bool(policy_settings)
    if query_rewrite is None and "query_rewrite" in policy_settings:
        query_rewrite = bool(policy_settings.get("query_rewrite"))
    if reranker is None and str(policy_settings.get("reranker") or "").strip():
        reranker = str(policy_settings.get("reranker") or "").strip()
    if no_answer_min_score is None and policy_settings.get("no_answer_min_score") is not None:
        try:
            no_answer_min_score = float(policy_settings.get("no_answer_min_score"))
        except (TypeError, ValueError):
            no_answer_min_score = None
    if no_answer_min_results is None and policy_settings.get("no_answer_min_results") is not None:
        try:
            no_answer_min_results = int(policy_settings.get("no_answer_min_results"))
        except (TypeError, ValueError):
            no_answer_min_results = None

    auto_filters = _auto_filters_from_query(query_text)
    policy_filters = policy_settings.get("filters") if isinstance(policy_settings.get("filters"), Mapping) else None
    raw_effective_filters = _combine_filter_conditions(
        [
            filters,
            policy_filters,
            *auto_filters,
        ]
    )
    effective_filters = _apply_metadata_field_aliases(
        raw_effective_filters,
        policy_settings.get("metadata_field_aliases") if isinstance(policy_settings.get("metadata_field_aliases"), Mapping) else None,
    )
    client, collection, resolved_backend = get_collection_handle(
        persist_dir=persist_dir,
        collection_name=collection_name,
        backend=backend,
        model_name=model_name,
    )
    try:
        collection_count = collection.count()
        if collection_count == 0:
            return {
                "collection": safe_collection_name(collection_name),
                "query": query_text,
                "top_k": top_k,
                "results": [],
                "retrieval_diagnostics": {
                    "retrieval_path": "hybrid",
                    "fusion_mode": "rrf",
                    "no_answer": True,
                    "no_answer_reason": "empty_collection",
                    "candidate_pool_count": 0,
                    "filters_applied": bool(effective_filters),
                    "auto_filters": auto_filters,
                    "effective_filters": effective_filters,
                    "retrieval_policy": {"applied": policy_applied, "settings": policy_settings},
                },
                "embedding_backend": resolved_backend.name,
                "embedding_model": resolved_backend.model_name,
                "embedding_warning": resolved_backend.warning,
            }

        from retrieval_engine.hybrid import HybridRetriever
        vector_retriever = _ChromaCollectionRetriever(collection)
        keyword_retriever = _keyword_retriever_for_collection(
            collection,
            persist_dir=persist_dir,
            collection_name=collection_name,
            collection_count=collection_count,
        )
        retrievers: list[Any] = [vector_retriever, keyword_retriever]
        if graph_retriever is not None:
            retrievers.append(graph_retriever)

        backend_name = str(resolved_backend.name or "").lower()
        use_query_rewrite = (backend_name != "hashing") if query_rewrite is None else bool(query_rewrite)
        if reranker is not None:
            effective_reranker = reranker
        elif backend_name == "hashing":
            # Hashing is the offline fallback path. Pulling a cross-encoder here can
            # import heavyweight local model stacks during basic ingestion/search
            # tests and desktop smoke runs, which makes the fallback fragile.
            effective_reranker = None
        else:
            effective_reranker = _default_search_reranker()
        candidate_k = min(
            collection_count,
            max(_candidate_pool_size(top_k), _rerank_candidate_pool_size(top_k, effective_reranker)),
        )
        hybrid = HybridRetriever(
            retrievers,
            weights=_retrieval_weights(resolved_backend.name),
            fusion_mode="rrf",
            rrf_k=60,
            per_retriever_k=candidate_k,
            query_rewriter=_TemplateQueryRewriter() if use_query_rewrite else None,
            reranker=_build_search_reranker(effective_reranker),
            no_answer_min_score=no_answer_min_score,
            no_answer_min_results=no_answer_min_results,
            name="hybrid",
        )
        fusion_top_k = min(collection_count, max(top_k * 4, top_k))
        hybrid_results = hybrid.retrieve(query_text, top_k=fusion_top_k, filters=effective_filters)
        source_file_filter = _source_file_filter_value(effective_filters)
        hybrid_results = _limit_results_per_boundary(hybrid_results, top_k=top_k, max_per_boundary=2)
        if source_file_filter:
            hybrid_results = _backfill_source_local_neighbors(
                collection,
                hybrid_results,
                source_file=source_file_filter,
                collection_count=collection_count,
                top_k=top_k,
            )
        results = [_hybrid_result_to_api_result(result) for result in hybrid_results]
        diagnostics = getattr(hybrid, "last_diagnostics", None)

        return {
            "collection": safe_collection_name(collection_name),
            "query": query_text,
            "top_k": top_k,
            "results": results,
            "retrieval_diagnostics": {
                "original_query": query_text,
                "rewritten_queries": list(getattr(diagnostics, "rewritten_queries", [query_text])),
                "retrieval_path": "hybrid",
                "fusion_mode": "rrf",
                "raw_candidate_count": int(getattr(diagnostics, "raw_candidate_count", len(results))),
                "filtered_candidate_count": int(getattr(diagnostics, "filtered_candidate_count", len(results))),
                "final_candidate_count": len(results),
                "candidate_pool_count": collection_count,
                "filters_applied": bool(effective_filters),
                "auto_filters": auto_filters,
                "effective_filters": effective_filters,
                "retrieval_policy": {"applied": policy_applied, "settings": policy_settings},
                "reranker_name": getattr(diagnostics, "reranker_name", None),
                "reranker_error": getattr(diagnostics, "reranker_error", None),
                "no_answer": bool(getattr(diagnostics, "no_answer", False)),
                "no_answer_reason": getattr(diagnostics, "no_answer_reason", None),
                "retrievers": [
                    {
                        "name": str(getattr(retriever, "name", retriever.__class__.__name__)),
                        "candidate_count": int(getattr(retriever, "candidate_count", 0)),
                    }
                    for retriever in retrievers
                ],
            },
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
        repair_note = _try_repair_legacy_chroma_store(persist_dir, exc)
        if repair_note:
            try:
                client = _open_chroma_client(persist_dir)
                print(f"Recovered legacy Chroma store in place: {repair_note}")
                return client
            except Exception as retry_exc:
                exc = retry_exc
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


def _try_repair_legacy_chroma_store(persist_dir: Path, exc: Exception) -> str | None:
    db_path = persist_dir / "chroma.sqlite3"
    if not db_path.exists() or not db_path.is_file():
        return None
    message = str(exc).lower()
    if "default_tenant" not in message and "could not connect to tenant" not in message and "tenant" not in message:
        return None

    con: sqlite3.Connection | None = None
    try:
        con = sqlite3.connect(str(db_path))
        table_names = {
            row[0]
            for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if not {"tenants", "databases"}.issubset(table_names):
            return None

        changes: list[str] = []
        if not _sqlite_row_exists(con, "tenants", "id", "default_tenant"):
            _copy_sqlite_before_repair(db_path)
            con.execute("INSERT INTO tenants(id) VALUES (?)", ("default_tenant",))
            changes.append("inserted default_tenant")

        if not _sqlite_row_exists(con, "databases", "name", "default_database"):
            _copy_sqlite_before_repair(db_path)
            con.execute(
                "INSERT INTO databases(id, name, tenant_id) VALUES (?, ?, ?)",
                ("00000000-0000-0000-0000-000000000000", "default_database", "default_tenant"),
            )
            changes.append("inserted default_database")

        database_row = con.execute(
            "SELECT id FROM databases WHERE name = ? LIMIT 1",
            ("default_database",),
        ).fetchone()
        default_database_id = (
            str(database_row[0])
            if database_row and database_row[0]
            else "00000000-0000-0000-0000-000000000000"
        )

        database_columns = _sqlite_columns(con, "databases")
        if "tenant_id" in database_columns:
            updated = con.execute(
                "UPDATE databases SET tenant_id = ? WHERE name = ? AND (tenant_id IS NULL OR tenant_id = '')",
                ("default_tenant", "default_database"),
            ).rowcount
            if updated:
                _copy_sqlite_before_repair(db_path)
                changes.append("linked default_database to default_tenant")

        collection_columns = _sqlite_columns(con, "collections")
        if "database_id" in collection_columns:
            updated = con.execute(
                "UPDATE collections SET database_id = ? WHERE database_id IS NULL OR database_id = ''",
                (default_database_id,),
            ).rowcount
            if updated:
                _copy_sqlite_before_repair(db_path)
                changes.append(f"linked {updated} collections to default_database")

        if not changes:
            return None
        con.commit()
        return "; ".join(changes)
    except sqlite3.Error:
        return None
    except OSError:
        return None
    finally:
        if con is not None:
            con.close()


def _sqlite_row_exists(con: sqlite3.Connection, table: str, column: str, value: str) -> bool:
    row = con.execute(f"SELECT 1 FROM {table} WHERE {column} = ? LIMIT 1", (value,)).fetchone()
    return row is not None


def _sqlite_columns(con: sqlite3.Connection, table: str) -> set[str]:
    try:
        return {row[1] for row in con.execute(f"PRAGMA table_info({table})")}
    except sqlite3.Error:
        return set()


def _copy_sqlite_before_repair(db_path: Path) -> None:
    backup_pattern = f"{db_path.name}.repair_backup_*"
    if any(db_path.parent.glob(backup_pattern)):
        return
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = db_path.with_name(f"{db_path.name}.repair_backup_{timestamp}")
    counter = 1
    while backup_path.exists():
        backup_path = db_path.with_name(f"{db_path.name}.repair_backup_{timestamp}_{counter}")
        counter += 1
    shutil.copy2(db_path, backup_path)


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
