from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
API_SRC = REPO_ROOT / "api_server" / "current_console" / "chroma_rag_poc" / "src"
REPORT_DIR = REPO_ROOT / "docs" / "challenge_cup" / "reproducibility"
REPORT_JSON = REPORT_DIR / "live_demo_smoke_report.json"
REPORT_MD = REPORT_DIR / "live_demo_smoke_report.md"
DEMO_FRONTEND_DIR = REPO_ROOT / "frontend_app" / "current_console"
LIVE_RETRIEVAL_COLLECTION = "challenge_cup_live_retrieval_smoke"
LIVE_RETRIEVAL_QUERY = "GT-07 abnormal vibration compressor outlet temperature repair"
LIVE_RETRIEVAL_SOURCE = "gt07-live-smoke.json"
LIVE_RETRIEVAL_RECORDS = [
    {
        "id": "live-gt07-threshold",
        "title": "GT-07 threshold evidence",
        "content": (
            "GT-07 compressor outlet temperature and vibration review starts from operating thresholds. "
            "The live retrieval smoke record keeps the threshold evidence separate from public-demo frontend data."
        ),
    },
    {
        "id": "live-gt07-fault",
        "title": "GT-07 abnormal vibration evidence",
        "content": (
            "GT-07 reached 75 percent load, compressor outlet temperature increased, and vibration sensor "
            "VIB-CMP-01 reported abnormal vibration. Operators recorded a stable flame and no obvious combustion swing."
        ),
    },
    {
        "id": "live-gt07-repair",
        "title": "GT-07 repair evidence",
        "content": (
            "The repair path checked inlet filter pressure drop, cleaned compressor blades, reset TT-COMP-02, "
            "and confirmed vibration dropped after restart. This record is returned by a live Chroma search."
        ),
    },
]
EXPECTED_LIVE_RECORD_IDS = {str(item["id"]) for item in LIVE_RETRIEVAL_RECORDS}

if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from chroma_rag_poc.api import create_app  # noqa: E402


@dataclass(slots=True)
class SmokeCheck:
    name: str
    passed: bool
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


def check(condition: bool, name: str, detail: str) -> SmokeCheck:
    return SmokeCheck(name=name, passed=bool(condition), detail=detail)


def build_app(temp_root: Path, frontend_dir: Path = DEMO_FRONTEND_DIR) -> TestClient:
    persist_dir = temp_root / "chroma"
    upload_dir = temp_root / "uploads"
    log_dir = temp_root / "logs"
    for path in (persist_dir, upload_dir, log_dir):
        path.mkdir(parents=True, exist_ok=True)
    app = create_app(
        persist_dir=persist_dir,
        upload_dir=upload_dir,
        log_dir=log_dir,
        frontend_dir=frontend_dir,
    )
    return TestClient(app)


def live_record_id(raw_record_id: Any) -> str:
    text = str(raw_record_id or "")
    marker = "::item-"
    return text.split(marker, 1)[1] if marker in text else text


