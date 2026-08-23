from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from hashlib import sha256

import pytest

from core_domain.fmea.errors import FmeaDomainError
from core_domain.fmea.states import (
    FMEA_SCHEMA_ID,
    ActorType,
    ClaimStatus,
    EvidenceSupportStatus,
    PublicationStatus,
    ReviewStatus,
    RunStatus,
)
from core_domain.fmea.value_objects import EvidencePack, EvidenceRef, VersionSet


def _versions() -> VersionSet:
    return VersionSet(
        schema_id=FMEA_SCHEMA_ID,
        data_version="data-2026-08-23",
        graph_version="graph-7",
        evidence_pack_version="evidence-1",
        profile_version="gas-turbine-1",
        template_version="canonical-1",
        scoring_version="risk-1",
        prompt_version="prompt-0",
        model_version="model-0",
        input_snapshot_hash="a" * 64,
    )


def _ref(evidence_id: str = "ev-1") -> EvidenceRef:
    return EvidenceRef(
        evidence_id=evidence_id,
        workspace_id="ws-1",
        document_id="doc-1",
        document_version="doc-v1",
        content_hash="b" * 64,
        locator="page:4#span:2",
        quote="Fuel pressure falls below the threshold.",
        normalized_quote="fuel pressure falls below the threshold.",
        evidence_hash=sha256(b"Fuel pressure falls below the threshold.").hexdigest(),
        acl_scope=("engineering",),
        source_type="primary_document",
        source_trust="reviewed",
        is_primary=True,
        created_at="2026-08-23T00:00:00Z",
        expires_at=None,
    )


def test_state_axes_and_schema_are_exact() -> None:
    assert FMEA_SCHEMA_ID == "graphrag.fmea.v1"
    assert [item.value for item in ClaimStatus] == [
        "known", "unknown", "insufficient_evidence", "conflict", "not_applicable"
    ]
    assert [item.value for item in ReviewStatus] == [
        "draft", "suggested", "in_review", "accepted", "rejected", "superseded"
    ]
    assert [item.value for item in PublicationStatus] == ["unpublished", "published", "withdrawn"]
    assert [item.value for item in ActorType] == ["human", "model", "system"]
    assert [item.value for item in RunStatus] == [
        "queued", "running", "cancelling", "cancelled", "succeeded", "failed"
    ]
    assert [item.value for item in EvidenceSupportStatus] == [
        "supported", "partially_supported", "contradicted", "not_supported"
    ]


def test_evidence_pack_hash_is_deterministic_and_immutable() -> None:
    first = EvidencePack.build(
        pack_id="pack-1",
        workspace_id="ws-1",
        acl_scope=("engineering",),
        versions=_versions(),
        refs=(_ref(),),
        created_at="2026-08-23T00:00:00Z",
        expires_at=None,
    )
    second = EvidencePack.build(
        pack_id="pack-1",
        workspace_id="ws-1",
        acl_scope=("engineering",),
        versions=_versions(),
        refs=(_ref(),),
        created_at="2026-08-23T00:00:00Z",
        expires_at=None,
    )

    assert first.pack_hash == second.pack_hash

    ordered = EvidencePack.build(
        pack_id="pack-1",
        workspace_id="ws-1",
        acl_scope=("engineering",),
        versions=_versions(),
        refs=(_ref("ev-1"), _ref("ev-2")),
        created_at="2026-08-23T00:00:00Z",
        expires_at=None,
    )
    reversed_order = EvidencePack.build(
        pack_id="pack-1",
        workspace_id="ws-1",
        acl_scope=("engineering",),
        versions=_versions(),
        refs=(_ref("ev-2"), _ref("ev-1")),
        created_at="2026-08-23T00:00:00Z",
        expires_at=None,
    )
    changed_hash = EvidencePack.build(
        pack_id="pack-1",
        workspace_id="ws-1",
        acl_scope=("engineering",),
        versions=_versions(),
        refs=(replace(_ref(), evidence_hash="c" * 64),),
        created_at="2026-08-23T00:00:00Z",
        expires_at=None,
    )
    changed_locator = EvidencePack.build(
        pack_id="pack-1",
        workspace_id="ws-1",
        acl_scope=("engineering",),
        versions=_versions(),
        refs=(replace(_ref(), locator="page:9#span:1"),),
        created_at="2026-08-23T00:00:00Z",
        expires_at=None,
    )

    assert ordered.pack_hash == reversed_order.pack_hash
    assert changed_hash.pack_hash != first.pack_hash
    assert changed_locator.pack_hash != first.pack_hash
    assert first.ref_by_id("ev-1") == first.refs[0]
    assert first.ref_by_id("missing") is None
    with pytest.raises(FrozenInstanceError):
        first.pack_id = "changed"


def test_evidence_pack_rejects_duplicate_ids_and_bad_schema() -> None:
    with pytest.raises(FmeaDomainError, match="duplicate evidence_id"):
        EvidencePack.build(
            pack_id="pack-1",
            workspace_id="ws-1",
            acl_scope=("engineering",),
            versions=_versions(),
            refs=(_ref("ev-1"), _ref("ev-1")),
            created_at="2026-08-23T00:00:00Z",
            expires_at=None,
        )

    with pytest.raises(FmeaDomainError, match="graphrag.fmea.v1"):
        VersionSet(
            schema_id="graphrag.query.v1",
            data_version="data-1",
            graph_version="graph-1",
            evidence_pack_version="evidence-1",
            profile_version="profile-1",
            template_version="template-1",
            scoring_version="score-1",
            prompt_version="prompt-0",
            model_version="model-0",
            input_snapshot_hash="c" * 64,
        )


@pytest.mark.parametrize(
    "field_name",
    (
        "evidence_id",
        "workspace_id",
        "document_id",
        "document_version",
        "content_hash",
        "evidence_hash",
        "quote",
        "normalized_quote",
    ),
)
def test_evidence_ref_rejects_empty_identity_hash_and_quote_values(field_name: str) -> None:
    with pytest.raises(FmeaDomainError, match=field_name):
        replace(_ref(), **{field_name: ""})


def test_evidence_pack_rejects_cross_workspace_refs() -> None:
    with pytest.raises(FmeaDomainError, match="workspace_id"):
        EvidencePack.build(
            pack_id="pack-1",
            workspace_id="ws-1",
            acl_scope=("engineering",),
            versions=_versions(),
            refs=(replace(_ref(), workspace_id="ws-2"),),
            created_at="2026-08-23T00:00:00Z",
            expires_at=None,
        )


def test_evidence_pack_rejects_acl_scope_outside_pack_scope() -> None:
    with pytest.raises(FmeaDomainError, match="acl_scope"):
        EvidencePack.build(
            pack_id="pack-1",
            workspace_id="ws-1",
            acl_scope=("engineering",),
            versions=_versions(),
            refs=(replace(_ref(), acl_scope=("engineering", "restricted")),),
            created_at="2026-08-23T00:00:00Z",
            expires_at=None,
        )
