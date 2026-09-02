"""Application authority lifecycle for imported DomainPack templates."""

# TRY003 is consistent with the stable ReviewError boundary used by FMEA.
# ruff: noqa: TRY003

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone

from core_domain.fmea.states import ActorType
from core_domain.fmea.template_migration import TemplateDraft, TemplatePatchCandidate, TemplatePatchStatus

from .assistance_contracts import AssistanceKind, AssistanceSuggestion
from .ports import (
    TemplateCompilerPort,
    TemplateImporter,
    TemplatePatchGenerator,
    TemplatePatchRequest,
    TemplateRegistryPort,
    TemplateSourceBuilder,
)
from .review_contracts import ActorContext
from .review_errors import ReviewError


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _invalid(message: str) -> ReviewError:
    return ReviewError("FMEA_REVIEW_REQUEST_INVALID", message)


def _forbidden(message: str) -> ReviewError:
    return ReviewError("FMEA_REVIEW_FORBIDDEN", message)


def _conflict(message: str) -> ReviewError:
    return ReviewError("FMEA_VERSION_CONFLICT", message)


@dataclass(frozen=True, slots=True)
class ImportTemplateCommand:
    raw_bytes: bytes
    filename: str
    workspace_id: str


@dataclass(frozen=True, slots=True)
class SuggestTemplatePatchCommand:
    draft_id: str
    patch_id: str
    input_template_version: str
    target_template_id: str
    target_template_version: str
    target_template_hash: str
    domain_pack_id: str
    domain_pack_version: str
    domain_pack_hash: str
    evidence_pack_id: str
    evidence_pack_hash: str
    run_id: str
    trace_id: str
    model_version: str
    prompt_version: str
    target_record_version: int = 1


@dataclass(frozen=True, slots=True)
class AcceptTemplatePatchCommand:
    suggestion_id: str
    patch_id: str
    draft_id: str
    draft_sha256: str
    target_template_version: str
    target_template_hash: str
    domain_pack_hash: str
    evidence_pack_hash: str
    confirm_template_change: bool


@dataclass(frozen=True, slots=True)
class RejectTemplatePatchCommand:
    suggestion_id: str
    patch_id: str
    reason: str


def _default_source_builder(draft: TemplateDraft, patch: TemplatePatchCandidate) -> Mapping[str, object]:
    """Create a small declarative template source; no executable rule is accepted."""

    properties: dict[str, object] = {mapping.target_field: {"type": "string"} for mapping in draft.proposed_fields}
    for operation in patch.diff:
        path = str(operation["path"])
        field_name = path.rsplit("/", 1)[-1]
        if operation["op"] == "remove":
            properties.pop(field_name, None)
        else:
            properties[field_name] = {"type": "string"}
    return {
        "template": {
            "id": patch.target_template_id,
            "version": patch.target_template_version,
            "title": "Imported FMEA template",
            "description": f"Imported from {draft.source_type} structural draft.",
            "domain_tags": ["generic-fmea"],
            "schema_dialect": "https://json-schema.org/draft/2020-12/schema",
        },
        "output_schema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": properties,
            "additionalProperties": False,
        },
        "evidence_bindings": [],
    }


def _candidate_from_payload(payload: object) -> TemplatePatchCandidate:
    if not isinstance(payload, Mapping):
        raise _invalid("template patch suggestion payload is invalid")
    required = {
        "patch_id",
        "draft_id",
        "input_template_version",
        "target_template_id",
        "target_template_version",
        "target_template_hash",
        "domain_pack_id",
        "domain_pack_version",
        "domain_pack_hash",
        "evidence_pack_id",
        "evidence_pack_hash",
        "run_id",
        "trace_id",
        "model_version",
        "prompt_version",
        "diff",
        "evidence_ids",
        "status",
        "created_at",
        "applied",
    }
    if set(payload) != required:
        raise _invalid("template patch suggestion payload has unknown or missing fields")
    try:
        return TemplatePatchCandidate(
            patch_id=payload["patch_id"],
            draft_id=payload["draft_id"],
            input_template_version=payload["input_template_version"],
            target_template_id=payload["target_template_id"],
            target_template_version=payload["target_template_version"],
            target_template_hash=payload["target_template_hash"],
            domain_pack_id=payload["domain_pack_id"],
            domain_pack_version=payload["domain_pack_version"],
            domain_pack_hash=payload["domain_pack_hash"],
            evidence_pack_id=payload["evidence_pack_id"],
            evidence_pack_hash=payload["evidence_pack_hash"],
            run_id=payload["run_id"],
            trace_id=payload["trace_id"],
            model_version=payload["model_version"],
            prompt_version=payload["prompt_version"],
            diff=payload["diff"],
            evidence_ids=payload["evidence_ids"],
            status=payload["status"],
            created_at=payload["created_at"],
            applied=payload["applied"],
        )
    except (TypeError, ValueError) as exc:
        raise _invalid("template patch suggestion candidate is invalid") from exc


