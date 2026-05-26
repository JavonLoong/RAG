"""Observability layer for the GraphRAG system.

Provides structured logging, performance tracing, and error attribution
to support debugging and monitoring of the RAG pipeline.
"""
from __future__ import annotations

import json
import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Generator

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class TraceSpan:
    """A single span in a trace, representing one operation."""
    name: str
    started_at: float
    ended_at: float = 0.0
    duration_ms: float = 0.0
    status: str = "ok"
    attributes: dict[str, Any] = field(default_factory=dict)
    children: list[TraceSpan] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result = {
            "name": self.name,
            "duration_ms": round(self.duration_ms, 2),
            "status": self.status,
            "attributes": self.attributes,
        }
        if self.error:
            result["error"] = self.error
        if self.children:
            result["children"] = [c.to_dict() for c in self.children]
        return result


class Tracer:
    """Lightweight tracer for recording operation durations and metadata.

    Usage:
        tracer = Tracer()
        with tracer.span("retrieval", query=query):
            results = retriever.retrieve(query)
        with tracer.span("generation"):
            answer = llm.generate(prompt)
        print(tracer.to_dict())
    """

    def __init__(self, name: str = "graphrag") -> None:
        self.name = name
        self.spans: list[TraceSpan] = []
        self._stack: list[TraceSpan] = []
        self.started_at = time.time()

    @contextmanager
    def span(self, name: str, **attributes: Any) -> Generator[TraceSpan, None, None]:
        """Create a trace span that measures execution time."""
        span = TraceSpan(name=name, started_at=time.time(), attributes=attributes)
        self._stack.append(span)
        try:
            yield span
            span.status = "ok"
        except Exception as exc:
            span.status = "error"
            span.error = str(exc)
            raise
        finally:
            span.ended_at = time.time()
            span.duration_ms = (span.ended_at - span.started_at) * 1000
            self._stack.pop()
            if self._stack:
                self._stack[-1].children.append(span)
            else:
                self.spans.append(span)

    @property
    def total_duration_ms(self) -> float:
        return sum(s.duration_ms for s in self.spans)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tracer": self.name,
            "total_duration_ms": round(self.total_duration_ms, 2),
            "span_count": self._count_spans(self.spans),
            "spans": [s.to_dict() for s in self.spans],
        }

    def _count_spans(self, spans: list[TraceSpan]) -> int:
        count = len(spans)
        for s in spans:
            count += self._count_spans(s.children)
        return count


class PerformanceMonitor:
    """Collects and reports performance metrics for the RAG pipeline."""

    def __init__(self) -> None:
        self.metrics: dict[str, list[float]] = {}

    def record(self, metric_name: str, value: float) -> None:
        """Record a metric value."""
        if metric_name not in self.metrics:
            self.metrics[metric_name] = []
        self.metrics[metric_name].append(value)

    def summary(self) -> dict[str, dict[str, float]]:
        """Get summary statistics for all recorded metrics."""
        result = {}
        for name, values in self.metrics.items():
            if not values:
                continue
            result[name] = {
                "count": len(values),
                "mean": sum(values) / len(values),
                "min": min(values),
                "max": max(values),
                "total": sum(values),
            }
        return result


class StructuredLogger:
    """Structured logger that outputs JSON-formatted log entries.

    Wraps Python's logging module to add structured context fields.
    """

    def __init__(self, name: str = "graphrag", log_dir: str | Path | None = None) -> None:
        self.logger = logging.getLogger(name)
        self.context: dict[str, Any] = {}
        if log_dir:
            log_path = Path(log_dir)
            log_path.mkdir(parents=True, exist_ok=True)
            handler = logging.FileHandler(
                log_path / f"{name}.log", encoding="utf-8"
            )
            handler.setFormatter(logging.Formatter("%(message)s"))
            self.logger.addHandler(handler)

    def with_context(self, **kwargs: Any) -> StructuredLogger:
        """Create a new logger with additional context fields."""
        new_logger = StructuredLogger.__new__(StructuredLogger)
        new_logger.logger = self.logger
        new_logger.context = {**self.context, **kwargs}
        return new_logger

    def _emit(self, level: str, event: str, **kwargs: Any) -> None:
        entry = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "level": level,
            "event": event,
            **self.context,
            **kwargs,
        }
        self.logger.log(
            getattr(logging, level.upper(), logging.INFO),
            json.dumps(entry, ensure_ascii=False, default=str),
        )

    def info(self, event: str, **kwargs: Any) -> None:
        self._emit("info", event, **kwargs)

    def warning(self, event: str, **kwargs: Any) -> None:
        self._emit("warning", event, **kwargs)

    def error(self, event: str, **kwargs: Any) -> None:
        self._emit("error", event, **kwargs)

    def debug(self, event: str, **kwargs: Any) -> None:
        self._emit("debug", event, **kwargs)
