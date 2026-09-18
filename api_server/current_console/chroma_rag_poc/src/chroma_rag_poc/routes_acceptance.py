"""Local, evidence-backed PRD acceptance workbench endpoints."""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from evaluation.prd_acceptance import (
    ACCEPTANCE_CANDIDATE_FILES,
    ACCEPTANCE_RESPONSIBILITY,
    build_acceptance_work_items,
    evaluate_prd_acceptance,
    write_acceptance_package,
)

router = APIRouter(prefix="/api/delivery/acceptance", tags=["prd-acceptance"])

MAX_ARTIFACT_BYTES = 2 * 1024 * 1024
MAX_EVIDENCE_BYTES = 25 * 1024 * 1024
ALLOWED_EVIDENCE_SUFFIXES = {
    ".csv",
    ".docx",
    ".html",
    ".jpeg",
    ".jpg",
    ".json",
    ".jsonl",
    ".log",
    ".md",
    ".pdf",
    ".png",
    ".txt",
    ".webp",
    ".xlsx",
}
ACCEPTANCE_PACKAGE_FILES = {
    "acceptance.json",
    "acceptance.md",
    "human_review_handoff.md",
    "manifest.json",
    "work_items.json",
}

ARTIFACT_SPECS: dict[str, dict[str, Any]] = {
    "ocr_coverage": {
        "filename": "ocr_coverage.json",
        "format": "json",
        "gate_ids": ["AC-M2-01"],
        "template": {
            "total_documents": 0,
            "total_pages": 0,
            "text_or_structure_pages": 0,
            "blocked_pages": 0,
            "blocked_page_records": [],
            "spotchecks": [],
        },
    },
    "ocr_gold": {
        "filename": "ocr_gold.jsonl",
        "format": "jsonl",
        "gate_ids": ["AC-M2-02"],
        "template": [
            {
                "id": "ocr-001",
                "category": "clear",
                "source_file": "",
                "page_num": 1,
                "gold_text": "",
                "predicted_text": "",
                "critical_fields": [],
                "reviewer": "",
                "reviewed_at": "",
                "evidence_ref": "",
            }
        ],
    },
    "retrieval_gold": {
        "filename": "retrieval_gold.jsonl",
        "format": "jsonl",
        "gate_ids": ["AC-M3-01", "AC-M3-02"],
        "template": [
            {
                "id": "q-001",
                "question": "",
                "case_type": "ordinary",
                "passed": False,
                "relevant_evidence_ids": [],
                "retrieved_evidence_ids": [],
                "citations": [],
                "reviewer": "",
                "reviewed_at": "",
                "evidence_ref": "",
            }
        ],
    },
    "graph_gold": {
        "filename": "graph_gold.json",
        "format": "json",
        "gate_ids": ["AC-M4-01", "AC-M4-02"],
        "template": {
            "gold_relations": [],
            "predicted_relations": [],
            "published_statements": [],
            "same_question_comparison": [],
            "review": {"reviewer": "", "reviewed_at": "", "evidence_refs": []},
        },
    },
    "fmea_expert": {
        "filename": "fmea_expert.jsonl",
        "format": "jsonl",
        "gate_ids": ["AC-M5-01"],
        "template": [
            {
                "item_id": "F-001",
                "fields": {},
                "field_evidence": {},
                "expert_decision": "accepted",
                "severity": None,
                "occurrence": None,
                "detection": None,
                "rpn": None,
                "reviewer": "",
                "reviewed_at": "",
                "evidence_ref": "",
            }
        ],
    },
    "fmea_export_verification": {
        "filename": "fmea_export_verification.json",
        "format": "json",
        "gate_ids": ["AC-M5-02"],
        "template": {
            "row_count": 0,
            "json_rows": 0,
            "csv_rows": 0,
            "docx_rows": 0,
            "docx_verified": False,
            "consistent": False,
            "lineage_consistent": False,
            "review": {"reviewer": "", "reviewed_at": "", "evidence_refs": []},
        },
    },
    "e2e_signoff": {
        "filename": "e2e_signoff.json",
        "format": "json",
        "gate_ids": ["AC-E2E-01", "AC-E2E-02"],
        "template": {
            "knowledge_engineer": "",
            "domain_reviewer": "",
            "ui_only": True,
            "operations": {},
            "signed_at": "",
            "signatures": [],
            "evidence_refs": [],
        },
    },
    "performance": {
        "filename": "performance.json",
        "format": "json",
        "gate_ids": ["TECH-15"],
        "template": {
            "windows_reference_device": "",
            "pilot_document_count": 14,
            "embedding_model": "",
            "retrieval_seconds": [],
            "graph_path_seconds": [],
            "preview_seconds": [],
            "review": {"reviewer": "", "reviewed_at": "", "evidence_refs": []},
        },
    },
    "large_file": {
        "filename": "large_file.json",
        "format": "json",
        "gate_ids": ["TECH-16"],
        "template": {
            "file_size_mb": 60,
            "task_id": "",
            "source_sha256": "",
            "asynchronous": False,
            "progress_visible": False,
            "browser_frozen": False,
            "request_timed_out": False,
            "review": {"reviewer": "", "reviewed_at": "", "evidence_refs": []},
        },
    },
}


