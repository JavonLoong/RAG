"""Provider-neutral, bounded model suggestions for imported template mappings."""

# TRY003 is consistent with the stable ReviewError boundary used by FMEA.
# ruff: noqa: TRY003

from __future__ import annotations

import json
import re
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from hashlib import sha256
from math import isfinite
from pathlib import Path
from typing import Any, Protocol

from core_domain.fmea.template_migration import TemplateDraft, TemplatePatchCandidate, TemplatePatchStatus
from core_domain.fmea.value_objects import EvidencePack, EvidenceRef
from core_domain.structured_generation import GenerationRunStatus, GenerationStage, StructuredGenerationError
from core_domain.structured_output import StructuredOutputError
from fmea_application.assistance_contracts import AssistanceKind, AssistanceSuggestion
from fmea_application.ports import TemplatePatchRequest
from fmea_application.review_errors import ReviewError
from fmea_application.template_patch_contracts import (
    TemplatePatchSuggestion,
    candidate_payload,
    normalize_source_mapping_key,
)


class TemplatePatchModelGateway(Protocol):
    """A provider-neutral model boundary; implementations may be local or remote."""

    def generate(self, request: Mapping[str, object]) -> object: ...


_PATH = re.compile(r"^/(?:fields|mappings)/[a-z][a-z0-9_.-]{0,127}$")
_FORBIDDEN_TEXT = re.compile(
    r"(?i)(?:https?://|file://|\\\\|(?:[a-z]:[\\/])|\.\.|\b(?:exec|eval|import|lambda|select|insert|update|delete|drop|curl|wget|powershell|bash)\b|(?:api[_ -]?key|password|secret|authorization|token))"
)
_SHA = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$")
_MAX_DIFF = 64
_MAX_VALUE_DEPTH = 4
_MAX_VALUE_NODES = 512
_MAX_MODEL_INPUT_BYTES = 3_500
_MAX_MODEL_RESPONSE_BYTES = 64 * 1024
_MAX_EVIDENCE_ID_LENGTH = 256
_MAX_PROJECTED_EVIDENCE_REFS = 8
_MAX_PROJECTED_QUOTE_CHARS = 256
_MODEL_LABEL = re.compile(r"^[a-z][a-z0-9_.-]{0,127}$")
_TEMPLATE_ID = "fmea-template-patch"
_TEMPLATE_VERSION = "1.0.0"
_UNAVAILABLE_CODES = {
    "MODEL_AUTHENTICATION_FAILED",
    "MODEL_CONFIGURATION_INVALID",
    "MODEL_RATE_LIMITED",
    "MODEL_REQUEST_REJECTED",
    "MODEL_UPSTREAM_UNAVAILABLE",
    "MODEL_TIMEOUT",
    "MODEL_TOTAL_TIMEOUT",
}


@dataclass(frozen=True, slots=True)
class TemplatePatchGatewayResult:
    """Provider payload plus hashes from the final model trace."""

    payload: Mapping[str, object]
    model_hash: str
    prompt_hash: str

    def __post_init__(self) -> None:
        if not isinstance(self.payload, Mapping):
            raise TypeError("payload must be a mapping")
        if re.fullmatch(r"[0-9a-f]{64}", self.model_hash) is None:
            raise ValueError("model_hash must be lowercase SHA-256")
        if re.fullmatch(r"[0-9a-f]{64}", self.prompt_hash) is None:
            raise ValueError("prompt_hash must be lowercase SHA-256")


