"""Bounded real propagation proposal/review lifecycle for Task 8.

The helper consumes the native objects produced by the connected candidate,
review, and risk slice.  It owns no acceptance manifest semantics and does
not import test fixtures.  The only deterministic double is the suggestion
generator at the model gateway; repositories, topology loading, validation,
and human review remain real.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path

from core_domain.fmea.entities import FmeaAnalysis, FmeaRow
from core_domain.fmea.governance import canonical_hash, canonical_json_bytes
from core_domain.fmea.propagation import PropagationGraphRevision, TopologySnapshot
from core_domain.fmea.scoring import RiskAssessmentRecord
from core_domain.fmea.states import (
    ActorType,
    ClaimStatus,
    EvidenceSupportStatus,
    ReviewStatus,
    RiskStatus,
)
from core_domain.fmea.value_objects import EvidencePack
from fmea_application.assistance_contracts import AssistanceKind, AssistanceSuggestion
from fmea_application.propagation_service import (
    ConfirmPropagationCommand,
    PropagationAnalysisService,
    PropagationDecisionAction,
    PropagationEdgeDecision,
    PropagationModelRequest,
    PropagationReviewService,
    StartPropagationCommand,
    propagation_review_payload_hash,
    propagation_start_payload_hash,
)
from fmea_application.review_contracts import ActorContext, IdempotencyScope, idempotency_key_hash
from fmea_infrastructure.assistance_repository_sqlite import SqliteAssistanceRepository
from fmea_infrastructure.domain_pack_registry import FileDomainPackRegistry, load_domain_pack_manifest
from fmea_infrastructure.propagation_repository_sqlite import SqlitePropagationRepository
from fmea_infrastructure.propagation_rule_registry import (
    FilePropagationRuleRegistry,
    load_propagation_rule_pack,
)
from fmea_infrastructure.risk_repository_sqlite import SqliteRiskRepository
from fmea_infrastructure.sqlite_codec import decode_audit_event
from fmea_infrastructure.topology_json import JsonTopologyRepository, topology_snapshot_hash

_REPO_ROOT = Path(__file__).resolve().parents[3]
_UTC = "2026-09-04T00:00:00Z"
_TOPOLOGY_ID = "demo"
_TOPOLOGY_VERSION = "1.0.0"
_DOMAIN_MANIFEST_PATH = _REPO_ROOT / "domain_packs" / "fuel-combustion" / "manifest.yaml"
_RULE_PATH = _REPO_ROOT / "domain_packs" / "fuel-combustion" / "propagation" / "fuel-combustion-1.0.0.yaml"
_TOPOLOGY_PATH = _REPO_ROOT / "domain_packs" / "fuel-combustion" / "topology" / "demo-1.0.0.json"


class _BoundTopologyPort:
    """Expose an immutable source snapshot in the caller's workspace context."""

    def __init__(self, snapshot: TopologySnapshot) -> None:
        self._snapshot = snapshot
        self._repository = JsonTopologyRepository(_TOPOLOGY_PATH.parent)

    def load_snapshot(self, topology_id: str, version: str) -> TopologySnapshot:
        if (topology_id, version) != (_TOPOLOGY_ID, _TOPOLOGY_VERSION):
            raise ValueError("unexpected topology identity")  # noqa: TRY003 - bounded port invariant
        return self._snapshot

    def neighbors(self, snapshot: TopologySnapshot, entity_id: str):
        if snapshot != self._snapshot:
            raise ValueError("topology snapshot is not the bound source snapshot")  # noqa: TRY003 - bounded port invariant
        return self._repository.neighbors(snapshot, entity_id)


_NATIVE_ITEM_TOPOLOGY_MAPPING = {"fuel-filter-1": "fuel_filter"}


class _NativeMappedPropagationRepository(SqlitePropagationRepository):
    """Keep persisted row identity while mapping its native item to topology."""

    def get_row(self, row_id: str, workspace_id: str):
        row = super().get_row(row_id, workspace_id)
        if row is None:
            return None
        mapped_item_id = _NATIVE_ITEM_TOPOLOGY_MAPPING.get(row.item_id)
        return row if mapped_item_id is None else replace(row, item_id=mapped_item_id)


