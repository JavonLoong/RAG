from __future__ import annotations

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


def build_app(temp_root: Path) -> TestClient:
    persist_dir = temp_root / "chroma"
    upload_dir = temp_root / "uploads"
    log_dir = temp_root / "logs"
    for path in (persist_dir, upload_dir, log_dir):
        path.mkdir(parents=True, exist_ok=True)
    app = create_app(
        persist_dir=persist_dir,
        upload_dir=upload_dir,
        log_dir=log_dir,
        frontend_dir=temp_root / "missing-frontend",
    )
    return TestClient(app)


def run_smoke_checks() -> list[SmokeCheck]:
    checks: list[SmokeCheck] = []
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
            checks.append(
                check(
                    index.status_code == 404 and "message" in index.json(),
                    "missing frontend fallback",
                    f"GET / -> {index.status_code}",
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
    finally:
        shutil.rmtree(outside_root, ignore_errors=True)
    return checks


def write_reports(checks: list[SmokeCheck]) -> dict[str, Any]:
    passed = sum(1 for item in checks if item.passed)
    payload = {
        "report_type": "challenge_cup_live_demo_smoke",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "status": "pass" if passed == len(checks) else "fail",
        "passed": passed,
        "total": len(checks),
        "checks": [item.to_dict() for item in checks],
        "boundary": "This smoke test verifies local API readiness and route guards; it does not replace browser or production-load verification.",
    }
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Live Demo Smoke Report",
        "",
        f"- Status: `{payload['status']}`",
        f"- Passed: {passed}/{len(checks)}",
        "- Scope: local FastAPI app factory, health route, CORS, search guard, GraphRAG path guard",
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
            "## Boundary",
            "",
            str(payload["boundary"]),
        ]
    )
    REPORT_MD.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return payload


def main() -> int:
    checks = run_smoke_checks()
    payload = write_reports(checks)
    print(f"Wrote {REPORT_MD.relative_to(REPO_ROOT)}")
    print(f"Status: {payload['status']} ({payload['passed']}/{payload['total']} checks)")
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
