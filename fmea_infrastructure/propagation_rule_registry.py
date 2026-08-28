"""Strict YAML loading and immutable storage for propagation rule packs."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import NoReturn

from core_domain.fmea.errors import FmeaDomainError
from core_domain.fmea.propagation import PropagationRulePack, validate_propagation_rule_pack

from .domain_pack_registry import (
    _exact_mapping,
    _FileImmutableRegistry,
    _integer,
    _load_yaml,
    _string_list,
    _text,
)

_RULE_ROOT_KEYS = frozenset({"rule_pack"})
_RULE_KEYS = frozenset(
    {
        "id",
        "version",
        "applicable_analysis_types",
        "relation_types",
        "interface_variables",
        "units",
        "directions",
        "max_automatic_depth",
        "mandatory_review_conditions",
        "barrier_semantics",
        "timing_constraints",
        "risk_escalation",
        "prohibit_silent_fallback",
    }
)
_TIMING_KEYS = frozenset({"delay_ms", "response_time_ms", "fault_tolerance_time_ms"})
_TIMING_VALUE = "non_negative"


def _rule_error(message: str, cause: BaseException | None = None) -> NoReturn:
    error = FmeaDomainError(f"PROPAGATION_RULE_SOURCE_INVALID: {message}")
    if cause is None:
        raise error
    raise error from cause


def _validate_timing_constraints(value: object) -> None:
    try:
        mapping = _exact_mapping(value, "rule_pack.timing_constraints", _TIMING_KEYS)
    except FmeaDomainError as exc:
        _rule_error(str(exc).split(": ", 1)[-1], exc)
    for key in _TIMING_KEYS:
        if mapping[key] != _TIMING_VALUE:
            _rule_error(f"rule_pack.timing_constraints.{key} must be '{_TIMING_VALUE}'")


def _as_rule_pack(raw: Mapping[str, object]) -> PropagationRulePack:
    try:
        pack = PropagationRulePack(
            rule_pack_id=_text(raw["id"], "rule_pack.id"),
            version=_text(raw["version"], "rule_pack.version"),
            applicable_analysis_types=_string_list(
                raw["applicable_analysis_types"], "rule_pack.applicable_analysis_types"
            ),
            relation_types=_string_list(raw["relation_types"], "rule_pack.relation_types"),
            interface_variables=_string_list(raw["interface_variables"], "rule_pack.interface_variables"),
            units=_string_list(raw["units"], "rule_pack.units"),
            directions=_string_list(raw["directions"], "rule_pack.directions"),
            max_automatic_depth=_integer(raw["max_automatic_depth"], "rule_pack.max_automatic_depth"),
            mandatory_review_conditions=_string_list(
                raw["mandatory_review_conditions"], "rule_pack.mandatory_review_conditions"
            ),
            barrier_semantics=_text(raw["barrier_semantics"], "rule_pack.barrier_semantics"),
            risk_escalation=_text(raw["risk_escalation"], "rule_pack.risk_escalation"),
            prohibit_silent_fallback=raw["prohibit_silent_fallback"],  # type: ignore[arg-type]
        )
        validate_propagation_rule_pack(pack)
    except FmeaDomainError:
        raise
    except (TypeError, ValueError) as exc:
        _rule_error("rule_pack contains invalid field types", exc)
    else:
        return pack


def load_propagation_rule_pack(source: bytes | str | Path) -> PropagationRulePack:
    """Load one strict, semantically validated propagation-rule YAML source."""

    try:
        loaded = _load_yaml(source)
        root = _exact_mapping(loaded, "root", _RULE_ROOT_KEYS)
        raw = _exact_mapping(root["rule_pack"], "rule_pack", _RULE_KEYS)
        _validate_timing_constraints(raw["timing_constraints"])
        return _as_rule_pack(raw)
    except FmeaDomainError:
        raise
    except (TypeError, ValueError) as exc:
        _rule_error("rule_pack source is invalid", exc)


def _canonical_json(value: Mapping[str, object]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _rule_body(pack: PropagationRulePack) -> dict[str, object]:
    return {
        "id": pack.rule_pack_id,
        "version": pack.version,
        "applicable_analysis_types": list(pack.applicable_analysis_types),
        "relation_types": list(pack.relation_types),
        "interface_variables": list(pack.interface_variables),
        "units": list(pack.units),
        "directions": list(pack.directions),
        "max_automatic_depth": pack.max_automatic_depth,
        "mandatory_review_conditions": list(pack.mandatory_review_conditions),
        "barrier_semantics": pack.barrier_semantics,
        "timing_constraints": dict.fromkeys(sorted(_TIMING_KEYS), _TIMING_VALUE),
        "risk_escalation": pack.risk_escalation,
        "prohibit_silent_fallback": pack.prohibit_silent_fallback,
    }


def canonical_propagation_rule_body(pack: PropagationRulePack) -> str:
    """Return stable semantic JSON for one validated propagation-rule pack."""

    if not isinstance(pack, PropagationRulePack):
        _rule_error("propagation rule pack is invalid")
    validate_propagation_rule_pack(pack)
    return _canonical_json(_rule_body(pack))


def propagation_rule_content_hash(pack: PropagationRulePack) -> str:
    """Calculate the SHA-256 hash of a normalized propagation-rule body."""

    return hashlib.sha256(canonical_propagation_rule_body(pack).encode("utf-8")).hexdigest()


class FilePropagationRuleRegistry(_FileImmutableRegistry[PropagationRulePack]):
    """Contained, source-bound, immutable filesystem registry for rule packs."""

    def __init__(self, root: str | Path, *, source_suffix: str = ".yaml") -> None:
        super().__init__(
            root,
            model_type=PropagationRulePack,
            loader=load_propagation_rule_pack,
            canonical_body=canonical_propagation_rule_body,
            identity=lambda pack: (pack.rule_pack_id, pack.version),
            kind="propagation_rule",
            errors={
                "not_found": "PROPAGATION_RULE_NOT_FOUND",
                "conflict": "PROPAGATION_RULE_IDENTITY_CONFLICT",
                "path": "PROPAGATION_RULE_PATH_INVALID",
                "limit": "PROPAGATION_RULE_LIMIT_EXCEEDED",
                "source": "PROPAGATION_RULE_SOURCE_INVALID",
                "integrity": "PROPAGATION_RULE_INTEGRITY_FAILED",
                "io": "PROPAGATION_RULE_REGISTRY_ERROR",
            },
            source_suffix=source_suffix,
        )

    def register(self, rule_pack: PropagationRulePack, source_bytes: bytes) -> PropagationRulePack:
        return self._register(rule_pack, source_bytes)

    def get(self, rule_pack_id: str, version: str) -> PropagationRulePack:
        return self._get(rule_pack_id, version)


__all__ = [
    "FilePropagationRuleRegistry",
    "canonical_propagation_rule_body",
    "load_propagation_rule_pack",
    "propagation_rule_content_hash",
]
