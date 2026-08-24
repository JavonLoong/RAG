"""Offline verifier for the synthetic fuel/combustion FMEA live acceptance run."""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import NoReturn, Protocol, cast

import orjson

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_TEMPLATE_PATH = _ROOT / "templates" / "examples" / "fuel-combustion-fmea-full.yaml"

SCHEMA_VERSION = "rag.structured-generation.acceptance.v1"
_GENERATION_SCHEMA = "rag.structured-generation.v1"
_MAX_OUTPUT_BYTES = 16_000_000
_MAX_PACK_BYTES = 16_000_000
_MAX_ANALYSIS_BYTES = 2_000_000
_MAX_REQUEST_BYTES = 64_000
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SAFE_CODE = re.compile(r"^[A-Z][A-Z0-9_]{0,127}$")
_PRIVATE_MARKER = re.compile(r"\b[A-Z][A-Z0-9_]*PRIVATE_MARKER\b")
_FMEA_FIELDS = (
    "item_id",
    "function_id",
    "failure_mode",
    "causes",
    "mechanisms",
    "effects",
    "symptoms",
    "controls",
    "barriers",
    "actions",
)
_FMEA_POINTERS = {
    "item_id": "/item",
    "function_id": "/function",
    "failure_mode": "/failure_mode",
    "causes": "/causes",
    "mechanisms": "/mechanisms",
    "effects": "/effects",
    "symptoms": "/symptoms",
    "controls": "/controls",
    "barriers": "/barriers",
    "actions": "/actions",
}
_ARRAY_PAYLOAD_FIELDS = (
    "causes",
    "mechanisms",
    "effects",
    "symptoms",
    "controls",
    "barriers",
    "actions",
)
_PAYLOAD_FIELDS = frozenset(
    {
        "item",
        "function",
        "failure_mode",
        "causes",
        "mechanisms",
        "effects",
        "symptoms",
        "controls",
        "barriers",
        "actions",
    }
)
_RESULT_KEYS = frozenset(
    {
        "batch",
        "critic",
        "deterministic_issues",
        "generation_issues",
        "traces",
        "repair_count",
        "fmea",
    }
)
_BATCH_KEYS = frozenset(
    {
        "template_id",
        "template_version",
        "template_hash",
        "evidence_pack_id",
        "candidates",
    }
)
_CANDIDATE_KEYS = frozenset({"candidate_id", "payload", "claims"})
_CLAIM_KEYS = frozenset({"target", "state", "evidence_ids"})
_TRACE_KEYS = frozenset(
    {
        "stage",
        "model_id",
        "prompt_hash",
        "response_hash",
        "http_attempts",
        "input_tokens",
        "output_tokens",
        "error_code",
    }
)
_ROW_KEYS = frozenset(
    {
        "row_id",
        "analysis_id",
        "evidence_pack_id",
        "item_id",
        "function_id",
        "failure_mode",
        "causes",
        "mechanisms",
        "effects",
        "symptoms",
        "controls",
        "barriers",
        "actions",
        "risk_assessment",
        "field_evidence",
        "field_support",
        "claim_status",
        "review_status",
        "publication_status",
        "record_version",
    }
)
_SCOPE_FORBIDDEN_KEYS = frozenset(
    {
        "severity",
        "severity_by_consequence_class",
        "occurrence",
        "detection",
        "rpn",
        "propagation",
        "propagation_edges",
        "approved_at",
        "approver_actor_id",
    }
)
_PRIVACY_FORBIDDEN_KEYS = frozenset(
    {
        "finish_reason",
        "reasoning",
        "reasoning_content",
        "raw_response",
        "system_prompt",
        "user_prompt",
    }
)


class _EvidenceRefView(Protocol):
    evidence_id: str
    quote: str


class _EvidencePackView(Protocol):
    pack_id: str
    refs: tuple[_EvidenceRefView, ...]


class _AnalysisView(Protocol):
    analysis_id: str


