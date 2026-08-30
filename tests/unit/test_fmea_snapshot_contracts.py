from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest
from fmea_governance_fixtures import (
    make_large_revision,
    make_normalized_snapshot,
    make_normalized_snapshot_input,
)

from core_domain.fmea.errors import FmeaDomainError
from fmea_application.snapshot_contracts import (
    NormalizedFmeaSnapshot,
    build_normalized_snapshot,
    iter_normalized_snapshot_pages,
)


def test_normalized_snapshot_rejects_different_publication_revision() -> None:
    with pytest.raises(FmeaDomainError, match="snapshot publication binding"):
        make_normalized_snapshot(revision_id="rev-1", publication_revision_id="rev-2")


def test_normalized_snapshot_hash_is_deterministic_for_mapping_order() -> None:
    first = make_normalized_snapshot_input(row_payload={"z": 1, "a": "stable"})
    second = make_normalized_snapshot_input(row_payload={"a": "stable", "z": 1})
    assert build_normalized_snapshot(first).snapshot_hash == build_normalized_snapshot(second).snapshot_hash


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


def test_large_snapshot_keeps_page_contract_bounded() -> None:
    revision = make_large_revision(10_000)
    assert len(revision.row_versions) == 10_000
