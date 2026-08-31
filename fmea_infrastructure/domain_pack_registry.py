"""Strict source loaders for immutable FMEA domain and scoring packs.

This module deliberately stops at source decoding and semantic normalization.  It
does not discover, persist, or register packs on disk; those concerns belong to
the filesystem registry slice.
"""

from __future__ import annotations

import errno
import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Generic, NoReturn, TypeVar, cast

import yaml  # type: ignore[import-untyped]

from core_domain.fmea.domain_pack import DomainPackManifest
from core_domain.fmea.errors import FmeaDomainError
from core_domain.fmea.scoring import ScoringRulePack

_MAX_SOURCE_BYTES = 1024 * 1024
_DOMAIN_ROOT_KEYS = frozenset({"domain_pack"})
_DOMAIN_KEYS = frozenset({
    "id",
    "version",
    "content_hash",
    "kernel_compatibility_range",
    "compatible_schema_ids",
    "analysis_types",
    "templates",
    "scoring_rules",
    "propagation_rules",
    "extension_fields",
})
_SCORING_ROOT_KEYS = frozenset({"rule_pack"})
_SCORING_KEYS = frozenset({
    "id",
    "version",
    "applicable_analysis_types",
    "score_range",
    "dimensions",
    "occurrence",
    "detection",
    "decision_severity",
    "rpn",
    "risk_matrix",
    "priority",
    "uncertainty",
    "policy_basis",
})
_DIMENSION_NAMES = ("severity", "occurrence", "detection")
_ANCHOR_KEYS = frozenset({"anchors"})
_REGISTRY_SUFFIXES = frozenset({".yaml", ".yml"})
_REGISTRY_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_REGISTRY_SEMVER = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
_REGISTRY_HASH = re.compile(r"^[0-9a-f]{64}$")
_MAX_YAML_DEPTH = 128
_MAX_YAML_EVENTS = 8192
_MAX_YAML_NODES = 4096
_MAX_READ_CHUNK_BYTES = 64 * 1024
_MAX_STORED_BODY_BYTES = 256 * 1024
_MAX_STORED_MANIFEST_BYTES = 64 * 1024
_WINDOWS_RESERVED_NAMES = frozenset({
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
})

_ModelT = TypeVar("_ModelT")


class _BoundedReadLimitExceeded(Exception):
    """Internal signal that a bounded file read found more bytes than allowed."""


class _UnsafeFilePath(Exception):
    """Internal signal that a path changed or traversed a reparse/link object."""


def _invalid(message: str, cause: BaseException | None = None) -> NoReturn:
    error = FmeaDomainError(message)
    if cause is None:
        raise error
    raise error from cause


def _read_path(path: Path) -> bytes:
    try:
        return _read_bounded_path(path, _MAX_SOURCE_BYTES)
    except _BoundedReadLimitExceeded as exc:
        _invalid("FMEA YAML source exceeds 1 MiB", exc)
    except _UnsafeFilePath as exc:
        _invalid("FMEA YAML source is invalid", exc)
    except OSError as exc:
        _invalid("FMEA YAML source is invalid", exc)


def _encode_text(text: str) -> bytes:
    try:
        return text.encode("utf-8")
    except UnicodeEncodeError as exc:
        _invalid("FMEA YAML source is not valid UTF-8", exc)


def _source_text_or_path(source: str) -> bytes:
    # Text is the normal string form.  Supporting an existing path string as
    # well keeps the boundary convenient for CLI callers without making a
    # missing path look like a valid source.
    if "\n" in source or "\r" in source:
        return _encode_text(source)
    try:
        candidate = Path(source)
        is_file = candidate.is_file()
    except (OSError, ValueError):
        return _encode_text(source)
    return _read_path(candidate) if is_file else _encode_text(source)


def _source_bytes(source: bytes | str | Path) -> bytes:
    if isinstance(source, Path):
        raw = _read_path(source)
    elif isinstance(source, bytes):
        raw = source
    elif isinstance(source, str):
        raw = _source_text_or_path(source)
    else:
        _invalid("FMEA YAML source must be bytes, text, or a Path")

    if len(raw) > _MAX_SOURCE_BYTES:
        _invalid("FMEA YAML source exceeds 1 MiB")
    try:
        raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        _invalid("FMEA YAML source is not valid UTF-8", exc)
    return raw


def _node_key(node: object) -> tuple[str, str]:
    if isinstance(node, yaml.nodes.ScalarNode):
        return cast("str", node.tag), cast("str", node.value)
    return type(node).__name__, repr(node)


def _reject_duplicate_keys(node: object | None) -> None:
    if node is None:
        return
    pending: list[tuple[object, int]] = [(node, 0)]
    node_count = 0
    while pending:
        current, depth = pending.pop()
        node_count += 1
        if node_count > _MAX_YAML_NODES or depth > _MAX_YAML_DEPTH:
            _invalid("FMEA YAML source is invalid: parser resource limits exceeded")
        if isinstance(current, yaml.nodes.MappingNode):
            seen: set[tuple[str, str]] = set()
            children: list[object] = []
            for key_node, value_node in current.value:
                identity = _node_key(key_node)
                if identity in seen:
                    _invalid("FMEA YAML source contains duplicate YAML key")
                seen.add(identity)
                children.extend((key_node, value_node))
            pending.extend((child, depth + 1) for child in reversed(children))
        elif isinstance(current, yaml.nodes.SequenceNode):
            pending.extend((child, depth + 1) for child in reversed(current.value))


def _consume_yaml_event(event: object, depth: int, node_count: int) -> tuple[int, int]:
    if isinstance(event, yaml.events.AliasEvent) or getattr(event, "anchor", None) is not None:
        _invalid("FMEA YAML source aliases and anchors are not allowed")
    if isinstance(event, yaml.events.MappingStartEvent | yaml.events.SequenceStartEvent):
        node_count += 1
        depth += 1
        if depth > _MAX_YAML_DEPTH:
            _invalid("FMEA YAML source is invalid: parser resource limits exceeded")
    elif isinstance(event, yaml.events.ScalarEvent):
        node_count += 1
    elif isinstance(event, yaml.events.MappingEndEvent | yaml.events.SequenceEndEvent):
        depth -= 1
    if node_count > _MAX_YAML_NODES:
        _invalid("FMEA YAML source is invalid: parser resource limits exceeded")
    return depth, node_count


