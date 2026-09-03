"""Bounded narrative assistance over the shared structured-generation pipeline."""

# The generator is intentionally a provider adapter. It does not persist a
# suggestion and it never receives the workspace's private source objects.
# ruff: noqa: TRY003

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Protocol

from core_domain.fmea.value_objects import EvidencePack, EvidenceRef, VersionSet
from core_domain.structured_generation import (
    GenerationBudget,
    GenerationRunStatus,
    GenerationStage,
    StructuredGenerationError,
)
from core_domain.structured_output import (
    CompiledTemplate,
)
from fmea_application.export_service import (
    ExportNarrativeClaim,
    ExportNarrativeDraft,
    ExportNarrativeGenerationResult,
    ExportNarrativeRequest,
)

_HASH = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$")
_ROOT_KEYS = frozenset({"title", "sections", "claims"})
_SECTION_KEYS = frozenset({"section_id", "title", "body", "claim_ids"})
_CLAIM_KEYS = frozenset({"claim_id", "text", "evidence_ids"})
_NARRATIVE_TEMPLATE_ID = "fmea-export-narrative"
_NARRATIVE_TEMPLATE_VERSION = "1.0.0"
_NARRATIVE_TASK_MAX_CHARACTERS = 4_000
_NARRATIVE_TASK_MAX_UTF8_BYTES = 4_000
_NARRATIVE_CONTEXT_ITEM_LIMITS = {"rows": 4, "evidence": 12, "unresolved": 4}
_NARRATIVE_CONTEXT_PRIORITY = ("evidence", "unresolved", "rows")
_UNAVAILABLE_CODES = {
    "MODEL_AUTHENTICATION_FAILED",
    "MODEL_CONFIGURATION_INVALID",
    "MODEL_RATE_LIMITED",
    "MODEL_REQUEST_REJECTED",
    "MODEL_UPSTREAM_UNAVAILABLE",
    "MODEL_TIMEOUT",
    "MODEL_TOTAL_TIMEOUT",
}


class ExportNarrativeGenerationError(ValueError):
    """Stable, public-safe narrative generator error."""

    _CODES = frozenset({"FMEA_EXPORT_NARRATIVE_INVALID", "FMEA_EXPORT_NARRATIVE_UNAVAILABLE"})

    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        if code not in self._CODES:
            raise ValueError("unsupported narrative error code")
        self.code = code
        self.retryable = retryable
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True, slots=True)
class ExportNarrativePipelineResult:
    """Provider-neutral output of either a fake or shared generation pipeline."""

    payload: object
    evidence_refs: tuple[str, ...]
    model_hash: str
    prompt_hash: str
    run_id: str
    trace_id: str
    status: str
    repair_count: int = 0
    stages: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class _BoundedNarrativeContext:
    """Canonical task plus the exact projection identities exposed to the model."""

    task: str
    projection: Mapping[str, object]
    evidence_refs: tuple[str, ...]


class ExportNarrativePipeline(Protocol):
    def run(self, request: ExportNarrativeRequest) -> ExportNarrativePipelineResult: ...


def _invalid(message: str) -> ExportNarrativeGenerationError:
    return ExportNarrativeGenerationError("FMEA_EXPORT_NARRATIVE_INVALID", message)


def _unavailable(message: str, *, retryable: bool = True) -> ExportNarrativeGenerationError:
    return ExportNarrativeGenerationError(
        "FMEA_EXPORT_NARRATIVE_UNAVAILABLE",
        message,
        retryable=retryable,
    )


def _hash(value: object, name: str) -> str:
    if not isinstance(value, str) or _HASH.fullmatch(value) is None:
        raise _invalid(f"{name} provenance is invalid")
    return value


