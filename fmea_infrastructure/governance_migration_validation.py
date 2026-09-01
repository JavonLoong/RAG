"""Application-defined validation used by the additive governance migration."""

# The migration guard deliberately centralizes a long cross-table predicate;
# its failures are converted to a database CHECK failure by the SQL migration.
# ruff: noqa: C901, TRY003, TRY300

from __future__ import annotations

import json
import sqlite3
from hashlib import sha256
from typing import Any

from core_domain.fmea.governance import canonical_json_bytes
from fmea_application.governance_contracts import (
    PublicationResult,
    RevisionResult,
    canonical_governance_payload,
    governance_payload_hash,
)
from fmea_application.review_contracts import IdempotencyScope, encode_review_json
from fmea_application.risk_contracts import canonical_json
from fmea_infrastructure.sqlite_codec import decode_audit_event, load_strict_json


def _hash_json(payload: str) -> str:
    return "sha256:" + sha256(payload.encode("utf-8")).hexdigest()


def _canonical_contract_json(value: object) -> str:
    return canonical_json_bytes(value).decode("utf-8")


def _require_json_hash(bundle: dict[str, object], key: str, payload: object) -> None:
    if bundle[key] != _hash_json(payload):
        raise ValueError("persisted dependency JSON hash is invalid")


def _decode_snapshot(payload: object) -> object:
    from fmea_application.snapshot_contracts import NormalizedFmeaSnapshot

    data = load_strict_json(payload, "normalized snapshot")
    return NormalizedFmeaSnapshot(**data)


def _decode_authority_bundle(kind: str, bundle: dict[str, object]) -> tuple[object, dict[str, object]]:
    from fmea_infrastructure.governance_repository_sqlite import (
        _decode_approval,
        _decode_export_eligibility,
        _decode_manifest,
        _decode_publication,
        _decode_revision,
        _decode_submission,
    )

    authority_json = bundle["authority_json"]
    if kind == "revision":
        authority = _decode_revision(authority_json)
    else:
        authority = _decode_publication(authority_json)
        bundle["revision"] = _decode_revision(bundle["dependency_revision_json"])
        bundle["submission"] = _decode_submission(bundle["dependency_submission_json"])
        bundle["approval"] = _decode_approval(bundle["dependency_approval_json"])
        bundle["manifest"] = _decode_manifest(bundle["dependency_manifest_json"])
        bundle["snapshot"] = _decode_snapshot(bundle["dependency_snapshot_json"])
        bundle["eligibility"] = _decode_export_eligibility(bundle["dependency_eligibility_json"])
    if _canonical_contract_json(authority) != authority_json:
        raise ValueError("authority JSON is not canonical")
    if bundle["authority_canonical_json_hash"] != _hash_json(authority_json):
        raise ValueError("authority JSON hash is invalid")
    return authority, bundle


def _validate_revision_runtime_row(
    connection: Any, revision: object, workspace_id: object, resource_id: object
) -> None:
    row = connection.execute(
        "SELECT workspace_id,revision_id,analysis_id,analysis_record_version,parent_revision_id,parent_revision_hash,"
        "revision_hash,canonical_json_hash,record_version FROM fmea_revisions "
        "WHERE workspace_id=? AND revision_id=?",
        (workspace_id, resource_id),
    ).fetchone()
    if row is None:
        raise ValueError("persisted revision is missing")
    if (
        revision.workspace_id != workspace_id
        or revision.revision_id != resource_id
        or row["workspace_id"] != workspace_id
        or row["revision_id"] != resource_id
        or revision.analysis_id != row["analysis_id"]
        or revision.parent_revision_id != row["parent_revision_id"]
        or revision.parent_revision_hash != row["parent_revision_hash"]
        or revision.revision_hash != row["revision_hash"]
        or row["canonical_json_hash"] != _hash_json(_canonical_contract_json(revision))
        or revision.analysis_record_version != row["analysis_record_version"]
        or row["record_version"] != 1
    ):
        raise ValueError("persisted revision identity or hash is invalid")

    binding = connection.execute(
        "SELECT analysis_id,analysis_record_version,analysis_hash "
        "FROM fmea_revision_analysis_bindings WHERE workspace_id=? AND revision_id=?",
        (workspace_id, resource_id),
    ).fetchone()
    if binding is None or (
        binding["analysis_id"] != revision.analysis_id
        or binding["analysis_record_version"] != revision.analysis_record_version
        or str(binding["analysis_hash"]).removeprefix("sha256:") != revision.analysis_hash.removeprefix("sha256:")
    ):
        raise ValueError("persisted revision analysis lineage binding is invalid")


