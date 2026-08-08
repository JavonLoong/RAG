"""Executable feedback remediation for the governed M2-M5 delivery flow."""
# ruff: noqa: TRY003

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core_domain.delivery import FMEATaskRequest
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
                },
            )

        if module == "M2":
            if not document_version_id or not corrections:
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
            revision = self.store.create_document_revision(
                document_version_id,
                reviewer=actor,
                corrections=corrections,
                comment=f"Remediation for {feedback_id}",
            )
            return self.store.record_feedback_run(
                feedback_id=feedback_id,
                actor=actor,
                action="create_document_revision",
                status="needs_review",
                result={
                    "document_version": revision.to_dict(),
                    "next_action": "approve and publish the revised material, then rebuild downstream artifacts",
                },
            )

        if module == "M3":
            rebuilt = self.document_index.rebuild(self.store.list_published_document_versions())
            return self.store.record_feedback_run(
                feedback_id=feedback_id,
                actor=actor,
                action="rebuild_published_material_index",
                status="completed",
                result=rebuilt,
                resolve_feedback=True,
            )

        if module == "M4":
            graph = self.store.get_graph_version(task.request.graph_version_id)
            edges = normalize_kg_payload(self.store.graph_as_edge_payload(graph.graph_version_id))
            graph_summary = self.graph_store.import_edges(edges, reset=True)
            rerun = FMEAService(self.store).run(
                FMEATaskRequest(
                    requested_by=actor,
                    graph_version_id=task.request.graph_version_id,
                    document_version_ids=task.request.document_version_ids,
                    template=task.request.template,
                    metadata={**task.request.metadata, "remediates_feedback_id": feedback_id, "supersedes_task_id": task.task_id},
                )
            )
            return self.store.record_feedback_run(
                feedback_id=feedback_id,
                actor=actor,
                action="resync_graph_and_regenerate_fmea",
                status="completed",
                result={"graph_store": graph_summary, "new_fmea_task": rerun.to_dict()},
                resolve_feedback=True,
            )

        if module == "M5":
            rerun = FMEAService(self.store).run(
                FMEATaskRequest(
                    requested_by=actor,
                    graph_version_id=task.request.graph_version_id,
                    document_version_ids=task.request.document_version_ids,
                    template=task.request.template,
                    metadata={**task.request.metadata, "remediates_feedback_id": feedback_id, "supersedes_task_id": task.task_id},
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
