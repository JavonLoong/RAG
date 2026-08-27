from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from uuid import UUID

import pytest

from core_domain.fmea.states import ActorType
from fmea_application.assistance_contracts import (
    AssistanceDecision,
    AssistanceDecisionAction,
    AssistanceKind,
    AssistanceSuggestion,
)
from fmea_application.ports import AssistanceRepository
from fmea_application.review_contracts import AuditEvent, IdempotencyScope, idempotency_key_hash
from fmea_application.risk_contracts import (
    PreparedAssistanceDecision,
    PreparedAssistanceSuggestion,
    assistance_decision_payload_hash,
    assistance_suggestion_payload_hash,
)

HASH = "sha256:" + "a" * 64
UUID_KEY = "00000000-0000-4000-8000-000000000001"


def audit_event(
    *,
    actor_id: str = "model-1",
    actor_type: ActorType = ActorType.MODEL,
    decision_id: str | None = None,
    canonical_hash: str = HASH,
    key_hash: str = HASH,
) -> AuditEvent:
    from core_domain.fmea.value_objects import VersionSet

    return AuditEvent(
        event_id="event-1",
        occurred_at_server="2026-01-01T00:00:00Z",
        workspace_id="ws-1",
        actor_id=actor_id,
        actor_type=actor_type,
        actor_roles=(),
        command="fmea.assistance",
        action=None,
        reason_code=None,
        reason="model suggestion",
        analysis_id="analysis-1",
        row_id="row-1",
        suggestion_id="suggestion-1",
        decision_id=decision_id,
        expected_record_version=3,
        applied_record_version=None,
        before_hash=None,
        after_hash=None,
        changed_fields=(),
        evidence_ids=("e-1",),
        evidence_request_targets=(),
        idempotency_key_hash=key_hash,
        canonical_payload_hash=canonical_hash,
        versions=VersionSet(
            schema_id="graphrag.fmea.v1",
            data_version="1.0.0",
            graph_version="1.0.0",
            evidence_pack_version="1.0.0",
            profile_version="1.0.0",
            template_version="1.0.0",
            scoring_version="1.0.0",
            prompt_version="1.0.0",
            model_version="1.0.0",
            input_snapshot_hash=HASH,
        ),
        template_id="fuel-fmea",
        template_version="1.0.0",
        profile_id="combined",
        profile_version="1.0.0",
        model_manifest=None,
        request_id="request-1",
        trace_id="trace-1",
        retrieval_trace_id="retrieval-1",
    )


def suggestion() -> AssistanceSuggestion[object]:
    return AssistanceSuggestion(
        suggestion_id="suggestion-1",
        kind=AssistanceKind.SCORE_RECOMMENDATION,
        workspace_id="ws-1",
        target_type="fmea_row",
        target_id="row-1",
        target_record_version=3,
        evidence_pack_ids=("pack-1",),
        payload={"score": 9},
        evidence_ids=("e-1",),
        model_hash=HASH,
        prompt_hash=HASH,
        run_id="run-1",
        trace_id="trace-1",
        domain_pack_id="fuel-combustion",
        domain_pack_version="1.0.0",
        template_id="fuel-fmea",
        template_version="1.0.0",
        rule_pack_id="fuel-sod-rpn",
        rule_pack_version="1.0.0",
        created_at="2026-01-01T00:00:00Z",
    )


def decision(suggestion_value: AssistanceSuggestion[object]) -> AssistanceDecision:
    return AssistanceDecision(
        decision_id="decision-1",
        suggestion_id=suggestion_value.suggestion_id,
        suggestion_hash=suggestion_value.suggestion_hash,
        suggestion_record_version=suggestion_value.record_version,
        target_record_version=suggestion_value.target_record_version,
        action=AssistanceDecisionAction.ADOPT,
        actor_id="reviewer-1",
        actor_type=ActorType.HUMAN,
        edits=(),
        reason="reviewed",
        idempotency_key=UUID_KEY,
        resulting_resource_identity=("fmea_row", "row-1"),
        created_at="2026-01-01T00:00:00Z",
    )


def scope(actor_id: str) -> IdempotencyScope:
    key_hash = idempotency_key_hash(UUID_KEY) if actor_id == "reviewer-1" else HASH
    return IdempotencyScope(
        workspace_id="ws-1",
        actor_id=actor_id,
        command="fmea.assistance",
        resource_path="/fmea/rows/row-1",
        key_hash=key_hash,
    )


