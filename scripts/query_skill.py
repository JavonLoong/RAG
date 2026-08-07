"""Stable command-line adapter for one GraphRAG query."""

from __future__ import annotations

import argparse
import logging
import sys
import uuid
from pathlib import Path
from typing import Any, NoReturn

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
EXIT_CODES = {
    "INVALID_REQUEST": 2,
    "WORKSPACE_NOT_FOUND": 3,
    "INDEX_NOT_READY": 4,
    "LLM_UNAVAILABLE": 5,
    "QUERY_FAILED": 10,
}
PUBLIC_ERRORS = {
    "INVALID_REQUEST": ("Invalid query request.", False),
    "WORKSPACE_NOT_FOUND": ("The requested workspace was not found.", False),
    "INDEX_NOT_READY": ("The workspace index is not ready.", True),
    "LLM_UNAVAILABLE": ("The language model is unavailable.", True),
    "QUERY_FAILED": ("Query failed.", True),
}


class ArgumentError(ValueError):
    """Raised for parser failures that must use the v1 error envelope."""


class V1ArgumentParser(argparse.ArgumentParser):
    """Argparse parser that never writes usage text for invalid input."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(add_help=False, allow_abbrev=False, **kwargs)

    def error(self, message: str) -> NoReturn:
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
) -> QueryErrorResponse:
    public_code = code if code in PUBLIC_ERRORS else "QUERY_FAILED"
    message, retryable = PUBLIC_ERRORS[public_code]
    request_id = str(uuid.uuid4())
    return QueryErrorResponse(
        request_id=request_id,
        trace_id=str(uuid.uuid4()),
        error=ErrorDetail(
            code=public_code,
            message=message,
            retryable=retryable,
            details={},
        ),
    )


def _emit_error(
    code: str,
    pretty: bool = False,
) -> int:
    public_code = code if code in PUBLIC_ERRORS else "QUERY_FAILED"
    LOGGER.error("query failed with code=%s", public_code)
    _serialize(_error_response(public_code), pretty=pretty)
    return EXIT_CODES[public_code]


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

    registry = WorkspaceRegistry.from_env()
    return QueryService(registry, EngineQueryRuntimeFactory())


def _pretty_requested(argv: list[str] | None) -> bool:
    values = sys.argv[1:] if argv is None else argv
    return "--pretty" in values


def main(argv: list[str] | None = None) -> int:
    _configure_logging()
    parser = build_parser()
    pretty = _pretty_requested(argv)
    try:
        args = parser.parse_args(argv)
        request = _request_from_args(args)
    except (ArgumentError, ValidationError):
        return _emit_error("INVALID_REQUEST", pretty=pretty)

    try:
        response = build_query_service().query(request)
    except WorkspaceNotFoundError:
        return _emit_error("WORKSPACE_NOT_FOUND", pretty=args.pretty)
    except QueryExecutionError as exc:
        return _emit_error(exc.code, pretty=args.pretty)
    except WorkspaceConfigError:
        return _emit_error("QUERY_FAILED", pretty=args.pretty)
    except Exception:
        return _emit_error("QUERY_FAILED", pretty=args.pretty)

    _serialize(response, pretty=args.pretty)
    return 0 if response.status in {QueryStatus.OK, QueryStatus.PARTIAL} else EXIT_CODES["QUERY_FAILED"]


if __name__ == "__main__":
    raise SystemExit(main())