class _ClaimView(Protocol):
    target: str
    state: object
    evidence_ids: tuple[str, ...]


class _CandidateView(Protocol):
    candidate_id: str
    payload: object
    claims: tuple[_ClaimView, ...]


class _BatchView(Protocol):
    candidates: tuple[_CandidateView, ...]


class _TemplateView(Protocol):
    template_hash: str


class _ValidationReportView(Protocol):
    valid: bool


class _CandidateBatchCodec(Protocol):
    def decode_batch(self, content: str) -> _BatchView: ...


class _TemplateCompiler(Protocol):
    def compile_path(self, path: Path) -> _TemplateView: ...


class _CandidateValidator(Protocol):
    def validate(
        self,
        batch: _BatchView,
        template: _TemplateView,
        evidence_pack: _EvidencePackView,
    ) -> _ValidationReportView: ...


class _RowView(Protocol):
    failure_mode: str
    causes: tuple[str, ...]
    mechanisms: tuple[str, ...]
    effects: tuple[str, ...]
    symptoms: tuple[str, ...]
    controls: tuple[str, ...]
    barriers: tuple[str, ...]
    actions: tuple[str, ...]
    field_evidence: tuple[tuple[str, tuple[str, ...]], ...]
    claim_status: object


class _FmeaCodec(Protocol):
    def decode_analysis(self, payload: str) -> _AnalysisView: ...

    def decode_evidence_pack(self, payload: str) -> _EvidencePackView: ...

    def decode_row(self, payload: str) -> _RowView: ...


_FMEA_CODEC = cast("_FmeaCodec", import_module("core_domain.fmea.codec"))


class AcceptanceVerificationError(ValueError):
    """Stable error containing no model, evidence or filesystem text."""

    def __init__(self, code: str) -> None:
        super().__init__("Structured-generation acceptance verification failed.")
        self.code = code


class _CliUsageError(ValueError):
    pass


class _SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        del message
        raise _CliUsageError from None


@dataclass(frozen=True, slots=True)
class AcceptanceSummary:
    status: str
    candidate_count: int
    row_count: int
    trace_count: int
    evidence_link_count: int


def _fail(code: str) -> NoReturn:
    raise AcceptanceVerificationError(code)


def _bounded_text(payload: bytes | str, maximum: int, code: str) -> str:
    if isinstance(payload, bytes):
        if len(payload) > maximum:
            _fail(code)
        try:
            return payload.decode("utf-8", errors="strict")
        except UnicodeError:
            _fail(code)
    if not isinstance(payload, str) or len(payload.encode("utf-8")) > maximum:
        _fail(code)
    return payload


def _json_object(payload: str, code: str) -> dict[str, object]:
    try:
        value = orjson.loads(payload)
    except orjson.JSONDecodeError:
        _fail(code)
    if not isinstance(value, dict):
        _fail(code)
    return cast("dict[str, object]", value)


def _object(value: object, code: str) -> dict[str, object]:
    if not isinstance(value, dict):
        _fail(code)
    return cast("dict[str, object]", value)


def _array(value: object, code: str) -> list[object]:
    if not isinstance(value, list):
        _fail(code)
    return cast("list[object]", value)


def _exact_keys(value: dict[str, object], expected: frozenset[str] | set[str], code: str) -> None:
    if set(value) != expected:
        _fail(code)


