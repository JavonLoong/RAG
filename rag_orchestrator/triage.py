from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _record_date(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "unknown"
    normalized = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    try:
        return datetime.fromisoformat(normalized).date().isoformat()
    except ValueError:
        return raw[:10] if len(raw) >= 10 else "unknown"


@dataclass(slots=True)
class GraphRagTriageStore:
    path: Path

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, record: dict[str, Any]) -> dict[str, Any]:
        item = dict(record)
        item.setdefault("id", f"triage-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:8]}")
        item.setdefault("created_at", utc_now_iso())
        item.setdefault("review_status", "unreviewed")
        item.setdefault("review_note", "")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")
        return item

    def list(
        self,
        *,
        limit: int = 50,
        graph_quality_status: str = "",
        review_status: str = "",
        route_strategy: str = "",
    ) -> list[dict[str, Any]]:
        records = self._filter_records(
            graph_quality_status=graph_quality_status,
            review_status=review_status,
            route_strategy=route_strategy,
        )
        records.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        return records[: max(0, int(limit))]

    def get(self, triage_id: str) -> dict[str, Any] | None:
        for item in self._read_all():
            if item.get("id") == triage_id:
                return item
        return None

    def review(self, triage_id: str, *, review_status: str, review_note: str = "") -> dict[str, Any] | None:
        records = self._read_all()
        updated: dict[str, Any] | None = None
        for item in records:
            if item.get("id") != triage_id:
                continue
            item["review_status"] = str(review_status or "unreviewed")
            item["review_note"] = str(review_note or "")
            item["reviewed_at"] = utc_now_iso()
            updated = item
            break
        if updated is None:
            return None
        self._write_all(records)
        return updated

    def mark_promoted(self, triage_id: str, *, evaluation_case_id: str, dataset_path: str | Path) -> dict[str, Any] | None:
        records = self._read_all()
        updated: dict[str, Any] | None = None
        for item in records:
            if item.get("id") != triage_id:
                continue
            item["evaluation_case_id"] = str(evaluation_case_id)
            item["promoted_dataset_path"] = str(dataset_path)
            item["promoted_at"] = utc_now_iso()
            updated = item
            break
        if updated is None:
            return None
        self._write_all(records)
        return updated

    def analytics(
        self,
        *,
        graph_quality_status: str = "",
        review_status: str = "",
        route_strategy: str = "",
    ) -> dict[str, Any]:
        records = self._filter_records(
            graph_quality_status=graph_quality_status,
            review_status=review_status,
            route_strategy=route_strategy,
        )
        by_quality: Counter[str] = Counter()
        by_review: Counter[str] = Counter()
        by_route: Counter[str] = Counter()
        by_failure_metric: Counter[str] = Counter()
        failure_trend: dict[str, dict[str, Any]] = {}
        route_drilldown: dict[str, dict[str, Any]] = {}
        source_covered = 0
        source_missing = 0
        promoted = 0
        total_source_evidence = 0

        for item in records:
            quality = str(item.get("graph_quality_status") or "unknown")
            review = str(item.get("review_status") or "unreviewed")
            route = str((item.get("route") or {}).get("strategy") or item.get("strategy") or "UNKNOWN")
            by_quality[quality] += 1
            by_review[review] += 1
            by_route[route] += 1
            source_count = int(item.get("source_evidence_count") or 0)
            total_source_evidence += source_count
            is_source_covered = source_count > 0
            if source_count > 0:
                source_covered += 1
            else:
                source_missing += 1
            is_promoted = bool(item.get("evaluation_case_id"))
            if item.get("evaluation_case_id"):
                promoted += 1
            date_key = _record_date(item.get("created_at"))
            trend = failure_trend.setdefault(
                date_key,
                {
                    "date": date_key,
                    "total_count": 0,
                    "fail_count": 0,
                    "pass_count": 0,
                    "source_missing_count": 0,
                    "promoted_case_count": 0,
                },
            )
            trend["total_count"] += 1
            if quality == "fail":
                trend["fail_count"] += 1
            if quality == "pass":
                trend["pass_count"] += 1
            if not is_source_covered:
                trend["source_missing_count"] += 1
            if is_promoted:
                trend["promoted_case_count"] += 1

            route_bucket = route_drilldown.setdefault(
                route,
                {
                    "route_strategy": route,
                    "total_count": 0,
                    "pass_count": 0,
                    "fail_count": 0,
                    "accepted_count": 0,
                    "rejected_count": 0,
                    "unreviewed_count": 0,
                    "source_covered_count": 0,
                    "source_missing_count": 0,
                    "promoted_case_count": 0,
                    "failure_metrics": Counter(),
                },
            )
            route_bucket["total_count"] += 1
            if quality == "pass":
                route_bucket["pass_count"] += 1
            if quality == "fail":
                route_bucket["fail_count"] += 1
            if review == "accepted":
                route_bucket["accepted_count"] += 1
            elif review == "rejected":
                route_bucket["rejected_count"] += 1
            else:
                route_bucket["unreviewed_count"] += 1
            if is_source_covered:
                route_bucket["source_covered_count"] += 1
            else:
                route_bucket["source_missing_count"] += 1
            if is_promoted:
                route_bucket["promoted_case_count"] += 1
            quality_gate = ((item.get("graph_quality") or {}).get("quality_gate") or {})
            for failure in quality_gate.get("failures") or []:
                metric = str((failure or {}).get("metric") or "unknown")
                by_failure_metric[metric] += 1
                route_bucket["failure_metrics"][metric] += 1

        total = len(records)
        route_drilldown_items = []
        for route, bucket in sorted(route_drilldown.items()):
            route_total = int(bucket["total_count"] or 0)
            route_drilldown_items.append(
                {
                    "route_strategy": route,
                    "total_count": route_total,
                    "pass_count": int(bucket["pass_count"]),
                    "fail_count": int(bucket["fail_count"]),
                    "accepted_count": int(bucket["accepted_count"]),
                    "rejected_count": int(bucket["rejected_count"]),
                    "unreviewed_count": int(bucket["unreviewed_count"]),
                    "source_coverage_rate": round(int(bucket["source_covered_count"]) / route_total, 6)
                    if route_total
                    else 0.0,
                    "source_missing_count": int(bucket["source_missing_count"]),
                    "promoted_case_count": int(bucket["promoted_case_count"]),
                    "failure_metrics": dict(sorted(bucket["failure_metrics"].items())),
                }
            )
        return {
            "total_count": total,
            "by_graph_quality_status": dict(sorted(by_quality.items())),
            "by_review_status": dict(sorted(by_review.items())),
            "by_route_strategy": dict(sorted(by_route.items())),
            "by_failure_metric": dict(sorted(by_failure_metric.items())),
            "failure_trend": [failure_trend[key] for key in sorted(failure_trend)],
            "route_drilldown": route_drilldown_items,
            "promoted_case_count": promoted,
            "source_evidence": {
                "covered_count": source_covered,
                "missing_count": source_missing,
                "coverage_rate": round(source_covered / total, 6) if total else 0.0,
                "average_count": round(total_source_evidence / total, 6) if total else 0.0,
            },
        }

    def _filter_records(
        self,
        *,
        graph_quality_status: str = "",
        review_status: str = "",
        route_strategy: str = "",
    ) -> list[dict[str, Any]]:
        records = self._read_all()
        if graph_quality_status:
            expected = graph_quality_status.strip().lower()
            records = [item for item in records if str(item.get("graph_quality_status") or "").lower() == expected]
        if review_status:
            expected = review_status.strip().lower()
            records = [item for item in records if str(item.get("review_status") or "").lower() == expected]
        if route_strategy:
            expected = route_strategy.strip().lower()
            records = [
                item
                for item in records
                if str((item.get("route") or {}).get("strategy") or item.get("strategy") or "").lower() == expected
            ]
        return records

    def _read_all(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        records: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict) and payload.get("id"):
                records.append(payload)
        return records

    def _write_all(self, records: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        body = "".join(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in records)
        self.path.write_text(body, encoding="utf-8")
