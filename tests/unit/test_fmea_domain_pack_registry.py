from __future__ import annotations

import errno
import hashlib
import inspect
import json
from pathlib import Path

import pytest
import yaml

from core_domain.fmea.errors import FmeaDomainError
from fmea_application.ports import DomainPackRegistry, ScoringRuleRegistry
from fmea_infrastructure.domain_pack_registry import (
    FileDomainPackRegistry,
    FileScoringRuleRegistry,
    canonical_domain_pack_body,
    canonical_scoring_rule_body,
    load_domain_pack_manifest,
    load_scoring_rule_pack,
)


def _domain_body() -> dict[str, object]:
    return {
        "id": "fuel-combustion",
        "version": "1.0.0",
        "kernel_compatibility_range": ">=1.0.0,<2.0.0",
        "compatible_schema_ids": ["graphrag.fmea.v1"],
        "analysis_types": ["design_fmea", "process_fmea", "system_fmea"],
        "templates": [{"id": "fuel-combustion-fmea", "version": "1.0.0"}],
        "scoring_rules": [{"id": "fuel-sod-rpn", "version": "1.0.0"}],
        "propagation_rules": [],
        "extension_fields": [
            {"key": "fuel.heating_value", "type": "decimal"},
            {"key": "combustion.flame_stability", "type": "text"},
        ],
    }


def _domain_source(body: dict[str, object] | None = None) -> bytes:
    semantic_body = body or _domain_body()
    canonical = json.dumps(semantic_body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    payload = {"domain_pack": {**semantic_body, "content_hash": hashlib.sha256(canonical.encode("utf-8")).hexdigest()}}
    return yaml.safe_dump(payload, sort_keys=False, allow_unicode=True).encode("utf-8")


def _anchors(prefix: str) -> dict[int, str]:
    return {score: f"{prefix}-{score}" for score in range(1, 11)}


def _scoring_payload() -> dict[str, object]:
    return {
        "rule_pack": {
            "id": "fuel-sod-rpn",
            "version": "1.0.0",
            "applicable_analysis_types": ["design_fmea", "process_fmea", "system_fmea"],
            "score_range": {"min": 1, "max": 10},
            "dimensions": {
                "severity": {"anchors": _anchors("severity")},
                "occurrence": {"anchors": _anchors("occurrence")},
                "detection": {"anchors": _anchors("detection")},
            },
            "occurrence": {"window": "operating_hours", "denominator": "1000_operating_hours"},
            "detection": {"positions": ["sensor", "logic", "operator"]},
            "decision_severity": {"aggregation": "max_consequence"},
            "rpn": {"formula": "S*O*D", "version": "S*O*D-1"},
            "risk_matrix": {"version": "fuel-risk-matrix-1"},
            "priority": {"version": "fuel-priority-1", "high_rpn": 200, "critical_severity": 9, "medium_rpn": 100},
            "uncertainty": {
                "missing_score_policy": "unknown_no_zero",
                "conflict_score_policy": "block_rpn",
                "uncertainty_policy": "preserve_require_review",
            },
            "policy_basis": "project_default_non_certification",
        }
    }


def _scoring_source(payload: dict[str, object] | None = None) -> bytes:
    return yaml.safe_dump(payload or _scoring_payload(), sort_keys=False, allow_unicode=True).encode("utf-8")


def test_valid_domain_manifest_loads_and_maps_to_immutable_contract() -> None:
    manifest = load_domain_pack_manifest(_domain_source())

    assert manifest.pack_id == "fuel-combustion"
    assert manifest.version == "1.0.0"
    assert manifest.compatible_schema_ids == ("graphrag.fmea.v1",)
    assert manifest.template_identities == (("fuel-combustion-fmea", "1.0.0"),)
    assert manifest.scoring_rule_identities == (("fuel-sod-rpn", "1.0.0"),)
    assert manifest.extension_fields == (("fuel.heating_value", "decimal"), ("combustion.flame_stability", "text"))


def test_domain_manifest_loader_accepts_yaml_text_and_path(tmp_path: Path) -> None:
    source = _domain_source()
    path = tmp_path / "manifest.yaml"
    path.write_bytes(source)

    assert load_domain_pack_manifest(source.decode("utf-8")) == load_domain_pack_manifest(path)


def test_domain_content_hash_is_normalized_and_deterministic() -> None:
    first = load_domain_pack_manifest(_domain_source())
    reordered = dict(reversed(tuple(_domain_body().items())))
    second = load_domain_pack_manifest(_domain_source(reordered))

    assert canonical_domain_pack_body(first) == canonical_domain_pack_body(second)
    assert first.content_hash == second.content_hash


def test_domain_content_hash_mismatch_fails_closed() -> None:
    body = _domain_body()
    source = yaml.safe_dump(
        {"domain_pack": {**body, "content_hash": "0" * 64}},
        sort_keys=False,
        allow_unicode=True,
    ).encode("utf-8")

    with pytest.raises(FmeaDomainError, match="content_hash mismatch"):
        load_domain_pack_manifest(source)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda payload: payload["domain_pack"].update({"unexpected": True}), "unknown key"),
        (lambda payload: payload["domain_pack"].pop("version"), "missing key"),
        (lambda payload: payload["domain_pack"].update({"analysis_types": "design_fmea"}), "analysis_types"),
    ],
)
def test_domain_manifest_rejects_unknown_missing_and_wrong_typed_fields(mutation, message: str) -> None:
    payload = yaml.safe_load(_domain_source())
    mutation(payload)

    with pytest.raises(FmeaDomainError, match=message):
        load_domain_pack_manifest(yaml.safe_dump(payload, sort_keys=False))


