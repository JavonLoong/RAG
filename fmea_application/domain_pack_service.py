"""Application authority lifecycle for imported DomainPack templates."""

# TRY003 is consistent with the stable ReviewError boundary used by FMEA.
# ruff: noqa: TRY003

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from threading import RLock

from core_domain.fmea.states import ActorType
from core_domain.fmea.template_migration import TemplateDraft, TemplatePatchCandidate, TemplatePatchStatus

from .assistance_contracts import AssistanceKind, AssistanceSuggestion
from .ports import (
    TemplateCompilerPort,
    TemplateEvidenceProvider,
    TemplateImporter,
    TemplatePatchGenerator,
    TemplatePatchRequest,
    TemplateRegistryPort,
    TemplateSourceBuilder,
    TemplateWorkflowRepository,
)
from .review_contracts import ActorContext, IdempotencyScope, idempotency_key_hash
from .review_errors import ReviewError
from .template_patch_contracts import (
    TemplatePatchDecision,
    TemplatePatchSuggestion,
    normalize_source_mapping_key,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _invalid(message: str) -> ReviewError:
    return ReviewError("FMEA_REVIEW_REQUEST_INVALID", message)


def _forbidden(message: str) -> ReviewError:
    return ReviewError("FMEA_REVIEW_FORBIDDEN", message)


def _conflict(message: str) -> ReviewError:
    return ReviewError("FMEA_VERSION_CONFLICT", message)


def _payload_hash(value: Mapping[str, object]) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return "sha256:" + sha256(payload.encode("utf-8")).hexdigest()


def _scope(actor: ActorContext, *, key: str | None, command: str, resource_path: str) -> IdempotencyScope:
    if key is None:
        raise _invalid("idempotency_key is required for durable template workflow operations")
    try:
        key_hash = idempotency_key_hash(key)
    except Exception:
        raise _invalid("idempotency_key must be a canonical UUID") from None
    return IdempotencyScope(
        workspace_id=actor.workspace_id,
        actor_id=actor.actor_id,
        command=command,
        resource_path=resource_path,
        key_hash=key_hash,
    )


@dataclass(frozen=True, slots=True)
class ImportTemplateCommand:
    raw_bytes: bytes
    filename: str
    workspace_id: str
    idempotency_key: str | None = None


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
    idempotency_key: str | None = None


@dataclass(frozen=True, slots=True)
class AcceptTemplatePatchCommand:
    suggestion_id: str
    patch_id: str
    draft_id: str
    draft_sha256: str
    target_template_version: str
    target_template_hash: str
    new_template_version: str
    domain_pack_hash: str
    evidence_pack_hash: str
    confirm_template_change: bool
    expected_patch_version: int = 1
    idempotency_key: str | None = None


@dataclass(frozen=True, slots=True)
class RejectTemplatePatchCommand:
    suggestion_id: str
    patch_id: str
    reason: str
    expected_patch_version: int = 1
    idempotency_key: str | None = None


_SEMVER = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
_FIELD_NAME = re.compile(r"^[a-z][a-z0-9_.-]{0,127}$")
_SOURCE_MAPPINGS_KEY = "source_mappings"


def _semver(value: object, field_name: str) -> tuple[int, int, int]:
    if not isinstance(value, str):
        raise _invalid(f"{field_name} is invalid")
    matched = _SEMVER.fullmatch(value)
    if matched is None:
        raise _invalid(f"{field_name} is invalid")
    return tuple(int(part) for part in matched.groups())  # type: ignore[return-value]


def _base_source(compiled: object, candidate: TemplatePatchCandidate) -> dict[str, object]:
    template_hash = getattr(compiled, "template_hash", None)
    canonical_json = getattr(compiled, "canonical_json", None)
    expected_hash = candidate.target_template_hash.removeprefix("sha256:")
    if template_hash != expected_hash or not isinstance(canonical_json, str):
        raise _conflict("base template hash does not match the patch candidate")
    try:
        source = json.loads(canonical_json)
    except (TypeError, ValueError) as exc:
        raise _conflict("base template source is invalid") from exc
    required_keys = {"template", "output_schema", "evidence_bindings"}
    allowed_keys = required_keys | {_SOURCE_MAPPINGS_KEY}
    if not isinstance(source, dict) or not required_keys.issubset(source) or not set(source).issubset(allowed_keys):
        raise _conflict("base template source is invalid")
    metadata = source.get("template")
    if (
        not isinstance(metadata, dict)
        or metadata.get("id") != candidate.target_template_id
        or metadata.get("version") != candidate.target_template_version
    ):
        raise _conflict("base template identity does not match the patch candidate")
    return source


def _default_source_builder(  # noqa: C901 - patch groups retain explicit fail-closed branches
    base_source: Mapping[str, object],
    draft: TemplateDraft,
    patch: TemplatePatchCandidate,
    new_template_version: str,
) -> Mapping[str, object]:
    """Apply an allowlisted patch to a verified base source without inventing fields."""

    try:
        source = json.loads(json.dumps(base_source, ensure_ascii=False, allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise _invalid("base template source is not canonical JSON") from exc
    if not isinstance(source, dict):
        raise _invalid("base template source is invalid")
    metadata = source.get("template")
    schema = source.get("output_schema")
    if not isinstance(metadata, dict) or not isinstance(schema, dict):
        raise _invalid("base template source is invalid")
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        raise _invalid("base template properties are invalid")
    if _semver(new_template_version, "new template version") <= _semver(
        patch.target_template_version, "base template version"
    ):
        raise _conflict("new template version must be higher than the base template version")

    mapping_operations: list[Mapping[str, object]] = []
    for operation in patch.diff:
        path = str(operation["path"])
        group, name = path.strip("/").split("/", 1)
        if _FIELD_NAME.fullmatch(name) is None:
            raise _invalid("template patch path is invalid")
        if group == "mappings":
            mapping_operations.append(operation)
            continue
        exists = name in properties
        action = operation["op"]
        if action == "add" and exists:
            raise _conflict("template patch add target already exists")
        if action in {"replace", "remove"} and not exists:
            raise _conflict("template patch target does not exist")
        if action == "remove":
            del properties[name]
            required = schema.get("required")
            if isinstance(required, list):
                schema["required"] = [item for item in required if item != name]
        else:
            value = operation.get("value")
            if not isinstance(value, Mapping):
                raise _invalid("field patch values must be JSON Schema objects")
            properties[name] = dict(value)

    source_keys = {normalize_source_mapping_key(item.source_key) for item in draft.proposed_fields}
    source_keys.update(normalize_source_mapping_key(item) for item in draft.unknown_fields)
    source_keys.update(normalize_source_mapping_key(item) for item in draft.ambiguous_fields)
    raw_mappings = source.get(_SOURCE_MAPPINGS_KEY, {})
    if not isinstance(raw_mappings, dict) or len(raw_mappings) > 500:
        raise _invalid("base template source mappings are invalid")
    resolved_mappings: dict[str, str] = {}
    for source_key, target_field in raw_mappings.items():
        if (
            not isinstance(source_key, str)
            or _FIELD_NAME.fullmatch(source_key) is None
            or not isinstance(target_field, str)
        ):
            raise _invalid("base template source mappings are invalid")
        resolved_mappings[source_key] = target_field
    for item in draft.proposed_fields:
        source_key = normalize_source_mapping_key(item.source_key)
        existing_target = resolved_mappings.get(source_key)
        if existing_target is not None and existing_target != item.target_field:
            raise _conflict("base and imported source mappings conflict")
        resolved_mappings[source_key] = item.target_field
    if len(resolved_mappings) > 500:
        raise _invalid("template source mappings exceed the configured limit")
    for operation in mapping_operations:
        name = str(operation["path"]).rsplit("/", 1)[-1]
        action = operation["op"]
        if name not in source_keys:
            raise _conflict("mapping patch source does not exist in the imported draft")
        if action == "remove":
            if name not in resolved_mappings:
                raise _conflict("template patch mapping target does not exist")
            del resolved_mappings[name]
            continue
        target = operation.get("value")
        if not isinstance(target, str) or target not in properties:
            raise _invalid("mapping patch target must reference a resulting template field")
        if action == "add" and name in resolved_mappings:
            raise _conflict("mapping patch add target already exists")
        if action == "replace" and name not in resolved_mappings:
            raise _conflict("template patch mapping target does not exist")
        resolved_mappings[name] = target
        if len(resolved_mappings) > 500:
            raise _invalid("template source mappings exceed the configured limit")

    if any(target not in properties for target in resolved_mappings.values()):
        raise _conflict("source mapping references a missing resulting template field")
    source[_SOURCE_MAPPINGS_KEY] = dict(sorted(resolved_mappings.items()))
    metadata["version"] = new_template_version
    return source


class DomainPackService:
    """Orchestrate draft/review/register without owning persistence or adapters."""

    def __init__(
        self,
        *,
        importers: Mapping[str, TemplateImporter],
        patch_generator: TemplatePatchGenerator,
        evidence_provider: TemplateEvidenceProvider,
        compiler: TemplateCompilerPort,
        registry: TemplateRegistryPort,
        source_builder: TemplateSourceBuilder | None = None,
        workflow_repository: TemplateWorkflowRepository | None = None,
        clock: Callable[[], str] = _now,
    ) -> None:
        if not importers:
            raise ValueError("at least one template importer is required")
        self._importers = dict(importers)
        self._patch_generator = patch_generator
        self._evidence_provider = evidence_provider
        self._compiler = compiler
        self._registry = registry
        self._source_builder = source_builder
        self._workflow_repository = workflow_repository
        self._clock = clock
        self._drafts: dict[str, TemplateDraft] = {}
        self._suggestions: dict[str, TemplatePatchSuggestion] = {}
        self._suggestion_reservations: dict[str, str] = {}
        self._decisions: dict[str, TemplatePatchDecision] = {}
        self._decision_lock = RLock()

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
        if self._workflow_repository is not None:
            scope = _scope(
                actor,
                key=command.idempotency_key,
                command="fmea.template.import",
                resource_path="/fmea/template-drafts",
            )
            payload_hash = _payload_hash({
                "workspace_id": command.workspace_id,
                "filename": command.filename,
                "source_sha256": sha256(command.raw_bytes).hexdigest(),
            })
            try:
                stored, _, _ = self._workflow_repository.save_template_draft(
                    draft, scope, payload_hash, actor_type=actor.actor_type
                )
            except ReviewError:
                raise
            except Exception:
                raise ReviewError(
                    "FMEA_REVIEW_STORAGE_UNAVAILABLE", "template draft storage is unavailable", retryable=True
                ) from None
            return stored
        existing = self._drafts.get(draft.draft_id)
        if existing is not None and existing != draft:
            raise _conflict("template draft identity already has different content")
        self._drafts[draft.draft_id] = draft
        return draft

    def get_draft_record(self, draft_id: str, actor: ActorContext) -> tuple[TemplateDraft, int]:
        if not isinstance(draft_id, str) or not isinstance(actor, ActorContext):
            raise _invalid("template draft query is invalid")
        if self._workflow_repository is not None:
            try:
                item = self._workflow_repository.get_template_draft(draft_id, actor.workspace_id)
            except ReviewError:
                raise
            except Exception:
                raise ReviewError(
                    "FMEA_REVIEW_STORAGE_UNAVAILABLE", "template draft storage is unavailable", retryable=True
                ) from None
            if item is None:
                raise _invalid("template draft was not found")
            return item
        draft = self._drafts.get(draft_id)
        if draft is None:
            raise _invalid("template draft was not found")
        if draft.workspace_id != actor.workspace_id:
            raise _forbidden("template draft belongs to another workspace")
        return draft, 1

    def suggest_patch(self, command: SuggestTemplatePatchCommand, actor: ActorContext) -> TemplatePatchSuggestion:
        if not isinstance(command, SuggestTemplatePatchCommand) or not isinstance(actor, ActorContext):
            raise _invalid("template patch request is invalid")
        with self._decision_lock:
            existing = None if self._workflow_repository is not None else self._suggestions.get(command.patch_id)
            reserved_workspace = self._suggestion_reservations.get(command.patch_id)
            if existing is not None:
                if existing.envelope.workspace_id == actor.workspace_id:
                    raise _conflict("template patch suggestion already exists")
                raise _forbidden("template patch belongs to another workspace")
            if reserved_workspace is not None:
                if reserved_workspace == actor.workspace_id:
                    raise _conflict("template patch suggestion generation is already in progress")
                raise _forbidden("template patch belongs to another workspace")
            self._suggestion_reservations[command.patch_id] = actor.workspace_id
        try:
            return self._suggest_patch(command, actor)
        finally:
            with self._decision_lock:
                if self._suggestion_reservations.get(command.patch_id) == actor.workspace_id:
                    del self._suggestion_reservations[command.patch_id]

    def _suggest_patch(  # noqa: C901 - provenance checks remain explicit at the authority boundary
        self, command: SuggestTemplatePatchCommand, actor: ActorContext
    ) -> TemplatePatchSuggestion:
        scope = None
        payload_hash = None
        if self._workflow_repository is not None:
            scope = _scope(
                actor,
                key=command.idempotency_key,
                command="fmea.template.patch.suggest",
                resource_path=f"/fmea/template-patches/{command.patch_id}",
            )
            payload_hash = _payload_hash({
                "draft_id": command.draft_id,
                "patch_id": command.patch_id,
                "input_template_version": command.input_template_version,
                "target_template_id": command.target_template_id,
                "target_template_version": command.target_template_version,
                "target_template_hash": command.target_template_hash,
                "domain_pack_id": command.domain_pack_id,
                "domain_pack_version": command.domain_pack_version,
                "domain_pack_hash": command.domain_pack_hash,
                "evidence_pack_id": command.evidence_pack_id,
                "evidence_pack_hash": command.evidence_pack_hash,
                "target_record_version": command.target_record_version,
            })
            try:
                replay = self._workflow_repository.reserve_template_patch_generation(
                    command.patch_id,
                    scope,
                    payload_hash,
                    created_at=self._clock(),
                )
            except ReviewError:
                raise
            except Exception:
                raise ReviewError(
                    "FMEA_REVIEW_STORAGE_UNAVAILABLE", "template patch replay is unavailable", retryable=True
                ) from None
            if replay is not None:
                return replay
        draft, draft_version = self.get_draft_record(command.draft_id, actor)
        if draft_version != command.target_record_version:
            raise _conflict("template draft version is stale")
        if draft.workspace_id != actor.workspace_id:
            raise _forbidden("template draft belongs to another workspace")
        try:
            evidence_pack = self._evidence_provider.load_pack(actor.workspace_id, command.evidence_pack_id)
        except ReviewError:
            raise
        except Exception as exc:
            raise ReviewError("FMEA_EVIDENCE_INVALID", "template mapping EvidencePack was not found") from exc
        if (
            evidence_pack.workspace_id != actor.workspace_id
            or evidence_pack.pack_id != command.evidence_pack_id
            or evidence_pack.pack_hash != command.evidence_pack_hash.removeprefix("sha256:")
        ):
            raise ReviewError("FMEA_EVIDENCE_INVALID", "template mapping EvidencePack identity is invalid")
        request = TemplatePatchRequest(
            patch_id=command.patch_id,
            draft=draft,
            evidence_pack=evidence_pack,
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
        if not isinstance(suggestion, TemplatePatchSuggestion):
            raise _invalid("template patch generator returned an invalid suggestion")
        envelope = suggestion.envelope
        if not isinstance(envelope, AssistanceSuggestion) or envelope.kind is not AssistanceKind.TEMPLATE_FIELD_MAPPING:
            raise _invalid("template patch generator returned an invalid suggestion")
        if envelope.workspace_id != actor.workspace_id or envelope.target_id != draft.draft_id or envelope.applied:
            raise _invalid("template patch suggestion identity is invalid")
        candidate = suggestion.candidate
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
            or envelope.target_type != "template_draft"
            or envelope.target_record_version != command.target_record_version
            or envelope.evidence_pack_ids != (candidate.evidence_pack_id,)
            or envelope.evidence_ids != candidate.evidence_ids
            or envelope.run_id != candidate.run_id
            or envelope.trace_id != candidate.trace_id
            or envelope.domain_pack_id != candidate.domain_pack_id
            or envelope.domain_pack_version != candidate.domain_pack_version
            or envelope.template_id != candidate.target_template_id
            or envelope.template_version != candidate.target_template_version
            or envelope.created_at != candidate.created_at
        ):
            raise _invalid("template patch suggestion provenance does not match the request")
        with self._decision_lock:
            if self._workflow_repository is None:
                if candidate.patch_id in self._suggestions:
                    raise _conflict("template patch suggestion already exists")
                self._suggestions[candidate.patch_id] = suggestion
            else:
                if scope is None or payload_hash is None:
                    raise _invalid("durable template suggestion binding is incomplete")
                try:
                    suggestion, _, _ = self._workflow_repository.save_template_patch(
                        suggestion,
                        scope,
                        payload_hash,
                        expected_draft_version=command.target_record_version,
                        actor_type=actor.actor_type,
                    )
                except ReviewError:
                    raise
                except Exception:
                    raise ReviewError(
                        "FMEA_REVIEW_STORAGE_UNAVAILABLE",
                        "template patch storage is unavailable",
                        retryable=True,
                    ) from None
        return suggestion

    def _load_candidate(
        self, suggestion_id: str, patch_id: str, actor: ActorContext
    ) -> tuple[TemplateDraft, TemplatePatchCandidate]:
        if self._workflow_repository is not None:
            item, _ = self.patch_for(patch_id, actor)
            if isinstance(item, TemplatePatchDecision):
                raise _conflict("template patch suggestion was already decided")
        else:
            item = self._suggestions.get(patch_id)
            if item is None:
                raise _invalid("template patch suggestion was not found")
        candidate = item.candidate
        envelope = item.envelope
        if envelope.suggestion_id != suggestion_id:
            raise _conflict("template patch suggestion identity does not match")
        draft, _ = self.get_draft_record(candidate.draft_id, actor)
        if draft.workspace_id != actor.workspace_id or envelope.workspace_id != actor.workspace_id:
            raise _forbidden("template patch belongs to another workspace")
        if self._workflow_repository is None and self._decisions.get(patch_id) is not None:
            raise _conflict("template patch suggestion was already decided")
        return draft, candidate

    @staticmethod
    def _require_template_admin(actor: ActorContext) -> None:
        if actor.actor_type is not ActorType.HUMAN or "template_admin" not in actor.roles:
            raise _forbidden("FMEA_TEMPLATE_ADMIN_REQUIRED: only a human template_admin may decide a template patch")

    def accept_patch(self, command: AcceptTemplatePatchCommand, actor: ActorContext) -> object:
        with self._decision_lock:
            return self._accept_patch(command, actor)

    def _accept_patch(  # noqa: C901 - authority, replay, compilation and persistence checks stay explicit
        self, command: AcceptTemplatePatchCommand, actor: ActorContext
    ) -> object:
        if not isinstance(command, AcceptTemplatePatchCommand) or not isinstance(actor, ActorContext):
            raise _invalid("template patch acceptance request is invalid")
        self._require_template_admin(actor)
        if command.confirm_template_change is not True:
            raise _forbidden("FMEA_TEMPLATE_CONFIRMATION_REQUIRED: explicit template confirmation is required")
        existing_decision: TemplatePatchDecision | None = None
        suggestion_id = command.suggestion_id
        if self._workflow_repository is not None:
            existing, _ = self.patch_for(command.patch_id, actor)
            suggestion_id = existing.suggestion_id
            if isinstance(existing, TemplatePatchDecision):
                existing_decision = existing
                candidate = existing.candidate
            else:
                candidate = existing.candidate
            draft, _ = self.get_draft_record(candidate.draft_id, actor)
        else:
            draft, candidate = self._load_candidate(command.suggestion_id, command.patch_id, actor)
        if (
            command.suggestion_id != suggestion_id
            or command.expected_patch_version != 1
            or command.draft_id != draft.draft_id
            or command.draft_sha256 != draft.source_sha256
            or command.target_template_version != candidate.target_template_version
            or command.target_template_hash != candidate.target_template_hash
            or command.domain_pack_hash != candidate.domain_pack_hash
            or command.evidence_pack_hash != candidate.evidence_pack_hash
            or candidate.status is not TemplatePatchStatus.SUGGESTED
            or candidate.applied
        ):
            raise _conflict("template patch acceptance precondition is stale")
        scope: IdempotencyScope | None = None
        payload_hash: str | None = None
        if self._workflow_repository is not None:
            scope = _scope(
                actor,
                key=command.idempotency_key,
                command="fmea.template.patch.accept",
                resource_path=f"/fmea/template-patches/{command.patch_id}/acceptance",
            )
            payload_hash = _payload_hash({
                "suggestion_id": command.suggestion_id,
                "patch_id": command.patch_id,
                "draft_id": command.draft_id,
                "draft_sha256": command.draft_sha256,
                "target_template_version": command.target_template_version,
                "target_template_hash": command.target_template_hash,
                "new_template_version": command.new_template_version,
                "domain_pack_hash": command.domain_pack_hash,
                "evidence_pack_hash": command.evidence_pack_hash,
                "expected_patch_version": command.expected_patch_version,
                "confirm_template_change": command.confirm_template_change,
            })
        if existing_decision is not None:
            if (
                existing_decision.action != "accepted"
                or existing_decision.new_template_version != command.new_template_version
            ):
                raise _conflict("template patch was already decided")
            if scope is None or payload_hash is None:
                raise _invalid("durable template acceptance binding is incomplete")
            self._workflow_repository.save_template_patch_decision(
                existing_decision,
                scope,
                payload_hash,
                expected_patch_version=command.expected_patch_version,
            )
            try:
                return self._registry.get(candidate.target_template_id, command.new_template_version)
            except Exception:
                raise ReviewError(
                    "FMEA_REVIEW_STORAGE_UNAVAILABLE", "registered template replay is unavailable", retryable=True
                ) from None
        try:
            base = self._registry.get(candidate.target_template_id, candidate.target_template_version)
        except ReviewError:
            raise
        except Exception as exc:
            raise ReviewError("FMEA_REVIEW_STORAGE_UNAVAILABLE", "base template cannot be loaded") from exc
        base_source = _base_source(base, candidate)
        builder = self._source_builder or _DefaultSourceBuilder()
        source = builder.build(base_source, draft, candidate, command.new_template_version)
        if not isinstance(source, Mapping):
            raise _invalid("template source builder returned an invalid source")
        source_object = dict(source)
        source_bytes = json.dumps(
            source_object, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
        try:
            compiled = self._compiler.compile(source_object)
        except ReviewError:
            raise
        except Exception as exc:
            raise ReviewError("FMEA_REVIEW_STORAGE_UNAVAILABLE", "template compilation failed") from exc
        decision = TemplatePatchDecision(
            decision_id=f"template-patch-decision-{command.patch_id}",
            suggestion_id=suggestion_id,
            patch_id=command.patch_id,
            workspace_id=actor.workspace_id,
            actor_id=actor.actor_id,
            actor_type=actor.actor_type,
            action="accepted",
            reason="accepted after explicit template change confirmation",
            base_template_id=candidate.target_template_id,
            base_template_version=candidate.target_template_version,
            base_template_hash=candidate.target_template_hash,
            candidate=candidate,
            new_template_version=command.new_template_version,
            created_at=self._clock(),
        )
        decision_completed = False
        if self._workflow_repository is not None:
            if scope is None or payload_hash is None:
                raise _invalid("durable template acceptance binding is incomplete")
            try:
                decision, decision_completed = self._workflow_repository.reserve_template_patch_decision(
                    decision,
                    scope,
                    payload_hash,
                    expected_patch_version=command.expected_patch_version,
                )
            except ReviewError:
                raise
            except Exception:
                raise ReviewError(
                    "FMEA_REVIEW_STORAGE_UNAVAILABLE",
                    "template patch decision reservation is unavailable",
                    retryable=True,
                ) from None
            if decision_completed:
                try:
                    return self._registry.get(candidate.target_template_id, command.new_template_version)
                except Exception:
                    raise ReviewError(
                        "FMEA_REVIEW_STORAGE_UNAVAILABLE", "registered template replay is unavailable", retryable=True
                    ) from None
        try:
            registered = self._registry.register(compiled, source_bytes, ".json")
        except ReviewError:
            raise
        except Exception as exc:
            raise ReviewError("FMEA_REVIEW_STORAGE_UNAVAILABLE", "template compilation or registration failed") from exc
        if self._workflow_repository is None:
            self._decisions[command.patch_id] = decision
        else:
            if scope is None or payload_hash is None:
                raise _invalid("durable template acceptance binding is incomplete")
            try:
                self._workflow_repository.save_template_patch_decision(
                    decision,
                    scope,
                    payload_hash,
                    expected_patch_version=command.expected_patch_version,
                )
            except ReviewError:
                raise
            except Exception:
                raise ReviewError(
                    "FMEA_REVIEW_STORAGE_UNAVAILABLE",
                    "template patch decision storage is unavailable",
                    retryable=True,
                ) from None
        return registered

    def reject_patch(self, command: RejectTemplatePatchCommand, actor: ActorContext) -> TemplatePatchDecision:
        with self._decision_lock:
            return self._reject_patch(command, actor)

    def _reject_patch(self, command: RejectTemplatePatchCommand, actor: ActorContext) -> TemplatePatchDecision:
        if not isinstance(command, RejectTemplatePatchCommand) or not isinstance(actor, ActorContext):
            raise _invalid("template patch rejection request is invalid")
        self._require_template_admin(actor)
        if not isinstance(command.reason, str) or not command.reason.strip():
            raise _invalid("template patch rejection reason is required")
        existing_decision: TemplatePatchDecision | None = None
        suggestion_id = command.suggestion_id
        if self._workflow_repository is not None:
            existing, _ = self.patch_for(command.patch_id, actor)
            suggestion_id = existing.suggestion_id
            if isinstance(existing, TemplatePatchDecision):
                candidate = existing.candidate
                existing_decision = existing
            else:
                candidate = existing.candidate
        else:
            _, candidate = self._load_candidate(command.suggestion_id, command.patch_id, actor)
        if command.suggestion_id != suggestion_id:
            raise _conflict("template patch suggestion identity does not match")
        decision = existing_decision or TemplatePatchDecision(
            decision_id=f"template-patch-decision-{command.patch_id}",
            suggestion_id=command.suggestion_id,
            patch_id=command.patch_id,
            workspace_id=actor.workspace_id,
            actor_id=actor.actor_id,
            actor_type=actor.actor_type,
            action="rejected",
            reason=command.reason.strip(),
            base_template_id=candidate.target_template_id,
            base_template_version=candidate.target_template_version,
            base_template_hash=candidate.target_template_hash,
            candidate=candidate,
            new_template_version=None,
            created_at=self._clock(),
        )
        if self._workflow_repository is None:
            self._decisions[command.patch_id] = decision
            return decision
        scope = _scope(
            actor,
            key=command.idempotency_key,
            command="fmea.template.patch.reject",
            resource_path=f"/fmea/template-patches/{command.patch_id}/rejection",
        )
        payload_hash = _payload_hash({
            "suggestion_id": command.suggestion_id,
            "patch_id": command.patch_id,
            "reason": command.reason.strip(),
            "expected_patch_version": command.expected_patch_version,
        })
        try:
            decision, decision_completed = self._workflow_repository.reserve_template_patch_decision(
                decision,
                scope,
                payload_hash,
                expected_patch_version=command.expected_patch_version,
            )
            if decision_completed:
                return decision
            stored, _, _ = self._workflow_repository.save_template_patch_decision(
                decision,
                scope,
                payload_hash,
                expected_patch_version=command.expected_patch_version,
            )
        except ReviewError:
            raise
        except Exception:
            raise ReviewError(
                "FMEA_REVIEW_STORAGE_UNAVAILABLE", "template patch decision storage is unavailable", retryable=True
            ) from None
        return stored

    def decision_for_patch(self, patch_id: str, actor: ActorContext) -> TemplatePatchDecision | None:
        if not isinstance(patch_id, str) or not isinstance(actor, ActorContext):
            raise _invalid("template patch decision query is invalid")
        with self._decision_lock:
            if self._workflow_repository is not None:
                try:
                    item = self._workflow_repository.get_template_patch(patch_id, actor.workspace_id)
                except ReviewError:
                    raise
                except Exception:
                    raise ReviewError(
                        "FMEA_REVIEW_STORAGE_UNAVAILABLE",
                        "template patch storage is unavailable",
                        retryable=True,
                    ) from None
                return item[0] if item is not None and isinstance(item[0], TemplatePatchDecision) else None
            decision = self._decisions.get(patch_id)
            if decision is not None and decision.workspace_id != actor.workspace_id:
                raise _forbidden("template patch decision belongs to another workspace")
            return decision

    def patch_for(
        self, patch_id: str, actor: ActorContext
    ) -> tuple[TemplatePatchSuggestion | TemplatePatchDecision, int]:
        if not isinstance(patch_id, str) or not isinstance(actor, ActorContext):
            raise _invalid("template patch query is invalid")
        if self._workflow_repository is not None:
            try:
                item = self._workflow_repository.get_template_patch(patch_id, actor.workspace_id)
            except ReviewError:
                raise
            except Exception:
                raise ReviewError(
                    "FMEA_REVIEW_STORAGE_UNAVAILABLE", "template patch storage is unavailable", retryable=True
                ) from None
            if item is None:
                raise _invalid("template patch was not found")
            return item
        decision = self._decisions.get(patch_id)
        if decision is not None:
            if decision.workspace_id != actor.workspace_id:
                raise _forbidden("template patch belongs to another workspace")
            return decision, 2
        suggestion = self._suggestions.get(patch_id)
        if suggestion is None:
            raise _invalid("template patch was not found")
        if suggestion.envelope.workspace_id != actor.workspace_id:
            raise _forbidden("template patch belongs to another workspace")
        return suggestion, 1


@dataclass(frozen=True, slots=True)
class _DefaultSourceBuilder:
    def build(
        self,
        base_source: Mapping[str, object],
        draft: TemplateDraft,
        patch: TemplatePatchCandidate,
        new_template_version: str,
    ) -> Mapping[str, object]:
        return _default_source_builder(base_source, draft, patch, new_template_version)


__all__ = [
    "AcceptTemplatePatchCommand",
    "DomainPackService",
    "ImportTemplateCommand",
    "RejectTemplatePatchCommand",
    "SuggestTemplatePatchCommand",
]
