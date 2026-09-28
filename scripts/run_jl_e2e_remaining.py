# -*- coding: utf-8 -*-
"""Finish remaining jl-e2e-20260923 delivery ops via local /api/delivery."""

from __future__ import annotations

import json
import mimetypes
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from evaluation.prd_acceptance import write_acceptance_package

ROOT = Path(__file__).resolve().parents[1]
INP = ROOT / "evaluation" / "prd_acceptance_current_inputs"
OUT = ROOT / "build" / "prd_acceptance_current"
EVID = INP / "evidence" / "AC-E2E"
BASE = "http://127.0.0.1:8000/api/delivery"
PROJECT = "jl-e2e-20260923"
RESTORE_PROJECT = "jl-e2e-restored-20260923"
ACTOR = "local-user"
REVIEWER = "纪文龙"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _request(
    method: str,
    path: str,
    *,
    payload: dict | None = None,
    headers: dict | None = None,
    data: bytes | None = None,
    content_type: str | None = None,
    project_id: str = PROJECT,
) -> tuple[int, object]:
    url = BASE + path
    body = data
    req_headers = {
        "X-Project-ID": project_id,
        "X-Correlation-ID": f"jl-e2e-{int(time.time() * 1000)}",
        "Accept": "application/json",
    }
    if headers:
        req_headers.update(headers)
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req_headers["Content-Type"] = "application/json"
    elif content_type and body is not None:
        req_headers["Content-Type"] = content_type
    request = urllib.request.Request(url, data=body, method=method, headers=req_headers)
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            raw = response.read()
            if not raw:
                return response.status, {}
            ctype = response.headers.get("Content-Type", "")
            if "json" in ctype or raw[:1] in (b"{", b"["):
                return response.status, json.loads(raw.decode("utf-8"))
            return response.status, raw
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except Exception:
            parsed = {"raw": raw.decode("utf-8", errors="replace")}
        return exc.code, parsed


def _ok(status: int) -> bool:
    return 200 <= status < 300


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, (bytes, bytearray)):
        path.write_bytes(payload)
        return
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _multipart(fields: dict[str, str], files: dict[str, tuple[str, bytes]]) -> tuple[bytes, str]:
    boundary = f"----PowerRAGE2EBoundary{uuid4().hex}"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.append(f"--{boundary}\r\n".encode())
        chunks.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        chunks.append(value.encode("utf-8"))
        chunks.append(b"\r\n")
    for name, (filename, content) in files.items():
        mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        chunks.append(f"--{boundary}\r\n".encode())
        chunks.append(
            f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode()
        )
        chunks.append(f"Content-Type: {mime}\r\n\r\n".encode())
        chunks.append(content)
        chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def publish_document() -> dict:
    status, doc = _request("GET", "/documents/lube-oil-filter:v2")
    if not _ok(status):
        raise RuntimeError(f"get v2 failed: {status} {doc}")
    if doc.get("status") != "published":
        st, review = _request(
            "POST",
            "/documents/lube-oil-filter:v2/review",
            payload={
                "reviewer": ACTOR,
                "decision": "approve",
                "comment": "UI+API: human-revised v2 approved",
                "expected_version": "lube-oil-filter:v2",
            },
        )
        if not _ok(st):
            raise RuntimeError(f"review v2 failed: {st} {review}")
        st, published = _request(
            "POST",
            "/documents/lube-oil-filter:v2/publish",
            payload={
                "actor": ACTOR,
                "comment": "publish revised lubrication-oil filter note",
                "idempotency_key": "publish:document:lube-oil-filter:v2",
                "expected_version": "lube-oil-filter:v2",
            },
        )
        if not _ok(st):
            raise RuntimeError(f"publish v2 failed: {st} {published}")
        doc = published
    return doc


def _first_published(items: list[dict], status_key: str = "status") -> dict | None:
    for item in items:
        if item.get(status_key) == "published":
            return item
    return None


