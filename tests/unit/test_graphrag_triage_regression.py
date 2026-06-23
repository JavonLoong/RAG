from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CONSOLE_SRC = REPO_ROOT / "api_server" / "current_console" / "chroma_rag_poc" / "src"
if str(CONSOLE_SRC) not in sys.path:
    sys.path.insert(0, str(CONSOLE_SRC))


def test_graphrag_triage_regression_runner_skips_missing_dataset(tmp_path: Path) -> None:
    from evaluation.triage_regression import run_graphrag_triage_regression

    result = run_graphrag_triage_regression(
        rag_system=lambda question: {"answer": "", "retrieval_results": [], "citations": []},
        dataset_path=tmp_path / "missing.jsonl",
        report_dir=tmp_path / "reports",
    )

    assert result["status"] == "skipped"
    assert result["gate_status"] == "pass"
    assert result["case_count"] == 0


def test_graphrag_triage_regression_runner_evaluates_promoted_cases(tmp_path: Path) -> None:
    from evaluation.triage_regression import load_graphrag_triage_regression_cases, run_graphrag_triage_regression

    dataset_path = tmp_path / "graphrag_triage_regression.jsonl"
    dataset_path.write_text(
        json.dumps(
            {
                "id": "triage_case_1",
                "question": "Why is the graph answer trusted?",
                "reference_answer": "The graph answer is trusted when source evidence supports it.",
                "expected_evidence_keywords": ["source evidence", "trusted"],
                "task_type": "graphrag_triage",
                "source_scope": "graph.sqlite",
                "grading_notes": "promoted_from=triage-1",
                "expected_modes": ["global"],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    cases = load_graphrag_triage_regression_cases(dataset_path)
    assert [case.id for case in cases] == ["triage_case_1"]

    result = run_graphrag_triage_regression(
        rag_system=lambda question: {
            "answer": "The graph answer is trusted because source evidence supports it.",
            "retrieval_results": [{"text": "source evidence supports the trusted graph answer"}],
            "citations": [{"source": "graph.sqlite", "text": "source evidence supports the trusted graph answer"}],
        },
        dataset_path=dataset_path,
        report_dir=tmp_path / "reports",
    )

    assert result["status"] == "pass"
    assert result["gate_status"] == "pass"
    assert result["case_count"] == 1
    assert Path(result["reports"]["json"]).exists()
    assert Path(result["reports"]["md"]).exists()


def test_graphrag_triage_regression_cli_allows_empty_dataset(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_graphrag_triage_regression.py",
            "--dataset",
            str(tmp_path / "missing.jsonl"),
            "--report-dir",
            str(tmp_path / "reports"),
            "--allow-empty",
        ],
        cwd=Path(__file__).resolve().parents[2],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "triage_regression=pass" in completed.stdout
    assert "case_count=0" in completed.stdout


def test_graphrag_triage_regression_cli_runs_nonempty_cases_against_local_chroma(tmp_path: Path) -> None:
    from evaluation.smoke import SMOKE_COLLECTION
    from chroma_rag_poc.pipeline import ingest_source_payloads

    persist_dir = tmp_path / "chroma"
    report_dir = tmp_path / "reports"
    dataset_path = tmp_path / "graphrag_triage_regression.jsonl"
    ingest_source_payloads(
        payloads=[
            (
                "graph_trust.md",
                (
                    "Graph answers are trusted when source evidence supports every claim. "
                    "Human review promotes weak GraphRAG cases into regression tests."
                ).encode("utf-8"),
            )
        ],
        persist_dir=persist_dir,
        collection_name=SMOKE_COLLECTION,
        chunk_size=400,
        overlap=40,
        backend="hashing",
    )
    dataset_path.write_text(
        json.dumps(
            {
                "id": "triage_case_local_chroma",
                "question": "When are graph answers trusted?",
                "reference_answer": "Graph answers are trusted when source evidence supports every claim.",
                "expected_evidence_keywords": ["graph answers", "source evidence", "trusted"],
                "task_type": "graphrag_triage",
                "source_scope": "local_chroma",
                "expected_modes": ["local"],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_graphrag_triage_regression.py",
            "--dataset",
            str(dataset_path),
            "--report-dir",
            str(report_dir),
            "--persist-dir",
            str(persist_dir),
            "--collection",
            SMOKE_COLLECTION,
            "--backend",
            "hashing",
        ],
        cwd=Path(__file__).resolve().parents[2],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "triage_regression=pass" in completed.stdout
    assert "case_count=1" in completed.stdout
    assert list(report_dir.glob("rag_eval_graphrag_triage_regression_*.json"))
