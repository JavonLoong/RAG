# -*- coding: utf-8 -*-
"""Run stages 1-2 of the governed workflow over the 2026-09-27 Tsinghua literature set."""

from __future__ import annotations

import base64
import json
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api_server" / "current_console" / "chroma_rag_poc" / "src"))
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from chroma_rag_poc.api import create_app  # noqa: E402

CORPUS = ROOT / "data_pipeline" / "raw" / "tsinghua_thermo_literature_20260927"
RUNTIME = ROOT / "build" / "thermo_wf_run_20260927"
OUT = ROOT / "evaluation" / "reports" / "thermo_wf_run_20260927.json"

PDFS = sorted(p for p in CORPUS.glob("*.pdf"))
print(f"corpus: {len(PDFS)} pdf")


def summarize_intake(payload: dict) -> dict:
    version = payload.get("document_version") or {}
    intake = payload.get("intake") or {}
    blocks = intake.get("blocks") or []
    issues = intake.get("quality_issues") or []
    pages = intake.get("page_count")
    return {
        "status": intake.get("status"),
        "page_count": pages,
        "block_count": len(blocks),
        "quality_issue_count": len(issues),
        "quality_issue_codes": sorted({str(i.get("code")) for i in issues if isinstance(i, dict)}),
        "requires_ocr": (intake.get("profile") or {}).get("requires_ocr"),
        "chunk_count": len(version.get("chunks") or []) or version.get("chunk_count"),
        "version_id": version.get("version_id"),
        "ocr_job": (payload.get("ocr_job") or {}).get("status"),
    }


