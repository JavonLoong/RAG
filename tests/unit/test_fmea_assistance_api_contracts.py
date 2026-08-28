from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_SRC = REPO_ROOT / "api_server" / "current_console" / "chroma_rag_poc" / "src"
for import_path in (REPO_ROOT, PACKAGE_SRC):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from chroma_rag_poc.fmea_assistance_contracts import (  # noqa: E402
    AnalysisScopeRunBody,
    AssistanceDecisionBody,
)


def _scope_body() -> dict[str, object]:
    return {
        "target_id": "analysis-1",
        "target_record_version": 1,
        "evidence_pack_ids": ["pack-1"],
        "payload": {"question": "Draft the analysis scope."},
        "domain_pack_id": "fuel-combustion",
        "domain_pack_version": "1.0.0",
        "template_id": "fmea-analysis-scope",
        "template_version": "1.0.0",
        "rule_pack_id": "fuel-sod-rpn",
        "rule_pack_version": "1.0.0",
    }


def test_scope_request_is_strict_and_cannot_supply_authority_or_model_fields() -> None:
    assert AnalysisScopeRunBody.model_validate(_scope_body()).target_id == "analysis-1"
    for forbidden in ("actor_id", "actor_type", "roles", "applied", "model", "provider"):
        with pytest.raises(ValidationError):
            AnalysisScopeRunBody.model_validate({**_scope_body(), forbidden: "attacker"})


def test_assistance_decision_requires_typed_human_edit_surface_only() -> None:
    body = AssistanceDecisionBody.model_validate(
        {
            "action": "edit_and_adopt",
            "target_record_version": 3,
            "reason": "Human-reviewed scope edits.",
            "edits": [{"field": "scope", "value": "Fuel delivery and combustion."}],
        }
    )
    assert body.action.value == "edit_and_adopt"
    with pytest.raises(ValidationError):
        AssistanceDecisionBody.model_validate({**body.model_dump(), "resulting_resource_identity": ["x", "y"]})
