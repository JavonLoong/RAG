from __future__ import annotations

from pathlib import Path

from core_domain.fmea.propagation import validate_propagation_rule_pack, validate_topology_snapshot
from fmea_infrastructure.domain_pack_registry import load_domain_pack_manifest
from fmea_infrastructure.propagation_rule_registry import (
    FilePropagationRuleRegistry,
    load_propagation_rule_pack,
)
from fmea_infrastructure.topology_json import JsonTopologyRepository

REPO_ROOT = Path(__file__).resolve().parents[2]
PACK_ROOT = REPO_ROOT / "domain_packs" / "fuel-combustion"
MANIFEST_PATH = PACK_ROOT / "manifest.yaml"
RULE_PATH = PACK_ROOT / "propagation" / "fuel-combustion-1.0.0.yaml"
TOPOLOGY_ROOT = PACK_ROOT / "topology"
EXPECTED_TOPOLOGY_SOURCE_HASH = "53559c5c6ed45e1a9e787a5452268cc5c1fc8259d0694459546162af418304e5"


def test_fuel_combustion_propagation_pack_binds_manifest_topology_and_rules(tmp_path: Path) -> None:
    manifest = load_domain_pack_manifest(MANIFEST_PATH.read_bytes())
    rule_source = RULE_PATH.read_bytes()
    rule_pack = load_propagation_rule_pack(rule_source)
    topology = JsonTopologyRepository(
        TOPOLOGY_ROOT,
        source_hashes={("demo", "1.0.0"): EXPECTED_TOPOLOGY_SOURCE_HASH},
    ).load_snapshot("demo", "1.0.0")

    assert manifest.pack_id == "fuel-combustion"
    assert manifest.version == "1.0.0"
    assert manifest.propagation_rule_identities == ((rule_pack.rule_pack_id, rule_pack.version),)
    assert rule_pack.applicable_analysis_types == manifest.analysis_types
    assert {item.interface_variable for item in topology.interfaces} <= set(rule_pack.interface_variables)
    assert {item.unit for item in topology.interfaces} <= set(rule_pack.units)
    assert {item.direction for item in topology.interfaces} <= set(rule_pack.directions)
    assert rule_pack.max_automatic_depth == 2
    assert rule_pack.prohibit_silent_fallback is True
    validate_topology_snapshot(topology)
    validate_propagation_rule_pack(rule_pack)

    registry = FilePropagationRuleRegistry(tmp_path / "propagation-registry")
    assert registry.register(rule_pack, rule_source) == rule_pack
    assert registry.get(rule_pack.rule_pack_id, rule_pack.version) == rule_pack
