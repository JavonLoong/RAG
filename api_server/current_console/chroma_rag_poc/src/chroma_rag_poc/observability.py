"""Runtime operation logging for upload and ingestion flows."""
from __future__ import annotations

import json
import os
import re
import time
import traceback
import uuid
from contextlib import AbstractContextManager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _safe_segment(value: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z._-]+", "-", value.strip())
    cleaned = cleaned.strip(".-")
    return cleaned or "operation"


def _json_default(value: Any) -> str:
    if isinstance(value, Path):
        return str(value)
    return str(value)


class _NullStage(AbstractContextManager):
    def __enter__(self) -> "_NullStage":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


class NullOperationLogger:
    """No-op logger used when callers do not request an operation log."""

    file_name: str | None = None
    file_path: Path | None = None

    def info(self, event: str, **fields: Any) -> None:
        del event, fields

    def warning(self, event: str, **fields: Any) -> None:
        del event, fields

    def error(self, event: str, **fields: Any) -> None:
        del event, fields

    def exception(self, event: str, exc: BaseException, **fields: Any) -> None:
        del event, exc, fields

    def stage(self, name: str, **fields: Any) -> _NullStage:
        del name, fields
        return _NullStage()

    def close(self, status: str = "ok", **fields: Any) -> None:
        del status, fields


class OperationLogger:
    """Append-only per-operation logger.

    The log format is line-oriented text with a JSON payload per line, so it is
    readable in Notepad and still easy to parse when debugging large failures.
    """

    def __init__(self, log_dir: str | Path, operation: str, **context: Any) -> None:
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.operation = _safe_segment(operation)
        self.run_id = uuid.uuid4().hex[:12]
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.file_name = f"{timestamp}-{self.operation}-{self.run_id}.log"
        self.file_path = self.log_dir / self.file_name
        self._started_wall = time.perf_counter()
        self._started_cpu = time.process_time()
        self._closed = False
        self.info(
            "operation_start",
            operation=self.operation,
            run_id=self.run_id,
            pid=os.getpid(),
            **context,
        )

    def info(self, event: str, **fields: Any) -> None:
        self._write("INFO", event, fields)

    def warning(self, event: str, **fields: Any) -> None:
        self._write("WARNING", event, fields)

    def error(self, event: str, **fields: Any) -> None:
        self._write("ERROR", event, fields)

    def exception(self, event: str, exc: BaseException, **fields: Any) -> None:
        self._write(
            "ERROR",
            event,
            {
                **fields,
                "error_type": type(exc).__name__,
                "error": str(exc),
                "traceback": "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
            },
        )

    def stage(self, name: str, **fields: Any) -> "OperationStage":
        return OperationStage(self, name, fields)

    def close(self, status: str = "ok", **fields: Any) -> None:
        if self._closed:
            self.warning("operation_close_ignored", requested_status=status)
            return

        extras = dict(fields)
        if "elapsed_s" in extras:
            extras["reported_elapsed_s"] = extras.pop("elapsed_s")
        if "cpu_s" in extras:
            extras["reported_cpu_s"] = extras.pop("cpu_s")
        self.info(
            "operation_end",
            status=status,
            elapsed_s=round(time.perf_counter() - self._started_wall, 3),
            cpu_s=round(time.process_time() - self._started_cpu, 3),
            **extras,
        )
        self._closed = True

    def _write(self, level: str, event: str, fields: dict[str, Any]) -> None:
        payload = {
            "ts": _utc_now(),
            "level": level,
            "event": event,
            "run_id": self.run_id,
            **fields,
        }
        line = f"{payload['ts']} {level:<7} {event} {json.dumps(payload, ensure_ascii=False, default=_json_default)}\n"
        with self.file_path.open("a", encoding="utf-8") as handle:
            handle.write(line)


class OperationStage(AbstractContextManager):
    def __init__(self, logger: OperationLogger, name: str, fields: dict[str, Any]) -> None:
        self.logger = logger
        self.name = name
        self.fields = fields
        self._started_wall = 0.0
        self._started_cpu = 0.0

    def __enter__(self) -> "OperationStage":
        self._started_wall = time.perf_counter()
        self._started_cpu = time.process_time()
        self.logger.info(f"{self.name}_start", **self.fields)
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        elapsed_s = round(time.perf_counter() - self._started_wall, 3)
        cpu_s = round(time.process_time() - self._started_cpu, 3)
        if exc is None:
            self.logger.info(f"{self.name}_ok", elapsed_s=elapsed_s, cpu_s=cpu_s, **self.fields)
            return False

        self.logger.exception(
            f"{self.name}_error",
            exc,
            elapsed_s=elapsed_s,
            cpu_s=cpu_s,
            **self.fields,
        )
        return False
