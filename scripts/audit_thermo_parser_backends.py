# -*- coding: utf-8 -*-
"""Probe parser-backend reporting and the human-annotation surface."""

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
RUNTIME = ROOT / "build" / "thermo_probe2_20260927"
OUT = ROOT / "evaluation" / "reports" / "thermo_probe2_20260927.json"


def main() -> int:
    RUNTIME.mkdir(parents=True, exist_ok=True)
    app = create_app(
        persist_dir=RUNTIME / "persist",
        upload_dir=RUNTIME / "uploads",
        log_dir=RUNTIME / "logs",
    )
    client = TestClient(app)
    sample = sorted(CORPUS.glob("*.pdf"))[0]
    blob = base64.b64encode(sample.read_bytes()).decode()
    out: dict = {"backends": {}, "annotation_surface": {}}

    for backend in ("native", "auto", "deepdoc", "docling", "mineru", "unstructured"):
        r = client.post(
            "/api/delivery/documents/intake",
            json={
                "document_id": f"bk-{backend}",
                "source_name": sample.name,
                "content_base64": blob,
                "chunk_size": 800,
                "overlap": 100,
                "parser_backend": backend,
                "use_ocr": "never",
            },
            timeout=600,
        )
        entry: dict = {"status": r.status_code}
        if r.status_code == 200:
            intake = r.json().get("intake") or {}
            entry["intake_status"] = intake.get("status")
            entry["warnings"] = intake.get("warnings")
            entry["processing_plan"] = intake.get("processing_plan")
            entry["quality_keys"] = sorted((intake.get("quality") or {}).keys())
            quality = intake.get("quality") or {}
            entry["parser_runtime"] = quality.get("parser_runtime") or quality.get("runtime")
            entry["profile_parser_route"] = (quality.get("profile") or {}).get("parser_route")
        else:
            entry["body"] = r.text[:400]
        out["backends"][backend] = entry

    # annotation surface: what endpoints mention annotation / labels
    spec = app.openapi()
    paths = sorted(spec.get("paths", {}))
    out["annotation_surface"]["paths_mentioning_annotation"] = [
        p for p in paths if "annot" in p.lower() or "label" in p.lower()
    ]
    out["annotation_surface"]["paths_mentioning_public_books"] = [
        p for p in paths if "public-books" in p or "public_books" in p
    ]
    routed = [p for p in paths if p.startswith("/api/delivery")]
    out["annotation_surface"]["delivery_paths"] = routed

    # extra keys beyond the documented contract?
    one = client.post(
        "/api/delivery/documents/intake",
        json={
            "document_id": "keys-check",
            "source_name": sample.name,
            "content_base64": blob,
            "chunk_size": 800,
            "overlap": 100,
            "use_ocr": "never",
        },
        timeout=600,
    )
    if one.status_code == 200:
        out["intake_response_keys"] = sorted(one.json().keys())

    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out["backends"], ensure_ascii=False, indent=2))
    print("\nintake_response_keys:", out.get("intake_response_keys"))
    print("annotation paths:", out["annotation_surface"]["paths_mentioning_annotation"])
    print("public-books paths:", out["annotation_surface"]["paths_mentioning_public_books"])
    print("delivery path count:", len(out["annotation_surface"]["delivery_paths"]))
    print(f"\nreport -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