class _DeterministicPropagationGenerator:
    """Deterministic proposal generation at the model gateway only."""

    def __init__(self) -> None:
        self.requests: list[PropagationModelRequest] = []

    def generate(self, request: PropagationModelRequest) -> AssistanceSuggestion[object]:
        self.requests.append(request)
        edges: tuple[dict[str, object], ...] = ()
        if request.candidate_interfaces:
            candidate = request.candidate_interfaces[0]
            evidence_ids = request.candidate_evidence_ids[:1]
            edge = {
                "interface_id": candidate.interface_id,
                "source_entity_id": candidate.source_node_id,
                "target_entity_id": candidate.target_node_id,
                "relation_type": (
                    "propagation"
                    if "propagation" in request.allowed_relation_types
                    else request.allowed_relation_types[0]
                ),
                "interface_variable": candidate.interface_variable,
                "unit": candidate.unit,
                "direction": candidate.direction,
                "threshold": None,
                "operating_modes": candidate.operating_modes,
                "delay_ms": 0,
                "response_time_ms": 0,
                "fault_tolerance_time_ms": 0,
                "barrier_ids": (),
                "evidence_ids": evidence_ids,
                "evidence_support": EvidenceSupportStatus.SUPPORTED.value,
                "claim_status": ClaimStatus.KNOWN.value,
                "path_length": candidate.path_length,
                "is_cyclic": False,
                "is_unprocessed": False,
                "is_external": False,
                "is_terminal": False,
                "risk_priority": "normal",
            }
            edges = (edge,)
        return AssistanceSuggestion(
            suggestion_id="propagation-suggestion-fuel-1",
            kind=AssistanceKind.PROPAGATION_HYPOTHESIS,
            workspace_id=request.evidence_pack.workspace_id,
            target_type="fmea_analysis",
            target_id=request.analysis.analysis_id,
            target_record_version=request.analysis.record_version,
            evidence_pack_ids=(request.evidence_pack.pack_id,),
            payload={"edges": edges},
            evidence_ids=request.candidate_evidence_ids[:1] if edges else (),
            uncertainty="bounded-demo-input",
            model_hash="sha256:" + "7" * 64,
            prompt_hash="sha256:" + "8" * 64,
            run_id=request.run_id,
            trace_id="propagation-trace-fuel-1",
            domain_pack_id=request.domain_pack.pack_id,
            domain_pack_version=request.domain_pack.version,
            template_id="fmea-propagation-hypothesis",
            template_version="1.0.0",
            rule_pack_id=request.rule_pack.rule_pack_id,
            rule_pack_version=request.rule_pack.version,
            created_at=_UTC,
        )


@dataclass(frozen=True, slots=True)
class PropagationRunResult:
    graph: PropagationGraphRevision
    evidence: dict[str, object]


def _public(value: object) -> object:
    """Project one native DTO through the canonical public JSON codec."""

    return json.loads(canonical_json_bytes(value).decode("utf-8"))


def _hash_json(value: object) -> str:
    return canonical_hash(value, prefixed=True)


def _persisted_counts(database_path: Path, repository: SqlitePropagationRepository, workspace_id: str) -> dict[str, int]:
    with closing(sqlite3.connect(database_path)) as connection:
        audit_events = connection.execute(
            "SELECT COUNT(*) FROM audit_events WHERE workspace_id = ?", (workspace_id,)
        ).fetchone()[0]
        outbox_events = connection.execute(
            "SELECT COUNT(*) FROM fmea_outbox_events WHERE workspace_id = ?", (workspace_id,)
        ).fetchone()[0]
    return {
        "audit_events": int(audit_events),
        "outbox_events": int(outbox_events),
        "propagation_records": repository.count_propagation_records(workspace_id),
    }