def _walk_keys(value: object) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str):
                keys.add(key)
            keys.update(_walk_keys(item))
    elif isinstance(value, list):
        for item in value:
            keys.update(_walk_keys(item))
    return keys


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _decode_inputs(
    evidence_pack_payload: bytes | str,
    analysis_payload: bytes | str,
    request_payload: bytes | str,
) -> tuple[_EvidencePackView, _AnalysisView, dict[str, object]]:
    pack_text = _bounded_text(evidence_pack_payload, _MAX_PACK_BYTES, "EVIDENCE_PACK_INVALID")
    analysis_text = _bounded_text(analysis_payload, _MAX_ANALYSIS_BYTES, "ANALYSIS_INVALID")
    request_text = _bounded_text(request_payload, _MAX_REQUEST_BYTES, "REQUEST_INVALID")
    try:
        pack = _FMEA_CODEC.decode_evidence_pack(pack_text)
    except (KeyError, TypeError, ValueError):
        _fail("EVIDENCE_PACK_INVALID")
    try:
        analysis = _FMEA_CODEC.decode_analysis(analysis_text)
    except (KeyError, TypeError, ValueError):
        _fail("ANALYSIS_INVALID")
    request = _json_object(request_text, "REQUEST_INVALID")
    _exact_keys(request, {"run_id", "task"}, "REQUEST_INVALID")
    if not isinstance(request["run_id"], str) or not isinstance(request["task"], str):
        _fail("REQUEST_INVALID")
    return pack, analysis, request


def _validate_privacy(
    output_text: str,
    output: dict[str, object],
    pack: _EvidencePackView,
    request: dict[str, object],
) -> None:
    private_sources = [cast("str", request["task"])]
    private_sources.extend(ref.quote for ref in pack.refs)
    fragments = {
        marker
        for source in private_sources
        for marker in _PRIVATE_MARKER.findall(source)
    }
    if any(fragment in output_text for fragment in fragments):
        _fail("OUTPUT_PRIVACY_VIOLATION")
    if cast("str", request["task"]) in output_text:
        _fail("OUTPUT_PRIVACY_VIOLATION")
    if any(len(ref.quote) >= 80 and ref.quote in output_text for ref in pack.refs):
        _fail("OUTPUT_PRIVACY_VIOLATION")
    if _walk_keys(output) & _PRIVACY_FORBIDDEN_KEYS:
        _fail("OUTPUT_PRIVACY_VIOLATION")


def _production_batch(
    batch_payload: dict[str, object],
    pack: _EvidencePackView,
) -> _BatchView:
    try:
        generation_module = import_module("structured_generation_infrastructure")
        output_application = import_module("structured_output_application")
        output_infrastructure = import_module("structured_output_infrastructure")
        codec_factory = cast(
            "Callable[[], _CandidateBatchCodec]",
            generation_module.StrictCandidateBatchCodec,
        )
        schema_factory = cast(
            "Callable[[], object]",
            output_infrastructure.Draft202012SchemaAdapter,
        )
        compiler_factory = cast(
            "Callable[..., _TemplateCompiler]",
            output_application.TemplateCompiler,
        )
        validator_factory = cast(
            "Callable[[object], _CandidateValidator]",
            output_application.StructuredCandidateValidator,
        )
        source_loader = output_infrastructure.load_template_source
        schema = schema_factory()
        template = compiler_factory(schema_validator=schema, source_loader=source_loader).compile_path(
            _TEMPLATE_PATH
        )
        validator = validator_factory(schema)
    except Exception:
        _fail("ACCEPTANCE_CONFIGURATION_INVALID")
    try:
        batch = codec_factory().decode_batch(orjson.dumps(batch_payload).decode("utf-8"))
        report = validator.validate(batch, template, pack)
    except Exception:
        _fail("CANDIDATE_BATCH_INVALID")
    if not report.valid:
        _fail("CANDIDATE_BATCH_INVALID")
    return batch


