"""Connect actual reviewed/scored/propagated state to governance and delivery.

The ports below read the same SQLite database written by preceding slices.
Only source documents and model outputs are deterministic fixtures.
"""

# ruff: noqa: TRY003, S608
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from hashlib import sha256
from pathlib import Path

from core_domain.fmea.codec import decode_analysis
from core_domain.fmea.governance import canonical_hash, canonical_json_bytes
from core_domain.fmea.states import ActorType
from fmea_application.export_service import ExportService, StartExportCommand
from fmea_application.governance_contracts import (
    ApprovalCommand,
    AssembleRevisionCommand,
    PublishCommand,
    RevisionAssemblyRequest,
    SubmitApprovalCommand,
    SupersedePublicationCommand,
    WithdrawPublicationCommand,
)
from fmea_application.ports import GovernanceRepositoryProviders
from fmea_application.review_contracts import ActorContext, idempotency_key_hash
from fmea_application.revision_assembler import (
    GovernanceRetrievalProvenance,
    ResolvedAnalysisRecord,
)
from fmea_infrastructure.artifact_store import WorkspaceArtifactStore
from fmea_infrastructure.composition import RegistryGovernanceArtifactProvider, build_workspace_governance_runtime
from fmea_infrastructure.delivery_repository_sqlite import SqliteFmeaDeliveryRepository
from fmea_infrastructure.domain_pack_registry import (
    FileDomainPackRegistry,
    FileScoringRuleRegistry,
    load_domain_pack_manifest,
)
from fmea_infrastructure.export_docx import DocxFmeaExporter
from fmea_infrastructure.export_json import CanonicalJsonExporter
from fmea_infrastructure.export_xlsx import XlsxFmeaExporter
from fmea_infrastructure.governance_repository_sqlite import SqliteGovernanceRepository
from fmea_infrastructure.propagation_rule_registry import FilePropagationRuleRegistry, load_propagation_rule_pack
from fmea_infrastructure.repository_sqlite import SqliteFmeaRepository
from fmea_infrastructure.risk_repository_sqlite import SqliteRiskRepository
from structured_output_application import TemplateCompiler
from structured_output_infrastructure import Draft202012SchemaAdapter, FileTemplateRegistry, load_template_source

ROOT = Path(__file__).resolve().parents[3]
UTC = "2026-09-04T00:00:00Z"


def public(value):
    return json.loads(canonical_json_bytes(value))


def key(number):
    return f"00000000-0000-4000-8000-{number:012d}"


def records(database_path, table, column, workspace_id):
    with closing(sqlite3.connect(database_path)) as connection:
        return [
            json.loads(row[0])
            for row in connection.execute(
                f"SELECT {column} FROM {table} WHERE workspace_id=? ORDER BY rowid",
                (workspace_id,),
            )
        ]


def persisted_events(database_path, workspace_id):
    audits = records(database_path, "audit_events", "event_json", workspace_id)
    audits += records(database_path, "fmea_audit_events", "event_json", workspace_id)
    with closing(sqlite3.connect(database_path)) as connection:
        connection.row_factory = sqlite3.Row
        events = [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM fmea_outbox_events WHERE workspace_id=? ORDER BY rowid",
                (workspace_id,),
            )
        ]
    for event in events:
        event["payload"] = json.loads(event.pop("payload_json"))
    return audits, events


def event_counts(database_path, workspace_id):
    audits, outbox = persisted_events(database_path, workspace_id)
    return {"audit_events": len(audits), "outbox_events": len(outbox)}


