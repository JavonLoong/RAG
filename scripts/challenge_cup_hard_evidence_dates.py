from __future__ import annotations

from datetime import date
from typing import Any


def parse_not_future_iso_date(value: str, *, today: date | None = None) -> date:
    parsed = date.fromisoformat(value)
    if parsed > (today or date.today()):
        raise ValueError("date must not be in the future")
    return parsed


def is_not_future_iso_date(value: Any, *, today: date | None = None) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parse_not_future_iso_date(value, today=today)
    except ValueError:
        return False
    return True