def _text(value: object, name: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise _invalid(f"{name} is invalid")
    return value.strip()


def _string_ids(value: object, name: str, maximum: int) -> tuple[str, ...]:
    if isinstance(value, str | bytes) or not isinstance(value, Sequence):
        raise _invalid(f"{name} is invalid")
    if len(value) > maximum:
        raise _invalid(f"{name} exceeds its bounded limit")
    values = tuple(_text(item, name, 128) for item in value)
    if len(values) != len(set(values)):
        raise _invalid(f"{name} contains duplicate values")
    return values


def _json_safe(value: object) -> None:
    try:
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise _invalid("narrative pipeline output is not finite JSON") from exc


def _parse_draft(value: object, *, known_evidence: frozenset[str]) -> ExportNarrativeDraft:  # noqa: C901
    _json_safe(value)
    if not isinstance(value, Mapping) or set(value) != _ROOT_KEYS:
        raise _invalid("narrative output contains unknown or missing fields")
    raw_sections = value["sections"]
    raw_claims = value["claims"]
    if isinstance(raw_sections, str | bytes) or not isinstance(raw_sections, Sequence):
        raise _invalid("narrative sections are invalid")
    if isinstance(raw_claims, str | bytes) or not isinstance(raw_claims, Sequence):
        raise _invalid("narrative claims are invalid")
    if not 1 <= len(raw_sections) <= 8 or not 1 <= len(raw_claims) <= 32:
        raise _invalid("narrative sections or claims exceed the bounded limit")

    claims: list[ExportNarrativeClaim] = []
    for raw_claim in raw_claims:
        if not isinstance(raw_claim, Mapping) or set(raw_claim) != _CLAIM_KEYS:
            raise _invalid("narrative claim contains unknown or missing fields")
        try:
            evidence_ids = _string_ids(raw_claim["evidence_ids"], "claim evidence_ids", 8)
            if not set(evidence_ids).issubset(known_evidence):
                raise _invalid("narrative claim references evidence outside the safe projection")
            claims.append(
                ExportNarrativeClaim(
                    claim_id=_text(raw_claim["claim_id"], "claim_id", 128),
                    text=_text(raw_claim["text"], "claim text", 1000),
                    evidence_ids=evidence_ids,
                )
            )
        except ExportNarrativeGenerationError:
            raise
        except (TypeError, ValueError) as exc:
            raise _invalid("narrative claim is invalid") from exc

    sections: list[Any] = []
    known_claims = {claim.claim_id for claim in claims}
    for raw_section in raw_sections:
        if not isinstance(raw_section, Mapping) or set(raw_section) != _SECTION_KEYS:
            raise _invalid("narrative section contains unknown or missing fields")
        try:
            claim_ids = _string_ids(raw_section["claim_ids"], "section claim_ids", 32)
            if not set(claim_ids).issubset(known_claims):
                raise _invalid("narrative section references an unknown claim")
            from fmea_application.export_service import ExportNarrativeSection

            sections.append(
                ExportNarrativeSection(
                    section_id=_text(raw_section["section_id"], "section_id", 128),
                    title=_text(raw_section["title"], "section title", 256),
                    body=_text(raw_section["body"], "section body", 2500),
                    claim_ids=claim_ids,
                )
            )
        except ExportNarrativeGenerationError:
            raise
        except (TypeError, ValueError) as exc:
            raise _invalid("narrative section is invalid") from exc
    try:
        return ExportNarrativeDraft(
            title=_text(value["title"], "narrative title", 256),
            sections=tuple(sections),
            claims=tuple(claims),
        )
    except (TypeError, ValueError) as exc:
        raise _invalid("narrative draft is invalid") from exc


def _safe_projection_refs(request: ExportNarrativeRequest) -> frozenset[str]:
    projection = request.projection
    evidence = projection.get("evidence")
    if isinstance(evidence, str | bytes) or not isinstance(evidence, Sequence) or len(evidence) > 12:
        raise _invalid("narrative evidence projection is invalid")
    refs: list[str] = []
    for item in evidence:
        if not isinstance(item, Mapping) or set(item) != {"ref", "kind", "excerpt"}:
            raise _invalid("narrative evidence projection contains unknown fields")
        ref = item.get("ref")
        if not isinstance(ref, str) or not ref.strip() or len(ref) > 128:
            raise _invalid("narrative evidence projection identity is invalid")
        if ref in refs:
            raise _invalid("narrative evidence projection contains duplicate references")
        refs.append(ref)
    return frozenset(refs)


def _coerce_pipeline_result(raw: object) -> ExportNarrativePipelineResult:
    if not isinstance(raw, ExportNarrativePipelineResult):
        raise _invalid("narrative pipeline result is invalid")
    if raw.status not in {"succeeded", "needs_review"}:
        raise _unavailable("narrative pipeline did not produce a reviewable result", retryable=False)
    if raw.repair_count not in {0, 1}:
        raise _invalid("narrative pipeline repair count is invalid")
    _string_ids(raw.evidence_refs, "pipeline evidence_refs", 12)
    _hash(raw.model_hash, "model")
    _hash(raw.prompt_hash, "prompt")
    _text(raw.run_id, "run_id", 256)
    _text(raw.trace_id, "trace_id", 256)
    return raw


class StructuredExportNarrativeGenerator:
    """Adapt the existing Flash -> Pro critic -> one-repair pipeline."""

    def __init__(self, pipeline: ExportNarrativePipeline, *, clock: Any = None) -> None:
        if not callable(getattr(pipeline, "run", None)):
            raise TypeError("pipeline must provide a callable run method")
        self._pipeline = pipeline
        self._clock = clock

    @staticmethod
    def projection(snapshot: Any) -> Mapping[str, object]:
        from fmea_application.export_service import build_export_narrative_projection

        return build_export_narrative_projection(snapshot)

    def generate(self, request: ExportNarrativeRequest) -> ExportNarrativeGenerationResult:
        if not isinstance(request, ExportNarrativeRequest):
            raise _invalid("narrative request is invalid")
        supplied_evidence = _safe_projection_refs(request)
        try:
            raw = self._pipeline.run(request)
        except ExportNarrativeGenerationError:
            raise
        except StructuredGenerationError as exc:
            raise _unavailable("narrative model is temporarily unavailable") from exc
        except Exception as exc:
            raise _unavailable("narrative model is temporarily unavailable") from exc
        result = _coerce_pipeline_result(raw)
        included_evidence = frozenset(result.evidence_refs)
        if not included_evidence.issubset(supplied_evidence):
            raise _invalid("narrative pipeline exposed evidence outside the safe projection")
        draft = _parse_draft(result.payload, known_evidence=included_evidence)
        return ExportNarrativeGenerationResult(
            draft=draft,
            model_hash=result.model_hash,
            prompt_hash=result.prompt_hash,
            run_id=result.run_id,
            trace_id=result.trace_id,
            status=result.status,  # type: ignore[arg-type]
            repair_count=result.repair_count,
        )


def _narrative_template() -> CompiledTemplate:
    from structured_output_application import TemplateCompiler
    from structured_output_infrastructure import Draft202012SchemaAdapter

    schema: dict[str, object] = {
        "type": "object",
        "additionalProperties": False,
        "required": ["title", "sections", "claims"],
        "properties": {
            "title": {"type": "string", "minLength": 1, "maxLength": 256},
            "sections": {
                "type": "array",
                "minItems": 1,
                "maxItems": 8,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["section_id", "title", "body", "claim_ids"],
                    "properties": {
                        "section_id": {"type": "string", "minLength": 1, "maxLength": 128},
                        "title": {"type": "string", "minLength": 1, "maxLength": 256},
                        "body": {"type": "string", "minLength": 1, "maxLength": 2500},
                        "claim_ids": {
                            "type": "array",
                            "maxItems": 32,
                            "uniqueItems": True,
                            "items": {"type": "string", "minLength": 1, "maxLength": 128},
                        },
                    },
                },
            },
            "claims": {
                "type": "array",
                "minItems": 1,
                "maxItems": 32,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["claim_id", "text", "evidence_ids"],
                    "properties": {
                        "claim_id": {"type": "string", "minLength": 1, "maxLength": 128},
                        "text": {"type": "string", "minLength": 1, "maxLength": 1000},
                        "evidence_ids": {
                            "type": "array",
                            "maxItems": 8,
                            "uniqueItems": True,
                            "items": {"type": "string", "minLength": 1, "maxLength": 128},
                        },
                    },
                },
            },
        },
    }
    source = {
        "template": {
            "id": _NARRATIVE_TEMPLATE_ID,
            "version": _NARRATIVE_TEMPLATE_VERSION,
            "title": "Bounded FMEA export narrative",
            "description": "Draft an evidence-bound narrative without granting model authority.",
            "domain_tags": ["fmea", "export", "narrative"],
            "schema_dialect": "https://json-schema.org/draft/2020-12/schema",
        },
        "output_schema": schema,
        "evidence_bindings": [
            {
                "target": "/claims/*/text",
                "requirement": "optional",
                "min_refs": 0,
                "max_refs": 8,
                "allowed_source_types": ["rag_text", "graph", "primary_document"],
            }
        ],
    }
    return TemplateCompiler(schema_validator=Draft202012SchemaAdapter(), source_loader=lambda *_: source).compile(
        source
    )


