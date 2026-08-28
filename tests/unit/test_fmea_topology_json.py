from __future__ import annotations

import hashlib
import json
from dataclasses import FrozenInstanceError, fields
from pathlib import Path

import pytest

from core_domain.fmea.errors import FmeaDomainError
from core_domain.fmea.propagation import validate_topology_snapshot
from fmea_infrastructure.topology_json import (
    JsonTopologyRepository,
    canonical_topology_snapshot_body,
    load_topology_snapshot,
    topology_snapshot_hash,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
TOPOLOGY_ROOT = REPO_ROOT / "domain_packs" / "fuel-combustion" / "topology"
TOPOLOGY_PATH = TOPOLOGY_ROOT / "demo-1.0.0.json"


def _source() -> bytes:
    return TOPOLOGY_PATH.read_bytes()


def _interface(snapshot, source: str, target: str):
    return next(
        item
        for item in snapshot.interfaces
        if item.source_node_id == source and item.target_node_id == target
    )


def test_fuel_to_combustion_fixture_has_explicit_interfaces() -> None:
    snapshot = JsonTopologyRepository(TOPOLOGY_ROOT).load_snapshot("demo", "1.0.0")

    assert snapshot.topology_snapshot_id == "fuel-combustion-demo"
    assert snapshot.workspace_id == "fuel-combustion"
    assert snapshot.analysis_id is None
    assert {node.node_id for node in snapshot.nodes} == {
        "fuel_pump",
        "fuel_filter",
        "fuel_manifold",
        "fuel_nozzle",
        "combustor_flame",
        "pressure_sensor",
        "controller",
    }
    assert _interface(snapshot, "fuel_pump", "fuel_manifold").variable == "fuel_pressure"
    assert _interface(snapshot, "fuel_nozzle", "combustor_flame").variable == "atomization_quality"
    assert _interface(snapshot, "controller", "fuel_pump").direction == "control_to_fuel"
    validate_topology_snapshot(snapshot)


def test_topology_neighbors_return_incident_immutable_interfaces() -> None:
    repository = JsonTopologyRepository(TOPOLOGY_ROOT)
    snapshot = repository.load_snapshot("demo", "1.0.0")

    neighbors = repository.neighbors(snapshot, "fuel_manifold")

    assert {(item.source_node_id, item.target_node_id) for item in neighbors} == {
        ("fuel_filter", "fuel_manifold"),
        ("fuel_pump", "fuel_manifold"),
        ("fuel_manifold", "fuel_nozzle"),
    }
    with pytest.raises(FrozenInstanceError):
        neighbors[0].unit = "bar"  # type: ignore[misc]


def test_topology_loader_rejects_path_traversal(tmp_path: Path) -> None:
    with pytest.raises(FmeaDomainError, match="TOPOLOGY_PATH_OUTSIDE_ROOT"):
        JsonTopologyRepository(tmp_path).load_snapshot("..\\outside", "1.0.0")


def test_topology_loader_rejects_symlink_escape(tmp_path: Path) -> None:
    outside = tmp_path / "outside.json"
    outside.write_bytes(_source())
    link = tmp_path / "escape-1.0.0.json"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")

    with pytest.raises(FmeaDomainError, match="TOPOLOGY_PATH_OUTSIDE_ROOT"):
        JsonTopologyRepository(tmp_path).load_snapshot("escape", "1.0.0")


def test_topology_loader_rejects_duplicate_json_keys() -> None:
    payload = _source().decode("utf-8")
    duplicate = payload.replace(
        '"topology_snapshot": {',
        '"topology_snapshot": {"record_version": 2,',
        1,
    )
    with pytest.raises(FmeaDomainError, match="duplicate JSON key"):
        load_topology_snapshot(duplicate.encode("utf-8"))


def test_topology_hash_is_canonical_and_loader_rejects_tampering() -> None:
    snapshot = load_topology_snapshot(_source())

    assert snapshot.topology_hash == topology_snapshot_hash(snapshot)
    assert snapshot.topology_hash == hashlib.sha256(
        canonical_topology_snapshot_body(snapshot).encode("utf-8")
    ).hexdigest()
    assert tuple(field.name for field in fields(snapshot)) == (
        "topology_snapshot_id",
        "workspace_id",
        "analysis_id",
        "topology_hash",
        "nodes",
        "interfaces",
        "record_version",
        "created_at",
    )
    with pytest.raises(FrozenInstanceError):
        snapshot.workspace_id = "changed"  # type: ignore[misc]

    payload = json.loads(_source())
    payload["topology_snapshot"]["nodes"][0]["type"] = "tampered"
    with pytest.raises(FmeaDomainError, match="topology_hash mismatch"):
        load_topology_snapshot(json.dumps(payload).encode("utf-8"))


def test_topology_loader_rejects_unknown_node_keys() -> None:
    payload = json.loads(_source())
    payload["topology_snapshot"]["nodes"][0]["unexpected"] = True

    with pytest.raises(FmeaDomainError, match="unknown key"):
        load_topology_snapshot(json.dumps(payload).encode("utf-8"))