class DomainPackService:
    """Orchestrate draft/review/register without owning persistence or adapters."""

    def __init__(
        self,
        *,
        importers: Mapping[str, TemplateImporter],
        patch_generator: TemplatePatchGenerator,
        compiler: TemplateCompilerPort,
        registry: TemplateRegistryPort,
        source_builder: TemplateSourceBuilder | None = None,
        clock: Callable[[], str] = _now,
    ) -> None:
        if not importers:
            raise ValueError("at least one template importer is required")
        self._importers = dict(importers)
        self._patch_generator = patch_generator
        self._compiler = compiler
        self._registry = registry
        self._source_builder = source_builder
        self._clock = clock
        self._drafts: dict[str, TemplateDraft] = {}
        self._suggestions: dict[str, tuple[AssistanceSuggestion[object], TemplatePatchCandidate]] = {}
        self._decisions: dict[str, str] = {}

    def import_template(self, command: ImportTemplateCommand, actor: ActorContext) -> TemplateDraft:
        if not isinstance(command, ImportTemplateCommand) or not isinstance(actor, ActorContext):
            raise _invalid("template import request is invalid")
        if command.workspace_id != actor.workspace_id:
            raise _forbidden("template import workspace does not match actor")
        if not isinstance(command.filename, str):
            raise _invalid("template source filename is invalid")
        source_type = command.filename.rsplit(".", 1)[-1].casefold() if "." in command.filename else ""
        importer = self._importers.get(source_type)
        if importer is None:
            raise _invalid("template source type is unsupported")
        draft = importer.parse(command.raw_bytes, command.filename, workspace_id=command.workspace_id)
        if draft.workspace_id != actor.workspace_id:
            raise _forbidden("template draft workspace does not match actor")
        existing = self._drafts.get(draft.draft_id)
        if existing is not None and existing != draft:
            raise _conflict("template draft identity already has different content")
        self._drafts[draft.draft_id] = draft
        return draft

    def suggest_patch(self, command: SuggestTemplatePatchCommand, actor: ActorContext) -> AssistanceSuggestion[object]:
        if not isinstance(command, SuggestTemplatePatchCommand) or not isinstance(actor, ActorContext):
            raise _invalid("template patch request is invalid")
        draft = self._drafts.get(command.draft_id)
        if draft is None:
            raise _invalid("template draft was not found")
        if draft.workspace_id != actor.workspace_id:
            raise _forbidden("template draft belongs to another workspace")
        if command.patch_id in self._suggestions:
            existing, _ = self._suggestions[command.patch_id]
            if existing.workspace_id == actor.workspace_id:
                raise _conflict("template patch suggestion already exists")
            raise _forbidden("template patch belongs to another workspace")
        request = TemplatePatchRequest(
            patch_id=command.patch_id,
            draft=draft,
            input_template_version=command.input_template_version,
            target_template_id=command.target_template_id,
            target_template_version=command.target_template_version,
            target_template_hash=command.target_template_hash,
            domain_pack_id=command.domain_pack_id,
            domain_pack_version=command.domain_pack_version,
            domain_pack_hash=command.domain_pack_hash,
            evidence_pack_id=command.evidence_pack_id,
            evidence_pack_hash=command.evidence_pack_hash,
            run_id=command.run_id,
            trace_id=command.trace_id,
            model_version=command.model_version,
            prompt_version=command.prompt_version,
            created_at=self._clock(),
            target_record_version=command.target_record_version,
        )
        suggestion = self._patch_generator.suggest(request)
        if (
            not isinstance(suggestion, AssistanceSuggestion)
            or suggestion.kind is not AssistanceKind.TEMPLATE_FIELD_MAPPING
        ):
            raise _invalid("template patch generator returned an invalid suggestion")
        if (
            suggestion.workspace_id != actor.workspace_id
            or suggestion.target_id != draft.draft_id
            or suggestion.applied
        ):
            raise _invalid("template patch suggestion identity is invalid")
        candidate = _candidate_from_payload(suggestion.payload)
        if (
            candidate.patch_id != command.patch_id
            or candidate.draft_id != draft.draft_id
            or candidate.input_template_version != command.input_template_version
            or candidate.target_template_id != command.target_template_id
            or candidate.target_template_version != command.target_template_version
            or candidate.target_template_hash != command.target_template_hash
            or candidate.domain_pack_id != command.domain_pack_id
            or candidate.domain_pack_version != command.domain_pack_version
            or candidate.domain_pack_hash != command.domain_pack_hash
            or candidate.evidence_pack_id != command.evidence_pack_id
            or candidate.evidence_pack_hash != command.evidence_pack_hash
            or candidate.run_id != command.run_id
            or candidate.trace_id != command.trace_id
            or candidate.model_version != command.model_version
            or candidate.prompt_version != command.prompt_version
            or candidate.status is not TemplatePatchStatus.SUGGESTED
            or suggestion.target_type != "template_draft"
            or suggestion.target_record_version != command.target_record_version
            or suggestion.evidence_pack_ids != (candidate.evidence_pack_id,)
            or suggestion.evidence_ids != candidate.evidence_ids
            or suggestion.run_id != candidate.run_id
            or suggestion.trace_id != candidate.trace_id
            or suggestion.domain_pack_id != candidate.domain_pack_id
            or suggestion.domain_pack_version != candidate.domain_pack_version
            or suggestion.template_id != candidate.target_template_id
            or suggestion.template_version != candidate.target_template_version
            or suggestion.created_at != candidate.created_at
        ):
            raise _invalid("template patch suggestion provenance does not match the request")
        self._suggestions[candidate.patch_id] = (suggestion, candidate)
        return suggestion

    def _load_candidate(
        self, suggestion_id: str, patch_id: str, actor: ActorContext
    ) -> tuple[TemplateDraft, TemplatePatchCandidate]:
        item = self._suggestions.get(patch_id)
        if item is None:
            raise _invalid("template patch suggestion was not found")
        suggestion, candidate = item
        if suggestion.suggestion_id != suggestion_id:
            raise _conflict("template patch suggestion identity does not match")
        draft = self._drafts.get(candidate.draft_id)
        if draft is None:
            raise _invalid("template draft was not found")
        if draft.workspace_id != actor.workspace_id or suggestion.workspace_id != actor.workspace_id:
            raise _forbidden("template patch belongs to another workspace")
        if self._decisions.get(patch_id) is not None:
            raise _conflict("template patch suggestion was already decided")
        return draft, candidate

    @staticmethod
    def _require_template_admin(actor: ActorContext) -> None:
        if actor.actor_type is not ActorType.HUMAN or "template_admin" not in actor.roles:
            raise _forbidden("FMEA_TEMPLATE_ADMIN_REQUIRED: only a human template_admin may decide a template patch")

    def accept_patch(self, command: AcceptTemplatePatchCommand, actor: ActorContext) -> object:
        if not isinstance(command, AcceptTemplatePatchCommand) or not isinstance(actor, ActorContext):
            raise _invalid("template patch acceptance request is invalid")
        self._require_template_admin(actor)
        if command.confirm_template_change is not True:
            raise _forbidden("FMEA_TEMPLATE_CONFIRMATION_REQUIRED: explicit template confirmation is required")
        draft, candidate = self._load_candidate(command.suggestion_id, command.patch_id, actor)
        if (
            command.draft_id != draft.draft_id
            or command.draft_sha256 != draft.source_sha256
            or command.target_template_version != candidate.target_template_version
            or command.target_template_hash != candidate.target_template_hash
            or command.domain_pack_hash != candidate.domain_pack_hash
            or command.evidence_pack_hash != candidate.evidence_pack_hash
            or candidate.status is not TemplatePatchStatus.SUGGESTED
            or candidate.applied
        ):
            raise _conflict("template patch acceptance precondition is stale")
        builder = self._source_builder or _DefaultSourceBuilder()
        source = builder.build(draft, candidate)
        if not isinstance(source, Mapping):
            raise _invalid("template source builder returned an invalid source")
        source_bytes = json.dumps(
            source, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
        try:
            compiled = self._compiler.compile(source)
            registered = self._registry.register(compiled, source_bytes, ".json")
        except ReviewError:
            raise
        except Exception as exc:
            raise ReviewError("FMEA_REVIEW_STORAGE_UNAVAILABLE", "template compilation or registration failed") from exc
        self._decisions[command.patch_id] = "accepted"
        return registered

    def reject_patch(self, command: RejectTemplatePatchCommand, actor: ActorContext) -> TemplatePatchCandidate:
        if not isinstance(command, RejectTemplatePatchCommand) or not isinstance(actor, ActorContext):
            raise _invalid("template patch rejection request is invalid")
        self._require_template_admin(actor)
        if not isinstance(command.reason, str) or not command.reason.strip():
            raise _invalid("template patch rejection reason is required")
        _, candidate = self._load_candidate(command.suggestion_id, command.patch_id, actor)
        self._decisions[command.patch_id] = "rejected"
        return candidate


@dataclass(frozen=True, slots=True)
class _DefaultSourceBuilder:
    def build(self, draft: TemplateDraft, patch: TemplatePatchCandidate) -> Mapping[str, object]:
        return _default_source_builder(draft, patch)


__all__ = [
    "AcceptTemplatePatchCommand",
    "DomainPackService",
    "ImportTemplateCommand",
    "RejectTemplatePatchCommand",
    "SuggestTemplatePatchCommand",
]
