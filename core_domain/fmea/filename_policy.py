"""Shared bounded filename validation for source and delivery contracts."""

from __future__ import annotations

import unicodedata

from .errors import FmeaDomainError

_MAX_FILENAME_LENGTH = 255
_WINDOWS_RESERVED_BASENAMES = frozenset(
    {
        "aux",
        "con",
        "nul",
        "prn",
        *(f"com{index}" for index in range(1, 10)),
        *(f"lpt{index}" for index in range(1, 10)),
    },
)
_INVALID_FILENAME_CHARACTERS = frozenset('\\/:*?"<>|')


def validate_filename(
    value: object,
    field_name: str = "filename",
    *,
    expected_extension: str | None = None,
) -> str:
    """Return a contained filename or fail closed on platform/path hazards."""

    if not isinstance(value, str) or not value.strip():
        raise FmeaDomainError(f"{field_name} must not be empty")  # noqa: TRY003
    if len(value) > _MAX_FILENAME_LENGTH:
        raise FmeaDomainError(f"{field_name} exceeds maximum length {_MAX_FILENAME_LENGTH}")  # noqa: TRY003
    if any(unicodedata.category(character) == "Cc" for character in value):
        raise FmeaDomainError(f"{field_name} must not contain control characters")  # noqa: TRY003
    if value.endswith((".", " ")):
        raise FmeaDomainError(f"{field_name} must not end with a dot or space")  # noqa: TRY003

    normalized = value.strip()
    if (
        normalized in {".", ".."}
        or ".." in normalized
        or any(character in _INVALID_FILENAME_CHARACTERS for character in normalized)
        or normalized.endswith(("/", "\\"))
    ):
        raise FmeaDomainError(f"{field_name} must be a contained filename")  # noqa: TRY003

    basename = normalized.rsplit(".", 1)[0] if "." in normalized else normalized
    if basename.casefold() in _WINDOWS_RESERVED_BASENAMES:
        raise FmeaDomainError(f"{field_name} uses a Windows reserved basename")  # noqa: TRY003

    if expected_extension is not None:
        extension = expected_extension.strip().lstrip(".").casefold()
        if not extension or not normalized.casefold().endswith(f".{extension}"):
            raise FmeaDomainError(f"{field_name} extension does not match expected {extension}")  # noqa: TRY003
    return normalized


__all__ = ["validate_filename"]