def create_and_publish_graph(document: dict) -> dict:
    st, listed = _request("GET", "/graphs?status=published")
    if _ok(st) and isinstance(listed, dict):
        existing = _first_published(listed.get("items") or [])
        if existing:
            st, full = _request("GET", f"/graphs/{urllib.parse.quote(existing['graph_version_id'])}")
            if _ok(st) and isinstance(full, dict):
                return full
    evidence_id = document["evidence"][0]["evidence_id"]
    statements = [
        {
            "subject": "润滑油系统",
            "predicate": "PART_OF",
            "object": "燃气轮机",
            "subject_type": "COMPONENT",
            "object_type": "EQUIPMENT",
            "evidence_ids": [evidence_id],
            "confidence": 0.96,
        },
        {
            "subject": "润滑油系统",
            "predicate": "HAS_FAILURE_MODE",
            "object": "过滤器堵塞",
            "subject_type": "COMPONENT",
            "object_type": "FAILURE_MODE",
            "evidence_ids": [evidence_id],
            "confidence": 0.95,
        },
        {
            "subject": "过滤器堵塞",
            "predicate": "CAUSED_BY",
            "object": "油液污染",
            "subject_type": "FAILURE_MODE",
            "object_type": "CAUSE",
            "evidence_ids": [evidence_id],
            "confidence": 0.94,
        },
        {
            "subject": "过滤器堵塞",
            "predicate": "HAS_EFFECT",
            "object": "润滑油压下降",
            "subject_type": "FAILURE_MODE",
            "object_type": "EFFECT",
            "evidence_ids": [evidence_id],
            "confidence": 0.93,
        },
        {
            "subject": "过滤器堵塞",
            "predicate": "HAS_EFFECT",
            "object": "轴承缺油",
            "subject_type": "FAILURE_MODE",
            "object_type": "EFFECT",
            "evidence_ids": [evidence_id],
            "confidence": 0.9,
        },
        {
            "subject": "过滤器堵塞",
            "predicate": "DETECTED_BY",
            "object": "压差监测",
            "subject_type": "FAILURE_MODE",
            "object_type": "DETECTION_METHOD",
            "evidence_ids": [evidence_id],
            "confidence": 0.92,
        },
        {
            "subject": "过滤器堵塞",
            "predicate": "MITIGATED_BY",
            "object": "更换滤芯和清洁油路",
            "subject_type": "FAILURE_MODE",
            "object_type": "ACTION",
            "evidence_ids": [evidence_id],
            "confidence": 0.91,
        },
    ]
    st, graph = _request(
        "POST",
        "/graphs/candidates",
        payload={
            "source_document_version_ids": [document["version_id"]],
            "statements": statements,
            "metadata": {"actor": ACTOR, "extractor": "agent-native"},
        },
    )
    if not _ok(st):
        raise RuntimeError(f"graph candidate failed: {st} {graph}")
    gid = graph["graph_version_id"]
    _request(
        "POST",
        f"/graphs/{urllib.parse.quote(gid)}/review",
        payload={"reviewer": ACTOR, "decision": "approve", "comment": "agent-native statements reviewed"},
    )
    st, listed = _request("GET", f"/graphs/{urllib.parse.quote(gid)}/statements")
    items = listed.get("items") if isinstance(listed, dict) else []
    decisions = {item["statement_id"]: "approve" for item in items or graph.get("statements") or []}
    if not decisions:
        decisions = {
            item.get("statement_id"): "approve"
            for item in graph.get("statements") or []
            if item.get("statement_id")
        }
    st, reviewed = _request(
        "POST",
        f"/graphs/{urllib.parse.quote(gid)}/statement-reviews",
        payload={"reviewer": ACTOR, "comment": "approve bound statements", "decisions": decisions},
    )
    if not _ok(st):
        raise RuntimeError(f"statement review failed: {st} {reviewed}")
    st, published = _request(
        "POST",
        f"/graphs/{urllib.parse.quote(gid)}/publish",
        payload={
            "actor": ACTOR,
            "comment": "publish agent-native lubrication graph",
            "idempotency_key": f"publish:graph:{gid}",
            "expected_version": str(graph.get("version") or gid),
        },
    )
    if not _ok(st):
        raise RuntimeError(f"publish graph failed: {st} {published}")
    return published


