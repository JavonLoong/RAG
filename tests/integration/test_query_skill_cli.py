"""Process-level tests for the stable GraphRAG skill query CLI."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PYTHON = REPO_ROOT / ".venv" / "Scripts" / "python.exe"
SCRIPT = REPO_ROOT / "scripts" / "query_skill.py"
TEST_OUTCOME_ENV = "RAG_QUERY_SKILL_TEST_OUTCOME"


def run_cli(
    *arguments: str,
    outcome: str | None = None,
    env_updates: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment.pop("RAG_WORKSPACE_CONFIG", None)
    if outcome is not None:
        environment[TEST_OUTCOME_ENV] = outcome
    else:
        environment.pop(TEST_OUTCOME_ENV, None)
    environment.update(env_updates or {})
    return subprocess.run(  # noqa: S603
        [str(PYTHON), str(SCRIPT), *arguments],
        cwd=REPO_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def response_payload(result: subprocess.CompletedProcess[str]) -> dict[str, object]:
    assert result.stdout.endswith("\n")
    return json.loads(result.stdout)


def test_success_emits_one_v1_response_and_keeps_logs_on_stderr() -> None:
    result = run_cli(
        "--query",
        "燃烧不稳定原因",
        "--workspace",
        "power-equipment",
        "--mode",
        "local",
        "--top-k",
        "5",
        "--include-context",
        "--include-debug",
        outcome="success",
        env_updates={"OPENAI_API_KEY": "test-api-key"},
    )

    assert result.returncode == 0
    payload = response_payload(result)
    assert payload["schema_version"] == "graphrag.query.v1"
    assert payload["status"] == "ok"
    assert result.stdout.count("\n") == 1
    assert "test-api-key" not in result.stderr


def test_pretty_serialization_is_one_v1_object() -> None:
    result = run_cli(
        "--query",
        "燃烧不稳定原因",
        "--workspace",
        "power-equipment",
        "--pretty",
        outcome="success",
    )

    assert result.returncode == 0
    payload = response_payload(result)
    assert payload["schema_version"] == "graphrag.query.v1"
    assert result.stdout.count("\n") > 1


@pytest.mark.parametrize(
    "arguments",
    [
        ("--workspace", "power-equipment"),
        ("--query", "q", "--workspace", "power-equipment", "--top-k", "0"),
        ("--query", "q", "--workspace", "power-equipment", "--mode", "drift"),
        ("--query", "q", "--workspace", "power-equipment", "--upload", "file.pdf"),
    ],
)
def test_argument_errors_emit_invalid_request_json(arguments: tuple[str, ...]) -> None:
    result = run_cli(*arguments)

    assert result.returncode == 2
    payload = response_payload(result)
    assert payload["schema_version"] == "graphrag.query.v1"
    assert payload["status"] == "error"
    assert payload["error"]["code"] == "INVALID_REQUEST"  # type: ignore[index]
    assert "usage:" not in result.stdout


@pytest.mark.parametrize(
    ("outcome", "expected_code", "expected_exit"),
    [
        ("WORKSPACE_NOT_FOUND", "WORKSPACE_NOT_FOUND", 3),
        ("INDEX_NOT_READY", "INDEX_NOT_READY", 4),
        ("LLM_UNAVAILABLE", "LLM_UNAVAILABLE", 5),
        ("QUERY_FAILED", "QUERY_FAILED", 10),
    ],
)
def test_service_outcomes_map_to_stable_exit_codes(
    outcome: str,
    expected_code: str,
    expected_exit: int,
) -> None:
    result = run_cli(
        "--query",
        "燃烧不稳定原因",
        "--workspace",
        "power-equipment",
        outcome=outcome,
    )

    assert result.returncode == expected_exit
    payload = response_payload(result)
    assert payload["schema_version"] == "graphrag.query.v1"
    assert payload["status"] == "error"
    assert payload["error"]["code"] == expected_code  # type: ignore[index]
