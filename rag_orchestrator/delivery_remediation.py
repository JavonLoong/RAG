"""Executable feedback remediation for the governed M2-M5 delivery flow."""
# ruff: noqa: TRY003

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core_domain.delivery import ContentStatus, FMEATaskRequest
from kg_pipeline.governed_extraction import GovernedExtractionError, extract_governed_statements
from rag_orchestrator.fmea import FMEAService
from storage_layer.governance_store import GovernanceError, GovernanceStore
from storage_layer.governed_index import GovernedDocumentIndex
from storage_layer.graph_store import GraphStore, normalize_kg_payload


class DeliveryRemediationService:
    """Turn a feedback record into a real action or an explicit human gate."""

    def __init__(
        self,
        store: GovernanceStore,
        *,
        document_index: GovernedDocumentIndex,
        graph_store: GraphStore,
    ) -> None:
        self.store = store
        self.document_index = document_index
        self.graph_store = graph_store

    def remediate(
        self,
        feedback_id: str,
        *,
        actor: str,
        document_version_id: str | None = None,
        graph_version_id: str | None = None,
        corrections: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        feedback = self.store.get_feedback(feedback_id)
        task = self.store.get_fmea_task(str(feedback["task_id"]))
        module = str(feedback["routed_module"])

        if module == "M1":
            return self.store.record_feedback_run(
                feedback_id=feedback_id,
                actor=actor,
                action="request_source_or_permission_review",
                status="needs_human_input",
                result={
                    "message": "M1 source, permission, or acquisition issues require a human decision before rerun.",
                    "task_id": task.task_id,
                    "next_actions": [
                        "confirm source ownership and access permission",
                        "intake and publish an approved replacement source",
                        "create a new governed graph and FMEA task",
                    ],
                },
            )

        if module == "M2":
            if graph_version_id:
                return self._activate_graph_and_regenerate(
                    feedback_id=feedback_id,
                    actor=actor,
                    source_task=task,
                    graph_version_id=graph_version_id,
                    required_document_version_id=document_version_id,
                    action="publish_m2_downstream_revalidation",
                )
            if document_version_id and corrections:
                revision = self.store.create_document_revision(
                    document_version_id,
                    reviewer=actor,
                    corrections=corrections,
                    comment=f"Remediation for {feedback_id}",
                )
                review_task = self.store.create_document_review_task(
                    document_version_id=revision.version_id,
                    source_asset_id=str(revision.metadata.get("source_asset_id") or "") or None,
                    reasons=[
                        {
                            "code": "feedback_document_correction",
                            "message": f"Review corrected material created for {feedback_id}.",
                        }
                    ],
                )
                return self.store.record_feedback_run(
                    feedback_id=feedback_id,
                    actor=actor,
                    action="create_document_revision",
                    status="needs_review",
                    result={
                        "document_version": revision.to_dict(),
                        "review_task": review_task,
                        "next_action": (
                            "approve and publish the revised material, then call remediation "
                            "with its document_version_id"
                        ),
                    },
                )
            if document_version_id:
                document = self.store.get_document_version(document_version_id)
                if document.status is not ContentStatus.PUBLISHED:
                    return self.store.record_feedback_run(
                        feedback_id=feedback_id,
                        actor=actor,
                        action="await_document_approval",
                        status="needs_human_input",
                        result={
                            "document_version_id": document_version_id,
                            "document_status": document.status.value,
                            "next_action": "approve and publish the corrected document version",
                        },
                    )
                index_result = self.document_index.rebuild(
                    self.store.list_published_document_versions(),
                    created_by=actor,
                )
                try:
                    extraction = extract_governed_statements([document], backend="rules")
                except GovernedExtractionError as exc:
                    return self.store.record_feedback_run(
                        feedback_id=feedback_id,
                        actor=actor,
                        action="rebuild_index_and_request_graph_extraction_review",
                        status="needs_human_input",
                        result={
                            "document_index": index_result,
                            "message": str(exc),
                            "next_action": "configure a governed extractor or create a graph candidate manually",
                        },
                    )
                graph_candidate = self.store.create_graph_candidate(
                    source_document_version_ids=[document.version_id],
                    statements=extraction.statements,
                    metadata={
                        "remediates_feedback_id": feedback_id,
                        "extraction": extraction.diagnostics,
                    },
                    created_by=actor,
                )
                return self.store.record_feedback_run(
                    feedback_id=feedback_id,
                    actor=actor,
                    action="rebuild_index_and_create_graph_candidate",
                    status="needs_review",
                    result={
                        "document_index": index_result,
                        "graph_candidate": graph_candidate.to_dict(),
                        "next_action": (
                            "review and publish the graph candidate, then call remediation "
                            "with graph_version_id"
                        ),
                    },
                )
            if not document_version_id:
                return self.store.record_feedback_run(
                    feedback_id=feedback_id,
                    actor=actor,
                    action="request_document_correction",
                    status="needs_human_input",
                    result={
                        "message": "M2 remediation requires document_version_id and corrected chunks.",
                        "task_id": task.task_id,
                    },
                )

        if module == "M3":
            rebuilt = self.document_index.rebuild(
                self.store.list_published_document_versions(),
                created_by=actor,
            )
            expected_versions = sorted(item.version_id for item in self.store.list_published_document_versions())
            actual_versions = sorted(str(item) for item in rebuilt.get("document_versions") or ())
            return self.store.record_feedback_run(
                feedback_id=feedback_id,
                actor=actor,
                action="rebuild_published_material_index",
                status="completed",
                result={
                    **rebuilt,
                    "revalidation": {
                        "expected_document_versions": expected_versions,
                        "actual_document_versions": actual_versions,
                        "consistent": actual_versions == expected_versions,
                    },
                },
                resolve_feedback=actual_versions == expected_versions,
            )

        if module == "M4":
            normalized_code = str(feedback["code"]).lower()
            if graph_version_id:
                return self._activate_graph_and_regenerate(
                    feedback_id=feedback_id,
                    actor=actor,
                    source_task=task,
                    graph_version_id=graph_version_id,
                    action="activate_corrected_graph_and_regenerate_fmea",
                )
            if any(token in normalized_code for token in ("stale", "sync", "projection")):
                return self._activate_graph_and_regenerate(
                    feedback_id=feedback_id,
                    actor=actor,
                    source_task=task,
                    graph_version_id=task.request.graph_version_id,
                    action="resync_graph_and_regenerate_fmea",
                )
            return self.store.record_feedback_run(
                feedback_id=feedback_id,
                actor=actor,
                action="request_corrected_graph_version",
                status="needs_human_input",
                result={
                    "current_graph_version_id": task.request.graph_version_id,
                    "next_action": "review and publish a corrected graph, then call remediation with graph_version_id",
                },
            )

        if module == "M5":
            rerun = FMEAService(self.store).run(
                FMEATaskRequest(
                    requested_by=actor,
                    graph_version_id=task.request.graph_version_id,
                    document_version_ids=task.request.document_version_ids,
                    template=task.request.template,
                    template_version=task.request.template_version,
                    metadata={
                        **task.request.metadata,
                        "remediates_feedback_id": feedback_id,
                        "supersedes_task_id": task.task_id,
                    },
                )
            )
            return self.store.record_feedback_run(
                feedback_id=feedback_id,
                actor=actor,
                action="regenerate_fmea",
                status="completed",
                result={"new_fmea_task": rerun.to_dict()},
                resolve_feedback=True,
            )

        raise GovernanceError(f"Unsupported feedback route: {module}")

    def _activate_graph_and_regenerate(
        self,
        *,
        feedback_id: str,
        actor: str,
        source_task: Any,
        graph_version_id: str,
        action: str,
        required_document_version_id: str | None = None,
    ) -> dict[str, Any]:
        graph = self.store.get_graph_version(graph_version_id)
        if graph.status is not ContentStatus.PUBLISHED:
            return self.store.record_feedback_run(
                feedback_id=feedback_id,
                actor=actor,
                action="await_graph_approval",
                status="needs_human_input",
                result={
                    "graph_version_id": graph_version_id,
                    "graph_status": graph.status.value,
                    "next_action": "approve and publish the corrected graph version",
                },
            )
        if required_document_version_id and required_document_version_id not in graph.source_document_version_ids:
            raise GovernanceError(
                "Corrected graph does not use the required remediated document version",
                code="remediation_graph_source_mismatch",
                details={
                    "required_document_version_id": required_document_version_id,
                    "graph_source_document_version_ids": list(graph.source_document_version_ids),
                },
            )
        edges = normalize_kg_payload(self.store.graph_as_edge_payload(graph.graph_version_id))
        graph_summary = self.graph_store.import_edges(edges, reset=True)
        rerun = FMEAService(self.store).run(
            FMEATaskRequest(
                requested_by=actor,
                graph_version_id=graph.graph_version_id,
                document_version_ids=graph.source_document_version_ids,
                template=source_task.request.template,
                template_version=source_task.request.template_version,
                metadata={
                    **source_task.request.metadata,
                    "remediates_feedback_id": feedback_id,
                    "supersedes_task_id": source_task.task_id,
                },
            )
        )
        revalidation = {
            "graph_version_id": graph.graph_version_id,
            "graph_store_edge_count": graph_summary.get("edge_count"),
            "expected_edge_count": len(graph.statements),
            "new_fmea_status": rerun.status.value,
            "lineage_consistent": set(rerun.request.document_version_ids) == set(graph.source_document_version_ids),
        }
        completed = (
            revalidation["graph_store_edge_count"] == revalidation["expected_edge_count"]
            and revalidation["new_fmea_status"] == "needs_review"
            and revalidation["lineage_consistent"]
        )
        return self.store.record_feedback_run(
            feedback_id=feedback_id,
            actor=actor,
            action=action,
            status="completed" if completed else "failed",
            result={
                "graph_store": graph_summary,
                "new_fmea_task": FMEAService(self.store).result_payload(rerun.task_id),
                "revalidation": revalidation,
            },
            resolve_feedback=completed,
        )