def _validate_publication_runtime_row(
    connection: Any, publication: object, workspace_id: object, resource_id: object
) -> None:
    row = connection.execute(
        "SELECT workspace_id,publication_id,analysis_id,revision_id,revision_hash,approval_id,manifest_id,"
        "manifest_hash,snapshot_id,snapshot_hash,audit_chain_head,publisher_actor_id,record_version,"
        "canonical_json_hash FROM fmea_publications WHERE workspace_id=? AND publication_id=?",
        (workspace_id, resource_id),
    ).fetchone()
    if row is None:
        raise ValueError("persisted publication is missing")
    if (
        publication.workspace_id != workspace_id
        or publication.publication_id != resource_id
        or row["workspace_id"] != workspace_id
        or row["publication_id"] != resource_id
        or publication.revision_hash != row["revision_hash"]
        or publication.manifest_hash != row["manifest_hash"]
        or publication.snapshot_hash != row["snapshot_hash"]
        or publication.analysis_id != row["analysis_id"]
        or publication.revision_id != row["revision_id"]
        or publication.approval_id != row["approval_id"]
        or publication.manifest_id != row["manifest_id"]
        or publication.snapshot_id != row["snapshot_id"]
        or publication.audit_chain_head != row["audit_chain_head"]
        or publication.publisher_actor_id != row["publisher_actor_id"]
        or publication.record_version != row["record_version"]
        or row["canonical_json_hash"] != _hash_json(_canonical_contract_json(publication))
    ):
        raise ValueError("persisted publication identity or hash is invalid")

    lineage = connection.execute(
        "SELECT manifest_id,snapshot_id,revision_id,analysis_id,revision_hash,manifest_hash,snapshot_hash "
        "FROM fmea_publication_lineage_bindings WHERE workspace_id=? AND publication_id=?",
        (workspace_id, resource_id),
    ).fetchone()
    expected = (
        publication.manifest_id,
        publication.snapshot_id,
        publication.revision_id,
        publication.analysis_id,
        publication.revision_hash,
        publication.manifest_hash,
        publication.snapshot_hash,
    )
    if lineage is None or tuple(lineage) != expected:
        raise ValueError("persisted publication manifest snapshot lineage binding is invalid")


def _validate_submission_runtime_row(connection: Any, submission: object, workspace_id: object) -> None:
    row = connection.execute(
        "SELECT workspace_id,submission_id,revision_id,revision_hash,status,submitter_actor_id,record_version,"
        "canonical_json_hash FROM fmea_approval_submissions WHERE workspace_id=? AND submission_id=?",
        (workspace_id, submission.submission_id),
    ).fetchone()
    if row is None or (
        submission.workspace_id != workspace_id
        or submission.submission_id != row["submission_id"]
        or submission.revision_id != row["revision_id"]
        or submission.revision_hash != row["revision_hash"]
        or submission.status.value != row["status"]
        or submission.submitter_actor_id != row["submitter_actor_id"]
        or submission.record_version != row["record_version"]
        or row["canonical_json_hash"] != _hash_json(_canonical_contract_json(submission))
    ):
        raise ValueError("persisted approval submission identity or hash is invalid")


def _validate_approval_runtime_row(connection: Any, approval: object, workspace_id: object) -> None:
    row = connection.execute(
        "SELECT workspace_id,approval_id,submission_id,revision_id,revision_hash,status,approver_actor_id,reason,"
        "record_version,canonical_json_hash FROM fmea_approval_decisions WHERE workspace_id=? AND approval_id=?",
        (workspace_id, approval.approval_id),
    ).fetchone()
    if row is None or (
        row["workspace_id"] != workspace_id
        or approval.approval_id != row["approval_id"]
        or approval.submission_id != row["submission_id"]
        or approval.revision_id != row["revision_id"]
        or approval.revision_hash != row["revision_hash"]
        or approval.status.value != row["status"]
        or approval.approver_actor_id != row["approver_actor_id"]
        or approval.reason != row["reason"]
        or approval.record_version != row["record_version"]
        or row["canonical_json_hash"] != _hash_json(_canonical_contract_json(approval))
    ):
        raise ValueError("persisted approval decision identity or hash is invalid")


