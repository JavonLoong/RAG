"""Security regressions for canonical governance acceptance artifacts."""

from __future__ import annotations

import ast
import json
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import pytest

import scripts.run_fmea_governance_acceptance as runner
from core_domain.fmea.governance import canonical_hash, canonical_json_bytes
from scripts.run_fmea_governance_acceptance import run_acceptance
from scripts.verify_fmea_governance_acceptance import verify, verify_latest


def test_verifier_does_not_import_runner_validation_functions() -> None:
    source = Path("scripts/verify_fmea_governance_acceptance.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    imported_modules.update(node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module)
    assert not any(name and name.endswith("run_fmea_governance_acceptance") for name in imported_modules)


def test_verifier_rejects_private_markers_before_hash_replay(tmp_path: Path) -> None:
    result = run_acceptance(output_root=tmp_path / "acceptance")
    snapshot_path = result.artifact_dir / "snapshots.json"
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    payload["items"][0]["private_path"] = "C:\\Users\\private\\evidence"
    snapshot_path.write_bytes((json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"))

    assert verify(result.artifact_dir).error_code == "FMEA_PRIVATE_MARKER"


def test_component_walk_rejects_non_directory_without_symlink_privilege(tmp_path: Path) -> None:
    blocked = tmp_path / "blocked-component"
    blocked.write_text("not a directory", encoding="utf-8")

    with pytest.raises(runner.AcceptanceRunError) as error:
        runner._safe_output_root(blocked / "nested")

    assert error.value.code == "OUTPUT_ROOT_INVALID"


def test_verifier_rejects_noncanonical_json(tmp_path: Path) -> None:
    result = run_acceptance(output_root=tmp_path / "acceptance")
    summary_path = result.artifact_dir / "acceptance-summary.json"
    summary_path.write_bytes(summary_path.read_bytes().replace(b"{", b"{ ", 1))

    assert verify(result.artifact_dir).error_code == "FMEA_NON_CANONICAL_JSON"


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_bytes(canonical_json_bytes(payload) + b"\n")


def _refresh_summary(artifact_dir: Path) -> None:
    summary_path = artifact_dir / "acceptance-summary.json"
    summary = _json(summary_path)
    summary["artifact_hashes"] = {
        path.name: "sha256:" + sha256(path.read_bytes()).hexdigest()
        for path in artifact_dir.glob("*.json")
        if path.name != summary_path.name
    }
    _write_json(summary_path, summary)


def test_verifier_rejects_manifest_revision_hash_detached_from_revision(tmp_path: Path) -> None:
    result = run_acceptance(output_root=tmp_path / "acceptance")
    revisions = _json(result.artifact_dir / "revisions.json")["items"]
    manifests_path = result.artifact_dir / "manifests.json"
    manifests = _json(manifests_path)
    forged = manifests["items"][0]
    forged["revision_hash"] = "f" * 64
    manifest_body = {
        key: forged.get(key)
        for key in (
            "manifest_id",
            "revision_id",
            "revision_hash",
            "approval_id",
            "snapshot_id",
            "snapshot_hash",
            "version_manifest_hash",
            "previous_audit_chain_head",
            "export_eligible",
        )
    }
    forged["manifest_hash"] = canonical_hash(manifest_body, prefixed=True)
    publications_path = result.artifact_dir / "publications.json"
    publications = _json(publications_path)
    publications["items"][0]["revision_hash"] = forged["revision_hash"]
    _write_json(manifests_path, manifests)
    _write_json(publications_path, publications)
    _refresh_summary(result.artifact_dir)

    verification = verify(result.artifact_dir)

    assert revisions[0]["revision_hash"] != forged["revision_hash"]
    assert verification.error_code == "FMEA_MANIFEST_BINDING_INVALID"


def test_verifier_rejects_snapshot_revision_detached_from_publication(tmp_path: Path) -> None:
    result = run_acceptance(output_root=tmp_path / "acceptance")
    revisions = _json(result.artifact_dir / "revisions.json")["items"]
    snapshots_path = result.artifact_dir / "snapshots.json"
    snapshots = _json(snapshots_path)
    snapshot = snapshots["items"][0]
    snapshot["revision_id"] = revisions[1]["revision_id"]
    snapshot["revision_hash"] = revisions[1]["revision_hash"]
    snapshot["snapshot_hash"] = canonical_hash(
        {key: value for key, value in snapshot.items() if key != "snapshot_hash"},
        max_array_items=10_000,
    )
    manifests_path = result.artifact_dir / "manifests.json"
    manifests = _json(manifests_path)
    manifest = manifests["items"][0]
    manifest["snapshot_hash"] = snapshot["snapshot_hash"]
    manifest_body = {
        key: manifest.get(key)
        for key in (
            "manifest_id",
            "revision_id",
            "revision_hash",
            "approval_id",
            "snapshot_id",
            "snapshot_hash",
            "version_manifest_hash",
            "previous_audit_chain_head",
            "export_eligible",
        )
    }
    manifest["manifest_hash"] = canonical_hash(manifest_body, prefixed=True)
    publications_path = result.artifact_dir / "publications.json"
    publications = _json(publications_path)
    publications["items"][0]["snapshot_hash"] = snapshot["snapshot_hash"]
    publications["items"][0]["manifest_hash"] = manifest["manifest_hash"]
    _write_json(snapshots_path, snapshots)
    _write_json(manifests_path, manifests)
    _write_json(publications_path, publications)
    _refresh_summary(result.artifact_dir)

    verification = verify(result.artifact_dir)

    assert verification.error_code == "FMEA_SNAPSHOT_BINDING_INVALID"


def test_verifier_requires_durable_authority_evidence_and_withdrawals(tmp_path: Path) -> None:
    result = run_acceptance(output_root=tmp_path / "acceptance")
    for name in (
        "outbox.json",
        "idempotency.json",
        "approval-withdrawals.json",
        "publication-withdrawals.json",
    ):
        path = result.artifact_dir / name
        payload = _json(path)
        payload["items"] = []
        _write_json(path, payload)
    _refresh_summary(result.artifact_dir)

    verification = verify(result.artifact_dir)

    assert verification.error_code == "FMEA_AUTHORITY_EVIDENCE_INCOMPLETE"


def test_verifier_rejects_outbox_payload_detached_from_authority_event(tmp_path: Path) -> None:
    result = run_acceptance(output_root=tmp_path / "acceptance")
    outbox_path = result.artifact_dir / "outbox.json"
    outbox = _json(outbox_path)
    publication_event = next(item for item in outbox["items"] if item["event_type"] == "publication.published")
    publication_event["payload"]["publication"]["revision_hash"] = "f" * 64
    publication_event["payload_hash"] = canonical_hash(publication_event["payload"], prefixed=True)
    _write_json(outbox_path, outbox)
    _refresh_summary(result.artifact_dir)

    verification = verify(result.artifact_dir)

    assert verification.error_code == "FMEA_OUTBOX_BINDING_INVALID"


def test_verifier_rejects_idempotency_response_detached_from_audit_event(tmp_path: Path) -> None:
    result = run_acceptance(output_root=tmp_path / "acceptance")
    audits = _json(result.artifact_dir / "audits.json")["items"]
    idempotency_path = result.artifact_dir / "idempotency.json"
    idempotency = _json(idempotency_path)
    idempotency["items"][0]["response"]["audit_event_id"] = audits[1]["event_id"]
    _write_json(idempotency_path, idempotency)
    _refresh_summary(result.artifact_dir)

    verification = verify(result.artifact_dir)

    assert verification.error_code == "FMEA_IDEMPOTENCY_BINDING_INVALID"


def test_verifier_derives_summary_identity_claims_from_authority_artifacts(tmp_path: Path) -> None:
    result = run_acceptance(output_root=tmp_path / "acceptance")
    summary_path = result.artifact_dir / "acceptance-summary.json"
    summary = _json(summary_path)
    summary["parent_revision_id"] = "revision-forged"
    _write_json(summary_path, summary)

    verification = verify(result.artifact_dir)

    assert verification.error_code == "FMEA_SUMMARY_MISMATCH"


def test_verifier_rejects_audit_aggregate_detached_from_authority_event(tmp_path: Path) -> None:
    result = run_acceptance(output_root=tmp_path / "acceptance")
    audits_path = result.artifact_dir / "audits.json"
    audits = _json(audits_path)
    audits["items"][0]["resource_id"] = "revision-ef676789612b693ee9736cd6e4b4214d"
    _write_json(audits_path, audits)
    _refresh_summary(result.artifact_dir)

    verification = verify(result.artifact_dir)

    assert verification.error_code == "FMEA_AUDIT_BINDING_INVALID"


def _rebind_snapshot_probe(result: object, value: str) -> None:
    artifact_dir = result.artifact_dir

    def manifest_hash(manifest: dict[str, object]) -> str:
        return canonical_hash(
            {
                key: manifest.get(key)
                for key in (
                    "manifest_id",
                    "revision_id",
                    "revision_hash",
                    "approval_id",
                    "snapshot_id",
                    "snapshot_hash",
                    "version_manifest_hash",
                    "previous_audit_chain_head",
                    "export_eligible",
                )
            },
            prefixed=True,
        )

    def audit_chain_head(
        publication: dict[str, object],
        manifest: dict[str, object],
        snapshot: dict[str, object],
        revision: dict[str, object],
        approval: dict[str, object],
    ) -> str:
        return canonical_hash(
            {
                "previous_audit_chain_head": manifest.get("previous_audit_chain_head"),
                "revision_hash": revision.get("revision_hash"),
                "approval_hash": canonical_hash(approval, prefixed=True),
                "snapshot_hash": snapshot.get("snapshot_hash"),
                "manifest_hash": manifest.get("manifest_hash"),
            },
            prefixed=True,
        )

    def rebind_event(
        command: str,
        payload: dict[str, object],
        *,
        audit_items: list[dict[str, object]],
        outbox_items: list[dict[str, object]],
        idempotency_items: list[dict[str, object]],
    ) -> None:
        event_type = {
            "fmea.publication.publish": "publication.published",
            "fmea.publication.supersede": "publication.superseded",
            "fmea.publication.withdraw": "publication.withdrawn",
        }[command]
        outbox = next(item for item in outbox_items if item["event_type"] == event_type and item["payload"] is payload)
        outbox["payload_hash"] = canonical_hash(outbox["payload"], prefixed=True)
        audit = next(item for item in audit_items if item["idempotency_scope"] == outbox["idempotency_scope"])
        payload_hash = outbox["payload_hash"]
        audit["canonical_payload_hash"] = payload_hash
        event = audit["event"]
        event["canonical_payload_hash"] = payload_hash
        event["request_hash"] = payload_hash
        event["versions"]["input_snapshot_hash"] = payload_hash.removeprefix("sha256:")
        if command == "fmea.publication.publish":
            event["after_hash"] = payload["publication"]["audit_chain_head"]
        audit["event_hash"] = canonical_hash(event, prefixed=True)
        idempotency = next(item for item in idempotency_items if item["scope_key"] == outbox["idempotency_scope"])
        idempotency["payload_hash"] = payload_hash

    snapshots_path = artifact_dir / "snapshots.json"
    snapshots = _json(snapshots_path)
    snapshot = snapshots["items"][0]
    snapshot["privacy_probe"] = value
    snapshot["snapshot_hash"] = canonical_hash(
        {key: item for key, item in snapshot.items() if key != "snapshot_hash"},
        max_array_items=10_000,
    )
    manifests_path = artifact_dir / "manifests.json"
    manifests = _json(manifests_path)
    parent_manifest = manifests["items"][0]
    parent_manifest["snapshot_hash"] = snapshot["snapshot_hash"]
    parent_manifest["manifest_hash"] = manifest_hash(parent_manifest)
    child_manifest = manifests["items"][1]
    publications_path = artifact_dir / "publications.json"
    publications = _json(publications_path)
    revisions = _json(artifact_dir / "revisions.json")["items"]
    approvals = _json(artifact_dir / "approvals.json")["items"]
    parent_revision = revisions[0]
    child_revision = revisions[1]
    parent_approval = next(item for item in approvals if item["revision_id"] == parent_revision["revision_id"])
    child_approval = next(item for item in approvals if item["revision_id"] == child_revision["revision_id"])
    parent_publication = publications["items"][0]
    child_publication = publications["items"][1]
    parent_publication["snapshot_hash"] = snapshot["snapshot_hash"]
    parent_publication["manifest_hash"] = parent_manifest["manifest_hash"]
    parent_publication["audit_chain_head"] = audit_chain_head(
        parent_publication, parent_manifest, snapshot, parent_revision, parent_approval
    )
    child_manifest["previous_audit_chain_head"] = parent_publication["audit_chain_head"]
    child_manifest["manifest_hash"] = manifest_hash(child_manifest)
    child_snapshot = snapshots["items"][1]
    child_publication["manifest_hash"] = child_manifest["manifest_hash"]
    child_publication["audit_chain_head"] = audit_chain_head(
        child_publication, child_manifest, child_snapshot, child_revision, child_approval
    )

    lifecycle_path = artifact_dir / "lifecycle.json"
    lifecycle = _json(lifecycle_path)
    for item, publication in zip(lifecycle["items"], publications["items"], strict=False):
        item["publication"] = publication

    audits_path = artifact_dir / "audits.json"
    audits = _json(audits_path)
    outbox_path = artifact_dir / "outbox.json"
    outbox = _json(outbox_path)
    idempotency_path = artifact_dir / "idempotency.json"
    idempotency = _json(idempotency_path)
    publish_payloads = [
        (parent_publication, parent_manifest, snapshot, parent_revision, parent_approval),
        (child_publication, child_manifest, child_snapshot, child_revision, child_approval),
    ]
    for publication, manifest, snapshot_item, revision, _approval in publish_payloads:
        publish_outbox = next(
            item
            for item in outbox["items"]
            if item["event_type"] == "publication.published"
            and item["payload"]["publication"]["publication_id"] == publication["publication_id"]
        )
        publish_outbox["payload"]["publication"] = publication
        publish_outbox["payload"]["manifest"] = manifest
        publish_outbox["payload"]["snapshot"] = snapshot_item
        eligibility = publish_outbox["payload"]["export_eligibility"]
        eligibility["source_hashes"] = [
            ["manifest", manifest["manifest_hash"]],
            ["revision", revision["revision_hash"]],
            ["snapshot", snapshot_item["snapshot_hash"]],
        ]
        eligibility["eligibility_hash"] = canonical_hash(
            {
                "eligibility_id": eligibility["eligibility_id"],
                "workspace_id": eligibility["workspace_id"],
                "publication_id": eligibility["publication_id"],
                "manifest_id": eligibility["manifest_id"],
                "eligible": eligibility["eligible"],
                "source_hashes": eligibility["source_hashes"],
            },
            prefixed=True,
        )
        rebind_event(
            "fmea.publication.publish",
            publish_outbox["payload"],
            audit_items=audits["items"],
            outbox_items=outbox["items"],
            idempotency_items=idempotency["items"],
        )
    supersede_outbox = next(item for item in outbox["items"] if item["event_type"] == "publication.superseded")
    supersede_outbox["payload"]["old"] = parent_publication
    supersede_outbox["payload"]["replacement"] = child_publication
    rebind_event(
        "fmea.publication.supersede",
        supersede_outbox["payload"],
        audit_items=audits["items"],
        outbox_items=outbox["items"],
        idempotency_items=idempotency["items"],
    )
    withdraw_outbox = next(item for item in outbox["items"] if item["event_type"] == "publication.withdrawn")
    withdraw_outbox["payload"]["publication"] = child_publication
    rebind_event(
        "fmea.publication.withdraw",
        withdraw_outbox["payload"],
        audit_items=audits["items"],
        outbox_items=outbox["items"],
        idempotency_items=idempotency["items"],
    )

    _write_json(snapshots_path, snapshots)
    _write_json(manifests_path, manifests)
    _write_json(publications_path, publications)
    _write_json(lifecycle_path, lifecycle)
    _write_json(audits_path, audits)
    _write_json(outbox_path, outbox)
    _write_json(idempotency_path, idempotency)
    _refresh_summary(artifact_dir)


@pytest.mark.parametrize(
    "private_value",
    (
        "C:/secrets/evidence",
        "C:\\secrets\\evidence",
        "\\\\server\\share\\evidence",
        "\\private\\evidence",
        "/workspace/private",
        "../private/evidence",
    ),
)
def test_verifier_rejects_decoded_local_path_forms(tmp_path: Path, private_value: str) -> None:
    result = run_acceptance(output_root=tmp_path / "acceptance")
    _rebind_snapshot_probe(result, private_value)

    verification = verify(result.artifact_dir)

    assert verification.error_code == "FMEA_PRIVATE_MARKER"


@pytest.mark.parametrize(
    "allowed_value",
    (
        "Normal domain prose mentions C: drive notation without a path.",
        "a/b is a domain identifier, not a local path",
        "https://example.com/a/b",
    ),
)
def test_verifier_allows_domain_prose_and_https_urls(tmp_path: Path, allowed_value: str) -> None:
    result = run_acceptance(output_root=tmp_path / "acceptance")
    _rebind_snapshot_probe(result, allowed_value)

    verification = verify(result.artifact_dir)

    assert verification.passed is True


def test_verifier_rejects_reparse_point_artifact_leaf(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result = run_acceptance(output_root=tmp_path / "acceptance")
    original_lstat = Path.lstat

    def mark_reparse(path: Path) -> object:
        info = original_lstat(path)
        if path.name == "snapshots.json":
            return SimpleNamespace(st_mode=info.st_mode, st_file_attributes=0x400)
        return info

    monkeypatch.setattr(Path, "lstat", mark_reparse)

    assert verify(result.artifact_dir).error_code == "FMEA_ARTIFACT_PATH_INVALID"


def test_verifier_rejects_reparse_point_latest_leaf(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result = run_acceptance(output_root=tmp_path / "acceptance")
    original_lstat = Path.lstat

    def mark_reparse(path: Path) -> object:
        info = original_lstat(path)
        if path.name == "latest":
            return SimpleNamespace(st_mode=info.st_mode, st_file_attributes=0x400)
        return info

    monkeypatch.setattr(Path, "lstat", mark_reparse)

    assert verify_latest(result.artifact_dir.parent).error_code == "FMEA_LATEST_POINTER_INVALID"


def test_acceptance_records_independently_verified_model_and_system_denials(tmp_path: Path) -> None:
    result = run_acceptance(output_root=tmp_path / "acceptance")
    denial_path = result.artifact_dir / "authority-denials.json"

    assert denial_path.is_file()
    denials = _json(denial_path)["items"]
    assert len(denials) == 17
    assert sum(item["actor_type"] == "model" for item in denials) == 8
    assert sum(item["actor_type"] == "system" for item in denials) == 8
    assert sum(item["probe"] == "stale_approval" for item in denials) == 1
    assert all(item["before_counts"] == item["after_counts"] for item in denials)
    assert verify(result.artifact_dir).passed is True