def test_domain_manifest_rejects_invalid_encoding_and_source_size(tmp_path: Path) -> None:
    with pytest.raises(FmeaDomainError, match="UTF-8"):
        load_domain_pack_manifest(b"\xff")

    path = tmp_path / "oversized.yaml"
    path.write_bytes(b"x" * (1024 * 1024 + 1))
    with pytest.raises(FmeaDomainError, match="1 MiB"):
        load_domain_pack_manifest(path)


def test_yaml_depth_attack_below_source_limit_fails_as_stable_domain_error() -> None:
    depth = 800
    source = (
        "\n".join(
            ["domain_pack:"]
            + [f"{'  ' * (index + 1)}nested{index}:" for index in range(depth)]
            + [f"{'  ' * (depth + 1)}value"]
        )
        + "\n"
    ).encode("utf-8")
    assert len(source) < 1024 * 1024

    with pytest.raises(FmeaDomainError, match="FMEA YAML source is invalid"):
        load_domain_pack_manifest(source)


def test_path_source_rejects_oversized_file_before_unbounded_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "oversized.yaml"
    path.write_bytes(b"x" * (1024 * 1024 + 1))

    def fail_unbounded_read(self: Path) -> bytes:
        raise AssertionError

    monkeypatch.setattr(Path, "read_bytes", fail_unbounded_read)

    with pytest.raises(FmeaDomainError, match="1 MiB"):
        load_domain_pack_manifest(path)


def test_valid_scoring_rule_pack_loads_all_sod_anchors_and_policies() -> None:
    pack = load_scoring_rule_pack(_scoring_source())

    assert pack.rule_pack_id == "fuel-sod-rpn"
    assert pack.required_dimensions == ("severity", "occurrence", "detection")
    assert tuple(name for name, _ in pack.dimension_anchors) == pack.required_dimensions
    assert all(len(anchors) == 10 for _, anchors in pack.dimension_anchors)
    assert pack.severity_anchors == tuple((score, f"severity-{score}") for score in range(1, 11))
    assert pack.occurrence_window == "operating_hours"
    assert pack.occurrence_denominator == "1000_operating_hours"
    assert pack.rpn_formula == "S*O*D"
    assert pack.high_priority_rpn == 200
    assert pack.medium_priority_rpn == 100
    assert pack.missing_score_policy == "unknown_no_zero"


def test_scoring_rule_canonical_body_is_stable_for_yaml_key_order() -> None:
    first = load_scoring_rule_pack(_scoring_source())
    payload = _scoring_payload()
    rule_pack = payload["rule_pack"]
    assert isinstance(rule_pack, dict)
    payload["rule_pack"] = dict(reversed(tuple(rule_pack.items())))
    second = load_scoring_rule_pack(_scoring_source(payload))

    assert canonical_scoring_rule_body(first) == canonical_scoring_rule_body(second)


@pytest.mark.parametrize(
    "path",
    [
        ("dimensions", "severity", "anchors"),
        ("dimensions", "occurrence", "anchors"),
        ("dimensions", "detection", "anchors"),
    ],
)
def test_scoring_rule_rejects_incomplete_anchors(path: tuple[str, str, str]) -> None:
    payload = _scoring_payload()
    anchors = payload["rule_pack"][path[0]][path[1]][path[2]]
    assert isinstance(anchors, dict)
    anchors.pop(10)

    with pytest.raises(FmeaDomainError, match="anchors"):
        load_scoring_rule_pack(_scoring_source(payload))


