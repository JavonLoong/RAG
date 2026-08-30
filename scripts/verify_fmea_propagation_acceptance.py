"""Independent, bytes-first verifier for the FMEA propagation acceptance pack."""

from __future__ import annotations

import argparse
import json
import ntpath
import os
import posixpath
import re
import stat
import sys
from hashlib import sha256
from itertools import pairwise
from pathlib import Path
from typing import NoReturn, cast

SCHEMA_VERSION = "graphrag.fmea.propagation.acceptance.v1"
CASE_IDS = ["forward", "reverse", "cycle", "conflict", "long_path"]
EVIDENCE_PROFILES = [
    "rag_only",
    "graphrag_local_only",
    "graphrag_global_only",
    "graphrag_only",
    "combined",
    "auto",
    "custom",
]
ARTIFACT_NAMES = {
    "topology.json",
    "proposal.json",
    "reviewed-graph.json",
    "paths.json",
    "decisions.json",
    "issues.json",
    "audit-summary.json",
    "acceptance-summary.json",
}

_MAX_ARTIFACT_BYTES = 2 * 1024 * 1024
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_PATH_START_BOUNDARY = r"(?<![\w.\\/])"
_EMBEDDED_ABSOLUTE_PATH_PATTERNS = (
    re.compile(_PATH_START_BOUNDARY + r"/{1,2}(?=[^/\s])"),
    re.compile(_PATH_START_BOUNDARY + r"[A-Za-z]:[\\/]"),
    re.compile(_PATH_START_BOUNDARY + r"\\\\(?=[^\\/\s])"),
    re.compile(_PATH_START_BOUNDARY + r"\\(?![\\\s])"),
)
_HTTP_URL_SPAN = re.compile(r"\bhttps?://\S+", re.IGNORECASE)
_TOPOLOGY_SOURCE_HASH = "sha256:53559c5c6ed45e1a9e787a5452268cc5c1fc8259d0694459546162af418304e5"
_TOPOLOGY_SOURCE_CANONICAL_HASH = "sha256:d698f66f461367a468de0ed100a344bf1c29caf1223b7c2a66d8a91b5a50fc18"
_TOPOLOGY_PATH = Path(__file__).resolve().parents[1] / "domain_packs" / "fuel-combustion" / "topology" / "demo-1.0.0.json"
_DOMAIN_CONTENT_HASH = "1b5453082ee1cf09657a69e93fc4aee02651c93348454578539a72c8f0908fac"
_RULE_PACK_HASH = "e9e7768be8e78836b6fab019400950a87c9ddc25ca4fc5cf8cde796a770a48d6"
_PROFILE_PACK_PROFILES = {
    "pack-rag-only": "rag_only",
    "pack-graphrag-local-only": "graphrag_local_only",
    "pack-graphrag-global-only": "graphrag_global_only",
    "pack-graphrag-only": "graphrag_only",
    "pack-combined": "combined",
    "pack-custom": "custom",
}
_OFFLINE_GENERATION_CONSTRAINTS = {
    "execution_mode": "deterministic_offline",
    "network_allowed": False,
    "paid_model_allowed": False,
    "budget": {
        "max_input_tokens": 2048,
        "max_output_tokens": 1024,
        "max_total_tokens": 3072,
    },
    "caps": {
        "max_cases": 5,
        "max_edges": 14,
        "max_path_depth": 2,
        "max_evidence_refs_per_edge": 3,
    },
}
_PROFILE_TYPES = {
    "rag_only": ["text"],
    "graphrag_local_only": ["graph"],
    "graphrag_global_only": ["community"],
    "graphrag_only": ["graph", "community"],
    "combined": ["text", "graph", "community"],
    "auto": ["text", "graph", "community"],
    "custom": ["text", "graph"],
}
_PROFILE_PACKS = {
    "rag_only": "pack-rag-only",
    "graphrag_local_only": "pack-graphrag-local-only",
    "graphrag_global_only": "pack-graphrag-global-only",
    "graphrag_only": "pack-graphrag-only",
    "combined": "pack-combined",
    "auto": "pack-combined",
    "custom": "pack-custom",
}
_PROFILE_RESOLUTION = {
    "rag_only": "rag_only",
    "graphrag_local_only": "graphrag_local_only",
    "graphrag_global_only": "graphrag_global_only",
    "graphrag_only": "graphrag_only",
    "combined": "combined",
    "auto": "combined",
    "custom": "custom",
}
_PACK_PARENT_IDS = {
    "pack-rag-only": [],
    "pack-graphrag-local-only": ["pack-rag-only"],
    "pack-graphrag-global-only": ["pack-rag-only"],
    "pack-graphrag-only": ["pack-graphrag-global-only", "pack-graphrag-local-only"],
    "pack-combined": ["pack-graphrag-global-only", "pack-graphrag-local-only", "pack-rag-only"],
    "pack-custom": ["pack-graphrag-local-only", "pack-rag-only"],
}
_EVIDENCE_SOURCE_TYPES = {"primary_document": "text", "graphrag_relation": "graph", "graphrag_community": "community"}
_INTERFACE_FIELDS = {
    "interface_id",
    "source_node_id",
    "target_node_id",
    "interface_variable",
    "unit",
    "direction",
    "operating_modes",
}
_EDGE_FIELDS = {
    "edge_id",
    "case_id",
    "analysis_id",
    "source_entity_id",
    "target_entity_id",
    "relation_type",
    "interface_variable",
    "unit",
    "direction",
    "threshold",
    "operating_modes",
    "delay_ms",
    "response_time_ms",
    "fault_tolerance_time_ms",
    "barrier_ids",
    "evidence_pack_id",
    "evidence_ids",
    "evidence_support",
    "claim_status",
    "review_status",
    "publication_status",
    "path_length",
    "is_cyclic",
    "is_unprocessed",
    "is_external",
    "is_terminal",
    "risk_priority",
    "record_version",
}


class AcceptanceVerificationError(ValueError):
    """Stable verification failure without artifact values or local paths."""

    def __init__(self, code: str) -> None:
        super().__init__("FMEA propagation acceptance verification failed.")
        self.code = code


def _fail(code: str) -> NoReturn:
    raise AcceptanceVerificationError(code)


def _canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _hash_bytes(value: bytes) -> str:
    return "sha256:" + sha256(value).hexdigest()


def _hash_json(value: object) -> str:
    return _hash_bytes(_canonical_bytes(value))


def _strict_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            _fail("FMEA_PROPAGATION_JSON_DUPLICATE_KEY")
        result[key] = value
    return result


def _reject_constant(value: str) -> NoReturn:
    del value
    _fail("FMEA_PROPAGATION_JSON_INVALID")


