"""Evidence-bound FMEA task generation and review.

The generator is intentionally deterministic: it transforms approved graph
statements into an auditable candidate and never invents risk scores or missing
professional facts.  Missing and conflicting fields stay visible for a human
reviewer, as required by the delivery workflow.
"""
# ruff: noqa: TRY003

from __future__ import annotations

import csv
import io
import json
from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any

from core_domain.delivery import (
    FMEA_FIELDS,
    FMEAItem,
    FMEATaskRequest,
    FMEATaskResult,
    GraphStatement,
    IssueSeverity,
    QualityIssue,
    ReviewDecision,
    TaskStatus,
)
from storage_layer.governance_store import GovernanceError, GovernanceStore


class FMEAService:
    """Run, review, publish, and export evidence-grounded FMEA tasks."""

    def __init__(self, store: GovernanceStore) -> None:
        self.store = store

    def run(self, request: FMEATaskRequest) -> FMEATaskResult:
        if request.template != "gas_turbine_minimum_v1":
            raise GovernanceError(f"Unsupported FMEA template: {request.template}")
        task = self.store.create_fmea_task(request)
        self.store.save_fmea_result(task.task_id, status=TaskStatus.RUNNING, items=())
        try:
            graph = self.store.get_graph_version(request.graph_version_id)
            items = build_fmea_items(graph.statements)
            if not items:
                return self.store.save_fmea_result(
                    task.task_id,
                    status=TaskStatus.FAILED,
                    items=(),
                    errors=("No HAS_FAILURE_MODE statements were available for the selected graph version.",),
                )
            return self.store.save_fmea_result(
                task.task_id,
                status=TaskStatus.NEEDS_REVIEW,
                items=items,
            )
        except Exception as exc:
            self.store.save_fmea_result(
                task.task_id,
                status=TaskStatus.FAILED,
                items=(),
                errors=(str(exc),),
            )
            raise

    def review(
        self,
        task_id: str,
        *,
        reviewer: str,
        decision: ReviewDecision | str,
        comment: str = "",
        corrections: Mapping[str, Any] | None = None,
    ) -> FMEATaskResult:
        decision = decision if isinstance(decision, ReviewDecision) else ReviewDecision(str(decision))
        task = self.store.get_fmea_task(task_id)
        if task.status not in {TaskStatus.NEEDS_REVIEW, TaskStatus.APPROVED}:
            raise GovernanceError(f"Task {task_id} is not reviewable from status {task.status.value}")

        corrected_items = _apply_corrections(task.items, corrections or {})
        if decision is ReviewDecision.APPROVE:
            corrected_items = tuple(replace(item, review_status="approved") for item in corrected_items)
            status = TaskStatus.APPROVED
        elif decision is ReviewDecision.REJECT:
            corrected_items = tuple(replace(item, review_status="rejected") for item in corrected_items)
            status = TaskStatus.NEEDS_REVIEW
        else:
            status = TaskStatus.NEEDS_REVIEW

        self.store.record_review(
            target_type="fmea",
            target_id=task_id,
            reviewer=reviewer,
            decision=decision,
            comment=comment,
            corrections=dict(corrections or {}),
        )
        return self.store.save_fmea_result(task_id, status=status, items=corrected_items, errors=task.errors)

    def publish(self, task_id: str) -> FMEATaskResult:
        task = self.store.get_fmea_task(task_id)
        if task.status is not TaskStatus.APPROVED:
            raise GovernanceError("FMEA task must be approved before publication")
        return self.store.publish_fmea_task(task_id)

    def export_json(self, task_id: str) -> str:
        task = self._published(task_id)
        return json.dumps(task.to_dict(), ensure_ascii=False, indent=2)

    def export_csv(self, task_id: str) -> str:
        task = self._published(task_id)
        output = io.StringIO(newline="")
        fieldnames = ["item_id", *FMEA_FIELDS, *[f"{field}_evidence" for field in FMEA_FIELDS], "issues"]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for item in task.items:
            row: dict[str, Any] = {"item_id": item.item_id}
            row.update({field: item.fields.get(field) or "" for field in FMEA_FIELDS})
            row.update({f"{field}_evidence": "|".join(item.field_evidence.get(field, ())) for field in FMEA_FIELDS})
            row["issues"] = "|".join(issue.code for issue in item.issues if not issue.resolved)
            writer.writerow(row)
        return output.getvalue()

    def _published(self, task_id: str) -> FMEATaskResult:
        task = self.store.get_fmea_task(task_id)
        if task.status is not TaskStatus.PUBLISHED:
            raise GovernanceError("Only published FMEA tasks can be exported")
        return task


