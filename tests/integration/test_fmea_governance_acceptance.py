"""Independent Phase 3 governance acceptance tests."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from core_domain.fmea.governance import canonical_hash
from scripts.run_fmea_governance_acceptance import (
    build_normalized_snapshot,
    iter_normalized_snapshot_pages,
    make_large_revision,
    make_normalized_snapshot_input,
    run_acceptance,
)
from scripts.verify_fmea_governance_acceptance import (
    PUBLICATION_BODY_SCHEMA_VERSION,
    _VerificationFailure,
    _verify_new_publication_body,
    verify,
    verify_latest,
)


def _new_body_artifacts(tmp_path: Path) -> tuple[dict[str, object], dict[str, object]]:
    result = run_acceptance(output_root=tmp_path / "acceptance")
    snapshots = json.loads((result.artifact_dir / "snapshots.json").read_text(encoding="utf-8"))["items"]
    snapshot = next(
        item
        for item in snapshots
        if item["version_manifest"].get("body_schema_version") == PUBLICATION_BODY_SCHEMA_VERSION
    )
    revisions = json.loads((result.artifact_dir / "revisions.json").read_text(encoding="utf-8"))["items"]
    revision = next(item for item in revisions if item["revision_id"] == snapshot["revision_id"])
    return deepcopy(snapshot), deepcopy(revision)


def test_acceptance_publishes_with_human_actors_and_replays_withdrawal(tmp_path: Path) -> None:
    result = run_acceptance(output_root=tmp_path / "acceptance")

    assert result["approval_actor_type"] == "human"
    assert result["publisher_actor_type"] == "human"
    assert result["model_publication_count"] == 0
    assert result["withdrawn_publication_retained"] is True
    assert result["replay_checks"] == {"approve": True, "publish": True, "withdraw_publication": True}
    assert verify_latest(tmp_path / "acceptance").passed is True


def test_verifier_rejects_snapshot_hash_mismatch(tmp_path: Path) -> None:
    result = run_acceptance(output_root=tmp_path / "acceptance")
    snapshot_path = result.artifact_dir / "snapshots.json"
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    payload["items"][0]["rows"][0]["failure_mode"] = "tampered"
    snapshot_path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")), encoding="utf-8")

    verification = verify(result.artifact_dir)
    assert verification.error_code == "FMEA_SNAPSHOT_HASH_MISMATCH"


@pytest.mark.parametrize("case", ("missing-row-body", "removed-quoted-ref", "mismatched-decision", "graph", "unsafe-layout"))
def test_new_body_verifier_rejects_structural_counterexamples(tmp_path: Path, case: str) -> None:
    snapshot, revision = _new_body_artifacts(tmp_path)
    if case == "missing-row-body":
        del snapshot["rows"][0]["failure_mode"]
    elif case == "removed-quoted-ref":
        del snapshot["evidence_summary"][0]["refs"][0]
    elif case == "mismatched-decision":
        snapshot["decision_summary"][0]["row_id"] = "missing-row"
    elif case == "unsafe-layout":
        snapshot["version_manifest"]["report_layout"]["columns"][0]["value_path"] = ["row", "__class__"]
    else:
        del snapshot["propagation"]["nodes"]
    snapshot["snapshot_hash"] = canonical_hash(
        {key: value for key, value in snapshot.items() if key != "snapshot_hash"},
        max_array_items=10_000,
    )

    with pytest.raises(_VerificationFailure) as captured:
        _verify_new_publication_body(snapshot, revision)

    assert captured.value.code == "FMEA_SNAPSHOT_BINDING_INVALID"


def test_acceptance_preserves_all_upstream_evidence_profiles(tmp_path: Path) -> None:
    result = run_acceptance(output_root=tmp_path / "acceptance")

    assert result["profile_cases"] == {
        "rag_only": ["text"],
        "graphrag_only": ["graph", "community"],
        "combined": ["text", "graph", "community"],
        "auto": ["text", "graph", "community"],
    }
    assert result["retrieval_call_count"] == 0


def test_ten_thousand_row_snapshot_is_streamable_and_bounded() -> None:
    revision = make_large_revision(row_count=10_000)
    source = make_normalized_snapshot_input(revision=revision, rows=10_000)
    snapshot = build_normalized_snapshot(source)
    pages = tuple(iter_normalized_snapshot_pages(snapshot, page_size=250))

    assert snapshot.row_count == 10_000
    assert len(pages) == 40
    assert max(len(page.rows) for page in pages) == 250
    assert pages[-1].next_offset is None