class PersistedProviders:
    def __init__(self, database_path, source, graph):
        self.database_path = database_path
        self.source = source
        self.graph = graph
        self.parent_revision = None
        self.review = SqliteFmeaRepository(database_path)
        self.risk = SqliteRiskRepository(database_path)
        self.publication_reviews = SqliteGovernanceRepository(database_path)
        domain_source = (ROOT / "domain_packs/fuel-combustion/manifest.yaml").read_bytes()
        domain = load_domain_pack_manifest(domain_source)

        registry_root = Path(database_path).parent / "immutable-registries"
        template_registry = FileTemplateRegistry(registry_root / "templates")
        self.template_registry = template_registry
        compiler = TemplateCompiler(schema_validator=Draft202012SchemaAdapter(), source_loader=load_template_source)
        for path in (
            ROOT / "templates/examples/fuel-combustion-fmea.yaml",
            ROOT / "domain_packs/fuel-combustion/templates/fmea-propagation-hypothesis-1.0.0.yaml",
        ):
            template_registry.register(compiler.compile_path(path), path.read_bytes(), path.suffix)
        propagation_registry = FilePropagationRuleRegistry(registry_root / "propagation")
        propagation_bytes = (ROOT / "domain_packs/fuel-combustion/propagation/fuel-combustion-1.0.0.yaml").read_bytes()
        propagation_registry.register(load_propagation_rule_pack(propagation_bytes), propagation_bytes)
        self.artifact_provider = RegistryGovernanceArtifactProvider(
            domain_pack=domain,
            domain_pack_registry=FileDomainPackRegistry(registry_root / "domain"),
            template_registry=template_registry,
            scoring_rule_registry=FileScoringRuleRegistry(registry_root / "scoring"),
            propagation_rule_registry=propagation_registry,
        )

    def get_report_template(self, template_id, version):
        return self.artifact_provider.get_report_template(template_id, version)

    def load_publication_reviews(self, revision):
        return self.publication_reviews.load_publication_reviews(revision)

    def _scope(self, analysis_id, workspace_id):
        if (analysis_id, workspace_id) != (self.source.analysis.analysis_id, self.source.evidence_pack.workspace_id):
            raise ValueError("acceptance source scope mismatch")

    def get_analysis(self, analysis_id, workspace_id):
        self._scope(analysis_id, workspace_id)
        raw = records(self.database_path, "fmea_analyses", "analysis_json", workspace_id)
        analysis = next(decode_analysis(json.dumps(item)) for item in raw if item["analysis_id"] == analysis_id)
        digest = canonical_hash(analysis)
        return ResolvedAnalysisRecord(workspace_id, analysis, analysis.record_version, digest, digest)

    def list_rows(self, analysis_id, workspace_id):
        self._scope(analysis_id, workspace_id)
        return (self.review.get_row(self.source.row.row_id, workspace_id),)

    def list_risk_records(self, analysis_id, workspace_id):
        self._scope(analysis_id, workspace_id)
        return (self.risk.get_current_assessment(self.source.row.row_id, workspace_id),)

    def get_current_graph(self, analysis_id, workspace_id):
        self._scope(analysis_id, workspace_id)
        return self.graph

    def list_evidence_packs(self, analysis_id, workspace_id):
        self._scope(analysis_id, workspace_id)
        return (self.review.get_evidence_pack(self.source.evidence_pack.pack_id, workspace_id),)

    def get_artifacts(self, analysis_id, workspace_id, analysis):
        self._scope(analysis_id, workspace_id)
        return self.artifact_provider.get_artifacts(analysis_id, workspace_id, analysis)

    def list_active_run_ids(self, analysis_id, workspace_id):
        self._scope(analysis_id, workspace_id)
        return ()

    def list_human_acknowledgements(self, analysis_id, workspace_id):
        self._scope(analysis_id, workspace_id)
        return ()

    def get_provenance(self, analysis_id, workspace_id):
        self._scope(analysis_id, workspace_id)
        source = self.review.get_review_source(self.source.row.row_id, workspace_id)
        return GovernanceRetrievalProvenance(
            workspace_id,
            analysis_id,
            source.requested_evidence_profile.value,
            source.resolved_evidence_profile.value,
            tuple(kind.value for kind in source.evidence_types),
            (("text", 1),),
            source.retrieval_warnings,
        )

    def get_parent_revision(self, analysis_id, workspace_id):
        self._scope(analysis_id, workspace_id)
        return self.parent_revision


