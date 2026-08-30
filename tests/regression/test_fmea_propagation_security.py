from __future__ import annotations

import copy
import json
import os
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.run_fmea_propagation_acceptance import run_acceptance
from scripts.verify_fmea_propagation_acceptance import (
    AcceptanceVerificationError,
    verify_acceptance_directory,
)


def _canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _hash_json(value: object) -> str:
    return "sha256:" + sha256(_canonical(value)).hexdigest()


def _rewrite(output: Path, name: str, mutate) -> None:
    value = json.loads((output / name).read_text(encoding="utf-8"))
    mutate(value)
    (output / name).write_bytes(_canonical(value))
    if name != "acceptance-summary.json":
        summary_path = output / "acceptance-summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        summary["artifact_hashes"][name] = "sha256:" + sha256((output / name).read_bytes()).hexdigest()
        summary_path.write_bytes(_canonical(summary))


def _refresh_manifest(output: Path, names: tuple[str, ...]) -> None:
    summary_path = output / "acceptance-summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    for name in names:
        summary["artifact_hashes"][name] = "sha256:" + sha256((output / name).read_bytes()).hexdigest()
    summary_path.write_bytes(_canonical(summary))


def _rehash_audit_chain(value: dict[str, object]) -> None:
    events = value["events"]
    assert isinstance(events, list)
    previous_event_hash: str | None = None
    for event in events:
        event["previous_event_hash"] = previous_event_hash
        event["event_hash"] = _hash_json({key: item for key, item in event.items() if key != "event_hash"})
        previous_event_hash = event["event_hash"]
    value["chain_head"] = previous_event_hash


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


