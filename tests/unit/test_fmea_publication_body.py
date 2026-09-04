from __future__ import annotations

import json
from dataclasses import replace
from hashlib import sha256

import pytest
from fmea_governance_fixtures import (
    make_assemble_request,
    make_governance_assembler,
    make_governance_inputs,
    make_governance_source,
)

from core_domain.fmea.entities import FieldClaim, FieldValue, FmeaRow
from core_domain.fmea.errors import FmeaDomainError
from core_domain.fmea.scoring import RiskAssessment, RiskAssessmentRecord, ScoreDimension
from core_domain.fmea.states import (
    ClaimStatus,
    EvidenceSupportStatus,
    PropagationStatus,
    ReviewStatus,
    RiskStatus,
)
from core_domain.fmea.value_objects import EvidencePack


def _contracts():
    try:
        from fmea_application.publication_body import PublicationReviewRecord, _project_publication_body
    except ModuleNotFoundError as exc:
        pytest.fail(f"publication body contract is missing: {exc}")
    return PublicationReviewRecord, _project_publication_body


def _production_evidence_pack(fixture_pack: EvidencePack, *, locator: str | None = None) -> EvidencePack:
    locator = locator or json.dumps({"page": 1, "span": 1}, sort_keys=True, separators=(",", ":"))
    ref = fixture_pack.refs[0]
    identity = json.dumps(
        {
            "source_type": ref.source_type,
            "document_id": ref.document_id,
            "document_version": ref.document_version,
            "locator": locator,
            "normalized_quote": ref.normalized_quote,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    ref = replace(ref, locator=locator, evidence_hash=sha256(identity.encode("utf-8")).hexdigest())
    return EvidencePack.build(
        pack_id=fixture_pack.pack_id,
        workspace_id=fixture_pack.workspace_id,
        acl_scope=fixture_pack.acl_scope,
        versions=fixture_pack.versions,
        refs=(ref,),
        created_at=fixture_pack.created_at,
        expires_at=fixture_pack.expires_at,
    )


def _publication_inputs(fixture_pack: EvidencePack, fixture_row: FmeaRow):
    pack = _production_evidence_pack(fixture_pack)
    extension_key = "fuel.pressure_drop"
    domain_pack = replace(
        make_governance_inputs().domain_pack,
        extension_fields=((extension_key, "decimal"),),
    )
    row = replace(
        fixture_row,
        review_status=ReviewStatus.ACCEPTED,
        extension_values=(FieldValue(extension_key, "decimal", "48.2"),),
        field_claims=(
            FieldClaim("failure_mode", ClaimStatus.KNOWN, EvidenceSupportStatus.SUPPORTED, ("ev-1",)),
            FieldClaim(extension_key, ClaimStatus.KNOWN, EvidenceSupportStatus.SUPPORTED, ("ev-1",)),
        ),
    )
    inputs = make_governance_inputs(rows=(row,), evidence_packs=(pack,), domain_pack=domain_pack)
    source = make_governance_source(inputs)
    revision = make_governance_assembler(inputs).assemble(make_assemble_request(), inputs)
    return inputs, source, revision, row, pack


def _review_record(revision, row, **overrides):
    PublicationReviewRecord, _ = _contracts()
    values = {
        "decision_id": "decision-1",
        "workspace_id": row.analysis_id.replace("analysis", "ws"),
        "analysis_id": row.analysis_id,
        "row_id": row.row_id,
        "record_version": row.record_version,
        "row_hash": revision.row_versions[0][2],
        "public_fields": {
            "role_category": "human_reviewer",
            "decision": "accepted",
            "reason": "reviewed against the cited source",
            "decided_at": "2026-09-04T00:00:00Z",
        },
    }
    values.update(overrides)
    return PublicationReviewRecord(**values)


def _confirmed_risk() -> RiskAssessmentRecord:
    dimensions = tuple(
        ScoreDimension(name, value, ("ev-1",), reason, None)
        for name, value, reason in (
            ("severity", 9, "high consequence"),
            ("occurrence", 4, "observed frequency"),
            ("detection", 3, "online detection"),
        )
    )
    return RiskAssessmentRecord(
        assessment_id="assessment-1",
        workspace_id="ws-1",
        row_id="row-1",
        source_record_version=1,
        evidence_pack_id="pack-1",
        domain_pack_id="generic-domain",
        domain_pack_version="1.0.0",
        rule_pack_id="generic-scoring",
        rule_pack_version="1.0.0",
        status=RiskStatus.CONFIRMED,
        dimensions=dimensions,
        derived=RiskAssessment(
            severity_by_consequence_class=(("safety", 9),),
            decision_severity=9,
            occurrence=4,
            detection=3,
            rpn=108,
            decision_priority="critical",
            inherent_risk=None,
            current_risk=None,
            target_residual_risk=None,
            verified_residual_risk=None,
            uncertainty=None,
            reason="confirmed",
            scoring_rule_pack_id="generic-scoring",
            scoring_rule_pack_version="1.0.0",
            evidence_ids=("ev-1",),
        ),
        proposal_id="proposal-1",
        assistance_suggestion_id=None,
        confirmer_actor_id="reviewer-1",
        invalidated_reason=None,
        record_version=1,
        created_at="2026-09-04T00:00:00Z",
        updated_at="2026-09-04T00:00:00Z",
    )


def test_runtime_source_projects_version_bound_full_row_and_safe_evidence(
    fixture_pack: EvidencePack,
    fixture_row: FmeaRow,
) -> None:
    inputs, source, revision, row, pack = _publication_inputs(fixture_pack, fixture_row)
    review = _review_record(revision, row)

    body = source.build_publication_body(revision, inputs, review_records=(review,))

    assert body.rows[0]["failure_mode"] == row.failure_mode
    assert body.rows[0]["record_version"] == row.record_version
    assert body.rows[0]["row_hash"] == revision.row_versions[0][2]
    assert body.rows[0]["field_claims"]
    assert body.rows[0]["extension_values"][0]["value"] == "48.2"
    assert body.evidence_summary[0]["pack_hash"] == pack.pack_hash
    assert body.evidence_summary[0]["refs"][0]["locator"] == {"page": 1, "span": 1}
    assert "acl_scope" not in body.evidence_summary[0]["refs"][0]


def test_projector_preserves_confirmed_native_risk_without_rescoring(
    fixture_pack: EvidencePack,
    fixture_row: FmeaRow,
) -> None:
    pack = _production_evidence_pack(fixture_pack)
    row = replace(fixture_row, review_status=ReviewStatus.ACCEPTED)
    risk = _confirmed_risk()
    inputs = make_governance_inputs(rows=(row,), risk_records=(risk,), evidence_packs=(pack,))
    source = make_governance_source(inputs)
    revision = make_governance_assembler(inputs).assemble(make_assemble_request(), inputs)

    body = source.build_publication_body(revision, inputs, review_records=(_review_record(revision, row),))

    assert body.risk_records[0]["status"] == "confirmed"
    assert body.risk_records[0]["derived"]["rpn"] == 108
    assert body.risk_records[0]["dimensions"][0]["value"] == 3


def test_projector_preserves_confirmed_propagation_and_row_lineage(
    fixture_pack: EvidencePack,
    fixture_row: FmeaRow,
) -> None:
    from fmea_propagation_fixtures import _graph

    pack = _production_evidence_pack(fixture_pack)
    row = replace(fixture_row, review_status=ReviewStatus.ACCEPTED)
    graph = replace(
        _graph("ws-1"),
        domain_pack_id="generic-domain",
        rule_pack_id="generic-propagation",
        status=PropagationStatus.CONFIRMED,
    )
    inputs = make_governance_inputs(rows=(row,), propagation_graph_revision=graph, evidence_packs=(pack,))
    source = make_governance_source(inputs)
    revision = make_governance_assembler(inputs).assemble(make_assemble_request(), inputs)

    body = source.build_publication_body(revision, inputs, review_records=(_review_record(revision, row),))

    assert body.propagation is not None
    assert body.propagation["status"] == "confirmed"
    assert body.propagation["topology_hash"] == "1" * 64
    assert body.propagation["edges"][0]["evidence_ids"] == ("ev-1",)


def test_projected_publication_body_is_deeply_immutable(
    fixture_pack: EvidencePack,
    fixture_row: FmeaRow,
) -> None:
    inputs, source, revision, row, _ = _publication_inputs(fixture_pack, fixture_row)
    body = source.build_publication_body(revision, inputs, review_records=(_review_record(revision, row),))

    with pytest.raises(TypeError):
        body.rows[0]["failure_mode"] = "changed"  # type: ignore[index]
    with pytest.raises(TypeError):
        body.rows[0]["field_claims"][0]["claim_status"] = "changed"  # type: ignore[index]


def test_projector_rejects_missing_review_record(
    fixture_pack: EvidencePack,
    fixture_row: FmeaRow,
) -> None:
    inputs, source, revision, _row, _ = _publication_inputs(fixture_pack, fixture_row)

    with pytest.raises(FmeaDomainError, match="FMEA_PUBLICATION_BODY_INCOMPLETE"):
        source.build_publication_body(revision, inputs, review_records=())


def test_runtime_source_rejects_cross_runtime_attestation(
    fixture_pack: EvidencePack,
    fixture_row: FmeaRow,
) -> None:
    first_inputs, first_source, first_revision, first_row, _ = _publication_inputs(fixture_pack, fixture_row)
    second_inputs, _second_source, _second_revision, _second_row, _ = _publication_inputs(fixture_pack, fixture_row)
    review = _review_record(first_revision, first_row)

    with pytest.raises(ValueError, match="attestation"):
        first_source.build_publication_body(first_revision, second_inputs, review_records=(review,))


def test_projector_rejects_recomputed_row_hash_mismatch(
    fixture_pack: EvidencePack,
    fixture_row: FmeaRow,
) -> None:
    inputs, _source, revision, row, _ = _publication_inputs(fixture_pack, fixture_row)
    _, projector = _contracts()
    tampered_inputs = replace(inputs, rows=(replace(row, failure_mode="tampered"),))
    review = _review_record(revision, row)

    with pytest.raises(FmeaDomainError, match="FMEA_PUBLICATION_BODY_STALE"):
        projector(revision, tampered_inputs, review_records=(review,))


def test_projector_rejects_recomputed_row_version_mismatch(
    fixture_pack: EvidencePack,
    fixture_row: FmeaRow,
) -> None:
    inputs, _source, revision, row, _ = _publication_inputs(fixture_pack, fixture_row)
    _, projector = _contracts()
    tampered_inputs = replace(inputs, rows=(replace(row, record_version=2),))
    review = _review_record(revision, row)

    with pytest.raises(FmeaDomainError, match="FMEA_PUBLICATION_BODY_STALE"):
        projector(revision, tampered_inputs, review_records=(review,))


@pytest.mark.parametrize("field_name", ("record_version", "row_hash", "workspace_id"))
def test_projector_rejects_review_record_not_bound_to_selected_row(
    fixture_pack: EvidencePack,
    fixture_row: FmeaRow,
    field_name: str,
) -> None:
    inputs, _source, revision, row, _ = _publication_inputs(fixture_pack, fixture_row)
    _, projector = _contracts()
    review = _review_record(revision, row, **{field_name: 2 if field_name == "record_version" else "b" * 64 if field_name == "row_hash" else "ws-2"})

    with pytest.raises(FmeaDomainError, match="FMEA_PUBLICATION_BODY_STALE"):
        projector(revision, inputs, review_records=(review,))


def test_projector_rejects_evidence_content_hash_mismatch_before_projection(
    fixture_pack: EvidencePack,
    fixture_row: FmeaRow,
) -> None:
    inputs, _source, revision, row, pack = _publication_inputs(fixture_pack, fixture_row)
    _, projector = _contracts()
    tampered_ref = replace(pack.refs[0], normalized_quote="tampered quote")
    tampered_pack = replace(pack, refs=(tampered_ref,))
    tampered_inputs = replace(inputs, evidence_packs=(tampered_pack,))
    review = _review_record(revision, row)

    with pytest.raises(FmeaDomainError, match="FMEA_PUBLICATION_BODY_STALE"):
        projector(revision, tampered_inputs, review_records=(review,))


def test_projector_rejects_unsafe_locator_without_dropping_evidence(
    fixture_pack: EvidencePack,
    fixture_row: FmeaRow,
) -> None:
    inputs, _source, revision, row, pack = _publication_inputs(fixture_pack, fixture_row)
    _, projector = _contracts()
    unsafe_pack = _production_evidence_pack(fixture_pack, locator="https://private.example/source")
    unsafe_inputs = replace(inputs, evidence_packs=(unsafe_pack,))
    review = _review_record(revision, row)

    with pytest.raises(FmeaDomainError, match="FMEA_PUBLICATION_BODY_UNSAFE"):
        projector(revision, unsafe_inputs, review_records=(review,))


def test_projector_preserves_unknown_status_and_empty_bindings(
    fixture_pack: EvidencePack,
    fixture_row: FmeaRow,
) -> None:
    pack = _production_evidence_pack(fixture_pack)
    unknown_row = replace(
        fixture_row,
        claim_status=ClaimStatus.UNKNOWN,
        field_evidence=(),
        field_support=(),
        field_claims=(),
        review_status=ReviewStatus.ACCEPTED,
    )
    inputs = make_governance_inputs(rows=(unknown_row,), evidence_packs=(pack,))
    source = make_governance_source(inputs)
    revision = make_governance_assembler(inputs).assemble(make_assemble_request(), inputs)

    body = source.build_publication_body(revision, inputs, review_records=(_review_record(revision, unknown_row),))

    assert body.rows[0]["claim_status"] == "unknown"
    assert body.rows[0]["field_evidence"] == ()
    assert body.rows[0]["field_claims"] == ()


def test_projector_stably_sorts_rows_and_reviews(
    fixture_pack: EvidencePack,
    fixture_row: FmeaRow,
) -> None:
    pack = _production_evidence_pack(fixture_pack)
    row_a = replace(fixture_row, row_id="row-a", review_status=ReviewStatus.ACCEPTED)
    row_b = replace(fixture_row, row_id="row-b", review_status=ReviewStatus.ACCEPTED)
    inputs = make_governance_inputs(rows=(row_b, row_a), evidence_packs=(pack,))
    source = make_governance_source(inputs)
    revision = make_governance_assembler(inputs).assemble(make_assemble_request(), inputs)
    row_hashes = {row_id: row_hash for row_id, _version, row_hash in revision.row_versions}
    reviews = tuple(
        _review_record(
            revision,
            row,
            decision_id=f"decision-{row.row_id}",
            row_hash=row_hashes[row.row_id],
        )
        for row in (row_b, row_a)
    )

    body = source.build_publication_body(revision, inputs, review_records=reviews)

    assert tuple(row["row_id"] for row in body.rows) == ("row-a", "row-b")
    assert tuple(item["decision_id"] for item in body.decision_summary) == ("decision-row-a", "decision-row-b")
