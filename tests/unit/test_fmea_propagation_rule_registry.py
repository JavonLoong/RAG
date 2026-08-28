from __future__ import annotations

import hashlib
import json
from dataclasses import FrozenInstanceError, fields
from pathlib import Path

import pytest
import yaml

from core_domain.fmea.errors import FmeaDomainError
from fmea_infrastructure.propagation_rule_registry import (
    FilePropagationRuleRegistry,
    canonical_propagation_rule_body,
    load_propagation_rule_pack,
    propagation_rule_content_hash,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
RULE_PATH = REPO_ROOT / "domain_packs" / "fuel-combustion" / "propagation" / "fuel-combustion-1.0.0.yaml"


def _source() -> bytes:
    return RULE_PATH.read_bytes()


def test_fuel_combustion_rule_pack_declares_closed_propagation_controls() -> None:
    pack = load_propagation_rule_pack(_source())

    assert pack.rule_pack_id == "fuel-combustion-propagation"
    assert pack.version == "1.0.0"
    assert pack.applicable_analysis_types == ("design_fmea", "process_fmea", "system_fmea")
    assert pack.relation_types == ("propagation", "common_cause", "dependency", "feedback")
    assert pack.interface_variables == (
        "fuel_pressure",
        "fuel_flow",
        "atomization_quality",
        "flame_stability",
        "pressure_signal",
        "trip_command",
    )
    assert pack.units == ("kPa", "kg_per_s", "quality_index", "stability_index", "signal", "boolean")
    assert pack.directions == (
        "fuel_to_combustion",
        "combustion_to_control",
        "feedback",
        "control_to_fuel",
    )
    assert pack.max_automatic_depth == 2
    assert pack.mandatory_review_conditions == (
        "long_path",
        "cyclic",
        "high_risk",
        "external",
        "evidence_gap",
        "barrier_crossing",
        "timing_violation",
    )
    assert pack.barrier_semantics == "explicit_barriers"
    assert pack.risk_escalation == "high_and_critical_require_review"
    assert pack.prohibit_silent_fallback is True


def test_rule_pack_loader_rejects_unlocked_depth_and_silent_fallback() -> None:
    payload = yaml.safe_load(_source())
    payload["rule_pack"]["max_automatic_depth"] = 3
    with pytest.raises(FmeaDomainError, match="max_automatic_depth.*2"):
        load_propagation_rule_pack(yaml.safe_dump(payload, sort_keys=False).encode("utf-8"))

    payload = yaml.safe_load(_source())
    payload["rule_pack"]["prohibit_silent_fallback"] = False
    with pytest.raises(FmeaDomainError, match="silent fallback"):
        load_propagation_rule_pack(yaml.safe_dump(payload, sort_keys=False).encode("utf-8"))


def test_rule_pack_loader_rejects_unknown_yaml_keys() -> None:
    payload = yaml.safe_load(_source())
    payload["rule_pack"]["unreviewed_extension"] = True

    with pytest.raises(FmeaDomainError, match="unknown key"):
        load_propagation_rule_pack(yaml.safe_dump(payload, sort_keys=False).encode("utf-8"))


def test_file_rule_registry_is_immutable_and_replays_canonical_source(tmp_path: Path) -> None:
    source = _source()
    pack = load_propagation_rule_pack(source)
    registry = FilePropagationRuleRegistry(tmp_path)

    assert registry.register(pack, source) == pack
    assert registry.get(pack.rule_pack_id, pack.version) == pack
    assert (tmp_path / pack.rule_pack_id / pack.version / "source.yaml").read_bytes() == source

    stored_manifest = json.loads(
        (tmp_path / pack.rule_pack_id / pack.version / "manifest.json").read_text(encoding="utf-8")
    )
    assert stored_manifest["body_hash"] == propagation_rule_content_hash(pack)
    assert stored_manifest["source_hash"] == hashlib.sha256(source).hexdigest()

    reordered = yaml.safe_dump(yaml.safe_load(source), sort_keys=True).encode("utf-8")
    assert registry.register(load_propagation_rule_pack(reordered), reordered) == pack
    assert (tmp_path / pack.rule_pack_id / pack.version / "source.yaml").read_bytes() == source


def test_rule_pack_body_hash_is_stable_for_equivalent_yaml() -> None:
    source = load_propagation_rule_pack(_source())
    assert propagation_rule_content_hash(source) == hashlib.sha256(
        canonical_propagation_rule_body(source).encode("utf-8")
    ).hexdigest()
    assert tuple(field.name for field in fields(source)) == (
        "rule_pack_id",
        "version",
        "applicable_analysis_types",
        "relation_types",
        "interface_variables",
        "units",
        "directions",
        "max_automatic_depth",
        "mandatory_review_conditions",
        "barrier_semantics",
        "risk_escalation",
        "prohibit_silent_fallback",
    )
    with pytest.raises(FrozenInstanceError):
        source.rule_pack_id = "changed"  # type: ignore[misc]


def test_file_rule_registry_rejects_identity_path_escape(tmp_path: Path) -> None:
    registry = FilePropagationRuleRegistry(tmp_path)
    pack = load_propagation_rule_pack(_source())

    with pytest.raises(FmeaDomainError, match="PROPAGATION_RULE_PATH_INVALID"):
        registry.get("../outside", pack.version)