def build_fmea_items(statements: Sequence[GraphStatement]) -> tuple[FMEAItem, ...]:
    """Build the minimum gas-turbine FMEA template from governed graph facts."""
    statements = tuple(statements)
    node_types = _node_types(statements)
    parent_edges = [item for item in statements if item.predicate == "PART_OF"]
    failure_edges = [item for item in statements if item.predicate == "HAS_FAILURE_MODE"]
    by_subject_relation: dict[tuple[str, str], list[GraphStatement]] = {}
    for statement in statements:
        by_subject_relation.setdefault((statement.subject, statement.predicate), []).append(statement)

    items: list[FMEAItem] = []
    for index, failure_edge in enumerate(failure_edges, start=1):
        component = failure_edge.subject
        failure_mode = failure_edge.object_name
        equipment, equipment_edges = _resolve_equipment(component, parent_edges, node_types)
        if failure_edge.subject_type == "EQUIPMENT":
            equipment = component
            component_value: str | None = None
        else:
            component_value = component

        cause_edges = by_subject_relation.get((failure_mode, "CAUSED_BY"), [])
        effect_edges = by_subject_relation.get((failure_mode, "HAS_EFFECT"), [])
        detection_edges = by_subject_relation.get((failure_mode, "DETECTED_BY"), [])
        action_edges = by_subject_relation.get((failure_mode, "MITIGATED_BY"), [])

        fields: dict[str, str | None] = {
            "equipment": equipment,
            "component": component_value,
            "failure_mode": failure_mode,
            "cause": _join_objects(cause_edges),
            "effect": _join_objects(effect_edges),
            "detection_method": _join_objects(detection_edges),
            "recommended_action": _join_objects(action_edges),
        }
        field_evidence: dict[str, tuple[str, ...]] = {
            "equipment": _edge_evidence(equipment_edges or [failure_edge]),
            "component": failure_edge.evidence_ids,
            "failure_mode": failure_edge.evidence_ids,
            "cause": _edge_evidence(cause_edges),
            "effect": _edge_evidence(effect_edges),
            "detection_method": _edge_evidence(detection_edges),
            "recommended_action": _edge_evidence(action_edges),
        }
        issues = _fmea_issues(
            item_id=f"FMEA-{index:04d}",
            fields=fields,
            field_evidence=field_evidence,
            field_edges={
                "cause": cause_edges,
                "effect": effect_edges,
                "detection_method": detection_edges,
                "recommended_action": action_edges,
            },
        )
        source_statement_ids = tuple(
            dict.fromkeys(
                statement.statement_id
                for statement in [
                    failure_edge,
                    *equipment_edges,
                    *cause_edges,
                    *effect_edges,
                    *detection_edges,
                    *action_edges,
                ]
            )
        )
        items.append(
            FMEAItem(
                item_id=f"FMEA-{index:04d}",
                fields=fields,
                field_evidence=field_evidence,
                issues=issues,
                metadata={"source_statement_ids": list(source_statement_ids)},
            )
        )
    return tuple(items)


def _resolve_equipment(
    component: str,
    parent_edges: Sequence[GraphStatement],
    node_types: Mapping[str, str],
) -> tuple[str | None, list[GraphStatement]]:
    by_child: dict[str, list[GraphStatement]] = {}
    for edge in parent_edges:
        by_child.setdefault(edge.subject, []).append(edge)
    current = component
    visited = {current}
    path: list[GraphStatement] = []
    while by_child.get(current):
        edge = by_child[current][0]
        path.append(edge)
        current = edge.object_name
        if current in visited:
            break
        visited.add(current)
        if node_types.get(current) == "EQUIPMENT" or edge.object_type == "EQUIPMENT":
            return current, path
    return (current if path else None), path