def _projection_pack(request: ExportNarrativeRequest) -> EvidencePack:
    evidence = request.projection.get("evidence", ())
    refs: list[EvidenceRef] = []
    for index, item in enumerate(evidence, start=1):
        if not isinstance(item, Mapping):
            raise _invalid("narrative evidence projection is invalid")
        alias = item["ref"]
        excerpt = item["excerpt"]
        if not isinstance(alias, str) or not isinstance(excerpt, str):
            raise _invalid("narrative evidence projection is invalid")
        digest = sha256(f"{alias}:{excerpt}".encode()).hexdigest()
        refs.append(
            EvidenceRef(
                evidence_id=alias,
                workspace_id="narrative-model-projection",
                document_id=f"projection-document-{index}",
                document_version="projection",
                content_hash=digest,
                locator=alias,
                quote=excerpt or "bounded snapshot evidence",
                normalized_quote=excerpt or "bounded snapshot evidence",
                evidence_hash=digest,
                acl_scope=("model-projection",),
                source_type="rag_text",
                source_trust="derived",
                is_primary=False,
                created_at=request.snapshot.created_at,
                expires_at=None,
            )
        )
    versions = VersionSet(
        "graphrag.fmea.v1",
        "export-narrative-projection",
        "export-narrative-projection",
        "export-narrative-projection",
        "export-narrative-projection",
        "export-narrative-projection",
        "export-narrative-projection",
        "export-narrative-projection",
        "export-narrative-projection",
        "a" * 64,
    )
    pack_id = "export-narrative-projection-" + sha256(request.snapshot.snapshot_hash.encode("ascii")).hexdigest()[:24]
    return EvidencePack.build(
        pack_id=pack_id,
        workspace_id="narrative-model-projection",
        acl_scope=("model-projection",),
        versions=versions,
        refs=tuple(refs),
        created_at=request.snapshot.created_at,
        expires_at=None,
    )


