from __future__ import annotations

import pytest
from chroma_rag_poc.fmea_propagation_contracts import (
    PropagationEdgeDecisionBody,
    PropagationReviewBody,
    PropagationStartBody,
)
from pydantic import ValidationError


def valid_start_body() -> dict[str, object]:
    return {
        "source_row_ids": ["row-1"],
        "evidence_pack_id": "pack-1",
    }


def test_propagation_start_contract_is_strict_and_bounded() -> None:
    body = PropagationStartBody.model_validate(valid_start_body())
    assert body.record_version == 1
    assert body.source_row_ids == ["row-1"]

    with pytest.raises(ValidationError):
        PropagationStartBody.model_validate({**valid_start_body(), "model": "client-selected"})
    with pytest.raises(ValidationError):
        PropagationStartBody.model_validate({**valid_start_body(), "source_row_ids": ["row-1", "row-1"]})
    with pytest.raises(ValidationError):
        PropagationStartBody.model_validate({**valid_start_body(), "analysis_id": "client-override"})


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("topology_id", "client-topology"),
        ("topology_version", "9.9.9"),
        ("domain_pack_id", "client-domain"),
        ("domain_pack_version", "9.9.9"),
        ("rule_pack_id", "client-rule"),
        ("rule_pack_version", "9.9.9"),
    ],
)
def test_propagation_start_contract_rejects_server_resource_overrides(
    field_name: str,
    value: str,
) -> None:
    with pytest.raises(ValidationError):
        PropagationStartBody.model_validate({**valid_start_body(), field_name: value})


def test_propagation_review_contract_rejects_unknown_fields_and_unbounded_reason() -> None:
    valid = {
        "edge_decisions": [{"edge_id": "edge-1", "action": "accept", "reason": "accepted"}],
        "acknowledgements": [],
    }
    assert PropagationReviewBody.model_validate(valid).edge_decisions[0].action == "accept"

    with pytest.raises(ValidationError):
        PropagationReviewBody.model_validate({**valid, "provider": "client-override"})
    with pytest.raises(ValidationError):
        PropagationEdgeDecisionBody.model_validate(
            {"edge_id": "edge-1", "action": "accept", "reason": "x" * 4097}
        )


def test_propagation_request_models_reject_coercion() -> None:
    with pytest.raises(ValidationError):
        PropagationStartBody.model_validate({**valid_start_body(), "evidence_pack_id": 1})
    with pytest.raises(ValidationError):
        PropagationReviewBody.model_validate(
            {"edge_decisions": [{"edge_id": "edge-1", "action": "accept", "reason": "ok"}], "acknowledgements": "x"}
        )
