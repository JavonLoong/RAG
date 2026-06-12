"""Helpers for resolving offline model directories before loading adapters."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

DEFAULT_EMBEDDING_MODEL = "BAAI/bge-m3"
DEFAULT_RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"
_COMMON_MODEL_ROOT_ENVS = ("RAG_LOCAL_MODEL_DIR", "RAG_MODELS_DIR", "RAG_MODEL_DIR")
_TRUE_VALUES = {"1", "true", "yes", "on"}


def online_model_loading_allowed() -> bool:
    """Return whether adapters may fall back to HuggingFace model ids."""
    return os.environ.get("RAG_ALLOW_ONLINE_MODELS", "").strip().lower() in _TRUE_VALUES


def is_existing_model_path(value: str | os.PathLike[str] | None) -> bool:
    if not value:
        return False
    try:
        return Path(value).expanduser().exists()
    except OSError:
        return False


def resolve_local_model_path(
    model_name: str | None,
    *,
    local_roots: Iterable[str | os.PathLike[str]] | None = None,
    env_var: str | None = None,
    default_model: str = DEFAULT_EMBEDDING_MODEL,
) -> str:
    """Resolve a HuggingFace-style model id to a local directory when present.

    The caller can still pass an absolute/relative path directly. By default,
    unresolved model ids are returned unchanged so higher layers can decide
    whether to fall back or permit online loading.
    """
    requested = str(model_name or default_model).strip() or default_model

    exact_candidates: list[Path] = []
    if env_var:
        exact_candidates.extend(_split_path_env(os.environ.get(env_var)))
    exact_candidates.append(Path(requested).expanduser())
    for candidate in exact_candidates:
        if candidate.exists():
            return str(candidate.resolve())

    roots = list(_iter_model_roots(local_roots))
    for root in roots:
        for relative in _candidate_relative_paths(requested):
            candidate = root / relative
            if candidate.exists():
                return str(candidate.resolve())

    return requested


def require_local_model_path(
    model_name: str | None,
    *,
    local_roots: Iterable[str | os.PathLike[str]] | None = None,
    env_var: str | None = None,
    default_model: str = DEFAULT_EMBEDDING_MODEL,
) -> str:
    resolved = resolve_local_model_path(
        model_name,
        local_roots=local_roots,
        env_var=env_var,
        default_model=default_model,
    )
    if is_existing_model_path(resolved) or online_model_loading_allowed():
        return resolved
    raise FileNotFoundError(
        "Local model directory was not found for "
        f"'{model_name or default_model}'. Set {env_var or 'RAG_LOCAL_MODEL_DIR'} "
        "or RAG_ALLOW_ONLINE_MODELS=1 to permit HuggingFace downloads."
    )


def _iter_model_roots(
    local_roots: Iterable[str | os.PathLike[str]] | None,
) -> Iterable[Path]:
    seen: set[Path] = set()
    for value in local_roots or ():
        root = Path(value).expanduser()
        if root not in seen:
            seen.add(root)
            yield root
    for env_name in _COMMON_MODEL_ROOT_ENVS:
        for root in _split_path_env(os.environ.get(env_name)):
            if root not in seen:
                seen.add(root)
                yield root
    repo_root = Path(__file__).resolve().parents[1]
    for root in (repo_root / "models", repo_root / "local_models"):
        if root not in seen:
            seen.add(root)
            yield root


def _split_path_env(value: str | None) -> list[Path]:
    if not value:
        return []
    return [Path(item).expanduser() for item in value.split(os.pathsep) if item.strip()]


def _candidate_relative_paths(model_name: str) -> list[Path]:
    normalized = model_name.strip().strip("/\\")
    if not normalized:
        return []
    parts = [part for part in normalized.replace("\\", "/").split("/") if part]
    leaf = parts[-1] if parts else normalized
    candidates = [
        Path(*parts),
        Path(leaf),
        Path(normalized.replace("/", "__").replace("\\", "__")),
        Path(normalized.replace("/", "--").replace("\\", "--")),
    ]
    unique: list[Path] = []
    for item in candidates:
        if item not in unique:
            unique.append(item)
    return unique
