"""Versioned, approved FMEA template registry."""

# ruff: noqa: TRY003

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from core_domain.delivery import FMEA_FIELDS


class FMEATemplateError(ValueError):
    """Raised when a requested FMEA template is unavailable or invalid."""

    def __init__(self, message: str, *, code: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.details = dict(details or {})


@dataclass(frozen=True, slots=True)
class FMEATemplate:
    template_id: str
    version: str
    status: str
    description: str
    fields: tuple[dict[str, Any], ...]
    graph_constraints: dict[str, Any]
    evidence_policy: dict[str, Any]
    scoring_policy: dict[str, Any]
    report_layout: dict[str, Any]
    source_path: str
    content_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "template_id": self.template_id,
            "version": self.version,
            "status": self.status,
            "description": self.description,
            "fields": [dict(item) for item in self.fields],
            "graph_constraints": dict(self.graph_constraints),
            "evidence_policy": dict(self.evidence_policy),
            "scoring_policy": dict(self.scoring_policy),
            "report_layout": dict(self.report_layout),
            "source_path": self.source_path,
            "content_hash": self.content_hash,
        }

    def lineage(self) -> dict[str, str]:
        return {
            "template_id": self.template_id,
            "template_version": self.version,
            "template_content_hash": self.content_hash,
        }


class FMEATemplateRegistry:
    """Load immutable template definitions from the repository configuration."""

    def __init__(
        self,
        template_dir: str | Path | None = None,
        *,
        definitions: Sequence[Mapping[str, Any]] = (),
    ) -> None:
        self.template_dir = Path(template_dir or Path(__file__).resolve().parents[1] / "configs" / "fmea")
        self.definitions = tuple(dict(item) for item in definitions)

    def list(self, *, approved_only: bool = True) -> tuple[FMEATemplate, ...]:
        by_version = {
            (item.template_id, item.version): item
            for item in (self._load(path) for path in sorted(self.template_dir.glob("*.yaml")))
        }
        for record in self.definitions:
            item = self._load_definition(record)
            by_version[(item.template_id, item.version)] = item
        templates = tuple(by_version[key] for key in sorted(by_version))
        if approved_only:
            templates = tuple(item for item in templates if item.status == "approved")
        return templates

    def get(self, template_id: str, version: str | None = None) -> FMEATemplate:
        clean_id = str(template_id or "").strip()
        clean_version = str(version).strip() if version not in (None, "") else None
        matches = [item for item in self.list(approved_only=True) if item.template_id == clean_id]
        if clean_version:
            matches = [item for item in matches if item.version == clean_version]
        if not matches:
            raise FMEATemplateError(
                f"Unknown or unapproved FMEA template: {clean_id}"
                + (f" version {clean_version}" if clean_version else ""),
                code="fmea_template_not_found",
                details={"template": clean_id, "template_version": clean_version},
            )
        return sorted(matches, key=lambda item: item.version)[-1]

    def _load(self, path: Path) -> FMEATemplate:
        raw = path.read_bytes()
        try:
            payload = yaml.safe_load(raw.decode("utf-8")) or {}
        except (UnicodeDecodeError, yaml.YAMLError) as exc:
            raise FMEATemplateError(
                f"Invalid FMEA template file: {path}",
                code="invalid_fmea_template",
                details={"source_path": str(path)},
            ) from exc
        return self._from_payload(
            payload,
            source_path=str(path.resolve()),
            content_hash=hashlib.sha256(raw).hexdigest(),
        )

    def _load_definition(self, record: Mapping[str, Any]) -> FMEATemplate:
        payload = dict(record.get("definition") or record)
        if record.get("status"):
            payload["status"] = record["status"]
        template_id = str(record.get("template_id") or payload.get("template") or "").strip()
        version = str(record.get("version") or payload.get("version") or "").strip()
        payload["template"] = template_id
        payload["version"] = version
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return self._from_payload(
            payload,
            source_path=f"project-catalog://{template_id}/{version}",
            content_hash=str(record.get("content_hash") or hashlib.sha256(canonical.encode()).hexdigest()),
        )

    def _from_payload(
        self,
        payload: Mapping[str, Any],
        *,
        source_path: str,
        content_hash: str,
    ) -> FMEATemplate:
        template_id = str(payload.get("template") or "").strip()
        version = str(payload.get("version") or "").strip()
        status = str(payload.get("status") or "draft").strip().lower()
        raw_fields = payload.get("fields") or []
        field_names = tuple(str(item.get("name") or "").strip() for item in raw_fields if isinstance(item, dict))
        if not template_id or not version:
            raise FMEATemplateError(
                f"Template ID and version are required: {source_path}",
                code="invalid_fmea_template",
                details={"source_path": source_path},
            )
        if field_names != FMEA_FIELDS:
            raise FMEATemplateError(
                f"Template {template_id} fields must exactly match the governed FMEA contract",
                code="invalid_fmea_template_fields",
                details={"expected": list(FMEA_FIELDS), "actual": list(field_names)},
            )
        report_layout = dict(payload.get("report_layout") or {})
        orientation = str(report_layout.get("orientation") or "landscape").lower()
        if orientation not in {"landscape", "portrait"}:
            raise FMEATemplateError(
                f"Template {template_id} report orientation is invalid",
                code="invalid_fmea_report_template",
                details={"orientation": orientation},
            )
        report_layout["orientation"] = orientation
        report_layout.setdefault("title", "PowerRAG 可信 FMEA 正式交付表")
        report_layout.setdefault("font", "Microsoft YaHei")
        report_layout.setdefault("accent_color", "1F4E79")
        return FMEATemplate(
            template_id=template_id,
            version=version,
            status=status,
            description=str(payload.get("description") or "").strip(),
            fields=tuple(dict(item) for item in raw_fields),
            graph_constraints=dict(payload.get("graph_constraints") or {}),
            evidence_policy=dict(payload.get("evidence_policy") or {}),
            scoring_policy=dict(payload.get("scoring_policy") or {}),
            report_layout=report_layout,
            source_path=source_path,
            content_hash=content_hash,
        )