def _persisted_state_hash(database_path: Path) -> str:
    """Hash a consistent logical snapshot of every persisted table and column.

    Full-table coverage includes rows, graphs, runs, suggestions, decisions,
    idempotency reservations/results, audit and outbox, including JSON payloads.
    Sorting canonical rows makes the digest independent of query row order;
    retaining duplicates and SQL values detects same-count in-place changes.
    """

    tables = {}
    with closing(sqlite3.connect(database_path)) as connection:
        connection.execute("BEGIN")
        schemas = connection.execute(
            "SELECT name, sql FROM sqlite_schema WHERE type = 'table' ORDER BY name"
        ).fetchall()
        for name, schema in schemas:
            quoted_name = '"' + name.replace('"', '""') + '"'
            cursor = connection.execute(f"SELECT * FROM {quoted_name}")  # noqa: S608 - quoted SQLite schema identifier
            rows = [
                [
                    {"sqlite_blob_hex": value.hex()} if isinstance(value, bytes) else value
                    for value in row
                ]
                for row in cursor.fetchall()
            ]
            tables[name] = {
                "schema": schema,
                "columns": [column[0] for column in cursor.description],
                "rows": sorted(rows, key=canonical_json_bytes),
            }
    return _hash_json(tables)


def _propagation_audits(database_path: Path, workspace_id: str) -> tuple[object, ...]:
    with closing(sqlite3.connect(database_path)) as connection:
        rows = connection.execute(
            "SELECT event_json FROM audit_events WHERE workspace_id = ? ORDER BY rowid", (workspace_id,)
        ).fetchall()
    return tuple(
        event
        for event in (decode_audit_event(row[0]) for row in rows)
        if event.command.startswith("fmea.propagation.")
    )


def _propagation_outbox(
    propagation_repository: SqlitePropagationRepository,
    database_path: Path,
    graph_ids: tuple[str, ...],
    workspace_id: str,
) -> tuple[object, ...]:
    events = []
    with closing(sqlite3.connect(database_path)) as connection:
        connection.row_factory = sqlite3.Row
        for graph_id in graph_ids:
            rows = connection.execute(
                "SELECT event_id FROM fmea_outbox_events "
                "WHERE aggregate_id = ? AND workspace_id = ? ORDER BY created_at, event_id",
                (graph_id, workspace_id),
            ).fetchall()
            events.extend(
                SqlitePropagationRepository._decode_outbox(connection, row["event_id"], workspace_id)
                for row in rows
            )
    return tuple(sorted(events, key=lambda event: (event.created_at, event.event_id)))


def _same_review_persistence(first: object, replayed: object) -> bool:
    """Compare persisted review identity while ignoring replay transport metadata."""

    return (
        getattr(first, "graph", None) == getattr(replayed, "graph", None)
        and getattr(first, "decision_id", None) == getattr(replayed, "decision_id", None)
        and getattr(first, "audit_event_id", None) == getattr(replayed, "audit_event_id", None)
        and getattr(first, "outbox_event_id", None) == getattr(replayed, "outbox_event_id", None)
        and getattr(first, "persisted", None) == getattr(replayed, "persisted", None)
    )


def _step(
    *,
    command: str,
    actor: ActorContext,
    request_id: str,
    request_hash: str,
    idempotency_key: str,
    before: dict[str, object],
    after: dict[str, object],
    result_ids: dict[str, str],
) -> dict[str, object]:
    return {
        "step_id": command,
        "command": command,
        "actor_id": actor.actor_id,
        "actor_type": actor.actor_type.value,
        "request_identity": {
            "request_id": request_id,
            "request_hash": request_hash,
            "idempotency_key_hash": idempotency_key_hash(idempotency_key),
        },
        "before": before,
        "after": after,
        "result_ids": result_ids,
    }


