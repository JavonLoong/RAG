"""Atomic immutable filesystem registry for compiled templates."""

from __future__ import annotations

import os
import re
import shutil
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
_MANIFEST_KEYS = frozenset(
    {"template_id", "version", "template_hash", "source_suffix", "schema_dialect"}
)


def _error(code: str, message: str) -> StructuredOutputError:
    return StructuredOutputError(code, message)


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

    def _manifest(self, template: CompiledTemplate, source_suffix: str) -> dict[str, JsonValue]:
        return {
            "template_id": template.metadata.template_id,
            "version": template.metadata.version,
            "template_hash": template.template_hash,
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
        ):
            raise _error("TEMPLATE_HASH_MISMATCH", "Compiled template contract does not match its content.")

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
            temp_dir = self._validated_temp(
                Path(tempfile.mkdtemp(prefix=f".{version}.tmp-", dir=identity_dir))
            )
        except OSError as exc:
            raise _error("TEMPLATE_REGISTRY_ERROR", "Template registry setup failed.") from exc
        try:
            self._write_file(temp_dir / f"source{source_suffix}", source_bytes)
            self._write_file(temp_dir / "compiled.json", template.canonical_json.encode("utf-8"))
            manifest_bytes = canonical_json(self._manifest(template, source_suffix)).encode("utf-8")
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

    def get(self, template_id: str, version: str) -> CompiledTemplate:
        self._validate_identity(template_id, version)
        version_dir = self._safe_path(template_id, version)
        if not version_dir.is_dir():
            raise _error("TEMPLATE_NOT_FOUND", "Template version was not found.")
        try:
            compiled_bytes = (version_dir / "compiled.json").read_bytes()
            manifest_bytes = (version_dir / "manifest.json").read_bytes()
            compiled_text = compiled_bytes.decode("utf-8", errors="strict")
            compiled_object = orjson.loads(compiled_bytes)
            manifest = orjson.loads(manifest_bytes)
            template = self._reconstruct(compiled_object, compiled_text)
        except (OSError, UnicodeDecodeError, orjson.JSONDecodeError, TypeError, ValueError, KeyError) as exc:
            raise _error("TEMPLATE_HASH_MISMATCH", "Stored template integrity check failed.") from exc
        if not isinstance(manifest, dict) or set(manifest) != _MANIFEST_KEYS:
            raise _error("TEMPLATE_HASH_MISMATCH", "Stored template manifest is invalid.")
        expected = self._manifest(template, cast("str", manifest.get("source_suffix")))
        if manifest != expected:
            raise _error("TEMPLATE_HASH_MISMATCH", "Stored template manifest does not match.")
        if template.metadata.template_id != template_id or template.metadata.version != version:
            raise _error("TEMPLATE_HASH_MISMATCH", "Stored template identity does not match its directory.")
        source_suffix = cast("str", manifest["source_suffix"])
        if source_suffix not in _SUFFIXES or not (version_dir / f"source{source_suffix}").is_file():
            raise _error("TEMPLATE_HASH_MISMATCH", "Stored template source entry is invalid.")
        return template

    @staticmethod
    def _reconstruct(compiled_object: object, compiled_text: str) -> CompiledTemplate:
        if not isinstance(compiled_object, dict) or set(compiled_object) != {
            "template",
            "output_schema",
            "evidence_bindings",
        }:
            raise _error("TEMPLATE_HASH_MISMATCH", "Stored compiled template is invalid.")
        normalized = canonical_json(compiled_object)
        if normalized != compiled_text:
            raise _error("TEMPLATE_HASH_MISMATCH", "Stored compiled template is not canonical.")
        raw_metadata = compiled_object["template"]
        raw_schema = compiled_object["output_schema"]
        raw_bindings = compiled_object["evidence_bindings"]
        if not isinstance(raw_metadata, dict) or not isinstance(raw_schema, dict) or not isinstance(raw_bindings, list):
            raise _error("TEMPLATE_HASH_MISMATCH", "Stored compiled template shape is invalid.")
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
        )


__all__ = ["FileTemplateRegistry"]