def _validate_manifest_runtime_row(connection: Any, manifest: object, workspace_id: object) -> None:
    row = connection.execute(
        "SELECT workspace_id,manifest_id,revision_id,revision_hash,approval_id,snapshot_id,snapshot_hash,"
        "manifest_hash,canonical_json_hash FROM fmea_publication_manifests WHERE workspace_id=? AND manifest_id=?",
        (workspace_id, manifest.manifest_id),
    ).fetchone()
    if row is None or (
        row["workspace_id"] != workspace_id
        or manifest.manifest_id != row["manifest_id"]
        or manifest.revision_id != row["revision_id"]
        or manifest.revision_hash != row["revision_hash"]
        or manifest.approval_id != row["approval_id"]
        or manifest.snapshot_id != row["snapshot_id"]
        or manifest.snapshot_hash != row["snapshot_hash"]
        or manifest.manifest_hash != row["manifest_hash"]
        or row["canonical_json_hash"] != _hash_json(_canonical_contract_json(manifest))
    ):
        raise ValueError("persisted publication manifest identity or hash is invalid")


def _validate_snapshot_runtime_row(connection: Any, snapshot: object, workspace_id: object) -> None:
    row = connection.execute(
        "SELECT workspace_id,snapshot_id,publication_id,manifest_id,revision_id,revision_hash,analysis_id,"
        "snapshot_hash,canonical_json_hash FROM fmea_normalized_snapshots WHERE workspace_id=? AND snapshot_id=?",
        (workspace_id, snapshot.snapshot_id),
    ).fetchone()
    if row is None or (
        snapshot.workspace_id != workspace_id
        or snapshot.snapshot_id != row["snapshot_id"]
        or snapshot.publication_id != row["publication_id"]
        or snapshot.manifest_id != row["manifest_id"]
        or snapshot.revision_id != row["revision_id"]
        or snapshot.analysis_id != row["analysis_id"]
        or snapshot.revision_hash != row["revision_hash"]
        or snapshot.snapshot_hash != row["snapshot_hash"]
        or row["canonical_json_hash"] != _hash_json(_canonical_contract_json(snapshot))
    ):
        raise ValueError("persisted normalized snapshot identity or hash is invalid")


def _validate_eligibility_runtime_row(connection: Any, eligibility: object, workspace_id: object) -> None:
    row = connection.execute(
        "SELECT workspace_id,eligibility_id,publication_id,manifest_id,eligible,eligibility_hash,"
        "source_hashes_json,canonical_json_hash FROM fmea_export_eligibility "
        "WHERE workspace_id=? AND publication_id=?",
        (workspace_id, eligibility.publication_id),
    ).fetchone()
    if row is None or (
        eligibility.workspace_id != workspace_id
        or eligibility.publication_id != row["publication_id"]
        or eligibility.manifest_id != row["manifest_id"]
        or eligibility.eligibility_id != row["eligibility_id"]
        or eligibility.eligible is not bool(row["eligible"])
        or eligibility.eligibility_hash != row["eligibility_hash"]
        or canonical_json(dict(eligibility.source_hashes)) != row["source_hashes_json"]
        or row["canonical_json_hash"] != _hash_json(_canonical_contract_json(eligibility))
    ):
        raise ValueError("persisted export eligibility identity or hash is invalid")


def _verify_publication_dependency_authority_chains(
    connection: sqlite3.Connection,
    *,
    workspace_id: str,
    revision_id: str,
    submission_id: str,
    approval_id: str,
) -> None:
    # Late import is required: repository_sqlite imports this migration module.
    from .governance_repository_sqlite import SqliteGovernanceRepository

    for kind, resource_id in (
        ("revision", revision_id),
        ("approval_submission", submission_id),
        ("approval", approval_id),
    ):
        SqliteGovernanceRepository._verify_persisted_dependency_chain(
            connection,
            kind,
            workspace_id,
            resource_id,
        )