def _load_native_resources(
    *,
    registry_root: Path,
    analysis: FmeaAnalysis,
    workspace_id: str,
) -> tuple[object, object, TopologySnapshot, str]:
    domain_source = _DOMAIN_MANIFEST_PATH.read_bytes()
    rule_source = _RULE_PATH.read_bytes()
    topology_source = _TOPOLOGY_PATH.read_bytes()
    domain_pack = load_domain_pack_manifest(domain_source)
    rule_pack = load_propagation_rule_pack(rule_source)
    FileDomainPackRegistry(registry_root / "domain").register(domain_pack, domain_source)
    FilePropagationRuleRegistry(registry_root / "propagation").register(rule_pack, rule_source)
    source_topology = JsonTopologyRepository(
        _TOPOLOGY_PATH.parent,
        source_hashes={(_TOPOLOGY_ID, _TOPOLOGY_VERSION): sha256(topology_source).hexdigest()},
    ).load_snapshot(_TOPOLOGY_ID, _TOPOLOGY_VERSION)
    bound_topology = replace(source_topology, workspace_id=workspace_id, analysis_id=analysis.analysis_id)
    bound_topology = replace(bound_topology, topology_hash=topology_snapshot_hash(bound_topology))
    return domain_pack, rule_pack, bound_topology, source_topology.topology_hash


def _validate_native_bindings(
    *,
    repository: SqlitePropagationRepository,
    risk_repository: SqliteRiskRepository,
    analysis: FmeaAnalysis,
    row: FmeaRow,
    assessment: RiskAssessmentRecord,
    evidence_pack: EvidencePack,
) -> None:
    if row.analysis_id != analysis.analysis_id:
        raise ValueError("native analysis and row are not bound")  # noqa: TRY003 - native input invariant
    if row.evidence_pack_id != evidence_pack.pack_id or evidence_pack.workspace_id != assessment.workspace_id:
        raise ValueError("native row, risk, and evidence pack are not bound")  # noqa: TRY003 - native input invariant
    if assessment.row_id != row.row_id or assessment.evidence_pack_id != evidence_pack.pack_id:
        raise ValueError("native risk assessment is not bound to the reviewed row")  # noqa: TRY003 - native input invariant
    if assessment.status is not RiskStatus.CONFIRMED or row.review_status is not ReviewStatus.ACCEPTED:
        raise ValueError("propagation requires an accepted row and confirmed risk")  # noqa: TRY003 - native input invariant
    persisted_analysis = repository.get_analysis(analysis.analysis_id, evidence_pack.workspace_id)
    persisted_row = repository.get_row(row.row_id, evidence_pack.workspace_id)
    persisted_pack = repository.get_evidence_pack(evidence_pack.pack_id, evidence_pack.workspace_id)
    persisted_assessment = risk_repository.get_current_assessment(row.row_id, evidence_pack.workspace_id)
    if (
        persisted_analysis != analysis
        or persisted_row != row
        or persisted_pack != evidence_pack
        or persisted_assessment != assessment
    ):
        raise ValueError(  # noqa: TRY003 - native input invariant
            "native propagation inputs do not match the same persisted SQLite state"
        )


def _source_row_lineage(
    *,
    repository: SqlitePropagationRepository,
    request: PropagationModelRequest,
    graphs: tuple[PropagationGraphRevision, ...],
    row: FmeaRow,
    row_hash: str,
) -> list[dict[str, object]]:
    lineage = []
    for graph in graphs:
        persisted_source_ids = repository.get_graph_source_row_ids(
            graph.graph_revision_id, request.evidence_pack.workspace_id,
        )
        if tuple(source.row_id for source in request.source_rows) != persisted_source_ids:
            raise AssertionError("gateway source rows differ from persisted graph lineage")  # noqa: TRY003
        for source in request.source_rows:
            mapped_item_id = _NATIVE_ITEM_TOPOLOGY_MAPPING.get(row.item_id, row.item_id)
            if source != replace(row, item_id=mapped_item_id):
                raise AssertionError("gateway source row differs from its native mapping view")  # noqa: TRY003
            lineage.append({
                "graph_revision_id": graph.graph_revision_id,
                "run_id": request.run_id,
                "source_row_id": source.row_id,
                "record_version": source.record_version,
                "canonical_row_hash": row_hash,
            })
    return lineage


