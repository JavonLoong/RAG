"""Independent Phase 3 governance acceptance tests."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.run_fmea_governance_acceptance import (
    build_normalized_snapshot,
    iter_normalized_snapshot_pages,
    make_large_revision,
    make_normalized_snapshot_input,
    run_acceptance,
)
from scripts.verify_fmea_governance_acceptance import verify, verify_latest


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
