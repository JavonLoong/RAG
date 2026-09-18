"""Atomic immutable filesystem registry for compiled templates."""

from __future__ import annotations

import os
import re
import shutil
import stat
import tempfile
from hashlib import sha256
from pathlib import Path
from typing import cast

import orjson

from core_domain.structured_output import (
    CompiledTemplate,
    EvidenceBinding,
    JsonValue,
    StructuredOutputError,
    TemplateLimits,
    TemplateMetadata,
    canonical_json,
)

_ID = re.compile(r"^[a-z0-9._-]{1,128}$")
_SEMVER = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
_SUFFIXES = frozenset({".json", ".yaml", ".yml"})
_MANIFEST_KEYS = frozenset({
    "template_id",
    "version",
    "template_hash",
    "source_hash",
    "source_suffix",
    "schema_dialect",
})
_MAX_STORED_MANIFEST_BYTES = 64 * 1024
_MAX_STORED_COMPILED_BYTES = 256 * 1024


def _error(code: str, message: str) -> StructuredOutputError:
    return StructuredOutputError(code, message)


class _UnsafeStoredTemplatePath(Exception):
    pass


class _StoredTemplateReadLimit(Exception):
    pass


def _template_file_identity(info: os.stat_result) -> tuple[int, int]:
    return int(getattr(info, "st_dev", 0)), int(getattr(info, "st_ino", 0))


def _same_template_file(first: os.stat_result, second: os.stat_result) -> bool:
    first_identity = _template_file_identity(first)
    second_identity = _template_file_identity(second)
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


def _template_reparse(info: os.stat_result) -> bool:
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


