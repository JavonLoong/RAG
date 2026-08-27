from __future__ import annotations

from dataclasses import FrozenInstanceError
from types import MappingProxyType

import pytest

from core_domain.fmea.states import ActorType
from fmea_application.assistance_contracts import (
    AssistanceDecision,
    AssistanceDecisionAction,
    AssistanceKind,
    AssistanceRequest,
    AssistanceSuggestion,
    _json_value,
)

_MISSING = object()
_IDEMPOTENCY_KEY = "00000000-0000-4abc-8def-000000000001"


def _suggestion(*, applied: bool = False, payload: object = _MISSING, **overrides: object) -> AssistanceSuggestion[object]:
    values: dict[str, object] = {
        "suggestion_id": "suggestion-1",
        "kind": AssistanceKind.SCORE_RECOMMENDATION,
        "workspace_id": "ws-1",
        "target_type": "fmea_row",
        "target_id": "row-1",
        "target_record_version": 3,
        "evidence_pack_ids": ("pack-1",),
        "payload": {"severity": 7} if payload is _MISSING else payload,
        "evidence_ids": ("ev-1",),
        "conflict_ids": (),
        "uncertainty": "low",
        "model_hash": "a" * 64,
        "prompt_hash": "b" * 64,
        "run_id": "run-1",
        "trace_id": "trace-1",
        "created_at": "2026-08-27T00:00:00Z",
        "applied": applied,
    }
    values.update(overrides)
    return AssistanceSuggestion(**values)  # type: ignore[arg-type]


def _request(**overrides: object) -> AssistanceRequest[object]:
    values: dict[str, object] = {
        "request_id": "request-1",
        "kind": AssistanceKind.REVIEW_SUMMARY,
        "workspace_id": "ws-1",
        "target_type": "fmea_row",
        "target_id": "row-1",
        "target_record_version": 3,
        "evidence_pack_ids": ("pack-1",),
        "payload": {"focus": "missing evidence"},
    }
    values.update(overrides)
    return AssistanceRequest(**values)  # type: ignore[arg-type]


def _decision(suggestion: AssistanceSuggestion[object] | None = None, **overrides: object) -> AssistanceDecision:
    suggestion = _suggestion() if suggestion is None else suggestion
    values: dict[str, object] = {
        "decision_id": "decision-1",
        "suggestion_id": suggestion.suggestion_id,
        "suggestion_hash": suggestion.suggestion_hash,
        "suggestion_record_version": suggestion.record_version,
        "target_record_version": suggestion.target_record_version,
        "action": AssistanceDecisionAction.ADOPT,
        "actor_id": "reviewer-1",
        "actor_type": ActorType.HUMAN,
        "edits": (),
        "reason": "accepted after review",
        "idempotency_key": _IDEMPOTENCY_KEY,
        "resulting_resource_identity": ("fmea_row", "row-1"),
        "created_at": "2026-08-27T00:00:00Z",
    }
    values.update(overrides)
    return AssistanceDecision(**values)  # type: ignore[arg-type]


def test_assistance_is_immutable_unapplied_and_version_bound() -> None:
    suggestion = _suggestion()
    assert suggestion.applied is False
    assert suggestion.target_record_version == 3
    assert suggestion.evidence_pack_ids == ("pack-1",)
    with pytest.raises(FrozenInstanceError):
        suggestion.applied = True


def test_assistance_suggestion_cannot_be_created_as_applied() -> None:
    with pytest.raises(ValueError, match="applied"):
        _suggestion(applied=True)


