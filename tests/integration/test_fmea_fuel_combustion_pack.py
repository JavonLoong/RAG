from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml

from core_domain.fmea.scoring import calculate_risk
from fmea_infrastructure.domain_pack_registry import (
    FileDomainPackRegistry,
    FileScoringRuleRegistry,
    canonical_domain_pack_body,
    load_domain_pack_manifest,
    load_scoring_rule_pack,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO_ROOT / "domain_packs" / "fuel-combustion" / "manifest.yaml"
SCORING_PATH = REPO_ROOT / "domain_packs" / "fuel-combustion" / "scoring" / "sod-rpn-1.0.0.yaml"
EXPECTED_MANIFEST_HASH = "560ab4fb9ff287b7ce43458707e8f1d768c17c3678d0513a1c5e54905d086e0c"


def _source(path: Path) -> bytes:
    return path.read_bytes()


def test_fuel_manifest_loads_with_identity_hash_and_complete_scope() -> None:
    source = _source(MANIFEST_PATH)
    manifest = load_domain_pack_manifest(source)

    assert manifest.pack_id == "fuel-combustion"
    assert manifest.version == "1.0.0"
    assert manifest.compatible_schema_ids == ("graphrag.fmea.v1",)
    assert manifest.analysis_types == ("design_fmea", "process_fmea", "system_fmea")
    assert manifest.template_identities == (("fuel-combustion-fmea", "1.0.0"),)
    assert manifest.scoring_rule_identities == (("fuel-sod-rpn", "1.0.0"),)
    assert manifest.propagation_rule_identities == (("fuel-combustion-propagation", "1.0.0"),)
    assert len(manifest.extension_fields) == 14
    assert len({key for key, _ in manifest.extension_fields}) == 14
    assert all("." in key for key, _ in manifest.extension_fields)

    canonical = canonical_domain_pack_body(manifest).encode("utf-8")
    assert hashlib.sha256(canonical).hexdigest() == EXPECTED_MANIFEST_HASH
    assert manifest.content_hash == EXPECTED_MANIFEST_HASH


def test_fuel_manifest_hash_is_stable_when_yaml_key_order_changes() -> None:
    payload = yaml.safe_load(_source(MANIFEST_PATH))
    root = payload["domain_pack"]
    payload["domain_pack"] = dict(reversed(tuple(root.items())))

    reordered = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True).encode("utf-8")
    original = load_domain_pack_manifest(_source(MANIFEST_PATH))
    equivalent = load_domain_pack_manifest(reordered)

    assert canonical_domain_pack_body(equivalent) == canonical_domain_pack_body(original)
    assert equivalent.content_hash == original.content_hash


def test_fuel_registries_register_get_and_replay_source(tmp_path: Path) -> None:
    manifest_source = _source(MANIFEST_PATH)
    scoring_source = _source(SCORING_PATH)
    manifest = load_domain_pack_manifest(manifest_source)
    rule_pack = load_scoring_rule_pack(scoring_source)

    domain_registry = FileDomainPackRegistry(tmp_path / "domain-registry")
    scoring_registry = FileScoringRuleRegistry(tmp_path / "scoring-registry")

    assert domain_registry.register(manifest, manifest_source) == manifest
    assert domain_registry.get("fuel-combustion", "1.0.0") == manifest
    assert scoring_registry.register(rule_pack, scoring_source) == rule_pack
    assert scoring_registry.get("fuel-sod-rpn", "1.0.0") == rule_pack

    reordered_manifest = yaml.safe_dump(
        yaml.safe_load(manifest_source), sort_keys=True, allow_unicode=True
    ).encode("utf-8")
    assert domain_registry.register(load_domain_pack_manifest(reordered_manifest), reordered_manifest) == manifest
    assert (tmp_path / "domain-registry" / "fuel-combustion" / "1.0.0" / "source.yaml").read_bytes() == manifest_source