def _canonical_context_json(value: object) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise _invalid("narrative context projection is invalid") from exc


def _json_round_trip(value: object) -> object:
    encoded = _canonical_context_json(value)
    try:
        return json.loads(encoded)
    except (UnicodeError, json.JSONDecodeError) as exc:  # pragma: no cover - json.dumps produced the input.
        raise _invalid("narrative context projection is invalid") from exc


def _context_entries(projection: Mapping[str, object], name: str) -> list[dict[str, object]]:  # noqa: C901
    raw_entries = projection.get(name, ())
    if isinstance(raw_entries, str | bytes) or not isinstance(raw_entries, Sequence) or len(raw_entries) > 64:
        raise _invalid("narrative context projection is invalid")
    expected_keys = {
        "rows": {"row_alias", "fields"},
        "evidence": {"ref", "kind", "excerpt"},
        "unresolved": {"issue_alias", "code", "severity", "evidence_refs"},
    }[name]
    identity_key = {"rows": "row_alias", "evidence": "ref", "unresolved": "issue_alias"}[name]
    normalized: list[dict[str, object]] = []
    identities: list[str] = []
    for raw_entry in raw_entries:
        entry = _json_round_trip(raw_entry)
        if not isinstance(entry, dict) or set(entry) != expected_keys:
            raise _invalid("narrative context projection is invalid")
        identity = entry.get(identity_key)
        if not isinstance(identity, str) or _text(identity, identity_key, 128) != identity:
            raise _invalid("narrative context projection is invalid")
        if name == "rows" and not isinstance(entry.get("fields"), dict):
            raise _invalid("narrative context projection is invalid")
        if name == "evidence":
            kind = entry.get("kind")
            excerpt = entry.get("excerpt")
            if (
                not isinstance(kind, str)
                or _text(kind, "evidence kind", 128) != kind
                or not isinstance(excerpt, str)
                or len(excerpt) > 512
            ):
                raise _invalid("narrative context projection is invalid")
        if name == "unresolved":
            code = entry.get("code")
            severity = entry.get("severity")
            refs = entry.get("evidence_refs")
            if (
                not isinstance(code, str)
                or _text(code, "unresolved code", 128) != code
                or not isinstance(severity, str)
                or _text(severity, "unresolved severity", 32) != severity
                or isinstance(refs, str | bytes)
                or not isinstance(refs, Sequence)
            ):
                raise _invalid("narrative context projection is invalid")
            _string_ids(refs, "unresolved evidence_refs", 12)
        if identity in identities:
            raise _invalid("narrative context projection contains duplicate aliases")
        identities.append(identity)
        normalized.append(entry)
    return sorted(normalized, key=lambda item: str(item[identity_key]))


