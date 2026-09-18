from __future__ import annotations

import json
import sqlite3
import sys
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest

PACKAGE_SRC = Path(__file__).resolve().parents[2] / "api_server" / "current_console" / "chroma_rag_poc" / "src"
if str(PACKAGE_SRC) not in sys.path:
    sys.path.insert(0, str(PACKAGE_SRC))

from core_domain.fmea.errors import FmeaDomainError  # noqa: E402
from core_domain.fmea.states import ReviewStatus  # noqa: E402
from fmea_application.governance_service import GovernanceServiceError, RevisionGovernanceService  # noqa: E402
from fmea_application.publication_body import PublicationBody  # noqa: E402
from fmea_application.review_contracts import ReviewCandidateBundle  # noqa: E402
from fmea_application.snapshot_contracts import PUBLICATION_BODY_SCHEMA_VERSION  # noqa: E402
from fmea_infrastructure.composition import build_workspace_governance_runtime  # noqa: E402
from fmea_infrastructure.governance_repository_sqlite import SqliteGovernanceRepository  # noqa: E402
from fmea_infrastructure.repository_sqlite import SqliteFmeaRepository  # noqa: E402


def _production_pack(pack):
    ref = pack.refs[0]
    locator = json.dumps({"page": 1, "span": 1}, sort_keys=True, separators=(",", ":"))
    evidence_identity = json.dumps(
        {
            "source_type": ref.source_type,
            "document_id": ref.document_id,
            "document_version": ref.document_version,
            "locator": locator,
            "normalized_quote": ref.normalized_quote,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    from core_domain.fmea.value_objects import EvidencePack

    return EvidencePack.build(
        pack_id=pack.pack_id,
        workspace_id=pack.workspace_id,
        acl_scope=pack.acl_scope,
        versions=pack.versions,
        refs=(replace(ref, locator=locator, evidence_hash=sha256(evidence_identity.encode("utf-8")).hexdigest()),),
        created_at=pack.created_at,
        expires_at=pack.expires_at,
    )


class _PersistedInputProvider:
    def __init__(self, repository: SqliteFmeaRepository, *, row_ids: tuple[str, ...] = ("row-1",)) -> None:
        self.repository = repository
        self.row_ids = row_ids

    def list_rows(self, _analysis_id: str, _workspace_id: str):
        return tuple(
            row
            for row_id in self.row_ids
            if (row := self.repository.get_row(row_id, _workspace_id)) is not None
        )

    def list_evidence_packs(self, _analysis_id: str, _workspace_id: str):
        pack = self.repository.get_evidence_pack("pack-1", _workspace_id)
        return () if pack is None else (pack,)


class _ReportArtifacts:
    """Use actual compiled content instead of the old identity-only fixture."""

    def __init__(self, delegate):
        from structured_output_application.compiler import TemplateCompiler
        from structured_output_infrastructure import Draft202012SchemaAdapter, load_template_source

        self.delegate = delegate
        self.template = TemplateCompiler(
            schema_validator=Draft202012SchemaAdapter(), source_loader=load_template_source,
        ).compile({
            "template": {"id": "generic-template", "version": "1.0.0", "title": "报告",
                         "description": "Publication test", "domain_tags": ["fmea"],
                         "schema_dialect": "https://json-schema.org/draft/2020-12/schema"},
            "output_schema": {"type": "object", "properties": {
                "failure_mode": {"type": "string", "title": "故障模式"},
                "effects": {"type": "array", "items": {"type": "string"}},
                "causes": {"type": "array", "items": {"type": "string"}},
            }}, "evidence_bindings": [],
        })

    def get_artifacts(self, *args):
        from fmea_application.revision_assembler import ResolvedArtifactIdentity

        artifacts = self.delegate.get_artifacts(*args)
        return replace(artifacts, template_identities=(ResolvedArtifactIdentity(
            "template", "generic-template", "1.0.0", self.template.template_hash,
            sha256(self.template.canonical_json.encode("utf-8")).hexdigest(),
        ),))

    def get_report_template(self, template_id, version):
        assert (template_id, version) == ("generic-template", "1.0.0")
        return self.template.canonical_json


def _persisted_body_runtime(
    tmp_path: Path,
    fixture_pack,
    fixture_review_row,
    fixture_review_source,
    fixture_system_actor,
    fixture_human_reviewer,
    *,
    governance_repository_type=SqliteGovernanceRepository,
    publication_reviews=None,
    persist_review_decision=True,
    additional_review_rows=(),
    additional_review_sources=(),
    decision_ids=(),
):
    import fmea_governance_fixtures as governance_fixtures
    from fmea_review_fixtures import make_decision_command

    from fmea_application.review_service import ReviewService

    database_path = tmp_path / "fmea.sqlite3"
    review_database_path = database_path if persist_review_decision else tmp_path / "review-source.sqlite3"
    review_repository = SqliteFmeaRepository(review_database_path)
    review_repository.initialize()
    pack = _production_pack(fixture_pack)
    row = replace(fixture_review_row, evidence_pack_id=pack.pack_id)
    review_rows = (row, *additional_review_rows)
    review_sources = (fixture_review_source, *additional_review_sources)
    if len(review_rows) != len(review_sources):
        raise ValueError
    source_inputs = governance_fixtures.make_governance_inputs(
        rows=tuple(replace(item, review_status=ReviewStatus.ACCEPTED, record_version=2) for item in review_rows),
        evidence_packs=(pack,),
    )
    review_repository.save_review_candidate_bundle(
        ReviewCandidateBundle(
            analysis=source_inputs.analysis.analysis,
            evidence_pack=pack,
            rows=review_rows,
            source_snapshots=review_sources,
        ),
        fixture_system_actor,
    )
    ids: dict[str, int] = {}

    def id_factory(prefix: str) -> str:
        ids[prefix] = ids.get(prefix, 0) + 1
        if prefix == "decision" and ids[prefix] <= len(decision_ids):
            return decision_ids[ids[prefix] - 1]
        return f"{prefix}-publication-test-{ids[prefix]}"

    review_service = ReviewService(
        review_repository,
        clock=lambda: "2026-09-04T00:00:00Z",
        id_factory=id_factory,
    )
    for index, review_row in enumerate(review_rows, start=1):
        review_service.submit_decision(
            make_decision_command(
                row_id=review_row.row_id,
                idempotency_key=f"00000000-0000-4000-8000-0000000000{10 + index:02d}",
            ),
            fixture_human_reviewer,
        )
    accepted_row = review_repository.get_row(row.row_id, row.analysis_id.replace("analysis", "ws"))
    assert accepted_row is not None

    if not persist_review_decision:
        target_repository = SqliteFmeaRepository(database_path)
        target_repository.initialize()
        target_repository.save_review_candidate_bundle(
            ReviewCandidateBundle(
                analysis=source_inputs.analysis.analysis,
                evidence_pack=pack,
                rows=review_rows,
                source_snapshots=review_sources,
            ),
            fixture_system_actor,
        )
        accepted_json, accepted_hash = target_repository._row_json(accepted_row)
        workspace_id = accepted_row.analysis_id.replace("analysis", "ws")
        with sqlite3.connect(database_path) as connection:
            existing_timestamp = connection.execute(
                "SELECT updated_at FROM fmea_rows WHERE row_id=? AND workspace_id=?",
                (accepted_row.row_id, workspace_id),
            ).fetchone()[0]
            connection.execute(
                "UPDATE fmea_rows SET review_status=?, record_version=?, row_hash=?, row_json=?, updated_at=? "
                "WHERE row_id=? AND workspace_id=?",
                (
                    accepted_row.review_status.value,
                    accepted_row.record_version,
                    accepted_hash,
                    accepted_json,
                    existing_timestamp,
                    accepted_row.row_id,
                    workspace_id,
                ),
            )
        review_repository = target_repository

    providers = governance_fixtures._INPUT_PROVIDERS[id(source_inputs._source_attestation)]
    persisted = _PersistedInputProvider(review_repository, row_ids=tuple(item.row_id for item in review_rows))
    providers = replace(
        providers,
        artifacts=_ReportArtifacts(providers.artifacts),
        review=persisted,
        evidence=persisted,
        publication_reviews=publication_reviews,
    )
    governance_repository = governance_repository_type(review_repository.database_path)
    governance_repository.initialize()
    runtime = build_workspace_governance_runtime(providers, repository=governance_repository)
    return runtime, governance_repository, accepted_row, pack


def _prepare_real_publication(
    tmp_path: Path,
    fixture_pack,
    fixture_review_row,
    fixture_review_source,
    fixture_system_actor,
    fixture_human_reviewer,
    *,
    governance_repository_type=SqliteGovernanceRepository,
    publication_reviews=None,
    additional_review_rows=(),
    additional_review_sources=(),
    decision_ids=(),
):
    import fmea_governance_fixtures as governance_fixtures

    from fmea_application.governance_contracts import (
        ApprovalCommand,
        AssembleRevisionCommand,
        PublishCommand,
        SubmitApprovalCommand,
    )
    from fmea_application.revision_assembler import PublicationReadinessReport

    runtime, repository, accepted_row, pack = _persisted_body_runtime(
        tmp_path,
        fixture_pack,
        fixture_review_row,
        fixture_review_source,
        fixture_system_actor,
        fixture_human_reviewer,
        governance_repository_type=governance_repository_type,
        publication_reviews=publication_reviews,
        additional_review_rows=additional_review_rows,
        additional_review_sources=additional_review_sources,
        decision_ids=decision_ids,
    )

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
    assert service is not None
    service._readiness_policy = _AlwaysReady()
    assembler_actor = governance_fixtures.make_governance_actor(
        actor_id="reviewer-1", roles=frozenset({"reviewer"})
    )
    approver = governance_fixtures.make_governance_actor(actor_id="approver-1", roles=frozenset({"approver"}))
    publisher = governance_fixtures.make_governance_actor(actor_id="publisher-1", roles=frozenset({"publisher"}))
    assembled = service.assemble(
        AssembleRevisionCommand(
            governance_fixtures.make_assemble_request(),
            "00000000-0000-4000-8000-000000000901",
        ),
        assembler_actor,
    )
    revision = repository.get_revision(assembled.revision_id, publisher.workspace_id)
    assert revision is not None
    submitted = service.submit_for_approval(
        SubmitApprovalCommand(
            revision.revision_id,
            revision.revision_hash,
            assembled.record_version,
            "00000000-0000-4000-8000-000000000902",
        ),
        assembler_actor,
    )
    approved = service.approve(
        ApprovalCommand(
            submitted.submission_id,
            revision.revision_id,
            revision.revision_hash,
            submitted.record_version,
            "accepted persisted body",
            "00000000-0000-4000-8000-000000000903",
        ),
        approver,
    )
    command = PublishCommand(
        revision.revision_id,
        revision.revision_hash,
        approved.approval_id,
        assembled.record_version,
        "00000000-0000-4000-8000-000000000904",
    )
    return runtime, repository, accepted_row, pack, service, command, publisher


class _MutatingGovernanceRepository(SqliteGovernanceRepository):
    def commit_publication(self, prepared):
        source_repository = SqliteFmeaRepository(self.database_path)
        row = source_repository.get_row("row-1", prepared.revision.workspace_id)
        assert row is not None
        changed = replace(row, failure_mode="tampered after body preparation")
        row_json, row_hash = SqliteFmeaRepository._row_json(changed)
        with sqlite3.connect(self.database_path) as connection:
            original = connection.execute(
                "SELECT row_hash, row_json, updated_at FROM fmea_rows WHERE row_id=? AND workspace_id=?",
                (row.row_id, prepared.revision.workspace_id),
            ).fetchone()
            assert original is not None
            connection.execute(
                "UPDATE fmea_rows SET row_hash=?, row_json=?, updated_at=? WHERE row_id=? AND workspace_id=?",
                (row_hash, row_json, "2026-09-04T00:00:01Z", row.row_id, prepared.revision.workspace_id),
            )
        try:
            return super().commit_publication(prepared)
        except Exception:
            with sqlite3.connect(self.database_path) as connection:
                connection.execute(
                    "UPDATE fmea_rows SET row_hash=?, row_json=?, updated_at=? WHERE row_id=? AND workspace_id=?",
                    (*original, row.row_id, prepared.revision.workspace_id),
                )
            raise


class _ForgedReviewAuthorityRepository(SqliteGovernanceRepository):
    def load_publication_reviews(self, revision, *, _connection=None):
        records = super().load_publication_reviews(revision, _connection=_connection)
        return tuple(
            replace(
                record,
                authority=replace(
                    record.authority,
                    reviewer_actor_id="substituted-reviewer",
                    audit_actor_id="substituted-reviewer",
                ),
            )
            for record in records
        )


def _database_state(database_path: Path) -> dict[str, tuple[tuple[object, ...], ...]]:
    def quote(identifier: str) -> str:
        return '"' + identifier.replace('"', '""') + '"'

    with sqlite3.connect(database_path) as connection:
        tables = tuple(
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        )
        state: dict[str, tuple[tuple[object, ...], ...]] = {}
        for table in tables:
            columns = tuple(row[1] for row in connection.execute(f"PRAGMA table_info({quote(table)})"))
            column_sql = ", ".join(quote(column) for column in columns)
            rows = connection.execute(
                f"SELECT {column_sql} FROM {quote(table)} ORDER BY {column_sql}"  # noqa: S608
            ).fetchall()
            state[table] = tuple(tuple(row) for row in rows)
        return state


def _seed_persisted_legacy_publication(repository: SqliteGovernanceRepository, prepared) -> None:
    """Persist a pre-body package with the real writer for replay compatibility."""

    from test_fmea_governance_sqlite import _persist_publication_authority_chain

    _persist_publication_authority_chain(repository, prepared)
    meta = repository._meta("publication", prepared)
    connection = repository._connect()
    try:
        connection.execute("BEGIN IMMEDIATE")
        repository._insert_idempotency(connection, prepared.scope, prepared.payload_hash, prepared.audit.occurred_at_server)
        repository._insert_audit(connection, prepared.audit, prepared.scope, prepared.payload_hash, meta)
        result = repository._writer(connection, prepared, meta, repository._fail)
        repository._insert_outbox(
            connection,
            prepared.outbox,
            prepared.scope,
            meta,
            repository._lifecycle_event_type("publication", prepared),
        )
        repository._insert_event_binding(connection, meta, result)
        repository._complete_idempotency(
            connection,
            prepared.scope,
            prepared.payload_hash,
            meta.resource_id,
            result,
            prepared.audit.occurred_at_server,
        )
        connection.execute("COMMIT")
    except Exception:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()


def _forge_consistent_body(prepared, *, version_manifest=None):
    from core_domain.fmea.governance import canonical_hash
    from fmea_application.governance_contracts import (
        PreparedPublication,
        canonical_governance_payload,
        governance_payload_hash,
        publication_body_content_hash,
    )
    from fmea_application.risk_contracts import outbox_payload_hash
    from fmea_application.snapshot_contracts import NormalizedSnapshotInput, build_normalized_snapshot

    rows = tuple(
        {**dict(row), "failure_mode": "forged but internally consistent body"}
        if row["row_id"] == "row-1"
        else row
        for row in prepared.snapshot.rows
    )
    original = prepared.snapshot
    if version_manifest is not None:
        rows = original.rows
    forged_snapshot = build_normalized_snapshot(
        NormalizedSnapshotInput(
            revision=original.revision if hasattr(original, "revision") else prepared.revision,
            publication_id=original.publication_id,
            manifest_id=original.manifest_id,
            publication_revision_id=original.revision_id,
            publication_revision_hash=original.revision_hash,
            publication_workspace_id=original.workspace_id,
            publication_analysis_id=original.analysis_id,
            rows=rows,
            risk_records=original.risk_records,
            propagation=original.propagation,
            evidence_summary=original.evidence_summary,
            decision_summary=original.decision_summary,
            version_manifest=original.version_manifest if version_manifest is None else version_manifest,
            audit_summary=original.audit_summary,
            created_at=original.created_at,
        )
    )
    binding = replace(
        prepared.source_binding,
        body_hash=publication_body_content_hash(
            forged_snapshot.rows,
            forged_snapshot.risk_records,
            forged_snapshot.propagation,
            forged_snapshot.evidence_summary,
            forged_snapshot.decision_summary,
        ),
    )
    manifest_body = {
        "manifest_id": prepared.manifest.manifest_id,
        "revision_id": prepared.manifest.revision_id,
        "revision_hash": prepared.manifest.revision_hash,
        "approval_id": prepared.manifest.approval_id,
        "snapshot_id": prepared.manifest.snapshot_id,
        "snapshot_hash": forged_snapshot.snapshot_hash,
        "version_manifest_hash": prepared.manifest.version_manifest_hash,
        "previous_audit_chain_head": prepared.manifest.previous_audit_chain_head,
        "export_eligible": prepared.manifest.export_eligible,
    }
    manifest = replace(prepared.manifest, snapshot_hash=forged_snapshot.snapshot_hash, manifest_hash=canonical_hash(manifest_body, prefixed=True))
    chain_head = canonical_hash(
        {
            "previous_audit_chain_head": manifest.previous_audit_chain_head,
            "revision_hash": prepared.revision.revision_hash,
            "approval_hash": canonical_hash(prepared.approval, prefixed=True),
            "snapshot_hash": forged_snapshot.snapshot_hash,
            "manifest_hash": manifest.manifest_hash,
        },
        prefixed=True,
    )
    publication = replace(
        prepared.publication,
        manifest_hash=manifest.manifest_hash,
        snapshot_hash=forged_snapshot.snapshot_hash,
        audit_chain_head=chain_head,
    )
    eligibility_body = {
        "eligibility_id": prepared.export_eligibility.eligibility_id,
        "workspace_id": prepared.export_eligibility.workspace_id,
        "publication_id": prepared.export_eligibility.publication_id,
        "manifest_id": prepared.export_eligibility.manifest_id,
        "eligible": prepared.export_eligibility.eligible,
        "source_hashes": (
            ("manifest", manifest.manifest_hash),
            ("revision", prepared.revision.revision_hash),
            ("snapshot", forged_snapshot.snapshot_hash),
        ),
    }
    eligibility = replace(
        prepared.export_eligibility,
        source_hashes=eligibility_body["source_hashes"],
        eligibility_hash=canonical_hash(eligibility_body, prefixed=True),
    )
    payload = canonical_governance_payload(
        "publication.publish",
        prepared.command,
        revision=prepared.revision,
        approval=prepared.approval,
        submission=prepared.submission,
        manifest=manifest,
        publication=publication,
        snapshot=forged_snapshot,
        export_eligibility=eligibility,
    )
    payload_hash = governance_payload_hash(payload)
    audit = replace(prepared.audit, canonical_payload_hash=payload_hash, after_hash=chain_head)
    outbox = replace(prepared.outbox, payload=payload, payload_hash=outbox_payload_hash(payload))
    return PreparedPublication(
        prepared.scope,
        payload_hash,
        prepared.command,
        prepared.revision_record_version,
        prepared.revision,
        prepared.approval,
        prepared.submission,
        manifest,
        publication,
        forged_snapshot,
        audit,
        outbox,
        eligibility,
        binding,
    )


class _ForgingGovernanceRepository(SqliteGovernanceRepository):
    def commit_publication(self, prepared):
        return super().commit_publication(_forge_consistent_body(prepared))


class _FailingGovernanceRepository(SqliteGovernanceRepository):
    def __init__(self, database_path: Path) -> None:
        self.fail_publication = False

        def fail(step: str) -> None:
            if self.fail_publication and step == "outbox":
                raise OSError("publication outbox fault")  # noqa: TRY003

        super().__init__(database_path, fault_injector=fail)


def test_publication_snapshot_is_projected_from_runtime_body() -> None:
    from fmea_governance_fixtures import make_approval_decision, make_assemble_request, make_governance_inputs

    inputs = make_governance_inputs()
    providers = __import__("fmea_governance_fixtures", fromlist=["_INPUT_PROVIDERS"])._INPUT_PROVIDERS[
        id(inputs._source_attestation)
    ]
    base_runtime = build_workspace_governance_runtime(
        replace(providers, artifacts=_ReportArtifacts(providers.artifacts)),
    )
    source = base_runtime.source
    calls: list[tuple[object, object]] = []

    class SpySource:
        def load_inputs(self, analysis_id: str, workspace_id: str):
            return source.load_inputs(analysis_id, workspace_id)

        def build_publication_body(self, revision, trusted_inputs):
            calls.append((revision, trusted_inputs))
            return PublicationBody((), (), None, (), ())

        def get_publication_templates(self, revision, trusted_inputs):
            return source.get_publication_templates(revision, trusted_inputs)

    trusted_inputs = source.load_inputs("analysis-1", "ws-1")
    revision = base_runtime.assembler.assemble(make_assemble_request(), trusted_inputs)
    approval = make_approval_decision(revision_id=revision.revision_id, revision_hash=revision.revision_hash)
    readiness = __import__(
        "fmea_governance_fixtures", fromlist=["make_blocked_readiness_report"]
    ).make_blocked_readiness_report(
        revision_id=revision.revision_id,
        revision_hash=revision.revision_hash,
        analysis_id=revision.analysis_id,
    )
    service = RevisionGovernanceService(
        SqliteGovernanceRepository("C:/nonexistent/fmea-task2-test.sqlite3"),
        base_runtime.assembler,
        base_runtime.readiness_policy,
        SpySource(),
    )

    snapshot, _binding = service._snapshot(
        revision,
        approval,
        "publication-1",
        "manifest-1",
        readiness,
        "2026-09-04T00:00:00Z",
    )

    assert len(calls) == 1
    assert calls[0][0] is revision
    assert snapshot.version_manifest["body_schema_version"] == PUBLICATION_BODY_SCHEMA_VERSION


def test_sqlite_runtime_publishes_real_body_and_replays_immutable_snapshot(
    tmp_path: Path,
    fixture_pack,
    fixture_review_row,
    fixture_review_source,
    fixture_system_actor,
    fixture_human_reviewer,
) -> None:
    _runtime, repository, accepted_row, pack, service, command, publisher = _prepare_real_publication(
        tmp_path,
        fixture_pack,
        fixture_review_row,
        fixture_review_source,
        fixture_system_actor,
        fixture_human_reviewer,
    )
    published = service.publish(command, publisher)
    snapshot = service.get_snapshot(published.publication_id, publisher)

    assert snapshot.rows[0]["failure_mode"] == accepted_row.failure_mode
    assert snapshot.evidence_summary[0]["pack_hash"] == pack.pack_hash
    assert snapshot.evidence_summary[0]["refs"][0]["quote"] == pack.refs[0].quote
    assert snapshot.decision_summary[0]["decision"] == "accepted"
    assert snapshot.decision_summary[0]["role_category"] == "human_reviewer"
    assert snapshot.version_manifest["body_schema_version"] == PUBLICATION_BODY_SCHEMA_VERSION

    replay = service.publish(command, publisher)
    replayed_snapshot = service.get_snapshot(replay.publication_id, publisher)
    assert replay.replayed is True
    assert replayed_snapshot.snapshot_hash == snapshot.snapshot_hash


def test_publication_pins_template_and_saved_view_survives_registry_upgrade(
    tmp_path, fixture_pack, fixture_review_row, fixture_review_source,
    fixture_system_actor, fixture_human_reviewer,
):
    from fmea_application.report_view import build_report_view

    runtime, repository, _, _, service, command, publisher = _prepare_real_publication(
        tmp_path, fixture_pack, fixture_review_row, fixture_review_source,
        fixture_system_actor, fixture_human_reviewer,
    )
    published = service.publish(command, publisher)
    snapshot = service.get_snapshot(published.publication_id, publisher)
    assert snapshot.version_manifest["report_layout"]["columns"][2]["label"] == "故障模式"
    view = build_report_view(snapshot)
    # Any registry dependency would now fail; read/replay must use saved bytes only.
    runtime.source._providers.artifacts.template = None
    saved = repository.get_snapshot(published.publication_id, publisher.workspace_id)
    assert build_report_view(saved) == view
    assert service.publish(command, publisher).replayed


@pytest.mark.parametrize("attack", ["label", "order", "missing_layout", "missing_content", "forged_content", "noncanonical_content", "missing_source_set", "forged_source_set"])
def test_commit_rejects_fully_rehashed_layout_or_private_template_tampering(
    tmp_path, fixture_pack, fixture_review_row, fixture_review_source,
    fixture_system_actor, fixture_human_reviewer, attack,
):
    class TamperingRepository(SqliteGovernanceRepository):
        def commit_publication(self, prepared):
            if attack in {"missing_source_set", "forged_source_set"}:
                sources = prepared.source_binding.template_canonical_sources
                sources = () if attack == "missing_source_set" else tuple(
                    source.replace("故障模式", "伪造标签") for source in sources
                )
                prepared = replace(prepared, source_binding=replace(
                    prepared.source_binding, template_canonical_sources=sources,
                ))
            elif attack in {"missing_content", "forged_content", "noncanonical_content"}:
                canonical = prepared.source_binding.template_canonical_json
                replacement = None if attack == "missing_content" else (
                    canonical.replace("故障模式", "伪造标签") if attack == "forged_content" else canonical + " "
                )
                prepared = replace(prepared, source_binding=replace(
                    prepared.source_binding, template_canonical_json=replacement,
                ))
            else:
                manifest = dict(prepared.snapshot.version_manifest)
                layout = dict(manifest["report_layout"])
                columns = [dict(c) for c in layout["columns"]]
                if attack == "label":
                    columns[0]["label"] = "forged label"
                elif attack == "order":
                    columns.reverse()
                layout["columns"] = tuple(columns)
                manifest["report_layout"] = layout
                if attack == "missing_layout":
                    del manifest["report_layout"]
                prepared = _forge_consistent_body(prepared, version_manifest=manifest)
            return super().commit_publication(prepared)

    _, repository, _, _, service, command, publisher = _prepare_real_publication(
        tmp_path, fixture_pack, fixture_review_row, fixture_review_source,
        fixture_system_actor, fixture_human_reviewer, governance_repository_type=TamperingRepository,
    )
    before = _database_state(repository.database_path)
    with pytest.raises(GovernanceServiceError) as caught:
        service.publish(command, publisher)
    assert caught.value.code in {"FMEA_PUBLICATION_BODY_UNSAFE", "FMEA_PUBLICATION_BODY_INCOMPLETE"}
    assert _database_state(repository.database_path) == before


def test_two_row_publication_normalizes_reversed_decision_id_authority_order(
    tmp_path: Path,
    fixture_pack,
    fixture_review_row,
    fixture_review_source,
    fixture_system_actor,
    fixture_human_reviewer,
) -> None:
    from fmea_review_fixtures import make_review_source

    second_row = replace(fixture_review_row, row_id="row-2", item_id="filter-2")
    second_source = make_review_source(row_id="row-2", candidate_id="candidate-2")
    _runtime, _repository, _accepted_row, _pack, service, command, publisher = _prepare_real_publication(
        tmp_path,
        fixture_pack,
        fixture_review_row,
        fixture_review_source,
        fixture_system_actor,
        fixture_human_reviewer,
        additional_review_rows=(second_row,),
        additional_review_sources=(second_source,),
        decision_ids=("decision-z", "decision-a"),
    )

    published = service.publish(command, publisher)
    snapshot = service.get_snapshot(published.publication_id, publisher)

    assert tuple(item["decision_id"] for item in snapshot.decision_summary) == ("decision-a", "decision-z")
    assert {item["row_id"] for item in snapshot.decision_summary} == {"row-1", "row-2"}


def test_missing_persisted_review_record_blocks_body_projection(
    tmp_path: Path,
    fixture_pack,
    fixture_review_row,
    fixture_review_source,
    fixture_system_actor,
    fixture_human_reviewer,
) -> None:
    import fmea_governance_fixtures as governance_fixtures

    runtime, repository, _accepted_row, _pack = _persisted_body_runtime(
        tmp_path,
        fixture_pack,
        fixture_review_row,
        fixture_review_source,
        fixture_system_actor,
        fixture_human_reviewer,
        persist_review_decision=False,
    )
    with sqlite3.connect(repository.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM review_decisions").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0] == 0
    trusted_inputs = runtime.source.load_inputs("analysis-1", "ws-1")
    revision = runtime.assembler.assemble(governance_fixtures.make_assemble_request(), trusted_inputs)

    with pytest.raises(FmeaDomainError, match="FMEA_PUBLICATION_BODY_INCOMPLETE"):
        runtime.source.build_publication_body(revision, trusted_inputs)


def test_forged_review_authority_is_rejected_before_any_write(
    tmp_path: Path,
    fixture_pack,
    fixture_review_row,
    fixture_review_source,
    fixture_system_actor,
    fixture_human_reviewer,
) -> None:
    _runtime, repository, _accepted_row, _pack, service, command, publisher = _prepare_real_publication(
        tmp_path,
        fixture_pack,
        fixture_review_row,
        fixture_review_source,
        fixture_system_actor,
        fixture_human_reviewer,
        governance_repository_type=_ForgedReviewAuthorityRepository,
    )
    before = _database_state(repository.database_path)

    with pytest.raises(GovernanceServiceError) as captured:
        service.publish(command, publisher)

    assert captured.value.code == "FMEA_PUBLICATION_BODY_STALE"
    assert _database_state(repository.database_path) == before


def test_post_publication_source_mutation_does_not_change_saved_snapshot_or_replay(
    tmp_path: Path,
    fixture_pack,
    fixture_review_row,
    fixture_review_source,
    fixture_system_actor,
    fixture_human_reviewer,
) -> None:
    _runtime, repository, accepted_row, _pack, service, command, publisher = _prepare_real_publication(
        tmp_path,
        fixture_pack,
        fixture_review_row,
        fixture_review_source,
        fixture_system_actor,
        fixture_human_reviewer,
    )
    published = service.publish(command, publisher)
    saved = service.get_snapshot(published.publication_id, publisher)

    changed = replace(accepted_row, failure_mode="changed after publication")
    row_json, row_hash = SqliteFmeaRepository._row_json(changed)
    workspace_id = changed.analysis_id.replace("analysis", "ws")
    with sqlite3.connect(repository.database_path) as connection:
        connection.execute(
            "UPDATE fmea_rows SET row_hash=?, row_json=? WHERE row_id=? AND workspace_id=?",
            (row_hash, row_json, changed.row_id, workspace_id),
        )

    assert service.get_snapshot(published.publication_id, publisher) == saved
    replay = service.publish(command, publisher)
    assert replay.replayed is True
    assert service.get_snapshot(replay.publication_id, publisher) == saved


def test_changed_persisted_row_is_stale_and_publication_transaction_rolls_back(
    tmp_path: Path,
    fixture_pack,
    fixture_review_row,
    fixture_review_source,
    fixture_system_actor,
    fixture_human_reviewer,
) -> None:
    _runtime, repository, _accepted_row, _pack, service, command, publisher = _prepare_real_publication(
        tmp_path,
        fixture_pack,
        fixture_review_row,
        fixture_review_source,
        fixture_system_actor,
        fixture_human_reviewer,
        governance_repository_type=_MutatingGovernanceRepository,
    )
    before = _database_state(repository.database_path)

    with pytest.raises(GovernanceServiceError) as captured:
        service.publish(command, publisher)

    assert captured.value.code == "FMEA_PUBLICATION_BODY_STALE"
    assert _database_state(repository.database_path) == before


def test_forged_body_and_recomputed_binding_are_rejected_before_any_write(
    tmp_path: Path,
    fixture_pack,
    fixture_review_row,
    fixture_review_source,
    fixture_system_actor,
    fixture_human_reviewer,
) -> None:
    _runtime, repository, _accepted_row, _pack, service, command, publisher = _prepare_real_publication(
        tmp_path,
        fixture_pack,
        fixture_review_row,
        fixture_review_source,
        fixture_system_actor,
        fixture_human_reviewer,
        governance_repository_type=_ForgingGovernanceRepository,
    )
    before = _database_state(repository.database_path)

    with pytest.raises(GovernanceServiceError) as captured:
        service.publish(command, publisher)

    assert captured.value.code == "FMEA_PUBLICATION_BODY_UNSAFE"
    assert _database_state(repository.database_path) == before


def test_fault_injection_rolls_back_real_body_publication_writes(
    tmp_path: Path,
    fixture_pack,
    fixture_review_row,
    fixture_review_source,
    fixture_system_actor,
    fixture_human_reviewer,
) -> None:
    _runtime, repository, _accepted_row, _pack, service, command, publisher = _prepare_real_publication(
        tmp_path,
        fixture_pack,
        fixture_review_row,
        fixture_review_source,
        fixture_system_actor,
        fixture_human_reviewer,
        governance_repository_type=_FailingGovernanceRepository,
    )
    repository.fail_publication = True
    before = _database_state(repository.database_path)

    with pytest.raises(GovernanceServiceError):
        service.publish(command, publisher)

    assert _database_state(repository.database_path) == before


def test_new_markerless_publication_is_rejected_but_replay_gate_is_first(
    tmp_path: Path,
) -> None:
    import fmea_governance_fixtures as governance_fixtures

    legacy_prepared = governance_fixtures.prepared_publication()
    fresh_repository = SqliteGovernanceRepository(tmp_path / "fresh.sqlite3")
    fresh_repository.initialize()
    before = _database_state(fresh_repository.database_path)
    with pytest.raises(FmeaDomainError, match="new publications require an authoritative body"):
        fresh_repository.commit_publication(legacy_prepared)
    assert _database_state(fresh_repository.database_path) == before

    legacy_repository = SqliteGovernanceRepository(tmp_path / "legacy.sqlite3")
    legacy_repository.initialize()
    governance_fixtures.seed_authoritative_analysis(legacy_repository.database_path)
    _seed_persisted_legacy_publication(legacy_repository, legacy_prepared)
    replay = legacy_repository.commit_publication(legacy_prepared)
    assert replay.replayed is True
    assert legacy_repository.get_snapshot(replay.publication_id, "ws-1") == legacy_prepared.snapshot


def test_publication_failure_injection_keeps_body_error_non_retryable_contract() -> None:
    error = GovernanceServiceError("FMEA_PUBLICATION_BODY_STALE", "safe stale body")
    assert error.retryable is False


@pytest.mark.parametrize(
    ("code", "status"),
    [
        ("FMEA_PUBLICATION_BODY_STALE", 409),
        ("FMEA_PUBLICATION_BODY_INCOMPLETE", 409),
        ("FMEA_PUBLICATION_BODY_UNSAFE", 400),
    ],
)
def test_publication_body_errors_are_public_non_retryable_contracts(code: str, status: int) -> None:
    from chroma_rag_poc.routes_fmea_governance_v1 import _ERROR_STATUS, _problem_response

    error = GovernanceServiceError(code, "safe publication body failure")
    response = _problem_response(error)

    assert _ERROR_STATUS[code] == status
    assert response.status_code == status
    assert response.body is not None
    assert b"retryable" in response.body
    assert b"false" in response.body
