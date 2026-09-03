from __future__ import annotations

from dataclasses import fields
from hashlib import sha256

import orjson
import pytest

from core_domain.fmea.governance import canonical_json_value
from fmea_application.snapshot_contracts import NormalizedFmeaSnapshot
from fmea_infrastructure.export_json import CanonicalJsonExporter
from tests.fmea_governance_fixtures import make_fmea_revision, make_normalized_snapshot

EXPECTED_JSON_SHA256 = "b6b8ebdab2777fd3752226867e2a22c6c28b0c6934071c6efac644043ef76a47"


def _forge_snapshot(snapshot: NormalizedFmeaSnapshot, **overrides: object) -> NormalizedFmeaSnapshot:
    forged = object.__new__(NormalizedFmeaSnapshot)
    for field in fields(snapshot):
        object.__setattr__(forged, field.name, getattr(snapshot, field.name))
    for field_name, value in overrides.items():
        object.__setattr__(forged, field_name, value)
    return forged


def test_json_export_bytes_and_sha256_are_stable() -> None:
    snapshot = make_normalized_snapshot()
    exporter = CanonicalJsonExporter()

    first = exporter.render(snapshot)
    second = exporter.render(snapshot)

    assert exporter.format == "json"
    assert exporter.media_type == "application/json"
    assert first == second
    assert sha256(first).hexdigest() == EXPECTED_JSON_SHA256


def test_json_export_projects_complete_normalized_snapshot_semantics() -> None:
    revision = make_fmea_revision()
    version_manifest = {
        "analysis_hash": revision.analysis_hash,
        "domain_pack_identity": revision.domain_pack_identity,
        "template_identities": revision.template_identities,
        "scoring_rule_identities": revision.scoring_rule_identities,
        "propagation_rule_identity": revision.propagation_rule_identity,
        "retrieval_provenance": {
            "requested_profile": revision.retrieval_provenance.requested_profile,
            "resolved_profile": revision.retrieval_provenance.resolved_profile,
            "evidence_types": revision.retrieval_provenance.evidence_types,
            "source_counts": revision.retrieval_provenance.source_counts,
            "warnings": revision.retrieval_provenance.warnings,
        },
    }
    snapshot = make_normalized_snapshot(revision=revision, version_manifest=version_manifest)
    body = orjson.loads(CanonicalJsonExporter().render(snapshot))

    assert body["schema_version"] == "graphrag.fmea.export.v1"
    assert body["snapshot_id"] == snapshot.snapshot_id
    assert body["snapshot_hash"] == snapshot.snapshot_hash
    assert body["workspace_id"] == snapshot.workspace_id
    assert body["analysis_id"] == snapshot.analysis_id
    assert body["revision_id"] == snapshot.revision_id
    assert body["revision_hash"] == snapshot.revision_hash
    assert body["publication_id"] == snapshot.publication_id
    assert body["manifest_id"] == snapshot.manifest_id
    assert body["rows"] == [dict(row) for row in snapshot.rows]
    assert body["row_count"] == snapshot.row_count
    assert body["risk_records"] == [dict(record) for record in snapshot.risk_records]
    assert body["propagation"] == dict(snapshot.propagation or {})
    assert body["evidence_summary"] == [dict(item) for item in snapshot.evidence_summary]
    assert body["decision_summary"] == [dict(item) for item in snapshot.decision_summary]
    assert body["version_manifest"] == canonical_json_value(version_manifest)
    assert body["unresolved_items"] == [dict(item) for item in snapshot.unresolved_items]
    assert body["audit_summary"] == dict(snapshot.audit_summary)


def test_json_export_is_utf8_compact_sorted_and_has_one_trailing_newline() -> None:
    snapshot = make_normalized_snapshot(row_payload={"row_id": "行-1", "failure_mode": "燃料压力低"})
    rendered = CanonicalJsonExporter().render(snapshot)
    parsed = orjson.loads(rendered)

    assert rendered.decode("utf-8").encode("utf-8") == rendered
    assert not rendered.startswith(b"\xef\xbb\xbf")
    assert rendered.endswith(b"\n")
    assert not rendered.endswith(b"\n\n")
    assert b"\r" not in rendered
    assert b"\n" not in rendered[:-1]
    assert list(parsed) == sorted(parsed)
    assert b" : " not in rendered
    assert b" , " not in rendered


@pytest.mark.parametrize("bad_value", (float("nan"), float("inf"), object(), "C:\\private\\snapshot.json"))
def test_json_export_rejects_non_export_safe_values_without_leaking_them(bad_value: object) -> None:
    snapshot = make_normalized_snapshot()
    forged = _forge_snapshot(snapshot, rows=({"row_id": "row-1", "value": bad_value},))

    with pytest.raises(ValueError) as captured:
        CanonicalJsonExporter().render(forged)

    assert getattr(captured.value, "code", None) == "FMEA_EXPORT_JSON_INVALID"
    assert str(captured.value) == "snapshot cannot be rendered as canonical JSON"
    assert "private" not in str(captured.value)


def test_json_export_rejects_wrong_type_without_object_repr() -> None:
    with pytest.raises(ValueError) as captured:
        CanonicalJsonExporter().render(object())  # type: ignore[arg-type]

    assert getattr(captured.value, "code", None) == "FMEA_EXPORT_SNAPSHOT_INVALID"
    assert str(captured.value) == "snapshot must be a NormalizedFmeaSnapshot"
    assert "object at" not in str(captured.value)


def test_json_export_rejects_unbounded_snapshot_arrays() -> None:
    snapshot = make_normalized_snapshot()
    rows = tuple({"row_id": f"row-{index}"} for index in range(10_001))
    forged = _forge_snapshot(snapshot, rows=rows, row_count=len(rows))

    with pytest.raises(ValueError) as captured:
        CanonicalJsonExporter().render(forged)

    assert getattr(captured.value, "code", None) == "FMEA_EXPORT_JSON_INVALID"
    assert str(captured.value) == "snapshot cannot be rendered as canonical JSON"


def test_json_export_does_not_mutate_snapshot() -> None:
    snapshot = make_normalized_snapshot()
    before = canonical_json_value(snapshot)

    CanonicalJsonExporter().render(snapshot)

    assert canonical_json_value(snapshot) == before
