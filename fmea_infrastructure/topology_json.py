"""Safe JSON topology snapshots for the transport-neutral FMEA contracts."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import NoReturn, cast

from core_domain.fmea.errors import FmeaDomainError
from core_domain.fmea.propagation import (
    TopologyInterface,
    TopologyNode,
    TopologySnapshot,
    validate_topology_snapshot,
)

from .domain_pack_registry import (
    _BoundedReadLimitExceeded,
    _is_reparse_point,
    _path_components,
    _read_bounded_path,
    _registry_identity_segment,
    _UnsafeFilePath,
)

_MAX_TOPOLOGY_BYTES = 1024 * 1024
_TOPOLOGY_ROOT_KEYS = frozenset({"topology_snapshot"})
_TOPOLOGY_KEYS = frozenset(
    {
        "id",
        "workspace_id",
        "analysis_id",
        "topology_hash",
        "nodes",
        "interfaces",
        "record_version",
        "created_at",
    }
)
_NODE_KEYS = frozenset({"id", "type", "operating_modes"})
_INTERFACE_KEYS = frozenset(
    {"id", "source_node_id", "target_node_id", "interface_variable", "unit", "direction", "operating_modes"}
)


def _topology_error(code: str, message: str, cause: BaseException | None = None) -> NoReturn:
    error = FmeaDomainError(f"{code}: {message}")
    if cause is None:
        raise error
    raise error from cause


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _topology_error("TOPOLOGY_SOURCE_INVALID", f"{field_name} must be a non-empty string")
    return value.strip()


def _integer(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        _topology_error("TOPOLOGY_SOURCE_INVALID", f"{field_name} must be a positive integer")
    return value


def _string_list(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        _topology_error("TOPOLOGY_SOURCE_INVALID", f"{field_name} must be a list")
    values = tuple(_text(item, f"{field_name} item") for item in value)
    if len(values) != len(set(values)):
        _topology_error("TOPOLOGY_SOURCE_INVALID", f"{field_name} contains duplicate values")
    return values


def _mapping(value: object, field_name: str) -> dict[str, object]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        _topology_error("TOPOLOGY_SOURCE_INVALID", f"{field_name} must be a mapping")
    return cast("dict[str, object]", value)


def _exact_mapping(value: object, field_name: str, expected: frozenset[str]) -> dict[str, object]:
    mapping = _mapping(value, field_name)
    unknown = sorted(set(mapping) - expected)
    if unknown:
        _topology_error("TOPOLOGY_SOURCE_INVALID", f"{field_name} contains unknown key: {unknown[0]}")
    missing = sorted(expected - set(mapping))
    if missing:
        _topology_error("TOPOLOGY_SOURCE_INVALID", f"{field_name} is missing key: {missing[0]}")
    return mapping


def _reject_constant(value: str) -> NoReturn:
    _topology_error("TOPOLOGY_SOURCE_INVALID", f"JSON constant {value} is not allowed")


def _object_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            _topology_error("TOPOLOGY_SOURCE_INVALID", f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _decode_json(raw: bytes) -> object:
    if len(raw) > _MAX_TOPOLOGY_BYTES:
        _topology_error("TOPOLOGY_LIMIT_EXCEEDED", "topology source exceeds 1 MiB")
    try:
        return json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_object_pairs,
            parse_constant=_reject_constant,
        )
    except FmeaDomainError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        _topology_error("TOPOLOGY_SOURCE_INVALID", "topology JSON is invalid", exc)


def _source_bytes(source: bytes | str | Path) -> bytes:
    if isinstance(source, bytes):
        return source
    if isinstance(source, str):
        try:
            return source.encode("utf-8")
        except UnicodeEncodeError as exc:
            _topology_error("TOPOLOGY_SOURCE_INVALID", "topology source is not valid UTF-8", exc)
    if isinstance(source, Path):
        try:
            info = source.lstat()
            if _is_reparse_point(source, info) or not stat.S_ISREG(info.st_mode):
                _topology_error("TOPOLOGY_PATH_OUTSIDE_ROOT", "topology source path is not a regular file")
            return _read_bounded_path(source, _MAX_TOPOLOGY_BYTES, expected_info=info)
        except _BoundedReadLimitExceeded as exc:
            _topology_error("TOPOLOGY_LIMIT_EXCEEDED", "topology source exceeds 1 MiB", exc)
        except _UnsafeFilePath as exc:
            _topology_error("TOPOLOGY_PATH_OUTSIDE_ROOT", "topology source path is unsafe", exc)
        except OSError as exc:
            _topology_error("TOPOLOGY_SOURCE_INVALID", "topology source cannot be read", exc)
    _topology_error("TOPOLOGY_SOURCE_INVALID", "topology source must be bytes, text, or a Path")


def _build_snapshot(raw: object) -> TopologySnapshot:
    root = _exact_mapping(raw, "root", _TOPOLOGY_ROOT_KEYS)
    payload = _exact_mapping(root["topology_snapshot"], "topology_snapshot", _TOPOLOGY_KEYS)
    raw_nodes = payload["nodes"]
    if not isinstance(raw_nodes, list):
        _topology_error("TOPOLOGY_SOURCE_INVALID", "topology_snapshot.nodes must be a list")
    nodes = tuple(
        TopologyNode(
            node_id=_text(item["id"], "topology_snapshot.nodes.id"),
            node_type=_text(item["type"], "topology_snapshot.nodes.type"),
            operating_modes=_string_list(item["operating_modes"], "topology_snapshot.nodes.operating_modes"),
        )
        for item in (_exact_mapping(node, "topology_snapshot.nodes[]", _NODE_KEYS) for node in raw_nodes)
    )
    raw_interfaces = payload["interfaces"]
    if not isinstance(raw_interfaces, list):
        _topology_error("TOPOLOGY_SOURCE_INVALID", "topology_snapshot.interfaces must be a list")
    interfaces = tuple(
        TopologyInterface(
            interface_id=_text(item["id"], "topology_snapshot.interfaces.id"),
            source_node_id=_text(item["source_node_id"], "topology_snapshot.interfaces.source_node_id"),
            target_node_id=_text(item["target_node_id"], "topology_snapshot.interfaces.target_node_id"),
            interface_variable=_text(
                item["interface_variable"], "topology_snapshot.interfaces.interface_variable"
            ),
            unit=_text(item["unit"], "topology_snapshot.interfaces.unit"),
            direction=_text(item["direction"], "topology_snapshot.interfaces.direction"),
            operating_modes=_string_list(
                item["operating_modes"], "topology_snapshot.interfaces.operating_modes"
            ),
        )
        for item in (_exact_mapping(interface, "topology_snapshot.interfaces[]", _INTERFACE_KEYS) for interface in raw_interfaces)
    )
    analysis_id = payload["analysis_id"]
    if analysis_id is not None:
        analysis_id = _text(analysis_id, "topology_snapshot.analysis_id")
    try:
        snapshot = TopologySnapshot(
            topology_snapshot_id=_text(payload["id"], "topology_snapshot.id"),
            workspace_id=_text(payload["workspace_id"], "topology_snapshot.workspace_id"),
            analysis_id=analysis_id,
            topology_hash=_text(payload["topology_hash"], "topology_snapshot.topology_hash"),
            nodes=nodes,
            interfaces=interfaces,
            record_version=_integer(payload["record_version"], "topology_snapshot.record_version"),
            created_at=_text(payload["created_at"], "topology_snapshot.created_at"),
        )
        validate_topology_snapshot(snapshot)
    except FmeaDomainError:
        raise
    except (TypeError, ValueError) as exc:
        _topology_error("TOPOLOGY_SOURCE_INVALID", "topology snapshot contains invalid fields", exc)
    if topology_snapshot_hash(snapshot) != snapshot.topology_hash:
        _topology_error("TOPOLOGY_INTEGRITY_FAILED", "topology_hash mismatch")
    return snapshot


def load_topology_snapshot(source: bytes | str | Path) -> TopologySnapshot:
    """Decode one immutable topology snapshot from strict JSON."""

    return _build_snapshot(_decode_json(_source_bytes(source)))


def _canonical_json(value: Mapping[str, object]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _snapshot_body(snapshot: TopologySnapshot) -> dict[str, object]:
    return {
        "id": snapshot.topology_snapshot_id,
        "workspace_id": snapshot.workspace_id,
        "analysis_id": snapshot.analysis_id,
        "nodes": [
            {"id": node.node_id, "type": node.node_type, "operating_modes": list(node.operating_modes)}
            for node in snapshot.nodes
        ],
        "interfaces": [
            {
                "id": interface.interface_id,
                "source_node_id": interface.source_node_id,
                "target_node_id": interface.target_node_id,
                "interface_variable": interface.interface_variable,
                "unit": interface.unit,
                "direction": interface.direction,
                "operating_modes": list(interface.operating_modes),
            }
            for interface in snapshot.interfaces
        ],
        "record_version": snapshot.record_version,
        "created_at": snapshot.created_at,
    }


def canonical_topology_snapshot_body(snapshot: TopologySnapshot) -> str:
    """Return stable semantic JSON for one validated topology snapshot."""

    if not isinstance(snapshot, TopologySnapshot):
        _topology_error("TOPOLOGY_SOURCE_INVALID", "topology snapshot is invalid")
    validate_topology_snapshot(snapshot)
    return _canonical_json(_snapshot_body(snapshot))


def topology_snapshot_hash(snapshot: TopologySnapshot) -> str:
    """Calculate the SHA-256 hash of a normalized topology body."""

    return hashlib.sha256(canonical_topology_snapshot_body(snapshot).encode("utf-8")).hexdigest()


class JsonTopologyRepository:
    """Load immutable JSON snapshots from a directory without link traversal."""

    def __init__(
        self,
        root: str | Path,
        *,
        source_hashes: Mapping[tuple[str, str], str] | None = None,
    ) -> None:
        self._root = Path(root).absolute()
        if source_hashes is not None and not isinstance(source_hashes, Mapping):
            _topology_error("TOPOLOGY_SOURCE_PIN_INVALID", "source_hashes must be a mapping")
        self._source_hashes = self._validate_source_hashes(source_hashes)

    @staticmethod
    def _validate_source_hashes(
        source_hashes: Mapping[tuple[str, str], str] | None,
    ) -> dict[tuple[str, str], str] | None:
        if source_hashes is None:
            return None
        validated: dict[tuple[str, str], str] = {}
        for identity, source_hash in source_hashes.items():
            if not isinstance(identity, tuple) or len(identity) != 2:
                _topology_error("TOPOLOGY_SOURCE_PIN_INVALID", "source hash identity must be an id/version pair")
            topology_id = _registry_identity_segment(
                identity[0], version=False, path_code="TOPOLOGY_SOURCE_PIN_INVALID"
            )
            version = _registry_identity_segment(
                identity[1], version=True, path_code="TOPOLOGY_SOURCE_PIN_INVALID"
            )
            if (
                not isinstance(source_hash, str)
                or len(source_hash) != hashlib.sha256().digest_size * 2
                or source_hash != source_hash.lower()
                or any(character not in "0123456789abcdef" for character in source_hash)
            ):
                _topology_error("TOPOLOGY_SOURCE_PIN_INVALID", "source hash must be lowercase SHA-256")
            validated[(topology_id, version)] = source_hash
        return validated

    @property
    def root(self) -> Path:
        return self._root

    def _safe_path_info(self, path: Path) -> os.stat_result | None:
        try:
            path.relative_to(self._root)
        except ValueError as exc:
            _topology_error("TOPOLOGY_PATH_OUTSIDE_ROOT", "topology path is outside the configured root", exc)
        components = _path_components(path)
        for index, component in enumerate(components):
            try:
                info = component.lstat()
            except FileNotFoundError:
                return None
            except OSError as exc:
                _topology_error("TOPOLOGY_PATH_OUTSIDE_ROOT", "topology path cannot be inspected", exc)
            if _is_reparse_point(component, info):
                _topology_error("TOPOLOGY_PATH_OUTSIDE_ROOT", "topology path crosses a link or reparse point")
            is_final = index == len(components) - 1
            if is_final:
                if not stat.S_ISREG(info.st_mode):
                    _topology_error("TOPOLOGY_PATH_OUTSIDE_ROOT", "topology path is not a regular file")
            elif not stat.S_ISDIR(info.st_mode):
                _topology_error("TOPOLOGY_PATH_OUTSIDE_ROOT", "topology path crosses a non-directory")
        return info

    def _canonical_path(self, topology_id: str, version: str) -> Path:
        topology_id = _registry_identity_segment(
            topology_id, version=False, path_code="TOPOLOGY_PATH_OUTSIDE_ROOT"
        )
        _registry_identity_segment(version, version=True, path_code="TOPOLOGY_PATH_OUTSIDE_ROOT")
        if topology_id.casefold().endswith(".json"):
            _topology_error(
                "TOPOLOGY_IDENTITY_AMBIGUOUS",
                "topology_id must be an identity, not a snapshot filename",
            )
        return self._root / f"{topology_id}-{version}.json"

    def load_snapshot(self, topology_id: str, version: str) -> TopologySnapshot:
        topology_id = _registry_identity_segment(
            topology_id, version=False, path_code="TOPOLOGY_PATH_OUTSIDE_ROOT"
        )
        _registry_identity_segment(version, version=True, path_code="TOPOLOGY_PATH_OUTSIDE_ROOT")
        path = self._canonical_path(topology_id, version)
        info = self._safe_path_info(path)
        fallback_path = self._root / topology_id / f"{version}.json"
        fallback_info = self._safe_path_info(fallback_path)
        if fallback_info is not None:
            _topology_error(
                "TOPOLOGY_PATH_AMBIGUOUS",
                "legacy nested topology layout is not a permitted fallback",
            )
        if info is None:
            _topology_error("TOPOLOGY_NOT_FOUND", "topology snapshot was not found")
        if self._source_hashes is None:
            _topology_error("TOPOLOGY_SOURCE_PIN_REQUIRED", "an external source hash pin is required")
        expected_source_hash = self._source_hashes.get((topology_id, version))
        if expected_source_hash is None:
            _topology_error("TOPOLOGY_SOURCE_PIN_MISSING", "no source hash pin exists for this identity/version")
        try:
            raw = _read_bounded_path(path, _MAX_TOPOLOGY_BYTES, expected_info=info)
        except _BoundedReadLimitExceeded as exc:
            _topology_error("TOPOLOGY_LIMIT_EXCEEDED", "topology source exceeds 1 MiB", exc)
        except _UnsafeFilePath as exc:
            _topology_error("TOPOLOGY_PATH_OUTSIDE_ROOT", "topology path changed during read", exc)
        except OSError as exc:
            _topology_error("TOPOLOGY_SOURCE_INVALID", "topology source cannot be read", exc)
        if hashlib.sha256(raw).hexdigest() != expected_source_hash:
            _topology_error("TOPOLOGY_SOURCE_HASH_MISMATCH", "topology source hash does not match its external pin")
        snapshot = load_topology_snapshot(raw)
        if snapshot.topology_snapshot_id != topology_id:
            _topology_error(
                "TOPOLOGY_IDENTITY_MISMATCH",
                "requested topology identity does not match the decoded snapshot identity",
            )
        return snapshot

    def neighbors(self, snapshot: TopologySnapshot, entity_id: str) -> tuple[TopologyInterface, ...]:
        """Return all incident interfaces while preserving their declared direction."""

        if not isinstance(snapshot, TopologySnapshot):
            _topology_error("TOPOLOGY_SOURCE_INVALID", "topology snapshot is invalid")
        validate_topology_snapshot(snapshot)
        entity = _text(entity_id, "entity_id")
        return tuple(
            interface
            for interface in snapshot.interfaces
            if interface.source_node_id == entity or interface.target_node_id == entity
        )


__all__ = [
    "JsonTopologyRepository",
    "canonical_topology_snapshot_body",
    "load_topology_snapshot",
    "topology_snapshot_hash",
]