def _validate_batch(
    result: dict[str, object],
    pack: _EvidencePackView,
) -> tuple[int, _BatchView]:
    batch = _object(result.get("batch"), "CANDIDATE_BATCH_INVALID")
    _exact_keys(batch, _BATCH_KEYS, "CANDIDATE_BATCH_INVALID")
    if (
        batch.get("template_id") != "fuel-combustion-fmea-full"
        or batch.get("template_version") != "1.0.0"
        or batch.get("evidence_pack_id") != pack.pack_id
        or not isinstance(batch.get("template_hash"), str)
        or _SHA256.fullmatch(cast("str", batch["template_hash"])) is None
    ):
        _fail("CANDIDATE_BATCH_INVALID")
    candidates = _array(batch.get("candidates"), "CANDIDATE_BATCH_INVALID")
    if not candidates or len(candidates) > 20:
        _fail("CANDIDATE_BATCH_INVALID")
    allowed_evidence_ids = {ref.evidence_id for ref in pack.refs}
    for raw_candidate in candidates:
        candidate = _object(raw_candidate, "CANDIDATE_BATCH_INVALID")
        _exact_keys(candidate, _CANDIDATE_KEYS, "CANDIDATE_BATCH_INVALID")
        if not isinstance(candidate.get("candidate_id"), str) or not candidate["candidate_id"]:
            _fail("CANDIDATE_BATCH_INVALID")
        payload = _object(candidate.get("payload"), "CANDIDATE_BATCH_INVALID")
        if set(payload) != _PAYLOAD_FIELDS:
            _fail("CANDIDATE_BATCH_INVALID")
        claims = _array(candidate.get("claims"), "CANDIDATE_BATCH_INVALID")
        for raw_claim in claims:
            claim = _object(raw_claim, "CANDIDATE_BATCH_INVALID")
            _exact_keys(claim, _CLAIM_KEYS, "CANDIDATE_BATCH_INVALID")
            if (
                not isinstance(claim.get("target"), str)
                or not claim["target"]
                or claim.get("state")
                not in {"known", "unknown", "insufficient_evidence", "conflict", "not_applicable"}
            ):
                _fail("CANDIDATE_BATCH_INVALID")
            evidence_ids = _array(claim.get("evidence_ids"), "CANDIDATE_BATCH_INVALID")
            if any(
                not isinstance(evidence_id, str) or evidence_id not in allowed_evidence_ids
                for evidence_id in evidence_ids
            ):
                _fail("FMEA_EVIDENCE_OUTSIDE_PACK")
    return len(candidates), _production_batch(batch, pack)


def _valid_optional_tokens(value: object) -> bool:
    return value is None or (_is_int(value) and cast("int", value) >= 0)


def _validate_trace(raw_trace: object, identity: tuple[str, str]) -> None:
    trace = _object(raw_trace, "MODEL_TRACE_INVALID")
    _exact_keys(trace, _TRACE_KEYS, "MODEL_TRACE_INVALID")
    if (trace.get("stage"), trace.get("model_id")) != identity:
        _fail("MODEL_TRACE_INVALID")
    for field_name in ("prompt_hash", "response_hash"):
        field = trace.get(field_name)
        if not isinstance(field, str) or _SHA256.fullmatch(field) is None:
            _fail("MODEL_TRACE_INVALID")
    if (
        trace.get("error_code") is not None
        or not _is_int(trace.get("http_attempts"))
        or cast("int", trace["http_attempts"]) < 1
        or not _valid_optional_tokens(trace.get("input_tokens"))
        or not _valid_optional_tokens(trace.get("output_tokens"))
    ):
        _fail("MODEL_TRACE_INVALID")


def _state_value(claim: _ClaimView) -> object:
    return getattr(claim.state, "value", None)


