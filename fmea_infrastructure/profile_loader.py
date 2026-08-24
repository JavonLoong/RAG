"""Strict loader for literal FMEA template profiles."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from core_domain.fmea.errors import FmeaDomainError
from fmea_application.structured_candidate_adapter import FMEA_PROFILE_FIELDS, FmeaTemplateProfile

_ROOT_KEYS = frozenset({"profile_id", "version", "template_id", "template_version", "fields"})
_FIELD_MAP = dict(FMEA_PROFILE_FIELDS)
_MAX_PROFILE_CHARS = 32_000


def _decode_profile(text: str) -> FmeaTemplateProfile:
    if len(text) > _MAX_PROFILE_CHARS:
        raise ValueError
    value = json.loads(text)
    if not isinstance(value, dict) or set(value) != _ROOT_KEYS:
        raise TypeError
    fields = value["fields"]
    if not isinstance(fields, dict) or fields != _FIELD_MAP:
        raise TypeError
    return FmeaTemplateProfile(
        profile_id=cast("str", value["profile_id"]),
        version=cast("str", value["version"]),
        template_id=cast("str", value["template_id"]),
        template_version=cast("str", value["template_version"]),
        fields=FMEA_PROFILE_FIELDS,
    )


def load_fmea_template_profile(path: str | Path) -> FmeaTemplateProfile:
    try:
        profile = _decode_profile(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
        safe_error = FmeaDomainError("FMEA profile is invalid")
    else:
        return profile
    raise safe_error


__all__ = ["load_fmea_template_profile"]