def run_live_retrieval_checks(client: TestClient) -> tuple[list[SmokeCheck], dict[str, Any]]:
    source_bytes = json.dumps(LIVE_RETRIEVAL_RECORDS, ensure_ascii=False).encode("utf-8")
    ingest = client.post(
        "/api/ingest",
        data={
            "collection": LIVE_RETRIEVAL_COLLECTION,
            "chunk_size": "1000",
            "overlap": "0",
            "backend": "hashing",
            "model_name": "challenge-cup-live-smoke-hashing",
        },
        files=[("files", (LIVE_RETRIEVAL_SOURCE, source_bytes, "application/json"))],
    )
    ingest_payload = ingest.json() if ingest.headers.get("content-type", "").startswith("application/json") else {}

    stats = client.get("/api/stats", params={"collection": LIVE_RETRIEVAL_COLLECTION})
    stats_payload = stats.json() if stats.headers.get("content-type", "").startswith("application/json") else {}

    search = client.post(
        "/api/search",
        json={
            "collection": LIVE_RETRIEVAL_COLLECTION,
            "query": LIVE_RETRIEVAL_QUERY,
            "top_k": 3,
        },
    )
    search_payload = search.json() if search.headers.get("content-type", "").startswith("application/json") else {}
    results = search_payload.get("results") if isinstance(search_payload, dict) else []
    results = results if isinstance(results, list) else []
    raw_record_ids = [
        str((item.get("metadata") or {}).get("record_id"))
        for item in results
        if isinstance(item, dict)
    ]
    record_ids = [live_record_id(record_id) for record_id in raw_record_ids]
    observed_ids = set(record_ids)
    not_public_demo = (
        search_payload.get("collection") == LIVE_RETRIEVAL_COLLECTION
        and LIVE_RETRIEVAL_COLLECTION != "gas_turbine_ocr_demo_snapshot"
        and all(LIVE_RETRIEVAL_SOURCE in record_id for record_id in raw_record_ids)
    )

    checks = [
        check(
            ingest.status_code == 200
            and ingest_payload.get("collection") == LIVE_RETRIEVAL_COLLECTION
            and int(ingest_payload.get("chunks_written") or 0) >= len(LIVE_RETRIEVAL_RECORDS)
            and ingest_payload.get("embedding_backend") == "hashing",
            "live retrieval ingest",
            (
                f"POST /api/ingest -> {ingest.status_code}; "
                f"collection={ingest_payload.get('collection')}; "
                f"chunks={ingest_payload.get('chunks_written')}; "
                f"backend={ingest_payload.get('embedding_backend')}"
            ),
        ),
        check(
            stats.status_code == 200
            and stats_payload.get("collection") == LIVE_RETRIEVAL_COLLECTION
            and int(stats_payload.get("chunk_count") or 0) >= len(LIVE_RETRIEVAL_RECORDS),
            "live retrieval stats",
            (
                f"GET /api/stats -> {stats.status_code}; "
                f"collection={stats_payload.get('collection')}; "
                f"chunks={stats_payload.get('chunk_count')}"
            ),
        ),
        check(
            search.status_code == 200
            and len(results) == 3
            and EXPECTED_LIVE_RECORD_IDS <= observed_ids
            and not_public_demo,
            "live retrieval search",
            (
                f"POST /api/search -> {search.status_code}; "
                f"results={len(results)}; ids={', '.join(record_ids)}; not public-demo={not_public_demo}"
            ),
        ),
    ]
    retrieval = {
        "collection": LIVE_RETRIEVAL_COLLECTION,
        "query": LIVE_RETRIEVAL_QUERY,
        "backend": ingest_payload.get("embedding_backend"),
        "model": ingest_payload.get("embedding_model"),
        "not_public_demo": not_public_demo,
        "ingest": {
            "status_code": ingest.status_code,
            "chunks_written": ingest_payload.get("chunks_written"),
            "records_processed": ingest_payload.get("records_processed"),
            "files_succeeded": ingest_payload.get("files_succeeded"),
        },
        "stats": {
            "status_code": stats.status_code,
            "collection": stats_payload.get("collection"),
            "chunk_count": stats_payload.get("chunk_count"),
            "record_count": stats_payload.get("record_count"),
            "source_file_count": stats_payload.get("source_file_count"),
            "embedding_backend": stats_payload.get("embedding_backend"),
            "persist_dir_storage_mb": stats_payload.get("persist_dir_storage_mb"),
        },
        "result_count": len(results),
        "record_ids": record_ids,
        "raw_record_ids": raw_record_ids,
        "scores": [item.get("score") for item in results if isinstance(item, dict)],
        "boundary": (
            "This retrieval evidence is produced from a temporary Chroma collection through /api/ingest, "
            "/api/stats, and /api/search. It proves the live API retrieval path works, while the browser "
            "public-demo snapshot remains only an offline presentation fallback."
        ),
    }
    return checks, retrieval


