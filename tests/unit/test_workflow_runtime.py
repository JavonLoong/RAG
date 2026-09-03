from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from workflow_runtime import (
    GateResult,
    NonRetryableStepError,
    PowerRagHandlers,
    QualityGate,
    RetryableStepError,
    RunStatus,
    StepStatus,
    WorkflowDefinition,
    WorkflowError,
    WorkflowRunner,
    WorkflowStep,
    WorkflowStore,
    build_local_to_fmea_workflow,
    workflow_report,
)


class WorkflowRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = WorkflowStore(Path(self.temp_dir.name) / "workflow.sqlite3")
        self.runner = WorkflowRunner(self.store)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_retry_uses_persistent_checkpoint_and_is_idempotent(self) -> None:
        def flaky(context):
            completed = context.load_checkpoint("completed", 0)
            if context.attempt == 1:
                context.save_checkpoint("completed", completed + 1)
                raise RetryableStepError("injected transient failure")
            return {"completed": context.load_checkpoint("completed")}

        definition = WorkflowDefinition(
            "checkpoint-test",
            "1.0.0",
            (WorkflowStep("work", flaky, max_attempts=2),),
        )
        result = self.runner.start(definition, {"source": "local"}, idempotency_key="same-input")
        self.assertEqual(result.status, RunStatus.SUCCEEDED)
        self.assertEqual(result.steps[0].attempt, 2)
        self.assertEqual(result.steps[0].output, {"completed": 1})

        repeated = self.runner.start(definition, {"source": "local"}, idempotency_key="same-input")
        self.assertEqual(repeated.run_id, result.run_id)
        with self.assertRaises(WorkflowError) as raised:
            self.runner.start(definition, {"source": "different"}, idempotency_key="same-input")
        self.assertEqual(raised.exception.code, "IDEMPOTENCY_CONFLICT")

    def test_quality_gate_blocks_downstream_and_operator_retry_resumes(self) -> None:
        switch = {"pass": False}

        def gate(_output, _context):
            return GateResult(switch["pass"], {"switch": switch["pass"]}, () if switch["pass"] else ("blocked",))

        definition = WorkflowDefinition(
            "quality-gate-test",
            "1.0.0",
            (
                WorkflowStep("build", lambda _context: {"artifact": "v1"}, quality_gates=(QualityGate("gate", gate),)),
                WorkflowStep("consume", lambda context: context.dependency_outputs["build"], depends_on=("build",)),
            ),
        )
        blocked = self.runner.start(definition, {})
        self.assertEqual(blocked.status, RunStatus.BLOCKED)
        self.assertEqual([step.status for step in blocked.steps], [StepStatus.BLOCKED, StepStatus.BLOCKED])
        self.assertFalse(self.store.gate_results(blocked.run_id)[0]["passed"])

        switch["pass"] = True
        self.store.retry_failed(blocked.run_id)
        resumed = self.runner.resume(blocked.run_id, definition)
        self.assertEqual(resumed.status, RunStatus.SUCCEEDED)
        self.assertEqual(resumed.steps[1].output, {"artifact": "v1"})

    def test_pending_run_can_be_cancelled_before_execution(self) -> None:
        definition = WorkflowDefinition("cancel-test", "1", (WorkflowStep("work", lambda _ctx: {}),))
        pending = self.runner.start(definition, {}, execute=False)
        self.store.request_cancel(pending.run_id)
        cancelled = self.runner.execute(pending.run_id, definition)
        self.assertEqual(cancelled.status, RunStatus.CANCELLED)
        self.assertEqual(cancelled.steps[0].status, StepStatus.CANCELLED)

    def test_non_retryable_failure_stops_after_one_attempt_and_reports_failed(self) -> None:
        attempts = {"count": 0}

        def fail(_context):
            attempts["count"] += 1
            raise NonRetryableStepError("permanent contract failure")

        definition = WorkflowDefinition(
            "non-retryable-test",
            "1",
            (
                WorkflowStep("fail", fail, max_attempts=3),
                WorkflowStep("downstream", lambda _ctx: {}, depends_on=("fail",)),
            ),
        )
        result = self.runner.start(definition, {})
        self.assertEqual(result.status, RunStatus.FAILED)
        self.assertEqual(attempts["count"], 1)
        self.assertEqual(result.steps[0].attempt, 1)
        self.assertEqual(result.steps[1].status, StepStatus.BLOCKED)

    def test_run_report_redacts_credentials_and_absolute_windows_paths(self) -> None:
        def fail(_context):
            raise RuntimeError(r"api_key=sk-example-secret-12345 failed at C:\private\runtime\index.sqlite3")

        definition = WorkflowDefinition("redaction-test", "1", (WorkflowStep("fail", fail),))
        result = self.runner.start(definition, {})
        serialized = str(workflow_report(self.store, result.run_id))
        self.assertNotIn("sk-example-secret-12345", serialized)
        self.assertNotIn(r"C:\private\runtime\index.sqlite3", serialized)
        self.assertIn("<REDACTED>", serialized)
        self.assertIn("<PATH>", serialized)

    def test_standard_local_to_fmea_workflow_enforces_version_chain(self) -> None:
        version = 3
        handlers = PowerRagHandlers(
            ingest=lambda _ctx: {"files_received": 2, "files_registered": 2, "files_failed": 0},
            parse_and_review=lambda _ctx: {
                "review_status": "approved",
                "evidence_coverage": 1.0,
                "unresolved_quality_issues": 0,
            },
            publish_knowledge_base=lambda _ctx: {
                "knowledge_base_version": version,
                "manifest_sha256": "a" * 64,
                "quality_passed": True,
            },
            build_graphrag=lambda _ctx: {
                "knowledge_base_version": version,
                "graph_version": "graph-v3",
                "graph_ready": True,
                "evidence_coverage": 1.0,
                "rag_fallback_ready": True,
            },
            generate_and_review_fmea=lambda _ctx: {
                "knowledge_base_version": version,
                "artifact_version": "fmea-v3",
                "review_status": "published",
                "field_evidence_coverage": 1.0,
            },
        )
        definition = build_local_to_fmea_workflow(handlers)
        result = self.runner.start(definition, {"local_paths": ["a.pdf", "b.docx"]})

        self.assertEqual(result.status, RunStatus.SUCCEEDED)
        self.assertTrue(all(step.status is StepStatus.SUCCEEDED for step in result.steps))
        report = workflow_report(self.store, result.run_id)
        self.assertEqual(report["schema_version"], "power-rag.workflow-report.v1")
        self.assertEqual(report["progress"], 1.0)
        self.assertEqual(len(report["quality_gates"]), 6)


if __name__ == "__main__":
    unittest.main()
