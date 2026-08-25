"""FMEA-specific adaptation around the generic structured-output contracts."""
# ruff: noqa: TRY003

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import replace
from functools import lru_cache
from pathlib import Path
from typing import Final, Literal, cast

from core_domain.fmea.states import ClaimStatus, EvidenceSupportStatus
from core_domain.fmea.value_objects import EvidencePack
from core_domain.query_contracts import (
    CitationType,
    citation_type_for_source_type,
    validate_evidence_source_types,
)
from core_domain.structured_generation import GenerationRunResult, GenerationRunStatus
from core_domain.structured_output import ClaimState, CompiledTemplate, JsonValue, StructuredOutputError
from structured_output_application import TemplateCompiler
from structured_output_infrastructure import Draft202012SchemaAdapter, load_template_source

from .review_contracts import (
    EDITABLE_REVIEW_FIELDS,
    ConflictItem,
    EvidenceRequestItem,
    FieldFinding,
    FieldReviewEdit,
    MissingEvidenceItem,
    ReviewAction,
    ReviewContext,
    ReviewEvidenceRef,
    ReviewJudgement,
    ReviewModelRequest,
    ReviewPriority,
    ReviewSuggestionDraft,
)
from .review_errors import ReviewError
from .review_projection import project_evidence_ref

_TEMPLATE_ID: Final[Literal["fmea-row-review"]] = "fmea-row-review"
_TEMPLATE_VERSION: Final[Literal["1.0.0"]] = "1.0.0"
_MAX_TASK_BYTES = 4_000
_ROOT_KEYS = frozenset(
    {
        "recommended_action",
        "field_findings",
        "proposed_edits",
        "evidence_requests",
        "missing_evidence",
        "conflicts",
        "rationale",
    }
)
_UNSAFE_TEXT = re.compile(r"(?i)(?:[a-z]:[\\/]|\\\\|(?<![a-z])//|file://|https?://|\.\.)")


def _invalid_request(message: str) -> ReviewError:
    return ReviewError("FMEA_REVIEW_REQUEST_INVALID", message)


def _invalid_suggestion(message: str) -> ReviewError:
    return ReviewError("FMEA_MODEL_SUGGESTION_INVALID", message)


def _normalized_pack_hash(pack_hash: str) -> str:
    if re.fullmatch(r"sha256:[0-9a-f]{64}", pack_hash):
        return pack_hash
    if re.fullmatch(r"[0-9a-f]{64}", pack_hash):
        return f"sha256:{pack_hash}"
    raise _invalid_request("Evidence pack hash is invalid.")


def _safe_text(value: str) -> str:
    return "redacted" if _UNSAFE_TEXT.search(value) is not None else value


def _safe_value(value: str | tuple[str, ...]) -> str | list[str]:
    if isinstance(value, str):
        return _safe_text(value)
    return [_safe_text(item) for item in value]


@lru_cache(maxsize=1)
def _compiled_template() -> CompiledTemplate:
    root = Path(__file__).resolve().parents[1]
    compiler = TemplateCompiler(
        schema_validator=Draft202012SchemaAdapter(),
        source_loader=load_template_source,
    )
    return compiler.compile_path(root / "templates" / "examples" / "fmea-row-review.yaml")


