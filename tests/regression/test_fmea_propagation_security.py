from __future__ import annotations

import json
import os
from hashlib import sha256
from pathlib import Path

import pytest

from scripts.run_fmea_propagation_acceptance import run_acceptance
from scripts.verify_fmea_propagation_acceptance import (
    AcceptanceVerificationError,
    verify_acceptance_directory,
)


def _canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _rewrite(output: Path, name: str, mutate) -> None:
    value = json.loads((output / name).read_text(encoding="utf-8"))
    mutate(value)
    (output / name).write_bytes(_canonical(value))
    if name != "acceptance-summary.json":
        summary_path = output / "acceptance-summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        summary["artifact_hashes"][name] = "sha256:" + sha256((output / name).read_bytes()).hexdigest()
        summary_path.write_bytes(_canonical(summary))


def _assert_rejected(output: Path, code: str) -> None:
    with pytest.raises(AcceptanceVerificationError) as caught:
        verify_acceptance_directory(output)
    assert caught.value.code == code


@pytest.fixture
def acceptance_pack(tmp_path: Path) -> Path:
    return run_acceptance(tmp_path / "runs").artifact_dir


def test_verifier_rejects_edge_without_independent_evidence(acceptance_pack: Path) -> None:
    def remove_second_edge_evidence(value: dict[str, object]) -> None:
        paths = value["paths"]
        assert isinstance(paths, list)
        edges = paths[0]["edges"]
        assert isinstance(edges, list) and len(edges) > 1
        edges[1]["evidence_ids"] = []

    _rewrite(acceptance_pack, "paths.json", remove_second_edge_evidence)
    _assert_rejected(acceptance_pack, "FMEA_PROPAGATION_EVIDENCE_INVALID")


@pytest.mark.parametrize(
    ("name", "mutate", "code"),
    [
        ("extra artifact", lambda output: (output / "unexpected.json").write_bytes(b"{}\n"), "FMEA_PROPAGATION_ARTIFACT_SET_INVALID"),
        ("missing artifact", lambda output: (output / "issues.json").unlink(), "FMEA_PROPAGATION_ARTIFACT_SET_INVALID"),
        (
            "noncanonical json",
            lambda output: (output / "topology.json").write_text('{"b":1,"a":2}\n', encoding="utf-8"),
            "FMEA_PROPAGATION_JSON_NOT_CANONICAL",
        ),
        (
            "duplicate id",
            lambda output: _rewrite(output, "reviewed-graph.json", lambda value: value["edges"].append(value["edges"][0].copy())),
            "FMEA_PROPAGATION_DUPLICATE_ID",
        ),
        (
            "lineage tamper",
            lambda output: _rewrite(output, "proposal.json", lambda value: value["lineage"].update({"topology_hash": "sha256:" + "0" * 64})),
            "FMEA_PROPAGATION_LINEAGE_INVALID",
        ),
        (
            "topology identity",
            lambda output: _rewrite(output, "topology.json", lambda value: value["topology_snapshot"].update({"topology_hash": "0" * 64})),
            "FMEA_PROPAGATION_TOPOLOGY_IDENTITY_INVALID",
        ),
        (
            "rule policy",
            lambda output: _rewrite(output, "topology.json", lambda value: value["rule_pack"].update({"max_automatic_depth": 3})),
            "FMEA_PROPAGATION_RULE_INVALID",
        ),
        (
            "graph identity",
            lambda output: _rewrite(output, "reviewed-graph.json", lambda value: value.update({"graph_hash": "sha256:" + "0" * 64})),
            "FMEA_PROPAGATION_GRAPH_IDENTITY_INVALID",
        ),
        (
            "broken path",
            lambda output: _rewrite(output, "paths.json", lambda value: value["paths"][0]["edges"][1].update({"source_entity_id": "fuel_nozzle"})),
            "FMEA_PROPAGATION_PATH_INVALID",
        ),
        (
            "external evidence",
            lambda output: _rewrite(output, "reviewed-graph.json", lambda value: value["edges"][0]["evidence_ids"].append("evidence-outside-pack")),
            "FMEA_PROPAGATION_EVIDENCE_INVALID",
        ),
        (
            "invented endpoint",
            lambda output: _rewrite(output, "reviewed-graph.json", lambda value: value["edges"][0].update({"target_entity_id": "invented-endpoint"})),
            "FMEA_PROPAGATION_ENDPOINT_INVALID",
        ),
        (
            "model confirmation",
            lambda output: _rewrite(output, "decisions.json", lambda value: value["decisions"][0]["actor"].update({"actor_type": "model", "action": "confirm"})),
            "FMEA_PROPAGATION_MODEL_AUTHORITY_INVALID",
        ),
        (
            "depth policy",
            lambda output: _rewrite(output, "decisions.json", lambda value: value["decisions"].append({"case_id": "long_path", "action": "confirm", "actor": {"actor_type": "human", "roles": ["propagation_reviewer"]}})),
            "FMEA_PROPAGATION_REVIEW_POLICY_INVALID",
        ),
        (
            "summary count tamper",
            lambda output: _rewrite(output, "acceptance-summary.json", lambda value: value.update({"invented_endpoint_count": 1})),
            "FMEA_PROPAGATION_SUMMARY_INVALID",
        ),
    ],
)
def test_verifier_rejects_semantic_tamper_classes(acceptance_pack: Path, name: str, mutate, code: str) -> None:
    del name
    mutate(acceptance_pack)
    _assert_rejected(acceptance_pack, code)


