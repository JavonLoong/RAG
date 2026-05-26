"""Experiment management utilities for GraphRAG.

Provides tools for running, tracking, and comparing experiments
with different configurations and parameters.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


EXPERIMENTS_DIR = Path(__file__).resolve().parent


@dataclass(slots=True)
class ExperimentRecord:
    """A single experiment run record."""
    experiment_id: str
    name: str
    config: dict[str, Any]
    results: dict[str, Any] = field(default_factory=dict)
    started_at: str = ""
    completed_at: str = ""
    status: str = "pending"  # "pending" | "running" | "completed" | "failed"
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "name": self.name,
            "config": self.config,
            "results": self.results,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "status": self.status,
            "notes": self.notes,
        }


class ExperimentTracker:
    """Tracks experiment runs and their results."""

    def __init__(self, output_dir: str | Path | None = None) -> None:
        self.output_dir = Path(output_dir) if output_dir else EXPERIMENTS_DIR / "runs"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def create(self, name: str, config: dict[str, Any]) -> ExperimentRecord:
        experiment_id = f"{name}_{int(time.time())}"
        return ExperimentRecord(
            experiment_id=experiment_id,
            name=name,
            config=config,
            started_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
            status="running",
        )

    def complete(self, record: ExperimentRecord, results: dict[str, Any]) -> None:
        record.results = results
        record.completed_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        record.status = "completed"
        self._save(record)

    def fail(self, record: ExperimentRecord, error: str) -> None:
        record.completed_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        record.status = "failed"
        record.notes = error
        self._save(record)

    def _save(self, record: ExperimentRecord) -> None:
        path = self.output_dir / f"{record.experiment_id}.json"
        path.write_text(
            json.dumps(record.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def list_experiments(self) -> list[dict[str, Any]]:
        results = []
        for path in sorted(self.output_dir.glob("*.json"), reverse=True):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                results.append(data)
            except (json.JSONDecodeError, OSError):
                continue
        return results