def _parse_yaml_event_limits(text: str) -> int:
    document_count = 0
    depth = 0
    event_count = 0
    node_count = 0
    try:
        for event in yaml.parse(text, Loader=yaml.SafeLoader):
            event_count += 1
            if event_count > _MAX_YAML_EVENTS:
                _invalid("FMEA YAML source is invalid: parser resource limits exceeded")
            if isinstance(event, yaml.events.DocumentStartEvent):
                document_count += 1
            depth, node_count = _consume_yaml_event(event, depth, node_count)
    except FmeaDomainError:
        raise
    except (yaml.YAMLError, RecursionError) as exc:
        _invalid("FMEA YAML source is invalid", exc)
    if depth != 0:
        _invalid("FMEA YAML source is invalid")
    return document_count


def _load_yaml(source: bytes | str | Path) -> object:
    raw = _source_bytes(source)
    text = raw.decode("utf-8", errors="strict")
    document_count = _parse_yaml_event_limits(text)
    if document_count != 1:
        _invalid("FMEA YAML source must contain exactly one document")
    try:
        node = yaml.compose(text, Loader=yaml.SafeLoader)
        _reject_duplicate_keys(node)
        # Keep construction on PyYAML's safe_load boundary; unknown tags and
        # arbitrary Python objects must remain rejected by the safe loader.
        loaded = yaml.safe_load(text)
    except FmeaDomainError:
        raise
    except (yaml.YAMLError, RecursionError) as exc:
        _invalid("FMEA YAML source is invalid", exc)
    return loaded


def _mapping(value: object, field_name: str) -> dict[str, object]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        _invalid(f"{field_name} must be a mapping")
    return cast("dict[str, object]", value)


def _exact_mapping(value: object, field_name: str, expected: frozenset[str]) -> dict[str, object]:
    mapping = _mapping(value, field_name)
    keys = set(mapping)
    unknown = sorted(keys - expected)
    if unknown:
        _invalid(f"{field_name} contains unknown key: {unknown[0]}")
    missing = sorted(expected - keys)
    if missing:
        _invalid(f"{field_name} is missing key: {missing[0]}")
    return mapping


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _invalid(f"{field_name} must be a non-empty string")
    return value.strip()


def _string_list(value: object, field_name: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, list):
        _invalid(f"{field_name} must be a list")
    values = tuple(_text(item, f"{field_name} item") for item in value)
    if not allow_empty and not values:
        _invalid(f"{field_name} must not be empty")
    if len(values) != len(set(values)):
        _invalid(f"{field_name} contains duplicate values")
    return values


def _identity_list(value: object, field_name: str, *, allow_empty: bool = True) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, list):
        _invalid(f"{field_name} must be a list")
    result: list[tuple[str, str]] = []
    for index, item in enumerate(value):
        mapping = _exact_mapping(item, f"{field_name}[{index}]", frozenset({"id", "version"}))
        result.append((
            _text(mapping["id"], f"{field_name}[{index}].id"),
            _text(mapping["version"], f"{field_name}[{index}].version"),
        ))
    identities = tuple(result)
    if not allow_empty and not identities:
        _invalid(f"{field_name} must not be empty")
    if len(identities) != len(set(identities)):
        _invalid(f"{field_name} contains duplicate identities")
    return identities


def _domain_extensions(value: object) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, list):
        _invalid("domain_pack.extension_fields must be a list")
    result: list[tuple[str, str]] = []
    for index, item in enumerate(value):
        mapping = _exact_mapping(item, f"domain_pack.extension_fields[{index}]", frozenset({"key", "type"}))
        result.append((
            _text(mapping["key"], f"domain_pack.extension_fields[{index}].key"),
            _text(mapping["type"], f"domain_pack.extension_fields[{index}].type"),
        ))
    keys = tuple(key for key, _ in result)
    if len(keys) != len(set(keys)):
        _invalid("domain_pack.extension_fields contains duplicate keys")
    return tuple(result)


