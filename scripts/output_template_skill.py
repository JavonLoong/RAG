"""Stable process interface for the generic structured-output template skill."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import NoReturn, cast

import orjson

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core_domain.fmea.codec import decode_evidence_pack  # noqa: E402
from core_domain.fmea.value_objects import EvidencePack  # noqa: E402
from core_domain.structured_output import (  # noqa: E402
    CandidateClaim,
    ClaimState,
    CompiledTemplate,
    JsonValue,
    StructuredCandidate,
    StructuredCandidateBatch,
    StructuredOutputError,
    TemplateLimits,
    ValidationIssue,
)
from structured_output_application import (  # noqa: E402
    StructuredCandidateValidator,
    StructuredOutputService,
    TemplateCompiler,
)
from structured_output_infrastructure import (  # noqa: E402
    Draft202012SchemaAdapter,
    FileTemplateRegistry,
    load_template_source,
)

SCHEMA_VERSION = "rag.structured-output.v1"
_MAX_INPUT_BYTES = 16 * 1024 * 1024

_PUBLIC_MESSAGES = {
    "CLI_USAGE_INVALID": "Command arguments are invalid.",
    "CANDIDATE_SOURCE_INVALID": "Candidate batch input is invalid.",
    "EVIDENCE_PACK_INVALID": "Evidence pack input is invalid.",
    "OUTPUT_PATH_INVALID": "Compiled output path is invalid.",
    "TEMPLATE_NOT_FOUND": "Template was not found.",
    "TEMPLATE_VERSION_CONFLICT": "Template version already exists with different content.",
    "TEMPLATE_HASH_MISMATCH": "Template integrity verification failed.",
    "TEMPLATE_PATH_INVALID": "Template registry path is invalid.",
    "TEMPLATE_REGISTRY_ERROR": "Template registry operation failed.",
    "INTERNAL_ERROR": "The command could not be completed.",
}
_REGISTRY_CODES = frozenset(
    {
        "OUTPUT_PATH_INVALID",
        "TEMPLATE_NOT_FOUND",
        "TEMPLATE_VERSION_CONFLICT",
        "TEMPLATE_HASH_MISMATCH",
        "TEMPLATE_PATH_INVALID",
        "TEMPLATE_REGISTRY_ERROR",
    }
)


class CliUsageError(ValueError):
    pass


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        del message
        raise CliUsageError


def _parser() -> SafeArgumentParser:
    parser = SafeArgumentParser(allow_abbrev=False, add_help=False)
    subparsers = parser.add_subparsers(dest="command", required=True)

    def command(name: str) -> argparse.ArgumentParser:
        result = subparsers.add_parser(name, allow_abbrev=False, add_help=False)
        result.add_argument("--pretty", action="store_true")
        return result

    validate = command("validate")
    validate.add_argument("source")

    compile_command = command("compile")
    compile_command.add_argument("source")
    compile_command.add_argument("--out", required=True)

    register = command("register")
    register.add_argument("source")
    register.add_argument("--registry", required=True)

    show = command("show")
    show.add_argument("template_ref")
    show.add_argument("--registry", required=True)

    example = command("example")
    example.add_argument("template_ref")
    example.add_argument("--registry", required=True)

    validate_candidate = command("validate-candidate")
    validate_candidate.add_argument("batch")
    validate_candidate.add_argument("--pack", required=True)
    validate_candidate.add_argument("--registry", required=True)
    return parser


def _compose(registry_root: str | Path | None = None) -> StructuredOutputService:
    limits = TemplateLimits()
    schema = Draft202012SchemaAdapter()
    compiler = TemplateCompiler(
        schema_validator=schema,
        source_loader=load_template_source,
        limits=limits,
    )
    root = Path(registry_root) if registry_root is not None else ROOT / ".structured-output-unused"
    registry = FileTemplateRegistry(root, limits=limits)
    validator = StructuredCandidateValidator(schema, limits=limits)
    return StructuredOutputService(
        compiler=compiler,
        registry=registry,
        schema_validator=schema,
        candidate_validator=validator,
        limits=limits,
    )


def _template_result(template: CompiledTemplate) -> dict[str, JsonValue]:
    compiled = orjson.loads(template.canonical_json)
    if not isinstance(compiled, dict):
        raise StructuredOutputError("TEMPLATE_HASH_MISMATCH", "Compiled template is invalid.")
    result = cast("dict[str, JsonValue]", compiled)
    result["template_hash"] = template.template_hash
    return result


def _issue_result(issue: ValidationIssue) -> dict[str, JsonValue]:
    return {
        "code": issue.code,
        "message": issue.message,
        "pointer": issue.pointer,
        "candidate_id": issue.candidate_id,
        "target": issue.target,
        "binding": issue.binding,
    }


def _batch_result(batch: StructuredCandidateBatch) -> dict[str, JsonValue]:
    return {
        "template_id": batch.template_id,
        "template_version": batch.template_version,
        "template_hash": batch.template_hash,
        "evidence_pack_id": batch.evidence_pack_id,
        "candidates": [
            {
                "candidate_id": candidate.candidate_id,
                "payload": candidate.payload,
                "claims": [
                    {
                        "target": claim.target,
                        "state": claim.state.value,
                        "evidence_ids": list(claim.evidence_ids),
                    }
                    for claim in candidate.claims
                ],
            }
            for candidate in batch.candidates
        ],
    }


def _read_bounded(path: str | Path) -> str:
    try:
        raw = Path(path).read_bytes()
    except OSError as exc:
        raise StructuredOutputError("CANDIDATE_SOURCE_INVALID", "Input file could not be read.") from exc
    if len(raw) > _MAX_INPUT_BYTES:
        raise StructuredOutputError("TEMPLATE_LIMIT_EXCEEDED", "Input file exceeds the configured limit.")
    try:
        return raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise StructuredOutputError("CANDIDATE_SOURCE_INVALID", "Input file must be UTF-8.") from exc


def _object(value: object, expected: frozenset[str]) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != expected:
        raise StructuredOutputError("CANDIDATE_SOURCE_INVALID", "Candidate input shape is invalid.")
    return cast("dict[str, object]", value)


def _array(value: object) -> list[object]:
    if not isinstance(value, list):
        raise StructuredOutputError("CANDIDATE_SOURCE_INVALID", "Candidate array input is invalid.")
    return value


def _decode_batch(path: str | Path) -> StructuredCandidateBatch:
    try:
        root = _object(
            orjson.loads(_read_bounded(path)),
            frozenset(
                {
                    "template_id",
                    "template_version",
                    "template_hash",
                    "evidence_pack_id",
                    "candidates",
                }
            ),
        )
        raw_candidates = _array(root["candidates"])
        candidates = []
        for raw_candidate in raw_candidates:
            candidate = _object(
                raw_candidate,
                frozenset({"candidate_id", "payload", "claims"}),
            )
            raw_claims = _array(candidate["claims"])
            claims = []
            for raw_claim in raw_claims:
                claim = _object(
                    raw_claim,
                    frozenset({"target", "state", "evidence_ids"}),
                )
                evidence_ids = _array(claim["evidence_ids"])
                claims.append(
                    CandidateClaim(
                        target=cast("str", claim["target"]),
                        state=ClaimState(cast("str", claim["state"])),
                        evidence_ids=tuple(cast("list[str]", evidence_ids)),
                    )
                )
            candidates.append(
                StructuredCandidate(
                    candidate_id=cast("str", candidate["candidate_id"]),
                    payload=cast("JsonValue", candidate["payload"]),
                    claims=tuple(claims),
                )
            )
        return StructuredCandidateBatch(
            template_id=cast("str", root["template_id"]),
            template_version=cast("str", root["template_version"]),
            template_hash=cast("str", root["template_hash"]),
            evidence_pack_id=cast("str", root["evidence_pack_id"]),
            candidates=tuple(candidates),
        )
    except StructuredOutputError:
        raise
    except (orjson.JSONDecodeError, TypeError, ValueError, KeyError) as exc:
        raise StructuredOutputError("CANDIDATE_SOURCE_INVALID", "Candidate batch input is invalid.") from exc


def _decode_pack(path: str | Path) -> EvidencePack:
    try:
        return decode_evidence_pack(_read_bounded(path))
    except Exception as exc:
        raise StructuredOutputError("EVIDENCE_PACK_INVALID", "Evidence pack input is invalid.") from exc


def _parse_ref(value: str) -> tuple[str, str]:
    if not isinstance(value, str) or value.count("@") != 1:
        raise StructuredOutputError("CLI_USAGE_INVALID", "Template reference is invalid.")
    template_id, version = value.split("@", 1)
    if not template_id or not version:
        raise StructuredOutputError("CLI_USAGE_INVALID", "Template reference is invalid.")
    return template_id, version


def _write_compiled(path: str | Path, template: CompiledTemplate) -> None:
    target = _validated_output_target(path)
    try:
        with target.open("xb") as stream:
            stream.write(template.canonical_json.encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as exc:
        raise StructuredOutputError("OUTPUT_PATH_INVALID", "Compiled output path is invalid.") from exc


def _validated_output_target(path: str | Path) -> Path:
    requested = Path(path)
    try:
        parent = requested.parent.resolve(strict=True)
        target = requested.resolve(strict=False)
    except OSError as exc:
        raise StructuredOutputError("OUTPUT_PATH_INVALID", "Compiled output path is invalid.") from exc
    if not parent.is_dir() or target.parent != parent or target.name in {"", ".", ".."}:
        raise StructuredOutputError("OUTPUT_PATH_INVALID", "Compiled output path is invalid.")
    return target


def _validation_failure(issues: tuple[ValidationIssue, ...]) -> tuple[dict[str, JsonValue], int]:
    first_code = issues[0].code if issues else "INTERNAL_ERROR"
    return _error_envelope(first_code, {"issues": [_issue_result(issue) for issue in issues]}), 2


def _execute(args: argparse.Namespace) -> tuple[dict[str, JsonValue], int]:
    command = cast("str", args.command)
    if command == "validate":
        template_report = _compose().validate_source(cast("str", args.source))
        if not template_report.valid:
            return _validation_failure(template_report.issues)
        return _success(
            command,
            _template_result(cast("CompiledTemplate", template_report.compiled_template)),
        ), 0
    if command == "compile":
        template = _compose().compile_source(cast("str", args.source))
        _write_compiled(cast("str", args.out), template)
        return _success(command, _template_result(template)), 0
    if command == "register":
        template = _compose(cast("str", args.registry)).register_source(cast("str", args.source))
        return _success(command, _template_result(template)), 0
    if command == "show":
        template_id, version = _parse_ref(cast("str", args.template_ref))
        template = _compose(cast("str", args.registry)).get_template(template_id, version)
        return _success(command, _template_result(template)), 0
    if command == "example":
        template_id, version = _parse_ref(cast("str", args.template_ref))
        batch = _compose(cast("str", args.registry)).make_example(template_id, version)
        return _success(command, {"example_only": True, "batch": _batch_result(batch)}), 0
    if command == "validate-candidate":
        batch = _decode_batch(cast("str", args.batch))
        pack = _decode_pack(cast("str", args.pack))
        candidate_report = _compose(cast("str", args.registry)).validate_candidates(batch, pack)
        if not candidate_report.valid:
            return _validation_failure(candidate_report.issues)
        return _success(
            command,
            {
                "valid": True,
                "issues": [],
                "batch": _batch_result(candidate_report.batch),
            },
        ), 0
    raise CliUsageError


def _success(command: str, result: dict[str, JsonValue]) -> dict[str, JsonValue]:
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ok",
        "command": command,
        "result": result,
    }


def _error_envelope(code: str, details: dict[str, JsonValue] | None = None) -> dict[str, JsonValue]:
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "error",
        "error": {
            "code": code,
            "message": _PUBLIC_MESSAGES.get(code, "Validation failed."),
            "details": details or {},
        },
    }


def _emit(payload: dict[str, JsonValue], *, pretty: bool) -> None:
    option = orjson.OPT_SORT_KEYS | (orjson.OPT_INDENT_2 if pretty else 0)
    sys.stdout.buffer.write(orjson.dumps(payload, option=option) + b"\n")
    sys.stdout.buffer.flush()


def main(argv: list[str] | None = None) -> int:
    raw_arguments = list(sys.argv[1:] if argv is None else argv)
    pretty = "--pretty" in raw_arguments
    try:
        args = _parser().parse_args(raw_arguments)
        response, exit_code = _execute(args)
    except CliUsageError:
        response, exit_code = _error_envelope("CLI_USAGE_INVALID"), 2
    except StructuredOutputError as exc:
        exit_code = 3 if exc.code in _REGISTRY_CODES else 2
        response = _error_envelope(exc.code)
    except Exception:
        response, exit_code = _error_envelope("INTERNAL_ERROR"), 1
    _emit(response, pretty=pretty)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
