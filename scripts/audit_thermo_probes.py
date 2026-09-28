# -*- coding: utf-8 -*-
"""Targeted probes: page locator loss, parser/OCR backends, human edit paths."""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api_server" / "current_console" / "chroma_rag_poc" / "src"))
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from chroma_rag_poc.api import create_app  # noqa: E402

CORPUS = ROOT / "data_pipeline" / "raw" / "tsinghua_thermo_literature_20260927"
RUNTIME = ROOT / "build" / "thermo_probe_20260927"
OUT = ROOT / "evaluation" / "reports" / "thermo_probe_20260927.json"


def main() -> int:
    RUNTIME.mkdir(parents=True, exist_ok=True)
    app = create_app(
        persist_dir=RUNTIME / "persist",
        upload_dir=RUNTIME / "uploads",
        log_dir=RUNTIME / "logs",
    )
    client = TestClient(app)
    out: dict = {}
    pdfs = sorted(CORPUS.glob("*.pdf"))
    sample = pdfs[0]

    def intake(name: str, **kwargs):
        payload = {
            "document_id": name,
            "source_name": sample.name,
            "content_base64": base64.b64encode(sample.read_bytes()).decode(),
            "chunk_size": 800,
            "overlap": 100,
        }
        payload.update(kwargs)
        return client.post("/api/delivery/documents/intake", json=payload, timeout=600)

    # 1. page loss: does intake extract pages, and does the store keep them?
    r = intake("probe-page")
    if r.status_code == 200:
        body = r.json()
        intake_info = body.get("intake") or {}
        diag = (intake_info.get("page_diagnostics") or [])[:2]
        preview = (intake_info.get("chunk_preview") or [])[:2]
        version_id = (body.get("document_version") or {}).get("version_id")
        out["page_probe"] = {
            "status": r.status_code,
            "intake_status": intake_info.get("status"),
            "intake_keys": sorted(intake_info.keys()),
            "page_diagnostics_sample": diag,
            "chunk_preview_sample": preview,
            "version_id": version_id,
        }
        if version_id:
            doc = client.get(f"/api/delivery/documents/{version_id}")
            if doc.status_code == 200:
                detail = doc.json()
                evidence = detail.get("evidence") or []
                out["page_probe"]["stored_evidence_sample"] = evidence[:2]
                out["page_probe"]["stored_with_page"] = sum(
                    1 for e in evidence if e.get("page")
                )
                out["page_probe"]["stored_total"] = len(evidence)
    else:
        out["page_probe"] = {"status": r.status_code, "body": r.text[:400]}

    # 2. optional parser backends
    out["parser_backends"] = {}
    for backend in ("docling", "mineru", "unstructured", "auto"):
        rr = intake(f"probe-{backend}", parser_backend=backend, use_ocr="never")
        out["parser_backends"][backend] = {
            "status": rr.status_code,
            "body": rr.text[:300],
        }

    # 3. default OCR behaviour without a configured provider
    rr = intake("probe-ocr-auto", use_ocr="auto", auto_run_ocr=True)
    detail = {"status": rr.status_code}
    if rr.status_code == 200:
        payload = rr.json()
        detail["intake_status"] = (payload.get("intake") or {}).get("status")
        detail["ocr_job"] = payload.get("ocr_job")
        detail["profile"] = (payload.get("intake") or {}).get("profile")
    else:
        detail["body"] = rr.text[:400]
    out["ocr_auto"] = detail

    # 4. human-authored statements into the governed graph
    published = (r.json().get("document_version") or {}).get("version_id")
    if published:
        client.post(
            f"/api/delivery/documents/{published}/review",
            json={"reviewer": "expert", "decision": "approve"},
        )
        client.post(f"/api/delivery/documents/{published}/publish", json={"actor": "expert"})
        cand = client.post(
            "/api/delivery/graphs/candidates",
            json={
                "source_document_version_ids": [published],
                "statements": [
                    {
                        "subject": "有机朗肯循环",
                        "predicate": "HAS_FAILURE_MODE",
                        "object": "工质泄漏",
                        "subject_type": "SYSTEM",
                        "object_type": "FAILURE_MODE",
                        "evidence_ids": ["EV-placeholder"],
                        "confidence": 0.9,
                    }
                ],
            },
        )
        out["human_statements"] = {"status": cand.status_code, "body": cand.text[:500]}

        # 5. runtime graph edit path
        imp = client.post(
            "/api/graphrag/import",
            json={
                "graph_db_path": str(RUNTIME / "persist" / "graph_store.sqlite"),
                "nodes": [{"id": "a", "label": "有机朗肯循环"}, {"id": "b", "label": "工质泄漏"}],
                "links": [
                    {"source": "a", "target": "b", "predicate": "HAS_FAILURE_MODE"},
                ],
                "reset": True,
            },
        )
        out["runtime_graph_import"] = {"status": imp.status_code, "body": imp.text[:400]}
        active = client.get("/api/delivery/graphs-active/status")
        out["governed_graph_after_runtime_edit"] = {
            "status": active.status_code,
            "body": active.text[:400],
        }

    # 6. annotation / metadata ingestion path
    ingest = client.post(
        "/api/public-books-json/ingest",
        json={"input_dir": str(CORPUS), "collection": "probe_annotations"},
        timeout=300,
    )
    out["public_books_ingest_on_this_corpus"] = {
        "status": ingest.status_code,
        "body": ingest.text[:600],
    }

    # 7. annotation support inside the M2 layer
    annotate = client.get("/api/delivery/identity")
    out["identity"] = {"status": annotate.status_code, "body": annotate.text[:200]}

    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2)[:6000])
    print(f"\nreport -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
