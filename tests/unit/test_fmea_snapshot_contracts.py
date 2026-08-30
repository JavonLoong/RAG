from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, replace
from hashlib import sha256

import pytest
from fmea_governance_fixtures import (
    make_large_revision,
    make_normalized_snapshot,
    make_normalized_snapshot_input,
)

from core_domain.fmea.errors import FmeaDomainError
from fmea_application.snapshot_contracts import (
    NormalizedFmeaSnapshot,
    NormalizedSnapshotInput,
    build_normalized_snapshot,
    canonical_json_bytes,
    canonical_normalized_snapshot_body,
    iter_normalized_snapshot_pages,
)


def test_normalized_snapshot_rejects_different_publication_revision() -> None:
    source = make_normalized_snapshot_input()
    with pytest.raises(FmeaDomainError, match="snapshot publication binding"):
        build_normalized_snapshot(replace(source, publication_revision_id="rev-2"))


@pytest.mark.parametrize(
    ("field_name", "value"),
    (
        ("publication_revision_hash", "b" * 64),
        ("publication_workspace_id", "ws-2"),
        ("publication_analysis_id", "analysis-2"),
    ),
)
def test_normalized_snapshot_rejects_mismatched_publication_lineage(field_name: str, value: str) -> None:
    source = make_normalized_snapshot_input()
    with pytest.raises(FmeaDomainError, match="snapshot publication"):
        build_normalized_snapshot(replace(source, **{field_name: value}))


def test_snapshot_input_requires_publication_lineage_fields() -> None:
    assert {
        "publication_revision_id",
        "publication_revision_hash",
        "publication_workspace_id",
        "publication_analysis_id",
    } <= {field.name for field in fields(NormalizedSnapshotInput)}


def test_normalized_snapshot_rejects_valid_format_but_wrong_content_hash() -> None:
    snapshot = make_normalized_snapshot()
    with pytest.raises(FmeaDomainError, match="snapshot hash"):
        replace(snapshot, snapshot_hash="b" * 64)


def test_normalized_snapshot_hash_is_deterministic_for_mapping_order() -> None:
    first = make_normalized_snapshot_input(row_payload={"row_id": "row-1", "z": 1, "a": "stable"})
    second = make_normalized_snapshot_input(row_payload={"a": "stable", "z": 1, "row_id": "row-1"})
    assert build_normalized_snapshot(first).snapshot_hash == build_normalized_snapshot(second).snapshot_hash


def test_normalized_snapshot_hash_is_deterministic_for_collection_order() -> None:
    rows = (
        {"row_id": "row-1", "failure_mode": "low pressure"},
        {"row_id": "row-2", "failure_mode": "high pressure"},
    )
    risk_records = (
        {"assessment_id": "assessment-1", "status": "confirmed"},
        {"assessment_id": "assessment-2", "status": "confirmed"},
    )
    evidence_summary = (
        {"pack_id": "pack-1", "evidence_count": 1},
        {"pack_id": "pack-2", "evidence_count": 2},
    )
    decision_summary = (
        {"decision_id": "decision-1", "action": "accept"},
        {"decision_id": "decision-2", "action": "reject"},
    )
    first = make_normalized_snapshot_input(
        rows=rows,
        risk_records=risk_records,
        evidence_summary=evidence_summary,
        decision_summary=decision_summary,
    )
    second = make_normalized_snapshot_input(
        rows=tuple(reversed(rows)),
        risk_records=tuple(reversed(risk_records)),
        evidence_summary=tuple(reversed(evidence_summary)),
        decision_summary=tuple(reversed(decision_summary)),
    )
    assert build_normalized_snapshot(first).snapshot_hash == build_normalized_snapshot(second).snapshot_hash


def test_normalized_snapshot_rejects_duplicate_keys_after_strip() -> None:
    with pytest.raises(FmeaDomainError, match="duplicate object keys"):
        make_normalized_snapshot_input(row_payload={"row_id": "row-1", " row_id ": "row-2"})


def test_normalized_snapshot_is_immutable_and_pages_are_bounded() -> None:
    snapshot = make_normalized_snapshot(rows=5)
    assert isinstance(snapshot, NormalizedFmeaSnapshot)
    assert snapshot.row_count == 5
    pages = list(iter_normalized_snapshot_pages(snapshot, page_size=2))
    assert [len(page.rows) for page in pages] == [2, 2, 1]
    assert [page.next_offset for page in pages] == [2, 4, None]
    with pytest.raises(FrozenInstanceError):
        snapshot.snapshot_id = "changed"  # type: ignore[misc]


def test_normalized_snapshot_rejects_invalid_page_size() -> None:
    snapshot = make_normalized_snapshot()
    with pytest.raises(ValueError, match="page_size must be between 1 and 500"):
        list(iter_normalized_snapshot_pages(snapshot, page_size=0))
    with pytest.raises(ValueError, match="page_size must be between 1 and 500"):
        list(iter_normalized_snapshot_pages(snapshot, page_size=501))


def test_normalized_snapshot_rejects_non_export_safe_fields() -> None:
    with pytest.raises(FmeaDomainError, match="snapshot contains non-export-safe field"):
        make_normalized_snapshot_input(row_payload={"prompt": "secret instruction"})


@pytest.mark.parametrize(
    "unsafe_value",
    (
        "file:///etc/shadow",
        "s3://bucket/object",
        "https://example.com/private",
        "\\\\server\\share\\secret.txt",
        "C:\\secret\\file.txt",
        "/etc/shadow",
    ),
)
def test_normalized_snapshot_rejects_all_absolute_or_uri_paths(unsafe_value: str) -> None:
    with pytest.raises(FmeaDomainError, match="snapshot contains non-export-safe value"):
        make_normalized_snapshot_input(row_payload={"description": unsafe_value})


def test_large_snapshot_keeps_page_contract_bounded() -> None:
    revision = make_large_revision(10_000)
    source = make_normalized_snapshot_input(revision=revision, rows=10_000)
    snapshot = build_normalized_snapshot(source)
    pages = list(iter_normalized_snapshot_pages(snapshot, page_size=500))
    assert len(revision.row_versions) == 10_000
    assert snapshot.row_count == 10_000
    assert sum(len(page.rows) for page in pages) == 10_000
    assert [page.next_offset for page in pages[:-1]] == list(range(500, 10_000, 500))
    assert pages[-1].next_offset is None
    assert snapshot.snapshot_hash == sha256(
        canonical_json_bytes(canonical_normalized_snapshot_body(source), max_array_items=10_000)
    ).hexdigest()
