from __future__ import annotations

import json
from dataclasses import replace

import pytest

from core_domain.fmea.codec import decode_evidence_pack, encode_json
from core_domain.fmea.errors import FmeaDomainError
from core_domain.fmea.value_objects import EvidencePack


def test_supplemental_evidence_pack_hashes_lineage_envelope(fixture_pack: EvidencePack) -> None:
    supplemental = EvidencePack.build(
        pack_id="pack-2",
        workspace_id="ws-1",
        acl_scope=fixture_pack.acl_scope,
        versions=fixture_pack.versions,
        refs=fixture_pack.refs,
        created_at=fixture_pack.created_at,
        expires_at=None,
        parent_pack_refs=((fixture_pack.pack_id, fixture_pack.pack_hash),),
        lineage_reason="evidence refresh",
        lineage_schema_version="graphrag.fmea.evidence-lineage.v1",
    )
    changed = EvidencePack.build(
        pack_id="pack-2",
        workspace_id="ws-1",
        acl_scope=fixture_pack.acl_scope,
        versions=fixture_pack.versions,
        refs=fixture_pack.refs,
        created_at=fixture_pack.created_at,
        expires_at=None,
        parent_pack_refs=((fixture_pack.pack_id, fixture_pack.pack_hash),),
        lineage_reason="different reason",
        lineage_schema_version="graphrag.fmea.evidence-lineage.v1",
    )
    assert supplemental.pack_hash != changed.pack_hash
    assert decode_evidence_pack(encode_json(supplemental)) == supplemental


def test_legacy_evidence_pack_json_keeps_old_canonical_bytes(fixture_pack: EvidencePack) -> None:
    payload = json.loads(encode_json(fixture_pack))
    payload.pop("parent_pack_refs", None)
    payload.pop("lineage_reason", None)
    payload.pop("lineage_schema_version", None)
    legacy_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    assert encode_json(decode_evidence_pack(legacy_json)) == legacy_json


def test_lineage_rejects_unknown_hash_workspace_mismatch_and_cycles(fixture_pack: EvidencePack) -> None:
    from core_domain.fmea.value_objects import validate_evidence_lineage

    unknown = replace(
        fixture_pack,
        pack_id="pack-2",
        parent_pack_refs=(("missing", "c" * 64),),
        lineage_reason="refresh",
        lineage_schema_version="graphrag.fmea.evidence-lineage.v1",
    )
    with pytest.raises(FmeaDomainError, match="unknown parent"):
        validate_evidence_lineage(unknown, (fixture_pack,))

    mismatch = replace(
        fixture_pack,
        pack_id="pack-2",
        parent_pack_refs=((fixture_pack.pack_id, "c" * 64),),
        lineage_reason="refresh",
        lineage_schema_version="graphrag.fmea.evidence-lineage.v1",
    )
    with pytest.raises(FmeaDomainError, match="parent pack hash"):
        validate_evidence_lineage(mismatch, (fixture_pack,))

    cross_workspace = replace(fixture_pack, workspace_id="ws-2")
    candidate = replace(
        fixture_pack,
        pack_id="pack-2",
        parent_pack_refs=((cross_workspace.pack_id, cross_workspace.pack_hash),),
        lineage_reason="refresh",
        lineage_schema_version="graphrag.fmea.evidence-lineage.v1",
    )
    with pytest.raises(FmeaDomainError, match="workspace"):
        validate_evidence_lineage(candidate, (cross_workspace,))

    parent = replace(
        fixture_pack,
        pack_id="pack-parent",
        parent_pack_refs=(("pack-2", "d" * 64),),
        lineage_reason="refresh",
        lineage_schema_version="graphrag.fmea.evidence-lineage.v1",
    )
    cyclic = replace(
        fixture_pack,
        pack_id="pack-2",
        parent_pack_refs=((parent.pack_id, parent.pack_hash),),
        lineage_reason="refresh",
        lineage_schema_version="graphrag.fmea.evidence-lineage.v1",
    )
    with pytest.raises(FmeaDomainError, match="cycle"):
        validate_evidence_lineage(cyclic, (parent,))


def test_lineage_rejects_candidate_replacing_a_resolved_pack(fixture_pack: EvidencePack) -> None:
    from core_domain.fmea.value_objects import validate_evidence_lineage

    candidate = replace(fixture_pack, pack_id="pack-2", created_at="2026-08-24T00:00:00Z")
    resolved = replace(fixture_pack, pack_id="pack-2")
    with pytest.raises(FmeaDomainError, match="silent parent pack replacement"):
        validate_evidence_lineage(candidate, (resolved,))