def run_smoke_checks() -> tuple[list[SmokeCheck], dict[str, Any]]:
    checks: list[SmokeCheck] = []
    retrieval: dict[str, Any] = {}
    outside_root = Path(tempfile.mkdtemp(prefix="challenge-cup-outside-"))
    try:
        with tempfile.TemporaryDirectory(prefix="challenge-cup-demo-") as temp_name:
            client = build_app(Path(temp_name))

            health = client.get("/api/health")
            checks.append(
                check(
                    health.status_code == 200 and health.json().get("status") == "ok",
                    "health endpoint",
                    f"GET /api/health -> {health.status_code}",
                )
            )

            index = client.get("/")
            index_content_type = index.headers.get("content-type", "")
            checks.append(
                check(
                    index.status_code == 200
                    and "text/html" in index_content_type
                    and index.text.lstrip().lower().startswith("<!doctype html"),
                    "frontend root page",
                    f"GET / -> {index.status_code}; frontend={display_path(DEMO_FRONTEND_DIR)}",
                )
            )

            allowed_cors = client.options(
                "/api/health",
                headers={
                    "Origin": "http://localhost:8000",
                    "Access-Control-Request-Method": "GET",
                },
            )
            rejected_cors = client.options(
                "/api/health",
                headers={
                    "Origin": "https://evil.example",
                    "Access-Control-Request-Method": "GET",
                },
            )
            checks.append(
                check(
                    allowed_cors.headers.get("access-control-allow-origin") == "http://localhost:8000"
                    and rejected_cors.headers.get("access-control-allow-origin") is None,
                    "trusted cors origin",
                    "localhost origin accepted; arbitrary origin rejected",
                )
            )

            top_k = client.get("/api/search", params={"q": "状态监测", "top_k": 999})
            checks.append(
                check(
                    top_k.status_code == 400 and "top_k" in str(top_k.json().get("detail", "")),
                    "search top_k guard",
                    f"GET /api/search?top_k=999 -> {top_k.status_code}",
                )
            )

            outside_graph = outside_root / "outside_graph.sqlite"
            outside_graph.write_bytes(b"")
            graph = client.post("/api/graphrag/stats", json={"graph_db_path": str(outside_graph)})
            checks.append(
                check(
                    graph.status_code == 400 and "Graph database path" in str(graph.json().get("detail", "")),
                    "graphrag path guard",
                    f"POST /api/graphrag/stats outside runtime root -> {graph.status_code}",
                )
            )

            retrieval_checks, retrieval = run_live_retrieval_checks(client)
            checks.extend(retrieval_checks)
    finally:
        shutil.rmtree(outside_root, ignore_errors=True)
    return checks, retrieval


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def write_reports(
    checks: list[SmokeCheck],
    retrieval: dict[str, Any],
    report_dir: Path = REPORT_DIR,
) -> dict[str, Any]:
    passed = sum(1 for item in checks if item.passed)
    report_json = report_dir / "live_demo_smoke_report.json"
    report_md = report_dir / "live_demo_smoke_report.md"
    payload = {
        "report_type": "challenge_cup_live_demo_smoke",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "status": "pass" if passed == len(checks) else "fail",
        "passed": passed,
        "total": len(checks),
        "checks": [item.to_dict() for item in checks],
        "retrieval": retrieval,
        "boundary": "This smoke test verifies local API readiness, project frontend serving, route guards, and a temporary live Chroma retrieval path; it does not replace browser or production-load verification.",
    }
    report_dir.mkdir(parents=True, exist_ok=True)
    report_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Live Demo Smoke Report",
        "",
        f"- Status: `{payload['status']}`",
        f"- Passed: {passed}/{len(checks)}",
        "- Scope: local FastAPI app factory, project frontend root page, health route, CORS, search guard, GraphRAG path guard, temporary Chroma ingest/stats/search",
        "",
        "| Check | Result | Detail |",
        "| --- | --- | --- |",
    ]
    for item in checks:
        result = "pass" if item.passed else "fail"
        lines.append(f"| {item.name} | {result} | {item.detail.replace('|', '/')} |")
    lines.extend(
        [
            "",
            "## Live Retrieval Evidence",
            "",
            f"- Collection: `{retrieval.get('collection')}`",
            f"- Backend: `{retrieval.get('backend')}`",
            f"- Query: `{retrieval.get('query')}`",
            f"- Result count: `{retrieval.get('result_count')}`",
            f"- Record ids: `{', '.join(str(item) for item in retrieval.get('record_ids', []))}`",
            f"- Backend boundary: not public-demo=`{retrieval.get('not_public_demo')}`",
            f"- Stats chunks: `{(retrieval.get('stats') or {}).get('chunk_count')}`",
            "",
            str(retrieval.get("boundary", "")),
        ]
    )
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            str(payload["boundary"]),
        ]
    )
    report_md.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return payload


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Challenge Cup live demo smoke checks.")
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=REPORT_DIR,
        help="Directory for live_demo_smoke_report.{json,md}; defaults to the committed reproducibility directory.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    checks, retrieval = run_smoke_checks()
    payload = write_reports(checks, retrieval, args.report_dir)
    print(f"Wrote {display_path(args.report_dir / 'live_demo_smoke_report.md')}")
    print(f"Status: {payload['status']} ({payload['passed']}/{payload['total']} checks)")
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