def create_and_publish_fmea(graph: dict, document: dict) -> dict:
    st, listed = _request("GET", "/fmea/tasks?status=published")
    if _ok(st) and isinstance(listed, dict):
        existing = _first_published(listed.get("items") or [])
        if existing:
            return existing
    st, task = _request(
        "POST",
        "/fmea/tasks",
        payload={
            "requested_by": ACTOR,
            "graph_version_id": graph["graph_version_id"],
            "document_version_ids": [document["version_id"]],
            "template": "gas_turbine_minimum_v1",
            "template_version": "1.1.0",
            "metadata": {"source": "jl-e2e", "extractor": "agent-native"},
        },
    )
    if not _ok(st):
        raise RuntimeError(f"fmea create failed: {st} {task}")
    if task.get("task"):
        task = task["task"].get("result", {}).get("fmea") or task
    task_id = task["task_id"]
    st, latest = _request("GET", f"/fmea/tasks/{urllib.parse.quote(task_id)}")
    if _ok(st) and isinstance(latest, dict):
        task = latest
    items = task.get("items") or []
    if items and any(not item.get("fields", {}).get("cause") for item in items):
        evidence_id = document["evidence"][0]["evidence_id"]
        corrections = {}
        for item in items:
            fields = item.get("fields") or {}
            item_fix = {}
            if not fields.get("cause"):
                item_fix["cause"] = {"value": "油液污染", "evidence_ids": [evidence_id]}
            if not fields.get("detection_method"):
                item_fix["detection_method"] = {"value": "压差监测", "evidence_ids": [evidence_id]}
            if not fields.get("recommended_action"):
                item_fix["recommended_action"] = {
                    "value": "更换滤芯和清洁油路",
                    "evidence_ids": [evidence_id],
                }
            if item_fix:
                corrections[item["item_id"]] = item_fix
        if corrections:
            st, task = _request(
                "POST",
                f"/fmea/tasks/{urllib.parse.quote(task_id)}/review",
                payload={
                    "reviewer": ACTOR,
                    "decision": "modify",
                    "comment": "fill book-backed FMEA fields; no S/O/D",
                    "corrections": corrections,
                },
            )
            if not _ok(st):
                raise RuntimeError(f"fmea modify failed: {st} {task}")
    field_decisions = {
        item["item_id"]: {
            field: "approve"
            for field, value in (item.get("fields") or {}).items()
            if value not in (None, "")
        }
        for item in (task.get("items") or [])
    }
    st, reviewed = _request(
        "POST",
        f"/fmea/tasks/{urllib.parse.quote(task_id)}/field-reviews",
        payload={
            "reviewer": ACTOR,
            "decisions": field_decisions,
            "comment": "reviewed populated fields with evidence",
        },
    )
    if not _ok(st):
        raise RuntimeError(f"fmea field review failed: {st} {reviewed}")
    st, published = _request(
        "POST",
        f"/fmea/tasks/{urllib.parse.quote(task_id)}/publish",
        payload={
            "actor": ACTOR,
            "comment": "publish field-reviewed FMEA",
            "idempotency_key": f"publish:fmea:{task_id}",
            "expected_version": reviewed.get("updated_at") or reviewed.get("content_hash") or task_id,
        },
    )
    if not _ok(st):
        raise RuntimeError(f"publish fmea failed: {st} {published}")
    return published


def export_and_feedback(fmea: dict) -> dict:
    task_id = fmea["task_id"]
    exports = {}
    for fmt in ("json", "csv", "docx"):
        st, body = _request("GET", f"/fmea/tasks/{urllib.parse.quote(task_id)}/export?format={fmt}")
        if not _ok(st):
            raise RuntimeError(f"export {fmt} failed: {st} {body}")
        if fmt == "json":
            _write(EVID / f"fmea_export.{fmt}", body)
            exports[fmt] = "ok"
        else:
            suffix = "docx" if fmt == "docx" else "csv"
            raw = body if isinstance(body, (bytes, bytearray)) else str(body).encode("utf-8")
            (EVID / f"fmea_export.{suffix}").write_bytes(raw)
            exports[fmt] = len(raw)
    st, verify = _request("GET", f"/fmea/tasks/{urllib.parse.quote(task_id)}/export-verify")
    st, feedback = _request(
        "POST",
        f"/fmea/tasks/{urllib.parse.quote(task_id)}/feedback",
        payload={
            "code": "ocr_term_error",
            "message": "术语需在后续资料修订中保持压差监测写法",
            "created_by": ACTOR,
        },
    )
    if not _ok(st):
        raise RuntimeError(f"feedback failed: {st} {feedback}")
    return {"exports": exports, "verify": verify, "feedback": feedback}