def main() -> int:
    RUNTIME.mkdir(parents=True, exist_ok=True)
    app = create_app(
        persist_dir=RUNTIME / "persist",
        upload_dir=RUNTIME / "uploads",
        log_dir=RUNTIME / "logs",
    )
    client = TestClient(app)
    report: dict = {"corpus": str(CORPUS), "file_count": len(PDFS), "files": [], "stages": {}}

    project_id = "thermo-literature-20260927"
    created = client.post(
        "/api/delivery/projects",
        json={"project_id": project_id, "name": "热力系统文献 2026-09-27", "domain": "gas_turbine"},
    )
    report["stages"]["create_project"] = {"status": created.status_code, "body": created.text[:400]}

    published: list[str] = []
    for index, pdf in enumerate(PDFS, start=1):
        entry: dict = {"file": pdf.name, "bytes": pdf.stat().st_size}
        started = time.perf_counter()
        try:
            response = client.post(
                "/api/delivery/documents/intake",
                json={
                    "document_id": f"lit-{index:03d}",
                    "source_name": pdf.name,
                    "content_base64": base64.b64encode(pdf.read_bytes()).decode(),
                    "chunk_size": 800,
                    "overlap": 100,
                    "parser_backend": "native",
                    "use_ocr": "never",
                    "auto_run_ocr": False,
                    "metadata": {"project_id": project_id, "source": "tsinghua_cloud_20260927"},
                },
                timeout=600,
            )
            entry["intake_status"] = response.status_code
            if response.status_code == 200:
                payload = response.json()
                entry.update(summarize_intake(payload))
                version_id = (payload.get("document_version") or {}).get("version_id")
                if version_id:
                    entry["review"] = client.post(
                        f"/api/delivery/documents/{version_id}/review",
                        json={"reviewer": "domain-expert", "decision": "approve", "comment": "自动跑批"},
                    ).status_code
                    publish = client.post(
                        f"/api/delivery/documents/{version_id}/publish",
                        json={"actor": "domain-expert", "comment": "自动跑批"},
                    )
                    entry["publish"] = publish.status_code
                    if publish.status_code == 200:
                        published.append(version_id)
            else:
                entry["error"] = response.text[:600]
        except Exception as exc:  # noqa: BLE001
            entry["exception"] = f"{type(exc).__name__}: {exc}"
            entry["traceback"] = traceback.format_exc()[-1200:]
        entry["seconds"] = round(time.perf_counter() - started, 2)
        report["files"].append(entry)
        print(f"[{index}/{len(PDFS)}] {entry.get('intake_status')} {pdf.name[:60]} "
              f"pages={entry.get('page_count')} blocks={entry.get('block_count')} "
              f"issues={entry.get('quality_issue_count')} {entry['seconds']}s")

    report["published_version_ids"] = published
    report["stages"]["published_count"] = len(published)

    # --- stage 2: governed graph extraction (rules) over published material ---
    if published:
        started = time.perf_counter()
        extract = client.post(
            "/api/delivery/graphs/extract",
            json={
                "source_document_version_ids": published,
                "backend": "rules",
                "metadata": {"project_id": project_id},
            },
            timeout=900,
        )
        report["stages"]["graphs_extract"] = {
            "status": extract.status_code,
            "seconds": round(time.perf_counter() - started, 2),
        }
        if extract.status_code == 200:
            graph = extract.json()
            statements = graph.get("statements") or []
            report["stages"]["graphs_extract"].update(
                {
                    "graph_version_id": graph.get("graph_version_id"),
                    "statement_count": len(statements),
                    "predicates": sorted({str(s.get("predicate")) for s in statements}),
                    "source_documents_used": len(graph.get("source_document_version_ids") or []),
                    "extraction": graph.get("extraction"),
                    "per_source": {},
                }
            )
            counts: dict[str, int] = {}
            for item in statements:
                for doc in item.get("metadata", {}).get("source_document_version_ids") or []:
                    counts[doc] = counts.get(doc, 0) + 1
            report["stages"]["graphs_extract"]["per_source"] = counts

            gid = graph.get("graph_version_id")
            report["stages"]["graph_review"] = client.post(
                f"/api/delivery/graphs/{gid}/review",
                json={"reviewer": "graph-expert", "decision": "approve"},
            ).status_code
            publish_graph = client.post(f"/api/delivery/graphs/{gid}/publish", json={"actor": "graph-expert"})
            report["stages"]["graph_publish"] = {
                "status": publish_graph.status_code,
                "body": publish_graph.text[:300],
            }
            resync = client.post(f"/api/delivery/graphs/{gid}/resync")
            report["stages"]["graph_resync"] = {"status": resync.status_code, "body": resync.text[:300]}
            active = client.get("/api/delivery/graphs-active/status")
            report["stages"]["graphs_active"] = {"status": active.status_code, "body": active.text[:400]}
            query = client.post(
                f"/api/delivery/graphs/{gid}/query",
                json={"question": "有机朗肯循环的工质选择依据是什么"},
            )
            report["stages"]["graph_query"] = {"status": query.status_code, "body": query.text[:800]}
        else:
            report["stages"]["graphs_extract"]["error"] = extract.text[:800]

    # --- retrieval projection (needs chromadb) ---
    try:
        rebuild = client.post("/api/delivery/documents-index/rebuild")
        report["stages"]["index_rebuild"] = {"status": rebuild.status_code, "body": rebuild.text[:800]}
    except Exception as exc:  # noqa: BLE001
        report["stages"]["index_rebuild"] = {"exception": f"{type(exc).__name__}: {exc}"}
    try:
        status = client.get("/api/delivery/documents-index/status")
        report["stages"]["index_status"] = {"status": status.status_code, "body": status.text[:400]}
    except Exception as exc:  # noqa: BLE001
        report["stages"]["index_status"] = {"exception": f"{type(exc).__name__}: {exc}"}
    try:
        search = client.get("/api/delivery/documents-search", params={"q": "有机朗肯循环", "mode": "hybrid"})
        report["stages"]["documents_search"] = {"status": search.status_code, "body": search.text[:500]}
    except Exception as exc:  # noqa: BLE001
        report["stages"]["documents_search"] = {"exception": f"{type(exc).__name__}: {exc}"}

    # --- FMEA over the published graph ---
    graphs = report["stages"].get("graphs_extract", {})
    gid = graphs.get("graph_version_id")
    if gid and graphs.get("statement_count"):
        task = client.post(
            "/api/delivery/fmea/tasks",
            json={
                "requested_by": "reviewer",
                "graph_version_id": gid,
                "document_version_ids": published,
                "template": "gas_turbine_minimum_v1",
            },
            timeout=600,
        )
        report["stages"]["fmea_task"] = {"status": task.status_code, "body": task.text[:600]}
        if task.status_code == 200:
            body = task.json()
            task_id = body.get("task_id") or (body.get("task") or {}).get("task_id")
            items = body.get("items") or []
            report["stages"]["fmea_task"].update({"task_id": task_id, "item_count": len(items)})
            if task_id:
                report["stages"]["fmea_review"] = client.post(
                    f"/api/delivery/fmea/tasks/{task_id}/review",
                    json={"reviewer": "fmea-expert", "decision": "approve"},
                ).status_code
                pub = client.post(f"/api/delivery/fmea/tasks/{task_id}/publish", json={"actor": "fmea-expert"})
                report["stages"]["fmea_publish"] = {"status": pub.status_code, "body": pub.text[:300]}
                for fmt in ("json", "csv", "docx"):
                    exp = client.get(f"/api/delivery/fmea/tasks/{task_id}/export", params={"format": fmt})
                    report["stages"][f"fmea_export_{fmt}"] = {
                        "status": exp.status_code,
                        "bytes": len(exp.content),
                    }

    # --- interactive graph edit path (runtime store) ---
    imp = client.post(
        "/api/graphrag/import",
        json={
            "graph_db_path": str(RUNTIME / "persist" / "graph_store.sqlite3"),
            "nodes": [{"id": "a", "label": "润滑油系统"}, {"id": "b", "label": "过滤器堵塞"}],
            "links": [{"source": "a", "target": "b", "label": "HAS_FAILURE_MODE"}],
            "reset": True,
        },
    )
    report["stages"]["graphrag_import"] = {"status": imp.status_code, "body": imp.text[:300]}

    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    ok = sum(1 for f in report["files"] if f.get("intake_status") == 200)
    print(f"\nINTAKE OK {ok}/{len(PDFS)}  published {len(published)}")
    print(f"report -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