def _validate_critic(
    raw_critic: object,
    batch: _BatchView,
    pack: _EvidencePackView,
) -> None:
    critic = _object(raw_critic, "MODEL_TRACE_INVALID")
    _exact_keys(critic, {"verdict", "findings"}, "MODEL_TRACE_INVALID")
    verdict = critic.get("verdict")
    if verdict not in {"accept", "needs_review"}:
        _fail("MODEL_TRACE_INVALID")
    findings = _array(critic.get("findings"), "MODEL_TRACE_INVALID")
    claims = {
        (candidate.candidate_id, claim.target): claim
        for candidate in batch.candidates
        for claim in candidate.claims
    }
    expected = {
        identity: claim
        for identity, claim in claims.items()
        if _state_value(claim) in {"known", "conflict", "insufficient_evidence"}
        and claim.evidence_ids
    }
    allowed_evidence = {ref.evidence_id for ref in pack.refs}
    seen: set[tuple[str, str]] = set()
    for raw_finding in findings:
        finding = _object(raw_finding, "MODEL_TRACE_INVALID")
        _exact_keys(
            finding,
            {"candidate_id", "target", "support", "code", "evidence_ids"},
            "MODEL_TRACE_INVALID",
        )
        candidate_id = finding.get("candidate_id")
        target = finding.get("target")
        code = finding.get("code")
        support = finding.get("support")
        if (
            not isinstance(candidate_id, str)
            or not isinstance(target, str)
            or not isinstance(code, str)
            or _SAFE_CODE.fullmatch(code) is None
            or support
            not in {
                "supported",
                "partially_supported",
                "contradicted",
                "not_supported",
            }
        ):
            _fail("MODEL_TRACE_INVALID")
        identity = (candidate_id, target)
        claim = expected.get(identity)
        if claim is None or identity in seen:
            _fail("MODEL_TRACE_INVALID")
        seen.add(identity)
        evidence_ids = _array(finding.get("evidence_ids"), "MODEL_TRACE_INVALID")
        if (
            not evidence_ids
            or len(evidence_ids) != len(set(cast("list[object]", evidence_ids)))
            or any(
                not isinstance(evidence_id, str)
                or evidence_id not in claim.evidence_ids
                or evidence_id not in allowed_evidence
                for evidence_id in evidence_ids
            )
        ):
            _fail("MODEL_TRACE_INVALID")
        state = _state_value(claim)
        if (
            (state == "known" and support in {"contradicted", "not_supported"})
            or (state in {"conflict", "insufficient_evidence"} and verdict != "needs_review")
            or (support == "partially_supported" and verdict != "needs_review")
        ):
            _fail("MODEL_TRACE_INVALID")
    if seen != set(expected):
        _fail("MODEL_TRACE_INVALID")


def _validate_traces(
    result: dict[str, object],
    batch: _BatchView,
    pack: _EvidencePackView,
) -> int:
    traces = _array(result.get("traces"), "MODEL_TRACE_INVALID")
    if len(traces) not in {2, 3}:
        _fail("MODEL_TRACE_INVALID")
    expected = [
        ("generate", "deepseek-v4-flash"),
        ("critic", "deepseek-v4-pro"),
    ]
    if len(traces) == 3:
        expected.append(("repair", "deepseek-v4-pro"))
    for raw_trace, identity in zip(traces, expected, strict=True):
        _validate_trace(raw_trace, identity)
    repair_count = result.get("repair_count")
    if not _is_int(repair_count) or repair_count != len(traces) - 2:
        _fail("MODEL_TRACE_INVALID")
    if repair_count == 1:
        if result.get("critic") is not None:
            _fail("MODEL_TRACE_INVALID")
    else:
        _validate_critic(result.get("critic"), batch, pack)
    return len(traces)


def _field_pairs(
    raw_pairs: object,
    *,
    value_code: str,
) -> tuple[dict[str, list[object]], int]:
    pairs = _array(raw_pairs, value_code)
    mapped: dict[str, list[object]] = {}
    total = 0
    for raw_pair in pairs:
        pair = _array(raw_pair, value_code)
        if len(pair) != 2 or not isinstance(pair[0], str):
            _fail(value_code)
        values = _array(pair[1], value_code)
        if pair[0] in mapped:
            _fail(value_code)
        mapped[pair[0]] = values
        total += len(values)
    if set(mapped) != set(_FMEA_FIELDS):
        _fail(value_code)
    return mapped, total