def test_assistance_decision_is_human_and_binds_exact_suggestion() -> None:
    suggestion = _suggestion()
    decision = AssistanceDecision(
        decision_id="decision-1",
        suggestion_id=suggestion.suggestion_id,
        suggestion_hash=suggestion.suggestion_hash,
        suggestion_record_version=suggestion.record_version,
        target_record_version=suggestion.target_record_version,
        action=AssistanceDecisionAction.ADOPT,
        actor_id="reviewer-1",
        actor_type=ActorType.HUMAN,
        edits=(),
        reason="accepted after review",
        idempotency_key=_IDEMPOTENCY_KEY,
        resulting_resource_identity=("fmea_row", "row-1"),
        created_at="2026-08-27T00:00:00Z",
    )
    assert decision.action is AssistanceDecisionAction.ADOPT
    assert decision.actor_type is ActorType.HUMAN

    with pytest.raises(ValueError, match="human actor"):
        AssistanceDecision(
            decision_id="decision-2",
            suggestion_id=suggestion.suggestion_id,
            suggestion_hash=suggestion.suggestion_hash,
            suggestion_record_version=suggestion.record_version,
            target_record_version=suggestion.target_record_version,
            action=AssistanceDecisionAction.ADOPT,
            actor_id="model-1",
            actor_type=ActorType.MODEL,
            edits=(),
            reason="model cannot adopt",
            idempotency_key="00000000-0000-4000-8000-000000000002",
            resulting_resource_identity=None,
            created_at="2026-08-27T00:00:00Z",
        )


def test_assistance_request_normalizes_version_bound_identities() -> None:
    request = _request(evidence_pack_ids=["pack-1"])
    assert request.evidence_pack_ids == ("pack-1",)


def test_assistance_payload_is_a_deep_frozen_input_snapshot() -> None:
    source = {"nested": {"items": [{"severity": 7}]}}
    suggestion = _suggestion(payload=source)

    source["nested"]["items"][0]["severity"] = 1
    source["nested"]["items"].append({"severity": 2})

    assert isinstance(suggestion.payload, MappingProxyType)
    assert suggestion.payload["nested"]["items"][0]["severity"] == 7  # type: ignore[index]
    with pytest.raises(TypeError):
        suggestion.payload["nested"]["items"][0]["severity"] = 1  # type: ignore[index]
    with pytest.raises(AttributeError):
        suggestion.payload["nested"]["items"].append({"severity": 2})  # type: ignore[attr-defined,index]


def test_json_value_supports_mapping_and_keeps_canonical_keys() -> None:
    value = MappingProxyType({"b": (2,), "a": MappingProxyType({"x": True})})

    assert _json_value(value) == {"a": {"x": True}, "b": [2]}


def test_assistance_rejects_non_string_keys_without_string_collision() -> None:
    with pytest.raises(ValueError, match="key must be a string"):
        _suggestion(payload={1: "integer", "1": "string"})


def test_assistance_rejects_unordered_ids_and_requires_evidence_pack() -> None:
    with pytest.raises(ValueError, match="tuple or list"):
        _suggestion(evidence_pack_ids={"pack-1"})
    with pytest.raises(ValueError, match="tuple or list"):
        _suggestion(evidence_pack_ids=(item for item in ("pack-1",)))
    with pytest.raises(ValueError, match="at least one"):
        _suggestion(evidence_pack_ids=[])
    with pytest.raises(ValueError, match="duplicates"):
        _suggestion(evidence_ids=["ev-1", "ev-1"])