def test_scoring_rule_rejects_duplicate_yaml_anchor_keys() -> None:
    source = (
        _scoring_source()
        .decode("utf-8")
        .replace(
            "        1: severity-1\n",
            "        1: duplicate\n        1: severity-1\n",
            1,
        )
    )

    with pytest.raises(FmeaDomainError, match="duplicate YAML key"):
        load_scoring_rule_pack(source)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("policy_basis", None, "policy_basis"),
        ("rpn", {"formula": "S+O+D", "version": "S*O*D-1"}, "formula"),
        (
            "uncertainty",
            {
                "missing_score_policy": "zero",
                "conflict_score_policy": "block_rpn",
                "uncertainty_policy": "preserve_require_review",
            },
            "missing_score_policy",
        ),
    ],
)
def test_scoring_rule_rejects_missing_or_unsupported_frozen_policies(field: str, value: object, message: str) -> None:
    payload = _scoring_payload()
    if value is None:
        payload["rule_pack"].pop(field)
    else:
        payload["rule_pack"][field] = value

    with pytest.raises(FmeaDomainError, match=message):
        load_scoring_rule_pack(_scoring_source(payload))


def test_scoring_loader_rejects_unknown_root_and_nested_keys() -> None:
    payload = _scoring_payload()
    payload["rule_pack"]["dimensions"]["severity"]["extra"] = True

    with pytest.raises(FmeaDomainError, match="unknown key"):
        load_scoring_rule_pack(_scoring_source(payload))


def test_loaders_reject_yaml_aliases_and_multiple_documents() -> None:
    aliased = (
        b"domain_pack: &pack\n  id: fuel-combustion\n  version: 1.0.0\n  content_hash: '"
        + b"0" * 64
        + b"'\ncopy: *pack\n"
    )
    with pytest.raises(FmeaDomainError, match="alias"):
        load_domain_pack_manifest(aliased)

    with pytest.raises(FmeaDomainError, match="document"):
        load_domain_pack_manifest(_domain_source() + b"\n---\nnull\n")


def test_domain_registry_protocol_requires_source_bytes_signature() -> None:
    signature = inspect.signature(DomainPackRegistry.register)

    assert tuple(signature.parameters) == ("self", "manifest", "source_bytes")
    assert signature.parameters["source_bytes"].annotation == "bytes"


def test_scoring_registry_protocol_requires_source_bytes_signature() -> None:
    signature = inspect.signature(ScoringRuleRegistry.register)

    assert tuple(signature.parameters) == ("self", "rule_pack", "source_bytes")
    assert signature.parameters["source_bytes"].annotation == "bytes"


def test_domain_registry_writes_exact_immutable_layout_and_round_trips(tmp_path: Path) -> None:
    source = _domain_source()
    manifest = load_domain_pack_manifest(source)
    registry = FileDomainPackRegistry(tmp_path)

    assert registry.register(manifest, source) == manifest
    version_dir = tmp_path / manifest.pack_id / manifest.version

    assert sorted(path.name for path in version_dir.iterdir()) == [
        "body.json",
        "manifest.json",
        "source.yaml",
    ]
    assert registry.get(manifest.pack_id, manifest.version) == manifest


def test_same_domain_identity_same_body_replay_preserves_first_raw_source(tmp_path: Path) -> None:
    first_source = _domain_source()
    manifest = load_domain_pack_manifest(first_source)
    registry = FileDomainPackRegistry(tmp_path)
    registry.register(manifest, first_source)
    version_dir = tmp_path / manifest.pack_id / manifest.version
    before = {path.name: path.stat().st_mtime_ns for path in version_dir.iterdir()}

    reformatted = yaml.safe_dump(yaml.safe_load(first_source), sort_keys=True, allow_unicode=True, indent=4).encode(
        "utf-8"
    )
    assert registry.register(load_domain_pack_manifest(reformatted), reformatted) == manifest

    assert (version_dir / "source.yaml").read_bytes() == first_source
    assert {path.name: path.stat().st_mtime_ns for path in version_dir.iterdir()} == before