def _validate_event_chain(connection: Any, kind: str, authority: object, bundle: dict[str, object]) -> None:
    resource_id = bundle["resource_id"]
    authority_scope = bundle["authority_scope"]
    authority_payload_hash = bundle["authority_payload_hash"]
    if not all(isinstance(value, str) and value for value in (authority_scope, authority_payload_hash)):
        raise ValueError("authority replay metadata is missing")

    workspace_id = bundle["workspace_id"]
    if kind == "revision":
        _validate_revision_runtime_row(connection, authority, workspace_id, resource_id)
        authority_analysis_id = authority.analysis_id
        authority_resource_path = f"/fmea/analyses/{authority.analysis_id}/revisions"
    else:
        _validate_publication_runtime_row(connection, authority, workspace_id, resource_id)
        authority_analysis_id = authority.analysis_id
        authority_resource_path = f"/fmea/revisions/{authority.revision_id}/publications"

    audit_json = bundle["audit_json"]
    audit = decode_audit_event(audit_json)
    if encode_review_json(audit) != audit_json:
        raise ValueError("audit JSON is not canonical")
    expected_resource_type = "revision" if kind == "revision" else "publication"
    expected_command = "fmea.revision.assemble" if kind == "revision" else "fmea.publication.publish"
    if (
        bundle["authority_audit_event_id"] != bundle["audit_event_id"]
        or bundle["authority_outbox_event_id"] != bundle["outbox_event_id"]
        or audit.event_id != bundle["audit_event_id"]
        or audit.workspace_id != bundle["workspace_id"]
        or audit.actor_id != bundle["audit_actor_id"]
        or audit.command != expected_command
        or audit.row_id != resource_id
        or audit.analysis_id != authority_analysis_id
        or audit.canonical_payload_hash != authority_payload_hash
        or bundle["audit_resource_type"] != expected_resource_type
        or bundle["audit_resource_id"] != resource_id
        or bundle["audit_actor_id"] != audit.actor_id
        or bundle["audit_command"] != audit.command
        or bundle["audit_scope"] != authority_scope
        or bundle["audit_payload_hash"] != authority_payload_hash
    ):
        raise ValueError("audit authority binding is invalid")
    try:
        expected_scope = IdempotencyScope(
            bundle["workspace_id"],
            audit.actor_id,
            audit.command,
            authority_resource_path,
            audit.idempotency_key_hash,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("authority idempotency scope is invalid") from exc
    if audit.idempotency_key_hash != expected_scope.key_hash or authority_scope != expected_scope.scope_key:
        raise ValueError("authority idempotency scope binding is invalid")

    outbox_payload = load_strict_json(bundle["outbox_json"], "governance outbox")
    outbox_json = bundle["outbox_json"]
    if (
        canonical_json(outbox_payload) != outbox_json
        or bundle["outbox_payload_hash"] != _hash_json(outbox_json)
        or bundle["outbox_payload_hash"] != authority_payload_hash
        or bundle["outbox_event_id"] != bundle["outbox_row_event_id"]
        or bundle["outbox_workspace_id"] != bundle["workspace_id"]
        or bundle["outbox_aggregate_type"] != "fmea_governance"
        or bundle["outbox_aggregate_id"] != resource_id
        or bundle["outbox_event_type"] != ("revision.assembled" if kind == "revision" else "publication.published")
        or bundle["outbox_scope"] != authority_scope
    ):
        raise ValueError("outbox authority binding is invalid")

    response_json = bundle["idempotency_response_json"]
    response_data = load_strict_json(response_json, "governance response")
    if encode_review_json(response_data) != response_json:
        raise ValueError("idempotency response is not canonical")
    if (
        bundle["idempotency_payload_hash"] != authority_payload_hash
        or bundle["idempotency_state"] != "completed"
        or bundle["idempotency_resource_id"] != resource_id
    ):
        raise ValueError("idempotency authority binding is invalid")

    if kind == "revision":
        result = RevisionResult(**response_data)
        revision = authority
        if (
            revision.workspace_id != bundle["workspace_id"]
            or revision.revision_id != resource_id
            or revision.analysis_id != bundle["authority_analysis_id"]
            or revision.revision_hash != bundle["authority_revision_hash"]
            or revision.analysis_record_version != bundle["authority_analysis_record_version"]
            or revision.parent_revision_id != bundle["authority_parent_revision_id"]
            or revision.parent_revision_hash != bundle["authority_parent_revision_hash"]
        ):
            raise ValueError("revision authority DTO identity is invalid")
        if (
            result.replayed
            or result.revision_id != resource_id
            or result.record_version != bundle["authority_record_version"]
            or result.audit_event_id != bundle["audit_event_id"]
            or result.outbox_event_id != bundle["outbox_event_id"]
        ):
            raise ValueError("revision result binding is invalid")
        command = {
            "request": {
                "analysis_id": revision.analysis_id,
                "parent_revision_id": revision.parent_revision_id,
                "expected_analysis_version": revision.analysis_record_version,
                "parent_revision_hash": revision.parent_revision_hash,
            }
        }
        expected_payload = canonical_governance_payload("revision.assemble", command, revision=revision)
    else:
        result = PublicationResult(**response_data)
        publication = authority
        revision = bundle["revision"]
        submission = bundle["submission"]
        approval = bundle["approval"]
        manifest = bundle["manifest"]
        snapshot = bundle["snapshot"]
        eligibility = bundle["eligibility"]
        _validate_revision_runtime_row(connection, revision, bundle["workspace_id"], publication.revision_id)
        _validate_submission_runtime_row(connection, submission, bundle["workspace_id"])
        _validate_approval_runtime_row(connection, approval, bundle["workspace_id"])
        _validate_manifest_runtime_row(connection, manifest, bundle["workspace_id"])
        _validate_snapshot_runtime_row(connection, snapshot, bundle["workspace_id"])
        _validate_eligibility_runtime_row(connection, eligibility, bundle["workspace_id"])
        for json_key, hash_key in (
            ("dependency_revision_json", "dependency_revision_canonical_json_hash"),
            ("dependency_submission_json", "dependency_submission_canonical_json_hash"),
            ("dependency_approval_json", "dependency_approval_canonical_json_hash"),
            ("dependency_manifest_json", "dependency_manifest_canonical_json_hash"),
            ("dependency_snapshot_json", "dependency_snapshot_canonical_json_hash"),
            ("dependency_eligibility_json", "dependency_eligibility_canonical_json_hash"),
        ):
            _require_json_hash(bundle, hash_key, bundle[json_key])
        if (
            result.replayed
            or result.publication_id != resource_id
            or result.manifest_id != bundle["authority_manifest_id"]
            or result.snapshot_id != bundle["authority_snapshot_id"]
            or result.record_version != bundle["authority_record_version"]
            or result.audit_event_id != bundle["audit_event_id"]
            or result.outbox_event_id != bundle["outbox_event_id"]
            or publication.workspace_id != bundle["workspace_id"]
            or publication.publication_id != resource_id
            or publication.analysis_id != bundle["authority_analysis_id"]
            or publication.revision_id != bundle["authority_revision_id"]
            or publication.revision_hash != bundle["authority_revision_hash"]
            or publication.approval_id != bundle["authority_approval_id"]
            or publication.manifest_id != bundle["authority_manifest_id"]
            or publication.manifest_hash != bundle["authority_manifest_hash"]
            or publication.snapshot_id != bundle["authority_snapshot_id"]
            or publication.snapshot_hash != bundle["authority_snapshot_hash"]
            or publication.audit_chain_head != bundle["authority_audit_chain_head"]
            or publication.publisher_actor_id != bundle["authority_publisher_actor_id"]
            or bundle["dependency_revision_record_version"] != 1
            or revision.workspace_id != bundle["workspace_id"]
            or submission.submission_id != bundle["dependency_submission_id"]
            or submission.workspace_id != bundle["workspace_id"]
            or revision.revision_id != publication.revision_id
            or revision.revision_hash != publication.revision_hash
            or revision.analysis_id != bundle["authority_analysis_id"]
            or submission.revision_id != revision.revision_id
            or submission.revision_hash != revision.revision_hash
            or submission.status.value != bundle["dependency_submission_status"]
            or submission.submitter_actor_id != bundle["dependency_submission_submitter_actor_id"]
            or submission.record_version != bundle["dependency_submission_record_version"]
            or approval.approval_id != bundle["dependency_approval_id"]
            or approval.submission_id != submission.submission_id
            or approval.revision_id != revision.revision_id
            or approval.revision_hash != revision.revision_hash
            or approval.status.value != bundle["dependency_approval_status"]
            or approval.approver_actor_id != bundle["dependency_approval_approver_actor_id"]
            or approval.reason != bundle["dependency_approval_reason"]
            or approval.record_version != bundle["dependency_approval_record_version"]
            or manifest.manifest_id != bundle["dependency_manifest_id"]
            or manifest.revision_id != bundle["dependency_manifest_revision_id"]
            or manifest.revision_hash != bundle["dependency_manifest_revision_hash"]
            or manifest.approval_id != bundle["dependency_manifest_approval_id"]
            or manifest.snapshot_id != bundle["dependency_manifest_snapshot_id"]
            or manifest.snapshot_hash != bundle["dependency_manifest_snapshot_hash"]
            or manifest.manifest_hash != bundle["dependency_manifest_hash"]
            or manifest.revision_id != revision.revision_id
            or manifest.revision_hash != revision.revision_hash
            or manifest.approval_id != approval.approval_id
            or manifest.snapshot_id != snapshot.snapshot_id
            or manifest.snapshot_hash != snapshot.snapshot_hash
            or manifest.manifest_hash != bundle["dependency_manifest_hash"]
            or snapshot.snapshot_id != bundle["dependency_snapshot_id"]
            or snapshot.publication_id != bundle["dependency_snapshot_publication_id"]
            or snapshot.manifest_id != bundle["dependency_snapshot_manifest_id"]
            or snapshot.revision_id != bundle["dependency_snapshot_revision_id"]
            or snapshot.revision_hash != bundle["dependency_snapshot_revision_hash"]
            or snapshot.analysis_id != bundle["dependency_snapshot_analysis_id"]
            or snapshot.snapshot_hash != bundle["dependency_snapshot_hash"]
            or snapshot.publication_id != publication.publication_id
            or snapshot.manifest_id != manifest.manifest_id
            or snapshot.revision_id != revision.revision_id
            or snapshot.revision_hash != revision.revision_hash
            or snapshot.analysis_id != publication.analysis_id
            or snapshot.snapshot_hash != publication.snapshot_hash
            or eligibility.eligibility_id != bundle["dependency_eligibility_id"]
            or eligibility.publication_id != bundle["dependency_eligibility_publication_id"]
            or eligibility.manifest_id != bundle["dependency_eligibility_manifest_id"]
            or eligibility.publication_id != publication.publication_id
            or eligibility.manifest_id != manifest.manifest_id
            or eligibility.eligible is not manifest.export_eligible
            or eligibility.eligibility_hash != bundle["dependency_eligibility_hash"]
            or eligibility.eligible is not bool(bundle["dependency_eligibility"])
            or dict(eligibility.source_hashes).get("revision") != revision.revision_hash
            or dict(eligibility.source_hashes).get("manifest") != manifest.manifest_hash
            or dict(eligibility.source_hashes).get("snapshot") != snapshot.snapshot_hash
        ):
            raise ValueError("publication dependency binding is invalid")
        _verify_publication_dependency_authority_chains(
            connection,
            workspace_id=bundle["workspace_id"],
            revision_id=revision.revision_id,
            submission_id=submission.submission_id,
            approval_id=approval.approval_id,
        )
        command = {
            "revision_id": revision.revision_id,
            "revision_hash": revision.revision_hash,
            "approval_id": approval.approval_id,
            "expected_revision_version": bundle["dependency_revision_record_version"],
        }
        expected_payload = canonical_governance_payload(
            "publication.publish",
            command,
            revision=revision,
            approval=approval,
            submission=submission,
            manifest=manifest,
            publication=publication,
            snapshot=snapshot,
            export_eligibility=eligibility,
        )
    if (
        canonical_json(expected_payload) != outbox_json
        or governance_payload_hash(expected_payload) != authority_payload_hash
    ):
        raise ValueError(f"{kind} authority DTO and outbox payload diverge")


def _sqlite_validate_governance_replay(bundle_json: object, connection: Any) -> int:
    try:
        if not isinstance(bundle_json, str):
            return 0
        bundle = load_strict_json(bundle_json, "migration replay bundle")
        kind = bundle.get("kind")
        if kind not in {"revision", "publication"}:
            return 0
        authority, bundle = _decode_authority_bundle(kind, bundle)
        _validate_event_chain(connection, kind, authority, bundle)
        return 1
    except (AttributeError, KeyError, TypeError, ValueError, json.JSONDecodeError, sqlite3.Error):
        return 0


def register_governance_migration_functions(connection: Any) -> None:
    def validate_governance_replay(bundle_json: object) -> int:
        return _sqlite_validate_governance_replay(bundle_json, connection)

    connection.create_function("fmea_validate_governance_replay", 1, validate_governance_replay)
