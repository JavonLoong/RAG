from __future__ import annotations

import hashlib
import re
from pathlib import Path, PurePosixPath
from typing import Any


SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


def source_path_looks_like_metadata(path_value: str | Path) -> bool:
    path_text = str(path_value).replace("\\", "/")
    return PurePosixPath(path_text).suffix.lower() == ".json"


def source_attachment_failure(path: Path) -> str | None:
    if path.stat().st_size <= 0:
        return f"source evidence file is empty: {path}"
    if source_path_looks_like_metadata(path):
        return f"source evidence file must not be a json metadata file: {path}"
    return None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_sha256_failure(path: Path, expected: Any) -> str | None:
    if not isinstance(expected, str) or not SHA256_PATTERN.fullmatch(expected):
        return f"{path}: source_sha256 must be a lowercase sha256 hex digest"
    actual = sha256_file(path)
    if actual != expected:
        return f"{path}: source_sha256 mismatch"
    return None
