"""Small durable workflow engine for the M1-to-M5 local pipeline.

This is intentionally an in-process runner, not a scheduler replacement.  Its
job is to make the current project's batch pipeline repeatable, inspectable,
idempotent, and resumable without introducing an operations platform.
"""

from __future__ import annotations

import json
import re
import sqlite3
import uuid
from collections.abc import Callable, Generator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any


class WorkflowError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class RetryableStepError(RuntimeError):
    """A transient step failure that may consume another configured attempt."""


class NonRetryableStepError(RuntimeError):
    """A permanent failure that must stop without automatic retry."""


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class GateResult:
    passed: bool
    metrics: dict[str, int | float | str | bool] = field(default_factory=dict)
    issues: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class QualityGate:
    name: str
    check: Callable[[Any, StepContext], GateResult]


@dataclass(frozen=True, slots=True)
class WorkflowStep:
    step_id: str
    handler: Callable[[StepContext], Any]
    depends_on: tuple[str, ...] = ()
    max_attempts: int = 1
    quality_gates: tuple[QualityGate, ...] = ()


@dataclass(frozen=True, slots=True)
class WorkflowDefinition:
    name: str
    version: str
    steps: tuple[WorkflowStep, ...]

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.version.strip():
            raise ValueError("workflow name and version are required")
        if not self.steps:
            raise ValueError("workflow requires at least one step")
        ids = [step.step_id for step in self.steps]
        if any(not value.strip() for value in ids) or len(ids) != len(set(ids)):
            raise ValueError("workflow step identifiers must be non-empty and unique")
        known = set(ids)
        for step in self.steps:
            if step.max_attempts <= 0:
                raise ValueError(f"max_attempts must be positive for {step.step_id}")
            missing = set(step.depends_on) - known
            if missing:
                raise ValueError(f"step {step.step_id} has unknown dependencies: {sorted(missing)}")
            if step.step_id in step.depends_on:
                raise ValueError(f"step {step.step_id} cannot depend on itself")
        _topological_steps(self)


@dataclass(frozen=True, slots=True)
class StepSnapshot:
    step_id: str
    status: StepStatus
    attempt: int
    max_attempts: int
    output: Any | None
    error: dict[str, Any] | None
    started_at: str | None
    finished_at: str | None


@dataclass(frozen=True, slots=True)
class RunSnapshot:
    run_id: str
    workflow_name: str
    workflow_version: str
    status: RunStatus
    idempotency_key: str | None
    inputs: dict[str, Any]
    cancellation_requested: bool
    created_at: str
    started_at: str | None
    finished_at: str | None
    steps: tuple[StepSnapshot, ...]

    @property
    def progress(self) -> float:
        if not self.steps:
            return 0.0
        completed = sum(
            1
            for step in self.steps
            if step.status in {StepStatus.SUCCEEDED, StepStatus.FAILED, StepStatus.BLOCKED, StepStatus.CANCELLED}
        )
        return completed / len(self.steps)


class StepContext:
    def __init__(
        self,
        *,
        store: WorkflowStore,
        run_id: str,
        step_id: str,
        attempt: int,
        inputs: dict[str, Any],
        dependency_outputs: dict[str, Any],
    ) -> None:
        self.store = store
        self.run_id = run_id
        self.step_id = step_id
        self.attempt = attempt
        self.inputs = inputs
        self.dependency_outputs = dependency_outputs

    def save_checkpoint(self, key: str, value: Any) -> None:
        self.store.save_checkpoint(self.run_id, self.step_id, key, value)

    def load_checkpoint(self, key: str, default: Any = None) -> Any:
        return self.store.load_checkpoint(self.run_id, self.step_id, key, default)

    def raise_if_cancelled(self) -> None:
        if self.store.cancellation_requested(self.run_id):
            raise NonRetryableStepError("Run cancellation was requested.")


class WorkflowStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS workflow_runs (
                    run_id TEXT PRIMARY KEY,
                    workflow_name TEXT NOT NULL,
                    workflow_version TEXT NOT NULL,
                    idempotency_key TEXT,
                    input_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    cancellation_requested INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    updated_at TEXT NOT NULL,
                    error_json TEXT,
                    UNIQUE(workflow_name, workflow_version, idempotency_key)
                );

                CREATE TABLE IF NOT EXISTS workflow_steps (
                    run_id TEXT NOT NULL REFERENCES workflow_runs(run_id) ON DELETE CASCADE,
                    step_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempt INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL,
                    output_json TEXT,
                    error_json TEXT,
                    started_at TEXT,
                    finished_at TEXT,
                    PRIMARY KEY(run_id, step_id)
                );

                CREATE TABLE IF NOT EXISTS workflow_checkpoints (
                    run_id TEXT NOT NULL,
                    step_id TEXT NOT NULL,
                    checkpoint_key TEXT NOT NULL,
                    value_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(run_id, step_id, checkpoint_key),
                    FOREIGN KEY(run_id, step_id) REFERENCES workflow_steps(run_id, step_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS quality_gate_results (
                    gate_result_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    step_id TEXT NOT NULL,
                    attempt INTEGER NOT NULL,
                    gate_name TEXT NOT NULL,
                    passed INTEGER NOT NULL,
                    metrics_json TEXT NOT NULL,
                    issues_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(run_id, step_id) REFERENCES workflow_steps(run_id, step_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS workflow_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL REFERENCES workflow_runs(run_id) ON DELETE CASCADE,
                    step_id TEXT,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_runs_status ON workflow_runs(status, updated_at);
                CREATE INDEX IF NOT EXISTS idx_events_run ON workflow_events(run_id, event_id);
                CREATE INDEX IF NOT EXISTS idx_gates_run ON quality_gate_results(run_id, step_id, attempt);
                """
            )

    def create_run(
        self,
        definition: WorkflowDefinition,
        inputs: Mapping[str, Any],
        *,
        idempotency_key: str | None = None,
    ) -> RunSnapshot:
        self.initialize()
        normalized_inputs = dict(inputs)
        input_json = _json(normalized_inputs)
        key = idempotency_key.strip() if idempotency_key and idempotency_key.strip() else None
        with self._connect() as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            if key is not None:
                row = connection.execute(
                    """
                    SELECT run_id, input_json FROM workflow_runs
                    WHERE workflow_name=? AND workflow_version=? AND idempotency_key=?
                    """,
                    (definition.name, definition.version, key),
                ).fetchone()
                if row is not None:
                    if str(row["input_json"]) != input_json:
                        raise WorkflowError(
                            "IDEMPOTENCY_CONFLICT",
                            "The idempotency key is already associated with different inputs.",
                        )
                    return self._get_run(connection, str(row["run_id"]))
            run_id = f"run_{uuid.uuid4().hex}"
            now = _utc_now()
            connection.execute(
                """
                INSERT INTO workflow_runs(
                    run_id, workflow_name, workflow_version, idempotency_key, input_json,
                    status, created_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (run_id, definition.name, definition.version, key, input_json, RunStatus.PENDING.value, now, now),
            )
            connection.executemany(
                """
                INSERT INTO workflow_steps(run_id, step_id, status, attempt, max_attempts)
                VALUES(?, ?, ?, 0, ?)
                """,
                ((run_id, step.step_id, StepStatus.PENDING.value, step.max_attempts) for step in definition.steps),
            )
            self._event(connection, run_id, None, "run_created", {"idempotency_key": key})
            return self._get_run(connection, run_id)

    def get_run(self, run_id: str) -> RunSnapshot:
        self.initialize()
        with self._connect() as connection:
            return self._get_run(connection, run_id)

    def request_cancel(self, run_id: str) -> RunSnapshot:
        self.initialize()
        with self._connect() as connection, connection:
            snapshot = self._get_run(connection, run_id)
            if snapshot.status in {RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED}:
                return snapshot
            now = _utc_now()
            connection.execute(
                "UPDATE workflow_runs SET cancellation_requested=1, updated_at=? WHERE run_id=?",
                (now, run_id),
            )
            self._event(connection, run_id, None, "cancellation_requested", {})
            return self._get_run(connection, run_id)

    def retry_failed(self, run_id: str) -> RunSnapshot:
        self.initialize()
        with self._connect() as connection, connection:
            snapshot = self._get_run(connection, run_id)
            if snapshot.status not in {RunStatus.FAILED, RunStatus.BLOCKED}:
                raise WorkflowError("RUN_NOT_RETRYABLE", "Only failed or blocked runs can be retried.")
            connection.execute(
                """
                UPDATE workflow_steps
                SET status=?, attempt=0, output_json=NULL, error_json=NULL, started_at=NULL, finished_at=NULL
                WHERE run_id=? AND status IN (?, ?)
                """,
                (StepStatus.PENDING.value, run_id, StepStatus.FAILED.value, StepStatus.BLOCKED.value),
            )
            now = _utc_now()
            connection.execute(
                """
                UPDATE workflow_runs SET status=?, cancellation_requested=0, finished_at=NULL,
                    error_json=NULL, updated_at=? WHERE run_id=?
                """,
                (RunStatus.PENDING.value, now, run_id),
            )
            self._event(connection, run_id, None, "operator_retry", {})
            return self._get_run(connection, run_id)

    def save_checkpoint(self, run_id: str, step_id: str, key: str, value: Any) -> None:
        normalized_key = key.strip()
        if not normalized_key:
            raise ValueError("checkpoint key is required")
        value_json = _json(value)
        with self._connect() as connection, connection:
            connection.execute(
                """
                INSERT INTO workflow_checkpoints(run_id, step_id, checkpoint_key, value_json, updated_at)
                VALUES(?, ?, ?, ?, ?)
                ON CONFLICT(run_id, step_id, checkpoint_key) DO UPDATE SET
                    value_json=excluded.value_json, updated_at=excluded.updated_at
                """,
                (run_id, step_id, normalized_key, value_json, _utc_now()),
            )
            self._event(connection, run_id, step_id, "checkpoint_saved", {"key": normalized_key})

    def load_checkpoint(self, run_id: str, step_id: str, key: str, default: Any = None) -> Any:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT value_json FROM workflow_checkpoints WHERE run_id=? AND step_id=? AND checkpoint_key=?",
                (run_id, step_id, key),
            ).fetchone()
        return default if row is None else json.loads(str(row["value_json"]))

    def cancellation_requested(self, run_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT cancellation_requested FROM workflow_runs WHERE run_id=?", (run_id,)
            ).fetchone()
        if row is None:
            raise WorkflowError("RUN_NOT_FOUND", f"Workflow run {run_id} does not exist.")
        return bool(row["cancellation_requested"])

    def gate_results(self, run_id: str) -> list[dict[str, Any]]:
        self.initialize()
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT step_id, attempt, gate_name, passed, metrics_json, issues_json, created_at
                FROM quality_gate_results WHERE run_id=? ORDER BY gate_result_id
                """,
                (run_id,),
            ).fetchall()
        return [
            {
                "step_id": str(row["step_id"]),
                "attempt": int(row["attempt"]),
                "gate_name": str(row["gate_name"]),
                "passed": bool(row["passed"]),
                "metrics": json.loads(str(row["metrics_json"])),
                "issues": json.loads(str(row["issues_json"])),
                "created_at": str(row["created_at"]),
            }
            for row in rows
        ]

    def _get_run(self, connection: sqlite3.Connection, run_id: str) -> RunSnapshot:
        row = connection.execute("SELECT * FROM workflow_runs WHERE run_id=?", (run_id,)).fetchone()
        if row is None:
            raise WorkflowError("RUN_NOT_FOUND", f"Workflow run {run_id} does not exist.")
        step_rows = connection.execute(
            "SELECT * FROM workflow_steps WHERE run_id=? ORDER BY rowid", (run_id,)
        ).fetchall()
        steps = tuple(
            StepSnapshot(
                step_id=str(item["step_id"]),
                status=StepStatus(str(item["status"])),
                attempt=int(item["attempt"]),
                max_attempts=int(item["max_attempts"]),
                output=None if item["output_json"] is None else json.loads(str(item["output_json"])),
                error=None if item["error_json"] is None else json.loads(str(item["error_json"])),
                started_at=None if item["started_at"] is None else str(item["started_at"]),
                finished_at=None if item["finished_at"] is None else str(item["finished_at"]),
            )
            for item in step_rows
        )
        return RunSnapshot(
            run_id=str(row["run_id"]),
            workflow_name=str(row["workflow_name"]),
            workflow_version=str(row["workflow_version"]),
            status=RunStatus(str(row["status"])),
            idempotency_key=None if row["idempotency_key"] is None else str(row["idempotency_key"]),
            inputs=json.loads(str(row["input_json"])),
            cancellation_requested=bool(row["cancellation_requested"]),
            created_at=str(row["created_at"]),
            started_at=None if row["started_at"] is None else str(row["started_at"]),
            finished_at=None if row["finished_at"] is None else str(row["finished_at"]),
            steps=steps,
        )

    @staticmethod
    def _event(
        connection: sqlite3.Connection,
        run_id: str,
        step_id: str | None,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        connection.execute(
            "INSERT INTO workflow_events(run_id, step_id, event_type, payload_json, created_at) VALUES(?, ?, ?, ?, ?)",
            (run_id, step_id, event_type, _json(payload), _utc_now()),
        )

    @contextmanager
    def _connect(self) -> Generator[sqlite3.Connection, None, None]:
        connection = sqlite3.connect(self.db_path, timeout=30.0)
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("PRAGMA busy_timeout=30000")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


class WorkflowRunner:
    def __init__(self, store: WorkflowStore) -> None:
        self.store = store

    def start(
        self,
        definition: WorkflowDefinition,
        inputs: Mapping[str, Any],
        *,
        idempotency_key: str | None = None,
        execute: bool = True,
    ) -> RunSnapshot:
        snapshot = self.store.create_run(definition, inputs, idempotency_key=idempotency_key)
        return self.execute(snapshot.run_id, definition) if execute else snapshot

    def start_batch(
        self,
        definition: WorkflowDefinition,
        inputs: Sequence[Mapping[str, Any]],
        *,
        idempotency_prefix: str | None = None,
        execute: bool = True,
    ) -> tuple[RunSnapshot, ...]:
        return tuple(
            self.start(
                definition,
                value,
                idempotency_key=(f"{idempotency_prefix}:{index}" if idempotency_prefix else None),
                execute=execute,
            )
            for index, value in enumerate(inputs)
        )

    def execute(self, run_id: str, definition: WorkflowDefinition) -> RunSnapshot:  # noqa: C901
        self.store.initialize()
        snapshot = self.store.get_run(run_id)
        if (snapshot.workflow_name, snapshot.workflow_version) != (definition.name, definition.version):
            raise WorkflowError("WORKFLOW_VERSION_MISMATCH", "Run and workflow definition versions do not match.")
        if snapshot.status in {RunStatus.SUCCEEDED, RunStatus.CANCELLED}:
            return snapshot
        self._recover_interrupted(run_id)
        self._set_run_running(run_id)

        step_by_id = {step.step_id: step for step in definition.steps}
        for step in _topological_steps(definition):
            current = self.store.get_run(run_id)
            if current.cancellation_requested:
                self._cancel_remaining(run_id)
                return self.store.get_run(run_id)
            snapshot_by_id = {item.step_id: item for item in current.steps}
            step_snapshot = snapshot_by_id[step.step_id]
            if step_snapshot.status is StepStatus.SUCCEEDED:
                continue
            dependency_states = [snapshot_by_id[item].status for item in step.depends_on]
            if any(
                status in {StepStatus.FAILED, StepStatus.BLOCKED, StepStatus.CANCELLED} for status in dependency_states
            ):
                self._block_step(run_id, step.step_id, "UPSTREAM_NOT_SUCCEEDED")
                continue
            if not all(status is StepStatus.SUCCEEDED for status in dependency_states):
                self._block_step(run_id, step.step_id, "UPSTREAM_INCOMPLETE")
                continue
            while True:
                updated = self.store.get_run(run_id)
                latest = next(item for item in updated.steps if item.step_id == step.step_id)
                if latest.status in {StepStatus.SUCCEEDED, StepStatus.BLOCKED, StepStatus.CANCELLED}:
                    break
                if latest.status is StepStatus.FAILED and latest.attempt >= latest.max_attempts:
                    break
                if latest.status is StepStatus.FAILED and latest.error and latest.error.get("retryable") is False:
                    break
                succeeded = self._execute_step(run_id, step, updated.inputs, step_by_id)
                if succeeded:
                    break
                latest = next(item for item in self.store.get_run(run_id).steps if item.step_id == step.step_id)
                if latest.attempt >= latest.max_attempts or (latest.error and latest.error.get("retryable") is False):
                    break

        final = self.store.get_run(run_id)
        statuses = {item.status for item in final.steps}
        if statuses == {StepStatus.SUCCEEDED}:
            self._finish_run(run_id, RunStatus.SUCCEEDED)
        elif StepStatus.CANCELLED in statuses:
            self._finish_run(run_id, RunStatus.CANCELLED)
        elif StepStatus.FAILED in statuses:
            self._finish_run(run_id, RunStatus.FAILED)
        elif StepStatus.BLOCKED in statuses:
            self._finish_run(run_id, RunStatus.BLOCKED)
        else:
            self._finish_run(run_id, RunStatus.FAILED)
        return self.store.get_run(run_id)

    def resume(self, run_id: str, definition: WorkflowDefinition) -> RunSnapshot:
        return self.execute(run_id, definition)

    def _execute_step(
        self,
        run_id: str,
        step: WorkflowStep,
        inputs: dict[str, Any],
        step_by_id: dict[str, WorkflowStep],
    ) -> bool:
        del step_by_id  # Reserved for future DAG diagnostics without changing the public signature.
        current = self.store.get_run(run_id)
        snapshots = {item.step_id: item for item in current.steps}
        attempt = snapshots[step.step_id].attempt + 1
        dependency_outputs = {item: snapshots[item].output for item in step.depends_on}
        now = _utc_now()
        with self.store._connect() as connection, connection:
            connection.execute(
                """
                UPDATE workflow_steps SET status=?, attempt=?, started_at=?, finished_at=NULL, error_json=NULL
                WHERE run_id=? AND step_id=?
                """,
                (StepStatus.RUNNING.value, attempt, now, run_id, step.step_id),
            )
            self.store._event(connection, run_id, step.step_id, "step_started", {"attempt": attempt})
        context = StepContext(
            store=self.store,
            run_id=run_id,
            step_id=step.step_id,
            attempt=attempt,
            inputs=inputs,
            dependency_outputs=dependency_outputs,
        )
        try:
            context.raise_if_cancelled()
            output = step.handler(context)
            output_json = _json(output)
            for gate in step.quality_gates:
                result = gate.check(output, context)
                if not isinstance(result, GateResult):
                    raise TypeError(f"quality gate {gate.name} must return GateResult")
                self._record_gate(run_id, step.step_id, attempt, gate.name, result)
                if not result.passed:
                    self._mark_step(
                        run_id,
                        step.step_id,
                        StepStatus.BLOCKED,
                        error={"code": "QUALITY_GATE_FAILED", "gate": gate.name, "issues": list(result.issues)},
                    )
                    return False
            with self.store._connect() as connection, connection:
                connection.execute(
                    """
                    UPDATE workflow_steps SET status=?, output_json=?, finished_at=?
                    WHERE run_id=? AND step_id=?
                    """,
                    (StepStatus.SUCCEEDED.value, output_json, _utc_now(), run_id, step.step_id),
                )
                self.store._event(connection, run_id, step.step_id, "step_succeeded", {"attempt": attempt})
            return True
        except Exception as exc:
            retryable = not isinstance(exc, NonRetryableStepError)
            code = "STEP_RETRYABLE" if isinstance(exc, RetryableStepError) else "STEP_FAILED"
            error = {"code": code, "type": type(exc).__name__, "message": str(exc), "retryable": retryable}
            error["message"] = _redact_error(error["message"])
            self._mark_step(run_id, step.step_id, StepStatus.FAILED, error=error)
            return False

    def _recover_interrupted(self, run_id: str) -> None:
        with self.store._connect() as connection, connection:
            rows = connection.execute(
                "SELECT step_id, attempt, max_attempts FROM workflow_steps WHERE run_id=? AND status=?",
                (run_id, StepStatus.RUNNING.value),
            ).fetchall()
            for row in rows:
                next_status = (
                    StepStatus.PENDING.value
                    if int(row["attempt"]) < int(row["max_attempts"])
                    else StepStatus.FAILED.value
                )
                connection.execute(
                    "UPDATE workflow_steps SET status=?, error_json=?, finished_at=? WHERE run_id=? AND step_id=?",
                    (
                        next_status,
                        _json({"code": "INTERRUPTED", "retryable": next_status == StepStatus.PENDING.value}),
                        _utc_now(),
                        run_id,
                        row["step_id"],
                    ),
                )
                self.store._event(connection, run_id, str(row["step_id"]), "step_recovered", {"status": next_status})

    def _set_run_running(self, run_id: str) -> None:
        now = _utc_now()
        with self.store._connect() as connection, connection:
            connection.execute(
                """
                UPDATE workflow_runs SET status=?, started_at=COALESCE(started_at, ?),
                    finished_at=NULL, updated_at=? WHERE run_id=?
                """,
                (RunStatus.RUNNING.value, now, now, run_id),
            )
            self.store._event(connection, run_id, None, "run_started", {})

    def _finish_run(self, run_id: str, status: RunStatus) -> None:
        now = _utc_now()
        with self.store._connect() as connection, connection:
            connection.execute(
                "UPDATE workflow_runs SET status=?, finished_at=?, updated_at=? WHERE run_id=?",
                (status.value, now, now, run_id),
            )
            self.store._event(connection, run_id, None, "run_finished", {"status": status.value})

    def _cancel_remaining(self, run_id: str) -> None:
        with self.store._connect() as connection, connection:
            connection.execute(
                """
                UPDATE workflow_steps SET status=?, finished_at=?
                WHERE run_id=? AND status IN (?, ?, ?)
                """,
                (
                    StepStatus.CANCELLED.value,
                    _utc_now(),
                    run_id,
                    StepStatus.PENDING.value,
                    StepStatus.RUNNING.value,
                    StepStatus.FAILED.value,
                ),
            )
        self._finish_run(run_id, RunStatus.CANCELLED)

    def _block_step(self, run_id: str, step_id: str, code: str) -> None:
        self._mark_step(run_id, step_id, StepStatus.BLOCKED, error={"code": code, "retryable": False})

    def _mark_step(
        self,
        run_id: str,
        step_id: str,
        status: StepStatus,
        *,
        error: dict[str, Any],
    ) -> None:
        with self.store._connect() as connection, connection:
            connection.execute(
                """
                UPDATE workflow_steps SET status=?, error_json=?, finished_at=?
                WHERE run_id=? AND step_id=?
                """,
                (status.value, _json(error), _utc_now(), run_id, step_id),
            )
            self.store._event(connection, run_id, step_id, f"step_{status.value}", error)

    def _record_gate(
        self,
        run_id: str,
        step_id: str,
        attempt: int,
        gate_name: str,
        result: GateResult,
    ) -> None:
        with self.store._connect() as connection, connection:
            connection.execute(
                """
                INSERT INTO quality_gate_results(
                    run_id, step_id, attempt, gate_name, passed, metrics_json, issues_json, created_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    step_id,
                    attempt,
                    gate_name,
                    int(result.passed),
                    _json(result.metrics),
                    _json(list(result.issues)),
                    _utc_now(),
                ),
            )


def workflow_report(store: WorkflowStore, run_id: str) -> dict[str, Any]:
    snapshot = store.get_run(run_id)
    return {
        "schema_version": "power-rag.workflow-report.v1",
        "run_id": snapshot.run_id,
        "workflow": {"name": snapshot.workflow_name, "version": snapshot.workflow_version},
        "status": snapshot.status.value,
        "progress": snapshot.progress,
        "created_at": snapshot.created_at,
        "started_at": snapshot.started_at,
        "finished_at": snapshot.finished_at,
        "steps": [
            {
                "step_id": step.step_id,
                "status": step.status.value,
                "attempt": step.attempt,
                "max_attempts": step.max_attempts,
                "output": step.output,
                "error": step.error,
            }
            for step in snapshot.steps
        ],
        "quality_gates": store.gate_results(run_id),
    }


def _topological_steps(definition: WorkflowDefinition) -> tuple[WorkflowStep, ...]:
    resolved: list[WorkflowStep] = []
    pending = list(definition.steps)
    while pending:
        ready = [step for step in pending if all(dep in {item.step_id for item in resolved} for dep in step.depends_on)]
        if not ready:
            raise ValueError("workflow dependencies contain a cycle")
        for step in ready:
            resolved.append(step)
            pending.remove(step)
    return tuple(resolved)


def _json(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise WorkflowError(
            "OUTPUT_NOT_SERIALIZABLE", "Workflow inputs, outputs, and checkpoints must be finite JSON data."
        ) from exc


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _redact_error(message: str) -> str:
    redacted = re.sub(r"(?i)(api[_-]?key|token|password|secret)\s*[:=]\s*[^\s;,]+", r"\1=<REDACTED>", message)
    redacted = re.sub(r"(?i)bearer\s+[A-Za-z0-9._-]+", "Bearer <REDACTED>", redacted)
    redacted = re.sub(r"\bsk-[A-Za-z0-9_-]{8,}\b", "<REDACTED>", redacted)
    redacted = re.sub(r"[A-Za-z]:\\[^\s;,]+", "<PATH>", redacted)
    return redacted
