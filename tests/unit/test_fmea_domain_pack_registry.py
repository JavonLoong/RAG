from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml

from core_domain.fmea.errors import FmeaDomainError
from fmea_infrastructure.domain_pack_registry import (
    canonical_domain_pack_body,
    canonical_scoring_rule_body,
    load_domain_pack_manifest,
    load_scoring_rule_pack,
)


def _domain_body() -> dict[str, object]:
    return {
        "id": "fuel-combustion",
        "version": "1.0.0",
        "kernel_compatibility_range": ">=1.0.0,<2.0.0",
        "compatible_schema_ids": ["graphrag.fmea.v1"],
        "analysis_types": ["design_fmea", "process_fmea", "system_fmea"],
        "templates": [{"id": "fuel-combustion-fmea", "version": "1.0.0"}],
        "scoring_rules": [{"id": "fuel-sod-rpn", "version": "1.0.0"}],
        "propagation_rules": [],
        "extension_fields": [
            {"key": "fuel.heating_value", "type": "decimal"},
            {"key": "combustion.flame_stability", "type": "text"},
        ],
    }


def _domain_source(body: dict[str, object] | None = None) -> bytes:
    semantic_body = body or _domain_body()
    canonical = json.dumps(semantic_body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    payload = {"domain_pack": {**semantic_body, "content_hash": hashlib.sha256(canonical.encode("utf-8")).hexdigest()}}
    return yaml.safe_dump(payload, sort_keys=False, allow_unicode=True).encode("utf-8")


def _anchors(prefix: str) -> dict[int, str]:
    return {score: f"{prefix}-{score}" for score in range(1, 11)}


def _scoring_payload() -> dict[str, object]:
    return {
        "rule_pack": {
            "id": "fuel-sod-rpn",
            "version": "1.0.0",
            "applicable_analysis_types": ["design_fmea", "process_fmea", "system_fmea"],
            "score_range": {"min": 1, "max": 10},
            "dimensions": {
                "severity": {"anchors": _anchors("severity")},
                "occurrence": {"anchors": _anchors("occurrence")},
                "detection": {"anchors": _anchors("detection")},
            },
            "occurrence": {"window": "operating_hours", "denominator": "1000_operating_hours"},
            "detection": {"positions": ["sensor", "logic", "operator"]},
            "decision_severity": {"aggregation": "max_consequence"},
            "rpn": {"formula": "S*O*D", "version": "S*O*D-1"},
            "risk_matrix": {"version": "fuel-risk-matrix-1"},
            "priority": {"version": "fuel-priority-1", "high_rpn": 200, "critical_severity": 9, "medium_rpn": 100},
            "uncertainty": {
                "missing_score_policy": "unknown_no_zero",
                "conflict_score_policy": "block_rpn",
                "uncertainty_policy": "preserve_require_review",
            },
            "policy_basis": "project_default_non_certification",
        }
    }


def _scoring_source(payload: dict[str, object] | None = None) -> bytes:
    return yaml.safe_dump(payload or _scoring_payload(), sort_keys=False, allow_unicode=True).encode("utf-8")


def test_valid_domain_manifest_loads_and_maps_to_immutable_contract() -> None:
    manifest = load_domain_pack_manifest(_domain_source())

    assert manifest.pack_id == "fuel-combustion"
    assert manifest.version == "1.0.0"
    assert manifest.compatible_schema_ids == ("graphrag.fmea.v1",)
    assert manifest.template_identities == (("fuel-combustion-fmea", "1.0.0"),)
    assert manifest.scoring_rule_identities == (("fuel-sod-rpn", "1.0.0"),)
    assert manifest.extension_fields == (("fuel.heating_value", "decimal"), ("combustion.flame_stability", "text"))


def test_domain_manifest_loader_accepts_yaml_text_and_path(tmp_path: Path) -> None:
    source = _domain_source()
    path = tmp_path / "manifest.yaml"
    path.write_bytes(source)

    assert load_domain_pack_manifest(source.decode("utf-8")) == load_domain_pack_manifest(path)


def test_domain_content_hash_is_normalized_and_deterministic() -> None:
    first = load_domain_pack_manifest(_domain_source())
    reordered = dict(reversed(tuple(_domain_body().items())))
    second = load_domain_pack_manifest(_domain_source(reordered))

    assert canonical_domain_pack_body(first) == canonical_domain_pack_body(second)
    assert first.content_hash == second.content_hash


def test_domain_content_hash_mismatch_fails_closed() -> None:
    body = _domain_body()
    source = yaml.safe_dump(
        {"domain_pack": {**body, "content_hash": "0" * 64}},
        sort_keys=False,
        allow_unicode=True,
    ).encode("utf-8")

    with pytest.raises(FmeaDomainError, match="content_hash mismatch"):
        load_domain_pack_manifest(source)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda payload: payload["domain_pack"].update({"unexpected": True}), "unknown key"),
        (lambda payload: payload["domain_pack"].pop("version"), "missing key"),
        (lambda payload: payload["domain_pack"].update({"analysis_types": "design_fmea"}), "analysis_types"),
    ],
)
def test_domain_manifest_rejects_unknown_missing_and_wrong_typed_fields(mutation, message: str) -> None:
    payload = yaml.safe_load(_domain_source())
    mutation(payload)

    with pytest.raises(FmeaDomainError, match=message):
        load_domain_pack_manifest(yaml.safe_dump(payload, sort_keys=False))