class GovernanceDeliveryRun:
    """One connected lifecycle; finish withdrawal after source migration."""

    def __init__(self, database_path, source, graph, work_dir):
        self.database_path = database_path
        self.workspace_id = source.evidence_pack.workspace_id
        self.source = source
        self.providers = PersistedProviders(database_path, source, graph)
        self.repository = SqliteFmeaDeliveryRepository(database_path)
        self.repository.initialize()
        providers = self.providers
        self.runtime = build_workspace_governance_runtime(
            GovernanceRepositoryProviders(
                analysis=providers,
                review=providers,
                risk=providers,
                propagation=providers,
                evidence=providers,
                artifacts=providers,
                runs=providers,
                acknowledgements=providers,
                retrieval=providers,
                parent=providers,
                publication_reviews=providers,
            ),
            repository=self.repository,
            clock=lambda: UTC,
        )
        self.service = self.runtime.service
        self.store = WorkspaceArtifactStore(Path(work_dir) / "artifacts", self.workspace_id)
        self.export_service = ExportService(
            self.repository,
            self.repository,
            self.store,
            (CanonicalJsonExporter(), XlsxFmeaExporter(), DocxFmeaExporter()),
            clock=lambda: UTC,
        )
        self.evidence = {
            name: []
            for name in (
                "steps",
                "replays",
                "revisions",
                "submissions",
                "approvals",
                "publications",
                "snapshots",
                "manifests",
                "exports",
                "lifecycle_events",
                "authority_denials",
            )
        }
        self.payloads = {}
        self.parent = None
        self.child = None

    def actor(self, role):
        return ActorContext(f"fuel-{role}", ActorType.HUMAN, frozenset({role}), self.workspace_id)

    def call(self, command_name, method, command, role, *, replay=False):
        actor = self.actor(role)
        before = event_counts(self.database_path, self.workspace_id)
        result = method(command, actor)
        after = event_counts(self.database_path, self.workspace_id)
        receipt = public(result)
        self.evidence["steps"].append({
            "step_id": f"governance-step-{len(self.evidence['steps']) + 1}",
            "command": command_name,
            "actor_id": actor.actor_id,
            "actor_type": actor.actor_type.value,
            "request_identity": {
                "request_hash": canonical_hash(command),
                "idempotency_key_hash": idempotency_key_hash(command.idempotency_key),
            },
            "request": public(command),
            "before": before,
            "after": after,
            "result_ids": {k: v for k, v in receipt.items() if k.endswith("_id")},
            "result": receipt,
        })
        if replay:
            replayed = method(command, actor)
            self.evidence["replays"].append({
                "command": command_name,
                "first": receipt,
                "replayed": public(replayed),
                "event_counts_before": after,
                "event_counts_after": event_counts(self.database_path, self.workspace_id),
            })
        return result

    def publish(self, *, parent=None, offset=100):
        self.providers.parent_revision = parent
        assembled = self.call(
            "fmea.revision.assemble",
            self.service.assemble,
            AssembleRevisionCommand(
                RevisionAssemblyRequest(
                    self.source.analysis.analysis_id,
                    None if parent is None else parent.revision_id,
                    1,
                    None if parent is None else parent.revision_hash,
                ),
                key(offset),
            ),
            "reviewer",
        )
        revision = self.service.get_revision(assembled.revision_id, self.actor("reviewer"))
        known_templates = {(item["template_id"], item["version"]) for item in self.evidence.get("registered_templates", [])}
        for template_id, version, content_hash in revision.template_identities:
            if (template_id, version) in known_templates:
                continue
            canonical = self.providers.get_report_template(template_id, version)
            source = self.providers.template_registry.get_source_bytes(template_id, version)
            self.evidence.setdefault("registered_templates", []).append({
                "compiled": {
                    "canonical_json": canonical,
                    "template_hash": content_hash,
                },
                "source_hash": sha256(source).hexdigest(),
                "template_hash": content_hash,
                "template_id": template_id,
                "version": version,
            })
            known_templates.add((template_id, version))
        readiness = self.service.readiness(revision.revision_id, self.actor("reviewer"))
        if not readiness.ready:
            raise ValueError(f"full acceptance readiness failed: {public(readiness)}")
        submitted = self.call(
            "fmea.approval.submit",
            self.service.submit_for_approval,
            SubmitApprovalCommand(
                revision.revision_id, revision.revision_hash, assembled.record_version, key(offset + 1)
            ),
            "reviewer",
        )
        approve_command = ApprovalCommand(
            submitted.submission_id,
            revision.revision_id,
            revision.revision_hash,
            submitted.record_version,
            "Human approval of evidence-bound offline case",
            key(offset + 2),
        )
        approved = self.call("fmea.approval.decide", self.service.approve, approve_command, "approver", replay=True)
        publish_command = PublishCommand(
            revision.revision_id,
            revision.revision_hash,
            approved.approval_id,
            assembled.record_version,
            key(offset + 3),
        )
        published = self.call(
            "fmea.publication.publish", self.service.publish, publish_command, "publisher", replay=True
        )
        # Exercise authority checks against the same commands, not a claimed zero.
        for command_name, method, command in (
            ("fmea.approval.decide", self.service.approve, approve_command),
            ("fmea.publication.publish", self.service.publish, publish_command),
        ):
            model = ActorContext(
                "fixture-model", ActorType.MODEL, frozenset({"approver", "publisher"}), self.workspace_id
            )
            before = event_counts(self.database_path, self.workspace_id)
            try:
                method(command, model)
            except Exception as error:
                code = getattr(error, "code", "")
                if not code.endswith("FORBIDDEN"):
                    raise
            else:
                raise ValueError("model authority unexpectedly accepted")
            self.evidence["authority_denials"].append({
                "command": command_name,
                "actor_type": "model",
                "error_code": code,
                "event_counts_before": before,
                "event_counts_after": event_counts(self.database_path, self.workspace_id),
            })
        self.evidence["revisions"].append(public(revision))
        self.evidence["submissions"].append(
            public(self.repository.get_approval_submission(submitted.submission_id, self.workspace_id))
        )
        self.evidence["approvals"].append(
            public(self.repository.get_approval_decision(approved.approval_id, self.workspace_id))
        )
        self.evidence["publications"].append(
            public(self.repository.get_publication(published.publication_id, self.workspace_id))
        )
        snapshot = self.repository.get_snapshot(published.publication_id, self.workspace_id)
        self.evidence["snapshots"].append(public(snapshot))
        for index, format_name in enumerate(("json", "xlsx", "docx")):
            filename = f"fuel-{offset}.{format_name}"
            command = StartExportCommand(
                export_run_id=f"full-export-{offset}-{format_name}",
                workspace_id=self.workspace_id,
                revision_id=revision.revision_id,
                snapshot_id=snapshot.snapshot_id,
                snapshot_hash=snapshot.snapshot_hash,
                publication_id=published.publication_id,
                format=format_name,
                draft_preview=False,
                filename=filename,
                idempotency_key=key(offset + 10 + index),
            )
            run = self.call("fmea.export.start", self.export_service.start, command, "exporter", replay=True)
            if run.status.value != "succeeded":
                raise ValueError(f"full acceptance export failed: {public(run)}")
            artifact = self.export_service.get_artifact(run.artifact_id, self.actor("exporter"))
            path = f"exports/{filename}"
            self.payloads[path] = artifact.payload
            self.evidence["exports"].append({
                "path": path,
                "format": format_name,
                "run": public(run),
                "manifest": public(artifact.manifest),
            })
        return revision, published

    def finish(self, parent_publication, child_publication):
        self.call(
            "fmea.publication.supersede",
            self.service.supersede,
            SupersedePublicationCommand(
                parent_publication.publication_id,
                child_publication.publication_id,
                1,
                1,
                "Child publication supersedes original",
                key(300),
            ),
            "publisher",
            replay=True,
        )
        self.call(
            "fmea.publication.withdraw",
            self.service.withdraw_publication,
            WithdrawPublicationCommand(
                child_publication.publication_id, 1, "Offline lifecycle withdrawal exercise", None, key(301)
            ),
            "publisher",
            replay=True,
        )
        self.evidence["manifests"] = records(
            self.database_path, "fmea_publication_manifests", "manifest_json", self.workspace_id
        )
        self.evidence["lifecycle_events"] = records(
            self.database_path, "fmea_supersessions", "supersession_json", self.workspace_id
        )
        self.evidence["lifecycle_events"] += records(
            self.database_path, "fmea_publication_withdrawals", "withdrawal_json", self.workspace_id
        )
        self.evidence["publication_lifecycle"] = [
            public(self.repository.get_publication_lifecycle(p.publication_id, self.workspace_id))
            for p in (parent_publication, child_publication)
        ]