def prepared_suggestion() -> PreparedAssistanceSuggestion:
    saved_suggestion = suggestion()
    prepared_hash = assistance_suggestion_payload_hash(scope("model-1"), saved_suggestion)
    return PreparedAssistanceSuggestion(
        scope=scope("model-1"),
        payload_hash=prepared_hash,
        suggestion=saved_suggestion,
        audit=audit_event(canonical_hash=prepared_hash),
    )


def prepared_decision() -> PreparedAssistanceDecision:
    saved_suggestion = suggestion()
    prepared_hash = assistance_decision_payload_hash(scope("reviewer-1"), saved_suggestion, decision(saved_suggestion))
    return PreparedAssistanceDecision(
        scope=scope("reviewer-1"),
        payload_hash=prepared_hash,
        suggestion=saved_suggestion,
        decision=decision(saved_suggestion),
        audit=audit_event(
            actor_id="reviewer-1",
            actor_type=ActorType.HUMAN,
            decision_id="decision-1",
            canonical_hash=prepared_hash,
            key_hash=scope("reviewer-1").key_hash,
        ),
    )


def test_prepared_assistance_suggestion_is_immutable_and_workspace_bound() -> None:
    prepared = prepared_suggestion()

    assert prepared.suggestion.applied is False
    assert prepared.scope.workspace_id == prepared.suggestion.workspace_id
    with pytest.raises(FrozenInstanceError):
        prepared.payload_hash = HASH


def test_prepared_assistance_decision_reuses_existing_decision_and_requires_exact_binding() -> None:
    saved_suggestion = suggestion()
    prepared = prepared_decision()

    assert prepared.decision is not None
    assert prepared.decision.suggestion_hash == saved_suggestion.suggestion_hash

    mismatched = replace(prepared.decision, suggestion_hash=HASH)
    with pytest.raises(ValueError, match="suggestion hash"):
        PreparedAssistanceDecision(
            scope=prepared.scope,
            payload_hash=prepared.payload_hash,
            suggestion=saved_suggestion,
            decision=mismatched,
            audit=prepared.audit,
        )

    wrong_scope = replace(prepared.scope, key_hash=HASH)
    wrong_hash = assistance_decision_payload_hash(wrong_scope, saved_suggestion, prepared.decision)
    with pytest.raises(ValueError, match="idempotency key"):
        PreparedAssistanceDecision(
            scope=wrong_scope,
            payload_hash=wrong_hash,
            suggestion=saved_suggestion,
            decision=prepared.decision,
            audit=replace(
                prepared.audit,
                idempotency_key_hash=wrong_scope.key_hash,
                canonical_payload_hash=wrong_hash,
            ),
        )


def test_prepared_assistance_decision_rejects_model_actor_and_cross_workspace() -> None:
    saved_suggestion = suggestion()
    human_decision = decision(saved_suggestion)
    with pytest.raises(ValueError, match="human actor"):
        decision(replace(human_decision, actor_id="model-1", actor_type=ActorType.MODEL))

    with pytest.raises(ValueError, match="workspace"):
        PreparedAssistanceSuggestion(
            scope=replace(scope("model-1"), workspace_id="ws-2"),
            payload_hash=HASH,
            suggestion=saved_suggestion,
            audit=audit_event(),
        )


def test_prepared_assistance_payload_hash_is_bound_to_body_and_audit() -> None:
    prepared = prepared_suggestion()
    forged_hash = "sha256:" + "c" * 64
    with pytest.raises(ValueError, match="payload hash does not match canonical payload"):
        PreparedAssistanceSuggestion(
            scope=prepared.scope,
            payload_hash=forged_hash,
            suggestion=prepared.suggestion,
            audit=prepared.audit,
        )

    with pytest.raises(ValueError, match="audit canonical payload hash"):
        PreparedAssistanceSuggestion(
            scope=prepared.scope,
            payload_hash=prepared.payload_hash,
            suggestion=prepared.suggestion,
            audit=replace(prepared.audit, canonical_payload_hash=forged_hash),
        )

    decision_prepared = prepared_decision()
    with pytest.raises(ValueError, match="payload hash does not match canonical payload"):
        PreparedAssistanceDecision(
            scope=decision_prepared.scope,
            payload_hash=forged_hash,
            suggestion=decision_prepared.suggestion,
            decision=decision_prepared.decision,
            audit=decision_prepared.audit,
        )


def test_assistance_repository_port_exposes_append_only_operations_without_infrastructure_imports() -> None:
    assert {"save_suggestion", "get_suggestion", "append_decision", "get_decision", "replay_decision"}.issubset(
        AssistanceRepository.__dict__
    )
    assert all("infrastructure" not in str(annotation) for annotation in AssistanceRepository.__dict__.values())
    assert UUID(UUID_KEY).version == 4
