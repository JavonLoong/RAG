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

from chroma_rag_poc.fmea_risk_contracts import (  # noqa: E402
    RiskConfirmationBody,
    RiskProposalBody,
    RiskRejectionBody,
)


def _proposal_body() -> dict[str, object]:
    return {
        "evidence_pack_id": "pack-1",
        "domain_pack_id": "fuel-combustion",
        "domain_pack_version": "1.0.0",
        "template_id": "fmea-risk-proposal",
        "template_version": "1.0.0",
        "rule_pack_id": "fuel-sod-rpn",
        "rule_pack_version": "1.0.0",
    }


def test_risk_proposal_contract_forbids_model_and_server_owned_fields() -> None:
    assert RiskProposalBody.model_validate(_proposal_body()).rule_pack_id == "fuel-sod-rpn"
    for forbidden in ("actor_id", "actor_type", "status", "dimensions", "model", "provider"):
        with pytest.raises(ValidationError):
            RiskProposalBody.model_validate({**_proposal_body(), forbidden: "attacker"})


def test_risk_human_transition_bodies_are_minimal_and_strict() -> None:
    assert RiskConfirmationBody.model_validate({"proposal_id": "proposal-1"}).proposal_id == "proposal-1"
    rejection = RiskRejectionBody.model_validate({"proposal_id": "proposal-1", "reason": "Evidence is insufficient."})
    assert rejection.reason == "Evidence is insufficient."
    with pytest.raises(ValidationError):
        RiskConfirmationBody.model_validate({"proposal_id": "proposal-1", "confirmed": True})