def test_same_domain_identity_with_different_body_is_rejected(tmp_path: Path) -> None:
    source = _domain_source()
    manifest = load_domain_pack_manifest(source)
    registry = FileDomainPackRegistry(tmp_path)
    registry.register(manifest, source)
    changed_body = _domain_body()
    changed_body["analysis_types"] = ["process_fmea"]
    changed_source = _domain_source(changed_body)

    with pytest.raises(FmeaDomainError, match="DOMAIN_PACK_IDENTITY_CONFLICT"):
        registry.register(load_domain_pack_manifest(changed_source), changed_source)


def test_scoring_registry_writes_exact_layout_and_round_trips(tmp_path: Path) -> None:
    source = _scoring_source()
    pack = load_scoring_rule_pack(source)
    registry = FileScoringRuleRegistry(tmp_path)

    assert registry.register(pack, source) == pack
    version_dir = tmp_path / pack.rule_pack_id / pack.version

    assert sorted(path.name for path in version_dir.iterdir()) == [
        "body.json",
        "manifest.json",
        "source.yaml",
    ]
    assert registry.get(pack.rule_pack_id, pack.version) == pack


def test_same_scoring_identity_with_different_body_is_rejected(tmp_path: Path) -> None:
    source = _scoring_source()
    pack = load_scoring_rule_pack(source)
    registry = FileScoringRuleRegistry(tmp_path)
    registry.register(pack, source)
    changed_payload = _scoring_payload()
    changed_payload["rule_pack"]["priority"]["high_rpn"] = 201
    changed_source = _scoring_source(changed_payload)

    with pytest.raises(FmeaDomainError, match="SCORING_RULE_IDENTITY_CONFLICT"):
        registry.register(load_scoring_rule_pack(changed_source), changed_source)


