"""Strict source loaders for immutable FMEA domain and scoring packs.

This module deliberately stops at source decoding and semantic normalization.  It
does not discover, persist, or register packs on disk; those concerns belong to
the filesystem registry slice.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import NoReturn, cast

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


def _invalid(message: str, cause: BaseException | None = None) -> NoReturn:
    error = FmeaDomainError(message)
    if cause is None:
        raise error
    raise error from cause


def _read_path(path: Path) -> bytes:
    try:
        return path.read_bytes()
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
    if isinstance(node, yaml.nodes.MappingNode):
        seen: set[tuple[str, str]] = set()
        for key_node, value_node in node.value:
            identity = _node_key(key_node)
            if identity in seen:
                _invalid("FMEA YAML source contains duplicate YAML key")
            seen.add(identity)
            _reject_duplicate_keys(key_node)
            _reject_duplicate_keys(value_node)
    elif isinstance(node, yaml.nodes.SequenceNode):
        for child in node.value:
            _reject_duplicate_keys(child)


def _load_yaml(source: bytes | str | Path) -> object:
    raw = _source_bytes(source)
    text = raw.decode("utf-8", errors="strict")
    try:
        events = tuple(yaml.parse(text, Loader=yaml.SafeLoader))
    except yaml.YAMLError as exc:
        _invalid("FMEA YAML source is invalid", exc)
    document_count = sum(isinstance(event, yaml.events.DocumentStartEvent) for event in events)
    if document_count != 1:
        _invalid("FMEA YAML source must contain exactly one document")
    if any(isinstance(event, yaml.events.AliasEvent) or getattr(event, "anchor", None) is not None for event in events):
        _invalid("FMEA YAML source aliases and anchors are not allowed")
    try:
        node = yaml.compose(text, Loader=yaml.SafeLoader)
        _reject_duplicate_keys(node)
        # Keep construction on PyYAML's safe_load boundary; unknown tags and
        # arbitrary Python objects must remain rejected by the safe loader.
        loaded = yaml.safe_load(text)
    except FmeaDomainError:
        raise
    except yaml.YAMLError as exc:
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
    "canonical_domain_pack_body",
    "canonical_scoring_rule_body",
    "domain_pack_content_hash",
    "load_domain_pack_manifest",
    "load_scoring_rule_pack",
    "scoring_rule_content_hash",
]
