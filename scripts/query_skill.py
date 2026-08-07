"""Stable command-line adapter for one GraphRAG query."""

from __future__ import annotations

import argparse
import logging
import os
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parents[1]
SITE_PACKAGES = REPO_ROOT / ".venv" / "Lib" / "site-packages"
POC_SRC = REPO_ROOT / "api_server" / "current_console" / "chroma_rag_poc" / "src"
for import_path in (REPO_ROOT, SITE_PACKAGES, POC_SRC):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

import orjson  # noqa: E402
from chroma_rag_poc.query_service import (  # noqa: E402
    EngineQueryRuntimeFactory,
    QueryExecutionError,
    QueryRuntime,
    QueryService,
)
from chroma_rag_poc.workspace_registry import (  # noqa: E402
    WorkspaceConfigError,
    WorkspaceNotFoundError,
    WorkspaceRegistry,
)
from pydantic import ValidationError  # noqa: E402

from core_domain.query_contracts import (  # noqa: E402
    ErrorDetail,
    QueryErrorResponse,
    QueryMode,
    QueryRequest,
    QueryResponse,
    QueryStatus,
)

LOGGER = logging.getLogger("graphrag.query_skill")
TEST_OUTCOME_ENV = "RAG_QUERY_SKILL_TEST_OUTCOME"
TEST_OUTCOMES = frozenset({"success", "WORKSPACE_NOT_FOUND", "INDEX_NOT_READY", "LLM_UNAVAILABLE", "QUERY_FAILED"})
EXIT_CODES = {
    "INVALID_REQUEST": 2,
    "WORKSPACE_NOT_FOUND": 3,
    "INDEX_NOT_READY": 4,
    "LLM_UNAVAILABLE": 5,
    "QUERY_FAILED": 10,
}


class ArgumentError(ValueError):
    """Raised for parser failures that must use the v1 error envelope."""


