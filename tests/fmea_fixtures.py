from __future__ import annotations

import pytest

from core_domain.fmea.entities import FmeaAnalysis, FmeaRow
from core_domain.fmea.states import (
    FMEA_SCHEMA_ID,
    ClaimStatus,
    EvidenceSupportStatus,
    PublicationStatus,
    ReviewStatus,
)
from core_domain.fmea.value_objects import EvidencePack, EvidenceRef, VersionSet


@pytest.fixture
def fixture_versions() -> VersionSet:
    return VersionSet(
        schema_id=FMEA_SCHEMA_ID,
        data_version="data-1",
        graph_version="graph-1",
        evidence_pack_version="evidence-1",
        profile_version="profile-1",
        template_version="template-1",
        scoring_version="score-1",
        prompt_version="prompt-0",
        model_version="model-0",
        input_snapshot_hash="d" * 64,
    )


@pytest.fixture
def fixture_pack(fixture_versions: VersionSet) -> EvidencePack:
    ref = EvidenceRef(
        evidence_id="ev-1",
        workspace_id="ws-1",
        document_id="doc-1",
        document_version="doc-v1",
        content_hash="e" * 64,
        locator="page:1#span:1",
        quote="pressure is low",
        normalized_quote="pressure is low",
        evidence_hash="f" * 64,
        acl_scope=("engineering",),
        source_type="primary_document",
        source_trust="reviewed",
        is_primary=True,
        created_at="2026-08-23T00:00:00Z",
        expires_at=None,
    )
    return EvidencePack.build(
        pack_id="pack-1",
        workspace_id="ws-1",
        acl_scope=("engineering",),
        versions=fixture_versions,
        refs=(ref,),
        created_at="2026-08-23T00:00:00Z",
        expires_at=None,
    )


@pytest.fixture
def fixture_analysis(fixture_versions: VersionSet) -> FmeaAnalysis:
    return FmeaAnalysis(
        analysis_id="analysis-1",
        project_id="project-1",
        analysis_type="fuel_system",
        lifecycle_stage="draft",
        scope="fuel delivery to combustor interface",
        system_boundary="fuel skid to burner manifold",
        exclusions=("plant electrical distribution",),
        equipment_configuration="configuration-1",
        control_software_version="control-1",
        fuel_type="natural_gas",
        operating_modes=("startup", "steady_state"),
        assumptions=("pressure transmitter is calibrated",),
        limitations=("no transient test data",),
        unanalysed_parts=("upstream pipeline",),
        versions=fixture_versions,
        owner_actor_id="analyst-1",
        reviewer_actor_ids=("reviewer-1",),
        approver_actor_id=None,
        approved_at=None,
        parent_revision_id=None,
        current_revision_id="revision-1",
    )


@pytest.fixture
def fixture_row(fixture_pack: EvidencePack) -> FmeaRow:
    return FmeaRow(
        row_id="row-1",
        analysis_id="analysis-1",
        evidence_pack_id=fixture_pack.pack_id,
        item_id="filter-1",
        function_id="fuel-filter-function",
        failure_mode="low fuel pressure",
        causes=("filter blockage",),
        mechanisms=("flow restriction",),
        effects=("flame instability",),
        symptoms=("pressure alarm",),
        controls=("pressure transmitter",),
        barriers=("trip logic",),
        actions=("inspect filter",),
        risk_assessment=None,
        field_evidence=(("failure_mode", ("ev-1",)),),
        field_support=(("failure_mode", EvidenceSupportStatus.SUPPORTED),),
        claim_status=ClaimStatus.KNOWN,
        review_status=ReviewStatus.DRAFT,
        publication_status=PublicationStatus.UNPUBLISHED,
    )
