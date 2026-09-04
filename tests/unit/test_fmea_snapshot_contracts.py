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
    revalidate_normalized_snapshot,
    snapshot_content_hash,
)


def _forge_snapshot(snapshot: NormalizedFmeaSnapshot, **overrides: object) -> NormalizedFmeaSnapshot:
    forged = object.__new__(NormalizedFmeaSnapshot)
    for field in fields(snapshot):
        object.__setattr__(forged, field.name, getattr(snapshot, field.name))
    for field_name, value in overrides.items():
        object.__setattr__(forged, field_name, value)
    return forged


class ExplosiveSnapshotValue:
    _ERROR = "secret snapshot value"

    def __init__(self) -> None:
        self.calls: list[str] = []

    def _explode(self, operation: str):
        self.calls.append(operation)
        raise RuntimeError(self._ERROR)

    def __eq__(self, other):
        return self._explode("eq")

    def __str__(self):
        return self._explode("str")

    def __hash__(self):
        return self._explode("hash")

    def __len__(self):
        return self._explode("len")


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


@pytest.mark.parametrize(
    "overrides",
    (
        {"row_count": 0},
        {"schema_version": "not-normalized-v99"},
    ),
)
def test_shared_revalidation_rejects_hash_consistent_constructor_invariant_bypass(overrides: dict[str, object]) -> None:
    snapshot = make_normalized_snapshot()
    forged = _forge_snapshot(snapshot, **overrides)
    object.__setattr__(forged, "snapshot_hash", snapshot_content_hash(forged))

    with pytest.raises(FmeaDomainError) as captured:
        revalidate_normalized_snapshot(forged)

    assert str(captured.value) == "snapshot revalidation failed"
    assert captured.value.__cause__ is None


def test_shared_revalidation_rejects_malicious_nested_value_without_invoking_its_protocols() -> None:
    snapshot = make_normalized_snapshot()
    malicious = ExplosiveSnapshotValue()
    forged = _forge_snapshot(
        snapshot,
        rows=({"row_id": "row-1", "value": malicious},),
        row_count=1,
    )

    with pytest.raises(FmeaDomainError) as captured:
        revalidate_normalized_snapshot(forged)

    assert str(captured.value) == "snapshot revalidation failed"
    assert captured.value.__cause__ is None
    assert malicious.calls == []


def test_shared_revalidation_rejects_reserved_preview_marker_in_plain_nested_value() -> None:
    marker = "DRAFT PREVIEW — NOT PUBLISHED"
    snapshot = make_normalized_snapshot()
    forged = _forge_snapshot(
        snapshot,
        rows=({"row_id": "row-1", "nested": {"value": f"private {marker} value"}},),
        row_count=1,
    )
    object.__setattr__(forged, "snapshot_hash", snapshot_content_hash(forged))

    with pytest.raises(FmeaDomainError) as captured:
        revalidate_normalized_snapshot(forged)

    assert str(captured.value) == "snapshot revalidation failed"
    assert captured.value.__cause__ is None
    assert marker not in str(captured.value)
    assert "private" not in str(captured.value)


def test_shared_revalidation_returns_a_fresh_exact_immutable_snapshot() -> None:
    snapshot = make_normalized_snapshot()

    rebuilt = revalidate_normalized_snapshot(snapshot)

    assert type(rebuilt) is NormalizedFmeaSnapshot
    assert rebuilt is not snapshot
    assert rebuilt == snapshot


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


@pytest.mark.parametrize(
    ("field_name", "identity_field"),
    (
        ("rows", "row_id"),
        ("risk_records", "assessment_id"),
        ("evidence_summary", "pack_id"),
        ("decision_summary", "decision_id"),
    ),
)
def test_normalized_snapshot_rejects_duplicate_stable_identities(
    field_name: str,
    identity_field: str,
) -> None:
    duplicate_items = (
        {identity_field: "duplicate-1", "value": 1},
        {identity_field: "duplicate-1", "value": 2},
    )
    with pytest.raises(FmeaDomainError, match=f"{field_name} must not contain duplicate identities"):
        make_normalized_snapshot_input(**{field_name: duplicate_items})


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


def test_legacy_snapshot_without_publication_body_marker_remains_accepted() -> None:
    source = make_normalized_snapshot_input()
    snapshot = build_normalized_snapshot(source)

    assert "body_schema_version" not in snapshot.version_manifest
    assert snapshot.rows[0]["failure_mode"] == "low pressure"