def run_propagation(
    *,
    database_path: Path,
    analysis: FmeaAnalysis,
    row: FmeaRow,
    assessment: RiskAssessmentRecord,
    evidence_pack: EvidencePack,
    registry_root: Path,
) -> PropagationRunResult:
    """Run real bounded propagation proposal, human review, and replays."""

    database_path = Path(database_path).expanduser().resolve()
    registry_root = Path(registry_root).expanduser().resolve()
    propagation_repository = SqlitePropagationRepository(database_path)
    propagation_repository.initialize()
    mapped_propagation_repository = _NativeMappedPropagationRepository(database_path)
    assistance_repository = SqliteAssistanceRepository(database_path)
    assistance_repository.initialize()
    risk_repository = SqliteRiskRepository(database_path)
    risk_repository.initialize()
    _validate_native_bindings(
        repository=propagation_repository,
        risk_repository=risk_repository,
        analysis=analysis,
        row=row,
        assessment=assessment,
        evidence_pack=evidence_pack,
    )
    source_row_hash = _hash_json(row)
    domain_pack, rule_pack, topology, source_topology_hash = _load_native_resources(
        registry_root=registry_root,
        analysis=analysis,
        workspace_id=evidence_pack.workspace_id,
    )
    domain_registry = FileDomainPackRegistry(registry_root / "domain")
    rule_registry = FilePropagationRuleRegistry(registry_root / "propagation")
    topology_port = _BoundTopologyPort(topology)
    analysis_actor = ActorContext(
        "fuel-propagation-analyst", ActorType.HUMAN, frozenset({"analyst"}), evidence_pack.workspace_id
    )
    reviewer = ActorContext(
        "fuel-propagation-reviewer",
        ActorType.HUMAN,
        frozenset({"propagation_reviewer"}),
        evidence_pack.workspace_id,
    )
    generator = _DeterministicPropagationGenerator()
    service_kwargs = {
        "assistance_repository": assistance_repository,
        "topology_port": topology_port,
        "domain_pack_registry": domain_registry,
        "propagation_rule_registry": rule_registry,
        "generator": generator,
        "risk_repository": risk_repository,
        "clock": lambda: _UTC,
    }
    analysis_service = PropagationAnalysisService(mapped_propagation_repository, **service_kwargs)
    review_service = PropagationReviewService(propagation_repository, **service_kwargs)
    start_command = StartPropagationCommand(
        analysis_id=analysis.analysis_id,
        expected_analysis_record_version=analysis.record_version,
        source_row_ids=(row.row_id,),
        evidence_pack_id=evidence_pack.pack_id,
        topology_id=_TOPOLOGY_ID,
        topology_version=_TOPOLOGY_VERSION,
        domain_pack_id=domain_pack.pack_id,
        domain_pack_version=domain_pack.version,
        rule_pack_id=rule_pack.rule_pack_id,
        rule_pack_version=rule_pack.version,
        idempotency_key="00000000-0000-4000-8000-000000000007",
        max_depth=rule_pack.max_automatic_depth,
        max_edges=40,
        require_confirmed_risk=True,
    )
    start_scope = IdempotencyScope(
        workspace_id=analysis_actor.workspace_id,
        actor_id=analysis_actor.actor_id,
        command="fmea.propagation.start",
        resource_path=f"/fmea/analyses/{analysis.analysis_id}/propagation",
        key_hash=idempotency_key_hash(start_command.idempotency_key),
    )
    start_hash = propagation_start_payload_hash(start_scope, start_command)
    start_before = _persisted_counts(database_path, propagation_repository, analysis_actor.workspace_id)
    proposed_run = analysis_service.start_analysis(start_command, analysis_actor)
    if proposed_run.graph is None or proposed_run.status.value != "succeeded":
        raise AssertionError("real propagation proposal did not persist a succeeded graph")  # noqa: TRY003
    proposed_graph = propagation_repository.get_graph(proposed_run.graph.graph_revision_id, analysis_actor.workspace_id)
    if proposed_graph is None or proposed_graph != proposed_run.graph:
        raise AssertionError("persisted propagation proposal does not match its native run")  # noqa: TRY003
    proposal_audits = _propagation_audits(database_path, analysis_actor.workspace_id)
    proposal_outbox = _propagation_outbox(
        propagation_repository, database_path, (proposed_graph.graph_revision_id,), analysis_actor.workspace_id
    )
    proposal_audit = next(event for event in proposal_audits if event.suggestion_id in proposed_graph.assistance_suggestion_ids)
    proposal_event = next(event for event in proposal_outbox if event.event_type == "propagation.proposed")
    start_after = _persisted_counts(database_path, propagation_repository, analysis_actor.workspace_id)

    start_replay_before = _persisted_counts(database_path, propagation_repository, analysis_actor.workspace_id)
    start_state_hash_before = _persisted_state_hash(database_path)
    replayed_run = analysis_service.start_analysis(start_command, analysis_actor)
    start_state_hash_after = _persisted_state_hash(database_path)
    start_replay_after = _persisted_counts(database_path, propagation_repository, analysis_actor.workspace_id)
    if start_state_hash_before != start_state_hash_after:
        raise AssertionError("propagation start replay changed persisted database state")  # noqa: TRY003

    edge_decisions = tuple(
        PropagationEdgeDecision(edge.edge_id, PropagationDecisionAction.ACCEPT, "human accepted evidence-bound edge")
        for edge in proposed_graph.edges
    )
    review_command = ConfirmPropagationCommand(
        graph_revision_id=proposed_graph.graph_revision_id,
        expected_graph_record_version=proposed_graph.record_version,
        edge_decisions=edge_decisions,
        acknowledgements=(),
        idempotency_key="00000000-0000-4000-8000-000000000008",
    )
    review_scope = IdempotencyScope(
        workspace_id=reviewer.workspace_id,
        actor_id=reviewer.actor_id,
        command="fmea.propagation.review",
        resource_path=f"/fmea/propagation-graphs/{proposed_graph.graph_revision_id}/reviews",
        key_hash=idempotency_key_hash(review_command.idempotency_key),
    )
    review_hash = propagation_review_payload_hash(review_scope, review_command, edge_decisions=edge_decisions)
    review_before = _persisted_counts(database_path, propagation_repository, reviewer.workspace_id)
    review_result = review_service.confirm_graph(review_command, reviewer)
    reviewed_graph = propagation_repository.get_graph(review_result.graph.graph_revision_id, reviewer.workspace_id)
    if reviewed_graph is None or reviewed_graph != review_result.graph:
        raise AssertionError("persisted propagation review does not match its native result")  # noqa: TRY003
    review_audits = _propagation_audits(database_path, reviewer.workspace_id)
    review_outbox = _propagation_outbox(
        propagation_repository,
        database_path,
        (proposed_graph.graph_revision_id, reviewed_graph.graph_revision_id),
        reviewer.workspace_id,
    )
    review_audit = next(event for event in review_audits if event.decision_id == review_result.decision_id)
    review_event = next(event for event in review_outbox if event.event_type == "propagation.confirmed")
    review_after = _persisted_counts(database_path, propagation_repository, reviewer.workspace_id)

    review_replay_before = _persisted_counts(database_path, propagation_repository, reviewer.workspace_id)
    review_state_hash_before = _persisted_state_hash(database_path)
    replayed_review = review_service.confirm_graph(review_command, reviewer)
    review_state_hash_after = _persisted_state_hash(database_path)
    review_replay_after = _persisted_counts(database_path, propagation_repository, reviewer.workspace_id)
    if review_state_hash_before != review_state_hash_after:
        raise AssertionError("propagation review replay changed persisted database state")  # noqa: TRY003
    persisted_row_after = propagation_repository.get_row(row.row_id, evidence_pack.workspace_id)
    if persisted_row_after != row or _hash_json(persisted_row_after) != source_row_hash:
        raise AssertionError("propagation lifecycle changed its native source row")  # noqa: TRY003
    if len(generator.requests) != 1 or generator.requests[0].run_id != proposed_run.run_id:
        raise AssertionError("propagation lineage requires the actual single gateway request")  # noqa: TRY003
    source_row_lineage = _source_row_lineage(
        repository=propagation_repository,
        request=generator.requests[0],
        graphs=(proposed_graph, reviewed_graph),
        row=row,
        row_hash=source_row_hash,
    )
    audits = _propagation_audits(database_path, reviewer.workspace_id)
    outbox = _propagation_outbox(
        propagation_repository,
        database_path,
        (proposed_graph.graph_revision_id, reviewed_graph.graph_revision_id),
        reviewer.workspace_id,
    )
    evidence: dict[str, object] = {
        "schema_version": "graphrag.fmea.propagation-lifecycle.v1",
        "case_id": "fuel-combustion",
        "source_row_lineage": source_row_lineage,
        "source_row_bindings": [{
            "row_id": row.row_id,
            "record_version": row.record_version,
            "row_hash": source_row_hash,
            "persisted_row_hash_after": _hash_json(persisted_row_after),
        }],
        "topology_snapshots": [_public(topology)],
        "source_topology_hash": source_topology_hash,
        "rule_packs": [_public(rule_pack)],
        "propagation_runs": [_public(proposed_run)],
        "propagation_graphs": [_public(proposed_graph), _public(reviewed_graph)],
        "audits": [_public(event) for event in audits],
        "outbox": [_public(event) for event in outbox],
        "steps": [
            _step(
                command="fmea.propagation.start",
                actor=analysis_actor,
                request_id=proposed_run.run_id,
                request_hash=start_hash,
                idempotency_key=start_command.idempotency_key,
                before=start_before,
                after=start_after,
                result_ids={
                    "run_id": proposed_run.run_id,
                    "graph_revision_id": proposed_graph.graph_revision_id,
                    "audit_event_id": proposal_audit.event_id,
                    "outbox_event_id": proposal_event.event_id,
                },
            ),
            _step(
                command="fmea.propagation.review",
                actor=reviewer,
                request_id=review_result.decision_id,
                request_hash=review_hash,
                idempotency_key=review_command.idempotency_key,
                before=review_before,
                after=review_after,
                result_ids={
                    "graph_revision_id": reviewed_graph.graph_revision_id,
                    "decision_id": review_result.decision_id,
                    "audit_event_id": review_audit.event_id,
                    "outbox_event_id": review_event.event_id,
                },
            ),
        ],
        "replays": [
            {
                "command": "fmea.propagation.start",
                "first": _public(proposed_run),
                "replayed": _public(replayed_run),
                "same_persisted_result": replayed_run == proposed_run,
                "state_hash_before": start_state_hash_before,
                "state_hash_after": start_state_hash_after,
                "event_counts_before": start_replay_before,
                "event_counts_after": start_replay_after,
                "propagation_records_before": start_replay_before["propagation_records"],
                "propagation_records_after": start_replay_after["propagation_records"],
            },
            {
                "command": "fmea.propagation.review",
                "first": _public(review_result),
                "replayed": _public(replayed_review),
                "same_persisted_result": _same_review_persistence(review_result, replayed_review),
                "state_hash_before": review_state_hash_before,
                "state_hash_after": review_state_hash_after,
                "event_counts_before": review_replay_before,
                "event_counts_after": review_replay_after,
                "propagation_records_before": review_replay_before["propagation_records"],
                "propagation_records_after": review_replay_after["propagation_records"],
            },
        ],
    }
    if not proposed_graph.edges:
        raise AssertionError("explicit fuel item-to-topology mapping produced no propagation edge")  # noqa: TRY003
    return PropagationRunResult(graph=reviewed_graph, evidence=evidence)


__all__ = ["PropagationRunResult", "run_propagation"]