class V1ArgumentParser(argparse.ArgumentParser):
    """Argparse parser that never writes usage text for invalid input."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(add_help=False, **kwargs)

    def error(self, message: str) -> None:
        raise ArgumentError(message)


def _top_k(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("top-k must be an integer from 1 to 100") from exc  # noqa: TRY003
    if not 1 <= parsed <= 100:
        raise argparse.ArgumentTypeError("top-k must be an integer from 1 to 100")  # noqa: TRY003
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = V1ArgumentParser(description="Run one GraphRAG query through the v1 skill adapter.")
    parser.add_argument("--query", required=True, help="Question to answer.")
    parser.add_argument("--workspace", required=True, dest="workspace_id", help="Logical workspace ID.")
    parser.add_argument("--mode", choices=tuple(mode.value for mode in QueryMode), default=QueryMode.AUTO.value)
    parser.add_argument("--top-k", type=_top_k, default=5)
    parser.add_argument("--include-context", action="store_true")
    parser.add_argument("--include-debug", action="store_true")
    parser.add_argument("--pretty", action="store_true")
    return parser


def _configure_logging() -> None:
    if LOGGER.handlers:
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    LOGGER.addHandler(handler)
    LOGGER.setLevel(logging.INFO)
    LOGGER.propagate = False


def _serialize(response: QueryResponse | QueryErrorResponse, *, pretty: bool) -> None:
    option = orjson.OPT_INDENT_2 if pretty else 0
    encoded = orjson.dumps(response.model_dump(mode="json"), option=option)
    sys.stdout.buffer.write(encoded)
    sys.stdout.buffer.write(b"\n")


def _error_response(
    code: str,
    message: str,
    *,
    retryable: bool,
    details: dict[str, Any] | None = None,
) -> QueryErrorResponse:
    request_id = str(uuid.uuid4())
    return QueryErrorResponse(
        request_id=request_id,
        trace_id=str(uuid.uuid4()),
        error=ErrorDetail(
            code=code,
            message=message,
            retryable=retryable,
            details=details or {},
        ),
    )


def _emit_error(
    code: str,
    message: str,
    *,
    retryable: bool,
    details: dict[str, Any] | None = None,
    pretty: bool = False,
) -> int:
    LOGGER.error("query failed with code=%s", code)
    _serialize(
        _error_response(code, message, retryable=retryable, details=details),
        pretty=pretty,
    )
    return EXIT_CODES.get(code, EXIT_CODES["QUERY_FAILED"])


def _request_from_args(args: argparse.Namespace) -> QueryRequest:
    return QueryRequest(
        query=args.query,
        workspace_id=args.workspace_id,
        mode=args.mode,
        top_k=args.top_k,
        include_context=args.include_context,
        include_debug=args.include_debug,
    )


def build_query_service() -> QueryService:
    """Build the same registry-backed service used by the HTTP adapter."""

    test_outcome = os.environ.get(TEST_OUTCOME_ENV)
    if test_outcome is not None:
        return _build_test_service(test_outcome)
    registry = WorkspaceRegistry.from_env()
    return QueryService(registry, EngineQueryRuntimeFactory())


def _build_test_service(outcome: str) -> QueryService:
    """Provide a narrow subprocess seam for deterministic adapter integration tests."""

    if outcome not in TEST_OUTCOMES:
        raise ValueError(f"Unsupported {TEST_OUTCOME_ENV} value.")  # noqa: TRY003
    return QueryService(
        _TestRegistry(outcome),
        _TestRuntimeFactory(outcome),
    )


@dataclass(frozen=True)
class _TestWorkspace:
    default_mode: QueryMode = QueryMode.LOCAL


class _TestRegistry:
    def __init__(self, outcome: str) -> None:
        self.outcome = outcome

    def get(self, workspace_id: str) -> _TestWorkspace:
        if self.outcome == "WORKSPACE_NOT_FOUND":
            raise WorkspaceNotFoundError(workspace_id)
        return _TestWorkspace()


class _TestRetriever:
    def __init__(self, results: list[dict[str, str]]) -> None:
        self.results = results

    def retrieve(self, query: str, *, top_k: int) -> list[dict[str, str]]:
        del query, top_k
        return self.results


class _TestLLM:
    def generate(self, prompt: str) -> str:
        del prompt
        return "test answer"


class _TestRuntimeFactory:
    def __init__(self, outcome: str) -> None:
        self.outcome = outcome

    def create(self, workspace: _TestWorkspace) -> QueryRuntime:
        del workspace
        if self.outcome != "success":
            raise QueryExecutionError(
                self.outcome,
                f"Controlled test outcome: {self.outcome}.",
                retryable=self.outcome in {"LLM_UNAVAILABLE", "QUERY_FAILED"},
            )
        return QueryRuntime(
            text_retriever=_TestRetriever([{"id": "T1", "text": "test evidence"}]),
            graph_retriever=_TestRetriever([]),
            global_searcher=None,
            query_router=None,
            reranker=None,
            hallucination_guard=None,
            llm=_TestLLM(),
        )


def main(argv: list[str] | None = None) -> int:
    _configure_logging()
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        request = _request_from_args(args)
    except (ArgumentError, ValidationError) as exc:
        return _emit_error(
            "INVALID_REQUEST",
            "Invalid query request.",
            retryable=False,
            details={"reason": str(exc)},
            pretty=False,
        )

    try:
        response = build_query_service().query(request)
    except WorkspaceNotFoundError as exc:
        return _emit_error(
            "WORKSPACE_NOT_FOUND",
            str(exc),
            retryable=False,
            details={"workspace_id": exc.workspace_id},
            pretty=args.pretty,
        )
    except QueryExecutionError as exc:
        return _emit_error(
            exc.code,
            exc.message,
            retryable=exc.retryable,
            details=exc.details,
            pretty=args.pretty,
        )
    except WorkspaceConfigError:
        return _emit_error(
            "QUERY_FAILED",
            "Unable to load the workspace registry.",
            retryable=False,
            pretty=args.pretty,
        )
    except Exception:
        return _emit_error(
            "QUERY_FAILED",
            "Query execution failed.",
            retryable=True,
            pretty=args.pretty,
        )

    _serialize(response, pretty=args.pretty)
    return 0 if response.status in {QueryStatus.OK, QueryStatus.PARTIAL} else EXIT_CODES["QUERY_FAILED"]


if __name__ == "__main__":
    raise SystemExit(main())