def _field_support(raw_pairs: object) -> dict[str, str]:
    pairs = _array(raw_pairs, "FMEA_SUPPORT_INVALID")
    mapped: dict[str, str] = {}
    allowed = {
        "supported",
        "partially_supported",
        "contradicted",
        "not_supported",
    }
    for raw_pair in pairs:
        pair = _array(raw_pair, "FMEA_SUPPORT_INVALID")
        if (
            len(pair) != 2
            or not isinstance(pair[0], str)
            or not isinstance(pair[1], str)
            or pair[1] not in allowed
            or pair[0] in mapped
        ):
            _fail("FMEA_SUPPORT_INVALID")
        mapped[pair[0]] = pair[1]
    if set(mapped) != set(_FMEA_FIELDS):
        _fail("FMEA_SUPPORT_INVALID")
    return mapped


def _domain_row(raw_row: dict[str, object], pack: _EvidencePackView) -> _RowView:
    try:
        row = _FMEA_CODEC.decode_row(orjson.dumps(raw_row).decode("utf-8"))
        policies = import_module("core_domain.fmea.policies")
        validate_row_evidence = cast(
            "Callable[[_RowView, _EvidencePackView], None]",
            policies.validate_row_evidence,
        )
        validate_row_evidence(row, pack)
    except Exception:
        _fail("FMEA_ROW_INVALID")
    return row


def _claim_matches_field(field_name: str, target: str) -> bool:
    pointer = _FMEA_POINTERS[field_name]
    return target == pointer or (field_name in _ARRAY_PAYLOAD_FIELDS and target.startswith(pointer + "/"))


def _expected_support(
    candidate: _CandidateView,
    raw_critic: object,
    repair_count: int,
) -> dict[str, str]:
    if repair_count:
        return dict.fromkeys(_FMEA_FIELDS, "not_supported")
    critic = _object(raw_critic, "MODEL_TRACE_INVALID")
    findings = _array(critic.get("findings"), "MODEL_TRACE_INVALID")
    priority = {
        "supported": 0,
        "partially_supported": 1,
        "contradicted": 2,
        "not_supported": 3,
    }
    result: dict[str, str] = {}
    for field_name in _FMEA_FIELDS:
        statuses = [
            cast("str", finding["support"])
            for raw_finding in findings
            if (finding := _object(raw_finding, "MODEL_TRACE_INVALID")).get("candidate_id")
            == candidate.candidate_id
            and isinstance(finding.get("target"), str)
            and _claim_matches_field(field_name, cast("str", finding["target"]))
        ]
        result[field_name] = (
            max(statuses, key=priority.__getitem__)
            if statuses
            else "not_supported"
        )
    return result


def _expected_claim_status(
    candidate: _CandidateView,
    support: dict[str, str],
    repair_count: int,
) -> str:
    priority = {
        "known": 0,
        "not_applicable": 1,
        "unknown": 2,
        "insufficient_evidence": 3,
        "conflict": 4,
    }
    states = [cast("str", _state_value(claim)) for claim in candidate.claims]
    active = max(states, key=priority.__getitem__) if states else "unknown"
    if "contradicted" in support.values():
        active = max((active, "conflict"), key=priority.__getitem__)
    if repair_count or {"not_supported", "partially_supported"} & set(support.values()):
        active = max((active, "insufficient_evidence"), key=priority.__getitem__)
    return active


def _validate_candidate_row(
    candidate: _CandidateView,
    row: _RowView,
    observed_support: dict[str, str],
    *,
    critic: object,
    repair_count: int,
) -> None:
    payload = _object(candidate.payload, "CANDIDATE_BATCH_INVALID")
    if row.failure_mode != payload.get("failure_mode"):
        _fail("FMEA_CANDIDATE_MISMATCH")
    for field_name in _ARRAY_PAYLOAD_FIELDS:
        values = _array(payload.get(field_name), "CANDIDATE_BATCH_INVALID")
        if getattr(row, field_name) != tuple(values):
            _fail("FMEA_CANDIDATE_MISMATCH")
    expected_evidence = {
        field_name: tuple(
            sorted(
                {
                    evidence_id
                    for claim in candidate.claims
                    if _claim_matches_field(field_name, claim.target)
                    for evidence_id in claim.evidence_ids
                }
            )
        )
        for field_name in _FMEA_FIELDS
    }
    if dict(row.field_evidence) != expected_evidence:
        _fail("FMEA_CANDIDATE_MISMATCH")
    expected_support = _expected_support(candidate, critic, repair_count)
    if observed_support != expected_support:
        _fail("FMEA_CANDIDATE_MISMATCH")
    if getattr(row.claim_status, "value", None) != _expected_claim_status(
        candidate,
        expected_support,
        repair_count,
    ):
        _fail("FMEA_CANDIDATE_MISMATCH")