def test_publication_body_marker_rejects_summary_rows() -> None:
    source = make_normalized_snapshot_input()
    with pytest.raises(FmeaDomainError, match="publication body is incomplete"):
        build_normalized_snapshot(
            replace(
                source,
                rows=({"row_id": "row-1", "failure_mode": "summary"},),
                version_manifest={
                    **source.version_manifest,
                    "body_schema_version": "graphrag.fmea.body.v1",
                },
            )
        )


def _marked_publication_body_source(**overrides: object) -> NormalizedSnapshotInput:
    source = make_normalized_snapshot_input()
    row = {
        "row_id": "row-1",
        "analysis_id": source.publication_analysis_id,
        "evidence_pack_id": "pack-1",
        "item_id": "item-1",
        "function_id": "function-1",
        "failure_mode": "low pressure",
        "causes": (),
        "mechanisms": (),
        "effects": (),
        "symptoms": (),
        "controls": (),
        "barriers": (),
        "actions": (),
        "risk_assessment": None,
        "claim_status": "unknown",
        "review_status": "accepted",
        "publication_status": "unpublished",
        "record_version": 1,
        "row_hash": "a" * 64,
        "field_evidence": (),
        "field_support": (),
        "field_claims": (),
        "extension_values": (),
        "unknown_extension": {"preserve": True},
    }
    decision = {
        "record_type": "row_review",
        "decision_id": "decision-1",
        "workspace_id": source.publication_workspace_id,
        "analysis_id": source.publication_analysis_id,
        "row_id": "row-1",
        "record_version": 1,
        "row_hash": "a" * 64,
        "role_category": "human_reviewer",
        "decision": "accepted",
        "reason": "reviewed",
        "decided_at": "2026-09-04T00:00:00Z",
    }
    values: dict[str, object] = {
        "rows": (row,),
        "risk_records": (),
        "propagation": None,
        "evidence_summary": (
            {
                "pack_id": "pack-1",
                "pack_hash": "b" * 64,
                "evidence_pack_version": "1",
                "refs": (),
            },
        ),
        "decision_summary": (decision,),
        "version_manifest": {
            **source.version_manifest,
            "body_schema_version": "graphrag.fmea.body.v1",
        },
    }
    values.update(overrides)
    return replace(source, **values)


def test_marked_publication_body_accepts_optional_empty_risk_and_graph_sections() -> None:
    source = _marked_publication_body_source()

    snapshot = build_normalized_snapshot(source)

    assert snapshot.risk_records == ()
    assert snapshot.propagation is None
    assert snapshot.rows[0]["unknown_extension"] == {"preserve": True}


def test_marked_publication_body_rejects_explicit_null_schema_marker() -> None:
    with pytest.raises(FmeaDomainError, match="publication body schema version"):
        make_normalized_snapshot_input(
            version_manifest={
                "schema_id": "graphrag.fmea.v1",
                "domain_pack": "fuel-combustion@1.0.0",
                "body_schema_version": None,
            }
        )


def test_marked_publication_body_rejects_null_required_row_value() -> None:
    source = _marked_publication_body_source()
    row = dict(source.rows[0])
    row["failure_mode"] = None

    with pytest.raises(FmeaDomainError, match="publication body is incomplete"):
        build_normalized_snapshot(replace(source, rows=(row,)))


def test_marked_publication_body_rejects_missing_evidence_reference() -> None:
    source = _marked_publication_body_source()
    row = dict(source.rows[0])
    row["field_evidence"] = ({"field_key": "failure_mode", "evidence_ids": ("ev-missing",)},)

    with pytest.raises(FmeaDomainError, match="publication body is incomplete"):
        build_normalized_snapshot(replace(source, rows=(row,)))


def test_marked_publication_body_rejects_review_reference_for_wrong_row_hash() -> None:
    source = _marked_publication_body_source()
    decision = dict(source.decision_summary[0])
    decision["row_hash"] = "b" * 64

    with pytest.raises(FmeaDomainError, match="publication body is incomplete"):
        build_normalized_snapshot(replace(source, decision_summary=(decision,)))


def test_marked_publication_body_rejects_section_over_minimum_bound() -> None:
    source = _marked_publication_body_source()
    decisions = tuple(
        {
            **source.decision_summary[0],
            "decision_id": f"decision-{index}",
        }
        for index in range(501)
    )

    with pytest.raises(FmeaDomainError, match="publication body is incomplete"):
        build_normalized_snapshot(replace(source, decision_summary=decisions))


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
    assert (
        snapshot.snapshot_hash
        == sha256(canonical_json_bytes(canonical_normalized_snapshot_body(source), max_array_items=10_000)).hexdigest()
    )
