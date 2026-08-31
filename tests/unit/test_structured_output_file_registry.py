from __future__ import annotations

import json
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest

from core_domain.structured_output import StructuredOutputError
from structured_output_application import TemplateCompiler
from structured_output_infrastructure import (
    Draft202012SchemaAdapter,
    FileTemplateRegistry,
    load_template_source,
)

FIXTURE = Path(__file__).parents[1] / "fixtures" / "structured_output" / "fmea.yaml"


def compiled():
    return TemplateCompiler(
        schema_validator=Draft202012SchemaAdapter(),
        source_loader=load_template_source,
    ).compile_path(FIXTURE)


def test_registry_writes_only_the_immutable_version_layout_and_round_trips(tmp_path: Path) -> None:
    template = compiled()
    registry = FileTemplateRegistry(tmp_path)

    registered = registry.register(template, FIXTURE.read_bytes(), FIXTURE.suffix)
    version_dir = tmp_path / template.metadata.template_id / template.metadata.version

    assert registered == template
    assert sorted(path.name for path in version_dir.iterdir()) == [
        "compiled.json",
        "manifest.json",
        "source.yaml",
    ]
    assert (
        FileTemplateRegistry(tmp_path).get(
            template.metadata.template_id,
            template.metadata.version,
        )
        == template
    )


def test_same_hash_registration_is_idempotent_without_mtime_changes(tmp_path: Path) -> None:
    template = compiled()
    registry = FileTemplateRegistry(tmp_path)
    registry.register(template, FIXTURE.read_bytes(), FIXTURE.suffix)
    version_dir = tmp_path / template.metadata.template_id / template.metadata.version
    before = {path.name: path.stat().st_mtime_ns for path in version_dir.iterdir()}

    returned = registry.register(template, FIXTURE.read_bytes(), FIXTURE.suffix)

    assert returned == template
    assert {path.name: path.stat().st_mtime_ns for path in version_dir.iterdir()} == before


def test_same_id_version_with_different_hash_is_rejected(tmp_path: Path) -> None:
    template = compiled()
    registry = FileTemplateRegistry(tmp_path)
    registry.register(template, FIXTURE.read_bytes(), FIXTURE.suffix)
    source = load_template_source(FIXTURE)
    source["output_schema"]["properties"]["item"]["maxLength"] = 128
    changed = TemplateCompiler(
        schema_validator=Draft202012SchemaAdapter(),
        source_loader=load_template_source,
    ).compile(source)

    with pytest.raises(StructuredOutputError) as raised:
        registry.register(changed, b"changed", ".yaml")

    assert raised.value.code == "TEMPLATE_VERSION_CONFLICT"


@pytest.mark.parametrize(("field", "value"), [("template_id", "../escape"), ("version", "1/../../x")])
def test_registry_identity_segments_cannot_escape_root(
    tmp_path: Path,
    field: str,
    value: str,
) -> None:
    template = compiled()
    metadata = replace(template.metadata, **{field: value})
    unsafe = replace(template, metadata=metadata)

    with pytest.raises(StructuredOutputError) as raised:
        FileTemplateRegistry(tmp_path).register(unsafe, b"source", ".yaml")

    assert raised.value.code == "TEMPLATE_PATH_INVALID"
    assert not (tmp_path.parent / "escape").exists()


def test_interrupted_temp_write_leaves_no_final_version_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    template = compiled()
    registry = FileTemplateRegistry(tmp_path)
    original = registry._write_file
    calls = 0

    def fail_second(path: Path, data: bytes) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError
        original(path, data)

    monkeypatch.setattr(registry, "_write_file", fail_second)

    with pytest.raises(StructuredOutputError) as raised:
        registry.register(template, FIXTURE.read_bytes(), FIXTURE.suffix)

    assert raised.value.code == "TEMPLATE_REGISTRY_ERROR"
    identity_dir = tmp_path / template.metadata.template_id
    assert not (identity_dir / template.metadata.version).exists()
    assert not tuple(identity_dir.glob(".*.tmp-*"))


