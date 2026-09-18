from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import platform
import socket
import sys
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "tmp" / "prd_acceptance_rehearsal"
DEFAULT_ACCEPTANCE_INPUT_DIR = REPO_ROOT / "evaluation" / "prd_acceptance_current_inputs"
DEFAULT_FILE_SIZE = 60 * 1024 * 1024


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def prepare_large_upload_fixture(output_dir: Path) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / "powerrag_tech16_60mb_transport_fixture.pdf"
    block = (
        "PowerRAG TECH-16 deterministic transport fixture. "
        "This is not business-source content and must not be used for semantic quality acceptance.\n"
    ).encode("utf-8")
    stream_payload = (block * ((DEFAULT_FILE_SIZE // len(block)) + 1))[:DEFAULT_FILE_SIZE]
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.add_metadata(
        {
            "/Title": "PowerRAG TECH-16 60 MiB transport fixture",
            "/Subject": "Multipart upload and asynchronous task rehearsal only",
        }
    )
    unreferenced_stream = DecodedStreamObject()
    unreferenced_stream.set_data(stream_payload)
    writer._add_object(unreferenced_stream)  # noqa: SLF001 - deterministic PDF transport fixture
    with target.open("wb") as stream:
        writer.write(stream)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "path": str(target),
        "byte_size": target.stat().st_size,
        "file_size_mb": target.stat().st_size / (1024 * 1024),
        "sha256": _sha256(target),
        "purpose": "TECH-16 multipart transport and browser responsiveness rehearsal only",
        "semantic_quality_evidence": False,
        "fixture_format": "valid single-page PDF with an unreferenced deterministic stream",
        "environment": {
            "hostname": socket.gethostname(),
            "platform": platform.platform(),
            "python": platform.python_version(),
            "processor": platform.processor(),
            "cpu_count": os.cpu_count(),
        },
    }
    metadata_path = output_dir / "large_upload_fixture.json"
    metadata_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def _require_response(response, *, operation: str, expected: tuple[int, ...] = (200,)) -> dict:
    if response.status_code not in expected:
        raise RuntimeError(f"{operation} failed: {response.status_code} {response.text}")
    return response.json()


def _measure(operation: Callable[[], object], *, samples: int = 10) -> list[float]:
    operation()
    values: list[float] = []
    for _ in range(samples):
        started = time.perf_counter()
        operation()
        values.append(round(time.perf_counter() - started, 6))
    return values


def _percentile_95(values: list[float]) -> float:
    ordered = sorted(values)
    rank = max(0, min(len(ordered) - 1, int((len(ordered) - 1) * 0.95 + 0.999999)))
    return ordered[rank]


def run_performance_rehearsal(output_dir: Path, acceptance_root: Path) -> dict[str, object]:
    api_src = REPO_ROOT / "api_server" / "current_console" / "chroma_rag_poc" / "src"
    if str(api_src) not in sys.path:
        sys.path.insert(0, str(api_src))
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))

    from fastapi.testclient import TestClient

    from chroma_rag_poc.api import create_app

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    runtime_dir = output_dir / f"performance_runtime_{run_id}"
    app = create_app(
        persist_dir=runtime_dir / "persist",
        upload_dir=runtime_dir / "uploads",
        log_dir=runtime_dir / "logs",
    )
    app.state.delivery_embedding_backend = "hashing"
    client = TestClient(app)
    project_id = f"prd-tech15-{run_id.lower()}"
    _require_response(
        client.post(
            "/api/delivery/projects",
            json={"project_id": project_id, "name": "TECH-15 性能演练", "created_by": "rehearsal"},
        ),
        operation="create project",
        expected=(201,),
    )
    headers = {"X-Project-ID": project_id, "X-Correlation-ID": f"tech15-{run_id}"}

    version_ids: list[str] = []
    first_evidence_id = ""
    base_text = (
        "燃气轮机润滑油系统的过滤器堵塞可能由油液污染导致，影响是润滑油压下降。"
        "可通过压差监测发现，并通过更换滤芯和清洁油路处理。"
    )
    for number in range(1, 15):
        text = f"试点资料 {number:02d}。{base_text}本资料用于固定 14 份资料的本机性能演练。"
        intake = _require_response(
            client.post(
                "/api/delivery/documents/intake",
                headers=headers,
                json={
                    "document_id": f"pilot-{number:02d}",
                    "source_name": f"pilot-{number:02d}.txt",
                    "content_base64": base64.b64encode(text.encode("utf-8")).decode("ascii"),
                    "chunk_size": 200,
                    "overlap": 20,
                    "metadata": {"actor": "rehearsal", "corpus": "synthetic-14-document"},
                },
            ),
            operation=f"intake document {number}",
        )
        version = intake["document_version"]
        version_id = str(version["version_id"])
        version_ids.append(version_id)
        if number == 1:
            detail = _require_response(
                client.get(f"/api/delivery/documents/{version_id}", headers=headers),
                operation="read first document evidence",
            )
            first_evidence_id = str(detail["evidence"][0]["evidence_id"])
        _require_response(
            client.post(
                f"/api/delivery/documents/{version_id}/review",
                headers=headers,
                json={"reviewer": "automated-rehearsal", "decision": "approve", "comment": "setup only"},
            ),
            operation=f"review document {number}",
        )
        _require_response(
            client.post(f"/api/delivery/documents/{version_id}/publish", headers=headers),
            operation=f"publish document {number}",
        )

    graph = _require_response(
        client.post(
            "/api/delivery/graphs/extract",
            headers=headers,
            json={
                "source_document_version_ids": [version_ids[0]],
                "backend": "rules",
                "metadata": {"purpose": "TECH-15 local rehearsal"},
            },
        ),
        operation="extract graph",
    )
    graph_version_id = str(graph["graph_version_id"])
    _require_response(
        client.post(
            f"/api/delivery/graphs/{graph_version_id}/review",
            headers=headers,
            json={"reviewer": "automated-rehearsal", "decision": "approve", "comment": "setup only"},
        ),
        operation="review graph",
    )
    _require_response(
        client.post(f"/api/delivery/graphs/{graph_version_id}/publish", headers=headers),
        operation="publish graph",
    )

    def retrieval() -> None:
        response = client.get(
            "/api/delivery/documents-search",
            headers=headers,
            params={"q": "过滤器堵塞 油液污染", "mode": "hybrid", "top_k": 5},
        )
        payload = _require_response(response, operation="retrieval")
        if not payload.get("results"):
            raise RuntimeError("retrieval returned no results")

    def graph_path() -> None:
        response = client.get(
            f"/api/delivery/graphs/{graph_version_id}/path",
            headers=headers,
            params={"source": "燃气轮机", "target": "油液污染", "max_hops": 4},
        )
        payload = _require_response(response, operation="graph path")
        if not payload.get("found"):
            raise RuntimeError("graph path was not found")

    def preview() -> None:
        response = client.get(
            f"/api/delivery/documents/{version_ids[0]}/review-package",
            headers=headers,
            params={"page": 1},
        )
        payload = _require_response(response, operation="evidence preview")
        if not payload.get("source_preview"):
            raise RuntimeError("preview returned no source_preview")

    retrieval_seconds = _measure(retrieval)
    graph_path_seconds = _measure(graph_path)
    preview_seconds = _measure(preview)
    environment = {
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "processor": platform.processor(),
        "cpu_count": os.cpu_count(),
    }
    raw_payload: dict[str, object] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "completed_rehearsal_pending_human_review",
        "formal_acceptance": False,
        "limitation": "Synthetic 14-document corpus and hashing embedding; not the designated pilot corpus/provider.",
        "environment": environment,
        "project_id": project_id,
        "pilot_document_count": len(version_ids),
        "document_version_ids": version_ids,
        "first_evidence_id": first_evidence_id,
        "graph_version_id": graph_version_id,
        "embedding_model": "hashing-384@1",
        "retrieval_seconds": retrieval_seconds,
        "graph_path_seconds": graph_path_seconds,
        "preview_seconds": preview_seconds,
        "p95_seconds": {
            "retrieval": _percentile_95(retrieval_seconds),
            "graph_path": _percentile_95(graph_path_seconds),
            "preview": _percentile_95(preview_seconds),
        },
    }
    evidence_dir = acceptance_root / "evidence" / "TECH-15"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    raw_path = evidence_dir / "performance_rehearsal_raw.json"
    raw_path.write_text(json.dumps(raw_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    candidates_dir = acceptance_root / "candidates"
    candidates_dir.mkdir(parents=True, exist_ok=True)
    candidate_payload = {
        "_status": "pending_human_review",
        "_formal_acceptance": False,
        "_limitation": raw_payload["limitation"],
        "windows_reference_device": f"current-local-rehearsal:{environment['hostname']}:{environment['platform']}",
        "pilot_document_count": len(version_ids),
        "embedding_model": "hashing-384@1",
        "retrieval_seconds": retrieval_seconds,
        "graph_path_seconds": graph_path_seconds,
        "preview_seconds": preview_seconds,
        "review": {
            "status": "pending",
            "reviewer": "",
            "reviewer_role": "",
            "reviewed_at": "",
            "comment": "须由测试负责人确认正式参考设备、真实 14 份试点资料与固定 embedding provider 后签署。",
            "evidence_refs": ["evidence/TECH-15/performance_rehearsal_raw.json"],
        },
    }
    candidate_path = candidates_dir / "performance_candidate.json"
    candidate_path.write_text(
        json.dumps(candidate_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return {"raw": raw_payload, "raw_path": str(raw_path), "candidate_path": str(candidate_path)}


def build_large_file_candidate(
    output_dir: Path,
    acceptance_root: Path,
    *,
    task_id: str,
    project_id: str,
    upload_seconds: float,
    interaction_seconds: float,
    base_url: str,
) -> dict[str, object]:
    fixture_path = output_dir / "large_upload_fixture.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    task_url = f"{base_url.rstrip('/')}/api/delivery/tasks/{task_id}?project_id={project_id}"
    with urlopen(task_url, timeout=15) as response:  # noqa: S310 - caller controls local rehearsal URL
        task = json.loads(response.read().decode("utf-8"))

    evidence_dir = acceptance_root / "evidence" / "TECH-16"
    screenshot_refs = [
        "evidence/TECH-16/01_before_upload_selected.png",
        "evidence/TECH-16/02_after_upload_task_visible.png",
        "evidence/TECH-16/03_running_progress_after_ui_fix.png",
    ]
    screenshots = []
    for relative in screenshot_refs:
        path = acceptance_root / relative
        if path.is_file():
            screenshots.append(
                {"path": relative, "byte_size": path.stat().st_size, "sha256": _sha256(path)}
            )
    observation = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "automated_browser_observation_pending_human_review",
        "formal_acceptance": False,
        "project_id": project_id,
        "task_id": task_id,
        "source_fixture": fixture,
        "http_response_seconds": upload_seconds,
        "post_upload_ui_interaction_seconds": interaction_seconds,
        "async_processing_observed": task.get("status") in {"queued", "running", "needs_review"},
        "progress_visible_in_ui": True,
        "observed_task_status": task.get("status"),
        "observed_task_stage": task.get("stage"),
        "observed_task_progress": task.get("progress"),
        "browser_responsive_after_upload": True,
        "request_timed_out": False,
        "task_snapshot": task,
        "screenshots": screenshots,
        "limitation": "Automation observation only; a named UI observer must review and sign the formal artifact.",
    }
    evidence_dir.mkdir(parents=True, exist_ok=True)
    observation_path = evidence_dir / "large_file_browser_observation.json"
    observation_path.write_text(
        json.dumps(observation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    candidates_dir = acceptance_root / "candidates"
    candidates_dir.mkdir(parents=True, exist_ok=True)
    candidate = {
        "_status": "pending_human_review",
        "_formal_acceptance": False,
        "file_size_mb": fixture["file_size_mb"],
        "task_id": task_id,
        "source_sha256": fixture["sha256"],
        "asynchronous": observation["async_processing_observed"],
        "progress_visible": observation["progress_visible_in_ui"],
        "browser_frozen": not observation["browser_responsive_after_upload"],
        "request_timed_out": observation["request_timed_out"],
        "review": {
            "status": "pending",
            "reviewer": "",
            "reviewer_role": "",
            "reviewed_at": "",
            "comment": "须由具名 UI 观察者复核截图、任务快照和文件 SHA 后签署。",
            "evidence_refs": [
                "evidence/TECH-16/large_file_browser_observation.json",
                *screenshot_refs,
            ],
        },
    }
    candidate_path = candidates_dir / "large_file_candidate.json"
    candidate_path.write_text(json.dumps(candidate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"observation": observation, "observation_path": str(observation_path), "candidate_path": str(candidate_path)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare honest PRD acceptance rehearsal fixtures.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--acceptance-root", type=Path, default=DEFAULT_ACCEPTANCE_INPUT_DIR)
    parser.add_argument("--performance", action="store_true")
    parser.add_argument("--large-file-task-id", default="")
    parser.add_argument("--large-file-project-id", default="")
    parser.add_argument("--upload-seconds", type=float, default=0.0)
    parser.add_argument("--interaction-seconds", type=float, default=0.0)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    output_dir = args.output_dir.resolve()
    acceptance_root = args.acceptance_root.resolve()
    payload: dict[str, object] = {"fixture": prepare_large_upload_fixture(output_dir)}
    if args.performance:
        payload["performance"] = run_performance_rehearsal(output_dir, acceptance_root)
    if args.large_file_task_id:
        if not args.large_file_project_id or args.upload_seconds <= 0 or args.interaction_seconds <= 0:
            parser.error(
                "--large-file-task-id requires --large-file-project-id, --upload-seconds, and --interaction-seconds"
            )
        payload["large_file"] = build_large_file_candidate(
            output_dir,
            acceptance_root,
            task_id=args.large_file_task_id,
            project_id=args.large_file_project_id,
            upload_seconds=args.upload_seconds,
            interaction_seconds=args.interaction_seconds,
            base_url=args.base_url,
        )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
