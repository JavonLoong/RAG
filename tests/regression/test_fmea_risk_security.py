from __future__ import annotations

import json
import sys
from hashlib import sha256
from pathlib import Path

import pytest

from scripts.run_fmea_risk_acceptance import AcceptanceRunError, run_acceptance
from scripts.verify_fmea_risk_acceptance import AcceptanceVerificationError, verify_acceptance_directory

PRIVATE_MARKERS = (
    b"Authorization",
    b"Bearer ",
    b"DEEPSEEK_API_KEY",
    b"sk-",
    b"C:\\private",
    b"REQUEST_PRIVATE_MARKER",
    b"EVIDENCE_PRIVATE_MARKER",
)


def _canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _expect_verification_error(directory: Path, code: str) -> None:
    with pytest.raises(AcceptanceVerificationError) as captured:
        verify_acceptance_directory(directory)
    assert captured.value.code == code
    assert str(captured.value) == "FMEA risk acceptance verification failed."


def test_acceptance_artifacts_contain_no_secret_or_private_path(tmp_path: Path) -> None:
    result = run_acceptance(tmp_path / "runs")

    for payload in result.artifact_bytes:
        assert all(marker not in payload for marker in PRIVATE_MARKERS)


def test_model_can_propose_but_cannot_confirm_or_invalidate(tmp_path: Path) -> None:
    result = run_acceptance(tmp_path / "runs")
    confirmation = json.loads((result.artifact_dir / "confirmation.json").read_text(encoding="utf-8"))
    invalidation = json.loads((result.artifact_dir / "invalidation.json").read_text(encoding="utf-8"))

    assert confirmation["actor"]["actor_type"] == "human"
    assert confirmation["replay"]["decision_id"] == confirmation["decision_id"]
    assert invalidation["actor"]["actor_type"] == "system"
    assert result["model_confirmation_count"] == 0


def test_runner_rejects_a_loaded_retrieval_backend(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "chromadb.acceptance_probe", object())

    with pytest.raises(AcceptanceRunError) as captured:
        run_acceptance(tmp_path / "runs")

    assert captured.value.code == "BACKEND_ISOLATION_VIOLATION"


def test_verifier_rejects_tampered_artifact_even_when_json_is_recanonicalized(tmp_path: Path) -> None:
    result = run_acceptance(tmp_path / "runs")
    proposal_path = result.artifact_dir / "proposal.json"
    proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
    proposal["proposals"][0]["dimensions"][0]["value"] = 1
    proposal_path.write_bytes(_canonical(proposal))

    _expect_verification_error(result.artifact_dir, "ARTIFACT_HASH_MISMATCH")


def test_verifier_rejects_rule_that_is_not_applicable_after_hashes_are_recomputed(tmp_path: Path) -> None:
    result = run_acceptance(tmp_path / "runs")
    proposal_path = result.artifact_dir / "proposal.json"
    proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
    proposal["analysis_type"] = "software_fmea"
    proposal_bytes = _canonical(proposal)
    proposal_path.write_bytes(proposal_bytes)

    summary_path = result.artifact_dir / "acceptance-summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["artifact_hashes"]["proposal.json"] = "sha256:" + sha256(proposal_bytes).hexdigest()
    summary_path.write_bytes(_canonical(summary))

    _expect_verification_error(result.artifact_dir, "RULE_APPLICABILITY_INVALID")


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("missing", "ARTIFACT_SET_INVALID"),
        ("extra", "ARTIFACT_SET_INVALID"),
        ("duplicate_case", "CASE_MATRIX_INVALID"),
        ("private_marker", "OUTPUT_PRIVATE_MARKER"),
    ],
)
def test_verifier_rejects_partial_extra_duplicate_or_private_artifacts(
    tmp_path: Path,
    mutation: str,
    expected_code: str,
) -> None:
    result = run_acceptance(tmp_path / mutation)
    if mutation == "missing":
        (result.artifact_dir / "audit-summary.json").unlink()
    elif mutation == "extra":
        (result.artifact_dir / "extra.json").write_bytes(b"{}\n")
    elif mutation == "duplicate_case":
        summary_path = result.artifact_dir / "acceptance-summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        summary["cases"][-1] = "confirmed"
        summary_path.write_bytes(_canonical(summary))
    else:
        summary_path = result.artifact_dir / "acceptance-summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        summary["operator_note"] = "DEEPSEEK_API_KEY"
        summary_path.write_bytes(_canonical(summary))

    _expect_verification_error(result.artifact_dir, expected_code)