@pytest.mark.parametrize("filename", ["compiled.json", "manifest.json"])
def test_compiled_or_manifest_tampering_is_detected(tmp_path: Path, filename: str) -> None:
    template = compiled()
    registry = FileTemplateRegistry(tmp_path)
    registry.register(template, FIXTURE.read_bytes(), FIXTURE.suffix)
    target = tmp_path / template.metadata.template_id / template.metadata.version / filename
    payload = json.loads(target.read_text(encoding="utf-8"))
    if filename == "compiled.json":
        payload["template"]["title"] = "tampered"
    else:
        payload["template_hash"] = "0" * 64
    target.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(StructuredOutputError) as raised:
        FileTemplateRegistry(tmp_path).get(template.metadata.template_id, template.metadata.version)

    assert raised.value.code == "TEMPLATE_HASH_MISMATCH"


def test_source_bytes_tampering_is_detected(tmp_path: Path) -> None:
    template = compiled()
    registry = FileTemplateRegistry(tmp_path)
    registry.register(template, FIXTURE.read_bytes(), FIXTURE.suffix)
    source_path = tmp_path / template.metadata.template_id / template.metadata.version / "source.yaml"
    source_path.write_bytes(b"tampered-source")

    with pytest.raises(StructuredOutputError) as raised:
        FileTemplateRegistry(tmp_path).get_source_bytes(template.metadata.template_id, template.metadata.version)

    assert raised.value.code == "TEMPLATE_HASH_MISMATCH"


def test_get_source_bytes_reads_source_once_and_returns_verified_bytes(tmp_path: Path, monkeypatch):
    template = compiled()
    registry = FileTemplateRegistry(tmp_path)
    source = FIXTURE.read_bytes()
    registry.register(template, source, FIXTURE.suffix)
    source_path = tmp_path / template.metadata.template_id / template.metadata.version / "source.yaml"
    original_read_entry = getattr(registry, "_read_entry_bytes", None)
    reads = 0

    def counting_read_bytes(path: Path, *, max_bytes: int) -> bytes:
        nonlocal reads
        if path == source_path:
            reads += 1
        if original_read_entry is not None:
            return original_read_entry(path, max_bytes=max_bytes)
        return Path.read_bytes(path)

    monkeypatch.setattr(registry, "_read_entry_bytes", counting_read_bytes, raising=False)
    assert registry.get_source_bytes(template.metadata.template_id, template.metadata.version) == source
    assert reads == 1


def test_get_source_bytes_does_not_reread_after_source_swap(tmp_path: Path, monkeypatch):
    template = compiled()
    registry = FileTemplateRegistry(tmp_path)
    source = FIXTURE.read_bytes()
    registry.register(template, source, FIXTURE.suffix)
    source_path = tmp_path / template.metadata.template_id / template.metadata.version / "source.yaml"
    original_read_entry = getattr(registry, "_read_entry_bytes", None)
    reads = 0

    def swap_after_first_read(path: Path, *, max_bytes: int) -> bytes:
        nonlocal reads
        if original_read_entry is not None:
            result = original_read_entry(path, max_bytes=max_bytes)
        else:
            result = Path.read_bytes(path)
        if path == source_path:
            reads += 1
            if reads == 1:
                path.write_bytes(b"replacement-after-verification")
        return result

    monkeypatch.setattr(registry, "_read_entry_bytes", swap_after_first_read, raising=False)
    assert registry.get_source_bytes(template.metadata.template_id, template.metadata.version) == source
    assert reads == 1


def test_noncanonical_compiled_contract_is_rejected_before_write(tmp_path: Path) -> None:
    template = compiled()
    noncanonical = f" {template.canonical_json}"
    malformed = replace(
        template,
        canonical_json=noncanonical,
        template_hash=sha256(noncanonical.encode("utf-8")).hexdigest(),
    )

    with pytest.raises(StructuredOutputError) as raised:
        FileTemplateRegistry(tmp_path).register(malformed, FIXTURE.read_bytes(), FIXTURE.suffix)

    assert raised.value.code == "TEMPLATE_HASH_MISMATCH"


def test_registry_root_that_is_a_file_returns_stable_registry_error(tmp_path: Path) -> None:
    root = tmp_path / "registry"
    root.write_text("not a directory", encoding="utf-8")

    with pytest.raises(StructuredOutputError) as raised:
        FileTemplateRegistry(root).register(compiled(), FIXTURE.read_bytes(), FIXTURE.suffix)

    assert raised.value.code == "TEMPLATE_REGISTRY_ERROR"