def _validate_row(
    raw_row: object,
    *,
    pack: _EvidencePackView,
    analysis: _AnalysisView,
) -> tuple[int, _RowView, dict[str, str]]:
    row = _object(raw_row, "FMEA_ROW_INVALID")
    _exact_keys(row, _ROW_KEYS, "FMEA_ROW_INVALID")
    if row.get("risk_assessment") is not None:
        _fail("FMEA_SCOPE_VIOLATION")
    if row.get("review_status") != "suggested" or row.get("publication_status") != "unpublished":
        _fail("FMEA_WORKFLOW_STATE_INVALID")
    if row.get("analysis_id") != analysis.analysis_id or row.get("evidence_pack_id") != pack.pack_id:
        _fail("FMEA_ROW_INVALID")
    if row.get("claim_status") not in {
        "known",
        "unknown",
        "insufficient_evidence",
        "conflict",
        "not_applicable",
    }:
        _fail("FMEA_ROW_INVALID")
    evidence, evidence_count = _field_pairs(
        row.get("field_evidence"),
        value_code="FMEA_EVIDENCE_INVALID",
    )
    support = _field_support(row.get("field_support"))
    allowed_ids = {ref.evidence_id for ref in pack.refs}
    for evidence_ids in evidence.values():
        if any(not isinstance(item, str) or item not in allowed_ids for item in evidence_ids):
            _fail("FMEA_EVIDENCE_OUTSIDE_PACK")
    if evidence_count == 0:
        _fail("FMEA_EVIDENCE_INVALID")
    return evidence_count, _domain_row(row, pack), support


def _validate_fmea(
    result: dict[str, object],
    *,
    pack: _EvidencePackView,
    analysis: _AnalysisView,
    batch: _BatchView,
) -> tuple[int, int]:
    fmea = _object(result.get("fmea"), "FMEA_RESULT_INVALID")
    _exact_keys(fmea, {"persisted", "needs_review", "rows", "issues"}, "FMEA_RESULT_INVALID")
    if fmea.get("persisted") is not False:
        _fail("FMEA_PERSISTENCE_FORBIDDEN")
    if not isinstance(fmea.get("needs_review"), bool):
        _fail("FMEA_RESULT_INVALID")
    _array(fmea.get("issues"), "FMEA_RESULT_INVALID")
    rows = _array(fmea.get("rows"), "FMEA_RESULT_INVALID")
    if not rows or len(rows) != len(batch.candidates):
        _fail("FMEA_RESULT_INVALID")
    validated_rows = [
        _validate_row(row, pack=pack, analysis=analysis)
        for row in rows
    ]
    total_evidence = sum(evidence_count for evidence_count, _, _ in validated_rows)
    candidates = sorted(batch.candidates, key=lambda candidate: candidate.candidate_id)
    repair_count = cast("int", result["repair_count"])
    for candidate, (_, row, support) in zip(candidates, validated_rows, strict=True):
        _validate_candidate_row(
            candidate,
            row,
            support,
            critic=result.get("critic"),
            repair_count=repair_count,
        )
    return len(rows), total_evidence


