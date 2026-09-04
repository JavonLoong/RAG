"""Offline full FMEA acceptance using real application services and SQLite."""
# ruff: noqa: TRY003

from __future__ import annotations

import argparse
import importlib.util
import io
import json
import os
import stat
import sys
import tempfile
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from types import ModuleType
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "graphrag.fmea.full.acceptance.v1"
DEFAULT_OUTPUT_ROOT = ROOT / "observability/reports/fmea-full-acceptance"


def _load_slice_module() -> ModuleType:
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    source = root / "examples" / "fmea" / "full-acceptance" / "candidate_review_risk_slice.py"
    name = "fmea_candidate_review_risk_slice"
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(name, source)
    if spec is None or spec.loader is None:
        raise RuntimeError("candidate/review/risk slice helper is not loadable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def run_candidate_review_risk(work_dir: str | Path):
    """Run one bounded fuel candidate -> review -> risk attempt."""

    return _load_slice_module().run_candidate_review_risk(work_dir)


def _load_helper(stem: str):
    _load_slice_module()
    name = f"fmea_full_{stem}"
    if name not in sys.modules:
        source = ROOT / "examples/fmea/full-acceptance" / f"{stem}.py"
        spec = importlib.util.spec_from_file_location(name, source)
        if spec is None or spec.loader is None:
            raise RuntimeError("acceptance helper cannot load")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


@dataclass(frozen=True)
class FullAcceptanceRun:
    artifact_dir: Path
    summary: dict[str, int]


def _merge_case(case, additions):
    for name, values in additions.items():
        if name in {"audits", "outbox", "schema_version", "case_id"}:
            continue  # Collect once from final authoritative persistence.
        if isinstance(values, list):
            case.setdefault(name, []).extend(values)
        else:
            case[name] = values


def _safe_root(path):
    candidate = Path(path).absolute()
    current = Path(candidate.anchor)
    for part in candidate.parts[1:]:
        if part in {".", ".."}:
            raise ValueError("invalid output path")
        current /= part
        current.mkdir(exist_ok=True)
        info = current.lstat()
        if (
            not stat.S_ISDIR(info.st_mode)
            or stat.S_ISLNK(info.st_mode)
            or getattr(info, "st_file_attributes", 0) & 0x400
        ):
            raise ValueError("output directory must not contain links")
    return candidate


def _domain_proofs(registry_root):
    from fmea_infrastructure.domain_pack_registry import (
        FileDomainPackRegistry,
        FileScoringRuleRegistry,
        load_domain_pack_manifest,
        load_scoring_rule_pack,
    )
    from structured_output_application import TemplateCompiler
    from structured_output_infrastructure import Draft202012SchemaAdapter, FileTemplateRegistry, load_template_source

    proofs = []
    for pack_id in ("fuel-combustion", "electrical-demo", "software-demo"):
        pack_root = ROOT / "domain_packs" / pack_id
        template_path = (
            ROOT / "templates/examples/fuel-combustion-fmea.yaml"
            if pack_id == "fuel-combustion"
            else pack_root / "templates/fmea.yaml"
        )
        scoring_path = pack_root / (
            "scoring/sod-rpn-1.0.0.yaml" if pack_id == "fuel-combustion" else "scoring/sod-rpn.yaml"
        )
        pack_source = (pack_root / "manifest.yaml").read_bytes()
        pack = load_domain_pack_manifest(pack_source)
        FileDomainPackRegistry(registry_root / "domain").register(pack, pack_source)
        rule_source = scoring_path.read_bytes()
        rule = load_scoring_rule_pack(rule_source)
        FileScoringRuleRegistry(registry_root / "scoring").register(rule, rule_source)
        template = TemplateCompiler(
            schema_validator=Draft202012SchemaAdapter(), source_loader=load_template_source
        ).compile_path(template_path)
        FileTemplateRegistry(registry_root / "templates").register(
            template, template_path.read_bytes(), template_path.suffix
        )
        proofs.append({
            "pack_id": pack.pack_id,
            "version": pack.version,
            "content_hash": pack.content_hash,
            "coverage": "registry_compile",
            "template_id": template.metadata.template_id,
            "template_version": template.metadata.version,
            "kernel_schema_id": "graphrag.fmea.v1",
            "scoring_rule_id": rule.rule_pack_id,
        })
    return proofs


def run_full_acceptance(*, output_root: str | Path = DEFAULT_OUTPUT_ROOT) -> FullAcceptanceRun:
    root = _safe_root(output_root)
    artifact_id = str(uuid4())
    summary = dict.fromkeys(
        (
            "model_approval_count",
            "known_without_evidence_count",
            "confirmed_invalid_score_count",
            "accepted_high_risk_evidence_free_edge_count",
        ),
        0,
    )
    governance = _load_helper("governance_delivery_slice")
    with tempfile.TemporaryDirectory(prefix="fmea-full-work-") as temporary:
        work = Path(temporary)
        source = run_candidate_review_risk(work)
        propagation = _load_helper("propagation_slice").run_propagation(
            database_path=work / "fmea.sqlite3",
            analysis=source.analysis,
            row=source.row,
            assessment=source.assessment,
            evidence_pack=source.evidence_pack,
            registry_root=work / "immutable-registries",
        )
        connected = governance.GovernanceDeliveryRun(work / "fmea.sqlite3", source, propagation.graph, work)
        parent, parent_publication = connected.publish()
        child, child_publication = connected.publish(parent=parent, offset=200)
        # A new plain template, not the presentation export (which has print
        # defined-names intentionally rejected by the strict import boundary).
        from openpyxl import Workbook

        workbook = Workbook()
        workbook.active.title = "FMEA template"
        workbook.active.append(["failure_mode", "legacy_criticality"])
        workbook.active.append(["fuel filter blockage", "review required"])
        buffer = io.BytesIO()
        workbook.save(buffer)
        workbook.close()
        import_bytes = buffer.getvalue()
        migration = _load_helper("migration_slice").run_migration(
            database_path=work / "fmea.sqlite3",
            source_revision=parent,
            registry_root=work / "immutable-registries",
            workspace_id=source.evidence_pack.workspace_id,
            import_bytes=import_bytes,
        )
        connected.finish(parent_publication, child_publication)
        case = dict(source.evidence)
        case.pop("schema_version")
        case["coverage"] = "full_lifecycle"
        case["analyses"] = [governance.public(source.analysis)]
        case["evidence_selection"] = {
            "mode": "offline_source_fixture",
            "requested_profile": "rag_only",
            "resolved_profile": "rag_only",
            "selected_evidence_ids": [ref.evidence_id for ref in source.evidence_pack.refs],
            "pack_id": source.evidence_pack.pack_id,
            "pack_hash": source.evidence_pack.pack_hash,
        }
        case["steps"].insert(
            0,
            {
                "step_id": "evidence-selection",
                "command": "evidence.select",
                "actor_id": "fixture-source",
                "actor_type": "system",
                "request_identity": {"profile": "rag_only"},
                "before": {"source_count": 1},
                "after": {"selected_count": len(source.evidence_pack.refs)},
                "result_ids": {"pack_id": source.evidence_pack.pack_id},
            },
        )
        _merge_case(case, propagation.evidence)
        _merge_case(case, connected.evidence)
        _merge_case(case, migration.evidence)
        case["template_import_sources"] = [
            {
                "path": "inputs/template.xlsx",
                "sha256": sha256(import_bytes).hexdigest(),
                "byte_length": len(import_bytes),
            }
        ]
        case["audits"], case["outbox"] = governance.persisted_events(
            work / "fmea.sqlite3", source.evidence_pack.workspace_id
        )
        evidence = {
            "schema_version": SCHEMA_VERSION,
            "cases": [case],
            "domain_proofs": _domain_proofs(work / "immutable-registries"),
        }
        payloads = {
            **connected.payloads,
            "inputs/template.xlsx": import_bytes,
            "evidence.json": json.dumps(
                evidence, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode("utf-8"),
        }
    # Fresh contained staging; only public DTOs and verified artifact bytes leave the private run.
    staging = root / f".pending-{artifact_id}"
    staging.mkdir()
    (staging / "exports").mkdir()
    (staging / "inputs").mkdir()
    for relative, payload in payloads.items():
        with (staging / relative).open("xb") as stream:
            stream.write(payload)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "artifact_id": artifact_id,
        "cases": ["fuel-combustion"],
        "summary": summary,
        "files": {
            name: {"sha256": sha256(payload).hexdigest(), "size_bytes": len(payload)}
            for name, payload in payloads.items()
        },
    }
    with (staging / "manifest.json").open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, sort_keys=True)
    from scripts.verify_fmea_full_acceptance import verify_acceptance_directory

    verified = verify_acceptance_directory(staging)
    if not verified.passed:
        raise ValueError(f"full acceptance verification failed: {verified.error_code}; pending artifact: {staging}")
    destination = root / artifact_id
    staging.rename(destination)
    pointer = root / f".latest-{artifact_id}.json"
    with pointer.open("x", encoding="utf-8") as stream:
        json.dump({"artifact_id": artifact_id}, stream)
    os.replace(pointer, root / "latest.json")
    return FullAcceptanceRun(destination, summary)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args()
    try:
        result = run_full_acceptance(output_root=args.output_root)
    except Exception as exc:
        error_code = getattr(exc, "code", None)
        print(
            json.dumps(
                {
                    "status": "error",
                    "error_code": error_code if isinstance(error_code, str) else type(exc).__name__,
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    print(
        json.dumps(
            {
                "status": "passed",
                "schema_version": SCHEMA_VERSION,
                "artifact_id": result.artifact_dir.name,
                "summary": result.summary,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