@pytest.mark.parametrize(
    ("payload", "message"),
    (
        (object(), "JSON scalar"),
        (float("nan"), "finite"),
        (float("inf"), "finite"),
        ({"secret": "do not persist"}, "forbidden"),
        ({"API-KEY": "do not persist"}, "forbidden"),
        ({"text": "x" * 4097}, "4096"),
    ),
)
def test_assistance_rejects_unsupported_or_sensitive_payloads(payload: object, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        _suggestion(payload=payload)


def test_assistance_rejects_payload_beyond_depth_and_canonical_size_limits() -> None:
    too_deep: object = True
    for _ in range(9):
        too_deep = {"nested": too_deep}
    too_large = {"items": tuple("x" * 4096 for _ in range(16))}

    with pytest.raises(ValueError, match="depth"):
        _suggestion(payload=too_deep)
    with pytest.raises(ValueError, match="canonical payload"):
        _suggestion(payload=too_large)


@pytest.mark.parametrize(
    "overrides",
    (
        {"domain_pack_id": "domain-1"},
        {"domain_pack_version": "1.0.0"},
        {"template_id": "template-1"},
        {"template_version": "1.0.0"},
        {"rule_pack_id": "rule-1"},
        {"rule_pack_version": "1.0.0"},
    ),
)
def test_assistance_requires_complete_domain_template_and_rule_pairs(overrides: dict[str, str]) -> None:
    with pytest.raises(ValueError, match="both ID and version"):
        _suggestion(**overrides)
    with pytest.raises(ValueError, match="both ID and version"):
        _request(**overrides)


def test_assistance_request_payload_is_deep_frozen_and_bounded() -> None:
    source = {"focus": ["evidence"]}
    request = _request(payload=source)
    source["focus"].append("secret")

    assert request.payload["focus"] == ("evidence",)  # type: ignore[index]
    with pytest.raises(TypeError):
        request.payload["focus"] = ("changed",)  # type: ignore[index]


def test_assistance_decision_requires_canonical_idempotency_and_timestamp() -> None:
    with pytest.raises(ValueError, match="lowercase UUID"):
        _decision(idempotency_key="idempotency-1")
    with pytest.raises(ValueError, match="lowercase UUID"):
        _decision(idempotency_key=_IDEMPOTENCY_KEY.upper())
    with pytest.raises(ValueError, match="created_at"):
        _decision(created_at="")


@pytest.mark.parametrize(
    "action",
    (
        AssistanceDecisionAction.ADOPT,
        AssistanceDecisionAction.REJECT,
        AssistanceDecisionAction.DEFER,
        AssistanceDecisionAction.REQUEST_EVIDENCE,
    ),
)
def test_assistance_non_edit_actions_require_empty_edits(action: AssistanceDecisionAction) -> None:
    with pytest.raises(ValueError, match="must not contain edits"):
        _decision(action=action, edits=(("controls", "corrected"),))


@pytest.mark.parametrize("action", (AssistanceDecisionAction.PARTIAL_ADOPT, AssistanceDecisionAction.EDIT_AND_ADOPT))
def test_assistance_edit_actions_require_edits(action: AssistanceDecisionAction) -> None:
    with pytest.raises(ValueError, match="must contain edits"):
        _decision(action=action, edits=())


def test_assistance_adopt_and_non_adopt_result_identity_invariants() -> None:
    with pytest.raises(ValueError, match="resulting_resource_identity"):
        _decision(resulting_resource_identity=None)
    with pytest.raises(ValueError, match="resulting_resource_identity"):
        _decision(action=AssistanceDecisionAction.REJECT, resulting_resource_identity=("fmea_row", "row-1"))


def test_assistance_decision_edits_are_deep_frozen_unique_and_bounded() -> None:
    source = {"nested": [1]}
    decision = _decision(action=AssistanceDecisionAction.EDIT_AND_ADOPT, edits=[("controls", source)])
    source["nested"].append(2)

    assert decision.edits[0][1]["nested"] == (1,)  # type: ignore[index]
    with pytest.raises(TypeError):
        decision.edits[0][1]["nested"] = (2,)  # type: ignore[index]
    with pytest.raises(ValueError, match="unique"):
        _decision(action=AssistanceDecisionAction.EDIT_AND_ADOPT, edits=(("controls", 1), ("controls", 2)))
    with pytest.raises(ValueError, match="32"):
        _decision(
            action=AssistanceDecisionAction.EDIT_AND_ADOPT,
            edits=tuple((f"field-{index}", index) for index in range(33)),
        )


def test_assistance_edit_payload_rejects_sensitive_fields_and_canonical_size() -> None:
    with pytest.raises(ValueError, match="forbidden"):
        _decision(action=AssistanceDecisionAction.EDIT_AND_ADOPT, edits=(("raw-prompt", "value"),))
    too_large = tuple((f"field-{index}", "x" * 4096) for index in range(16))
    with pytest.raises(ValueError, match="canonical edits"):
        _decision(action=AssistanceDecisionAction.EDIT_AND_ADOPT, edits=too_large)


def test_assistance_human_actor_validation_does_not_guess_from_actor_id() -> None:
    decision = _decision(actor_id="model-1")

    assert decision.actor_id == "model-1"