@pytest.mark.parametrize("registry_kind", ["domain", "scoring"])
def test_registry_manifest_binds_raw_and_canonical_hashes(tmp_path: Path, registry_kind: str) -> None:
    if registry_kind == "domain":
        source = _domain_source()
        model = load_domain_pack_manifest(source)
        registry = FileDomainPackRegistry(tmp_path)
        object_id = model.pack_id
    else:
        source = _scoring_source()
        model = load_scoring_rule_pack(source)
        registry = FileScoringRuleRegistry(tmp_path)
        object_id = model.rule_pack_id

    registry.register(model, source)
    version_dir = tmp_path / object_id / model.version
    manifest = json.loads((version_dir / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["body_hash"] == hashlib.sha256((version_dir / "body.json").read_bytes()).hexdigest()
    assert manifest["source_hash"] == hashlib.sha256(source).hexdigest()
    assert manifest["source_suffix"] == ".yaml"
    assert set(manifest) == {"kind", "id", "version", "body_hash", "source_hash", "source_suffix"}
    assert registry.get_source_bytes(object_id, model.version) == source

    (version_dir / "source.yaml").write_bytes(b"tampered-source")
    with pytest.raises(FmeaDomainError):
        registry.get_source_bytes(object_id, model.version)


def test_registry_get_does_not_auto_discover_authored_source(tmp_path: Path) -> None:
    authored = tmp_path / "authored.yaml"
    authored.write_bytes(_domain_source())

    with pytest.raises(FmeaDomainError, match="DOMAIN_PACK_NOT_FOUND"):
        FileDomainPackRegistry(tmp_path / "registry").get("fuel-combustion", "1.0.0")


@pytest.mark.parametrize("value", ["../escape", "a/b", "a\\b", "CON", "a.", "a "])
def test_domain_registry_rejects_unsafe_identity_segments(tmp_path: Path, value: str) -> None:
    registry = FileDomainPackRegistry(tmp_path)

    with pytest.raises(FmeaDomainError, match="DOMAIN_PACK_PATH_INVALID"):
        registry.get(value, "1.0.0")


def test_registry_returns_frozen_models(tmp_path: Path) -> None:
    source = _domain_source()
    manifest = load_domain_pack_manifest(source)
    returned = FileDomainPackRegistry(tmp_path).register(manifest, source)

    with pytest.raises((AttributeError, TypeError)):
        returned.pack_id = "changed"  # type: ignore[misc]


@pytest.mark.parametrize("filename", ["source.yaml", "body.json", "manifest.json"])
def test_domain_registry_rejects_single_file_tampering(tmp_path: Path, filename: str) -> None:
    source = _domain_source()
    manifest = load_domain_pack_manifest(source)
    registry = FileDomainPackRegistry(tmp_path)
    registry.register(manifest, source)
    target = tmp_path / manifest.pack_id / manifest.version / filename
    if filename == "source.yaml":
        target.write_bytes(_domain_source({**_domain_body(), "analysis_types": ["process_fmea"]}))
    elif filename == "body.json":
        target.write_bytes(b'{"tampered":true}')
    else:
        payload = json.loads(target.read_text(encoding="utf-8"))
        payload["body_hash"] = "0" * 64
        target.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(FmeaDomainError, match="DOMAIN_PACK_INTEGRITY_FAILED"):
        registry.get(manifest.pack_id, manifest.version)


def test_domain_registry_rejects_noncanonical_body_json(tmp_path: Path) -> None:
    source = _domain_source()
    manifest = load_domain_pack_manifest(source)
    registry = FileDomainPackRegistry(tmp_path)
    registry.register(manifest, source)
    target = tmp_path / manifest.pack_id / manifest.version / "body.json"
    target.write_text(json.dumps(json.loads(target.read_text(encoding="utf-8"))), encoding="utf-8")

    with pytest.raises(FmeaDomainError, match="DOMAIN_PACK_INTEGRITY_FAILED"):
        registry.get(manifest.pack_id, manifest.version)


@pytest.mark.parametrize("missing", ["source.yaml", "body.json", "manifest.json"])
def test_domain_registry_rejects_missing_final_entry(tmp_path: Path, missing: str) -> None:
    source = _domain_source()
    manifest = load_domain_pack_manifest(source)
    registry = FileDomainPackRegistry(tmp_path)
    registry.register(manifest, source)
    (tmp_path / manifest.pack_id / manifest.version / missing).unlink()

    with pytest.raises(FmeaDomainError, match="DOMAIN_PACK_INTEGRITY_FAILED"):
        registry.get(manifest.pack_id, manifest.version)


def test_domain_registry_rejects_extra_final_entry(tmp_path: Path) -> None:
    source = _domain_source()
    manifest = load_domain_pack_manifest(source)
    registry = FileDomainPackRegistry(tmp_path)
    registry.register(manifest, source)
    (tmp_path / manifest.pack_id / manifest.version / "extra").write_bytes(b"extra")

    with pytest.raises(FmeaDomainError, match="DOMAIN_PACK_INTEGRITY_FAILED"):
        registry.get(manifest.pack_id, manifest.version)


def test_register_rejects_non_bytes_source_before_io(tmp_path: Path) -> None:
    manifest = load_domain_pack_manifest(_domain_source())
    registry = FileDomainPackRegistry(tmp_path)

    with pytest.raises(FmeaDomainError, match="DOMAIN_PACK_SOURCE_INVALID"):
        registry.register(manifest, bytearray(_domain_source()))  # type: ignore[arg-type]
    assert not (tmp_path / manifest.pack_id).exists()


def test_domain_registry_rejects_oversized_source_before_io(tmp_path: Path) -> None:
    manifest = load_domain_pack_manifest(_domain_source())
    registry = FileDomainPackRegistry(tmp_path)

    with pytest.raises(FmeaDomainError, match="DOMAIN_PACK_LIMIT_EXCEEDED"):
        registry.register(manifest, b"x" * (1024 * 1024 + 1))
    assert not (tmp_path / manifest.pack_id).exists()


@pytest.mark.parametrize("filename", ["source.yaml", "body.json", "manifest.json"])
def test_registry_rejects_oversized_stored_file_before_unbounded_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, filename: str
) -> None:
    source = _domain_source()
    manifest = load_domain_pack_manifest(source)
    registry = FileDomainPackRegistry(tmp_path)
    registry.register(manifest, source)
    (tmp_path / manifest.pack_id / manifest.version / filename).write_bytes(b"x" * (1024 * 1024 + 1))

    def fail_unbounded_read(self: Path) -> bytes:
        raise AssertionError

    monkeypatch.setattr(Path, "read_bytes", fail_unbounded_read)

    with pytest.raises(FmeaDomainError, match="DOMAIN_PACK_INTEGRITY_FAILED"):
        registry.get(manifest.pack_id, manifest.version)


def test_registry_rejects_file_replaced_after_validation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = _domain_source()
    manifest = load_domain_pack_manifest(source)
    registry = FileDomainPackRegistry(tmp_path)
    registry.register(manifest, source)
    source_path = tmp_path / manifest.pack_id / manifest.version / "source.yaml"
    external = tmp_path / "outside-source.yaml"
    external.write_bytes(source)
    original_validate = registry._validate_existing_path
    injected = False

    def replace_after_validation(path: Path, *, expected_directory: bool, allow_missing: bool) -> object:
        nonlocal injected
        result = original_validate(path, expected_directory=expected_directory, allow_missing=allow_missing)
        if path == source_path and not injected:
            injected = True
            external.replace(source_path)
        return result

    monkeypatch.setattr(registry, "_validate_existing_path", replace_after_validation)

    with pytest.raises(FmeaDomainError, match="DOMAIN_PACK_(PATH_INVALID|INTEGRITY_FAILED)"):
        registry.get(manifest.pack_id, manifest.version)


def test_interrupted_registry_write_leaves_no_final_version_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _domain_source()
    manifest = load_domain_pack_manifest(source)
    registry = FileDomainPackRegistry(tmp_path)
    original = registry._write_file
    calls = 0

    def fail_second(path: Path, data: bytes) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError
        original(path, data)

    monkeypatch.setattr(registry, "_write_file", fail_second)

    with pytest.raises(FmeaDomainError, match="DOMAIN_PACK_REGISTRY_ERROR"):
        registry.register(manifest, source)
    identity_dir = tmp_path / manifest.pack_id
    assert not (identity_dir / manifest.version).exists()
    assert not tuple(identity_dir.glob(".*.tmp-*"))


def test_registry_per_file_writes_are_flushed_and_synced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = _domain_source()
    manifest = load_domain_pack_manifest(source)
    registry = FileDomainPackRegistry(tmp_path)
    written: list[str] = []
    original = registry._write_file

    def track(path: Path, data: bytes) -> None:
        written.append(path.name)
        original(path, data)

    monkeypatch.setattr(registry, "_write_file", track)
    registry.register(manifest, source)

    assert written == ["source.yaml", "body.json", "manifest.json"]


def _make_symlink_or_skip(link: Path, target: Path, *, target_is_directory: bool) -> None:
    try:
        link.symlink_to(target, target_is_directory=target_is_directory)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")


def test_registry_root_symlink_is_rejected(tmp_path: Path) -> None:
    external = tmp_path / "external"
    external.mkdir()
    root = tmp_path / "registry"
    _make_symlink_or_skip(root, external, target_is_directory=True)

    with pytest.raises(FmeaDomainError, match="DOMAIN_PACK_PATH_INVALID"):
        FileDomainPackRegistry(root).get("fuel-combustion", "1.0.0")


def test_identity_directory_symlink_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "registry"
    root.mkdir()
    external = tmp_path / "external"
    external.mkdir()
    _make_symlink_or_skip(root / "fuel-combustion", external, target_is_directory=True)

    with pytest.raises(FmeaDomainError, match="DOMAIN_PACK_PATH_INVALID"):
        FileDomainPackRegistry(root).register(load_domain_pack_manifest(_domain_source()), _domain_source())


def test_version_directory_symlink_is_rejected(tmp_path: Path) -> None:
    source = _domain_source()
    manifest = load_domain_pack_manifest(source)
    root = tmp_path / "registry"
    root.mkdir()
    identity_dir = root / manifest.pack_id
    identity_dir.mkdir()
    external = tmp_path / "external"
    external.mkdir()
    _make_symlink_or_skip(identity_dir / manifest.version, external, target_is_directory=True)

    with pytest.raises(FmeaDomainError, match="DOMAIN_PACK_PATH_INVALID"):
        FileDomainPackRegistry(root).get(manifest.pack_id, manifest.version)


@pytest.mark.parametrize("filename", ["source.yaml", "body.json", "manifest.json"])
def test_final_entry_symlink_is_rejected(tmp_path: Path, filename: str) -> None:
    source = _domain_source()
    manifest = load_domain_pack_manifest(source)
    registry = FileDomainPackRegistry(tmp_path)
    registry.register(manifest, source)
    version_dir = tmp_path / manifest.pack_id / manifest.version
    original = version_dir / filename
    external = tmp_path / f"external-{filename}"
    external.write_bytes(original.read_bytes())
    original.unlink()
    _make_symlink_or_skip(original, external, target_is_directory=False)

    with pytest.raises(FmeaDomainError, match="DOMAIN_PACK_PATH_INVALID"):
        registry.get(manifest.pack_id, manifest.version)


def test_directory_fsync_explicit_unsupported_error_is_ignored() -> None:
    assert FileDomainPackRegistry._directory_fsync_unsupported(OSError(errno.EINVAL, "unsupported"))