def test_verifier_rejects_private_markers_absolute_paths_secrets_and_raw_provider_response(acceptance_pack: Path) -> None:
    _rewrite(
        acceptance_pack,
        "audit-summary.json",
        lambda value: value.update({"note": "C:\\private\\prompt REQUEST_PRIVATE_MARKER sk-secret raw provider response"}),
    )
    _assert_rejected(acceptance_pack, "FMEA_PROPAGATION_PRIVATE_MARKER")


def test_verifier_rejects_duplicate_json_keys(acceptance_pack: Path) -> None:
    path = acceptance_pack / "topology.json"
    path.write_bytes(b'{"schema_version":"graphrag.fmea.propagation.acceptance.v1","schema_version":"tampered"}\n')
    _assert_rejected(acceptance_pack, "FMEA_PROPAGATION_JSON_DUPLICATE_KEY")


def test_verifier_rejects_symlink_artifact_directory_without_following_it(tmp_path: Path) -> None:
    target = run_acceptance(tmp_path / "target").artifact_dir
    link = tmp_path / "link"
    try:
        link.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError, PermissionError) as exc:
        pytest.skip(f"symlink creation unavailable on this platform: {exc}")

    _assert_rejected(link, "FMEA_PROPAGATION_ARTIFACT_SET_INVALID")


def test_verifier_checks_each_path_component_for_reparse_objects(tmp_path: Path) -> None:
    from scripts.verify_fmea_propagation_acceptance import _safe_artifact_directory

    regular = tmp_path / "regular" / "pack"
    regular.mkdir(parents=True)
    assert _safe_artifact_directory(regular) is True

    file_component = tmp_path / "file-component"
    file_component.write_text("not a directory", encoding="utf-8")
    assert _safe_artifact_directory(file_component / "pack") is False

    component = tmp_path / "component"
    component.mkdir()
    linked = tmp_path / "linked"
    try:
        linked.symlink_to(component, target_is_directory=True)
    except (OSError, NotImplementedError, PermissionError) as exc:
        pytest.skip(f"symlink creation unavailable on this platform: {exc}")

    assert _safe_artifact_directory(linked / "pack") is False


def test_verifier_does_not_require_or_import_retrieval_backend(acceptance_pack: Path) -> None:
    before = {name for name in os.sys.modules if name.startswith(("chromadb", "graphrag", "neo4j", "igraph"))}
    verify_acceptance_directory(acceptance_pack)
    after = {name for name in os.sys.modules if name.startswith(("chromadb", "graphrag", "neo4j", "igraph"))}
    assert after == before
