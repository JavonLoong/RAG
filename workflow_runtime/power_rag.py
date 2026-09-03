"""Standard M1→M5 workflow contract and independent module quality gates."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .engine import GateResult, QualityGate, StepContext, WorkflowDefinition, WorkflowStep

ModuleHandler = Callable[[StepContext], dict[str, Any]]


@dataclass(frozen=True, slots=True)
class PowerRagHandlers:
    ingest: ModuleHandler
    parse_and_review: ModuleHandler
    publish_knowledge_base: ModuleHandler
    build_graphrag: ModuleHandler
    generate_and_review_fmea: ModuleHandler


def build_local_to_fmea_workflow(handlers: PowerRagHandlers) -> WorkflowDefinition:
    """Create the fixed first-phase pipeline while keeping module implementations injectable."""

    return WorkflowDefinition(
        name="local-documents-to-reviewed-fmea",
        version="1.0.0",
        steps=(
            WorkflowStep(
                "m1_ingest",
                handlers.ingest,
                max_attempts=2,
                quality_gates=(QualityGate("m1_no_silent_loss", _m1_gate),),
            ),
            WorkflowStep(
                "m2_parse_review",
                handlers.parse_and_review,
                depends_on=("m1_ingest",),
                max_attempts=2,
                quality_gates=(QualityGate("m2_evidence_and_review", _m2_gate),),
            ),
            WorkflowStep(
                "m3_publish",
                handlers.publish_knowledge_base,
                depends_on=("m2_parse_review",),
                max_attempts=2,
                quality_gates=(QualityGate("m3_version_integrity", _m3_gate),),
            ),
            WorkflowStep(
                "m4_graphrag",
                handlers.build_graphrag,
                depends_on=("m3_publish",),
                max_attempts=2,
                quality_gates=(QualityGate("m4_evidence_or_rag_fallback", _m4_gate),),
            ),
            WorkflowStep(
                "m5_fmea",
                handlers.generate_and_review_fmea,
                depends_on=("m3_publish", "m4_graphrag"),
                max_attempts=2,
                quality_gates=(QualityGate("m5_reviewed_evidence", _m5_gate),),
            ),
            WorkflowStep(
                "m6_acceptance",
                _acceptance_handler,
                depends_on=("m1_ingest", "m2_parse_review", "m3_publish", "m4_graphrag", "m5_fmea"),
                quality_gates=(QualityGate("m6_version_chain", _m6_gate),),
            ),
        ),
    )


def _mapping(output: Any) -> dict[str, Any]:
    if not isinstance(output, dict):
        return {}
    return output


def _m1_gate(output: Any, _context: StepContext) -> GateResult:
    value = _mapping(output)
    received = int(value.get("files_received", -1))
    registered = int(value.get("files_registered", -2))
    failed = int(value.get("files_failed", 0))
    passed = received >= 0 and registered + failed == received and failed == 0
    return GateResult(
        passed,
        {"files_received": received, "files_registered": registered, "files_failed": failed},
        () if passed else ("M1 file accounting is incomplete or contains failed files.",),
    )


def _m2_gate(output: Any, _context: StepContext) -> GateResult:
    value = _mapping(output)
    status = str(value.get("review_status", ""))
    evidence_coverage = float(value.get("evidence_coverage", 0.0))
    unresolved = int(value.get("unresolved_quality_issues", -1))
    passed = status == "approved" and evidence_coverage >= 1.0 and unresolved == 0
    return GateResult(
        passed,
        {"review_status": status, "evidence_coverage": evidence_coverage, "unresolved_quality_issues": unresolved},
        ()
        if passed
        else ("M2 output must be approved, fully evidence-linked, and free of unresolved blocking issues.",),
    )


def _m3_gate(output: Any, _context: StepContext) -> GateResult:
    value = _mapping(output)
    version = value.get("knowledge_base_version")
    manifest = str(value.get("manifest_sha256", ""))
    quality_passed = value.get("quality_passed") is True
    passed = isinstance(version, int) and version > 0 and len(manifest) == 64 and quality_passed
    return GateResult(
        passed,
        {"knowledge_base_version": version or 0, "quality_passed": quality_passed},
        () if passed else ("M3 must return a verified version and 64-character manifest checksum.",),
    )


def _m4_gate(output: Any, _context: StepContext) -> GateResult:
    value = _mapping(output)
    graph_ready = bool(value.get("graph_ready", False))
    coverage = float(value.get("evidence_coverage", 0.0))
    fallback = bool(value.get("rag_fallback_ready", False))
    passed = (graph_ready and coverage >= 1.0) or fallback
    return GateResult(
        passed,
        {"graph_ready": graph_ready, "evidence_coverage": coverage, "rag_fallback_ready": fallback},
        () if passed else ("M4 requires fully evidenced graph output or an explicit basic-RAG fallback.",),
    )


def _m5_gate(output: Any, _context: StepContext) -> GateResult:
    value = _mapping(output)
    status = str(value.get("review_status", ""))
    coverage = float(value.get("field_evidence_coverage", 0.0))
    artifact_version = value.get("artifact_version")
    passed = status in {"approved", "published"} and coverage >= 1.0 and bool(artifact_version)
    return GateResult(
        passed,
        {"review_status": status, "field_evidence_coverage": coverage, "artifact_version": str(artifact_version or "")},
        ()
        if passed
        else ("M5 FMEA must be reviewed, versioned, and have evidence for every populated professional field.",),
    )


def _acceptance_handler(context: StepContext) -> dict[str, Any]:
    m3 = context.dependency_outputs["m3_publish"]
    m4 = context.dependency_outputs["m4_graphrag"]
    m5 = context.dependency_outputs["m5_fmea"]
    return {
        "knowledge_base_version": m3["knowledge_base_version"],
        "knowledge_base_manifest": m3["manifest_sha256"],
        "graph_version": m4.get("graph_version"),
        "artifact_version": m5["artifact_version"],
        "version_chain_consistent": m4.get("knowledge_base_version") == m3["knowledge_base_version"]
        and m5.get("knowledge_base_version") == m3["knowledge_base_version"],
    }


def _m6_gate(output: Any, _context: StepContext) -> GateResult:
    value = _mapping(output)
    passed = value.get("version_chain_consistent") is True
    return GateResult(
        passed,
        {
            "knowledge_base_version": int(value.get("knowledge_base_version", 0)),
            "version_chain_consistent": passed,
        },
        () if passed else ("Knowledge-base, graph, and FMEA artifacts do not use the same source version.",),
    )