def _is_reparse(info: os.stat_result) -> bool:
    attributes = getattr(info, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return stat.S_ISLNK(info.st_mode) or bool(attributes & reparse_flag)


def _safe_artifact_directory(directory: str | Path) -> bool:
    """Check every existing component without resolving or following links."""

    path = Path(directory).expanduser().absolute()
    anchor_parts = Path(path.anchor).parts if path.anchor else ()
    current = Path(path.anchor) if path.anchor else Path()
    parts = path.parts[len(anchor_parts) :]
    if not parts:
        return False
    for index, part in enumerate(parts):
        current /= part
        try:
            info = current.lstat()
        except (FileNotFoundError, OSError):
            return False
        if _is_reparse(info):
            return False
        if index == len(parts) - 1:
            return stat.S_ISDIR(info.st_mode)
        if not stat.S_ISDIR(info.st_mode):
            return False
    return False


def _safe_file(path: Path) -> bool:
    try:
        info = path.lstat()
    except OSError:
        return False
    return not _is_reparse(info) and stat.S_ISREG(info.st_mode)


def _mapping(value: object, code: str) -> dict[str, object]:
    if not isinstance(value, dict):
        _fail(code)
    return cast(dict[str, object], value)


def _list(value: object, code: str) -> list[object]:
    if not isinstance(value, list):
        _fail(code)
    return cast(list[object], value)


def _exact(value: object, expected: set[str], code: str) -> dict[str, object]:
    result = _mapping(value, code)
    if set(result) != expected:
        _fail(code)
    return result


def _text(value: object, code: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(code)
    return value


def _bool(value: object, code: str) -> bool:
    if not isinstance(value, bool):
        _fail(code)
    return value


def _positive_int(value: object, code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        _fail(code)
    return value


def _hex64(value: object, code: str) -> str:
    if not isinstance(value, str) or _HEX64.fullmatch(value) is None:
        _fail(code)
    return value


def _sha256_hash(value: object, code: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        _fail(code)
    return value


def _version_payload(profile: str) -> dict[str, object]:
    return {
        "schema_id": "graphrag.fmea.v1",
        "data_version": "propagation-fixture-v1",
        "graph_version": "fuel-combustion-propagation-v1",
        "evidence_pack_version": "1.0.0",
        "profile_version": profile,
        "template_version": "fmea-propagation-hypothesis@1.0.0",
        "scoring_version": "fuel-sod-rpn@1.0.0",
        "prompt_version": "offline-fixture-v1",
        "model_version": "deterministic-offline-model-v1",
        "input_snapshot_hash": sha256((profile + "|propagation-fixture-v1").encode("utf-8")).hexdigest(),
    }


def _generation_constraints() -> dict[str, object]:
    return json.loads(json.dumps(_OFFLINE_GENERATION_CONSTRAINTS, sort_keys=True))


def _is_absolute_local_path(value: str) -> bool:
    return posixpath.isabs(value) or ntpath.isabs(value) or value.startswith("\\")


def _contains_forbidden_local_path(value: object) -> bool:
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return False
        if _is_absolute_local_path(stripped):
            return True
        url_spans = tuple((match.start(), match.end()) for match in _HTTP_URL_SPAN.finditer(value))
        return any(
            not any(start <= match.start() < end for start, end in url_spans)
            for pattern in _EMBEDDED_ABSOLUTE_PATH_PATTERNS
            for match in pattern.finditer(value)
        )
    if isinstance(value, dict):
        return any(_contains_forbidden_local_path(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_forbidden_local_path(item) for item in value)
    return False


def _load(path: Path) -> tuple[dict[str, object], bytes]:
    if not _safe_file(path):
        _fail("FMEA_PROPAGATION_ARTIFACT_SET_INVALID")
    try:
        raw = path.read_bytes()
    except OSError:
        _fail("FMEA_PROPAGATION_ARTIFACT_SET_INVALID")
    if len(raw) > _MAX_ARTIFACT_BYTES:
        _fail("FMEA_PROPAGATION_ARTIFACT_TOO_LARGE")
    private_patterns = (
        b"Authorization",
        b"Bearer ",
        b"DEEPSEEK_API_KEY",
        b"REQUEST_PRIVATE_MARKER",
        b"EVIDENCE_PRIVATE_MARKER",
        b"raw provider response",
        b"raw_provider_response",
        b"\"prompt\"",
        b"api_key",
        b"API_KEY",
        b"secret",
        b"sk-",
        b"C:\\private",
        b"/private/",
    )
    if any(pattern in raw for pattern in private_patterns):
        _fail("FMEA_PROPAGATION_PRIVATE_MARKER")
    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_strict_pairs,
            parse_constant=_reject_constant,
        )
    except AcceptanceVerificationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, TypeError, ValueError):
        _fail("FMEA_PROPAGATION_JSON_INVALID")
    if not isinstance(value, dict):
        _fail("FMEA_PROPAGATION_JSON_SHAPE_INVALID")
    if _contains_forbidden_local_path(value):
        _fail("FMEA_PROPAGATION_PRIVATE_MARKER")
    if _canonical_bytes(value) != raw:
        _fail("FMEA_PROPAGATION_JSON_NOT_CANONICAL")
    return value, raw


def _schema(value: dict[str, object]) -> None:
    if value.get("schema_version") != SCHEMA_VERSION:
        _fail("FMEA_PROPAGATION_SCHEMA_INVALID")


def _authoritative_topology_source() -> tuple[str, str, dict[str, object]]:
    if not _safe_file(_TOPOLOGY_PATH):
        _fail("FMEA_PROPAGATION_TOPOLOGY_IDENTITY_INVALID")
    try:
        raw = _TOPOLOGY_PATH.read_bytes()
        source = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_strict_pairs,
            parse_constant=_reject_constant,
        )
    except AcceptanceVerificationError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, RecursionError, TypeError, ValueError):
        _fail("FMEA_PROPAGATION_TOPOLOGY_IDENTITY_INVALID")
    if _hash_bytes(raw) != _TOPOLOGY_SOURCE_HASH or _hash_bytes(_canonical_bytes(source)) != _TOPOLOGY_SOURCE_CANONICAL_HASH:
        _fail("FMEA_PROPAGATION_TOPOLOGY_IDENTITY_INVALID")
    root = _exact(source, {"topology_snapshot"}, "FMEA_PROPAGATION_TOPOLOGY_IDENTITY_INVALID")
    source_snapshot = _exact(
        root["topology_snapshot"],
        {"id", "workspace_id", "analysis_id", "topology_hash", "nodes", "interfaces", "record_version", "created_at"},
        "FMEA_PROPAGATION_TOPOLOGY_IDENTITY_INVALID",
    )
    normalized = {
        "id": source_snapshot["id"],
        "workspace_id": source_snapshot["workspace_id"],
        "analysis_id": source_snapshot["analysis_id"],
        "topology_hash": source_snapshot["topology_hash"],
        "nodes": [
            {
                "node_id": _exact(node, {"id", "type", "operating_modes"}, "FMEA_PROPAGATION_TOPOLOGY_IDENTITY_INVALID")["id"],
                "node_type": _exact(node, {"id", "type", "operating_modes"}, "FMEA_PROPAGATION_TOPOLOGY_IDENTITY_INVALID")["type"],
                "operating_modes": _exact(node, {"id", "type", "operating_modes"}, "FMEA_PROPAGATION_TOPOLOGY_IDENTITY_INVALID")["operating_modes"],
            }
            for node in _list(source_snapshot["nodes"], "FMEA_PROPAGATION_TOPOLOGY_IDENTITY_INVALID")
        ],
        "interfaces": [
            {
                "interface_id": _exact(interface, {"id", "source_node_id", "target_node_id", "interface_variable", "unit", "direction", "operating_modes"}, "FMEA_PROPAGATION_TOPOLOGY_IDENTITY_INVALID")["id"],
                "source_node_id": _exact(interface, {"id", "source_node_id", "target_node_id", "interface_variable", "unit", "direction", "operating_modes"}, "FMEA_PROPAGATION_TOPOLOGY_IDENTITY_INVALID")["source_node_id"],
                "target_node_id": _exact(interface, {"id", "source_node_id", "target_node_id", "interface_variable", "unit", "direction", "operating_modes"}, "FMEA_PROPAGATION_TOPOLOGY_IDENTITY_INVALID")["target_node_id"],
                "interface_variable": _exact(interface, {"id", "source_node_id", "target_node_id", "interface_variable", "unit", "direction", "operating_modes"}, "FMEA_PROPAGATION_TOPOLOGY_IDENTITY_INVALID")["interface_variable"],
                "unit": _exact(interface, {"id", "source_node_id", "target_node_id", "interface_variable", "unit", "direction", "operating_modes"}, "FMEA_PROPAGATION_TOPOLOGY_IDENTITY_INVALID")["unit"],
                "direction": _exact(interface, {"id", "source_node_id", "target_node_id", "interface_variable", "unit", "direction", "operating_modes"}, "FMEA_PROPAGATION_TOPOLOGY_IDENTITY_INVALID")["direction"],
                "operating_modes": _exact(interface, {"id", "source_node_id", "target_node_id", "interface_variable", "unit", "direction", "operating_modes"}, "FMEA_PROPAGATION_TOPOLOGY_IDENTITY_INVALID")["operating_modes"],
            }
            for interface in _list(source_snapshot["interfaces"], "FMEA_PROPAGATION_TOPOLOGY_IDENTITY_INVALID")
        ],
        "record_version": source_snapshot["record_version"],
        "created_at": source_snapshot["created_at"],
    }
    return _hash_bytes(raw), _hash_bytes(_canonical_bytes(source)), normalized


def _verify_topology(value: dict[str, object]) -> dict[str, object]:  # noqa: C901
    expected = {
        "schema_version",
        "resource_type",
        "workspace_id",
        "analysis_id",
        "domain_pack",
        "topology_source_hash",
        "topology_source_canonical_hash",
        "topology_snapshot",
        "rule_pack",
        "rule_pack_hash",
        "evidence_selection_profiles",
        "evidence_packs",
    }
    _exact(value, expected, "FMEA_PROPAGATION_TOPOLOGY_INVALID")
    if value["resource_type"] != "propagation_topology" or value["workspace_id"] != "fuel-combustion" or value["analysis_id"] != "analysis-fuel-combustion-1":
        _fail("FMEA_PROPAGATION_TOPOLOGY_INVALID")
    source_hash, source_canonical_hash, source_snapshot = _authoritative_topology_source()
    if value["topology_source_hash"] != source_hash or value["topology_source_canonical_hash"] != source_canonical_hash:
        _fail("FMEA_PROPAGATION_TOPOLOGY_IDENTITY_INVALID")
    domain = _exact(value["domain_pack"], {"id", "version", "content_hash"}, "FMEA_PROPAGATION_DOMAIN_IDENTITY_INVALID")
    if domain != {"id": "fuel-combustion", "version": "1.0.0", "content_hash": _DOMAIN_CONTENT_HASH}:
        _fail("FMEA_PROPAGATION_DOMAIN_IDENTITY_INVALID")
    snapshot = _exact(
        value["topology_snapshot"],
        {"id", "workspace_id", "analysis_id", "topology_hash", "nodes", "interfaces", "record_version", "created_at"},
        "FMEA_PROPAGATION_TOPOLOGY_INVALID",
    )
    if snapshot["id"] != "demo" or snapshot["workspace_id"] != "fuel-combustion" or snapshot["analysis_id"] is not None:
        _fail("FMEA_PROPAGATION_TOPOLOGY_IDENTITY_INVALID")
    topology_hash = _text(snapshot["topology_hash"], "FMEA_PROPAGATION_TOPOLOGY_INVALID")
    _hex64(topology_hash, "FMEA_PROPAGATION_TOPOLOGY_INVALID")
    nodes = _list(snapshot["nodes"], "FMEA_PROPAGATION_TOPOLOGY_INVALID")
    node_ids: list[str] = []
    for raw in nodes:
        node = _exact(raw, {"node_id", "node_type", "operating_modes"}, "FMEA_PROPAGATION_TOPOLOGY_INVALID")
        node_ids.append(_text(node["node_id"], "FMEA_PROPAGATION_TOPOLOGY_INVALID"))
        _text(node["node_type"], "FMEA_PROPAGATION_TOPOLOGY_INVALID")
        modes = _list(node["operating_modes"], "FMEA_PROPAGATION_TOPOLOGY_INVALID")
        if not modes or any(not isinstance(item, str) for item in modes):
            _fail("FMEA_PROPAGATION_TOPOLOGY_INVALID")
    if len(node_ids) != len(set(node_ids)):
        _fail("FMEA_PROPAGATION_DUPLICATE_ID")
    interfaces = _list(snapshot["interfaces"], "FMEA_PROPAGATION_TOPOLOGY_INVALID")
    interface_ids: list[str] = []
    interface_values: list[dict[str, object]] = []
    for raw in interfaces:
        interface = _exact(raw, _INTERFACE_FIELDS, "FMEA_PROPAGATION_TOPOLOGY_INVALID")
        interface_ids.append(_text(interface["interface_id"], "FMEA_PROPAGATION_TOPOLOGY_INVALID"))
        source = _text(interface["source_node_id"], "FMEA_PROPAGATION_TOPOLOGY_INVALID")
        target = _text(interface["target_node_id"], "FMEA_PROPAGATION_TOPOLOGY_INVALID")
        if source not in node_ids or target not in node_ids:
            _fail("FMEA_PROPAGATION_ENDPOINT_INVALID")
        for key in ("interface_variable", "unit", "direction"):
            _text(interface[key], "FMEA_PROPAGATION_TOPOLOGY_INVALID")
        modes = _list(interface["operating_modes"], "FMEA_PROPAGATION_TOPOLOGY_INVALID")
        if not modes or any(not isinstance(item, str) for item in modes):
            _fail("FMEA_PROPAGATION_TOPOLOGY_INVALID")
        interface_values.append(interface)
    if len(interface_ids) != len(set(interface_ids)):
        _fail("FMEA_PROPAGATION_DUPLICATE_ID")
    body = {
        "id": snapshot["id"],
        "workspace_id": snapshot["workspace_id"],
        "analysis_id": snapshot["analysis_id"],
        "nodes": [
            {"id": node["node_id"], "type": node["node_type"], "operating_modes": node["operating_modes"]}
            for node in nodes
        ],
        "interfaces": [
            {
                "id": interface["interface_id"],
                "source_node_id": interface["source_node_id"],
                "target_node_id": interface["target_node_id"],
                "interface_variable": interface["interface_variable"],
                "unit": interface["unit"],
                "direction": interface["direction"],
                "operating_modes": interface["operating_modes"],
            }
            for interface in interfaces
        ],
        "record_version": _positive_int(snapshot["record_version"], "FMEA_PROPAGATION_TOPOLOGY_INVALID"),
        "created_at": _text(snapshot["created_at"], "FMEA_PROPAGATION_TOPOLOGY_INVALID"),
    }
    if sha256(_canonical_json(body)).hexdigest() != topology_hash:
        _fail("FMEA_PROPAGATION_TOPOLOGY_IDENTITY_INVALID")
    if snapshot != source_snapshot:
        _fail("FMEA_PROPAGATION_TOPOLOGY_IDENTITY_INVALID")
    rule = _exact(
        value["rule_pack"],
        {
            "applicable_analysis_types",
            "barrier_semantics",
            "directions",
            "id",
            "interface_variables",
            "mandatory_review_conditions",
            "max_automatic_depth",
            "prohibit_silent_fallback",
            "relation_types",
            "risk_escalation",
            "timing_constraints",
            "units",
            "version",
        },
        "FMEA_PROPAGATION_RULE_INVALID",
    )
    if rule["id"] != "fuel-combustion-propagation" or rule["version"] != "1.0.0" or rule["max_automatic_depth"] != 2 or rule["prohibit_silent_fallback"] is not True:
        _fail("FMEA_PROPAGATION_RULE_INVALID")
    timing = _exact(rule["timing_constraints"], {"delay_ms", "fault_tolerance_time_ms", "response_time_ms"}, "FMEA_PROPAGATION_RULE_INVALID")
    if any(item != "non_negative" for item in timing.values()):
        _fail("FMEA_PROPAGATION_RULE_INVALID")
    if value["rule_pack_hash"] != _RULE_PACK_HASH or value["rule_pack_hash"] != sha256(_canonical_json(rule)).hexdigest():
        _fail("FMEA_PROPAGATION_RULE_IDENTITY_INVALID")
    profiles = _exact(value["evidence_selection_profiles"], set(EVIDENCE_PROFILES), "FMEA_PROPAGATION_PROFILE_MATRIX_INVALID")
    for profile in EVIDENCE_PROFILES:
        item = _exact(
            profiles[profile],
            {"requested_profile", "resolved_profile", "evidence_types", "evidence_pack_id", "evidence_pack_hash", "retrieval_incomplete", "version_set", "generation_constraints"},
            "FMEA_PROPAGATION_PROFILE_MATRIX_INVALID",
        )
        if item["requested_profile"] != profile or item["resolved_profile"] != _PROFILE_RESOLUTION[profile] or item["evidence_types"] != _PROFILE_TYPES[profile] or item["evidence_pack_id"] != _PROFILE_PACKS[profile] or item["retrieval_incomplete"] is not False:
            _fail("FMEA_PROPAGATION_PROFILE_MATRIX_INVALID")
        _hex64(item["evidence_pack_hash"], "FMEA_PROPAGATION_PROFILE_MATRIX_INVALID")
        if item["version_set"] != _version_payload(_PROFILE_RESOLUTION[profile]) or item["generation_constraints"] != _generation_constraints():
            _fail("FMEA_PROPAGATION_PROFILE_MATRIX_INVALID")
    packs = _list(value["evidence_packs"], "FMEA_PROPAGATION_EVIDENCE_INVALID")
    packs_by_id: dict[str, dict[str, object]] = {}
    for raw in packs:
        pack = _exact(raw, {"pack_id", "workspace_id", "acl_scope", "versions", "refs", "pack_hash", "created_at", "expires_at", "lineage"}, "FMEA_PROPAGATION_EVIDENCE_INVALID")
        pack_id = _text(pack["pack_id"], "FMEA_PROPAGATION_EVIDENCE_INVALID")
        if pack_id in packs_by_id:
            _fail("FMEA_PROPAGATION_DUPLICATE_ID")
        packs_by_id[pack_id] = pack
    if set(packs_by_id) != set(_PACK_PARENT_IDS):
        _fail("FMEA_PROPAGATION_EVIDENCE_INVALID")
    for pack_id, pack in packs_by_id.items():
        _verify_pack(pack, pack_id, packs_by_id)
    for profile in EVIDENCE_PROFILES:
        pack = packs_by_id[_PROFILE_PACKS[profile]]
        if pack["pack_hash"] != profiles[profile]["evidence_pack_hash"]:
            _fail("FMEA_PROPAGATION_EVIDENCE_INVALID")
        if pack["versions"] != profiles[profile]["version_set"]:
            _fail("FMEA_PROPAGATION_PROFILE_MATRIX_INVALID")
        source_types = [_EVIDENCE_SOURCE_TYPES[cast(str, ref["source_type"])] for ref in _list(pack["refs"], "FMEA_PROPAGATION_EVIDENCE_INVALID")]
        if source_types != _PROFILE_TYPES[profile] and profile != "auto":
            _fail("FMEA_PROPAGATION_PROFILE_MATRIX_INVALID")
    return {"snapshot": snapshot, "rule": rule, "rule_pack_hash": value["rule_pack_hash"], "domain": domain, "profiles": profiles, "packs": packs_by_id, "interfaces": interface_values}


def _verify_pack(pack: dict[str, object], pack_id: str, packs: dict[str, dict[str, object]]) -> None:  # noqa: C901
    if pack["workspace_id"] != "fuel-combustion" or pack["acl_scope"] != ["acceptance"] or not isinstance(pack["created_at"], str) or pack["expires_at"] is not None:
        _fail("FMEA_PROPAGATION_EVIDENCE_INVALID")
    versions = _exact(
        pack["versions"],
        {"schema_id", "data_version", "graph_version", "evidence_pack_version", "profile_version", "template_version", "scoring_version", "prompt_version", "model_version", "input_snapshot_hash"},
        "FMEA_PROPAGATION_EVIDENCE_INVALID",
    )
    if versions["schema_id"] != "graphrag.fmea.v1":
        _fail("FMEA_PROPAGATION_EVIDENCE_INVALID")
    _hex64(versions["input_snapshot_hash"], "FMEA_PROPAGATION_EVIDENCE_INVALID")
    if pack_id not in _PROFILE_PACK_PROFILES or versions != _version_payload(_PROFILE_PACK_PROFILES[pack_id]):
        _fail("FMEA_PROPAGATION_PROFILE_MATRIX_INVALID")
    refs = _list(pack["refs"], "FMEA_PROPAGATION_EVIDENCE_INVALID")
    if not refs:
        _fail("FMEA_PROPAGATION_EVIDENCE_INVALID")
    evidence_payload: list[dict[str, object]] = []
    ids: set[str] = set()
    for raw in refs:
        ref = _exact(
            raw,
            {"evidence_id", "workspace_id", "document_id", "document_version", "content_hash", "locator", "quote", "normalized_quote", "evidence_hash", "acl_scope", "source_type", "source_trust", "is_primary", "created_at", "expires_at"},
            "FMEA_PROPAGATION_EVIDENCE_INVALID",
        )
        evidence_id = _text(ref["evidence_id"], "FMEA_PROPAGATION_EVIDENCE_INVALID")
        quote = _text(ref["quote"], "FMEA_PROPAGATION_EVIDENCE_INVALID")
        if evidence_id in ids or ref["workspace_id"] != "fuel-combustion" or ref["normalized_quote"] != quote or ref["content_hash"] != sha256(quote.encode("utf-8")).hexdigest() or ref["evidence_hash"] != sha256((evidence_id + "|" + quote).encode("utf-8")).hexdigest() or ref["acl_scope"] != ["acceptance"] or ref["source_type"] not in _EVIDENCE_SOURCE_TYPES or ref["source_trust"] != "reviewed" or not isinstance(ref["is_primary"], bool) or ref["expires_at"] is not None:
            _fail("FMEA_PROPAGATION_EVIDENCE_INVALID")
        ids.add(evidence_id)
        evidence_payload.append({"evidence_id": evidence_id, "evidence_hash": ref["evidence_hash"], "locator": ref["locator"]})
    lineage = _exact(pack["lineage"], {"parent_pack_refs", "lineage_reason", "lineage_schema_version"}, "FMEA_PROPAGATION_LINEAGE_INVALID")
    parent_refs = _list(lineage["parent_pack_refs"], "FMEA_PROPAGATION_LINEAGE_INVALID")
    parent_ids: list[str] = []
    for raw_parent in parent_refs:
        parent = _exact(raw_parent, {"pack_id", "pack_hash"}, "FMEA_PROPAGATION_LINEAGE_INVALID")
        parent_id = _text(parent["pack_id"], "FMEA_PROPAGATION_LINEAGE_INVALID")
        if parent_id == pack_id or parent_id in parent_ids or parent_id not in packs or parent["pack_hash"] != packs[parent_id]["pack_hash"]:
            _fail("FMEA_PROPAGATION_LINEAGE_INVALID")
        _hex64(parent["pack_hash"], "FMEA_PROPAGATION_LINEAGE_INVALID")
        parent_ids.append(parent_id)
    if parent_ids != _PACK_PARENT_IDS[pack_id]:
        _fail("FMEA_PROPAGATION_LINEAGE_INVALID")
    evidence_payload = sorted(evidence_payload, key=lambda item: cast(str, item["evidence_id"]))
    if parent_ids:
        if not isinstance(lineage["lineage_reason"], str) or lineage["lineage_schema_version"] != "graphrag.fmea.evidence-lineage.v1":
            _fail("FMEA_PROPAGATION_LINEAGE_INVALID")
        hash_payload: object = {"evidence_refs": evidence_payload, "lineage": {"lineage_reason": lineage["lineage_reason"], "lineage_schema_version": lineage["lineage_schema_version"], "parent_pack_refs": parent_refs}}
    else:
        if lineage["lineage_reason"] is not None or lineage["lineage_schema_version"] is not None:
            _fail("FMEA_PROPAGATION_LINEAGE_INVALID")
        hash_payload = evidence_payload
    if pack["pack_hash"] != sha256(_canonical_json(hash_payload)).hexdigest():
        _fail("FMEA_PROPAGATION_EVIDENCE_HASH_INVALID")


def _interface_for(edge: dict[str, object], interfaces: list[dict[str, object]]) -> dict[str, object] | None:
    return next(
        (item for item in interfaces if item["source_node_id"] == edge["source_entity_id"] and item["target_node_id"] == edge["target_entity_id"]),
        None,
    )


def _validate_edge(edge: dict[str, object], topology: dict[str, object], *, review_status: str) -> None:  # noqa: C901
    _exact(edge, _EDGE_FIELDS, "FMEA_PROPAGATION_EDGE_INVALID")
    if edge["analysis_id"] != "analysis-fuel-combustion-1" or edge["relation_type"] not in ["propagation", "common_cause", "dependency", "feedback"]:
        _fail("FMEA_PROPAGATION_RELATION_INVALID")
    node_ids = {cast(str, node["node_id"]) for node in _list(topology["snapshot"]["nodes"], "FMEA_PROPAGATION_TOPOLOGY_INVALID")}
    if edge["source_entity_id"] not in node_ids or edge["target_entity_id"] not in node_ids:
        _fail("FMEA_PROPAGATION_ENDPOINT_INVALID")
    interface = _interface_for(edge, topology["interfaces"])
    if interface is None:
        _fail("FMEA_PROPAGATION_ENDPOINT_INVALID")
    if edge["interface_variable"] != interface["interface_variable"] or edge["unit"] != interface["unit"] or edge["direction"] != interface["direction"]:
        _fail("FMEA_PROPAGATION_RELATION_INVALID")
    modes = _list(edge["operating_modes"], "FMEA_PROPAGATION_EDGE_INVALID")
    if not modes or any(not isinstance(item, str) for item in modes) or not set(modes).intersection(cast(list[str], interface["operating_modes"])):
        _fail("FMEA_PROPAGATION_RELATION_INVALID")
    if any(isinstance(edge[key], bool) or not isinstance(edge[key], int) or edge[key] < 0 for key in ("delay_ms", "response_time_ms", "fault_tolerance_time_ms")):
        _fail("FMEA_PROPAGATION_RELATION_INVALID")
    _positive_int(edge["path_length"], "FMEA_PROPAGATION_EDGE_INVALID")
    evidence_ids_value = edge["evidence_ids"]
    if edge["evidence_pack_id"] != "pack-combined" or not isinstance(evidence_ids_value, list) or not evidence_ids_value or any(not isinstance(item, str) for item in evidence_ids_value) or len(evidence_ids_value) != len(set(evidence_ids_value)):
        _fail("FMEA_PROPAGATION_EVIDENCE_INVALID")
    combined = topology["packs"]["pack-combined"]
    evidence_ids = {cast(str, ref["evidence_id"]) for ref in _list(combined["refs"], "FMEA_PROPAGATION_EVIDENCE_INVALID")}
    if not set(cast(list[str], evidence_ids_value)).issubset(evidence_ids):
        _fail("FMEA_PROPAGATION_EVIDENCE_INVALID")
    if edge["review_status"] != review_status or edge["publication_status"] != "unpublished" or edge["record_version"] != 1:
        _fail("FMEA_PROPAGATION_REVIEW_POLICY_INVALID")
    for key in ("is_cyclic", "is_unprocessed", "is_external", "is_terminal"):
        _bool(edge[key], "FMEA_PROPAGATION_EDGE_INVALID")
    if edge["evidence_support"] not in {"supported", "partially_supported", "contradicted", "not_supported"} or edge["claim_status"] not in {"known", "unknown", "insufficient_evidence", "conflict", "not_applicable"} or edge["risk_priority"] not in {"normal", "medium", "high", "critical"}:
        _fail("FMEA_PROPAGATION_EDGE_INVALID")


def _verify_proposal(value: dict[str, object], topology: dict[str, object]) -> dict[str, dict[str, object]]:
    _exact(value, {"schema_version", "resource_type", "actor", "lineage", "case_ids", "edges"}, "FMEA_PROPAGATION_PROPOSAL_INVALID")
    if value["resource_type"] != "propagation_proposal" or value["case_ids"] != CASE_IDS:
        _fail("FMEA_PROPAGATION_PROPOSAL_INVALID")
    actor = _exact(value["actor"], {"actor_id", "actor_type"}, "FMEA_PROPAGATION_MODEL_AUTHORITY_INVALID")
    if actor["actor_type"] != "model":
        _fail("FMEA_PROPAGATION_MODEL_AUTHORITY_INVALID")
    lineage = _exact(value["lineage"], {"workspace_id", "analysis_id", "topology_snapshot_id", "topology_hash", "domain_pack_id", "domain_pack_version", "rule_pack_id", "rule_pack_version", "evidence_pack_ids"}, "FMEA_PROPAGATION_LINEAGE_INVALID")
    snapshot = topology["snapshot"]
    rule = topology["rule"]
    if lineage != {"workspace_id": "fuel-combustion", "analysis_id": "analysis-fuel-combustion-1", "topology_snapshot_id": snapshot["id"], "topology_hash": snapshot["topology_hash"], "domain_pack_id": "fuel-combustion", "domain_pack_version": "1.0.0", "rule_pack_id": rule["id"], "rule_pack_version": rule["version"], "evidence_pack_ids": ["pack-combined"]}:
        _fail("FMEA_PROPAGATION_LINEAGE_INVALID")
    edges = _list(value["edges"], "FMEA_PROPAGATION_PROPOSAL_INVALID")
    result: dict[str, dict[str, object]] = {}
    for raw in edges:
        edge = _mapping(raw, "FMEA_PROPAGATION_PROPOSAL_INVALID")
        edge_id = _text(edge.get("edge_id"), "FMEA_PROPAGATION_PROPOSAL_INVALID")
        if edge_id in result:
            _fail("FMEA_PROPAGATION_DUPLICATE_ID")
        _validate_edge(edge, topology, review_status="suggested")
        case_id = edge.get("case_id")
        if case_id not in CASE_IDS:
            _fail("FMEA_PROPAGATION_PROPOSAL_INVALID")
        result[edge_id] = edge
    if len(result) != 14:
        _fail("FMEA_PROPAGATION_PROPOSAL_INVALID")
    return result


def _verify_graph(value: dict[str, object], topology: dict[str, object], proposal: dict[str, dict[str, object]]) -> dict[str, dict[str, object]]:  # noqa: C901
    expected = {"schema_version", "resource_type", "graph_revision_id", "workspace_id", "analysis_id", "analysis_record_version", "topology_snapshot_id", "topology_hash", "domain_pack", "rule_pack", "evidence_pack_ids", "assistance_suggestion_ids", "status", "record_version", "nodes", "edges", "accepted_case_ids", "human_review_case_ids", "graph_hash"}
    _exact(value, expected, "FMEA_PROPAGATION_GRAPH_INVALID")
    if value["resource_type"] != "propagation_reviewed_graph" or value["graph_revision_id"] != "graph-reviewed-1" or value["workspace_id"] != "fuel-combustion" or value["analysis_id"] != "analysis-fuel-combustion-1" or value["status"] != "reviewed" or value["record_version"] != 1 or value["evidence_pack_ids"] != ["pack-combined"] or value["accepted_case_ids"] != ["forward", "reverse"] or value["human_review_case_ids"] != ["cycle", "conflict", "long_path"]:
        _fail("FMEA_PROPAGATION_GRAPH_INVALID")
    if value["topology_snapshot_id"] != topology["snapshot"]["id"] or value["topology_hash"] != topology["snapshot"]["topology_hash"]:
        _fail("FMEA_PROPAGATION_LINEAGE_INVALID")
    domain = _exact(value["domain_pack"], {"id", "version", "content_hash"}, "FMEA_PROPAGATION_LINEAGE_INVALID")
    if domain != topology["domain"]:
        _fail("FMEA_PROPAGATION_LINEAGE_INVALID")
    rule = _exact(value["rule_pack"], {"id", "version", "hash"}, "FMEA_PROPAGATION_LINEAGE_INVALID")
    if rule != {"id": topology["rule"]["id"], "version": topology["rule"]["version"], "hash": topology["rule_pack_hash"]}:
        _fail("FMEA_PROPAGATION_LINEAGE_INVALID")
    nodes = _list(value["nodes"], "FMEA_PROPAGATION_GRAPH_INVALID")
    if nodes != topology["snapshot"]["nodes"]:
        _fail("FMEA_PROPAGATION_TOPOLOGY_IDENTITY_INVALID")
    edges = _list(value["edges"], "FMEA_PROPAGATION_GRAPH_INVALID")
    result: dict[str, dict[str, object]] = {}
    for raw in edges:
        edge = _mapping(raw, "FMEA_PROPAGATION_GRAPH_INVALID")
        edge_id = _text(edge.get("edge_id"), "FMEA_PROPAGATION_GRAPH_INVALID")
        if edge_id in result:
            _fail("FMEA_PROPAGATION_DUPLICATE_ID")
        expected_status = "accepted" if edge["case_id"] in {"forward", "reverse"} else "in_review"
        _validate_edge(edge, topology, review_status=expected_status)
        if edge_id not in proposal or {key: edge[key] for key in _EDGE_FIELDS if key != "review_status"} != {key: proposal[edge_id][key] for key in _EDGE_FIELDS if key != "review_status"}:
            _fail("FMEA_PROPAGATION_GRAPH_INVALID")
        result[edge_id] = edge
    if set(result) != set(proposal):
        _fail("FMEA_PROPAGATION_GRAPH_INVALID")
    body = {key: item for key, item in value.items() if key != "graph_hash"}
    if value["graph_hash"] != _hash_json(body):
        _fail("FMEA_PROPAGATION_GRAPH_IDENTITY_INVALID")
    return result


def _case_edges(edges: dict[str, dict[str, object]], case_id: str) -> list[dict[str, object]]:
    return [edge for edge in edges.values() if edge["case_id"] == case_id]


def _required_codes(case_edges: list[dict[str, object]], path: dict[str, object]) -> list[str]:
    codes: set[str] = set()
    if path["path_length"] > 2:
        codes.add("long_path")
    if path["is_cyclic"]:
        codes.add("cyclic")
    if any(edge["risk_priority"] in {"high", "critical"} for edge in case_edges):
        codes.add("high_risk")
    if any(edge["is_external"] for edge in case_edges):
        codes.add("external")
    if any(edge["is_unprocessed"] for edge in case_edges):
        codes.add("incomplete")
    if any(edge["claim_status"] == "conflict" for edge in case_edges):
        codes.add("conflicting")
    if any(edge["evidence_support"] in {"contradicted", "not_supported"} or not edge["evidence_ids"] for edge in case_edges):
        codes.add("evidence_gap")
    return sorted(codes)


def _verify_paths(value: dict[str, object], topology: dict[str, object], graph: dict[str, dict[str, object]]) -> dict[str, dict[str, object]]:  # noqa: C901
    _exact(value, {"schema_version", "resource_type", "graph_revision_id", "paths"}, "FMEA_PROPAGATION_PATH_INVALID")
    if value["resource_type"] != "propagation_paths" or value["graph_revision_id"] != "graph-reviewed-1":
        _fail("FMEA_PROPAGATION_PATH_INVALID")
    paths = _list(value["paths"], "FMEA_PROPAGATION_PATH_INVALID")
    by_case: dict[str, dict[str, object]] = {}
    referenced: set[str] = set()
    for raw in paths:
        path = _exact(raw, {"path_id", "case_id", "analysis_id", "source_entity_id", "target_entity_id", "edge_ids", "edges", "path_length", "is_cyclic", "requires_human_review"}, "FMEA_PROPAGATION_PATH_INVALID")
        case_id = _text(path["case_id"], "FMEA_PROPAGATION_PATH_INVALID")
        if case_id in by_case or case_id not in CASE_IDS or path["path_id"] != f"path-{case_id}" or path["analysis_id"] != "analysis-fuel-combustion-1":
            _fail("FMEA_PROPAGATION_PATH_INVALID")
        edge_values = _list(path["edges"], "FMEA_PROPAGATION_PATH_INVALID")
        edge_ids = _list(path["edge_ids"], "FMEA_PROPAGATION_PATH_INVALID")
        if len(edge_values) != len(edge_ids) or not edge_values or path["path_length"] != len(edge_values) or any(not isinstance(item, str) for item in edge_ids) or len(edge_ids) != len(set(edge_ids)):
            _fail("FMEA_PROPAGATION_PATH_INVALID")
        normalized_edges: list[dict[str, object]] = []
        for raw_edge in edge_values:
            edge = _mapping(raw_edge, "FMEA_PROPAGATION_PATH_INVALID")
            if not edge.get("evidence_ids"):
                _fail("FMEA_PROPAGATION_EVIDENCE_INVALID")
            normalized_edges.append(edge)
        if path["source_entity_id"] != normalized_edges[0].get("source_entity_id") or path["target_entity_id"] != normalized_edges[-1].get("target_entity_id"):
            _fail("FMEA_PROPAGATION_PATH_INVALID")
        for previous, current in pairwise(normalized_edges):
            if previous.get("target_entity_id") != current.get("source_entity_id"):
                _fail("FMEA_PROPAGATION_PATH_INVALID")
        visited: set[object] = set()
        repeated = False
        for edge in normalized_edges:
            source = edge.get("source_entity_id")
            if source in visited:
                repeated = True
            visited.add(source)
        if normalized_edges[-1].get("target_entity_id") in visited:
            repeated = True
        if bool(path["is_cyclic"]) != repeated:
            _fail("FMEA_PROPAGATION_PATH_INVALID")
        if path["requires_human_review"] is not (case_id not in {"forward", "reverse"}):
            _fail("FMEA_PROPAGATION_REVIEW_POLICY_INVALID")
        for edge, edge_id in zip(normalized_edges, edge_ids, strict=True):
            if edge_id not in graph:
                _fail("FMEA_PROPAGATION_PATH_INVALID")
            if edge["edge_id"] != edge_id:
                _fail("FMEA_PROPAGATION_PATH_INVALID")
            _validate_edge(edge, topology, review_status=graph[edge_id]["review_status"])
            if edge != graph[edge_id]:
                _fail("FMEA_PROPAGATION_PATH_INVALID")
            referenced.add(edge_id)
        by_case[case_id] = path
    if set(by_case) != set(CASE_IDS) or referenced != set(graph):
        _fail("FMEA_PROPAGATION_PATH_INVALID")
    return by_case


def _verify_decisions(value: dict[str, object], paths: dict[str, dict[str, object]], graph: dict[str, dict[str, object]]) -> list[dict[str, object]]:  # noqa: C901
    _exact(value, {"schema_version", "resource_type", "graph_revision_id", "decisions"}, "FMEA_PROPAGATION_REVIEW_POLICY_INVALID")
    if value["resource_type"] != "propagation_decisions" or value["graph_revision_id"] != "graph-reviewed-1":
        _fail("FMEA_PROPAGATION_REVIEW_POLICY_INVALID")
    decisions = _list(value["decisions"], "FMEA_PROPAGATION_REVIEW_POLICY_INVALID")
    if len(decisions) != len(CASE_IDS):
        _fail("FMEA_PROPAGATION_REVIEW_POLICY_INVALID")
    by_case: dict[str, dict[str, object]] = {}
    for raw in decisions:
        decision = _exact(raw, {"decision_id", "case_id", "edge_ids", "action", "confirmed", "actor", "reason", "expected_graph_record_version", "applied_graph_record_version"}, "FMEA_PROPAGATION_REVIEW_POLICY_INVALID")
        case_id = _text(decision["case_id"], "FMEA_PROPAGATION_REVIEW_POLICY_INVALID")
        if case_id in by_case or case_id not in CASE_IDS:
            _fail("FMEA_PROPAGATION_REVIEW_POLICY_INVALID")
        actor_value = _mapping(decision["actor"], "FMEA_PROPAGATION_REVIEW_POLICY_INVALID")
        if decision["confirmed"] is True and actor_value.get("actor_type") == "model":
            _fail("FMEA_PROPAGATION_MODEL_AUTHORITY_INVALID")
        actor = _exact(actor_value, {"actor_id", "actor_type", "roles"}, "FMEA_PROPAGATION_REVIEW_POLICY_INVALID")
        if actor != {
            "actor_id": "propagation-reviewer-1",
            "actor_type": "human",
            "roles": ["propagation_reviewer"],
        }:
            _fail("FMEA_PROPAGATION_REVIEW_POLICY_INVALID")
        if not isinstance(decision["confirmed"], bool) or decision["expected_graph_record_version"] != 1 or decision["decision_id"] != f"decision-{case_id}":
            _fail("FMEA_PROPAGATION_REVIEW_POLICY_INVALID")
        by_case[case_id] = decision
    for case_id in CASE_IDS:
        decision = by_case[case_id]
        edge_ids = [edge["edge_id"] for edge in _case_edges(graph, case_id)]
        if decision["edge_ids"] != edge_ids:
            _fail("FMEA_PROPAGATION_REVIEW_POLICY_INVALID")
        required = _required_codes(_case_edges(graph, case_id), paths[case_id])
        requires_review = bool(required)
        expected_confirmed = not requires_review
        if decision["confirmed"] is not expected_confirmed or decision["action"] != ("confirm" if expected_confirmed else "retain_for_human_review") or decision["applied_graph_record_version"] != (2 if expected_confirmed else 1):
            _fail("FMEA_PROPAGATION_REVIEW_POLICY_INVALID")
    return decisions


def _verify_issues(value: dict[str, object], paths: dict[str, dict[str, object]], graph: dict[str, dict[str, object]]) -> list[dict[str, object]]:
    _exact(value, {"schema_version", "resource_type", "graph_revision_id", "issues"}, "FMEA_PROPAGATION_ISSUE_INVALID")
    if value["resource_type"] != "propagation_issues" or value["graph_revision_id"] != "graph-reviewed-1":
        _fail("FMEA_PROPAGATION_ISSUE_INVALID")
    issues = _list(value["issues"], "FMEA_PROPAGATION_ISSUE_INVALID")
    actual: dict[str, dict[str, object]] = {}
    expected_count = 0
    for case_id in CASE_IDS:
        case_edges = _case_edges(graph, case_id)
        codes = _required_codes(case_edges, paths[case_id])
        expected_count += len(codes)
        for index, code in enumerate(codes, start=1):
            actual[f"issue-{case_id}-{index}"] = {"case_id": case_id, "code": code, "edge_ids": [edge["edge_id"] for edge in case_edges], "severity": "important", "requires_human_review": True}
    if len(issues) != expected_count:
        _fail("FMEA_PROPAGATION_ISSUE_INVALID")
    issue_ids: set[str] = set()
    for raw in issues:
        issue = _exact(raw, {"issue_id", "case_id", "code", "severity", "edge_ids", "requires_human_review"}, "FMEA_PROPAGATION_ISSUE_INVALID")
        issue_id = _text(issue["issue_id"], "FMEA_PROPAGATION_ISSUE_INVALID")
        if issue_id in issue_ids or issue_id not in actual or {key: issue[key] for key in actual[issue_id]} != actual[issue_id]:
            _fail("FMEA_PROPAGATION_ISSUE_INVALID")
        issue_ids.add(issue_id)
    return [cast(dict[str, object], item) for item in issues]


def _verify_audit(value: dict[str, object], decisions: list[dict[str, object]]) -> dict[str, int]:  # noqa: C901
    _exact(value, {"schema_version", "resource_type", "events", "chain_head", "model_proposal_count", "model_confirmation_count", "human_confirmation_count", "human_review_required_count"}, "FMEA_PROPAGATION_AUDIT_INVALID")
    if value["resource_type"] != "propagation_audit_summary":
        _fail("FMEA_PROPAGATION_AUDIT_INVALID")
    events = _list(value["events"], "FMEA_PROPAGATION_AUDIT_INVALID")
    if len(events) != 10:
        _fail("FMEA_PROPAGATION_AUDIT_INVALID")
    event_ids: set[str] = set()
    previous_event_hash: str | None = None
    by_case: dict[str, dict[str, object]] = {}
    decisions_by_case = {str(item["case_id"]): item for item in decisions}
    if set(decisions_by_case) != set(CASE_IDS):
        _fail("FMEA_PROPAGATION_AUDIT_INVALID")
    event_fields = {"event_id", "event_type", "actor_id", "actor_type", "case_id", "resource_type", "resource_id", "decision_id", "action", "graph_revision_id", "previous_event_hash", "event_hash"}
    for index, raw in enumerate(events):
        event = _exact(raw, event_fields, "FMEA_PROPAGATION_AUDIT_INVALID")
        event_id = _text(event["event_id"], "FMEA_PROPAGATION_AUDIT_INVALID")
        if event_id in event_ids:
            _fail("FMEA_PROPAGATION_DUPLICATE_ID")
        event_ids.add(event_id)
        case_id = _text(event["case_id"], "FMEA_PROPAGATION_AUDIT_INVALID")
        if case_id not in CASE_IDS or index // 2 >= len(CASE_IDS) or case_id != CASE_IDS[index // 2]:
            _fail("FMEA_PROPAGATION_AUDIT_INVALID")
        expected_decision_id = f"decision-{case_id}"
        expected_review = index % 2 == 1
        decision_actor = _mapping(decisions_by_case[case_id]["actor"], "FMEA_PROPAGATION_AUDIT_INVALID")
        expected = {
            "event_id": f"event-review-{case_id}" if expected_review else f"event-proposal-{case_id}",
            "event_type": ("propagation.confirmed" if decisions_by_case[case_id]["confirmed"] else "propagation.review_required") if expected_review else "propagation.proposed",
            "actor_id": decision_actor["actor_id"] if expected_review else "deterministic-offline-model",
            "actor_type": decision_actor["actor_type"] if expected_review else "model",
            "case_id": case_id,
            "resource_type": "propagation_decision" if expected_review else "propagation_path",
            "resource_id": expected_decision_id if expected_review else f"path-{case_id}",
            "decision_id": expected_decision_id,
            "action": decisions_by_case[case_id]["action"] if expected_review else "propose",
            "graph_revision_id": "graph-reviewed-1",
        }
        if {key: event[key] for key in expected} != expected or event["previous_event_hash"] != previous_event_hash:
            _fail("FMEA_PROPAGATION_AUDIT_INVALID")
        if event["actor_type"] == "model" and event["event_type"] != "propagation.proposed":
            _fail("FMEA_PROPAGATION_MODEL_AUTHORITY_INVALID")
        event_hash = event["event_hash"]
        body = {key: item for key, item in event.items() if key != "event_hash"}
        if event_hash != _hash_json(body):
            _fail("FMEA_PROPAGATION_AUDIT_INVALID")
        _sha256_hash(event_hash, "FMEA_PROPAGATION_AUDIT_INVALID")
        previous_event_hash = event_hash
        if expected_review:
            by_case[case_id] = event
    if value["chain_head"] != previous_event_hash or set(by_case) != set(CASE_IDS):
        _fail("FMEA_PROPAGATION_AUDIT_INVALID")
    expected = {"model_proposal_count": 5, "model_confirmation_count": 0, "human_confirmation_count": 2, "human_review_required_count": 3}
    if {key: value.get(key) for key in expected} != expected:
        _fail("FMEA_PROPAGATION_AUDIT_INVALID")
    if sum(1 for item in decisions if item["confirmed"]) != value["human_confirmation_count"]:
        _fail("FMEA_PROPAGATION_AUDIT_INVALID")
    return cast(dict[str, int], expected)


def _verify_summary(value: dict[str, object], loaded: dict[str, tuple[dict[str, object], bytes]], topology: dict[str, object], proposal: dict[str, dict[str, object]], graph: dict[str, dict[str, object]], graph_hash: object, paths: dict[str, dict[str, object]], decisions: list[dict[str, object]], issues: list[dict[str, object]], audit: dict[str, int]) -> None:
    expected = {"schema_version", "resource_type", "status", "case_ids", "evidence_profiles", "topology_hash", "rule_pack_hash", "graph_hash", "edge_count", "path_count", "issue_count", "decision_count", "audit_event_count", "invented_endpoint_count", "model_confirmation_count", "human_confirmation_count", "human_review_required_count", "artifact_hashes"}
    _exact(value, expected, "FMEA_PROPAGATION_SUMMARY_INVALID")
    if value["resource_type"] != "propagation_acceptance_summary" or value["status"] != "passed" or value["case_ids"] != CASE_IDS or value["evidence_profiles"] != EVIDENCE_PROFILES or value["topology_hash"] != topology["snapshot"]["topology_hash"] or value["rule_pack_hash"] != topology["rule_pack_hash"] or value["graph_hash"] != graph_hash or value["edge_count"] != len(proposal) or value["path_count"] != len(paths) or value["issue_count"] != len(issues) or value["decision_count"] != len(decisions) or value["audit_event_count"] != 10 or value["invented_endpoint_count"] != 0 or value["model_confirmation_count"] != 0 or value["human_confirmation_count"] != audit["human_confirmation_count"] or value["human_review_required_count"] != audit["human_review_required_count"]:
        _fail("FMEA_PROPAGATION_SUMMARY_INVALID")
    hashes = _exact(value["artifact_hashes"], ARTIFACT_NAMES - {"acceptance-summary.json"}, "FMEA_PROPAGATION_SUMMARY_INVALID")
    for name in ARTIFACT_NAMES - {"acceptance-summary.json"}:
        if hashes[name] != _hash_bytes(loaded[name][1]):
            _fail("FMEA_PROPAGATION_ARTIFACT_HASH_INVALID")
        _sha256_hash(hashes[name], "FMEA_PROPAGATION_ARTIFACT_HASH_INVALID")


def verify_acceptance_directory(directory: str | Path) -> dict[str, object]:
    root = Path(directory).expanduser().absolute()
    if not _safe_artifact_directory(root):
        _fail("FMEA_PROPAGATION_ARTIFACT_SET_INVALID")
    try:
        children = tuple(root.iterdir())
    except OSError:
        _fail("FMEA_PROPAGATION_ARTIFACT_SET_INVALID")
    if any(not _safe_file(path) for path in children) or {path.name for path in children} != ARTIFACT_NAMES:
        _fail("FMEA_PROPAGATION_ARTIFACT_SET_INVALID")
    loaded = {name: _load(root / name) for name in ARTIFACT_NAMES}
    artifacts = {name: value for name, (value, _) in loaded.items()}
    for value in artifacts.values():
        _schema(value)
    topology = _verify_topology(artifacts["topology.json"])
    proposal = _verify_proposal(artifacts["proposal.json"], topology)
    graph_artifact = artifacts["reviewed-graph.json"]
    graph = _verify_graph(graph_artifact, topology, proposal)
    paths = _verify_paths(artifacts["paths.json"], topology, graph)
    decisions = _verify_decisions(artifacts["decisions.json"], paths, graph)
    issues = _verify_issues(artifacts["issues.json"], paths, graph)
    audit = _verify_audit(artifacts["audit-summary.json"], decisions)
    _verify_summary(artifacts["acceptance-summary.json"], loaded, topology, proposal, graph, graph_artifact["graph_hash"], paths, decisions, issues, audit)
    return artifacts["acceptance-summary.json"]


def _default_root() -> Path:
    return Path(__file__).resolve().parents[1] / ".local" / "fmea-propagation-acceptance"


def _latest(root: Path) -> Path:
    if not _safe_artifact_directory(root):
        _fail("FMEA_PROPAGATION_ARTIFACT_SET_INVALID")
    candidates = []
    for path in root.iterdir():
        if _safe_artifact_directory(path) and (path / "acceptance-summary.json").is_file():
            candidates.append(path)
    if not candidates:
        _fail("FMEA_PROPAGATION_ARTIFACT_SET_INVALID")
    return max(candidates, key=lambda path: path.name)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--artifact-dir")
    target.add_argument("--latest", action="store_true")
    parser.add_argument("--output-root", default=str(_default_root()))
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        directory = _latest(Path(args.output_root)) if args.latest else Path(args.artifact_dir)
        summary = verify_acceptance_directory(directory)
        sys.stdout.write(json.dumps({"schema_version": summary["schema_version"], "status": "passed"}, separators=(",", ":")) + "\n")
    except Exception as exc:
        code = exc.code if isinstance(exc, AcceptanceVerificationError) else "FMEA_PROPAGATION_VERIFICATION_FAILED"
        sys.stdout.write(json.dumps({"status": "failed", "error": {"code": code}}, separators=(",", ":")) + "\n")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ARTIFACT_NAMES",
    "CASE_IDS",
    "EVIDENCE_PROFILES",
    "SCHEMA_VERSION",
    "AcceptanceVerificationError",
    "_safe_artifact_directory",
    "main",
    "verify_acceptance_directory",
]