def _context_document(
    projection: Mapping[str, object],
    entries: Mapping[str, Sequence[Mapping[str, object]]],
    totals: Mapping[str, int],
    *,
    max_characters: int,
    max_utf8_bytes: int,
) -> dict[str, object]:
    summary = _json_round_trip(projection.get("summary"))
    expected_summary = {
        "row_count",
        "risk_record_count",
        "evidence_pack_count",
        "decision_count",
        "unresolved_count",
        "propagation_present",
    }
    if not isinstance(summary, dict) or set(summary) != expected_summary:
        raise _invalid("narrative context projection is invalid")
    for key in expected_summary - {"propagation_present"}:
        if isinstance(summary[key], bool) or not isinstance(summary[key], int) or summary[key] < 0:
            raise _invalid("narrative context projection is invalid")
    if not isinstance(summary["propagation_present"], bool):
        raise _invalid("narrative context projection is invalid")
    aliases: dict[str, str] = {}
    for key in ("snapshot_alias", "revision_alias"):
        value = projection.get(key)
        if not isinstance(value, str) or _text(value, key, 128) != value:
            raise _invalid("narrative context projection is invalid")
        aliases[key] = value
    included_counts = {name: len(entries[name]) for name in _NARRATIVE_CONTEXT_ITEM_LIMITS}
    if totals["rows"] == 0:
        row_quota = {"minimum": 0, "status": "not_applicable"}
    elif included_counts["rows"]:
        row_quota = {"minimum": 1, "status": "satisfied"}
    else:
        row_quota = {"minimum": 1, "status": "budget_insufficient"}
    return {
        **aliases,
        "summary": summary,
        "rows": list(entries["rows"]),
        "evidence": list(entries["evidence"]),
        "unresolved": list(entries["unresolved"]),
        "context_budget": {
            "contract": "unicode-characters-and-utf8-bytes",
            "max_characters": max_characters,
            "max_utf8_bytes": max_utf8_bytes,
            "item_limits": dict(_NARRATIVE_CONTEXT_ITEM_LIMITS),
            "source_counts": dict(totals),
            "included_counts": included_counts,
            "omitted_counts": {name: totals[name] - included_counts[name] for name in totals},
            "row_quota": row_quota,
        },
        "rule": "Draft narrative only; preserve unknowns and cite only included evidence refs.",
    }


