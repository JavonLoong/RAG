"""End-to-end governance lifecycle coverage through one application service."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from fmea_governance_fixtures import (
    _INPUT_PROVIDERS,
    make_governance_actor,
    make_governance_assembler,
    make_governance_inputs,
    seed_authoritative_analysis,
)

from fmea_application.governance_contracts import (
    ApprovalCommand,
    AssembleRevisionCommand,
    PublishCommand,
    RevisionAssemblyRequest,
    SubmitApprovalCommand,
)
from fmea_application.governance_service import RevisionGovernanceService
from fmea_application.revision_assembler import PublicationReadinessReport
from fmea_infrastructure.governance_repository_sqlite import SqliteGovernanceRepository


def test_governance_service_exposes_complete_lifecycle_surface() -> None:
    inputs = make_governance_inputs()
    service = RevisionGovernanceService(
        repository=object(),
        assembler=make_governance_assembler(inputs),
        readiness_policy=None,
        source=None,
    )

    expected = {
        "assemble",
        "readiness",
        "submit_for_approval",
        "approve",
        "reject",
        "withdraw_approval",
        "publish",
        "withdraw_publication",
        "supersede",
        "get_revision",
        "get_publication",
        "get_snapshot",
        "list_approval_events",
        "list_publication_events",
    }
    assert expected.issubset(set(dir(service)))
    assert make_governance_actor().workspace_id == inputs.workspace_id


def test_governance_service_commits_complete_lifecycle_to_sqlite(tmp_path: Path) -> None:
    inputs = make_governance_inputs()
    providers = _INPUT_PROVIDERS[id(inputs._source_attestation)]
    repository = SqliteGovernanceRepository(tmp_path / "fmea.sqlite3")
    repository.initialize()
    seed_authoritative_analysis(repository.database_path)
    build_runtime = __import__(
        "fmea_infrastructure.composition", fromlist=["build_workspace_governance_runtime"]
    ).build_workspace_governance_runtime
    runtime = build_runtime(providers, repository=repository)

    class _AlwaysReady:
        def evaluate(self, revision, _context):
            return PublicationReadinessReport(
                revision.revision_id,
                revision.workspace_id,
                revision.analysis_id,
                revision.revision_hash,
                revision.analysis_record_version,
                tuple(pack_id for pack_id, _ in revision.evidence_pack_hashes),
                True,
                (),
                (),
            )

    service = runtime.service
    assert isinstance(service, RevisionGovernanceService)
    service._readiness_policy = _AlwaysReady()
    reviewer = make_governance_actor(actor_id="reviewer-1", roles=frozenset({"reviewer"}))
    approver = make_governance_actor(actor_id="approver-1", roles=frozenset({"approver"}))
    publisher = make_governance_actor(actor_id="publisher-1", roles=frozenset({"publisher"}))

    assembled = service.assemble(
        AssembleRevisionCommand(RevisionAssemblyRequest("analysis-1", None, 1), "00000000-0000-4000-8000-000000000741"),
        reviewer,
    )
    revision = repository.get_revision(assembled.revision_id, reviewer.workspace_id)
    assert revision is not None
    submitted = service.submit_for_approval(
        SubmitApprovalCommand(
            revision.revision_id,
            revision.revision_hash,
            assembled.record_version,
            "00000000-0000-4000-8000-000000000742",
        ),
        reviewer,
    )
    approved = service.approve(
        ApprovalCommand(
            submitted.submission_id,
            revision.revision_id,
            revision.revision_hash,
            submitted.record_version,
            "approved",
            "00000000-0000-4000-8000-000000000743",
        ),
        approver,
    )
    published = service.publish(
        PublishCommand(
            revision.revision_id,
            revision.revision_hash,
            approved.approval_id,
            assembled.record_version,
            "00000000-0000-4000-8000-000000000744",
        ),
        publisher,
    )

    lifecycle = service.get_publication(published.publication_id, publisher)
    assert lifecycle.effective_status.value == "published"
    assert service.get_snapshot(published.publication_id, publisher).publication_id == published.publication_id


def test_two_service_instances_chain_publications_from_persisted_audit_head(tmp_path: Path) -> None:
    inputs = make_governance_inputs()
    providers = _INPUT_PROVIDERS[id(inputs._source_attestation)]
    repository = SqliteGovernanceRepository(tmp_path / "fmea.sqlite3")
    repository.initialize()
    seed_authoritative_analysis(repository.database_path)
    build_runtime = __import__(
        "fmea_infrastructure.composition", fromlist=["build_workspace_governance_runtime"]
    ).build_workspace_governance_runtime

    class _AlwaysReady:
        def evaluate(self, revision, _context):
            return PublicationReadinessReport(
                revision.revision_id,
                revision.workspace_id,
                revision.analysis_id,
                revision.revision_hash,
                revision.analysis_record_version,
                tuple(pack_id for pack_id, _ in revision.evidence_pack_hashes),
                True,
                (),
                (),
            )

    reviewer = make_governance_actor(actor_id="reviewer-1", roles=frozenset({"reviewer"}))
    approver = make_governance_actor(actor_id="approver-1", roles=frozenset({"approver"}))
    publisher = make_governance_actor(actor_id="publisher-1", roles=frozenset({"publisher"}))

    def publish_with(service, request, key_offset: int, *, existing_revision=None):
        service._readiness_policy = _AlwaysReady()
        if existing_revision is None:
            assembled = service.assemble(
                AssembleRevisionCommand(
                    request,
                    f"00000000-0000-4000-8000-{key_offset:012d}",
                ),
                reviewer,
            )
            revision = repository.get_revision(assembled.revision_id, reviewer.workspace_id)
            assert revision is not None
            revision_version = assembled.record_version
        else:
            revision = existing_revision
            revision_version = repository.get_revision_record_version(
                revision.revision_id,
                reviewer.workspace_id,
            )
            assert revision_version is not None
        submitted = service.submit_for_approval(
            SubmitApprovalCommand(
                revision.revision_id,
                revision.revision_hash,
                revision_version,
                f"00000000-0000-4000-8000-{key_offset + 1:012d}",
            ),
            reviewer,
        )
        approved = service.approve(
            ApprovalCommand(
                submitted.submission_id,
                revision.revision_id,
                revision.revision_hash,
                submitted.record_version,
                "approved",
                f"00000000-0000-4000-8000-{key_offset + 2:012d}",
            ),
            approver,
        )
        published = service.publish(
            PublishCommand(
                revision.revision_id,
                revision.revision_hash,
                approved.approval_id,
                revision_version,
                f"00000000-0000-4000-8000-{key_offset + 3:012d}",
            ),
            publisher,
        )
        return revision, published

    first_runtime = build_runtime(providers, repository=repository)
    first_revision, first = publish_with(
        first_runtime.service,
        RevisionAssemblyRequest("analysis-1", None, 1),
        800,
    )
    second_runtime = build_runtime(
        providers,
        repository=SqliteGovernanceRepository(repository.database_path),
    )
    _second_revision, second = publish_with(
        second_runtime.service,
        None,
        810,
        existing_revision=first_revision,
    )

    with sqlite3.connect(repository.database_path) as connection:
        first_head = connection.execute(
            "SELECT audit_chain_head FROM fmea_publications WHERE publication_id=?",
            (first.publication_id,),
        ).fetchone()[0]
        second_manifest = json.loads(
            connection.execute(
                "SELECT manifest_json FROM fmea_publication_manifests WHERE manifest_id=?",
                (second.manifest_id,),
            ).fetchone()[0]
        )
    assert second_manifest["previous_audit_chain_head"] == first_head