def verify_acceptance_output(
    output_payload: bytes | str,
    evidence_pack_payload: bytes | str,
    analysis_payload: bytes | str,
    request_payload: bytes | str,
) -> AcceptanceSummary:
    """Verify one live output without retaining evidence or provider text."""

    output_text = _bounded_text(output_payload, _MAX_OUTPUT_BYTES, "OUTPUT_INVALID")
    pack, analysis, request = _decode_inputs(
        evidence_pack_payload,
        analysis_payload,
        request_payload,
    )
    output = _json_object(output_text, "OUTPUT_JSON_INVALID")
    _validate_privacy(output_text, output, pack, request)
    if _walk_keys(output) & _SCOPE_FORBIDDEN_KEYS:
        _fail("FMEA_SCOPE_VIOLATION")
    _exact_keys(
        output,
        {"schema_version", "status", "run_id", "result", "error"},
        "OUTPUT_SHAPE_INVALID",
    )
    status = output.get("status")
    if output.get("schema_version") != _GENERATION_SCHEMA:
        _fail("OUTPUT_SCHEMA_INVALID")
    if status not in {"succeeded", "needs_review"}:
        _fail("OUTPUT_STATUS_INVALID")
    if output.get("run_id") != request["run_id"]:
        _fail("OUTPUT_RUN_ID_MISMATCH")
    if output.get("error") is not None:
        _fail("OUTPUT_ERROR_PRESENT")
    result = _object(output.get("result"), "RESULT_SHAPE_INVALID")
    _exact_keys(result, _RESULT_KEYS, "RESULT_SHAPE_INVALID")
    candidate_count, batch = _validate_batch(result, pack)
    trace_count = _validate_traces(result, batch, pack)
    row_count, evidence_count = _validate_fmea(
        result,
        pack=pack,
        analysis=analysis,
        batch=batch,
    )
    return AcceptanceSummary(
        status=cast("str", status),
        candidate_count=candidate_count,
        row_count=row_count,
        trace_count=trace_count,
        evidence_link_count=evidence_count,
    )


def _read_bounded(path_value: str, maximum: int, code: str) -> bytes:
    if path_value == "-":
        try:
            payload = sys.stdin.buffer.read(maximum + 1)
        except OSError:
            _fail(code)
        if len(payload) > maximum:
            _fail(code)
        return payload
    try:
        path = Path(path_value)
        if path.stat().st_size > maximum:
            _fail(code)
        payload = path.read_bytes()
    except OSError:
        _fail(code)
    if len(payload) > maximum:
        _fail(code)
    return payload


def _parser() -> argparse.ArgumentParser:
    parser = _SafeArgumentParser(allow_abbrev=False, add_help=False)
    parser.add_argument("--output", required=True)
    parser.add_argument("--pack", required=True)
    parser.add_argument("--analysis", required=True)
    parser.add_argument("--request", required=True)
    return parser


def _summary_payload(summary: AcceptanceSummary) -> dict[str, object]:
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
            "message": "Structured-generation acceptance verification failed.",
        },
    }


def _emit(payload: dict[str, object]) -> None:
    sys.stdout.write(orjson.dumps(payload).decode("utf-8") + "\n")


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        summary = verify_acceptance_output(
            _read_bounded(args.output, _MAX_OUTPUT_BYTES, "OUTPUT_INVALID"),
            _read_bounded(args.pack, _MAX_PACK_BYTES, "EVIDENCE_PACK_INVALID"),
            _read_bounded(args.analysis, _MAX_ANALYSIS_BYTES, "ANALYSIS_INVALID"),
            _read_bounded(args.request, _MAX_REQUEST_BYTES, "REQUEST_INVALID"),
        )
    except _CliUsageError:
        _emit(_error_payload("CLI_USAGE_INVALID"))
        return 2
    except AcceptanceVerificationError as error:
        _emit(_error_payload(error.code))
        return 2
    except Exception:
        _emit(_error_payload("INTERNAL_ERROR"))
        return 1
    _emit(_summary_payload(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "SCHEMA_VERSION",
    "AcceptanceSummary",
    "AcceptanceVerificationError",
    "main",
    "verify_acceptance_output",
]