def _canonical_json(value: Mapping[str, object]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _domain_body(manifest: DomainPackManifest) -> dict[str, object]:
    return {
        "id": manifest.pack_id,
        "version": manifest.version,
        "kernel_compatibility_range": manifest.kernel_compatibility_range,
        "compatible_schema_ids": list(manifest.compatible_schema_ids),
        "analysis_types": list(manifest.analysis_types),
        "templates": [{"id": item_id, "version": version} for item_id, version in manifest.template_identities],
        "scoring_rules": [{"id": item_id, "version": version} for item_id, version in manifest.scoring_rule_identities],
        "propagation_rules": [
            {"id": item_id, "version": version} for item_id, version in manifest.propagation_rule_identities
        ],
        "extension_fields": [{"key": key, "type": value_type} for key, value_type in manifest.extension_fields],
    }


def canonical_domain_pack_body(manifest: DomainPackManifest) -> str:
    """Return the stable semantic JSON body used by a domain-pack content hash."""

    if not isinstance(manifest, DomainPackManifest):
        _invalid("domain pack manifest is invalid")
    return _canonical_json(_domain_body(manifest))


def domain_pack_content_hash(manifest: DomainPackManifest) -> str:
    """Calculate the SHA-256 hash of a normalized domain-pack semantic body."""

    return hashlib.sha256(canonical_domain_pack_body(manifest).encode("utf-8")).hexdigest()


def load_domain_pack_manifest(source: bytes | str | Path) -> DomainPackManifest:
    """Load and validate one strict domain-pack manifest source."""

    loaded = _load_yaml(source)
    root = _exact_mapping(loaded, "root", _DOMAIN_ROOT_KEYS)
    raw = _exact_mapping(root["domain_pack"], "domain_pack", _DOMAIN_KEYS)
    try:
        manifest = DomainPackManifest(
            pack_id=_text(raw["id"], "domain_pack.id"),
            version=_text(raw["version"], "domain_pack.version"),
            content_hash=_text(raw["content_hash"], "domain_pack.content_hash"),
            compatible_schema_ids=_string_list(raw["compatible_schema_ids"], "domain_pack.compatible_schema_ids"),
            analysis_types=_string_list(raw["analysis_types"], "domain_pack.analysis_types"),
            template_identities=_identity_list(raw["templates"], "domain_pack.templates"),
            scoring_rule_identities=_identity_list(raw["scoring_rules"], "domain_pack.scoring_rules"),
            propagation_rule_identities=_identity_list(raw["propagation_rules"], "domain_pack.propagation_rules"),
            extension_fields=_domain_extensions(raw["extension_fields"]),
            kernel_compatibility_range=_text(
                raw["kernel_compatibility_range"], "domain_pack.kernel_compatibility_range"
            ),
        )
    except FmeaDomainError:
        raise
    except (TypeError, ValueError) as exc:
        _invalid("domain_pack contains invalid field types", exc)
    if domain_pack_content_hash(manifest) != manifest.content_hash:
        _invalid("domain_pack content_hash mismatch")
    return manifest


def _integer(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _invalid(f"{field_name} must be an integer")
    return value


def _anchor_map(value: object, field_name: str) -> tuple[tuple[int, str], ...]:
    mapping = _exact_mapping(value, field_name, _ANCHOR_KEYS)
    anchors = mapping["anchors"]
    if not isinstance(anchors, dict):
        _invalid(f"{field_name}.anchors must be a mapping")
    normalized: list[tuple[int, str]] = []
    for raw_score, raw_description in anchors.items():
        if isinstance(raw_score, bool) or not isinstance(raw_score, int):
            _invalid(f"{field_name}.anchors score must be an integer")
        normalized.append((raw_score, _text(raw_description, f"{field_name}.anchors[{raw_score}]")))
    scores = tuple(score for score, _ in normalized)
    if len(scores) != len(set(scores)):
        _invalid(f"{field_name}.anchors contains duplicate scores")
    if set(scores) != set(range(1, 11)):
        _invalid(f"{field_name}.anchors must contain complete scores 1..10")
    return tuple(sorted(normalized))


def _dimension_anchors(value: object) -> tuple[tuple[str, tuple[tuple[int, str], ...]], ...]:
    dimensions = _exact_mapping(value, "rule_pack.dimensions", frozenset(_DIMENSION_NAMES))
    result = []
    for name in _DIMENSION_NAMES:
        result.append((name, _anchor_map(dimensions[name], f"rule_pack.dimensions.{name}")))
    return tuple(result)


def _scoring_body(pack: ScoringRulePack) -> dict[str, object]:
    anchor_map = dict(pack.dimension_anchors)
    dimensions = {
        name: {"anchors": {str(score): description for score, description in anchor_map[name]}}
        for name in pack.required_dimensions
        if name in anchor_map
    }
    return {
        "id": pack.rule_pack_id,
        "version": pack.version,
        "applicable_analysis_types": list(pack.applicable_analysis_types),
        "score_range": {"min": pack.score_min, "max": pack.score_max},
        "dimensions": dimensions,
        "occurrence": {"window": pack.occurrence_window, "denominator": pack.occurrence_denominator},
        "detection": {"positions": list(pack.detection_positions)},
        "decision_severity": {"aggregation": pack.decision_severity_policy},
        "rpn": {"formula": pack.rpn_formula, "version": pack.rpn_formula_version},
        "risk_matrix": {"version": pack.risk_matrix_version},
        "priority": {
            "version": pack.decision_priority_version,
            "high_rpn": pack.high_priority_rpn,
            "critical_severity": pack.critical_severity_threshold,
            "medium_rpn": pack.medium_priority_rpn,
        },
        "uncertainty": {
            "missing_score_policy": pack.missing_score_policy,
            "conflict_score_policy": pack.conflict_score_policy,
            "uncertainty_policy": pack.uncertainty_policy,
        },
        "policy_basis": pack.policy_basis,
    }


def canonical_scoring_rule_body(pack: ScoringRulePack) -> str:
    """Return stable semantic JSON for a validated scoring-rule pack."""

    if not isinstance(pack, ScoringRulePack):
        _invalid("scoring rule pack is invalid")
    return _canonical_json(_scoring_body(pack))


def scoring_rule_content_hash(pack: ScoringRulePack) -> str:
    """Calculate the SHA-256 hash of a normalized scoring-rule semantic body."""

    return hashlib.sha256(canonical_scoring_rule_body(pack).encode("utf-8")).hexdigest()


def load_scoring_rule_pack(source: bytes | str | Path) -> ScoringRulePack:
    """Load and validate one strict scoring-rule pack source."""

    loaded = _load_yaml(source)
    root = _exact_mapping(loaded, "root", _SCORING_ROOT_KEYS)
    raw = _exact_mapping(root["rule_pack"], "rule_pack", _SCORING_KEYS)
    score_range = _exact_mapping(raw["score_range"], "rule_pack.score_range", frozenset({"min", "max"}))
    score_min = _integer(score_range["min"], "rule_pack.score_range.min")
    score_max = _integer(score_range["max"], "rule_pack.score_range.max")
    if (score_min, score_max) != (1, 10):
        _invalid("rule_pack.score_range must be exactly 1..10")
    dimension_anchors = _dimension_anchors(raw["dimensions"])

    occurrence = _exact_mapping(raw["occurrence"], "rule_pack.occurrence", frozenset({"window", "denominator"}))
    detection = _exact_mapping(raw["detection"], "rule_pack.detection", frozenset({"positions"}))
    positions = _string_list(detection["positions"], "rule_pack.detection.positions")
    decision_severity = _exact_mapping(
        raw["decision_severity"], "rule_pack.decision_severity", frozenset({"aggregation"})
    )
    rpn = _exact_mapping(raw["rpn"], "rule_pack.rpn", frozenset({"formula", "version"}))
    risk_matrix = _exact_mapping(raw["risk_matrix"], "rule_pack.risk_matrix", frozenset({"version"}))
    priority = _exact_mapping(
        raw["priority"],
        "rule_pack.priority",
        frozenset({"version", "high_rpn", "critical_severity", "medium_rpn"}),
    )
    uncertainty = _exact_mapping(
        raw["uncertainty"],
        "rule_pack.uncertainty",
        frozenset({"missing_score_policy", "conflict_score_policy", "uncertainty_policy"}),
    )
    medium_rpn = priority["medium_rpn"]
    if medium_rpn is not None:
        medium_rpn = _integer(medium_rpn, "rule_pack.priority.medium_rpn")
    critical_severity = _integer(priority["critical_severity"], "rule_pack.priority.critical_severity")
    try:
        return ScoringRulePack(
            rule_pack_id=_text(raw["id"], "rule_pack.id"),
            version=_text(raw["version"], "rule_pack.version"),
            applicable_analysis_types=_string_list(
                raw["applicable_analysis_types"], "rule_pack.applicable_analysis_types"
            ),
            severity_anchors=dict(dimension_anchors)["severity"],
            occurrence_window=_text(occurrence["window"], "rule_pack.occurrence.window"),
            occurrence_denominator=_text(occurrence["denominator"], "rule_pack.occurrence.denominator"),
            detection_positions=positions,
            score_min=score_min,
            score_max=score_max,
            rpn_formula_version=_text(rpn["version"], "rule_pack.rpn.version"),
            risk_matrix_version=_text(risk_matrix["version"], "rule_pack.risk_matrix.version"),
            decision_priority_version=_text(priority["version"], "rule_pack.priority.version"),
            high_priority_rpn=_integer(priority["high_rpn"], "rule_pack.priority.high_rpn"),
            required_dimensions=_DIMENSION_NAMES,
            dimension_anchors=dimension_anchors,
            decision_severity_policy=_text(decision_severity["aggregation"], "rule_pack.decision_severity.aggregation"),
            rpn_formula=_text(rpn["formula"], "rule_pack.rpn.formula"),
            critical_severity_threshold=critical_severity,
            medium_priority_rpn=cast("int | None", medium_rpn),
            missing_score_policy=_text(
                uncertainty["missing_score_policy"], "rule_pack.uncertainty.missing_score_policy"
            ),
            conflict_score_policy=_text(
                uncertainty["conflict_score_policy"], "rule_pack.uncertainty.conflict_score_policy"
            ),
            uncertainty_policy=_text(uncertainty["uncertainty_policy"], "rule_pack.uncertainty.uncertainty_policy"),
            policy_basis=_text(raw["policy_basis"], "rule_pack.policy_basis"),
        )
    except FmeaDomainError:
        raise
    except (TypeError, ValueError) as exc:
        _invalid("rule_pack contains invalid field types", exc)


__all__ = [
    "FileDomainPackRegistry",
    "FileScoringRuleRegistry",
    "canonical_domain_pack_body",
    "canonical_scoring_rule_body",
    "domain_pack_content_hash",
    "load_domain_pack_manifest",
    "load_scoring_rule_pack",
    "scoring_rule_content_hash",
]


def _registry_error(token: str, message: str, cause: BaseException | None = None) -> NoReturn:
    error = FmeaDomainError(f"{token}: {message}")
    if cause is None:
        raise error
    raise error from cause


def _registry_identity_segment(value: object, *, version: bool, path_code: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 128:
        _registry_error(path_code, "Registry identity is invalid.")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        _registry_error(path_code, "Registry identity is invalid.")
    if any(separator in value for separator in ("/", "\\", ":")) or value in {".", ".."}:
        _registry_error(path_code, "Registry identity is invalid.")
    if value.endswith((".", " ")):
        _registry_error(path_code, "Registry identity is invalid.")
    if version:
        if _REGISTRY_SEMVER.fullmatch(value) is None:
            _registry_error(path_code, "Registry identity is invalid.")
    elif _REGISTRY_ID.fullmatch(value) is None:
        _registry_error(path_code, "Registry identity is invalid.")
    if value.split(".", maxsplit=1)[0].upper() in _WINDOWS_RESERVED_NAMES:
        _registry_error(path_code, "Registry identity is invalid.")
    return value


def _registry_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _strict_json(data: bytes) -> object:
    def reject_constant(value: str) -> NoReturn:
        raise ValueError(value)

    return json.loads(data.decode("utf-8", errors="strict"), parse_constant=reject_constant)


def _path_lexists(path: Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    except OSError:
        # The caller immediately performs a typed lstat-based validation.  A
        # positive result here prevents an I/O error from being mistaken for a
        # missing path during that validation.
        return True
    return True


def _is_reparse_point(path: Path, info: os.stat_result | None = None) -> bool:
    try:
        stat_result = info or path.lstat()
    except FileNotFoundError:
        return False
    except OSError:
        raise
    if stat.S_ISLNK(stat_result.st_mode):
        return True
    attributes = getattr(stat_result, "st_file_attributes", 0)
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def _checked_regular_lstat(path: Path) -> os.stat_result:
    try:
        info = path.lstat()
    except OSError as exc:
        raise _UnsafeFilePath from exc
    if _is_reparse_point(path, info) or not stat.S_ISREG(info.st_mode):
        raise _UnsafeFilePath
    return info


def _checked_directory_lstat(path: Path) -> os.stat_result:
    try:
        info = path.lstat()
    except OSError as exc:
        raise _UnsafeFilePath from exc
    if _is_reparse_point(path, info) or not stat.S_ISDIR(info.st_mode):
        raise _UnsafeFilePath
    return info


def _file_identity(info: os.stat_result) -> tuple[int, int]:
    return int(getattr(info, "st_dev", 0)), int(getattr(info, "st_ino", 0))


def _same_file_identity(first: os.stat_result, second: os.stat_result) -> bool:
    first_identity = _file_identity(first)
    second_identity = _file_identity(second)
    if first_identity != (0, 0) and second_identity != (0, 0):
        return first_identity == second_identity
    return (
        first.st_mode,
        first.st_size,
        getattr(first, "st_mtime_ns", 0),
        getattr(first, "st_ctime_ns", 0),
    ) == (
        second.st_mode,
        second.st_size,
        getattr(second, "st_mtime_ns", 0),
        getattr(second, "st_ctime_ns", 0),
    )


def _verify_read_handle(path: Path, expected_info: os.stat_result, descriptor: int) -> None:
    descriptor_info = os.fstat(descriptor)
    current_info = _checked_regular_lstat(path)
    if not _same_file_identity(expected_info, descriptor_info) or not _same_file_identity(expected_info, current_info):
        raise _UnsafeFilePath


def _open_checked_read(path: Path, expected_info: os.stat_result) -> int:
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_CLOEXEC", 0)
    if os.name != "nt":
        flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(str(path), flags)
    except OSError as exc:
        try:
            current_info = path.lstat()
        except OSError:
            raise _UnsafeFilePath from exc
        if _is_reparse_point(path, current_info):
            raise _UnsafeFilePath from exc
        raise
    try:
        _verify_read_handle(path, expected_info, descriptor)
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor


def _read_bounded_path(
    path: Path,
    max_bytes: int,
    *,
    expected_info: os.stat_result | None = None,
) -> bytes:
    initial_info = _checked_regular_lstat(path) if expected_info is None else expected_info
    current_info = _checked_regular_lstat(path)
    if not _same_file_identity(initial_info, current_info):
        raise _UnsafeFilePath
    if initial_info.st_size > max_bytes:
        raise _BoundedReadLimitExceeded

    descriptor = _open_checked_read(path, initial_info)
    chunks: list[bytes] = []
    total = 0
    try:
        while True:
            remaining = max_bytes + 1 - total
            if remaining <= 0:
                raise _BoundedReadLimitExceeded
            chunk = os.read(descriptor, min(_MAX_READ_CHUNK_BYTES, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > max_bytes:
                raise _BoundedReadLimitExceeded

        final_descriptor_info = os.fstat(descriptor)
        final_path_info = _checked_regular_lstat(path)
        if not _same_file_identity(initial_info, final_descriptor_info) or not _same_file_identity(
            initial_info, final_path_info
        ):
            raise _UnsafeFilePath
        if final_descriptor_info.st_size > max_bytes:
            raise _BoundedReadLimitExceeded
        if final_descriptor_info.st_size != initial_info.st_size or final_descriptor_info.st_size != total:
            raise _UnsafeFilePath
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _raise_if_reparse(path: Path, cause: OSError) -> None:
    try:
        current_info = path.lstat()
    except OSError:
        return
    if _is_reparse_point(path, current_info):
        raise _UnsafeFilePath from cause


def _verify_new_file(path: Path, parent_info: os.stat_result, descriptor_info: os.stat_result) -> None:
    current_parent_info = _checked_directory_lstat(path.parent)
    current_path_info = _checked_regular_lstat(path)
    if not _same_file_identity(parent_info, current_parent_info) or not _same_file_identity(
        descriptor_info, current_path_info
    ):
        raise _UnsafeFilePath


def _open_exclusive_write(path: Path) -> tuple[int, os.stat_result, os.stat_result]:
    parent_info = _checked_directory_lstat(path.parent)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0) | getattr(os, "O_CLOEXEC", 0)
    if os.name != "nt":
        flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(str(path), flags, 0o600)
    except OSError as exc:
        _raise_if_reparse(path, exc)
        raise
    try:
        descriptor_info = os.fstat(descriptor)
        _verify_new_file(path, parent_info, descriptor_info)
    except BaseException:
        os.close(descriptor)
        raise
    else:
        return descriptor, parent_info, descriptor_info


def _write_all(descriptor: int, data: bytes) -> None:
    view = memoryview(data)
    offset = 0
    while offset < len(view):
        written = os.write(descriptor, view[offset:])
        if written <= 0:
            raise OSError(errno.EIO, "short registry write")
        offset += written


def _verify_written_file(
    path: Path,
    parent_info: os.stat_result,
    descriptor_info: os.stat_result,
    descriptor: int,
    expected_size: int,
) -> None:
    final_parent_info = _checked_directory_lstat(path.parent)
    final_path_info = _checked_regular_lstat(path)
    final_descriptor_info = os.fstat(descriptor)
    if (
        not _same_file_identity(parent_info, final_parent_info)
        or not _same_file_identity(descriptor_info, final_path_info)
        or not _same_file_identity(descriptor_info, final_descriptor_info)
    ):
        raise _UnsafeFilePath
    if final_descriptor_info.st_size != expected_size:
        raise OSError(errno.EIO, "short registry write")


def _path_components(path: Path) -> tuple[Path, ...]:
    anchor_parts = Path(path.anchor).parts if path.anchor else ()
    current = Path(path.anchor) if path.anchor else Path()
    components: list[Path] = []
    for part in path.parts[len(anchor_parts) :]:
        current = current / part
        components.append(current)
    return tuple(components)


class _FileImmutableRegistry(Generic[_ModelT]):
    """Contained, source-bound, immutable storage for one FMEA contract type."""

    def __init__(
        self,
        root: str | Path,
        *,
        model_type: type[_ModelT],
        loader: Callable[[bytes], _ModelT],
        canonical_body: Callable[[_ModelT], str],
        identity: Callable[[_ModelT], tuple[str, str]],
        kind: str,
        errors: Mapping[str, str],
        source_suffix: str = ".yaml",
        max_source_bytes: int = _MAX_SOURCE_BYTES,
    ) -> None:
        if source_suffix not in _REGISTRY_SUFFIXES:
            _registry_error(errors["path"], "Registry source suffix is invalid.")
        if not isinstance(max_source_bytes, int) or max_source_bytes <= 0:
            _registry_error(errors["limit"], "Registry source limit is invalid.")
        self._root = Path(root).absolute()
        self._model_type = model_type
        self._loader = loader
        self._canonical_body = canonical_body
        self._identity = identity
        self._kind = kind
        self._errors = dict(errors)
        self._source_suffix = source_suffix
        self._max_source_bytes = max_source_bytes

    @property
    def root(self) -> Path:
        return self._root

    def _raise_path(self, cause: BaseException | None = None) -> NoReturn:
        _registry_error(self._errors["path"], "Registry path is invalid.", cause)

    def _raise_io(self, cause: BaseException | None = None) -> NoReturn:
        _registry_error(self._errors["io"], "Registry I/O failed.", cause)

    def _raise_source(self, cause: BaseException | None = None) -> NoReturn:
        _registry_error(self._errors["source"], "Registry source is invalid.", cause)

    def _raise_integrity(self, cause: BaseException | None = None) -> NoReturn:
        _registry_error(self._errors["integrity"], "Stored registry integrity check failed.", cause)

    def _raise_not_found(self) -> NoReturn:
        _registry_error(self._errors["not_found"], "Registry version was not found.")

    def _raise_limit(self) -> NoReturn:
        _registry_error(self._errors["limit"], "Registry source exceeds the configured byte limit.")

    def _raise_conflict(self) -> NoReturn:
        _registry_error(self._errors["conflict"], "Registry identity already has different content.")

    def _validate_root_components(self, *, allow_missing: bool) -> None:
        root_info = self._inspect_path(self._root, allow_missing=allow_missing)
        if root_info is not None and not stat.S_ISDIR(root_info.st_mode):
            self._raise_path()

    def _lstat_or_missing(self, path: Path, *, allow_missing: bool) -> os.stat_result | None:
        try:
            return path.lstat()
        except FileNotFoundError:
            if allow_missing:
                return None
            self._raise_not_found()
        except OSError as exc:
            self._raise_path(exc)

    def _inspect_path(self, path: Path, *, allow_missing: bool) -> os.stat_result | None:
        try:
            path.relative_to(self._root)
        except ValueError as exc:
            self._raise_path(exc)
        for component in _path_components(path):
            info = self._lstat_or_missing(component, allow_missing=allow_missing)
            if info is None:
                return None
            if _is_reparse_point(component, info):
                self._raise_path()
        info = self._lstat_or_missing(path, allow_missing=allow_missing)
        if info is None:
            return None
        if _is_reparse_point(path, info):
            self._raise_path()
        return info

    def _ensure_root(self) -> None:
        self._validate_root_components(allow_missing=True)
        if not _path_lexists(self._root):
            try:
                self._root.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                self._raise_io(exc)
        self._validate_root_components(allow_missing=False)

    def _safe_identity_path(self, object_id: str, version: str) -> tuple[Path, Path]:
        _registry_identity_segment(object_id, version=False, path_code=self._errors["path"])
        _registry_identity_segment(version, version=True, path_code=self._errors["path"])
        target_identity = self._root / object_id
        target_version = target_identity / version
        try:
            target_identity.relative_to(self._root)
            target_version.relative_to(self._root)
        except ValueError as exc:
            self._raise_path(exc)
        self._validate_existing_path(target_identity, expected_directory=True, allow_missing=True)
        self._validate_existing_path(target_version, expected_directory=True, allow_missing=True)
        return target_identity, target_version

    def _validate_existing_path(
        self, path: Path, *, expected_directory: bool, allow_missing: bool
    ) -> os.stat_result | None:
        info = self._inspect_path(path, allow_missing=allow_missing)
        if info is None:
            return None
        is_directory = stat.S_ISDIR(info.st_mode)
        if is_directory != expected_directory:
            self._raise_path()
        return info

    @staticmethod
    def _write_file(path: Path, data: bytes) -> None:
        descriptor, parent_info, descriptor_info = _open_exclusive_write(path)
        try:
            _write_all(descriptor, data)
            os.fsync(descriptor)
            _verify_written_file(path, parent_info, descriptor_info, descriptor, len(data))
        finally:
            os.close(descriptor)

    @staticmethod
    def _directory_fsync_unsupported(error: OSError) -> bool:
        unsupported = {
            errno.EINVAL,
            errno.ENOSYS,
            getattr(errno, "ENOTSUP", errno.EINVAL),
            getattr(errno, "EOPNOTSUPP", errno.EINVAL),
        }
        if os.name == "nt":
            unsupported.add(errno.EACCES)
        return error.errno in unsupported

    @classmethod
    def _fsync_directory(cls, path: Path) -> None:
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        try:
            descriptor = os.open(str(path), flags)
        except OSError as exc:
            if cls._directory_fsync_unsupported(exc):
                return
            raise
        try:
            try:
                os.fsync(descriptor)
            except OSError as exc:
                if not cls._directory_fsync_unsupported(exc):
                    raise
        finally:
            os.close(descriptor)

    def _source_and_body(self, model: _ModelT, source_bytes: bytes) -> tuple[_ModelT, bytes, str]:
        if not isinstance(model, self._model_type):
            self._raise_source()
        if type(source_bytes) is not bytes:
            self._raise_source()
        if len(source_bytes) > self._max_source_bytes:
            self._raise_limit()
        try:
            loaded = self._loader(source_bytes)
            model_body = self._canonical_body(model)
            loaded_body = self._canonical_body(loaded)
        except (FmeaDomainError, TypeError, ValueError, UnicodeError) as exc:
            self._raise_source(exc)
        if self._identity(loaded) != self._identity(model) or loaded_body != model_body:
            self._raise_source()
        try:
            body_bytes = model_body.encode("utf-8")
        except UnicodeEncodeError as exc:
            self._raise_source(exc)
        return loaded, body_bytes, model_body

    def _manifest(self, model: _ModelT, body_bytes: bytes, source_bytes: bytes) -> dict[str, str]:
        object_id, version = self._identity(model)
        return {
            "kind": self._kind,
            "id": object_id,
            "version": version,
            "body_hash": _registry_hash(body_bytes),
            "source_hash": _registry_hash(source_bytes),
            "source_suffix": self._source_suffix,
        }

    def _read_bytes(self, path: Path, *, max_bytes: int) -> bytes:
        initial_info = self._validate_existing_path(path, expected_directory=False, allow_missing=False)
        if initial_info is None:
            self._raise_not_found()
        try:
            return _read_bounded_path(path, max_bytes, expected_info=initial_info)
        except _BoundedReadLimitExceeded as exc:
            self._raise_integrity(exc)
        except _UnsafeFilePath as exc:
            self._raise_path(exc)
        except (OSError, ValueError) as exc:
            self._raise_integrity(exc)

    def _stored_paths(self, version_dir: Path) -> tuple[Path, Path, Path]:
        try:
            children = tuple(version_dir.iterdir())
        except OSError as exc:
            self._raise_integrity(exc)
        for child in children:
            try:
                info = child.lstat()
            except OSError as exc:
                self._raise_integrity(exc)
            if _is_reparse_point(child, info):
                self._raise_path()
            if not stat.S_ISREG(info.st_mode):
                self._raise_integrity()
        names = {child.name for child in children}
        source_names = names & {"source.yaml", "source.yml"}
        if len(source_names) != 1 or names != source_names | {"body.json", "manifest.json"}:
            self._raise_integrity()
        source_path = version_dir / next(iter(source_names))
        return source_path, version_dir / "body.json", version_dir / "manifest.json"

    def _decode_stored_json(self, body_bytes: bytes, manifest_bytes: bytes) -> tuple[object, object]:
        if len(body_bytes) > _MAX_STORED_BODY_BYTES or len(manifest_bytes) > _MAX_STORED_MANIFEST_BYTES:
            self._raise_integrity()
        try:
            manifest_object = _strict_json(manifest_bytes)
            body_object = _strict_json(body_bytes)
            manifest_canonical = _canonical_json(cast("Mapping[str, object]", manifest_object)).encode("utf-8")
            body_canonical = _canonical_json(cast("Mapping[str, object]", body_object)).encode("utf-8")
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            self._raise_integrity(exc)
        if manifest_canonical != manifest_bytes or body_canonical != body_bytes:
            self._raise_integrity()
        return manifest_object, body_object

    def _validate_stored_manifest(
        self,
        manifest_object: object,
        *,
        object_id: str,
        version: str,
        source_path: Path,
        body_bytes: bytes,
        source_bytes: bytes,
    ) -> None:
        if not isinstance(manifest_object, dict) or set(manifest_object) != {
            "kind",
            "id",
            "version",
            "body_hash",
            "source_hash",
            "source_suffix",
        }:
            self._raise_integrity()
        expected_manifest = {
            "kind": self._kind,
            "id": object_id,
            "version": version,
            "body_hash": _registry_hash(body_bytes),
            "source_hash": _registry_hash(source_bytes),
            "source_suffix": source_path.suffix,
        }
        if manifest_object != expected_manifest:
            self._raise_integrity()

    def _verified_stored_model(self, object_id: str, version: str, version_dir: Path) -> tuple[_ModelT, bytes]:
        source_path, body_path, manifest_path = self._stored_paths(version_dir)
        source_bytes = self._read_bytes(source_path, max_bytes=self._max_source_bytes)
        body_bytes = self._read_bytes(body_path, max_bytes=_MAX_STORED_BODY_BYTES)
        manifest_bytes = self._read_bytes(manifest_path, max_bytes=_MAX_STORED_MANIFEST_BYTES)
        manifest_object, _ = self._decode_stored_json(body_bytes, manifest_bytes)
        self._validate_stored_manifest(
            manifest_object,
            object_id=object_id,
            version=version,
            source_path=source_path,
            body_bytes=body_bytes,
            source_bytes=source_bytes,
        )
        try:
            loaded = self._loader(source_bytes)
            loaded_id, loaded_version = self._identity(loaded)
            loaded_body = self._canonical_body(loaded).encode("utf-8")
        except (FmeaDomainError, TypeError, ValueError, UnicodeError) as exc:
            self._raise_integrity(exc)
        if (loaded_id, loaded_version) != (object_id, version) or loaded_body != body_bytes:
            self._raise_integrity()
        return loaded, source_bytes

    def _stored_model(self, object_id: str, version: str, version_dir: Path) -> _ModelT:
        return self._verified_stored_model(object_id, version, version_dir)[0]

    def get_source_bytes(self, object_id: str, version: str) -> bytes:
        """Return the bounded, integrity-checked source used by ``get``."""

        _, version_dir = self._safe_identity_path(object_id, version)
        self._validate_root_components(allow_missing=True)
        if not _path_lexists(self._root) or not _path_lexists(version_dir):
            self._raise_not_found()
        self._validate_existing_path(version_dir, expected_directory=True, allow_missing=False)
        return self._verified_stored_model(object_id, version, version_dir)[1]

    def _ensure_identity_directory(self, identity_dir: Path) -> None:
        self._validate_existing_path(identity_dir, expected_directory=True, allow_missing=True)
        if not _path_lexists(identity_dir):
            try:
                identity_dir.mkdir(parents=False, exist_ok=False)
            except FileExistsError:
                pass
            except OSError as exc:
                self._raise_io(exc)
            self._validate_existing_path(identity_dir, expected_directory=True, allow_missing=False)

    def _existing_model(self, object_id: str, version: str, final_dir: Path, candidate: _ModelT) -> _ModelT | None:
        if not _path_lexists(final_dir):
            return None
        self._validate_existing_path(final_dir, expected_directory=True, allow_missing=False)
        existing = self._stored_model(object_id, version, final_dir)
        if self._canonical_body(existing) == self._canonical_body(candidate):
            return existing
        self._raise_conflict()

    def _cleanup_temp(self, temp_dir: Path) -> None:
        if not _path_lexists(temp_dir):
            return
        self._validate_existing_path(temp_dir, expected_directory=True, allow_missing=False)
        try:
            shutil.rmtree(temp_dir)
        except OSError as exc:
            self._raise_io(exc)

    def _create_temp_entry(
        self,
        identity_dir: Path,
        version: str,
        loaded: _ModelT,
        body_bytes: bytes,
        source_bytes: bytes,
    ) -> Path:
        try:
            parent_info = self._validate_existing_path(identity_dir, expected_directory=True, allow_missing=False)
            if parent_info is None:
                self._raise_path()
            temp_dir = Path(tempfile.mkdtemp(prefix=f".{version}.tmp-", dir=str(identity_dir)))
            self._validate_existing_path(temp_dir, expected_directory=True, allow_missing=False)
            current_parent_info = self._validate_existing_path(
                identity_dir, expected_directory=True, allow_missing=False
            )
            if current_parent_info is None or not _same_file_identity(parent_info, current_parent_info):
                self._raise_path()
            self._write_file(temp_dir / f"source{self._source_suffix}", source_bytes)
            self._write_file(temp_dir / "body.json", body_bytes)
            manifest_bytes = _canonical_json(self._manifest(loaded, body_bytes, source_bytes)).encode("utf-8")
            self._write_file(temp_dir / "manifest.json", manifest_bytes)
            self._fsync_directory(temp_dir)
        except _UnsafeFilePath as exc:
            if "temp_dir" in locals():
                self._cleanup_temp(temp_dir)
            self._raise_path(exc)
        except FmeaDomainError:
            if "temp_dir" in locals():
                self._cleanup_temp(temp_dir)
            raise
        except OSError as exc:
            if "temp_dir" in locals():
                self._cleanup_temp(temp_dir)
            self._raise_io(exc)
        else:
            return temp_dir

    def _publish_new_model(
        self,
        identity_dir: Path,
        final_dir: Path,
        object_id: str,
        version: str,
        loaded: _ModelT,
        body_bytes: bytes,
        source_bytes: bytes,
    ) -> _ModelT:
        if _path_lexists(final_dir):
            existing = self._existing_model(object_id, version, final_dir, loaded)
            if existing is not None:
                return existing
        temp_dir = self._create_temp_entry(identity_dir, version, loaded, body_bytes, source_bytes)
        try:
            existing = self._existing_model(object_id, version, final_dir, loaded)
            if existing is not None:
                return existing
            temp_dir.rename(final_dir)
            self._fsync_directory(identity_dir)
        except FileExistsError:
            existing = self._existing_model(object_id, version, final_dir, loaded)
            if existing is not None:
                return existing
            self._raise_io()
        except FmeaDomainError:
            raise
        except OSError as exc:
            self._raise_io(exc)
        finally:
            self._cleanup_temp(temp_dir)
        return loaded

    def _register(self, model: _ModelT, source_bytes: bytes) -> _ModelT:
        loaded, body_bytes, _ = self._source_and_body(model, source_bytes)
        object_id, version = self._identity(loaded)
        identity_dir, final_dir = self._safe_identity_path(object_id, version)
        self._ensure_root()
        self._ensure_identity_directory(identity_dir)
        existing = self._existing_model(object_id, version, final_dir, loaded)
        if existing is not None:
            return existing
        return self._publish_new_model(
            identity_dir,
            final_dir,
            object_id,
            version,
            loaded,
            body_bytes,
            source_bytes,
        )

    def _get(self, object_id: str, version: str) -> _ModelT:
        _, version_dir = self._safe_identity_path(object_id, version)
        self._validate_root_components(allow_missing=True)
        if not _path_lexists(self._root):
            self._raise_not_found()
        self._validate_root_components(allow_missing=False)
        if not _path_lexists(version_dir):
            self._raise_not_found()
        self._validate_existing_path(version_dir, expected_directory=True, allow_missing=False)
        return self._stored_model(object_id, version, version_dir)


class FileDomainPackRegistry(_FileImmutableRegistry[DomainPackManifest]):
    def __init__(self, root: str | Path, *, source_suffix: str = ".yaml") -> None:
        super().__init__(
            root,
            model_type=DomainPackManifest,
            loader=load_domain_pack_manifest,
            canonical_body=canonical_domain_pack_body,
            identity=lambda manifest: (manifest.pack_id, manifest.version),
            kind="domain_pack",
            errors={
                "not_found": "DOMAIN_PACK_NOT_FOUND",
                "conflict": "DOMAIN_PACK_IDENTITY_CONFLICT",
                "path": "DOMAIN_PACK_PATH_INVALID",
                "limit": "DOMAIN_PACK_LIMIT_EXCEEDED",
                "source": "DOMAIN_PACK_SOURCE_INVALID",
                "integrity": "DOMAIN_PACK_INTEGRITY_FAILED",
                "io": "DOMAIN_PACK_REGISTRY_ERROR",
            },
            source_suffix=source_suffix,
        )

    def register(self, manifest: DomainPackManifest, source_bytes: bytes) -> DomainPackManifest:
        return self._register(manifest, source_bytes)

    def get(self, pack_id: str, version: str) -> DomainPackManifest:
        return self._get(pack_id, version)


class FileScoringRuleRegistry(_FileImmutableRegistry[ScoringRulePack]):
    def __init__(self, root: str | Path, *, source_suffix: str = ".yaml") -> None:
        super().__init__(
            root,
            model_type=ScoringRulePack,
            loader=load_scoring_rule_pack,
            canonical_body=canonical_scoring_rule_body,
            identity=lambda pack: (pack.rule_pack_id, pack.version),
            kind="scoring_rule",
            errors={
                "not_found": "SCORING_RULE_NOT_FOUND",
                "conflict": "SCORING_RULE_IDENTITY_CONFLICT",
                "path": "SCORING_RULE_PATH_INVALID",
                "limit": "SCORING_RULE_LIMIT_EXCEEDED",
                "source": "SCORING_RULE_SOURCE_INVALID",
                "integrity": "SCORING_RULE_INTEGRITY_FAILED",
                "io": "SCORING_RULE_REGISTRY_ERROR",
            },
            source_suffix=source_suffix,
        )

    def register(self, rule_pack: ScoringRulePack, source_bytes: bytes) -> ScoringRulePack:
        return self._register(rule_pack, source_bytes)

    def get(self, rule_pack_id: str, version: str) -> ScoringRulePack:
        return self._get(rule_pack_id, version)