def test_domain_manifest_rejects_invalid_encoding_and_source_size(tmp_path: Path) -> None:
    with pytest.raises(FmeaDomainError, match="UTF-8"):
        load_domain_pack_manifest(b"\xff")

    path = tmp_path / "oversized.yaml"
    path.write_bytes(b"x" * (1024 * 1024 + 1))
    with pytest.raises(FmeaDomainError, match="1 MiB"):
        load_domain_pack_manifest(path)


def test_valid_scoring_rule_pack_loads_all_sod_anchors_and_policies() -> None:
    pack = load_scoring_rule_pack(_scoring_source())

    assert pack.rule_pack_id == "fuel-sod-rpn"
    assert pack.required_dimensions == ("severity", "occurrence", "detection")
    assert tuple(name for name, _ in pack.dimension_anchors) == pack.required_dimensions
    assert all(len(anchors) == 10 for _, anchors in pack.dimension_anchors)
    assert pack.severity_anchors == tuple((score, f"severity-{score}") for score in range(1, 11))
    assert pack.occurrence_window == "operating_hours"
    assert pack.occurrence_denominator == "1000_operating_hours"
    assert pack.rpn_formula == "S*O*D"
    assert pack.high_priority_rpn == 200
    assert pack.medium_priority_rpn == 100
    assert pack.missing_score_policy == "unknown_no_zero"


def test_scoring_rule_canonical_body_is_stable_for_yaml_key_order() -> None:
    first = load_scoring_rule_pack(_scoring_source())
    payload = _scoring_payload()
    rule_pack = payload["rule_pack"]
    assert isinstance(rule_pack, dict)
    payload["rule_pack"] = dict(reversed(tuple(rule_pack.items())))
    second = load_scoring_rule_pack(_scoring_source(payload))

    assert canonical_scoring_rule_body(first) == canonical_scoring_rule_body(second)


@pytest.mark.parametrize(
    "path",
    [
        ("dimensions", "severity", "anchors"),
        ("dimensions", "occurrence", "anchors"),
        ("dimensions", "detection", "anchors"),
    ],
)
def test_scoring_rule_rejects_incomplete_anchors(path: tuple[str, str, str]) -> None:
    payload = _scoring_payload()
    anchors = payload["rule_pack"][path[0]][path[1]][path[2]]
    assert isinstance(anchors, dict)
    anchors.pop(10)

    with pytest.raises(FmeaDomainError, match="anchors"):
        load_scoring_rule_pack(_scoring_source(payload))


def test_scoring_rule_rejects_duplicate_yaml_anchor_keys() -> None:
    source = (
        _scoring_source()
        .decode("utf-8")
        .replace(
            "        1: severity-1\n",
            "        1: duplicate\n        1: severity-1\n",
            1,
        )
    )

    with pytest.raises(FmeaDomainError, match="duplicate YAML key"):
        load_scoring_rule_pack(source)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("policy_basis", None, "policy_basis"),
        ("rpn", {"formula": "S+O+D", "version": "S*O*D-1"}, "formula"),
        (
            "uncertainty",
            {
                "missing_score_policy": "zero",
                "conflict_score_policy": "block_rpn",
                "uncertainty_policy": "preserve_require_review",
            },
            "missing_score_policy",
        ),
    ],
)
def test_scoring_rule_rejects_missing_or_unsupported_frozen_policies(field: str, value: object, message: str) -> None:
    payload = _scoring_payload()
    if value is None:
        payload["rule_pack"].pop(field)
    else:
        payload["rule_pack"][field] = value

    with pytest.raises(FmeaDomainError, match=message):
        load_scoring_rule_pack(_scoring_source(payload))


def test_scoring_loader_rejects_unknown_root_and_nested_keys() -> None:
    payload = _scoring_payload()
    payload["rule_pack"]["dimensions"]["severity"]["extra"] = True

    with pytest.raises(FmeaDomainError, match="unknown key"):
        load_scoring_rule_pack(_scoring_source(payload))


def test_loaders_reject_yaml_aliases_and_multiple_documents() -> None:
    aliased = (
        b"domain_pack: &pack\n  id: fuel-combustion\n  version: 1.0.0\n  content_hash: '"
        + b"0" * 64
        + b"'\ncopy: *pack\n"
    )
    with pytest.raises(FmeaDomainError, match="alias"):
        load_domain_pack_manifest(aliased)

    with pytest.raises(FmeaDomainError, match="document"):
        load_domain_pack_manifest(_domain_source() + b"\n---\nnull\n")
