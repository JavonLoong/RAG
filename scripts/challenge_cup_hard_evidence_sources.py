from __future__ import annotations

from pathlib import Path, PurePosixPath


def source_path_looks_like_metadata(path_value: str | Path) -> bool:
    path_text = str(path_value).replace("\\", "/")
    return PurePosixPath(path_text).suffix.lower() == ".json"


def source_attachment_failure(path: Path) -> str | None:
    if path.stat().st_size <= 0:
        return f"source evidence file is empty: {path}"
    if source_path_looks_like_metadata(path):
        return f"source evidence file must not be a json metadata file: {path}"
    return None