def test_verifier_rejects_coordinated_topology_tamper(acceptance_pack: Path) -> None:
    topology = json.loads((acceptance_pack / "topology.json").read_text(encoding="utf-8"))
    snapshot = topology["topology_snapshot"]
    snapshot["nodes"][0]["node_type"] = "tampered-pump"
    snapshot["topology_hash"] = sha256(
        json.dumps(
            {
                "id": snapshot["id"],
                "workspace_id": snapshot["workspace_id"],
                "analysis_id": snapshot["analysis_id"],
                "nodes": [
                    {"id": node["node_id"], "type": node["node_type"], "operating_modes": node["operating_modes"]}
                    for node in snapshot["nodes"]
                ],
                "interfaces": [
                    {
                        "id": interface["interface_id"],
                        "source_node_id": interface["source_node_id"],
                        "target_node_id": interface["target_node_id"],
                        "interface_variable": interface["interface_variable"],
                        "unit": interface["unit"],
                        "direction": interface["direction"],
                        "operating_modes": interface["operating_modes"],
                    }
                    for interface in snapshot["interfaces"]
                ],
                "record_version": snapshot["record_version"],
                "created_at": snapshot["created_at"],
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    (acceptance_pack / "topology.json").write_bytes(_canonical(topology))

    proposal = json.loads((acceptance_pack / "proposal.json").read_text(encoding="utf-8"))
    proposal["lineage"]["topology_hash"] = snapshot["topology_hash"]
    (acceptance_pack / "proposal.json").write_bytes(_canonical(proposal))

    graph = json.loads((acceptance_pack / "reviewed-graph.json").read_text(encoding="utf-8"))
    graph["topology_hash"] = snapshot["topology_hash"]
    graph["nodes"] = copy.deepcopy(snapshot["nodes"])
    graph["graph_hash"] = _hash_json({key: item for key, item in graph.items() if key != "graph_hash"})
    (acceptance_pack / "reviewed-graph.json").write_bytes(_canonical(graph))

    summary = json.loads((acceptance_pack / "acceptance-summary.json").read_text(encoding="utf-8"))
    summary["topology_hash"] = snapshot["topology_hash"]
    summary["graph_hash"] = graph["graph_hash"]
    (acceptance_pack / "acceptance-summary.json").write_bytes(_canonical(summary))
    _refresh_manifest(acceptance_pack, ("topology.json", "proposal.json", "reviewed-graph.json"))

    _assert_rejected(acceptance_pack, "FMEA_PROPAGATION_TOPOLOGY_IDENTITY_INVALID")


@pytest.mark.parametrize(
    ("field", "value"),
    [("profile_version", "auto"), ("model_version", "paid-live-model")],
)
def test_verifier_rejects_non_deterministic_profile_version_contract(acceptance_pack: Path, field: str, value: str) -> None:
    def mutate(topology: dict[str, object]) -> None:
        packs = topology["evidence_packs"]
        assert isinstance(packs, list)
        combined = next(pack for pack in packs if pack["pack_id"] == "pack-combined")
        combined["versions"][field] = value

    _rewrite(acceptance_pack, "topology.json", mutate)
    _assert_rejected(acceptance_pack, "FMEA_PROPAGATION_PROFILE_MATRIX_INVALID")


def test_verifier_rejects_forged_audit_event_rehashed_with_valid_event_hash(acceptance_pack: Path) -> None:
    def forge(value: dict[str, object]) -> None:
        events = value["events"]
        assert isinstance(events, list)
        event = events[1]
        event["resource_id"] = "decision-cycle"
        event["event_hash"] = _hash_json({key: item for key, item in event.items() if key != "event_hash"})

    _rewrite(acceptance_pack, "audit-summary.json", forge)
    _assert_rejected(acceptance_pack, "FMEA_PROPAGATION_AUDIT_INVALID")


@pytest.mark.parametrize(
    ("case_id", "actor_patch"),
    [
        ("forward", {"actor_id": "different-human"}),
        ("cycle", {"actor_id": "different-human"}),
        ("cycle", {"actor_type": "service"}),
    ],
)
def test_verifier_rejects_non_authoritative_decision_actor_for_all_outcomes(
    acceptance_pack: Path,
    case_id: str,
    actor_patch: dict[str, str],
) -> None:
    def tamper(value: dict[str, object]) -> None:
        decision = next(item for item in value["decisions"] if item["case_id"] == case_id)
        decision["actor"].update(actor_patch)

    _rewrite(acceptance_pack, "decisions.json", tamper)
    _assert_rejected(acceptance_pack, "FMEA_PROPAGATION_REVIEW_POLICY_INVALID")


def test_verifier_rejects_coordinated_decision_and_audit_actor_tamper(acceptance_pack: Path) -> None:
    def tamper_decision(value: dict[str, object]) -> None:
        decision = next(item for item in value["decisions"] if item["case_id"] == "forward")
        decision["actor"]["actor_id"] = "different-human"

    def tamper_audit(value: dict[str, object]) -> None:
        event = next(item for item in value["events"] if item["event_id"] == "event-review-forward")
        event["actor_id"] = "different-human"
        _rehash_audit_chain(value)

    _rewrite(acceptance_pack, "decisions.json", tamper_decision)
    _rewrite(acceptance_pack, "audit-summary.json", tamper_audit)
    _assert_rejected(acceptance_pack, "FMEA_PROPAGATION_REVIEW_POLICY_INVALID")


@pytest.mark.parametrize(
    "forbidden_path",
    [
        "/",
        "/ foo/bar",
        "/workspace/sensitive-data",
        "source /workspace/file",
        r"C:\workspace\sensitive-data",
        r"\\server\share\sensitive-data",
        "\\",
        r"\workspace",
        r"\workspace\sensitive-data",
    ],
)
def test_verifier_rejects_forbidden_absolute_path_forms(acceptance_pack: Path, forbidden_path: str) -> None:
    def forge(value: dict[str, object]) -> None:
        events = value["events"]
        assert isinstance(events, list)
        event = events[0]
        event["resource_id"] = forbidden_path
        event["event_hash"] = _hash_json({key: item for key, item in event.items() if key != "event_hash"})

    _rewrite(
        acceptance_pack,
        "audit-summary.json",
        forge,
    )
    _assert_rejected(acceptance_pack, "FMEA_PROPAGATION_PRIVATE_MARKER")


@pytest.mark.parametrize(
    "candidate",
    [
        "source=/workspace/file",
        "source:/workspace/file",
        "source->/workspace/file",
        "source|/workspace/file",
        "source+/workspace/file",
        "source-/workspace/file",
        "source=//server/share/file",
        "source=(/workspace/file)",
        r"prefix=C:\workspace\file",
        r"prefix=[C:\workspace\file]",
        r"prefix=\\server\share\file",
        r"prefix=\workspace\file",
        "https://example.com/a/b source=/workspace/file",
    ],
)
def test_verifier_rejects_punctuation_adjacent_local_paths(
    acceptance_pack: Path,
    candidate: str,
) -> None:
    _rewrite(
        acceptance_pack,
        "decisions.json",
        lambda value: value["decisions"][0].update({"reason": candidate}),
    )

    _assert_rejected(acceptance_pack, "FMEA_PROPAGATION_PRIVATE_MARKER")


@pytest.mark.parametrize(
    "candidate",
    [
        r"https://example.com/a/b;C:\workspace\file",
        "https://example.com/a/b,source=//server/share",
        "https://example.com/a/b|/workspace/file",
        r"https://example.com/a/b)/workspace/file",
        r"https://example.com/a/b]C:\workspace\file",
        r"https://user:pass@[::1]:443/a]C:\workspace\file",
        r"https://example.com/a/b}/workspace/file",
        "https://example.com/a/b\"/workspace/file",
    ],
)
def test_verifier_rejects_local_paths_after_terminated_http_url_span(
    acceptance_pack: Path,
    candidate: str,
) -> None:
    _rewrite(
        acceptance_pack,
        "decisions.json",
        lambda value: value["decisions"][0].update({"reason": candidate}),
    )

    _assert_rejected(acceptance_pack, "FMEA_PROPAGATION_PRIVATE_MARKER")


@pytest.mark.parametrize(
    "candidate",
    [
        "https:///workspace",
        r"https://\workspace",
        r"https://C:\workspace",
        "https://",
        "https://example.com/a https:///workspace",
        "identifierhttps://example.com/a",
        "identifierhttps://",
        "identifier.https://example.com/a",
        "identifier-https://example.com/a",
        "identifier+https://example.com/a",
        "HTTPS://",
        "https://:443/a",
        "https://example.com:notaport/a",
        "https://example.com:65536/a",
        "https://user:pass@[::1/a",
        "https://user:pass@[[::1]]/a",
    ],
)
def test_verifier_rejects_malformed_http_url_candidates_before_masking(
    acceptance_pack: Path,
    candidate: str,
) -> None:
    _rewrite(
        acceptance_pack,
        "decisions.json",
        lambda value: value["decisions"][0].update({"reason": candidate}),
    )

    _assert_rejected(acceptance_pack, "FMEA_PROPAGATION_PRIVATE_MARKER")


@pytest.mark.parametrize(
    "candidate",
    [
        r"https://example.com:/C:\workspace\file",
        "https://example.com:/a",
        "https://[2001:db8::1]:/a",
        "https://user:pass@[::1]:/a",
    ],
)
def test_verifier_rejects_empty_explicit_http_url_ports_before_masking(
    acceptance_pack: Path,
    candidate: str,
) -> None:
    _rewrite(
        acceptance_pack,
        "decisions.json",
        lambda value: value["decisions"][0].update({"reason": candidate}),
    )

    _assert_rejected(acceptance_pack, "FMEA_PROPAGATION_PRIVATE_MARKER")


@pytest.mark.parametrize(
    "candidate",
    [
        "HtTpS://Example.com/a?x=1#fragment",
        "https://example.com:0/a",
        "https://example.com:443/a",
        r"https://example.com/C:\workspace",
        "https://example.com/a//server/share",
        "https://example.com/a HTTPS://example.org/b?x=1#fragment",
        "https://example.com/a;HTTP://example.org/b",
        "source=https://example.com/a",
        "(https://example.com/a)",
    ],
)
def test_verifier_masks_only_valid_http_url_candidates(
    acceptance_pack: Path,
    candidate: str,
) -> None:
    _rewrite(
        acceptance_pack,
        "decisions.json",
        lambda value: value["decisions"][0].update({"reason": candidate}),
    )

    assert verify_acceptance_directory(acceptance_pack)["status"] == "passed"


@pytest.mark.parametrize(
    "candidate",
    [
        "https://[2001:db8::1]:443/a",
        "https://[::1]/a",
    ],
)
def test_verifier_preserves_bracketed_ipv6_http_url_authority_spans(
    acceptance_pack: Path,
    candidate: str,
) -> None:
    _rewrite(
        acceptance_pack,
        "decisions.json",
        lambda value: value["decisions"][0].update({"reason": candidate}),
    )

    assert verify_acceptance_directory(acceptance_pack)["status"] == "passed"


@pytest.mark.parametrize(
    "candidate",
    [
        "https://user:pass@[::1]/a",
        "https://user:pass@[::1]:443/a",
    ],
)
def test_verifier_preserves_userinfo_bracketed_ipv6_authority_spans(
    acceptance_pack: Path,
    candidate: str,
) -> None:
    _rewrite(
        acceptance_pack,
        "decisions.json",
        lambda value: value["decisions"][0].update({"reason": candidate}),
    )

    assert verify_acceptance_directory(acceptance_pack)["status"] == "passed"


@pytest.mark.parametrize(
    "candidate",
    [
        "ordinary prose sentence.\nSecond ordinary sentence.",
        r"The ratio a/b is ordinary prose; slash / delimiter and backslash \ delimiter are harmless.",
        "source = / delimiter",
        r"source = \ delimiter",
        "http://example.com/a/b",
        "https://example.com/a/b",
        "https://example.com/a//server/share",
        r"https://example.com/C:\workspace\file",
        "user.name+tag@example.com",
        "scope.identifier/path-segment",
    ],
)
def test_verifier_allows_non_path_decoded_strings(
    acceptance_pack: Path,
    candidate: str,
) -> None:
    _rewrite(
        acceptance_pack,
        "decisions.json",
        lambda value: value["decisions"][0].update({"reason": candidate}),
    )

    assert verify_acceptance_directory(acceptance_pack)["status"] == "passed"


def test_verifier_rejects_private_markers_secrets_and_raw_provider_response(acceptance_pack: Path) -> None:
    def forge(value: dict[str, object]) -> None:
        events = value["events"]
        assert isinstance(events, list)
        event = events[0]
        event["resource_id"] = "prompt REQUEST_PRIVATE_MARKER sk-secret raw provider response"
        event["event_hash"] = _hash_json({key: item for key, item in event.items() if key != "event_hash"})

    _rewrite(
        acceptance_pack,
        "audit-summary.json",
        forge,
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


def test_verifier_accepts_regular_artifact_directory_without_privilege(tmp_path: Path) -> None:
    from scripts.verify_fmea_propagation_acceptance import _safe_artifact_directory

    regular = tmp_path / "regular" / "pack"
    regular.mkdir(parents=True)
    assert _safe_artifact_directory(regular) is True


def test_verifier_rejects_file_component_without_privilege(tmp_path: Path) -> None:
    from scripts.verify_fmea_propagation_acceptance import _safe_artifact_directory

    file_component = tmp_path / "file-component"
    file_component.write_text("not a directory", encoding="utf-8")
    assert _safe_artifact_directory(file_component / "pack") is False


def test_verifier_rejects_file_attribute_reparse_component_without_privilege(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import scripts.verify_fmea_propagation_acceptance as verifier

    artifact_dir = tmp_path / "regular" / "pack"
    artifact_dir.mkdir(parents=True)
    reparse_component = artifact_dir.parent
    real_lstat = Path.lstat
    reparse_flag = 0x400

    def lstat_with_reparse(path: Path):
        info = real_lstat(path)
        if path == reparse_component:
            return SimpleNamespace(st_mode=info.st_mode, st_file_attributes=reparse_flag)
        return info

    monkeypatch.setattr(verifier.stat, "FILE_ATTRIBUTE_REPARSE_POINT", reparse_flag, raising=False)
    monkeypatch.setattr(Path, "lstat", lstat_with_reparse)

    assert verifier._safe_artifact_directory(artifact_dir) is False


def test_verifier_rejects_symlink_component_when_platform_allows_creation(tmp_path: Path) -> None:
    from scripts.verify_fmea_propagation_acceptance import _safe_artifact_directory

    component = tmp_path / "component"
    component.mkdir()
    linked = tmp_path / "linked"
    try:
        linked.symlink_to(component, target_is_directory=True)
    except (OSError, NotImplementedError, PermissionError) as exc:
        pytest.skip(f"symlink creation unavailable on this platform: {exc}")

    assert _safe_artifact_directory(linked / "pack") is False


def test_runner_never_creates_through_symlinked_output_prefix(tmp_path: Path) -> None:
    import scripts.run_fmea_propagation_acceptance as runner

    outside = tmp_path / "outside"
    outside.mkdir()
    linked = tmp_path / "linked"
    try:
        linked.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError, PermissionError) as exc:
        pytest.skip(f"symlink creation unavailable on this platform: {exc}")

    with pytest.raises(runner.AcceptanceRunError):
        runner.run_acceptance(linked / "created" / "run")

    assert not (outside / "created").exists()


def test_verifier_does_not_require_or_import_retrieval_backend(acceptance_pack: Path) -> None:
    before = {name for name in os.sys.modules if name.startswith(("chromadb", "graphrag", "neo4j", "igraph"))}
    verify_acceptance_directory(acceptance_pack)
    after = {name for name in os.sys.modules if name.startswith(("chromadb", "graphrag", "neo4j", "igraph"))}
    assert after == before