def _serialize_context(
    document: Mapping[str, object],
    *,
    max_characters: int,
    max_utf8_bytes: int,
) -> str | None:
    encoded = _canonical_context_json(document)
    try:
        wire = encoded.encode("utf-8")
    except UnicodeError as exc:
        raise _invalid("narrative context serialization is invalid") from exc
    if len(encoded) > max_characters or len(wire) > max_utf8_bytes:
        return None
    try:
        decoded = json.loads(wire.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:  # pragma: no cover - canonical encoder produced the input.
        raise _invalid("narrative context serialization is invalid") from exc
    if _canonical_context_json(decoded) != encoded:
        raise _invalid("narrative context serialization is not canonical")
    return encoded


def _select_context_entry(
    projection: Mapping[str, object],
    selected: Mapping[str, Sequence[dict[str, object]]],
    totals: Mapping[str, int],
    name: str,
    entry: dict[str, object],
    *,
    max_characters: int,
    max_utf8_bytes: int,
) -> tuple[dict[str, list[dict[str, object]]], str] | None:
    candidate = {key: list(values) for key, values in selected.items()}
    candidate[name].append(entry)
    document = _context_document(
        projection,
        candidate,
        totals,
        max_characters=max_characters,
        max_utf8_bytes=max_utf8_bytes,
    )
    task = _serialize_context(
        document,
        max_characters=max_characters,
        max_utf8_bytes=max_utf8_bytes,
    )
    return None if task is None else (candidate, task)


def _validate_context_budget(projection: object, max_characters: object, max_utf8_bytes: object) -> None:
    if (
        not isinstance(projection, Mapping)
        or isinstance(max_characters, bool)
        or not isinstance(max_characters, int)
        or max_characters < 1
        or isinstance(max_utf8_bytes, bool)
        or not isinstance(max_utf8_bytes, int)
        or max_utf8_bytes < 1
    ):
        raise _invalid("narrative context budget is invalid")


def _context_dependencies_included(
    name: str,
    entry: Mapping[str, object],
    selected: Mapping[str, Sequence[Mapping[str, object]]],
) -> bool:
    if name != "unresolved":
        return True
    included_refs = {str(item["ref"]) for item in selected["evidence"]}
    return set(entry["evidence_refs"]).issubset(included_refs)


def _build_bounded_context(
    projection: Mapping[str, object],
    *,
    max_characters: int = _NARRATIVE_TASK_MAX_CHARACTERS,
    max_utf8_bytes: int = _NARRATIVE_TASK_MAX_UTF8_BYTES,
) -> _BoundedNarrativeContext:
    """Select whole entries under both Unicode-character and UTF-8-byte limits."""

    _validate_context_budget(projection, max_characters, max_utf8_bytes)
    available = {name: _context_entries(projection, name) for name in _NARRATIVE_CONTEXT_ITEM_LIMITS}
    totals = {name: len(items) for name, items in available.items()}
    selected: dict[str, list[dict[str, object]]] = {name: [] for name in _NARRATIVE_CONTEXT_ITEM_LIMITS}
    minimum = _context_document(
        projection,
        selected,
        totals,
        max_characters=max_characters,
        max_utf8_bytes=max_utf8_bytes,
    )
    task = _serialize_context(
        minimum,
        max_characters=max_characters,
        max_utf8_bytes=max_utf8_bytes,
    )
    if task is None:
        raise _invalid("narrative context minimum envelope exceeds its configured budget")

    for row in available["rows"]:
        reserved = _select_context_entry(
            projection,
            selected,
            totals,
            "rows",
            row,
            max_characters=max_characters,
            max_utf8_bytes=max_utf8_bytes,
        )
        if reserved is not None:
            selected, task = reserved
            break

    for name in _NARRATIVE_CONTEXT_PRIORITY:
        for entry in available[name]:
            if len(selected[name]) >= _NARRATIVE_CONTEXT_ITEM_LIMITS[name]:
                break
            if name == "rows" and any(
                selected_row["row_alias"] == entry["row_alias"] for selected_row in selected["rows"]
            ):
                continue
            if not _context_dependencies_included(name, entry, selected):
                continue
            accepted = _select_context_entry(
                projection,
                selected,
                totals,
                name,
                entry,
                max_characters=max_characters,
                max_utf8_bytes=max_utf8_bytes,
            )
            if accepted is not None:
                selected, task = accepted

    final_document = json.loads(task)
    evidence_refs = tuple(str(item["ref"]) for item in final_document["evidence"])
    return _BoundedNarrativeContext(task=task, projection=final_document, evidence_refs=evidence_refs)


def _bounded_task(projection: Mapping[str, object]) -> str:
    """Return canonical, structurally budgeted JSON for the shared 4K task field."""

    return _build_bounded_context(projection).task


class StructuredExportNarrativePipeline:
    """Bridge the FMEA request to the existing shared structured pipeline."""

    def __init__(self, pipeline: Any, *, template: CompiledTemplate | None = None) -> None:
        self._pipeline = pipeline
        self._template = template or _narrative_template()

    def run(self, request: ExportNarrativeRequest) -> ExportNarrativePipelineResult:
        from structured_generation_application import GenerationRunRequest

        if not isinstance(request, ExportNarrativeRequest):
            raise _invalid("narrative request is invalid")
        context = _build_bounded_context(request.projection)
        bounded_request = ExportNarrativeRequest(
            snapshot=request.snapshot,
            projection=context.projection,
            run_id=request.run_id,
        )
        model_pack = _projection_pack(bounded_request)
        try:
            result = self._pipeline.run(
                GenerationRunRequest(
                    run_id=request.run_id,
                    task=context.task,
                    template=self._template,
                    evidence_pack=model_pack,
                    budget=GenerationBudget(
                        max_candidates=1,
                        max_evidence_refs=12,
                        max_quote_chars_per_ref=512,
                        max_evidence_chars=8_000,
                        max_prompt_chars=48_000,
                        max_response_chars=16_000,
                        max_output_tokens=2_000,
                        max_logical_calls=3,
                        max_http_attempts=6,
                        max_repairs=1,
                        request_timeout_seconds=30.0,
                        total_timeout_seconds=90.0,
                    ),
                )
            )
        except StructuredGenerationError as exc:
            if exc.code in _UNAVAILABLE_CODES:
                raise _unavailable("narrative model is temporarily unavailable") from exc
            raise _invalid("narrative structured generation failed") from exc
        if result.status is GenerationRunStatus.FAILED or result.batch is None:
            raise _unavailable("narrative pipeline did not produce a reviewable result", retryable=False)
        if len(result.batch.candidates) != 1:
            raise _invalid("narrative pipeline returned an unexpected candidate count")
        successful = tuple(trace for trace in result.traces if trace.response_hash and trace.error_code is None)
        if (
            not successful
            or successful[0].stage is not GenerationStage.GENERATE
            or successful[0].model_id != "deepseek-v4-flash"
        ):
            raise _invalid("narrative generation trace is invalid")
        final_stage = GenerationStage.REPAIR if result.repair_count == 1 else GenerationStage.CRITIC
        final = tuple(
            trace for trace in successful if trace.stage is final_stage and trace.model_id == "deepseek-v4-pro"
        )
        if len(final) != 1:
            raise _invalid("narrative review trace is invalid")
        payload = result.batch.candidates[0].payload
        if not isinstance(payload, Mapping):
            raise _invalid("narrative candidate payload is invalid")
        _parse_draft(payload, known_evidence=frozenset(context.evidence_refs))
        return ExportNarrativePipelineResult(
            payload=payload,
            evidence_refs=context.evidence_refs,
            model_hash=final[0].response_hash or "",
            prompt_hash=final[0].prompt_hash,
            run_id=request.run_id,
            trace_id="export-narrative-trace-"
            + sha256(f"{request.run_id}:{final[0].response_hash}:{final[0].prompt_hash}".encode()).hexdigest()[:32],
            status=result.status.value,
            repair_count=result.repair_count,
            stages=tuple(f"{trace.stage.value}:{trace.model_id}" for trace in successful),
        )


class EnvironmentExportNarrativeGenerator:
    """Lazily compose the configured DeepSeek Flash -> Pro narrative stack."""

    def __init__(self, *, pipeline: ExportNarrativePipeline | None = None) -> None:
        self._pipeline = pipeline

    def generate(self, request: ExportNarrativeRequest) -> ExportNarrativeGenerationResult:
        if self._pipeline is None:
            try:
                from structured_generation_application import StructuredGenerationPipeline
                from structured_generation_infrastructure import (
                    StrictCandidateBatchCodec,
                    StrictCriticReportCodec,
                    build_deepseek_gateway_from_env,
                )
                from structured_output_application import StructuredCandidateValidator
                from structured_output_infrastructure import Draft202012SchemaAdapter

                self._pipeline = StructuredExportNarrativePipeline(
                    StructuredGenerationPipeline(
                        gateway=build_deepseek_gateway_from_env(),
                        batch_codec=StrictCandidateBatchCodec(max_response_chars=16_000),
                        critic_codec=StrictCriticReportCodec(max_response_chars=16_000),
                        candidate_validator=StructuredCandidateValidator(Draft202012SchemaAdapter()),
                    )
                )
            except Exception as exc:
                raise _unavailable("narrative model configuration is unavailable") from exc
        return StructuredExportNarrativeGenerator(self._pipeline).generate(request)


__all__ = [
    "EnvironmentExportNarrativeGenerator",
    "ExportNarrativeGenerationError",
    "ExportNarrativePipeline",
    "ExportNarrativePipelineResult",
    "StructuredExportNarrativeGenerator",
    "StructuredExportNarrativePipeline",
]
