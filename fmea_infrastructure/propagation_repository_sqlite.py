"""Append-only SQLite persistence for propagation graph revisions."""

# Stored propagation values are decoded through the strict review JSON codec;
# no arbitrary pickle or permissive JSON values cross this repository boundary.
# ruff: noqa: TRY003, TRY004, TRY300, TRY301

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Mapping
from dataclasses import replace
from hashlib import sha256
from typing import cast

from core_domain.fmea.codec import decode_evidence_pack
from core_domain.fmea.codec import encode_json as encode_evidence_json
from core_domain.fmea.errors import FmeaDomainError
from core_domain.fmea.propagation import (
    PropagationEdge,
    PropagationEvidenceResolution,
    PropagationGraphRevision,
    PropagationPath,
    PropagationRulePack,
    TopologyInterface,
    TopologyNode,
    TopologySnapshot,
    validate_graph_revision,
    validate_propagation_rule_pack,
    validate_topology_snapshot,
)
from core_domain.fmea.states import (
    ActorType,
    ClaimStatus,
    EvidenceSupportStatus,
    PropagationStatus,
    PublicationStatus,
    ReviewStatus,
    RunStatus,
)
from core_domain.fmea.value_objects import EvidencePack
from fmea_application.propagation_service import (
    PreparedPropagationInvalidation,
    PreparedPropagationProposal,
    PreparedPropagationReview,
    PropagationAnalysisService,
    PropagationDecisionAction,
    PropagationEdgeDecision,
    PropagationReviewResult,
    PropagationRun,
    propagation_invalidation_payload_hash,
    propagation_review_payload_hash,
    propagation_start_payload_hash,
    stable_id,
)
from fmea_application.review_contracts import IdempotencyScope, encode_review_json
from fmea_application.review_errors import ReviewError
from fmea_application.risk_contracts import (
    OutboxEvent,
    assistance_suggestion_payload_hash,
    canonical_json,
    outbox_payload_hash,
)

from .assistance_repository_sqlite import SqliteAssistanceRepository
from .repository_sqlite import SqliteFmeaRepository
from .sqlite_codec import audit_event_json_matches, decode_audit_event


def _storage_error(message: str = "Propagation storage is unavailable.", *, retryable: bool = True) -> ReviewError:
    return ReviewError("FMEA_REVIEW_STORAGE_UNAVAILABLE", message, retryable=retryable)


def _conflict() -> None:
    raise ReviewError("FMEA_IDEMPOTENCY_CONFLICT", "The idempotency key already has a different payload.")


def _hash_json(payload: str) -> str:
    return "sha256:" + sha256(payload.encode("utf-8")).hexdigest()


def _strict_json(payload: object, kind: str) -> object:
    if not isinstance(payload, str):
        raise ValueError(f"persisted {kind} JSON must be text")

    def reject_constant(value: str) -> None:
        raise ValueError(f"invalid JSON constant: {value}")

    try:
        value = json.loads(
            payload,
            object_pairs_hook=lambda pairs: _unique_pairs(pairs, kind),
            parse_constant=reject_constant,
        )
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid persisted {kind} JSON") from exc
    if encode_review_json(value) != payload:
        raise ValueError(f"persisted {kind} JSON is not canonical")
    return value


def _unique_pairs(pairs: list[tuple[str, object]], kind: str) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key in persisted {kind}: {key}")
        result[key] = value
    return result


def _object(value: object, fields: set[str], kind: str) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError(f"persisted {kind} fields are invalid")
    return value


def _array(value: object, kind: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"persisted {kind} must be an array")
    return value


def _string_array(value: object, kind: str) -> tuple[str, ...]:
    values = _array(value, kind)
    if not all(isinstance(item, str) for item in values):
        raise ValueError(f"persisted {kind} must contain strings")
    return tuple(cast(str, item) for item in values)


def _encode(value: object) -> tuple[str, str]:
    payload = encode_review_json(value)
    return payload, _hash_json(payload)


def _encode_rule_pack(rule_pack: PropagationRulePack) -> tuple[str, str]:
    payload = encode_review_json(rule_pack)
    return payload, _hash_json(payload)


def _decode_rule_pack(payload: object) -> PropagationRulePack:
    data = _object(
        payload,
        {
            "rule_pack_id",
            "version",
            "applicable_analysis_types",
            "relation_types",
            "interface_variables",
            "units",
            "directions",
            "max_automatic_depth",
            "mandatory_review_conditions",
            "barrier_semantics",
            "risk_escalation",
            "prohibit_silent_fallback",
        },
        "propagation rule pack",
    )
    return PropagationRulePack(
        rule_pack_id=cast(str, data["rule_pack_id"]),
        version=cast(str, data["version"]),
        applicable_analysis_types=_string_array(data["applicable_analysis_types"], "rule applicable analysis types"),
        relation_types=_string_array(data["relation_types"], "rule relation types"),
        interface_variables=_string_array(data["interface_variables"], "rule interface variables"),
        units=_string_array(data["units"], "rule units"),
        directions=_string_array(data["directions"], "rule directions"),
        max_automatic_depth=cast(int, data["max_automatic_depth"]),
        mandatory_review_conditions=_string_array(data["mandatory_review_conditions"], "rule review conditions"),
        barrier_semantics=cast(str, data["barrier_semantics"]),
        risk_escalation=cast(str, data["risk_escalation"]),
        prohibit_silent_fallback=cast(bool, data["prohibit_silent_fallback"]),
    )


def _decode_topology_node(value: object) -> TopologyNode:
    data = _object(value, {"node_id", "node_type", "operating_modes"}, "topology node")
    return TopologyNode(
        node_id=cast(str, data["node_id"]),
        node_type=cast(str, data["node_type"]),
        operating_modes=_string_array(data["operating_modes"], "topology node operating_modes"),
    )


def _decode_topology_interface(value: object) -> TopologyInterface:
    data = _object(
        value,
        {
            "interface_id",
            "source_node_id",
            "target_node_id",
            "interface_variable",
            "unit",
            "direction",
            "operating_modes",
        },
        "topology interface",
    )
    return TopologyInterface(
        interface_id=cast(str, data["interface_id"]),
        source_node_id=cast(str, data["source_node_id"]),
        target_node_id=cast(str, data["target_node_id"]),
        interface_variable=cast(str, data["interface_variable"]),
        unit=cast(str, data["unit"]),
        direction=cast(str, data["direction"]),
        operating_modes=_string_array(data["operating_modes"], "topology interface operating_modes"),
    )


def _decode_topology(payload: object) -> TopologySnapshot:
    data = _object(
        payload,
        {
            "topology_snapshot_id",
            "workspace_id",
            "analysis_id",
            "topology_hash",
            "nodes",
            "interfaces",
            "record_version",
            "created_at",
        },
        "topology snapshot",
    )
    topology = TopologySnapshot(
        topology_snapshot_id=cast(str, data["topology_snapshot_id"]),
        workspace_id=cast(str, data["workspace_id"]),
        analysis_id=None if data["analysis_id"] is None else cast(str, data["analysis_id"]),
        topology_hash=cast(str, data["topology_hash"]),
        nodes=tuple(_decode_topology_node(item) for item in _array(data["nodes"], "topology nodes")),
        interfaces=tuple(
            _decode_topology_interface(item) for item in _array(data["interfaces"], "topology interfaces")
        ),
        record_version=cast(int, data["record_version"]),
        created_at=cast(str, data["created_at"]),
    )
    validate_topology_snapshot(topology)
    return topology


_EDGE_FIELDS = {
    "edge_id",
    "analysis_id",
    "source_entity_id",
    "target_entity_id",
    "relation_type",
    "interface_variable",
    "unit",
    "direction",
    "threshold",
    "operating_modes",
    "delay_ms",
    "response_time_ms",
    "fault_tolerance_time_ms",
    "barrier_ids",
    "evidence_pack_id",
    "evidence_ids",
    "evidence_support",
    "claim_status",
    "review_status",
    "publication_status",
    "path_length",
    "is_cyclic",
    "is_unprocessed",
    "is_external",
    "is_terminal",
    "risk_priority",
    "record_version",
}


def _decode_edge(value: object) -> PropagationEdge:
    data = _object(value, _EDGE_FIELDS, "propagation edge")
    return PropagationEdge(
        edge_id=cast(str, data["edge_id"]),
        analysis_id=cast(str, data["analysis_id"]),
        source_entity_id=cast(str, data["source_entity_id"]),
        target_entity_id=cast(str, data["target_entity_id"]),
        relation_type=cast(str, data["relation_type"]),
        interface_variable=cast(str, data["interface_variable"]),
        unit=cast(str, data["unit"]),
        direction=cast(str, data["direction"]),
        threshold=None if data["threshold"] is None else cast(str, data["threshold"]),
        operating_modes=_string_array(data["operating_modes"], "edge operating_modes"),
        delay_ms=None if data["delay_ms"] is None else cast(int, data["delay_ms"]),
        response_time_ms=None if data["response_time_ms"] is None else cast(int, data["response_time_ms"]),
        fault_tolerance_time_ms=None
        if data["fault_tolerance_time_ms"] is None
        else cast(int, data["fault_tolerance_time_ms"]),
        barrier_ids=_string_array(data["barrier_ids"], "edge barrier_ids"),
        evidence_pack_id=cast(str, data["evidence_pack_id"]),
        evidence_ids=_string_array(data["evidence_ids"], "edge evidence_ids"),
        evidence_support=EvidenceSupportStatus(cast(str, data["evidence_support"])),
        claim_status=ClaimStatus(cast(str, data["claim_status"])),
        review_status=ReviewStatus(cast(str, data["review_status"])),
        publication_status=PublicationStatus(cast(str, data["publication_status"])),
        path_length=cast(int, data["path_length"]),
        is_cyclic=cast(bool, data["is_cyclic"]),
        is_unprocessed=cast(bool, data["is_unprocessed"]),
        is_external=cast(bool, data["is_external"]),
        is_terminal=cast(bool, data["is_terminal"]),
        risk_priority=None if data["risk_priority"] is None else cast(str, data["risk_priority"]),
        record_version=cast(int, data["record_version"]),
    )


def _decode_path(value: object) -> PropagationPath:
    data = _object(
        value,
        {
            "path_id",
            "analysis_id",
            "source_entity_id",
            "target_entity_id",
            "edges",
            "path_length",
            "is_cyclic",
            "requires_human_review",
        },
        "propagation path",
    )
    return PropagationPath(
        path_id=cast(str, data["path_id"]),
        analysis_id=cast(str, data["analysis_id"]),
        source_entity_id=cast(str, data["source_entity_id"]),
        target_entity_id=cast(str, data["target_entity_id"]),
        edges=tuple(_decode_edge(item) for item in _array(data["edges"], "path edges")),
        path_length=cast(int, data["path_length"]),
        is_cyclic=cast(bool, data["is_cyclic"]),
        requires_human_review=cast(bool, data["requires_human_review"]),
    )


_GRAPH_FIELDS = {
    "graph_revision_id",
    "workspace_id",
    "analysis_id",
    "analysis_record_version",
    "topology_snapshot_id",
    "topology_hash",
    "evidence_pack_ids",
    "domain_pack_id",
    "domain_pack_version",
    "rule_pack_id",
    "rule_pack_version",
    "status",
    "assistance_suggestion_ids",
    "nodes",
    "edges",
    "paths",
    "unresolved_issue_codes",
    "parent_graph_revision_id",
    "record_version",
    "created_at",
}