def _node_types(statements: Sequence[GraphStatement]) -> dict[str, str]:
    types: dict[str, str] = {}
    for item in statements:
        types.setdefault(item.subject, item.subject_type)
        types.setdefault(item.object_name, item.object_type)
    return types


def _join_objects(edges: Sequence[GraphStatement]) -> str | None:
    values = list(dict.fromkeys(edge.object_name for edge in edges if edge.object_name))
    return " / ".join(values) if values else None


def _edge_evidence(edges: Sequence[GraphStatement]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(evidence_id for edge in edges for evidence_id in edge.evidence_ids))


def _fmea_issues(
    *,
    item_id: str,
    fields: Mapping[str, str | None],
    field_evidence: Mapping[str, tuple[str, ...]],
    field_edges: Mapping[str, Sequence[GraphStatement]],
) -> tuple[QualityIssue, ...]:
    specs: list[tuple[str, str, IssueSeverity, tuple[str, ...], dict[str, Any]]] = []
    for field_name in FMEA_FIELDS:
        value = fields.get(field_name)
        citations = field_evidence.get(field_name, ())
        if not value:
            specs.append((
                "missing_field",
                f"FMEA field {field_name} is unknown and requires human review.",
                IssueSeverity.WARNING,
                (),
                {"field": field_name},
            ))
        elif not citations:
            specs.append((
                "insufficient_evidence",
                f"FMEA field {field_name} has a value but no source evidence.",
                IssueSeverity.ERROR,
                (),
                {"field": field_name},
            ))
    for field_name, edges in field_edges.items():
        values = {edge.object_name for edge in edges if edge.object_name}
        if len(values) > 1:
            specs.append((
                "field_conflict",
                f"FMEA field {field_name} has multiple source values: {', '.join(sorted(values))}.",
                IssueSeverity.WARNING,
                _edge_evidence(edges),
                {"field": field_name, "values": sorted(values)},
            ))
    return tuple(
        QualityIssue(
            issue_id=f"{item_id}:Q{index:03d}",
            code=code,
            message=message,
            severity=severity,
            evidence_ids=evidence_ids,
            metadata=metadata,
        )
        for index, (code, message, severity, evidence_ids, metadata) in enumerate(specs, start=1)
    )


def _apply_corrections(items: Sequence[FMEAItem], corrections: Mapping[str, Any]) -> tuple[FMEAItem, ...]:
    raw_items = corrections.get("items", corrections)
    if not isinstance(raw_items, Mapping):
        raise TypeError("FMEA corrections must be a mapping keyed by item_id")
    corrected: list[FMEAItem] = []
    for item in items:
        item_patch = raw_items.get(item.item_id, {})
        if not isinstance(item_patch, Mapping) or not item_patch:
            corrected.append(item)
            continue
        fields = dict(item.fields)
        field_evidence = dict(item.field_evidence)
        changed_fields: list[str] = []
        for field_name, raw_value in item_patch.items():
            if field_name not in FMEA_FIELDS:
                raise ValueError(f"Unknown FMEA correction field: {field_name}")
            if isinstance(raw_value, Mapping):
                value = raw_value.get("value")
                citations = tuple(
                    str(value).strip() for value in raw_value.get("evidence_ids", ()) if str(value).strip()
                )
            else:
                value = raw_value
                citations = field_evidence.get(field_name, ())
            fields[field_name] = str(value).strip() if value not in (None, "") else None
            field_evidence[field_name] = citations
            changed_fields.append(field_name)

        issues = tuple(
            replace(issue, resolved=True) if issue.metadata.get("field") in changed_fields else issue
            for issue in item.issues
        )
        for field_name in changed_fields:
            if fields.get(field_name) and not field_evidence.get(field_name):
                issues += (
                    QualityIssue(
                        issue_id=f"{item.item_id}:H{len(issues) + 1:03d}",
                        code="human_value_without_evidence",
                        message=f"Human correction for {field_name} has no evidence binding.",
                        severity=IssueSeverity.WARNING,
                        metadata={"field": field_name},
                    ),
                )
        corrected.append(
            replace(
                item,
                fields=fields,
                field_evidence=field_evidence,
                issues=issues,
                review_status="modified",
                metadata={**item.metadata, "human_modified_fields": changed_fields},
            )
        )
    return tuple(corrected)
