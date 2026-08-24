"""Raw-byte orchestration for the synthetic structured-generation acceptance run."""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import NoReturn, Protocol, cast

import orjson

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.verify_structured_generation_acceptance import (  # noqa: E402
    SCHEMA_VERSION,
    AcceptanceVerificationError,
    verify_acceptance_output,
)

_GENERATION_SCRIPT = _ROOT / "scripts" / "structured_generation_skill.py"
_PROFILE = _ROOT / "templates" / "fmea_profiles" / "fuel-combustion-fmea-full.json"
_TEMPLATE_REF = "fuel-combustion-fmea-full@1.0.0"
_PROCESS_TIMEOUT_SECONDS = 150.0


class _AcceptanceSummaryView(Protocol):
    status: str
    candidate_count: int
    row_count: int
    trace_count: int
    evidence_link_count: int


class _CliUsageError(ValueError):
    pass


class _SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        del message
        raise _CliUsageError from None


def _success_payload(summary: _AcceptanceSummaryView) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "passed",
        "summary": {
            "status": summary.status,
            "candidate_count": summary.candidate_count,
            "row_count": summary.row_count,
            "trace_count": summary.trace_count,
            "evidence_link_count": summary.evidence_link_count,
        },
        "error": None,
    }


def _error_payload(code: str) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "failed",
        "summary": None,
        "error": {
            "code": code,
            "message": "Structured-generation acceptance orchestration failed.",
        },
    }


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_bytes(orjson.dumps(payload) + b"\n")


def _generation_command(
    *,
    registry: Path,
    pack: Path,
    analysis: Path,
    request: Path,
) -> list[str]:
    return [
        sys.executable,
        str(_GENERATION_SCRIPT),
        "run-fmea",
        "--template",
        _TEMPLATE_REF,
        "--pack",
        str(pack),
        "--analysis",
        str(analysis),
        "--profile",
        str(_PROFILE),
        "--registry",
        str(registry),
        "--request",
        str(request),
    ]


def run_acceptance(
    *,
    registry: Path,
    output_directory: Path,
    pack: Path,
    analysis: Path,
    request: Path,
    run_process: Callable[..., subprocess.CompletedProcess[bytes]] | None = None,
) -> tuple[int, dict[str, object]]:
    """Run generation as raw bytes, verify in memory, then persist only accepted output."""

    command = _generation_command(
        registry=registry,
        pack=pack,
        analysis=analysis,
        request=request,
    )
    active_run = run_process or cast(
        "Callable[..., subprocess.CompletedProcess[bytes]]",
        subprocess.run,
    )
    try:
        completed = active_run(
            command,
            cwd=_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=_PROCESS_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        payload = _error_payload("GENERATION_PROCESS_FAILED")
        exit_code = 5
    else:
        raw_output = completed.stdout
        if completed.returncode not in {0, 4} or not isinstance(raw_output, bytes):
            payload = _error_payload("GENERATION_STEP_FAILED")
            exit_code = completed.returncode if completed.returncode in {1, 2, 3, 5} else 5
        else:
            try:
                summary = cast(
                    "_AcceptanceSummaryView",
                    verify_acceptance_output(
                        raw_output,
                        pack.read_bytes(),
                        analysis.read_bytes(),
                        request.read_bytes(),
                    ),
                )
            except AcceptanceVerificationError as error:
                payload = _error_payload(error.code)
                exit_code = 2
            except OSError:
                payload = _error_payload("ACCEPTANCE_INPUT_INVALID")
                exit_code = 2
            else:
                payload = _success_payload(summary)
                exit_code = 0
                output_directory.mkdir(parents=True, exist_ok=True)
                persisted_output = raw_output if raw_output.endswith(b"\n") else raw_output + b"\n"
                (output_directory / "run-fmea.json").write_bytes(persisted_output)

    output_directory.mkdir(parents=True, exist_ok=True)
    _write_json(output_directory / "acceptance-summary.json", payload)
    return exit_code, payload


def _parser() -> argparse.ArgumentParser:
    parser = _SafeArgumentParser(allow_abbrev=False, add_help=False)
    parser.add_argument("--registry", required=True)
    parser.add_argument("--output-directory", required=True)
    parser.add_argument("--pack", required=True)
    parser.add_argument("--analysis", required=True)
    parser.add_argument("--request", required=True)
    return parser


def _emit(payload: dict[str, object]) -> None:
    sys.stdout.buffer.write(orjson.dumps(payload) + b"\n")


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
    except _CliUsageError:
        payload = _error_payload("CLI_USAGE_INVALID")
        exit_code = 2
    else:
        exit_code, payload = run_acceptance(
            registry=Path(args.registry),
            output_directory=Path(args.output_directory),
            pack=Path(args.pack),
            analysis=Path(args.analysis),
            request=Path(args.request),
        )
    _emit(payload)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main", "run_acceptance"]