def _decode_graph(value: object) -> PropagationGraphRevision:
    data = _object(value, _GRAPH_FIELDS, "propagation graph")
    return PropagationGraphRevision(
        graph_revision_id=cast(str, data["graph_revision_id"]),
        workspace_id=cast(str, data["workspace_id"]),
        analysis_id=cast(str, data["analysis_id"]),
        analysis_record_version=cast(int, data["analysis_record_version"]),
        topology_snapshot_id=cast(str, data["topology_snapshot_id"]),
        topology_hash=cast(str, data["topology_hash"]),
        evidence_pack_ids=_string_array(data["evidence_pack_ids"], "graph evidence_pack_ids"),
        domain_pack_id=cast(str, data["domain_pack_id"]),
        domain_pack_version=cast(str, data["domain_pack_version"]),
        rule_pack_id=cast(str, data["rule_pack_id"]),
        rule_pack_version=cast(str, data["rule_pack_version"]),
        status=PropagationStatus(cast(str, data["status"])),
        assistance_suggestion_ids=_string_array(data["assistance_suggestion_ids"], "graph assistance_suggestion_ids"),
        nodes=tuple(_decode_topology_node(item) for item in _array(data["nodes"], "graph nodes")),
        edges=tuple(_decode_edge(item) for item in _array(data["edges"], "graph edges")),
        paths=tuple(_decode_path(item) for item in _array(data["paths"], "graph paths")),
        unresolved_issue_codes=_string_array(data["unresolved_issue_codes"], "graph unresolved_issue_codes"),
        parent_graph_revision_id=(
            None if data["parent_graph_revision_id"] is None else cast(str, data["parent_graph_revision_id"])
        ),
        record_version=cast(int, data["record_version"]),
        created_at=cast(str, data["created_at"]),
    )


