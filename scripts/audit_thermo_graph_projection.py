# -*- coding: utf-8 -*-
"""Demonstrate the governed graph projection being clobbered by the M2 graph-import path."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api_server" / "current_console" / "chroma_rag_poc" / "src"))
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from chroma_rag_poc.api import create_app  # noqa: E402

RUNTIME = ROOT / "build" / "thermo_wf_run_20260927"
OUT = ROOT / "evaluation" / "reports" / "thermo_graph_clobber_20260927.json"


def main() -> int:
    app = create_app(
        persist_dir=RUNTIME / "persist",
        upload_dir=RUNTIME / "uploads",
        log_dir=RUNTIME / "logs",
    )
    client = TestClient(app)
    out: dict = {}

    before = client.get("/api/delivery/graphs-active/status")
    out["before"] = {
        "status": before.status_code,
        "body": json.loads(before.text) if before.status_code == 200 else before.text[:300],
    }

    governed = client.get("/api/delivery/graphs")
    out["governed_graph_list"] = {
        "status": governed.status_code,
        "body": governed.text[:500],
    }

    # exactly what the M2 knowledge-organization page does: import a browser graph
    imp = client.post(
        "/api/graphrag/import",
        json={
            "nodes": [{"id": "x", "label": "测试节点A"}, {"id": "y", "label": "测试节点B"}],
            "links": [{"source": "x", "target": "y", "predicate": "RELATED_TO"}],
        },
    )
    out["import_default_path_reset_true"] = {"status": imp.status_code, "body": imp.text[:500]}

    after = client.get("/api/delivery/graphs-active/status")
    out["after"] = {
        "status": after.status_code,
        "body": json.loads(after.text) if after.status_code == 200 else after.text[:300],
    }

    detail = client.get("/api/delivery/graphs/graph:v1")
    out["governed_graph_version_after"] = {
        "status": detail.status_code,
        "statement_count_hint": (
            len((json.loads(detail.text).get("statements") or [])) if detail.status_code == 200 else None
        ),
        "body": detail.text[:400],
    }

    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2)[:4000])
    print(f"\nreport -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