def _timestamp(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("created_at must be an ISO-8601 timestamp") from exc
    offset = parsed.utcoffset()
    if parsed.tzinfo is None or offset is None or offset.total_seconds() != 0:
        raise ValueError("created_at must be an ISO-8601 UTC timestamp")
    return value


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _invalid(message: str) -> ReviewError:
    return ReviewError("FMEA_MODEL_SUGGESTION_INVALID", message)


def _safe_generation_error(error: StructuredGenerationError) -> ReviewError:
    if error.code in _UNAVAILABLE_CODES:
        return ReviewError(
            "FMEA_MODEL_SUGGESTION_UNAVAILABLE",
            "the template mapping model is temporarily unavailable",
            retryable=True,
        )
    return _invalid("the template mapping model returned an invalid suggestion")


def _safe_hash(value: str, field_name: str) -> str:
    if _SHA.fullmatch(value) is None:
        raise _invalid(f"{field_name} provenance is invalid")
    return value


def _validate_value(  # noqa: C901
    value: object, *, depth: int = 0, nodes: list[int] | None = None
) -> object:
    budget = [0] if nodes is None else nodes
    budget[0] += 1
    if budget[0] > _MAX_VALUE_NODES or depth > _MAX_VALUE_DEPTH:
        raise _invalid("patch value exceeds the bounded declarative limit")
    if value is None or isinstance(value, bool | int):
        return value
    if isinstance(value, float):
        if not isfinite(value):
            raise _invalid("patch values must be finite")
        return value
    if isinstance(value, str):
        if len(value) > 4096 or _FORBIDDEN_TEXT.search(value):
            raise _invalid("patch value contains unsupported executable or private content")
        return value
    if isinstance(value, Mapping):
        if len(value) > 32:
            raise _invalid("patch value mapping is too large")
        result: dict[str, object] = {}
        for key, child in sorted(value.items(), key=lambda pair: str(pair[0])):
            if not isinstance(key, str) or not key.strip() or _FORBIDDEN_TEXT.search(key):
                raise _invalid("patch value contains an unsupported key")
            result[key] = _validate_value(child, depth=depth + 1, nodes=budget)
        return result
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        if len(value) > 64:
            raise _invalid("patch value sequence is too large")
        return [_validate_value(child, depth=depth + 1, nodes=budget) for child in value]
    raise _invalid("patch values must be declarative JSON values")


def _validate_diff(value: object) -> tuple[Mapping[str, object], ...]:
    if isinstance(value, str | bytes) or not isinstance(value, Sequence):
        raise _invalid("patch diff must be a bounded array")
    if len(value) > _MAX_DIFF:
        raise _invalid("patch diff exceeds the bounded limit")
    paths: set[str] = set()
    normalized: list[Mapping[str, object]] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise _invalid("patch diff contains unknown or missing fields")
        operation = item.get("op")
        path = item.get("path")
        if operation not in {"add", "replace", "remove"} or not isinstance(path, str) or _PATH.fullmatch(path) is None:
            raise _invalid("patch diff is not an allowlisted declarative mapping")
        expected_keys = {"op", "path"} if operation == "remove" else {"op", "path", "value"}
        if set(item) != expected_keys:
            raise _invalid("patch diff contains unknown or missing fields")
        if path in paths:
            raise _invalid("patch diff paths must be unique")
        if operation != "remove" and "value" not in item:
            raise _invalid("patch add and replace operations require a value")
        paths.add(path)
        entry: dict[str, object] = {"op": operation, "path": path}
        if operation != "remove":
            entry["value"] = _validate_value(item["value"])
        normalized.append(entry)
    return tuple(normalized)


def _normalize_evidence_ids(value: object) -> tuple[str, ...]:
    if isinstance(value, str | bytes) or not isinstance(value, Sequence):
        raise _invalid("patch evidence IDs must be an array")
    if len(value) > 128 or any(
        not isinstance(item, str) or not item.strip() or len(item.strip()) > _MAX_EVIDENCE_ID_LENGTH for item in value
    ):
        raise _invalid("patch evidence IDs are invalid")
    result = tuple(item.strip() for item in value)
    if len(result) != len(set(result)):
        raise _invalid("patch evidence IDs must be unique")
    return result


def _projected_evidence(request: TemplatePatchRequest) -> tuple[tuple[str, EvidenceRef], ...]:
    raw_refs = tuple(request.evidence_pack.refs)
    if any(not isinstance(ref.evidence_id, str) for ref in raw_refs):
        raise _invalid("template mapping evidence identity is invalid")
    refs = tuple(sorted(raw_refs, key=lambda item: item.evidence_id))
    if len(refs) > _MAX_PROJECTED_EVIDENCE_REFS:
        raise _invalid("template mapping evidence projection exceeds the bounded limit")
    projected: list[tuple[str, EvidenceRef]] = []
    for index, ref in enumerate(refs, start=1):
        if (
            not isinstance(ref.evidence_id, str)
            or not ref.evidence_id.strip()
            or ref.evidence_id != ref.evidence_id.strip()
            or len(ref.evidence_id) > _MAX_EVIDENCE_ID_LENGTH
            or _FORBIDDEN_TEXT.search(ref.evidence_id)
            or not isinstance(ref.source_type, str)
            or _MODEL_LABEL.fullmatch(ref.source_type) is None
            or not isinstance(ref.source_trust, str)
            or _MODEL_LABEL.fullmatch(ref.source_trust) is None
            or not isinstance(ref.quote, str)
            or not isinstance(ref.normalized_quote, str)
            or not isinstance(ref.is_primary, bool)
        ):
            raise _invalid("template mapping evidence identity is invalid")
        projected.append((f"ref-{index:03d}", ref))
    return tuple(projected)


def _request_projection(request: TemplatePatchRequest) -> Mapping[str, object]:
    draft = request.draft
    refs = _projected_evidence(request)
    projection: Mapping[str, object] = {
        "untrusted_import_headers": {
            "delimiter": "BEGIN_UNTRUSTED_IMPORT_HEADERS/END_UNTRUSTED_IMPORT_HEADERS",
            "source_type": draft.source_type,
            "identified_fields": list(draft.identified_fields),
            "unknown_headers": [
                {
                    "source_header": item,
                    "normalized_source_key": normalize_source_mapping_key(item),
                }
                for item in draft.unknown_fields
            ],
            "ambiguous_headers": [
                {
                    "source_header": item,
                    "normalized_source_key": normalize_source_mapping_key(item),
                }
                for item in draft.ambiguous_fields
            ],
            "proposed_fields": [
                {
                    "source_header": item.source_key,
                    "normalized_source_key": normalize_source_mapping_key(item.source_key),
                    "target_field": item.target_field,
                }
                for item in draft.proposed_fields
            ],
        },
        "allowed_output": {
            "paths": ["/fields/<field_id>", "/mappings/<normalized_source_header>"],
            "operations": ["add", "replace", "remove"],
        },
        "untrusted_evidence": [
            {
                "evidence_id": alias,
                "source_type": ref.source_type,
                "source_trust": ref.source_trust,
                "is_primary": ref.is_primary,
                "quote": ref.quote[:_MAX_PROJECTED_QUOTE_CHARS],
                "truncated": len(ref.quote) > _MAX_PROJECTED_QUOTE_CHARS,
            }
            for alias, ref in refs
        ],
        "rule": "Return only declarative field mapping diff and evidence IDs; never return executable content or authority decisions.",
    }
    try:
        serialized = json.dumps(projection, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise _invalid("template mapping projection is invalid") from exc
    if len(serialized) > _MAX_MODEL_INPUT_BYTES:
        raise _invalid("template mapping projection exceeds the bounded limit")
    return projection


class TemplatePatchGenerator:
    """Decode one provider-neutral model response into an unapplied suggestion."""

    def __init__(self, gateway: TemplatePatchModelGateway, *, clock: Callable[[], str] = _now) -> None:
        self._gateway = gateway
        self._clock = clock

    def suggest(self, request: TemplatePatchRequest) -> TemplatePatchSuggestion:  # noqa: C901
        if not isinstance(request, TemplatePatchRequest):
            raise _invalid("template patch request is invalid")
        if not isinstance(request.draft, TemplateDraft):
            raise _invalid("template patch draft is invalid")
        if request.draft.workspace_id.strip() == "":
            raise _invalid("template patch draft workspace is invalid")
        try:
            projection = _request_projection(request)
            response = self._gateway.generate(projection)
        except ReviewError:
            raise
        except Exception as exc:
            raise ReviewError(
                "FMEA_MODEL_SUGGESTION_UNAVAILABLE",
                "the template mapping model is temporarily unavailable",
                retryable=True,
            ) from exc
        gateway_result = response if isinstance(response, TemplatePatchGatewayResult) else None
        if gateway_result is not None:
            response = gateway_result.payload
        try:
            response_bytes = json.dumps(
                response, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise _invalid("template mapping model returned invalid JSON") from exc
        if len(response_bytes) > _MAX_MODEL_RESPONSE_BYTES:
            raise _invalid("template mapping model response exceeds the bounded limit")
        if not isinstance(response, Mapping) or set(response) != {"diff", "evidence_ids"}:
            raise _invalid("template mapping model returned invalid, unknown, or missing fields")
        diff = _validate_diff(response["diff"])
        projected_ids = _normalize_evidence_ids(response["evidence_ids"])
        evidence_aliases = {alias: ref.evidence_id for alias, ref in _projected_evidence(request)}
        if not set(projected_ids).issubset(evidence_aliases):
            raise _invalid("template mapping evidence is outside the EvidencePack")
        evidence_ids = tuple(evidence_aliases[alias] for alias in projected_ids)
        created_at = request.created_at or self._clock()
        try:
            candidate = TemplatePatchCandidate(
                patch_id=request.patch_id,
                draft_id=request.draft.draft_id,
                input_template_version=request.input_template_version,
                target_template_id=request.target_template_id,
                target_template_version=request.target_template_version,
                target_template_hash=_safe_hash(request.target_template_hash, "target template"),
                domain_pack_id=request.domain_pack_id,
                domain_pack_version=request.domain_pack_version,
                domain_pack_hash=_safe_hash(request.domain_pack_hash, "DomainPack"),
                evidence_pack_id=request.evidence_pack_id,
                evidence_pack_hash=_safe_hash(request.evidence_pack_hash, "EvidencePack"),
                run_id=request.run_id,
                trace_id=request.trace_id,
                model_version=request.model_version,
                prompt_version=request.prompt_version,
                diff=diff,
                evidence_ids=evidence_ids,
                status=TemplatePatchStatus.SUGGESTED,
                created_at=created_at,
            )
        except ReviewError:
            raise
        except (TypeError, ValueError) as exc:
            raise _invalid("template mapping provenance or candidate is invalid") from exc
        model_hash = (
            gateway_result.model_hash
            if gateway_result is not None
            else sha256(request.model_version.encode("utf-8")).hexdigest()
        )
        prompt_hash = (
            gateway_result.prompt_hash
            if gateway_result is not None
            else sha256(request.prompt_version.encode("utf-8")).hexdigest()
        )
        try:
            envelope: AssistanceSuggestion[object] = AssistanceSuggestion(
                suggestion_id=f"template-patch-suggestion-{candidate.patch_id}",
                kind=AssistanceKind.TEMPLATE_FIELD_MAPPING,
                workspace_id=request.draft.workspace_id,
                target_type="template_draft",
                target_id=request.draft.draft_id,
                target_record_version=request.target_record_version,
                evidence_pack_ids=(candidate.evidence_pack_id,),
                payload=candidate_payload(candidate),
                evidence_ids=candidate.evidence_ids,
                model_hash=model_hash,
                prompt_hash=prompt_hash,
                run_id=candidate.run_id,
                trace_id=candidate.trace_id,
                domain_pack_id=candidate.domain_pack_id,
                domain_pack_version=candidate.domain_pack_version,
                template_id=candidate.target_template_id,
                template_version=candidate.target_template_version,
                created_at=created_at,
            )
            return TemplatePatchSuggestion(candidate=candidate, envelope=envelope)
        except ReviewError:
            raise
        except (TypeError, ValueError) as exc:
            raise _invalid("template mapping suggestion contract is invalid") from exc


def _compose_service(source_path: Path, registry_root: Path | None = None) -> Any:
    from structured_generation_application import StructuredGenerationPipeline, StructuredGenerationService
    from structured_generation_infrastructure import (
        StrictCandidateBatchCodec,
        StrictCriticReportCodec,
        build_deepseek_gateway_from_env,
    )
    from structured_output_application import StructuredCandidateValidator, TemplateCompiler
    from structured_output_infrastructure import Draft202012SchemaAdapter, FileTemplateRegistry, load_template_source

    schema = Draft202012SchemaAdapter()
    compiled = TemplateCompiler(schema_validator=schema, source_loader=load_template_source).compile_path(source_path)
    if compiled.metadata.template_id != _TEMPLATE_ID or compiled.metadata.version != _TEMPLATE_VERSION:
        raise _invalid("built-in template patch identity is invalid")
    registry = FileTemplateRegistry(registry_root or Path(tempfile.gettempdir()) / "fmea-assistance-template-registry")
    try:
        stored = registry.get(_TEMPLATE_ID, _TEMPLATE_VERSION)
    except StructuredOutputError as exc:
        if exc.code != "TEMPLATE_NOT_FOUND":
            raise _invalid("template patch registry is invalid") from exc
        registry.register(compiled, source_path.read_bytes(), source_path.suffix.lower())
    else:
        if stored.template_hash != compiled.template_hash:
            raise _invalid("template patch registry is stale")
    return StructuredGenerationService(
        registry=registry,
        pipeline=StructuredGenerationPipeline(
            gateway=build_deepseek_gateway_from_env(),
            batch_codec=StrictCandidateBatchCodec(),
            critic_codec=StrictCriticReportCodec(),
            candidate_validator=StructuredCandidateValidator(schema),
        ),
    )


def _structured_candidate(result: Any, *, evidence_pack_id: str) -> tuple[Mapping[str, object], Any]:
    accepted = result.status is GenerationRunStatus.SUCCEEDED or (
        result.status is GenerationRunStatus.NEEDS_REVIEW and result.repair_count == 1
    )
    if not accepted or result.batch is None or result.repair_count not in {0, 1}:
        raise _invalid("the template mapping model did not return one reviewable candidate")
    batch = result.batch
    if (
        batch.template_id != _TEMPLATE_ID
        or batch.template_version != _TEMPLATE_VERSION
        or batch.evidence_pack_id != evidence_pack_id
        or len(batch.candidates) != 1
    ):
        raise _invalid("the template mapping candidate identity is invalid")
    successful = tuple(trace for trace in result.traces if trace.response_hash is not None and trace.error_code is None)
    if (
        not successful
        or successful[0].stage is not GenerationStage.GENERATE
        or successful[0].model_id != "deepseek-v4-flash"
    ):
        raise _invalid("the template mapping generation trace is invalid")
    final_stage = GenerationStage.REPAIR if result.repair_count == 1 else GenerationStage.CRITIC
    final = tuple(trace for trace in successful if trace.stage is final_stage and trace.model_id == "deepseek-v4-pro")
    if len(final) != 1:
        raise _invalid("the template mapping final review trace is invalid")
    payload = batch.candidates[0].payload
    if not isinstance(payload, Mapping):
        raise _invalid("the template mapping candidate payload is invalid")
    return payload, final[0]


class StructuredTemplatePatchGenerator:
    """Adapt the shared Flash -> Pro structured pipeline to template patches."""

    def __init__(self, service: Any, *, clock: Callable[[], str] = _now) -> None:
        self._service = service
        self._clock = clock

    @staticmethod
    def projection_pack_id(request: TemplatePatchRequest) -> str:
        digest = sha256(f"{request.patch_id}:{request.run_id}".encode()).hexdigest()[:32]
        return f"template-patch-projection-{digest}"

    @classmethod
    def _projection_pack(cls, request: TemplatePatchRequest) -> EvidencePack:
        workspace_id = "template-patch-model-projection"
        refs = tuple(
            replace(
                ref,
                evidence_id=alias,
                workspace_id=workspace_id,
                document_id=f"redacted-document-{index}",
                document_version="redacted",
                content_hash=sha256(f"content:{index}".encode()).hexdigest(),
                locator=f"evidence:{alias}",
                quote=ref.quote[:_MAX_PROJECTED_QUOTE_CHARS],
                normalized_quote=ref.normalized_quote[:_MAX_PROJECTED_QUOTE_CHARS],
                evidence_hash=sha256(f"evidence:{index}".encode()).hexdigest(),
                acl_scope=("model-projection",),
            )
            for index, (alias, ref) in enumerate(_projected_evidence(request))
        )
        return EvidencePack.build(
            pack_id=cls.projection_pack_id(request),
            workspace_id=workspace_id,
            acl_scope=("model-projection",),
            versions=request.evidence_pack.versions,
            refs=refs,
            created_at=request.evidence_pack.created_at,
            expires_at=request.evidence_pack.expires_at,
        )

    def suggest(self, request: TemplatePatchRequest) -> TemplatePatchSuggestion:
        if not isinstance(request, TemplatePatchRequest):
            raise _invalid("template patch request is invalid")
        try:
            projection = _request_projection(request)
            model_pack = self._projection_pack(request)
            result = self._service.run(
                run_id=request.run_id,
                task=json.dumps(projection, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                template_id=_TEMPLATE_ID,
                version=_TEMPLATE_VERSION,
                evidence_pack=model_pack,
            )
            payload, trace = _structured_candidate(result, evidence_pack_id=model_pack.pack_id)
            gateway = _StaticGateway(
                TemplatePatchGatewayResult(
                    payload=payload,
                    model_hash=trace.response_hash,
                    prompt_hash=trace.prompt_hash,
                )
            )
            return TemplatePatchGenerator(gateway, clock=self._clock).suggest(request)
        except ReviewError:
            raise
        except StructuredGenerationError as exc:
            raise _safe_generation_error(exc) from exc
        except (KeyError, TypeError, ValueError) as exc:
            raise _invalid("the template mapping model returned an invalid suggestion") from exc
        except Exception as exc:
            raise ReviewError(
                "FMEA_MODEL_SUGGESTION_UNAVAILABLE",
                "the template mapping model is temporarily unavailable",
                retryable=True,
            ) from exc


@dataclass(frozen=True, slots=True)
class _StaticGateway:
    result: TemplatePatchGatewayResult

    def generate(self, request: Mapping[str, object]) -> TemplatePatchGatewayResult:
        return self.result


class EnvironmentTemplatePatchGenerator:
    """Lazily compose the configured DeepSeek Flash -> Pro mapping pipeline."""

    def __init__(
        self,
        *,
        registry_root: Path | None = None,
        template_path: Path | None = None,
        clock: Callable[[], str] = _now,
    ) -> None:
        self._registry_root = registry_root
        self._template_path = template_path or (
            Path(__file__).resolve().parents[1] / "templates" / "examples" / "fmea-template-patch.yaml"
        )
        self._clock = clock

    def suggest(self, request: TemplatePatchRequest) -> TemplatePatchSuggestion:
        try:
            return StructuredTemplatePatchGenerator(
                _compose_service(self._template_path, self._registry_root),
                clock=self._clock,
            ).suggest(request)
        except ReviewError:
            raise
        except Exception as exc:
            raise ReviewError(
                "FMEA_MODEL_SUGGESTION_UNAVAILABLE",
                "the template mapping model is temporarily unavailable",
                retryable=True,
            ) from exc


__all__ = [
    "EnvironmentTemplatePatchGenerator",
    "StructuredTemplatePatchGenerator",
    "TemplatePatchGatewayResult",
    "TemplatePatchGenerator",
    "TemplatePatchModelGateway",
    "TemplatePatchRequest",
]