class SqlitePropagationRepository(SqliteFmeaRepository):
    """Workspace-scoped, immutable propagation graph persistence."""

    def get_analysis(self, analysis_id: str, workspace_id: str):
        workspace = self._workspace(workspace_id)
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT a.* FROM fmea_analyses AS a "
                "JOIN fmea_rows AS r ON r.analysis_id = a.analysis_id "
                "WHERE a.analysis_id = ? AND r.workspace_id = ? "
                "AND r.workspace_id = ? LIMIT 1",
                (analysis_id, workspace, workspace),
            ).fetchone()
            return None if row is None else self._decode_analysis_record(row)
        finally:
            connection.close()

    @staticmethod
    def _decode_topology_row(row: sqlite3.Row) -> TopologySnapshot:
        snapshot_json = cast(str, row["snapshot_json"])
        topology = cast(TopologySnapshot, _decode_topology(_strict_json(snapshot_json, "topology snapshot")))
        if (
            encode_review_json(topology) != snapshot_json
            or topology.workspace_id != row["workspace_id"]
            or topology.topology_snapshot_id != row["topology_snapshot_id"]
            or topology.analysis_id != row["analysis_id"]
            or topology.topology_hash != row["topology_hash"]
            or topology.record_version != row["record_version"]
            or topology.created_at != row["created_at"]
            or _hash_json(cast(str, row["snapshot_json"])) != row["snapshot_hash"]
        ):
            raise ValueError("persisted topology snapshot identity or hash does not match")
        return topology

    @staticmethod
    def _decode_graph_row(  # noqa: C901
        connection: sqlite3.Connection, row: sqlite3.Row, workspace_id: str
    ) -> PropagationGraphRevision:
        graph_json = cast(str, row["graph_json"])
        graph = _decode_graph(_strict_json(graph_json, "propagation graph"))
        if (
            encode_review_json(graph) != graph_json
            or graph.workspace_id != workspace_id
            or graph.graph_revision_id != row["graph_revision_id"]
            or graph.analysis_id != row["analysis_id"]
            or graph.analysis_record_version != row["analysis_record_version"]
            or graph.topology_snapshot_id != row["topology_snapshot_id"]
            or graph.topology_hash != row["topology_hash"]
            or graph.evidence_pack_ids
            != _string_array(
                _strict_json(row["evidence_pack_ids_json"], "graph evidence_pack_ids"), "graph evidence_pack_ids"
            )
            or graph.domain_pack_id != row["domain_pack_id"]
            or graph.domain_pack_version != row["domain_pack_version"]
            or graph.rule_pack_id != row["rule_pack_id"]
            or graph.rule_pack_version != row["rule_pack_version"]
            or graph.status.value != row["status"]
            or graph.assistance_suggestion_ids
            != _string_array(
                _strict_json(row["assistance_suggestion_ids_json"], "graph assistance_suggestion_ids"),
                "graph assistance_suggestion_ids",
            )
            or graph.created_at != row["created_at"]
            or graph.parent_graph_revision_id != row["parent_graph_revision_id"]
            or graph.record_version != row["record_version"]
            or _hash_json(cast(str, row["graph_json"])) != row["graph_hash"]
        ):
            raise ValueError("persisted propagation graph identity or hash does not match")

        source_row_ids = _string_array(
            _strict_json(row["source_row_ids_json"], "graph source row IDs"), "graph source row IDs"
        )
        if not source_row_ids or len(source_row_ids) != len(set(source_row_ids)):
            raise ValueError("persisted graph source row IDs are invalid")
        for source_row_id in source_row_ids:
            source = connection.execute(
                "SELECT analysis_id FROM fmea_rows WHERE row_id = ? AND workspace_id = ?",
                (source_row_id, workspace_id),
            ).fetchone()
            if source is None or source["analysis_id"] != graph.analysis_id:
                raise ValueError("persisted graph source row binding is invalid")

        edge_rows = connection.execute(
            "SELECT edge_order, edge_id, edge_hash, edge_json FROM fmea_propagation_edges "
            "WHERE workspace_id = ? AND graph_revision_id = ? ORDER BY edge_order, edge_id",
            (workspace_id, graph.graph_revision_id),
        ).fetchall()
        edges: list[PropagationEdge] = []
        for edge_row in edge_rows:
            edge_json = cast(str, edge_row["edge_json"])
            edge = _decode_edge(_strict_json(edge_json, "propagation edge"))
            if (
                encode_review_json(edge) != edge_json
                or edge.edge_id != edge_row["edge_id"]
                or _hash_json(cast(str, edge_row["edge_json"])) != edge_row["edge_hash"]
            ):
                raise ValueError("persisted propagation edge identity or hash does not match")
            edges.append(edge)

        path_rows = connection.execute(
            "SELECT path_order, path_id, path_hash, path_json FROM fmea_propagation_paths "
            "WHERE workspace_id = ? AND graph_revision_id = ? ORDER BY path_order, path_id",
            (workspace_id, graph.graph_revision_id),
        ).fetchall()
        paths: list[PropagationPath] = []
        for path_row in path_rows:
            path_json = cast(str, path_row["path_json"])
            path = _decode_path(_strict_json(path_json, "propagation path"))
            if (
                encode_review_json(path) != path_json
                or path.path_id != path_row["path_id"]
                or _hash_json(cast(str, path_row["path_json"])) != path_row["path_hash"]
            ):
                raise ValueError("persisted propagation path identity or hash does not match")
            paths.append(path)

        if tuple(edges) != graph.edges or tuple(paths) != graph.paths:
            raise ValueError("persisted propagation graph ordering or child rows do not match")

        issues = connection.execute(
            "SELECT issue_code, issue_json FROM fmea_propagation_issues "
            "WHERE workspace_id = ? AND graph_revision_id = ? ORDER BY issue_id",
            (workspace_id, graph.graph_revision_id),
        ).fetchall()
        issue_codes: list[str] = []
        for issue in issues:
            issue_json = cast(str, issue["issue_json"])
            data = _object(_strict_json(issue_json, "propagation issue"), {"issue_code"}, "propagation issue")
            if encode_review_json(data) != issue_json or data["issue_code"] != issue["issue_code"]:
                raise ValueError("persisted propagation issue identity does not match")
            issue_codes.append(cast(str, data["issue_code"]))
        if tuple(sorted(issue_codes)) != tuple(sorted(graph.unresolved_issue_codes)):
            raise ValueError("persisted propagation issues do not match graph")
        return graph

    def _graph_row(
        self, connection: sqlite3.Connection, graph_revision_id: str, workspace_id: str
    ) -> sqlite3.Row | None:
        return connection.execute(
            "SELECT * FROM fmea_propagation_graph_revisions WHERE graph_revision_id = ? AND workspace_id = ?",
            (graph_revision_id, workspace_id),
        ).fetchone()

    def get_graph_revision(self, graph_revision_id: str, workspace_id: str) -> PropagationGraphRevision | None:
        workspace = self._workspace(workspace_id)
        connection = self._connect()
        try:
            row = self._graph_row(connection, graph_revision_id, workspace)
            return None if row is None else self._decode_graph_row(connection, row, workspace)
        except ReviewError:
            raise
        except Exception as exc:
            raise _storage_error() from exc
        finally:
            connection.close()

    def get_graph(self, graph_revision_id: str, workspace_id: str) -> PropagationGraphRevision | None:
        workspace = self._workspace(workspace_id)
        connection = self._connect()
        try:
            row = self._graph_row(connection, graph_revision_id, workspace)
            return None if row is None else self._decode_graph_row(connection, row, workspace)
        except ReviewError:
            raise
        except Exception as exc:
            raise _storage_error() from exc
        finally:
            connection.close()

    def get_current_graph(self, analysis_id: str, workspace_id: str) -> PropagationGraphRevision | None:
        workspace = self._workspace(workspace_id)
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM fmea_propagation_graph_revisions "
                "WHERE workspace_id = ? AND analysis_id = ? "
                "ORDER BY record_version DESC, graph_revision_id DESC LIMIT 1",
                (workspace, analysis_id),
            ).fetchone()
            return None if row is None else self._decode_graph_row(connection, row, workspace)
        except ReviewError:
            raise
        except Exception as exc:
            raise _storage_error() from exc
        finally:
            connection.close()

    def get_topology_snapshot(self, topology_snapshot_id: str, workspace_id: str) -> TopologySnapshot | None:
        workspace = self._workspace(workspace_id)
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM fmea_propagation_topology_snapshots WHERE topology_snapshot_id = ? AND workspace_id = ?",
                (topology_snapshot_id, workspace),
            ).fetchone()
            return None if row is None else self._decode_topology_row(row)
        except ReviewError:
            raise
        except Exception as exc:
            raise _storage_error() from exc
        finally:
            connection.close()

    def get_graph_source_row_ids(self, graph_revision_id: str, workspace_id: str) -> tuple[str, ...]:
        workspace = self._workspace(workspace_id)
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT source_row_ids_json FROM fmea_propagation_graph_revisions "
                "WHERE graph_revision_id = ? AND workspace_id = ?",
                (graph_revision_id, workspace),
            ).fetchone()
            if row is None:
                return ()
            values = _string_array(
                _strict_json(cast(str, row["source_row_ids_json"]), "graph source row IDs"), "graph source row IDs"
            )
            if not values or len(values) != len(set(values)):
                raise ValueError("persisted graph source row IDs are invalid")
            for row_id in values:
                source = connection.execute(
                    "SELECT row_id FROM fmea_rows WHERE row_id = ? AND workspace_id = ?",
                    (row_id, workspace),
                ).fetchone()
                if source is None:
                    raise ValueError("persisted graph source row is outside workspace")
            return values
        except ReviewError:
            raise
        except Exception as exc:
            raise _storage_error() from exc
        finally:
            connection.close()

    @staticmethod
    def _idempotency_row(connection: sqlite3.Connection, scope: IdempotencyScope) -> sqlite3.Row | None:
        # scope_key is the existing canonical compound key; workspace binding is
        # rechecked by every caller and by the response/audit rows below.
        return connection.execute(
            "SELECT payload_hash, state, status_code, resource_id, response_json, completed_at "
            "FROM idempotency_records WHERE scope_key = ?",
            (scope.scope_key,),
        ).fetchone()

    @classmethod
    def _reserve(
        cls, connection: sqlite3.Connection, scope: IdempotencyScope, payload_hash: str, created_at: str
    ) -> None:
        connection.execute(
            "INSERT INTO idempotency_records "
            "(scope_key, payload_hash, state, status_code, resource_id, response_json, created_at, completed_at) "
            "VALUES (?, ?, 'reserved', NULL, NULL, NULL, ?, NULL)",
            (scope.scope_key, payload_hash, created_at),
        )

    @classmethod
    def _complete(
        cls,
        connection: sqlite3.Connection,
        scope: IdempotencyScope,
        payload_hash: str,
        response: Mapping[str, object],
        resource_id: str,
        completed_at: str,
    ) -> None:
        cursor = connection.execute(
            "UPDATE idempotency_records SET state='completed', status_code=201, resource_id=?, response_json=?, "
            "completed_at=? WHERE scope_key=? AND payload_hash=? AND state='reserved'",
            (resource_id, canonical_json(response), completed_at, scope.scope_key, payload_hash),
        )
        if cursor.rowcount != 1:
            raise _storage_error("Propagation idempotency reservation could not be completed.")

    def _run_from_row(self, connection: sqlite3.Connection, row: sqlite3.Row, workspace_id: str) -> PropagationRun:
        graph = None
        if row["graph_revision_id"] is not None:
            graph_row = self._graph_row(connection, cast(str, row["graph_revision_id"]), workspace_id)
            if graph_row is None:
                raise _storage_error()
            graph = self._decode_graph_row(connection, graph_row, workspace_id)
        suggestions = _string_array(
            _strict_json(row["assistance_suggestion_ids_json"], "propagation run suggestions"),
            "propagation run suggestions",
        )
        if not suggestions or graph is None or tuple(graph.assistance_suggestion_ids) != suggestions:
            raise _storage_error()
        return PropagationRun(
            run_id=row["run_id"],
            workspace_id=row["workspace_id"],
            analysis_id=row["analysis_id"],
            status=RunStatus(row["status"]),
            graph=graph,
            error_code=row["error_code"],
            error_message=row["error_message"],
            assistance_suggestion_ids=suggestions,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            record_version=row["record_version"],
        )

    @staticmethod
    def _decode_start_response(row: sqlite3.Row, payload_hash: str) -> Mapping[str, object] | None:
        if row is None:
            return None
        if row["payload_hash"] != payload_hash:
            _conflict()
        if row["state"] != "completed" or row["status_code"] != 201 or row["response_json"] is None:
            raise _storage_error()
        response = _strict_json(row["response_json"], "propagation start idempotency response")
        expected = {
            "workspace_id",
            "resource_type",
            "run_id",
            "graph_revision_id",
            "suggestion_id",
            "audit_event_id",
            "outbox_event_id",
        }
        if (
            not isinstance(response, dict)
            or set(response) != expected
            or response["resource_type"] != "propagation_run"
        ):
            raise _storage_error()
        if response["run_id"] != row["resource_id"]:
            raise _storage_error()
        return response

    @staticmethod
    def _decode_response(row: sqlite3.Row, payload_hash: str, resource_type: str) -> Mapping[str, object] | None:
        if row is None:
            return None
        if row["payload_hash"] != payload_hash:
            _conflict()
        if row["state"] != "completed" or row["status_code"] != 201 or row["response_json"] is None:
            raise _storage_error()
        response = _strict_json(row["response_json"], "propagation idempotency response")
        expected = {
            "workspace_id",
            "resource_type",
            "graph_revision_id",
            "decision_id",
            "audit_event_id",
            "outbox_event_id",
        }
        if not isinstance(response, dict) or set(response) != expected or response["resource_type"] != resource_type:
            raise _storage_error()
        if response["graph_revision_id"] != row["resource_id"]:
            raise _storage_error()
        return response

    @staticmethod
    def _decode_outbox(connection: sqlite3.Connection, event_id: str, workspace_id: str) -> OutboxEvent:
        row = connection.execute(
            "SELECT event_id, workspace_id, aggregate_type, aggregate_id, event_type, status, payload_json, "
            "payload_hash, idempotency_scope, created_at FROM fmea_outbox_events "
            "WHERE event_id = ? AND workspace_id = ?",
            (event_id, workspace_id),
        ).fetchone()
        if row is None or row["status"] != "pending":
            raise _storage_error()
        payload = _strict_json(row["payload_json"], "propagation outbox payload")
        if not isinstance(payload, dict) or canonical_json(payload) != row["payload_json"]:
            raise _storage_error()
        try:
            event = OutboxEvent(
                event_id=row["event_id"],
                workspace_id=row["workspace_id"],
                aggregate_type=row["aggregate_type"],
                aggregate_id=row["aggregate_id"],
                event_type=row["event_type"],
                payload=payload,
                payload_hash=row["payload_hash"],
                created_at=row["created_at"],
                scope_key=row["idempotency_scope"],
            )
        except (TypeError, ValueError) as exc:
            raise _storage_error() from exc
        return event

    def _insert_outbox(self, connection: sqlite3.Connection, event: OutboxEvent) -> None:
        if event.aggregate_type != "propagation_graph" or event.workspace_id.strip() == "":
            raise _storage_error("Propagation outbox binding is invalid.", retryable=False)
        connection.execute(
            "INSERT INTO fmea_outbox_events "
            "(event_id, workspace_id, aggregate_type, aggregate_id, event_type, status, payload_json, payload_hash, idempotency_scope, created_at) "
            "VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?)",
            (
                event.event_id,
                event.workspace_id,
                event.aggregate_type,
                event.aggregate_id,
                event.event_type,
                canonical_json(event.payload),
                event.payload_hash,
                event.scope_key,
                event.created_at,
            ),
        )

    @staticmethod
    def _insert_topology(connection: sqlite3.Connection, topology: TopologySnapshot) -> None:
        snapshot_json, snapshot_hash = _encode(topology)
        existing = connection.execute(
            "SELECT snapshot_hash, snapshot_json FROM fmea_propagation_topology_snapshots "
            "WHERE workspace_id = ? AND topology_snapshot_id = ?",
            (topology.workspace_id, topology.topology_snapshot_id),
        ).fetchone()
        if existing is not None:
            if existing["snapshot_hash"] != snapshot_hash or existing["snapshot_json"] != snapshot_json:
                raise ReviewError(
                    "FMEA_REVIEW_ACTION_INVALID", "Topology snapshot identity is already bound to different data."
                )
            return
        connection.execute(
            "INSERT INTO fmea_propagation_topology_snapshots "
            "(workspace_id, topology_snapshot_id, analysis_id, topology_hash, record_version, snapshot_hash, snapshot_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                topology.workspace_id,
                topology.topology_snapshot_id,
                topology.analysis_id,
                topology.topology_hash,
                topology.record_version,
                snapshot_hash,
                snapshot_json,
                topology.created_at,
            ),
        )

    @staticmethod
    def _insert_evidence_snapshot(connection: sqlite3.Connection, pack: EvidencePack) -> None:
        payload = encode_evidence_json(pack)
        decoded = decode_evidence_pack(payload)
        if decoded != pack:
            raise ReviewError("FMEA_REVIEW_ACTION_INVALID", "Evidence snapshot does not round-trip canonically.")
        snapshot_hash = _hash_json(payload)
        existing = connection.execute(
            "SELECT pack_hash, pack_json, snapshot_hash FROM fmea_propagation_evidence_snapshots "
            "WHERE workspace_id = ? AND pack_id = ?",
            (pack.workspace_id, pack.pack_id),
        ).fetchone()
        if existing is not None:
            if (
                existing["pack_hash"] != pack.pack_hash
                or existing["pack_json"] != payload
                or existing["snapshot_hash"] != snapshot_hash
            ):
                raise ReviewError(
                    "FMEA_REVIEW_ACTION_INVALID", "Evidence snapshot identity is already bound differently."
                )
            return
        connection.execute(
            "INSERT INTO fmea_propagation_evidence_snapshots "
            "(workspace_id, pack_id, pack_hash, pack_json, snapshot_hash, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (pack.workspace_id, pack.pack_id, pack.pack_hash, payload, snapshot_hash, pack.created_at),
        )

    @staticmethod
    def _insert_rule_snapshot(
        connection: sqlite3.Connection, rule_pack: PropagationRulePack, workspace_id: str, created_at: str
    ) -> None:
        payload, rule_hash = _encode_rule_pack(rule_pack)
        decoded = _decode_rule_pack(_strict_json(payload, "propagation rule pack"))
        if decoded != rule_pack:
            raise ReviewError("FMEA_REVIEW_ACTION_INVALID", "Rule snapshot does not round-trip canonically.")
        existing = connection.execute(
            "SELECT rule_hash, rule_json FROM fmea_propagation_rule_snapshots "
            "WHERE workspace_id = ? AND rule_pack_id = ? AND rule_pack_version = ?",
            (workspace_id, rule_pack.rule_pack_id, rule_pack.version),
        ).fetchone()
        if existing is not None:
            if existing["rule_hash"] != rule_hash or existing["rule_json"] != payload:
                raise ReviewError("FMEA_REVIEW_ACTION_INVALID", "Rule snapshot identity is already bound differently.")
            return
        connection.execute(
            "INSERT INTO fmea_propagation_rule_snapshots "
            "(workspace_id, rule_pack_id, rule_pack_version, rule_hash, rule_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (workspace_id, rule_pack.rule_pack_id, rule_pack.version, rule_hash, payload, created_at),
        )

    @classmethod
    def _validate_snapshots(
        cls,
        connection: sqlite3.Connection,
        workspace_id: str,
        graph: PropagationGraphRevision,
        rule_pack: PropagationRulePack,
        evidence_packs: tuple[EvidencePack, ...],
    ) -> None:
        rule_row = connection.execute(
            "SELECT rule_hash, rule_json FROM fmea_propagation_rule_snapshots "
            "WHERE workspace_id = ? AND rule_pack_id = ? AND rule_pack_version = ?",
            (workspace_id, graph.rule_pack_id, graph.rule_pack_version),
        ).fetchone()
        if rule_row is None:
            raise ReviewError("FMEA_REVIEW_ACTION_INVALID", "Propagation rule snapshot is missing.")
        rule_json = cast(str, rule_row["rule_json"])
        if rule_row["rule_hash"] != _hash_json(rule_json):
            raise ReviewError("FMEA_REVIEW_ACTION_INVALID", "Propagation rule snapshot hash is invalid.")
        stored_rule = _decode_rule_pack(_strict_json(rule_json, "propagation rule pack"))
        if (
            stored_rule != rule_pack
            or stored_rule.rule_pack_id != graph.rule_pack_id
            or stored_rule.version != graph.rule_pack_version
        ):
            raise ReviewError("FMEA_REVIEW_ACTION_INVALID", "Propagation rule snapshot does not match the graph.")
        if tuple(pack.pack_id for pack in evidence_packs) != graph.evidence_pack_ids:
            raise ReviewError("FMEA_REVIEW_ACTION_INVALID", "Propagation evidence snapshot binding is invalid.")
        for pack in evidence_packs:
            row = connection.execute(
                "SELECT pack_hash, pack_json, snapshot_hash FROM fmea_propagation_evidence_snapshots "
                "WHERE workspace_id = ? AND pack_id = ?",
                (workspace_id, pack.pack_id),
            ).fetchone()
            if row is None or pack.workspace_id != workspace_id or row["pack_hash"] != pack.pack_hash:
                raise ReviewError("FMEA_REVIEW_ACTION_INVALID", "Propagation evidence snapshot is missing or drifted.")
            pack_json = cast(str, row["pack_json"])
            if row["snapshot_hash"] != _hash_json(pack_json):
                raise ReviewError("FMEA_REVIEW_ACTION_INVALID", "Propagation evidence snapshot hash is invalid.")
            try:
                stored_pack = decode_evidence_pack(pack_json)
            except Exception as exc:
                raise ReviewError("FMEA_REVIEW_ACTION_INVALID", "Propagation evidence snapshot is invalid.") from exc
            if encode_evidence_json(stored_pack) != pack_json or stored_pack != pack:
                raise ReviewError(
                    "FMEA_REVIEW_ACTION_INVALID", "Propagation evidence snapshot does not match the graph."
                )

    @classmethod
    def _validate_persisted_bindings(
        cls, connection: sqlite3.Connection, workspace_id: str, graph: PropagationGraphRevision
    ) -> None:
        topology_row = connection.execute(
            "SELECT topology_hash, snapshot_hash, snapshot_json FROM fmea_propagation_topology_snapshots "
            "WHERE workspace_id = ? AND topology_snapshot_id = ?",
            (workspace_id, graph.topology_snapshot_id),
        ).fetchone()
        if topology_row is None or topology_row["topology_hash"] != graph.topology_hash:
            raise _storage_error()
        topology_json = cast(str, topology_row["snapshot_json"])
        if topology_row["snapshot_hash"] != _hash_json(topology_json):
            raise _storage_error()
        topology = _decode_topology(_strict_json(topology_json, "topology snapshot"))
        if (
            topology.workspace_id != workspace_id
            or topology.topology_snapshot_id != graph.topology_snapshot_id
            or topology.analysis_id != graph.analysis_id
            or topology.topology_hash != graph.topology_hash
        ):
            raise _storage_error()
        evidence: list[EvidencePack] = []
        for pack_id in graph.evidence_pack_ids:
            row = connection.execute(
                "SELECT pack_hash, pack_json, snapshot_hash FROM fmea_propagation_evidence_snapshots "
                "WHERE workspace_id = ? AND pack_id = ?",
                (workspace_id, pack_id),
            ).fetchone()
            if row is None or row["snapshot_hash"] != _hash_json(cast(str, row["pack_json"])):
                raise _storage_error()
            pack_json = cast(str, row["pack_json"])
            try:
                pack = decode_evidence_pack(pack_json)
            except Exception as exc:
                raise _storage_error() from exc
            if (
                pack.workspace_id != workspace_id
                or pack.pack_id != pack_id
                or encode_evidence_json(pack) != pack_json
                or pack.pack_hash != row["pack_hash"]
            ):
                raise _storage_error()
            evidence.append(pack)
        rule_row = connection.execute(
            "SELECT rule_hash, rule_json FROM fmea_propagation_rule_snapshots "
            "WHERE workspace_id = ? AND rule_pack_id = ? AND rule_pack_version = ?",
            (workspace_id, graph.rule_pack_id, graph.rule_pack_version),
        ).fetchone()
        if rule_row is None or rule_row["rule_hash"] != _hash_json(cast(str, rule_row["rule_json"])):
            raise _storage_error()
        rule = _decode_rule_pack(_strict_json(rule_row["rule_json"], "propagation rule pack"))
        if rule.rule_pack_id != graph.rule_pack_id or rule.version != graph.rule_pack_version:
            raise _storage_error()
        cls._validate_snapshots(connection, workspace_id, graph, rule, tuple(evidence))
        cls._validate_source_rows(
            connection,
            workspace_id,
            graph.analysis_id,
            _string_array(
                _strict_json(
                    connection.execute(
                        "SELECT source_row_ids_json FROM fmea_propagation_graph_revisions "
                        "WHERE workspace_id = ? AND graph_revision_id = ?",
                        (workspace_id, graph.graph_revision_id),
                    ).fetchone()["source_row_ids_json"],
                    "graph source row IDs",
                ),
                "graph source row IDs",
            ),
        )

    @classmethod
    def _insert_graph(
        cls,
        connection: sqlite3.Connection,
        graph: PropagationGraphRevision,
        source_row_ids: tuple[str, ...],
    ) -> None:
        graph_json, graph_hash = _encode(graph)
        connection.execute(
            "INSERT INTO fmea_propagation_graph_revisions "
            "(workspace_id, graph_revision_id, analysis_id, analysis_record_version, topology_snapshot_id, topology_hash, "
            "evidence_pack_ids_json, domain_pack_id, domain_pack_version, rule_pack_id, rule_pack_version, status, "
            "assistance_suggestion_ids_json, source_row_ids_json, unresolved_issue_codes_json, parent_graph_revision_id, "
            "record_version, graph_hash, graph_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                graph.workspace_id,
                graph.graph_revision_id,
                graph.analysis_id,
                graph.analysis_record_version,
                graph.topology_snapshot_id,
                graph.topology_hash,
                encode_review_json(graph.evidence_pack_ids),
                graph.domain_pack_id,
                graph.domain_pack_version,
                graph.rule_pack_id,
                graph.rule_pack_version,
                graph.status.value,
                encode_review_json(graph.assistance_suggestion_ids),
                encode_review_json(source_row_ids),
                encode_review_json(graph.unresolved_issue_codes),
                graph.parent_graph_revision_id,
                graph.record_version,
                graph_hash,
                graph_json,
                graph.created_at,
            ),
        )
        for order, edge in enumerate(graph.edges):
            edge_json, edge_hash = _encode(edge)
            connection.execute(
                "INSERT INTO fmea_propagation_edges "
                "(workspace_id, graph_revision_id, edge_id, edge_order, edge_hash, edge_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    graph.workspace_id,
                    graph.graph_revision_id,
                    edge.edge_id,
                    order,
                    edge_hash,
                    edge_json,
                    graph.created_at,
                ),
            )
        for order, path in enumerate(graph.paths):
            path_json, path_hash = _encode(path)
            connection.execute(
                "INSERT INTO fmea_propagation_paths "
                "(workspace_id, graph_revision_id, path_id, path_order, path_hash, path_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    graph.workspace_id,
                    graph.graph_revision_id,
                    path.path_id,
                    order,
                    path_hash,
                    path_json,
                    graph.created_at,
                ),
            )
        for issue_code in sorted(graph.unresolved_issue_codes):
            issue_id = f"{graph.graph_revision_id}:{issue_code}"
            issue_json = encode_review_json({"issue_code": issue_code})
            connection.execute(
                "INSERT INTO fmea_propagation_issues "
                "(workspace_id, graph_revision_id, issue_id, issue_code, issue_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (graph.workspace_id, graph.graph_revision_id, issue_id, issue_code, issue_json, graph.created_at),
            )

    @staticmethod
    def _validate_source_rows(
        connection: sqlite3.Connection, workspace_id: str, analysis_id: str, source_row_ids: tuple[str, ...]
    ) -> None:
        if not source_row_ids or len(source_row_ids) != len(set(source_row_ids)):
            raise ReviewError("FMEA_REVIEW_ACTION_INVALID", "Propagation source row binding is invalid.")
        for row_id in source_row_ids:
            row = connection.execute(
                "SELECT analysis_id FROM fmea_rows WHERE row_id = ? AND workspace_id = ?",
                (row_id, workspace_id),
            ).fetchone()
            if row is None or row["analysis_id"] != analysis_id:
                raise ReviewError("FMEA_REVIEW_ACTION_INVALID", "Propagation source row binding is invalid.")

    @classmethod
    def _expected_confirmed_child(
        cls,
        parent: PropagationGraphRevision,
        prepared: PreparedPropagationReview,
    ) -> PropagationGraphRevision:
        decisions = {item.edge_id: item for item in prepared.edge_decisions}
        if set(decisions) != {edge.edge_id for edge in parent.edges}:
            raise ReviewError("FMEA_REVIEW_ACTION_INVALID", "Propagation edge decision coverage is invalid.")
        accepted = tuple(
            replace(edge, review_status=ReviewStatus.ACCEPTED)
            for edge in parent.edges
            if decisions[edge.edge_id].action is PropagationDecisionAction.ACCEPT
        )
        retained_issues = {issue for edge in accepted for issue in PropagationAnalysisService._review_issue_codes(edge)}
        if set(prepared.command.acknowledgements) != retained_issues:
            raise ReviewError(
                "FMEA_REVIEW_ACTION_INVALID", "Propagation acknowledgements do not match retained issues."
            )
        return replace(
            parent,
            graph_revision_id=stable_id("propagation-confirmed-graph", prepared.scope.scope_key),
            status=PropagationStatus.CONFIRMED,
            edges=accepted,
            paths=PropagationAnalysisService._paths(accepted, parent.analysis_id),
            unresolved_issue_codes=tuple(sorted(retained_issues)),
            parent_graph_revision_id=parent.graph_revision_id,
            record_version=parent.record_version + 1,
            created_at=prepared.graph.created_at,
        )

    @staticmethod
    def _expected_invalidated_child(
        parent: PropagationGraphRevision,
        prepared: PreparedPropagationInvalidation,
    ) -> PropagationGraphRevision:
        return replace(
            parent,
            graph_revision_id=stable_id("propagation-invalidated-graph", prepared.scope.scope_key),
            status=PropagationStatus.INVALIDATED,
            unresolved_issue_codes=tuple(sorted(set(parent.unresolved_issue_codes) | {"stale_evidence"})),
            parent_graph_revision_id=parent.graph_revision_id,
            record_version=parent.record_version + 1,
            created_at=prepared.graph.created_at,
        )

    @classmethod
    def _validate_dependencies(
        cls,
        connection: sqlite3.Connection,
        workspace_id: str,
        graph: PropagationGraphRevision,
        topology: TopologySnapshot,
        rule_pack: PropagationRulePack,
        evidence_packs: tuple[EvidencePack, ...],
        source_row_ids: tuple[str, ...],
    ) -> None:
        if (
            graph.workspace_id != workspace_id
            or topology.workspace_id != workspace_id
            or graph.topology_snapshot_id != topology.topology_snapshot_id
            or graph.topology_hash != topology.topology_hash
            or graph.rule_pack_id != rule_pack.rule_pack_id
            or graph.rule_pack_version != rule_pack.version
            or tuple(pack.pack_id for pack in evidence_packs) != graph.evidence_pack_ids
        ):
            raise ReviewError("FMEA_REVIEW_ACTION_INVALID", "Propagation dependency binding is invalid.")
        try:
            validate_topology_snapshot(topology)
            validate_propagation_rule_pack(rule_pack)
            validate_graph_revision(
                replace(graph, status=PropagationStatus.REVIEWED),
                topology,
                rule_pack,
                PropagationEvidenceResolution(evidence_packs),
            )
        except FmeaDomainError as exc:
            raise ReviewError("FMEA_REVIEW_ACTION_INVALID", "Propagation graph dependency validation failed.") from exc
        for pack in evidence_packs:
            if pack.workspace_id != workspace_id:
                raise ReviewError("FMEA_REVIEW_ACTION_INVALID", "Propagation evidence binding is invalid.")
            row = connection.execute(
                "SELECT pack_id, pack_hash, pack_json FROM evidence_packs WHERE pack_id = ? AND workspace_id = ?",
                (pack.pack_id, workspace_id),
            ).fetchone()
            if row is None or row["pack_hash"] != pack.pack_hash or row["pack_json"] != encode_evidence_json(pack):
                raise ReviewError("FMEA_REVIEW_ACTION_INVALID", "Propagation evidence binding is invalid.")
        cls._validate_snapshots(connection, workspace_id, graph, rule_pack, evidence_packs)
        cls._validate_source_rows(connection, workspace_id, graph.analysis_id, source_row_ids)

    @classmethod
    def _validate_review_prepared(cls, connection: sqlite3.Connection, prepared: PreparedPropagationReview) -> None:
        if (
            prepared.scope.command != "fmea.propagation.review"
            or prepared.scope.resource_path
            != f"/fmea/propagation-graphs/{prepared.previous_graph.graph_revision_id}/reviews"
            or prepared.graph.status is not PropagationStatus.CONFIRMED
            or prepared.previous_graph.status not in {PropagationStatus.PROPOSED, PropagationStatus.REVIEWED}
            or prepared.previous_graph.workspace_id != prepared.scope.workspace_id
            or prepared.graph.workspace_id != prepared.scope.workspace_id
            or prepared.graph.parent_graph_revision_id != prepared.previous_graph.graph_revision_id
            or prepared.graph.record_version != prepared.previous_graph.record_version + 1
            or prepared.command.graph_revision_id != prepared.previous_graph.graph_revision_id
            or prepared.command.expected_graph_record_version != prepared.previous_graph.record_version
            or prepared.audit.workspace_id != prepared.scope.workspace_id
            or prepared.audit.actor_id != prepared.scope.actor_id
            or prepared.audit.row_id not in prepared.source_row_ids
            or prepared.audit.suggestion_id
            != (prepared.graph.assistance_suggestion_ids[0] if prepared.graph.assistance_suggestion_ids else None)
            or prepared.decision_id != stable_id("propagation-review", prepared.scope.scope_key)
            or prepared.audit.event_id != stable_id("propagation-audit", prepared.scope.scope_key)
            or prepared.audit.idempotency_key_hash != prepared.scope.key_hash
        ):
            raise ReviewError("FMEA_REVIEW_ACTION_INVALID", "Propagation review binding is invalid.")
        decisions = tuple(sorted(prepared.edge_decisions, key=lambda item: item.edge_id))
        if tuple(prepared.edge_decisions) != decisions or {item.edge_id for item in decisions} != {
            edge.edge_id for edge in prepared.previous_graph.edges
        }:
            raise ReviewError("FMEA_REVIEW_ACTION_INVALID", "Propagation edge decision binding is invalid.")
        expected_hash = propagation_review_payload_hash(prepared.scope, prepared.command, edge_decisions=decisions)
        if prepared.payload_hash != expected_hash:
            raise ReviewError("FMEA_REVIEW_ACTION_INVALID", "Propagation review payload binding is invalid.")
        if (
            prepared.audit.actor_type is not ActorType.HUMAN
            or "propagation_reviewer" not in prepared.audit.actor_roles
            or prepared.audit.decision_id != prepared.decision_id
            or prepared.audit.canonical_payload_hash != prepared.payload_hash
            or prepared.audit.expected_record_version != prepared.previous_graph.record_version
            or prepared.audit.applied_record_version != prepared.graph.record_version
        ):
            raise ReviewError("FMEA_REVIEW_ACTION_INVALID", "Propagation review audit binding is invalid.")
        if (
            prepared.outbox.event_type != "propagation.confirmed"
            or prepared.outbox.workspace_id != prepared.scope.workspace_id
            or prepared.outbox.aggregate_id != prepared.graph.graph_revision_id
            or prepared.outbox.event_id != stable_id("propagation-outbox", prepared.scope.scope_key)
            or prepared.outbox.scope_key != prepared.scope.scope_key
        ):
            raise ReviewError("FMEA_REVIEW_ACTION_INVALID", "Propagation review outbox binding is invalid.")

    @classmethod
    def _validate_invalidation_prepared(
        cls, connection: sqlite3.Connection, prepared: PreparedPropagationInvalidation
    ) -> None:
        if (
            prepared.scope.command != "fmea.propagation.invalidate"
            or prepared.scope.resource_path
            != f"/fmea/propagation-graphs/{prepared.previous_graph.graph_revision_id}/invalidations"
            or prepared.graph.status is not PropagationStatus.INVALIDATED
            or prepared.previous_graph.status
            not in {
                PropagationStatus.PROPOSED,
                PropagationStatus.REVIEWED,
                PropagationStatus.CONFIRMED,
            }
            or prepared.previous_graph.workspace_id != prepared.scope.workspace_id
            or prepared.graph.workspace_id != prepared.scope.workspace_id
            or prepared.graph.parent_graph_revision_id != prepared.previous_graph.graph_revision_id
            or prepared.graph.record_version != prepared.previous_graph.record_version + 1
            or prepared.command.graph_revision_id != prepared.previous_graph.graph_revision_id
            or prepared.command.expected_graph_record_version != prepared.previous_graph.record_version
            or prepared.audit.actor_type is ActorType.MODEL
            or prepared.audit.workspace_id != prepared.scope.workspace_id
            or prepared.audit.actor_id != prepared.scope.actor_id
            or prepared.audit.row_id not in prepared.source_row_ids
            or prepared.audit.suggestion_id
            != (prepared.graph.assistance_suggestion_ids[0] if prepared.graph.assistance_suggestion_ids else None)
            or prepared.decision_id != stable_id("propagation-invalidation", prepared.scope.scope_key)
            or prepared.audit.event_id != stable_id("propagation-audit", prepared.scope.scope_key)
            or prepared.audit.idempotency_key_hash != prepared.scope.key_hash
            or prepared.audit.decision_id != prepared.decision_id
            or prepared.audit.canonical_payload_hash != prepared.payload_hash
        ):
            raise ReviewError("FMEA_REVIEW_ACTION_INVALID", "Propagation invalidation binding is invalid.")
        expected_hash = propagation_invalidation_payload_hash(prepared.scope, prepared.command)
        if prepared.payload_hash != expected_hash:
            raise ReviewError("FMEA_REVIEW_ACTION_INVALID", "Propagation invalidation payload binding is invalid.")
        if (
            prepared.outbox.event_type != "propagation.invalidated"
            or prepared.outbox.workspace_id != prepared.scope.workspace_id
            or prepared.outbox.aggregate_id != prepared.graph.graph_revision_id
            or prepared.outbox.event_id != stable_id("propagation-outbox", prepared.scope.scope_key)
            or prepared.outbox.scope_key != prepared.scope.scope_key
        ):
            raise ReviewError("FMEA_REVIEW_ACTION_INVALID", "Propagation invalidation outbox binding is invalid.")

    @staticmethod
    def _decision_json(
        previous: PropagationGraphRevision,
        graph: PropagationGraphRevision,
        decisions: tuple[PropagationEdgeDecision, ...],
        acknowledgements: tuple[str, ...],
    ) -> str:
        return encode_review_json({
            "previous_graph": previous,
            "graph": graph,
            "edge_decisions": decisions,
            "acknowledgements": acknowledgements,
        })

    @classmethod
    def _persist_assistance_suggestion(
        cls, connection: sqlite3.Connection, prepared: PreparedPropagationProposal
    ) -> None:
        assistance = prepared.assistance
        replay_id = SqliteAssistanceRepository._check_replay_row(
            SqliteAssistanceRepository._idempotency_row(connection, assistance.scope),
            assistance.payload_hash,
            "assistance_suggestion",
        )
        if replay_id is not None:
            if replay_id != assistance.suggestion.suggestion_id:
                raise _storage_error()
            row = connection.execute(
                "SELECT * FROM fmea_assistance_suggestions WHERE suggestion_id = ? AND workspace_id = ?",
                (replay_id, assistance.suggestion.workspace_id),
            ).fetchone()
            if row is None:
                raise _storage_error()
            decoded = SqliteAssistanceRepository._decode_suggestion(row, connection)
            if decoded != assistance.suggestion:
                raise _storage_error()
            return
        SqliteAssistanceRepository._validate_suggestion_source(connection, assistance.suggestion)
        SqliteAssistanceRepository._reserve_idempotency(
            connection, assistance.scope, assistance.payload_hash, assistance.audit.occurred_at_server
        )
        SqliteAssistanceRepository._insert_audit(
            connection,
            assistance.audit,
            target_type=assistance.suggestion.target_type,
            target_id=assistance.suggestion.target_id,
            scope=assistance.scope,
        )
        SqliteAssistanceRepository._insert_suggestion(
            connection,
            assistance.suggestion,
            assistance.payload_hash,
            assistance.audit.event_id,
        )
        SqliteAssistanceRepository._complete_idempotency(
            connection,
            assistance.scope,
            assistance.payload_hash,
            "assistance_suggestion",
            assistance.suggestion.suggestion_id,
            assistance.audit.occurred_at_server,
        )

    def save_run_and_proposal(self, prepared: PreparedPropagationProposal) -> PropagationRun:
        if not isinstance(prepared, PreparedPropagationProposal):
            raise ReviewError("FMEA_REVIEW_REQUEST_INVALID", "Prepared propagation proposal is invalid.")
        graph = prepared.graph
        run = prepared.run
        binding_checks = (
            ("source_row_ids", bool(prepared.source_row_ids)),
            ("source_row_ids_unique", len(prepared.source_row_ids) == len(set(prepared.source_row_ids))),
            ("graph_run_workspace", graph.workspace_id == run.workspace_id),
            ("graph_run_analysis", graph.analysis_id == run.analysis_id),
            ("graph_run_revision", graph.graph_revision_id == run.graph.graph_revision_id),
            ("topology_workspace", prepared.topology.workspace_id == graph.workspace_id),
            ("evidence_workspace", prepared.evidence_pack.workspace_id == graph.workspace_id),
            ("assistance_scope_workspace", prepared.assistance.scope.workspace_id == graph.workspace_id),
            ("assistance_suggestion_workspace", prepared.assistance.suggestion.workspace_id == graph.workspace_id),
            ("suggestion_bound", prepared.assistance.suggestion.suggestion_id in graph.assistance_suggestion_ids),
            ("assistance_audit_workspace", prepared.assistance.audit.workspace_id == graph.workspace_id),
            ("assistance_audit_actor", prepared.assistance.audit.actor_type is not ActorType.MODEL),
            ("assistance_audit_row", prepared.assistance.audit.row_id == prepared.assistance.suggestion.target_id),
            ("assistance_audit_analysis", prepared.assistance.audit.analysis_id == graph.analysis_id),
            (
                "assistance_audit_suggestion",
                prepared.assistance.audit.suggestion_id == prepared.assistance.suggestion.suggestion_id,
            ),
            (
                "assistance_audit_hash",
                prepared.assistance.audit.canonical_payload_hash == prepared.assistance.payload_hash,
            ),
            ("request_workspace", prepared.request_scope.workspace_id == graph.workspace_id),
            ("request_actor", prepared.request_scope.actor_id == prepared.assistance.scope.actor_id),
            ("request_command", prepared.request_scope.command == "fmea.propagation.start"),
            (
                "request_resource",
                prepared.request_scope.resource_path == f"/fmea/analyses/{graph.analysis_id}/propagation",
            ),
            ("request_key", prepared.request_scope.key_hash == prepared.assistance.scope.key_hash),
            ("command_analysis", prepared.command.analysis_id == graph.analysis_id),
            (
                "command_record_version",
                prepared.command.expected_analysis_record_version == graph.analysis_record_version,
            ),
            ("command_source_rows", prepared.command.source_row_ids == prepared.source_row_ids),
            ("command_evidence_pack", prepared.command.evidence_pack_id == prepared.evidence_pack.pack_id),
            ("command_domain_pack", prepared.command.domain_pack_id == graph.domain_pack_id),
            ("command_domain_version", prepared.command.domain_pack_version == graph.domain_pack_version),
            ("command_rule_pack", prepared.command.rule_pack_id == graph.rule_pack_id),
            ("command_rule_version", prepared.command.rule_pack_version == graph.rule_pack_version),
            (
                "request_hash",
                prepared.request_hash == propagation_start_payload_hash(prepared.request_scope, prepared.command),
            ),
        )
        failed_bindings = tuple(name for name, passed in binding_checks if not passed)
        if failed_bindings:
            raise ReviewError(
                "FMEA_REVIEW_ACTION_INVALID",
                "Propagation proposal binding is invalid.",
            )
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            replayed = self._replay_propagation_start(connection, prepared.request_scope, prepared.request_hash)
            if replayed is not None:
                connection.execute("COMMIT")
                return replayed
            self._reserve(connection, prepared.request_scope, prepared.request_hash, run.created_at)
            self._insert_topology(connection, prepared.topology)
            self._insert_evidence_snapshot(connection, prepared.evidence_pack)
            self._insert_rule_snapshot(connection, prepared.rule_pack, graph.workspace_id, run.created_at)
            self._validate_dependencies(
                connection,
                graph.workspace_id,
                graph,
                prepared.topology,
                prepared.rule_pack,
                (prepared.evidence_pack,),
                prepared.source_row_ids,
            )
            self._insert_graph(connection, graph, prepared.source_row_ids)
            connection.execute(
                "INSERT INTO fmea_propagation_runs "
                "(workspace_id, run_id, analysis_id, source_record_version, status, graph_revision_id, "
                "assistance_suggestion_ids_json, error_code, error_message, request_hash, idempotency_scope, record_version, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    run.workspace_id,
                    run.run_id,
                    run.analysis_id,
                    graph.analysis_record_version,
                    run.status.value,
                    graph.graph_revision_id,
                    encode_review_json(run.assistance_suggestion_ids),
                    run.error_code,
                    run.error_message,
                    prepared.request_hash,
                    prepared.request_scope.scope_key,
                    run.record_version,
                    run.created_at,
                    run.updated_at,
                ),
            )
            graph_audit = replace(
                prepared.assistance.audit,
                event_id=stable_id("propagation-proposal-audit", prepared.request_scope.scope_key),
                row_id=prepared.source_row_ids[0],
            )
            self._persist_assistance_suggestion(connection, prepared)
            self._insert_audit(connection, graph_audit)
            payload = {
                "graph": json.loads(encode_review_json(graph)),
                "audit_event_id": graph_audit.event_id,
                "source_row_ids": list(prepared.source_row_ids),
            }
            outbox = OutboxEvent(
                event_id=stable_id("propagation-proposal-outbox", prepared.request_scope.scope_key),
                workspace_id=graph.workspace_id,
                aggregate_type="propagation_graph",
                aggregate_id=graph.graph_revision_id,
                event_type="propagation.proposed",
                payload=payload,
                payload_hash=outbox_payload_hash(payload),
                created_at=graph_audit.occurred_at_server,
                scope_key=prepared.request_scope.scope_key,
            )
            self._insert_outbox(connection, outbox)
            response = {
                "workspace_id": run.workspace_id,
                "resource_type": "propagation_run",
                "run_id": run.run_id,
                "graph_revision_id": graph.graph_revision_id,
                "suggestion_id": prepared.suggestion.suggestion_id,
                "audit_event_id": graph_audit.event_id,
                "outbox_event_id": outbox.event_id,
            }
            self._complete(
                connection,
                prepared.request_scope,
                prepared.request_hash,
                response,
                run.run_id,
                run.updated_at,
            )
            connection.execute("COMMIT")
            return run
        except ReviewError:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        except sqlite3.IntegrityError as exc:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise ReviewError(
                "FMEA_REVIEW_ACTION_INVALID", "Propagation proposal conflicts with stored state."
            ) from exc
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def _replay_propagation_start(  # noqa: C901
        self, connection: sqlite3.Connection, scope: IdempotencyScope, payload_hash: str
    ) -> PropagationRun | None:
        row = self._idempotency_row(connection, scope)
        response = self._decode_start_response(row, payload_hash)
        if response is None:
            return None
        if response["workspace_id"] != scope.workspace_id:
            raise _storage_error()
        run_row = connection.execute(
            "SELECT * FROM fmea_propagation_runs WHERE run_id = ? AND workspace_id = ?",
            (response["run_id"], scope.workspace_id),
        ).fetchone()
        if (
            run_row is None
            or run_row["idempotency_scope"] != scope.scope_key
            or run_row["request_hash"] != payload_hash
        ):
            raise _storage_error()
        run = self._run_from_row(connection, run_row, scope.workspace_id)
        if run.status is not RunStatus.SUCCEEDED or response["graph_revision_id"] != run.graph.graph_revision_id:
            raise _storage_error()
        if response["suggestion_id"] not in run.assistance_suggestion_ids:
            raise _storage_error()
        graph_source_row = connection.execute(
            "SELECT source_row_ids_json FROM fmea_propagation_graph_revisions WHERE graph_revision_id = ? AND workspace_id = ?",
            (run.graph.graph_revision_id, scope.workspace_id),
        ).fetchone()
        if graph_source_row is None:
            raise _storage_error()
        source_row_ids = _string_array(
            _strict_json(graph_source_row["source_row_ids_json"], "graph source row IDs"), "graph source row IDs"
        )
        suggestion_row = connection.execute(
            "SELECT * FROM fmea_assistance_suggestions WHERE suggestion_id = ? AND workspace_id = ?",
            (response["suggestion_id"], scope.workspace_id),
        ).fetchone()
        if suggestion_row is None:
            raise _storage_error()
        suggestion = SqliteAssistanceRepository._decode_suggestion(suggestion_row, connection)
        suggestion_scope = IdempotencyScope(
            scope.workspace_id,
            scope.actor_id,
            "fmea.propagation.suggestion",
            f"/fmea/propagation-runs/{run.run_id}/suggestion",
            scope.key_hash,
        )
        if (
            suggestion.run_id != run.run_id
            or suggestion.workspace_id != scope.workspace_id
            or suggestion_row["payload_hash"] != assistance_suggestion_payload_hash(suggestion_scope, suggestion)
            or suggestion_row["suggestion_hash"] != suggestion.suggestion_hash
        ):
            raise _storage_error()
        audit_row = connection.execute(
            "SELECT * FROM audit_events WHERE event_id = ? AND workspace_id = ?",
            (response["audit_event_id"], scope.workspace_id),
        ).fetchone()
        if audit_row is None:
            raise _storage_error()
        audit = decode_audit_event(audit_row["event_json"])
        if (
            not audit_event_json_matches(audit_row["event_json"], audit)
            or audit.event_id != response["audit_event_id"]
            or audit.workspace_id != scope.workspace_id
            or audit.suggestion_id != suggestion.suggestion_id
            or audit.run_id != run.run_id
            or audit.canonical_payload_hash != suggestion_row["payload_hash"]
        ):
            raise _storage_error()
        event = self._decode_outbox(connection, cast(str, response["outbox_event_id"]), scope.workspace_id)
        expected_payload = {
            "graph": json.loads(encode_review_json(run.graph)),
            "audit_event_id": audit.event_id,
            "source_row_ids": list(source_row_ids),
        }
        if (
            event.workspace_id != scope.workspace_id
            or event.event_type != "propagation.proposed"
            or event.aggregate_id != run.graph.graph_revision_id
            or event.scope_key != scope.scope_key
            or event.payload_hash != outbox_payload_hash(event.payload)
            or canonical_json(event.payload) != canonical_json(expected_payload)
        ):
            raise _storage_error()
        return run

    def replay_propagation_start(self, scope: IdempotencyScope, payload_hash: str) -> PropagationRun | None:
        connection = self._connect()
        try:
            return self._replay_propagation_start(connection, scope, payload_hash)
        except ReviewError:
            raise
        except Exception as exc:
            raise _storage_error() from exc
        finally:
            connection.close()

    def get_run(self, run_id: str, workspace_id: str) -> PropagationRun | None:
        workspace = self._workspace(workspace_id)
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM fmea_propagation_runs WHERE run_id = ? AND workspace_id = ?",
                (run_id, workspace),
            ).fetchone()
            if row is None:
                return None
            graph = None
            if row["graph_revision_id"] is not None:
                graph_row = self._graph_row(connection, row["graph_revision_id"], workspace)
                if graph_row is None:
                    raise _storage_error()
                graph = self._decode_graph_row(connection, graph_row, workspace)
            return PropagationRun(
                run_id=row["run_id"],
                workspace_id=row["workspace_id"],
                analysis_id=row["analysis_id"],
                status=RunStatus(row["status"]),
                graph=graph,
                error_code=row["error_code"],
                error_message=row["error_message"],
                assistance_suggestion_ids=_string_array(
                    _strict_json(row["assistance_suggestion_ids_json"], "propagation run suggestions"),
                    "propagation run suggestions",
                ),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                record_version=row["record_version"],
            )
        except ReviewError:
            raise
        except Exception as exc:
            raise _storage_error() from exc
        finally:
            connection.close()

    def _replay_review(  # noqa: C901
        self, connection: sqlite3.Connection, scope: IdempotencyScope, payload_hash: str
    ) -> PropagationReviewResult | None:
        row = self._idempotency_row(connection, scope)
        response = self._decode_response(row, payload_hash, "propagation_review")
        if response is None:
            return None
        if response["workspace_id"] != scope.workspace_id:
            raise _storage_error()
        graph_row = self._graph_row(connection, cast(str, response["graph_revision_id"]), scope.workspace_id)
        if graph_row is None:
            raise _storage_error()
        graph = self._decode_graph_row(connection, graph_row, scope.workspace_id)
        decision = connection.execute(
            "SELECT * FROM fmea_propagation_graph_decisions WHERE decision_id = ? AND workspace_id = ?",
            (response["decision_id"], scope.workspace_id),
        ).fetchone()
        if decision is None:
            raise _storage_error()
        previous_row = self._graph_row(
            connection, cast(str, decision["previous_graph_revision_id"]), scope.workspace_id
        )
        if previous_row is None:
            raise _storage_error()
        previous_graph = self._decode_graph_row(connection, previous_row, scope.workspace_id)
        if (
            decision["decision_id"] != stable_id("propagation-review", scope.scope_key)
            or decision["workspace_id"] != scope.workspace_id
            or decision["resulting_graph_revision_id"] != graph.graph_revision_id
            or decision["decision_type"] != "confirm"
            or decision["from_status"] != previous_graph.status.value
            or decision["from_status"] not in {PropagationStatus.PROPOSED.value, PropagationStatus.REVIEWED.value}
            or decision["to_status"] != PropagationStatus.CONFIRMED.value
            or decision["expected_graph_version"] != previous_graph.record_version
            or decision["applied_graph_version"] != graph.record_version
            or decision["payload_hash"] != payload_hash
            or decision["idempotency_scope"] != scope.scope_key
            or decision["audit_event_id"] != response["audit_event_id"]
            or decision["outbox_event_id"] != response["outbox_event_id"]
            or response["decision_id"] != decision["decision_id"]
            or response["audit_event_id"] != decision["audit_event_id"]
            or response["outbox_event_id"] != decision["outbox_event_id"]
        ):
            raise _storage_error()
        audit_row = connection.execute(
            "SELECT * FROM audit_events WHERE event_id = ? AND workspace_id = ?",
            (response["audit_event_id"], scope.workspace_id),
        ).fetchone()
        if audit_row is None:
            raise _storage_error()
        audit = decode_audit_event(audit_row["event_json"])
        if (
            not audit_event_json_matches(audit_row["event_json"], audit)
            or audit.event_id != response["audit_event_id"]
            or audit.workspace_id != scope.workspace_id
            or audit.actor_type is not ActorType.HUMAN
            or "propagation_reviewer" not in audit.actor_roles
            or audit.actor_id != decision["actor_id"]
            or audit.command != scope.command
            or audit.idempotency_key_hash != scope.key_hash
            or audit.decision_id != decision["decision_id"]
            or audit.canonical_payload_hash != payload_hash
        ):
            raise _storage_error()
        event = self._decode_outbox(connection, cast(str, response["outbox_event_id"]), scope.workspace_id)
        decision_body = _object(
            _strict_json(decision["decision_json"], "propagation graph decision"),
            {"previous_graph", "graph", "edge_decisions", "acknowledgements"},
            "propagation graph decision",
        )
        expected_payload = {
            "graph": json.loads(encode_review_json(graph)),
            "audit_event_id": audit.event_id,
            "decision_id": decision["decision_id"],
            "edge_decisions": decision_body["edge_decisions"],
        }
        if (
            event.event_type != "propagation.confirmed"
            or event.workspace_id != scope.workspace_id
            or event.aggregate_type != "propagation_graph"
            or event.aggregate_id != graph.graph_revision_id
            or event.scope_key != scope.scope_key
            or event.payload_hash != outbox_payload_hash(event.payload)
            or canonical_json(event.payload) != canonical_json(expected_payload)
        ):
            raise _storage_error()
        edge_rows = connection.execute(
            "SELECT edge_id, decision_id, graph_revision_id, action, actor_id, actor_type, reason, decision_json, "
            "idempotency_scope, payload_hash FROM fmea_propagation_edge_decisions "
            "WHERE workspace_id = ? AND decision_id = ? ORDER BY edge_id",
            (scope.workspace_id, decision["decision_id"]),
        ).fetchall()
        if any(
            row["decision_id"] != decision["decision_id"]
            or row["graph_revision_id"] != previous_graph.graph_revision_id
            or row["actor_type"] != "human"
            or row["actor_id"] != decision["actor_id"]
            or row["idempotency_scope"] != scope.scope_key
            or row["payload_hash"] != payload_hash
            or _strict_json(row["decision_json"], "propagation edge decision")
            != {
                "edge_id": row["edge_id"],
                "action": row["action"],
                "reason": row["reason"],
            }
            for row in edge_rows
        ):
            raise _storage_error()
        stored_edge_decisions = [
            {"edge_id": row["edge_id"], "action": row["action"], "reason": row["reason"]} for row in edge_rows
        ]
        expected_edge_decisions = sorted(
            cast(list[dict[str, object]], decision_body["edge_decisions"]),
            key=lambda item: str(item.get("edge_id")),
        )
        parent_edge_ids = {edge.edge_id for edge in previous_graph.edges}
        if {item.get("edge_id") for item in expected_edge_decisions} != parent_edge_ids or any(
            not isinstance(item.get("edge_id"), str)
            or item.get("action") not in {"accept", "reject"}
            or not isinstance(item.get("reason"), str)
            for item in expected_edge_decisions
        ):
            raise _storage_error()
        if (
            decision_body["previous_graph"] != json.loads(encode_review_json(previous_graph))
            or decision_body["graph"] != json.loads(encode_review_json(graph))
            or stored_edge_decisions != expected_edge_decisions
            or decision_body["acknowledgements"] != json.loads(encode_review_json(graph.unresolved_issue_codes))
            or len(edge_rows) != len(expected_edge_decisions)
            or decision["actor_id"] != audit.actor_id
            or decision["actor_type"] != audit.actor_type.value
        ):
            raise _storage_error()
        expected_edges = tuple(
            replace(edge, review_status=ReviewStatus.ACCEPTED)
            for edge in previous_graph.edges
            if any(item["edge_id"] == edge.edge_id and item["action"] == "accept" for item in expected_edge_decisions)
        )
        expected_child = replace(
            previous_graph,
            graph_revision_id=stable_id("propagation-confirmed-graph", scope.scope_key),
            status=PropagationStatus.CONFIRMED,
            edges=expected_edges,
            paths=PropagationAnalysisService._paths(expected_edges, previous_graph.analysis_id),
            unresolved_issue_codes=tuple(sorted(cast(list[str], decision_body["acknowledgements"]))),
            parent_graph_revision_id=previous_graph.graph_revision_id,
            record_version=previous_graph.record_version + 1,
            created_at=graph.created_at,
        )
        if graph != expected_child:
            raise _storage_error()
        self._validate_persisted_bindings(connection, scope.workspace_id, previous_graph)
        self._validate_persisted_bindings(connection, scope.workspace_id, graph)
        return PropagationReviewResult(
            graph=graph,
            decision_id=cast(str, response["decision_id"]),
            audit_event_id=cast(str, response["audit_event_id"]),
            outbox_event_id=cast(str, response["outbox_event_id"]),
            replayed=True,
        )

    def replay_graph_review(self, scope: IdempotencyScope, payload_hash: str) -> PropagationReviewResult | None:
        connection = self._connect()
        try:
            return self._replay_review(connection, scope, payload_hash)
        except ReviewError:
            raise
        except Exception as exc:
            raise _storage_error() from exc
        finally:
            connection.close()

    def replay_invalidation(self, scope: IdempotencyScope, payload_hash: str) -> PropagationGraphRevision | None:
        connection = self._connect()
        try:
            return self._replay_invalidation(connection, scope, payload_hash)
        except ReviewError:
            raise
        except Exception as exc:
            raise _storage_error() from exc
        finally:
            connection.close()

    def commit_graph_review(  # noqa: C901
        self, prepared: PreparedPropagationReview
    ) -> PropagationReviewResult:
        if not isinstance(prepared, PreparedPropagationReview):
            raise ReviewError("FMEA_REVIEW_REQUEST_INVALID", "Prepared propagation review is invalid.")
        connection = self._connect()
        try:
            self._validate_review_prepared(connection, prepared)
            connection.execute("BEGIN IMMEDIATE")
            replayed = self._replay_review(connection, prepared.scope, prepared.payload_hash)
            if replayed is not None:
                connection.execute("COMMIT")
                return replayed
            self._insert_topology(connection, prepared.topology)
            self._validate_dependencies(
                connection,
                prepared.scope.workspace_id,
                prepared.previous_graph,
                prepared.topology,
                prepared.rule_pack,
                prepared.evidence_packs,
                prepared.source_row_ids,
            )
            current_row = self._graph_row(
                connection, prepared.previous_graph.graph_revision_id, prepared.scope.workspace_id
            )
            if current_row is None:
                raise ReviewError("FMEA_REVIEW_ACTION_INVALID", "Propagation parent revision was not found.")
            current = self._decode_graph_row(connection, current_row, prepared.scope.workspace_id)
            if (
                current != prepared.previous_graph
                or current.record_version != prepared.command.expected_graph_record_version
            ):
                raise ReviewError("FMEA_VERSION_CONFLICT", "Propagation graph revision is stale.")
            expected_child = self._expected_confirmed_child(current, prepared)
            if prepared.graph != expected_child:
                raise ReviewError("FMEA_REVIEW_ACTION_INVALID", "Prepared propagation child is not semantically valid.")
            self._validate_dependencies(
                connection,
                prepared.scope.workspace_id,
                current,
                prepared.topology,
                prepared.rule_pack,
                prepared.evidence_packs,
                prepared.source_row_ids,
            )
            self._validate_dependencies(
                connection,
                prepared.scope.workspace_id,
                replace(expected_child, status=PropagationStatus.REVIEWED),
                prepared.topology,
                prepared.rule_pack,
                prepared.evidence_packs,
                prepared.source_row_ids,
            )
            if self._graph_row(connection, prepared.graph.graph_revision_id, prepared.scope.workspace_id) is not None:
                raise ReviewError("FMEA_REVIEW_ACTION_INVALID", "Propagation child revision already exists.")
            self._validate_source_rows(
                connection, prepared.scope.workspace_id, prepared.graph.analysis_id, prepared.source_row_ids
            )
            self._insert_graph(connection, prepared.graph, prepared.source_row_ids)
            self._reserve(connection, prepared.scope, prepared.payload_hash, prepared.audit.occurred_at_server)
            self._insert_audit(connection, prepared.audit)
            for edge_decision in prepared.edge_decisions:
                decision_json = encode_review_json({
                    "edge_id": edge_decision.edge_id,
                    "action": edge_decision.action.value,
                    "reason": edge_decision.reason,
                })
                connection.execute(
                    "INSERT INTO fmea_propagation_edge_decisions "
                    "(workspace_id, edge_decision_id, graph_revision_id, decision_id, edge_id, action, actor_id, actor_type, reason, decision_json, idempotency_scope, payload_hash, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        prepared.scope.workspace_id,
                        f"{prepared.decision_id}:{edge_decision.edge_id}",
                        prepared.previous_graph.graph_revision_id,
                        prepared.decision_id,
                        edge_decision.edge_id,
                        edge_decision.action.value,
                        prepared.audit.actor_id,
                        prepared.audit.actor_type.value,
                        edge_decision.reason,
                        decision_json,
                        prepared.scope.scope_key,
                        prepared.payload_hash,
                        prepared.audit.occurred_at_server,
                    ),
                )
            decision_json = self._decision_json(
                prepared.previous_graph,
                prepared.graph,
                prepared.edge_decisions,
                prepared.command.acknowledgements,
            )
            payload = {
                "graph": json.loads(encode_review_json(prepared.graph)),
                "audit_event_id": prepared.audit.event_id,
                "decision_id": prepared.decision_id,
                "edge_decisions": json.loads(encode_review_json(prepared.edge_decisions)),
            }
            persisted_outbox = OutboxEvent(
                event_id=prepared.outbox.event_id,
                workspace_id=prepared.outbox.workspace_id,
                aggregate_type=prepared.outbox.aggregate_type,
                aggregate_id=prepared.outbox.aggregate_id,
                event_type=prepared.outbox.event_type,
                payload=payload,
                payload_hash=outbox_payload_hash(payload),
                created_at=prepared.outbox.created_at,
                scope_key=prepared.outbox.scope_key,
            )
            if persisted_outbox != prepared.outbox:
                raise ReviewError("FMEA_REVIEW_ACTION_INVALID", "Propagation review outbox payload is invalid.")
            connection.execute(
                "INSERT INTO fmea_propagation_graph_decisions "
                "(workspace_id, decision_id, previous_graph_revision_id, resulting_graph_revision_id, decision_type, from_status, to_status, "
                "expected_graph_version, applied_graph_version, actor_id, actor_type, acknowledged_issue_codes_json, decision_json, "
                "idempotency_scope, payload_hash, audit_event_id, outbox_event_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    prepared.scope.workspace_id,
                    prepared.decision_id,
                    prepared.previous_graph.graph_revision_id,
                    prepared.graph.graph_revision_id,
                    "confirm",
                    prepared.previous_graph.status.value,
                    prepared.graph.status.value,
                    prepared.previous_graph.record_version,
                    prepared.graph.record_version,
                    prepared.audit.actor_id,
                    prepared.audit.actor_type.value,
                    encode_review_json(prepared.command.acknowledgements),
                    decision_json,
                    prepared.scope.scope_key,
                    prepared.payload_hash,
                    prepared.audit.event_id,
                    persisted_outbox.event_id,
                    prepared.audit.occurred_at_server,
                ),
            )
            self._insert_outbox(connection, persisted_outbox)
            response = {
                "workspace_id": prepared.scope.workspace_id,
                "resource_type": "propagation_review",
                "graph_revision_id": prepared.graph.graph_revision_id,
                "decision_id": prepared.decision_id,
                "audit_event_id": prepared.audit.event_id,
                "outbox_event_id": persisted_outbox.event_id,
            }
            self._complete(
                connection,
                prepared.scope,
                prepared.payload_hash,
                response,
                prepared.graph.graph_revision_id,
                prepared.audit.occurred_at_server,
            )
            connection.execute("COMMIT")
            return PropagationReviewResult(
                graph=prepared.graph,
                decision_id=prepared.decision_id,
                audit_event_id=prepared.audit.event_id,
                outbox_event_id=persisted_outbox.event_id,
            )
        except ReviewError:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        except sqlite3.IntegrityError as exc:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise ReviewError("FMEA_REVIEW_ACTION_INVALID", "Propagation review conflicts with stored state.") from exc
        finally:
            connection.close()

    def _replay_invalidation(  # noqa: C901
        self, connection: sqlite3.Connection, scope: IdempotencyScope, payload_hash: str
    ) -> PropagationGraphRevision | None:
        row = self._idempotency_row(connection, scope)
        response = self._decode_response(row, payload_hash, "propagation_invalidation")
        if response is None:
            return None
        if response["workspace_id"] != scope.workspace_id:
            raise _storage_error()
        graph_row = self._graph_row(connection, cast(str, response["graph_revision_id"]), scope.workspace_id)
        if graph_row is None:
            raise _storage_error()
        graph = self._decode_graph_row(connection, graph_row, scope.workspace_id)
        decision = connection.execute(
            "SELECT * FROM fmea_propagation_graph_decisions WHERE decision_id = ? AND workspace_id = ?",
            (response["decision_id"], scope.workspace_id),
        ).fetchone()
        if decision is None or (
            decision["decision_id"] != stable_id("propagation-invalidation", scope.scope_key)
            or decision["workspace_id"] != scope.workspace_id
            or decision["resulting_graph_revision_id"] != graph.graph_revision_id
            or decision["decision_type"] != "invalidate"
            or decision["payload_hash"] != payload_hash
            or decision["idempotency_scope"] != scope.scope_key
            or decision["audit_event_id"] != response["audit_event_id"]
            or decision["outbox_event_id"] != response["outbox_event_id"]
            or response["workspace_id"] != scope.workspace_id
            or response["decision_id"] != decision["decision_id"]
            or response["audit_event_id"] != decision["audit_event_id"]
            or response["outbox_event_id"] != decision["outbox_event_id"]
        ):
            raise _storage_error()
        audit_row = connection.execute(
            "SELECT * FROM audit_events WHERE event_id = ? AND workspace_id = ?",
            (response["audit_event_id"], scope.workspace_id),
        ).fetchone()
        if audit_row is None:
            raise _storage_error()
        audit = decode_audit_event(audit_row["event_json"])
        if (
            not audit_event_json_matches(audit_row["event_json"], audit)
            or audit.workspace_id != scope.workspace_id
            or audit.actor_id != decision["actor_id"]
            or audit.actor_type.value != decision["actor_type"]
            or audit.canonical_payload_hash != payload_hash
            or audit.decision_id != decision["decision_id"]
            or audit.command != scope.command
            or audit.idempotency_key_hash != scope.key_hash
        ):
            raise _storage_error()
        event = self._decode_outbox(connection, cast(str, response["outbox_event_id"]), scope.workspace_id)
        decision_body = _object(
            _strict_json(decision["decision_json"], "propagation invalidation decision"),
            {"previous_graph", "graph", "changed_evidence_hash", "reason"},
            "propagation invalidation decision",
        )
        previous_row = self._graph_row(
            connection, cast(str, decision["previous_graph_revision_id"]), scope.workspace_id
        )
        if previous_row is None:
            raise _storage_error()
        previous_graph = self._decode_graph_row(connection, previous_row, scope.workspace_id)
        expected_payload = {
            "graph": json.loads(encode_review_json(graph)),
            "audit_event_id": audit.event_id,
            "decision_id": decision["decision_id"],
            "edge_decisions": [],
        }
        if (
            event.event_type != "propagation.invalidated"
            or event.workspace_id != scope.workspace_id
            or event.aggregate_type != "propagation_graph"
            or event.aggregate_id != graph.graph_revision_id
            or event.scope_key != scope.scope_key
            or event.payload_hash != outbox_payload_hash(event.payload)
            or audit.canonical_payload_hash != payload_hash
            or canonical_json(event.payload) != canonical_json(expected_payload)
            or decision_body["previous_graph"] != json.loads(encode_review_json(previous_graph))
            or decision_body["graph"] != json.loads(encode_review_json(graph))
            or decision_body["changed_evidence_hash"] is None
            or decision_body["reason"] is None
            or decision["expected_graph_version"] != previous_graph.record_version
            or decision["applied_graph_version"] != graph.record_version
            or decision["from_status"] != previous_graph.status.value
            or decision["to_status"] != graph.status.value
            or _strict_json(decision["acknowledged_issue_codes_json"], "propagation acknowledgements")
            != json.loads(encode_review_json(graph.unresolved_issue_codes))
        ):
            raise _storage_error()
        changed_hash = decision_body["changed_evidence_hash"]
        if not isinstance(changed_hash, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", changed_hash):
            raise _storage_error()
        expected_graph = replace(
            previous_graph,
            graph_revision_id=stable_id("propagation-invalidated-graph", scope.scope_key),
            status=PropagationStatus.INVALIDATED,
            unresolved_issue_codes=tuple(sorted(set(previous_graph.unresolved_issue_codes) | {"stale_evidence"})),
            parent_graph_revision_id=previous_graph.graph_revision_id,
            record_version=previous_graph.record_version + 1,
            created_at=graph.created_at,
        )
        if graph != expected_graph:
            raise _storage_error()
        self._validate_persisted_bindings(connection, scope.workspace_id, previous_graph)
        self._validate_persisted_bindings(connection, scope.workspace_id, graph)
        return graph

    def invalidate(self, prepared: PreparedPropagationInvalidation) -> PropagationGraphRevision:  # noqa: C901
        if not isinstance(prepared, PreparedPropagationInvalidation):
            raise ReviewError("FMEA_REVIEW_REQUEST_INVALID", "Prepared propagation invalidation is invalid.")
        connection = self._connect()
        try:
            self._validate_invalidation_prepared(connection, prepared)
            connection.execute("BEGIN IMMEDIATE")
            replayed = self._replay_invalidation(connection, prepared.scope, prepared.payload_hash)
            if replayed is not None:
                connection.execute("COMMIT")
                return replayed
            self._insert_topology(connection, prepared.topology)
            self._validate_dependencies(
                connection,
                prepared.scope.workspace_id,
                prepared.previous_graph,
                prepared.topology,
                prepared.rule_pack,
                prepared.evidence_packs,
                prepared.source_row_ids,
            )
            current_row = self._graph_row(
                connection, prepared.previous_graph.graph_revision_id, prepared.scope.workspace_id
            )
            if current_row is None:
                raise ReviewError("FMEA_REVIEW_ACTION_INVALID", "Propagation parent revision was not found.")
            current = self._decode_graph_row(connection, current_row, prepared.scope.workspace_id)
            if (
                current != prepared.previous_graph
                or current.record_version != prepared.command.expected_graph_record_version
            ):
                raise ReviewError("FMEA_VERSION_CONFLICT", "Propagation graph revision is stale.")
            expected_child = self._expected_invalidated_child(current, prepared)
            if prepared.graph != expected_child:
                raise ReviewError("FMEA_REVIEW_ACTION_INVALID", "Prepared invalidated child is not semantically valid.")
            self._validate_dependencies(
                connection,
                prepared.scope.workspace_id,
                current,
                prepared.topology,
                prepared.rule_pack,
                prepared.evidence_packs,
                prepared.source_row_ids,
            )
            self._validate_dependencies(
                connection,
                prepared.scope.workspace_id,
                replace(expected_child, status=PropagationStatus.REVIEWED),
                prepared.topology,
                prepared.rule_pack,
                prepared.evidence_packs,
                prepared.source_row_ids,
            )
            self._insert_graph(connection, prepared.graph, prepared.source_row_ids)
            self._reserve(connection, prepared.scope, prepared.payload_hash, prepared.audit.occurred_at_server)
            self._insert_audit(connection, prepared.audit)
            payload = {
                "graph": json.loads(encode_review_json(prepared.graph)),
                "audit_event_id": prepared.audit.event_id,
                "decision_id": prepared.decision_id,
                "edge_decisions": [],
            }
            persisted_outbox = OutboxEvent(
                event_id=prepared.outbox.event_id,
                workspace_id=prepared.outbox.workspace_id,
                aggregate_type=prepared.outbox.aggregate_type,
                aggregate_id=prepared.outbox.aggregate_id,
                event_type=prepared.outbox.event_type,
                payload=payload,
                payload_hash=outbox_payload_hash(payload),
                created_at=prepared.outbox.created_at,
                scope_key=prepared.outbox.scope_key,
            )
            if persisted_outbox != prepared.outbox:
                raise ReviewError("FMEA_REVIEW_ACTION_INVALID", "Propagation invalidation outbox payload is invalid.")
            connection.execute(
                "INSERT INTO fmea_propagation_graph_decisions "
                "(workspace_id, decision_id, previous_graph_revision_id, resulting_graph_revision_id, decision_type, from_status, to_status, "
                "expected_graph_version, applied_graph_version, actor_id, actor_type, acknowledged_issue_codes_json, decision_json, "
                "idempotency_scope, payload_hash, audit_event_id, outbox_event_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    prepared.scope.workspace_id,
                    prepared.decision_id,
                    prepared.previous_graph.graph_revision_id,
                    prepared.graph.graph_revision_id,
                    "invalidate",
                    prepared.previous_graph.status.value,
                    prepared.graph.status.value,
                    prepared.previous_graph.record_version,
                    prepared.graph.record_version,
                    prepared.audit.actor_id,
                    prepared.audit.actor_type.value,
                    encode_review_json(prepared.graph.unresolved_issue_codes),
                    encode_review_json({
                        "previous_graph": prepared.previous_graph,
                        "graph": prepared.graph,
                        "changed_evidence_hash": prepared.command.changed_evidence_hash,
                        "reason": prepared.command.reason,
                    }),
                    prepared.scope.scope_key,
                    prepared.payload_hash,
                    prepared.audit.event_id,
                    persisted_outbox.event_id,
                    prepared.audit.occurred_at_server,
                ),
            )
            self._insert_outbox(connection, persisted_outbox)
            response = {
                "workspace_id": prepared.scope.workspace_id,
                "resource_type": "propagation_invalidation",
                "graph_revision_id": prepared.graph.graph_revision_id,
                "decision_id": prepared.decision_id,
                "audit_event_id": prepared.audit.event_id,
                "outbox_event_id": persisted_outbox.event_id,
            }
            self._complete(
                connection,
                prepared.scope,
                prepared.payload_hash,
                response,
                prepared.graph.graph_revision_id,
                prepared.audit.occurred_at_server,
            )
            connection.execute("COMMIT")
            return prepared.graph
        except ReviewError:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        except sqlite3.IntegrityError as exc:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise ReviewError(
                "FMEA_REVIEW_ACTION_INVALID", "Propagation invalidation conflicts with stored state."
            ) from exc
        finally:
            connection.close()

    def count_propagation_records(self, workspace_id: str) -> int:
        workspace = self._workspace(workspace_id)
        connection = self._connect()
        try:
            return int(
                connection.execute(
                    "SELECT "
                    "(SELECT COUNT(*) FROM fmea_propagation_topology_snapshots WHERE workspace_id = ?) + "
                    "(SELECT COUNT(*) FROM fmea_propagation_runs WHERE workspace_id = ?) + "
                    "(SELECT COUNT(*) FROM fmea_propagation_graph_revisions WHERE workspace_id = ?) + "
                    "(SELECT COUNT(*) FROM fmea_propagation_edges WHERE workspace_id = ?) + "
                    "(SELECT COUNT(*) FROM fmea_propagation_paths WHERE workspace_id = ?) + "
                    "(SELECT COUNT(*) FROM fmea_propagation_issues WHERE workspace_id = ?) + "
                    "(SELECT COUNT(*) FROM fmea_propagation_edge_decisions WHERE workspace_id = ?) + "
                    "(SELECT COUNT(*) FROM fmea_propagation_graph_decisions WHERE workspace_id = ?)",
                    (workspace,) * 8,
                ).fetchone()[0]
            )
        finally:
            connection.close()


__all__ = ["SqlitePropagationRepository"]
