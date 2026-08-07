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
UNTRUSTED_TEST_OUTCOME_ENV = "RAG_QUERY_SKILL_TEST_OUTCOME"

PROCESS_SERVICE_RUNNER = r'''
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

script_path = Path(sys.argv[1])
service_outcome = sys.argv[2]
cli_args = sys.argv[3:]
spec = importlib.util.spec_from_file_location("query_skill_under_test", script_path)
cli = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(cli)
from chroma_rag_poc.query_service import QueryRuntime


class Registry:
    def get(self, workspace_id):
        if service_outcome == "WORKSPACE_NOT_FOUND":
            raise cli.WorkspaceNotFoundError(workspace_id)
        return SimpleNamespace(default_mode=cli.QueryMode.LOCAL)


class Retriever:
    def __init__(self, results):
        self.results = results

    def retrieve(self, query, *, top_k):
        del query, top_k
        return self.results


class LLM:
    def generate(self, prompt):
        del prompt
        return "test answer"


class RuntimeFactory:
    def create(self, workspace):
        del workspace
        if service_outcome == "sensitive":
            raise cli.QueryExecutionError(
                "QUERY_FAILED",
                "secret-api-key=TOPSECRET; path=C:\\private\\rag\\index",
                retryable=True,
                details={"path": "C:\\private\\rag\\index", "cause": "TOPSECRET"},
            )
        if service_outcome != "success":
            raise cli.QueryExecutionError(
                service_outcome,
                "internal message that must not be public",
                retryable=True,
                details={"cause": "TOPSECRET"},
            )
        return QueryRuntime(
            text_retriever=Retriever([{"id": "T1", "text": "test evidence"}]),
            graph_retriever=Retriever([]),
            global_searcher=None,
            query_router=None,
            reranker=None,
            hallucination_guard=None,
            llm=LLM(),
        )


cli.build_query_service = lambda: cli.QueryService(Registry(), RuntimeFactory())
raise SystemExit(cli.main(cli_args))
'''


def run_cli(
    *arguments: str,
    service_outcome: str | None = None,
    env_updates: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment.pop("RAG_WORKSPACE_CONFIG", None)
    environment.pop(UNTRUSTED_TEST_OUTCOME_ENV, None)
    environment.update(env_updates or {})
    if service_outcome is None:
        command = [str(PYTHON), str(SCRIPT), *arguments]
    else:
        command = [str(PYTHON), "-c", PROCESS_SERVICE_RUNNER, str(SCRIPT), service_outcome, *arguments]
    return subprocess.run(  # noqa: S603
        command,
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
        service_outcome="success",
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
        service_outcome="success",
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
        ("--q", "q", "--work", "power-equipment"),
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
        service_outcome=outcome,
    )

    assert result.returncode == expected_exit
    payload = response_payload(result)
    assert payload["schema_version"] == "graphrag.query.v1"
    assert payload["status"] == "error"
    assert payload["error"]["code"] == expected_code  # type: ignore[index]


def test_direct_script_ignores_untrusted_outcome_environment(tmp_path: Path) -> None:
    config_path = tmp_path / "workspaces.json"
    config_path.write_text(
        json.dumps(
            {
                "allowed_root": str(tmp_path),
                "workspaces": {
                    "power-equipment": {
                        "chroma_persist_dir": str(tmp_path / "index"),
                        "chroma_collection": "test",
                        "supported_modes": ["local"],
                        "default_mode": "local",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    result = run_cli(
        "--query",
        "q",
        "--workspace",
        "missing-workspace",
        env_updates={
            "RAG_WORKSPACE_CONFIG": str(config_path),
            UNTRUSTED_TEST_OUTCOME_ENV: "success",
        },
    )

    assert result.returncode == 3
    payload = response_payload(result)
    assert payload["error"]["code"] == "WORKSPACE_NOT_FOUND"  # type: ignore[index]


def test_internal_service_error_does_not_leak_message_or_details() -> None:
    leak_marker = "TOPSECRET"
    private_path = r"C:\private\rag\index"
    result = run_cli(
        "--query",
        "q",
        "--workspace",
        "power-equipment",
        service_outcome="sensitive",
    )

    payload = response_payload(result)
    assert result.returncode == 10
    assert payload["error"]["code"] == "QUERY_FAILED"  # type: ignore[index]
    assert payload["error"]["message"] == "Query failed."  # type: ignore[index]
    assert payload["error"]["details"] == {}  # type: ignore[index]
    assert leak_marker not in result.stdout + result.stderr
    assert private_path not in result.stdout + result.stderr


def test_invalid_argument_does_not_leak_unknown_value_and_pretty_is_preserved() -> None:
    leak_marker = "TOPSECRET-api-key"
    result = run_cli(
        "--pretty",
        "--query",
        "q",
        "--workspace",
        "power-equipment",
        "--secret",
        leak_marker,
    )

    payload = response_payload(result)
    assert result.returncode == 2
    assert payload["error"]["code"] == "INVALID_REQUEST"  # type: ignore[index]
    assert result.stdout.count("\n") > 1
    assert leak_marker not in result.stdout + result.stderr