class ArtifactWriteRequest(BaseModel):
    payload: dict[str, Any] | list[dict[str, Any]]
    expected_sha256: str | None = None


def _acceptance_input_root(request: Request) -> Path:
    configured = getattr(request.app.state, "acceptance_input_dir", None)
    if configured is None:
        configured = os.environ.get("POWER_RAG_ACCEPTANCE_INPUT_DIR")
    root = (
        Path(configured)
        if configured
        else Path(__file__).resolve().parents[5]
        / "evaluation"
        / "prd_acceptance_current_inputs"
    )
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def _acceptance_output_root(request: Request) -> Path:
    configured = getattr(request.app.state, "acceptance_output_dir", None)
    if configured is None:
        configured = os.environ.get("POWER_RAG_ACCEPTANCE_OUTPUT_DIR")
    root = (
        Path(configured)
        if configured
        else Path(__file__).resolve().parents[5] / "build" / "prd_acceptance_current"
    )
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def _require_acceptance_manager(request: Request) -> str:
    actor = str(getattr(request.state, "delivery_actor", "local-user") or "local-user")
    mode = str(getattr(request.app.state, "delivery_auth_mode", "local") or "local").lower()
    if mode != "oidc":
        return actor
    allowed = {
        item.strip().casefold()
        for item in os.environ.get(
            "POWER_RAG_ACCEPTANCE_GROUPS",
            "acceptance-managers,admin,owner",
        ).split(",")
        if item.strip()
    }
    groups = {
        str(item).strip().casefold()
        for item in getattr(request.state, "delivery_groups", [])
        if str(item).strip()
    }
    if not groups.intersection(allowed):
        raise HTTPException(
            status_code=403,
            detail={
                "code": "acceptance_access_denied",
                "message": "PRD acceptance workbench requires an acceptance manager role",
            },
        )
    return actor


def _artifact_spec(key: str) -> dict[str, Any]:
    spec = ARTIFACT_SPECS.get(str(key).strip())
    if spec is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "acceptance_artifact_not_found", "artifact": key},
        )
    return spec


def _artifact_for_gate(gate_id: str) -> tuple[str, dict[str, Any]]:
    for key, spec in ARTIFACT_SPECS.items():
        if gate_id in spec["gate_ids"]:
            return key, spec
    raise HTTPException(
        status_code=404,
        detail={"code": "acceptance_gate_artifact_not_found", "gate_id": gate_id},
    )


def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_artifact(path: Path, artifact_format: str) -> dict[str, Any] | list[dict[str, Any]]:
    if not path.is_file():
        return {} if artifact_format == "json" else []
    if artifact_format == "jsonl":
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=409,
            detail={"code": "acceptance_artifact_invalid", "path": path.name},
        )
    return payload