def _json_object(value: object, message: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise _invalid_suggestion(message)
    return value


def _json_array(value: object, message: str) -> list[object]:
    if not isinstance(value, list):
        raise _invalid_suggestion(message)
    return value


def _json_string(value: object, message: str) -> str:
    if not isinstance(value, str):
        raise _invalid_suggestion(message)
    return value


def _json_evidence_ids(value: object) -> tuple[str, ...]:
    items = _json_array(value, "Evidence IDs must be an array.")
    if not all(isinstance(item, str) for item in items):
        raise _invalid_suggestion("Evidence IDs must contain strings.")
    return tuple(cast(str, item) for item in items)


def _claim_state(collection: str, item: dict[str, object]) -> ClaimState:
    if collection == "conflicts":
        return ClaimState.CONFLICT
    field_name = "recommended_claim_status" if collection == "field_findings" else "claim_status"
    try:
        return ClaimState(_json_string(item[field_name], "Claim status is invalid."))
    except (KeyError, ValueError) as exc:
        raise _invalid_suggestion("Claim status is invalid.") from exc


def _claim_evidence_is_exact(  # noqa: C901
    result: GenerationRunResult,
    payload: dict[str, object],
    allowed_evidence_refs: Mapping[str, ReviewEvidenceRef],
    allowed_evidence_types: tuple[CitationType, ...],
) -> None:
    batch = result.batch
    if batch is None:
        raise _invalid_suggestion("Generation result does not contain a candidate.")
    candidate = batch.candidates[0]
    expected_targets: list[tuple[str, str, tuple[str, ...]]] = []
    for collection in ("field_findings", "proposed_edits", "conflicts"):
        items = _json_array(payload[collection], f"{collection} must be an array.")
        for index, raw_item in enumerate(items):
            item = _json_object(raw_item, f"{collection} item must be an object.")
            evidence_ids = _json_evidence_ids(item["evidence_ids"])
            for evidence_id in evidence_ids:
                ref = allowed_evidence_refs.get(evidence_id)
                if ref is None:
                    raise _invalid_suggestion("Model evidence must come from the projected evidence pack.")
                citation_type = citation_type_for_source_type(ref.source_type)
                if citation_type is None or citation_type not in allowed_evidence_types:
                    raise _invalid_suggestion("Model evidence is outside the resolved profile allowlist.")
            expected_targets.append((f"/{collection}/{index}", collection, evidence_ids))

    claims = {claim.target: claim for claim in candidate.claims}
    if set(claims) != {target for target, _, _ in expected_targets}:
        raise _invalid_suggestion("Candidate claims must exactly cover review evidence fields.")
    for target, collection, evidence_ids in expected_targets:
        claim = claims[target]
        if claim.evidence_ids != evidence_ids:
            raise _invalid_suggestion("Candidate claim evidence must exactly match the payload.")
        item_index = int(target.rsplit("/", 1)[1])
        item = _json_object(_json_array(payload[collection], "Review collection must be an array.")[item_index], "Review item must be an object.")
        if claim.state is not _claim_state(collection, item):
            raise _invalid_suggestion("Candidate claim state does not match the payload.")


class ReviewTemplateAdapter:
    """Map one review context to and from the generic structured-output seam."""

    def build_request(
        self,
        context: ReviewContext,
        evidence_pack: EvidencePack,
        run_id: str,
        *,
        review_policy: Literal["default"],
        focus_fields: tuple[str, ...],
    ) -> ReviewModelRequest:
        if not isinstance(context, ReviewContext) or not isinstance(evidence_pack, EvidencePack):
            raise _invalid_request("Review context and evidence pack are invalid.")
        normalized_hash = _normalized_pack_hash(evidence_pack.pack_hash)
        expected_ids = {ref.evidence_id for ref in context.evidence.refs}
        try:
            validate_evidence_source_types(
                context.retrieval.resolved_profile,
                context.retrieval.evidence_types,
                tuple(ref.source_type for ref in evidence_pack.refs),
                allow_subset=context.retrieval.incomplete,
                allow_empty=context.retrieval.incomplete,
            )
        except ValueError as exc:
            raise _invalid_request("Review retrieval provenance is invalid.") from exc
        if (
            context.evidence.pack_id != evidence_pack.pack_id
            or context.row.evidence_pack_id != evidence_pack.pack_id
            or context.evidence.pack_hash != normalized_hash
            or not expected_ids.issubset({ref.evidence_id for ref in evidence_pack.refs})
            or context.evidence.workspace_id != evidence_pack.workspace_id
        ):
            raise _invalid_request("Evidence pack does not match the review context.")
        projected_by_id = {ref.evidence_id: ref for ref in context.evidence.refs}
        bounded_refs = []
        for ref in evidence_pack.refs:
            if ref.evidence_id not in expected_ids:
                continue
            projected_ref = projected_by_id.get(ref.evidence_id)
            if projected_ref is None or project_evidence_ref(ref) != projected_ref:
                raise _invalid_request("Evidence pack fields do not match the validated review projection.")
            bounded_refs.append(
                replace(
                    ref,
                    source_type=projected_ref.source_type,
                    source_trust=projected_ref.source_trust,
                    is_primary=projected_ref.is_primary,
                    locator=projected_ref.locator,
                    quote=projected_ref.quote,
                )
            )
        bounded_pack = EvidencePack.build(
            pack_id=evidence_pack.pack_id,
            workspace_id=evidence_pack.workspace_id,
            acl_scope=evidence_pack.acl_scope,
            versions=evidence_pack.versions,
            refs=tuple(bounded_refs),
            created_at=evidence_pack.created_at,
            expires_at=evidence_pack.expires_at,
        )
        try:
            request = ReviewModelRequest(
                run_id=run_id,
                context=context,
                evidence_pack=bounded_pack,
                review_policy=review_policy,
                focus_fields=focus_fields,
                template_id=_TEMPLATE_ID,
                template_version=_TEMPLATE_VERSION,
            )
            self.render_task(request)
        except ReviewError:
            raise
        except (TypeError, ValueError) as exc:
            raise _invalid_request("Review model request is invalid.") from exc
        return request

    def render_task(self, request: ReviewModelRequest) -> str:
        """Render only the bounded, canonical advisory task sent to the model."""

        if not isinstance(request, ReviewModelRequest):
            raise _invalid_request("Review model request is invalid.")
        fields = {
            field_review.target_field: {
                "value": _safe_value(field_review.value),
                "claim_status": field_review.claim_status.value,
                "support_status": field_review.support_status.value,
            }
            for field_review in request.context.field_reviews
        }
        if set(fields) != set(EDITABLE_REVIEW_FIELDS):
            raise _invalid_request("Review model request must contain all editable fields.")
        task = json.dumps(
            {
                "item_label": _safe_text(request.context.item_label),
                "function_label": _safe_text(request.context.function_label),
                "fields": fields,
                "allowed_actions": [action.value for action in ReviewAction],
                "focus_fields": list(request.focus_fields),
                "retrieval": {
                    "requested_profile": request.context.retrieval.requested_profile.value,
                    "resolved_profile": request.context.retrieval.resolved_profile.value,
                    "allowed_evidence_types": [item.value for item in request.context.retrieval.evidence_types],
                    "warnings": list(request.context.retrieval.warnings),
                    "incomplete": request.context.retrieval.incomplete,
                },
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        if len(task.encode("utf-8")) > _MAX_TASK_BYTES:
            raise _invalid_request("Rendered review model task exceeds the UTF-8 byte limit.")
        return task

    def decode_draft(self, result: GenerationRunResult, context: ReviewContext) -> ReviewSuggestionDraft:  # noqa: C901
        try:
            if not isinstance(result, GenerationRunResult) or not isinstance(context, ReviewContext):
                raise _invalid_suggestion("Generation result or review context is invalid.")
            if result.status is not GenerationRunStatus.SUCCEEDED or result.batch is None:
                raise _invalid_suggestion("Generation result does not contain one accepted candidate.")
            if len(result.batch.candidates) != 1:
                raise _invalid_suggestion("Generation result must contain exactly one candidate.")
            template = _compiled_template()
            batch = result.batch
            if (
                batch.template_id != _TEMPLATE_ID
                or batch.template_version != _TEMPLATE_VERSION
                or batch.template_hash != template.template_hash
                or batch.evidence_pack_id != context.evidence.pack_id
            ):
                raise _invalid_suggestion("Candidate identity does not match the review template or evidence pack.")
            payload = _json_object(batch.candidates[0].payload, "Candidate payload must be an object.")
            if set(payload) != _ROOT_KEYS:
                raise _invalid_suggestion("Candidate payload contains unknown or missing root fields.")
            schema_issues = Draft202012SchemaAdapter().validate(
                cast(JsonValue, payload),
                template.output_schema,
            )
            if schema_issues:
                raise _invalid_suggestion("Candidate payload does not match the review template schema.")
            _claim_evidence_is_exact(
                result,
                payload,
                {ref.evidence_id: ref for ref in context.evidence.refs},
                context.retrieval.evidence_types,
            )

            action = ReviewAction(_json_string(payload["recommended_action"], "Recommended action is invalid."))
            findings = tuple(
                FieldFinding(
                    target_field=_json_string(item["target_field"], "Finding target field is invalid."),
                    judgement=ReviewJudgement(_json_string(item["judgement"], "Finding judgement is invalid.")),
                    recommended_claim_status=ClaimStatus(
                        _json_string(item["recommended_claim_status"], "Finding claim status is invalid.")
                    ),
                    evidence_ids=_json_evidence_ids(item["evidence_ids"]),
                    rationale=_json_string(item["rationale"], "Finding rationale is invalid."),
                )
                for item in (
                    _json_object(raw_item, "Field finding must be an object.")
                    for raw_item in _json_array(payload["field_findings"], "Field findings must be an array.")
                )
            )
            edits = tuple(
                FieldReviewEdit(
                    target_field=_json_string(item["target_field"], "Edit target field is invalid."),
                    operation=cast(Literal["replace"], _json_string(item["operation"], "Edit operation is invalid.")),
                    value=cast(str | tuple[str, ...], item["value"]),
                    claim_status=ClaimStatus(_json_string(item["claim_status"], "Edit claim status is invalid.")),
                    support_status=EvidenceSupportStatus(
                        _json_string(item["support_status"], "Edit support status is invalid.")
                    ),
                    evidence_ids=_json_evidence_ids(item["evidence_ids"]),
                    reason=_json_string(item["reason"], "Edit reason is invalid."),
                )
                for item in (
                    _json_object(raw_item, "Proposed edit must be an object.")
                    for raw_item in _json_array(payload["proposed_edits"], "Proposed edits must be an array.")
                )
            )
            evidence_requests = tuple(
                EvidenceRequestItem(
                    target_field=_json_string(item["target_field"], "Evidence request target field is invalid."),
                    question=_json_string(item["question"], "Evidence request question is invalid."),
                    preferred_source_types=tuple(
                        _json_string(value, "Evidence request source type is invalid.")
                        for value in _json_array(item["preferred_source_types"], "Source types must be an array.")
                    ),
                    priority=ReviewPriority(_json_string(item["priority"], "Evidence request priority is invalid.")),
                )
                for item in (
                    _json_object(raw_item, "Evidence request must be an object.")
                    for raw_item in _json_array(payload["evidence_requests"], "Evidence requests must be an array.")
                )
            )
            missing_evidence = tuple(
                self._missing_evidence(item)
                for item in (
                    _json_object(raw_item, "Missing evidence item must be an object.")
                    for raw_item in _json_array(payload["missing_evidence"], "Missing evidence must be an array.")
                )
            )
            conflicts = tuple(
                ConflictItem(
                    target_field=_json_string(item["target_field"], "Conflict target field is invalid."),
                    evidence_ids=_json_evidence_ids(item["evidence_ids"]),
                    description=_json_string(item["description"], "Conflict description is invalid."),
                )
                for item in (
                    _json_object(raw_item, "Conflict must be an object.")
                    for raw_item in _json_array(payload["conflicts"], "Conflicts must be an array.")
                )
            )
            if action is ReviewAction.MODIFY_AND_ACCEPT and not edits:
                raise _invalid_suggestion("modify_and_accept requires a proposed edit.")
            if action is ReviewAction.REQUEST_EVIDENCE and not evidence_requests:
                raise _invalid_suggestion("request_evidence requires an evidence request.")
            if action is not ReviewAction.MODIFY_AND_ACCEPT and edits:
                raise _invalid_suggestion("Only modify_and_accept may contain proposed edits.")
            if action is not ReviewAction.REQUEST_EVIDENCE and evidence_requests:
                raise _invalid_suggestion("Only request_evidence may contain evidence requests.")
            return ReviewSuggestionDraft(
                recommended_action=action,
                field_findings=findings,
                proposed_edits=edits,
                evidence_requests=evidence_requests,
                missing_evidence=missing_evidence,
                conflicts=conflicts,
                rationale=_json_string(payload["rationale"], "Review rationale is invalid."),
            )
        except ReviewError:
            raise
        except (KeyError, TypeError, ValueError, StructuredOutputError) as exc:
            raise _invalid_suggestion("Model review suggestion is invalid.") from exc

    @staticmethod
    def _missing_evidence(item: dict[str, object]) -> MissingEvidenceItem:
        return MissingEvidenceItem(
            target_field=_json_string(item["target_field"], "Missing evidence target field is invalid."),
            description=_json_string(item["description"], "Missing evidence description is invalid."),
        )


__all__ = ["ReviewTemplateAdapter"]