def _read_verified_template_file(  # noqa: C901 - one guarded read is intentionally linear
    path: Path, max_bytes: int, root: Path
) -> bytes:
    try:
        relative = path.relative_to(root)
        current = root
        for component in relative.parts[:-1]:
            current /= component
            directory_info = current.lstat()
            if _template_reparse(directory_info) or not stat.S_ISDIR(directory_info.st_mode):
                raise _UnsafeStoredTemplatePath
        initial_info = path.lstat()
    except (FileNotFoundError, OSError, ValueError) as exc:
        raise _UnsafeStoredTemplatePath from exc
    if _template_reparse(initial_info) or not stat.S_ISREG(initial_info.st_mode):
        raise _UnsafeStoredTemplatePath
    if initial_info.st_size > max_bytes:
        raise _StoredTemplateReadLimit
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_CLOEXEC", 0)
    if os.name != "nt":
        flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(str(path), flags)
    except OSError as exc:
        raise _UnsafeStoredTemplatePath from exc
    try:
        opened_info = os.fstat(descriptor)
        current_info = path.lstat()
        if not _same_template_file(initial_info, opened_info) or not _same_template_file(initial_info, current_info):
            raise _UnsafeStoredTemplatePath
        chunks: list[bytes] = []
        total = 0
        while True:
            remaining = max_bytes + 1 - total
            if remaining <= 0:
                raise _StoredTemplateReadLimit
            chunk = os.read(descriptor, min(64 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > max_bytes:
                raise _StoredTemplateReadLimit
        final_opened_info = os.fstat(descriptor)
        final_path_info = path.lstat()
        if not _same_template_file(initial_info, final_opened_info) or not _same_template_file(
            initial_info, final_path_info
        ):
            raise _UnsafeStoredTemplatePath
        if final_opened_info.st_size != initial_info.st_size or final_opened_info.st_size != total:
            raise _UnsafeStoredTemplatePath
        return b"".join(chunks)
    finally:
        os.close(descriptor)


class FileTemplateRegistry:
    def __init__(self, root: str | Path, *, limits: TemplateLimits | None = None) -> None:
        self._root = Path(root).resolve()
        self._limits = limits or TemplateLimits()

    @property
    def root(self) -> Path:
        return self._root

    @staticmethod
    def _validate_identity(template_id: str, version: str) -> None:
        if (
            not isinstance(template_id, str)
            or _ID.fullmatch(template_id) is None
            or ".." in template_id
            or not isinstance(version, str)
            or _SEMVER.fullmatch(version) is None
        ):
            raise _error("TEMPLATE_PATH_INVALID", "Template registry identity is invalid.")

    def _safe_path(self, *parts: str) -> Path:
        target = self._root.joinpath(*parts).resolve()
        try:
            target.relative_to(self._root)
        except ValueError as exc:
            raise _error("TEMPLATE_PATH_INVALID", "Template registry path is invalid.") from exc
        return target

    def _validated_temp(self, path: Path) -> Path:
        resolved = path.resolve()
        try:
            resolved.relative_to(self._root)
        except ValueError as exc:
            raise _error("TEMPLATE_PATH_INVALID", "Temporary registry path is invalid.") from exc
        return resolved

    @staticmethod
    def _write_file(path: Path, data: bytes) -> None:
        with path.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())

    def _manifest(self, template: CompiledTemplate, source_bytes: bytes, source_suffix: str) -> dict[str, JsonValue]:
        return {
            "template_id": template.metadata.template_id,
            "version": template.metadata.version,
            "template_hash": template.template_hash,
            "source_hash": sha256(source_bytes).hexdigest(),
            "source_suffix": source_suffix,
            "schema_dialect": template.metadata.schema_dialect,
        }

    @staticmethod
    def _verify_compiled_identity(template: CompiledTemplate) -> None:
        calculated = sha256(template.canonical_json.encode("utf-8")).hexdigest()
        if calculated != template.template_hash:
            raise _error("TEMPLATE_HASH_MISMATCH", "Compiled template hash does not match its content.")
        try:
            parsed = orjson.loads(template.canonical_json)
            reconstructed = FileTemplateRegistry._reconstruct(parsed, template.canonical_json)
        except (StructuredOutputError, orjson.JSONDecodeError, TypeError, ValueError, KeyError) as exc:
            raise _error("TEMPLATE_HASH_MISMATCH", "Compiled template content is not canonical.") from exc
        if (
            reconstructed.metadata != template.metadata
            or reconstructed.output_schema != template.output_schema
            or reconstructed.evidence_bindings != template.evidence_bindings
            or reconstructed.source_mappings != template.source_mappings
        ):
            raise _error("TEMPLATE_HASH_MISMATCH", "Compiled template contract does not match its content.")

    def _read_entry_bytes(self, path: Path, *, max_bytes: int) -> bytes:
        try:
            return _read_verified_template_file(path, max_bytes, self._root)
        except _StoredTemplateReadLimit as exc:
            raise _error("TEMPLATE_LIMIT_EXCEEDED", "Stored template entry exceeds its byte limit.") from exc
        except _UnsafeStoredTemplatePath as exc:
            raise _error("TEMPLATE_HASH_MISMATCH", "Stored template entry integrity check failed.") from exc

    def register(  # noqa: C901 - atomic write and race handling stay in one transaction
        self,
        template: CompiledTemplate,
        source_bytes: bytes,
        source_suffix: str,
    ) -> CompiledTemplate:
        template_id = template.metadata.template_id
        version = template.metadata.version
        self._validate_identity(template_id, version)
        if source_suffix not in _SUFFIXES:
            raise _error("TEMPLATE_PATH_INVALID", "Template source suffix is invalid.")
        if len(source_bytes) > self._limits.max_source_bytes:
            raise _error("TEMPLATE_LIMIT_EXCEEDED", "Template source exceeds the configured byte limit.")
        self._verify_compiled_identity(template)

        identity_dir = self._safe_path(template_id)
        final_dir = self._safe_path(template_id, version)
        if final_dir.exists():
            existing = self.get(template_id, version)
            if existing.template_hash == template.template_hash:
                return existing
            raise _error(
                "TEMPLATE_VERSION_CONFLICT",
                "Template version already has different content.",
            )

        try:
            self._root.mkdir(parents=True, exist_ok=True)
            identity_dir.mkdir(parents=True, exist_ok=True)
            temp_dir = self._validated_temp(Path(tempfile.mkdtemp(prefix=f".{version}.tmp-", dir=identity_dir)))
        except OSError as exc:
            raise _error("TEMPLATE_REGISTRY_ERROR", "Template registry setup failed.") from exc
        try:
            self._write_file(temp_dir / f"source{source_suffix}", source_bytes)
            self._write_file(temp_dir / "compiled.json", template.canonical_json.encode("utf-8"))
            manifest_bytes = canonical_json(self._manifest(template, source_bytes, source_suffix)).encode("utf-8")
            self._write_file(temp_dir / "manifest.json", manifest_bytes)
            temp_dir.rename(final_dir)
        except FileExistsError:
            existing = self.get(template_id, version)
            if existing.template_hash == template.template_hash:
                return existing
            raise _error(
                "TEMPLATE_VERSION_CONFLICT",
                "Template version already has different content.",
            ) from None
        except StructuredOutputError:
            raise
        except OSError as exc:
            raise _error("TEMPLATE_REGISTRY_ERROR", "Template registry write failed.") from exc
        finally:
            if temp_dir.exists():
                validated = self._validated_temp(temp_dir)
                shutil.rmtree(validated)
        return template

    def _verified_entry(self, template_id: str, version: str) -> tuple[CompiledTemplate, bytes]:
        self._validate_identity(template_id, version)
        version_dir = self._safe_path(template_id, version)
        if not version_dir.is_dir():
            raise _error("TEMPLATE_NOT_FOUND", "Template version was not found.")
        try:
            compiled_bytes = self._read_entry_bytes(version_dir / "compiled.json", max_bytes=_MAX_STORED_COMPILED_BYTES)
            manifest_bytes = self._read_entry_bytes(version_dir / "manifest.json", max_bytes=_MAX_STORED_MANIFEST_BYTES)
            compiled_text = compiled_bytes.decode("utf-8", errors="strict")
            compiled_object = orjson.loads(compiled_bytes)
            manifest = orjson.loads(manifest_bytes)
            template = self._reconstruct(compiled_object, compiled_text)
        except (OSError, UnicodeDecodeError, orjson.JSONDecodeError, TypeError, ValueError, KeyError) as exc:
            raise _error("TEMPLATE_HASH_MISMATCH", "Stored template integrity check failed.") from exc
        if not isinstance(manifest, dict) or set(manifest) != _MANIFEST_KEYS:
            raise _error("TEMPLATE_HASH_MISMATCH", "Stored template manifest is invalid.")
        if template.metadata.template_id != template_id or template.metadata.version != version:
            raise _error("TEMPLATE_HASH_MISMATCH", "Stored template identity does not match its directory.")
        source_suffix = cast("str", manifest["source_suffix"])
        if source_suffix not in _SUFFIXES or not (version_dir / f"source{source_suffix}").is_file():
            raise _error("TEMPLATE_HASH_MISMATCH", "Stored template source entry is invalid.")
        source_bytes = self._read_entry_bytes(
            version_dir / f"source{source_suffix}", max_bytes=self._limits.max_source_bytes
        )
        if len(source_bytes) > self._limits.max_source_bytes:
            raise _error("TEMPLATE_LIMIT_EXCEEDED", "Template source exceeds the configured byte limit.")
        expected = self._manifest(template, source_bytes, source_suffix)
        if manifest != expected:
            raise _error("TEMPLATE_HASH_MISMATCH", "Stored template manifest does not match.")
        return template, source_bytes

    def get(self, template_id: str, version: str) -> CompiledTemplate:
        return self._verified_entry(template_id, version)[0]

    def get_source_bytes(self, template_id: str, version: str) -> bytes:
        """Return the source bytes bound to a stored compiled template."""

        return self._verified_entry(template_id, version)[1]

    @staticmethod
    def _reconstruct(compiled_object: object, compiled_text: str) -> CompiledTemplate:
        base_keys = {"template", "output_schema", "evidence_bindings"}
        if not isinstance(compiled_object, dict) or frozenset(compiled_object) not in {
            frozenset(base_keys),
            frozenset(base_keys | {"source_mappings"}),
        }:
            raise _error("TEMPLATE_HASH_MISMATCH", "Stored compiled template is invalid.")
        normalized = canonical_json(compiled_object)
        if normalized != compiled_text:
            raise _error("TEMPLATE_HASH_MISMATCH", "Stored compiled template is not canonical.")
        raw_metadata = compiled_object["template"]
        raw_schema = compiled_object["output_schema"]
        raw_bindings = compiled_object["evidence_bindings"]
        raw_mappings = compiled_object.get("source_mappings", {})
        if not isinstance(raw_metadata, dict) or not isinstance(raw_schema, dict) or not isinstance(raw_bindings, list):
            raise _error("TEMPLATE_HASH_MISMATCH", "Stored compiled template shape is invalid.")
        if not isinstance(raw_mappings, dict):
            raise _error("TEMPLATE_HASH_MISMATCH", "Stored compiled template mappings are invalid.")
        metadata = TemplateMetadata(
            template_id=raw_metadata["id"],
            version=raw_metadata["version"],
            title=raw_metadata["title"],
            description=raw_metadata["description"],
            domain_tags=raw_metadata["domain_tags"],
            schema_dialect=raw_metadata["schema_dialect"],
        )
        bindings = tuple(
            EvidenceBinding(
                target=item["target"],
                requirement=item["requirement"],
                min_refs=item["min_refs"],
                max_refs=item["max_refs"],
                allowed_source_types=item["allowed_source_types"],
            )
            for item in raw_bindings
        )
        template_hash = sha256(normalized.encode("utf-8")).hexdigest()
        return CompiledTemplate(
            metadata=metadata,
            output_schema=cast("dict[str, JsonValue]", raw_schema),
            evidence_bindings=bindings,
            template_hash=template_hash,
            canonical_json=normalized,
            source_mappings=cast("dict[str, str]", raw_mappings),
        )


__all__ = ["FileTemplateRegistry"]