def _serialize_artifact(payload: Any, artifact_format: str) -> bytes:
    if artifact_format == "jsonl":
        if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
            raise HTTPException(
                status_code=422,
                detail={"code": "acceptance_jsonl_rows_required"},
            )
        text = "\n".join(
            json.dumps(item, ensure_ascii=False, sort_keys=True) for item in payload
        )
        return (text + ("\n" if text else "")).encode("utf-8")
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=422,
            detail={"code": "acceptance_json_object_required"},
        )
    return (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_bytes(content)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _append_audit(root: Path, *, actor: str, action: str, details: dict[str, Any]) -> None:
    entry = {
        "timestamp": datetime.now(UTC).isoformat(),
        "actor": actor,
        "action": action,
        **details,
    }
    with (root / "acceptance_audit.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")


def _status_payload(root: Path) -> dict[str, Any]:
    result = evaluate_prd_acceptance(root)
    return {
        **result,
        "work_items": build_acceptance_work_items(result, input_dir=root),
    }


@router.get("/status")
async def acceptance_status(request: Request):
    _require_acceptance_manager(request)
    root = _acceptance_input_root(request)
    return _status_payload(root)


@router.get("/schema")
async def acceptance_schema(request: Request):
    _require_acceptance_manager(request)
    artifacts = []
    for key, spec in ARTIFACT_SPECS.items():
        owner_roles = sorted(
            {
                role
                for gate_id in spec["gate_ids"]
                for role in ACCEPTANCE_RESPONSIBILITY[gate_id]["owner_roles"]
            }
        )
        artifacts.append({"key": key, **spec, "owner_roles": owner_roles})
    return {
        "artifacts": artifacts,
        "evidence_max_bytes": MAX_EVIDENCE_BYTES,
        "evidence_suffixes": sorted(ALLOWED_EVIDENCE_SUFFIXES),
    }


@router.get("/artifacts/{artifact_key}")
async def get_acceptance_artifact(request: Request, artifact_key: str):
    _require_acceptance_manager(request)
    spec = _artifact_spec(artifact_key)
    path = _acceptance_input_root(request) / spec["filename"]
    return {
        "key": artifact_key,
        "filename": spec["filename"],
        "format": spec["format"],
        "exists": path.is_file(),
        "sha256": _sha256(path),
        "payload": _read_artifact(path, spec["format"]) if path.is_file() else spec["template"],
    }


@router.get("/candidates/{gate_id}")
async def get_acceptance_candidate(request: Request, gate_id: str):
    _require_acceptance_manager(request)
    normalized_gate = str(gate_id).strip().upper()
    candidate_files = ACCEPTANCE_CANDIDATE_FILES.get(normalized_gate) or []
    if not candidate_files:
        raise HTTPException(
            status_code=404,
            detail={"code": "acceptance_candidate_not_declared", "gate_id": normalized_gate},
        )
    root = _acceptance_input_root(request)
    artifact_key, spec = _artifact_for_gate(normalized_gate)
    loaded: list[dict[str, Any]] = []
    for relative in candidate_files:
        candidate = (root / relative).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail={"code": "acceptance_candidate_path_invalid"},
            ) from exc
        if not candidate.is_file():
            continue
        suffix = candidate.suffix.lower()
        if suffix == ".jsonl":
            payload: Any = _read_artifact(candidate, "jsonl")
        elif suffix == ".json":
            payload = _read_artifact(candidate, "json")
        else:
            raise HTTPException(
                status_code=415,
                detail={"code": "acceptance_candidate_type_unsupported", "suffix": suffix},
            )
        loaded.append(
            {
                "path": relative,
                "sha256": _sha256(candidate),
                "payload": payload,
            }
        )
    if not loaded:
        raise HTTPException(
            status_code=404,
            detail={"code": "acceptance_candidate_not_found", "gate_id": normalized_gate},
        )
    candidate_payload = loaded[0]["payload"]
    if normalized_gate == "AC-M2-01":
        current_path = root / spec["filename"]
        current = (
            _read_artifact(current_path, spec["format"])
            if current_path.is_file()
            else dict(spec["template"])
        )
        candidate_payload = {
            **dict(current),
            "spotchecks": list(dict(candidate_payload).get("spotchecks") or []),
        }
    formal_path = root / spec["filename"]
    return {
        "gate_id": normalized_gate,
        "artifact_key": artifact_key,
        "filename": spec["filename"],
        "format": spec["format"],
        "formal_sha256": _sha256(formal_path),
        "payload": candidate_payload,
        "sources": [{"path": item["path"], "sha256": item["sha256"]} for item in loaded],
        "warning": "候选材料尚未签字；必须逐项复核并填写真实审核身份后才能保存为正式证据。",
    }


@router.put("/artifacts/{artifact_key}")
async def put_acceptance_artifact(
    request: Request,
    artifact_key: str,
    submission: ArtifactWriteRequest,
):
    actor = _require_acceptance_manager(request)
    spec = _artifact_spec(artifact_key)
    root = _acceptance_input_root(request)
    path = root / spec["filename"]
    previous_sha256 = _sha256(path)
    expected = str(submission.expected_sha256 or "").strip().lower() or None
    if previous_sha256 is not None and expected is None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "acceptance_expected_sha256_required",
                "current_sha256": previous_sha256,
            },
        )
    if expected is not None and expected != previous_sha256:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "acceptance_version_conflict",
                "expected_sha256": expected,
                "current_sha256": previous_sha256,
            },
        )
    content = _serialize_artifact(submission.payload, spec["format"])
    if len(content) > MAX_ARTIFACT_BYTES:
        raise HTTPException(
            status_code=413,
            detail={"code": "acceptance_artifact_too_large", "max_bytes": MAX_ARTIFACT_BYTES},
        )
    _atomic_write(path, content)
    current_sha256 = hashlib.sha256(content).hexdigest()
    _append_audit(
        root,
        actor=actor,
        action="acceptance_artifact_write",
        details={
            "artifact": artifact_key,
            "filename": spec["filename"],
            "previous_sha256": previous_sha256,
            "current_sha256": current_sha256,
            "record_count": len(submission.payload) if isinstance(submission.payload, list) else 1,
        },
    )
    return {
        "artifact": artifact_key,
        "filename": spec["filename"],
        "sha256": current_sha256,
        "status": _status_payload(root),
    }