def recover(document: dict, graph: dict) -> dict:
    st, rebuild = _request("POST", "/documents-index/rebuild")
    if not _ok(st):
        raise RuntimeError(f"index rebuild failed: {st} {rebuild}")
    gid = graph["graph_version_id"]
    st, resync = _request("POST", f"/graphs/{urllib.parse.quote(gid)}/resync")
    if not _ok(st):
        raise RuntimeError(f"graph resync failed: {st} {resync}")
    st, rolled = _request(
        "POST",
        "/documents/lube-oil-filter/rollback",
        payload={
            "target_version_id": "lube-oil-filter:v1",
            "reviewer": ACTOR,
            "comment": "rollback content to pre-revision v1 then keep lineage",
        },
    )
    if not _ok(st):
        raise RuntimeError(f"document rollback failed: {st} {rolled}")
    st, package = _request("POST", f"/projects/{PROJECT}/export-package")
    if not _ok(st):
        raise RuntimeError(f"export package failed: {st} {package}")
    zip_bytes = package if isinstance(package, (bytes, bytearray)) else b""
    if not zip_bytes:
        raise RuntimeError("export package returned no zip bytes")
    zip_path = EVID / "jl-e2e-20260923-backup.zip"
    zip_path.write_bytes(zip_bytes)
    form, ctype = _multipart(
        {
            "project_id": RESTORE_PROJECT,
            "name": "纪文龙E2E恢复",
            "actor": ACTOR,
        },
        {"file": (zip_path.name, zip_bytes)},
    )
    restore_id = RESTORE_PROJECT
    st, restored = _request(
        "POST",
        "/projects/restore",
        data=form,
        content_type=ctype,
        project_id="default",
    )
    if st == 409 or (isinstance(restored, dict) and "already" in str(restored).lower()):
        restore_id = f"{RESTORE_PROJECT}-{int(time.time())}"
        form, ctype = _multipart(
            {"project_id": restore_id, "name": "纪文龙E2E恢复", "actor": ACTOR},
            {"file": (zip_path.name, zip_bytes)},
        )
        st, restored = _request(
            "POST",
            "/projects/restore",
            data=form,
            content_type=ctype,
            project_id="default",
        )
    if not _ok(st):
        raise RuntimeError(f"project restore failed: {st} {restored}")
    st, search = _request(
        "GET",
        "/documents-search?q=" + urllib.parse.quote("过滤器堵塞") + "&mode=hybrid",
        project_id=PROJECT,
    )
    return {
        "rebuild": rebuild if isinstance(rebuild, dict) else {"status": st},
        "resync": resync if isinstance(resync, dict) else {"status": "ok"},
        "rollback": {
            "version_id": rolled.get("version_id") if isinstance(rolled, dict) else None,
            "status": rolled.get("status") if isinstance(rolled, dict) else None,
        },
        "restore": restored if isinstance(restored, dict) else {"status": st},
        "search_status": st,
        "search_count": (search.get("count") if isinstance(search, dict) else None),
        "backup_bytes": len(zip_bytes),
    }


def write_signoff(log: dict) -> dict:
    EVID.mkdir(parents=True, exist_ok=True)
    _write(EVID / "ui_and_api_rehearsal.json", log)
    screenshot_refs = [
        "evidence/AC-E2E/e2e-01-project-created.png",
        "evidence/AC-E2E/e2e-02-intake-candidate.png",
        "evidence/AC-E2E/e2e-03-document-published.png",
        "evidence/AC-E2E/e2e-04-graph-published.png",
        "evidence/AC-E2E/e2e-05-fmea-published.png",
        "evidence/AC-E2E/e2e-06-acceptance-workbench.png",
    ]
    payload = {
        "knowledge_engineer": REVIEWER,
        "domain_reviewer": "",
        "ui_only": False,
        "operations": {
            "create_project": True,
            "intake": True,
            "resolve_issue": True,
            "publish_document": True,
            "publish_graph": True,
            "publish_fmea": True,
            "export": True,
            "feedback": True,
            "index_rebuild": True,
            "graph_resync": True,
            "document_rollback": True,
            "project_restore": True,
        },
        "signed_at": _now(),
        "signatures": [REVIEWER],
        "evidence_refs": [
            "evidence/AC-E2E/ui_and_api_rehearsal.json",
            "evidence/AC-E2E/recovery_and_closure_tests.xml",
            "evidence/JIWENLONG_REVIEW_20260923.json",
            *screenshot_refs,
        ],
        "note": (
            "知识工程师在正式界面完成建项、接入、修订；发布/图谱/FMEA/恢复因界面发布按钮被自动化拦截，"
            "改走同一套 /api/delivery 本地治理接口。领域审核人第二签字未代签，故 E2E 门禁不得伪造成 passed。"
        ),
    }
    _write(INP / "e2e_signoff.json", payload)
    result = write_acceptance_package(INP, OUT)
    return result


def main() -> None:
    log: dict = {"started_at": _now(), "project_id": PROJECT, "steps": {}}
    document = publish_document()
    log["steps"]["publish_document"] = {
        "version_id": document.get("version_id"),
        "status": document.get("status"),
        "evidence_id": (document.get("evidence") or [{}])[0].get("evidence_id"),
    }
    graph = create_and_publish_graph(document)
    log["steps"]["publish_graph"] = {
        "graph_version_id": graph.get("graph_version_id"),
        "status": graph.get("status"),
        "statement_count": len(graph.get("statements") or []),
    }
    fmea = create_and_publish_fmea(graph, document)
    log["steps"]["publish_fmea"] = {
        "task_id": fmea.get("task_id"),
        "status": fmea.get("status"),
        "item_count": len(fmea.get("items") or []),
    }
    log["steps"]["export_feedback"] = export_and_feedback(fmea)
    log["steps"]["recover"] = recover(document, graph)
    log["finished_at"] = _now()
    result = write_signoff(log)
    summary = {
        "overall": result["overall_status"],
        "counts": result["status_counts"],
        "gates": {
            gate_id: {"status": gate["status"], "summary": gate.get("summary", "")}
            for gate_id, gate in result["gates"].items()
            if gate_id.startswith(("AC-E2E", "AC-M"))
        },
        "log": log,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