def test_fuel_scoring_pack_declares_complete_sod_and_frozen_policies() -> None:
    pack = load_scoring_rule_pack(_source(SCORING_PATH))

    assert pack.rule_pack_id == "fuel-sod-rpn"
    assert pack.version == "1.0.0"
    assert pack.applicable_analysis_types == ("design_fmea", "process_fmea", "system_fmea")
    assert pack.required_dimensions == ("severity", "occurrence", "detection")
    assert tuple(name for name, _ in pack.dimension_anchors) == pack.required_dimensions
    for name, anchors in pack.dimension_anchors:
        assert tuple(score for score, _ in anchors) == tuple(range(1, 11)), name
        assert all(description.strip() for _, description in anchors)
        assert all("-" not in description or not description.startswith(f"{name}-") for _, description in anchors)
    assert pack.occurrence_window == "operating_hours"
    assert pack.occurrence_denominator == "1000_operating_hours"
    assert pack.detection_positions == ("sensor", "logic", "operator")
    assert pack.decision_severity_policy == "max_consequence"
    assert pack.rpn_formula == "S*O*D"
    assert pack.rpn_formula_version == "S*O*D-1"
    assert pack.critical_severity_threshold == 9
    assert pack.high_priority_rpn == 200
    assert pack.medium_priority_rpn == 100
    assert pack.missing_score_policy == "unknown_no_zero"
    assert pack.conflict_score_policy == "block_rpn"
    assert pack.uncertainty_policy == "preserve_require_review"
    assert pack.policy_basis == "project_default_non_certification"


@pytest.mark.parametrize(
    ("severity", "occurrence", "detection"),
    [(9, None, 5), (None, 5, 5), (9, 5, None)],
)
def test_fuel_risk_missing_dimension_never_substitutes_zero(
    severity: int | None, occurrence: int | None, detection: int | None
) -> None:
    rule_pack = load_scoring_rule_pack(_source(SCORING_PATH))

    assessment = calculate_risk(
        rule_pack=rule_pack,
        severity_by_consequence_class=(("safety", severity),),
        occurrence=occurrence,
        detection=detection,
        inherent_risk=None,
        current_risk=None,
        target_residual_risk=None,
        verified_residual_risk=None,
        uncertainty="missing score requires review",
        reason="integration fixture",
        evidence_ids=("evidence-1",),
    )

    assert assessment.rpn is None
    assert assessment.rpn != 0


@pytest.mark.parametrize(
    ("scores", "rpn", "priority"),
    [((("safety", 9),), 225, "critical"), ((("process", 6),), 210, "high"), ((("process", 5),), 100, "medium")],
)
def test_fuel_risk_uses_max_severity_and_declared_priority_thresholds(
    scores: tuple[tuple[str, int], ...], rpn: int, priority: str
) -> None:
    rule_pack = load_scoring_rule_pack(_source(SCORING_PATH))

    assessment = calculate_risk(
        rule_pack=rule_pack,
        severity_by_consequence_class=scores,
        occurrence=5,
        detection=5 if rpn == 225 else 7 if rpn == 210 else 4,
        inherent_risk=None,
        current_risk=None,
        target_residual_risk=None,
        verified_residual_risk=None,
        uncertainty=None,
        reason="integration fixture",
        evidence_ids=("evidence-1",),
    )

    assert assessment.decision_severity == scores[0][1]
    assert assessment.rpn == rpn
    assert assessment.decision_priority == priority


def test_fuel_registry_stores_canonical_body_and_source_hashes(tmp_path: Path) -> None:
    source = _source(MANIFEST_PATH)
    manifest = load_domain_pack_manifest(source)
    registry = FileDomainPackRegistry(tmp_path)
    registry.register(manifest, source)

    stored_manifest = json.loads(
        (tmp_path / manifest.pack_id / manifest.version / "manifest.json").read_text(encoding="utf-8")
    )
    assert stored_manifest["body_hash"] == hashlib.sha256(
        (tmp_path / manifest.pack_id / manifest.version / "body.json").read_bytes()
    ).hexdigest()
    assert stored_manifest["source_hash"] == hashlib.sha256(source).hexdigest()