@router.post("/evidence", status_code=201)
async def upload_acceptance_evidence(
    request: Request,
    gate_id: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
):
    actor = _require_acceptance_manager(request)
    normalized_gate = str(gate_id).strip().upper()
    if normalized_gate not in ACCEPTANCE_RESPONSIBILITY:
        raise HTTPException(
            status_code=422,
            detail={"code": "acceptance_gate_invalid", "gate_id": gate_id},
        )
    original_name = Path(str(file.filename or "evidence.bin")).name
    suffix = Path(original_name).suffix.lower()
    if suffix not in ALLOWED_EVIDENCE_SUFFIXES:
        raise HTTPException(
            status_code=415,
            detail={
                "code": "acceptance_evidence_type_unsupported",
                "suffix": suffix,
                "allowed": sorted(ALLOWED_EVIDENCE_SUFFIXES),
            },
        )
    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(original_name).stem).strip("-.")
    safe_stem = safe_stem[:80] or "evidence"
    reference = Path("evidence") / normalized_gate.lower() / f"{uuid4().hex}-{safe_stem}{suffix}"
    root = _acceptance_input_root(request)
    destination = (root / reference).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.tmp")
    digest = hashlib.sha256()
    size = 0
    try:
        with temporary.open("wb") as handle:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_EVIDENCE_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail={
                            "code": "acceptance_evidence_too_large",
                            "max_bytes": MAX_EVIDENCE_BYTES,
                        },
                    )
                digest.update(chunk)
                handle.write(chunk)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
        await file.close()
    sha256 = digest.hexdigest()
    _append_audit(
        root,
        actor=actor,
        action="acceptance_evidence_upload",
        details={
            "gate_id": normalized_gate,
            "evidence_ref": reference.as_posix(),
            "byte_size": size,
            "sha256": sha256,
        },
    )
    return {
        "gate_id": normalized_gate,
        "evidence_ref": reference.as_posix(),
        "byte_size": size,
        "sha256": sha256,
    }


@router.get("/evidence/{reference:path}")
async def get_acceptance_evidence(request: Request, reference: str):
    _require_acceptance_manager(request)
    root = _acceptance_input_root(request)
    candidate = (root / reference).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "acceptance_evidence_path_invalid"},
        ) from exc
    if not candidate.is_file() or candidate.parent == root:
        raise HTTPException(
            status_code=404,
            detail={"code": "acceptance_evidence_not_found"},
        )
    return FileResponse(candidate, filename=candidate.name)


@router.post("/build-package")
async def build_acceptance_package(request: Request):
    actor = _require_acceptance_manager(request)
    input_root = _acceptance_input_root(request)
    output_root = _acceptance_output_root(request)
    current = _status_payload(input_root)
    _append_audit(
        input_root,
        actor=actor,
        action="acceptance_package_build_requested",
        details={
            "overall_status": current["overall_status"],
            "open_item_count": current["work_items"]["open_item_count"],
            "manifest_path": str(output_root / "manifest.json"),
        },
    )
    result = write_acceptance_package(input_root, output_root)
    return {
        **result,
        "package_files": [
            {
                "filename": filename,
                "download_url": f"/api/delivery/acceptance/package-files/{filename}",
            }
            for filename in sorted(ACCEPTANCE_PACKAGE_FILES)
        ],
    }


@router.get("/handoff")
async def get_acceptance_handoff(request: Request):
    _require_acceptance_manager(request)
    path = _acceptance_output_root(request) / "human_review_handoff.md"
    if not path.is_file():
        raise HTTPException(
            status_code=404,
            detail={
                "code": "acceptance_package_not_built",
                "message": "请先生成验收包。",
            },
        )
    return {
        "filename": path.name,
        "sha256": _sha256(path),
        "content": path.read_text(encoding="utf-8"),
        "download_url": f"/api/delivery/acceptance/package-files/{path.name}",
    }


@router.get("/package-files/{package_file}")
async def download_acceptance_package_file(request: Request, package_file: str):
    _require_acceptance_manager(request)
    filename = Path(str(package_file)).name
    if filename != package_file or filename not in ACCEPTANCE_PACKAGE_FILES:
        raise HTTPException(
            status_code=404,
            detail={"code": "acceptance_package_file_not_allowed"},
        )
    path = _acceptance_output_root(request) / filename
    if not path.is_file():
        raise HTTPException(
            status_code=404,
            detail={"code": "acceptance_package_file_not_found", "filename": filename},
        )
    return FileResponse(path, filename=filename)
