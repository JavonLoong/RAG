"""Build a deterministic offline FMEA risk acceptance artifact pack."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from collections.abc import Iterator, Mapping
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core_domain.fmea.scoring import (  # noqa: E402
    RiskAssessmentRecord,
    RiskProposal,
    ScoreDimension,
    validate_risk_confirmation,
)
from core_domain.fmea.states import RiskStatus  # noqa: E402
from core_domain.fmea.value_objects import EvidencePack, EvidenceRef, VersionSet  # noqa: E402
from fmea_infrastructure.domain_pack_registry import load_scoring_rule_pack  # noqa: E402

SCHEMA_VERSION = "graphrag.fmea.risk.acceptance.v1"
RETRIEVAL_MODES = (
    "rag_only",
    "graphrag_local",
    "graphrag_global",
    "graphrag_only",
    "combined",
    "auto",
    "custom",
)
ARTIFACT_NAMES = (
    "analysis-scope-suggestion.json",
    "proposal.json",
    "confirmation.json",
    "invalidation.json",
    "audit-summary.json",
    "acceptance-summary.json",
)
CASES = ("analysis_scope", "confirmed", "unknown", "conflict", "invalidated")

_FIXTURE_PATH = ROOT / "examples" / "fmea" / "risk" / "fuel-combustion" / "mode-fixtures.json"
_RULE_PATH = ROOT / "domain_packs" / "fuel-combustion" / "scoring" / "sod-rpn-1.0.0.yaml"
_UTC = "2026-08-28T00:00:00Z"
_WORKSPACE_ID = "fuel-combustion-acceptance"
_RETRIEVAL_BACKEND_PREFIXES = ("chromadb", "graphrag", "neo4j", "igraph")


def _loaded_retrieval_backends() -> frozenset[str]:
    return frozenset(
        name
        for name in sys.modules
        if any(name == prefix or name.startswith(prefix + ".") for prefix in _RETRIEVAL_BACKEND_PREFIXES)
    )


_INITIAL_RETRIEVAL_BACKENDS = _loaded_retrieval_backends()


def _assert_backend_isolation() -> list[str]:
    backend_imports = sorted(_loaded_retrieval_backends() - _INITIAL_RETRIEVAL_BACKENDS)
    if backend_imports:
        raise AcceptanceRunError("BACKEND_ISOLATION_VIOLATION")
    return backend_imports


class AcceptanceRunError(ValueError):
    """Stable runner failure that never includes local paths or input values."""

    def __init__(self, code: str) -> None:
        super().__init__("FMEA risk acceptance failed.")
        self.code = code


@dataclass(frozen=True, slots=True)
class AcceptanceRun(Mapping[str, object]):
    artifact_dir: Path
    summary: dict[str, object]
    artifact_bytes: tuple[bytes, ...]

    def __getitem__(self, key: str) -> object:
        return self.summary[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.summary)

    def __len__(self) -> int:
        return len(self.summary)


def _canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _hash_bytes(value: bytes) -> str:
    return "sha256:" + sha256(value).hexdigest()


def _stable_uuid(label: str) -> str:
    digest = sha256(label.encode("utf-8")).hexdigest()
    return f"{digest[:8]}-{digest[8:12]}-4{digest[13:16]}-8{digest[17:20]}-{digest[20:32]}"


def _json_value(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return _json_value(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_json_value(item) for item in value]
    return value


def _load_fixture() -> dict[str, Any]:
    try:
        value = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AcceptanceRunError("FIXTURE_INVALID") from exc
    if not isinstance(value, dict) or value.get("schema_version") != "graphrag.fmea.risk.fixture.v1":
        raise AcceptanceRunError("FIXTURE_INVALID")
    return value


def _evidence_pack(fixture: dict[str, Any], retrieval_mode: str) -> EvidencePack:
    modes = fixture.get("modes")
    evidence = fixture.get("evidence")
    if not isinstance(modes, dict) or not isinstance(evidence, dict):
        raise AcceptanceRunError("FIXTURE_INVALID")
    selected = modes.get(retrieval_mode)
    if not isinstance(selected, list) or not selected or any(not isinstance(item, str) for item in selected):
        raise AcceptanceRunError("FIXTURE_INVALID")
    refs: list[EvidenceRef] = []
    for evidence_id in selected:
        raw = evidence.get(evidence_id)
        if not isinstance(raw, dict):
            raise AcceptanceRunError("FIXTURE_INVALID")
        try:
            quote = str(raw["quote"])
            refs.append(
                EvidenceRef(
                    evidence_id=evidence_id,
                    workspace_id=_WORKSPACE_ID,
                    document_id=str(raw["document_id"]),
                    document_version="fixture-v1",
                    content_hash=sha256(quote.encode("utf-8")).hexdigest(),
                    locator=str(raw["locator"]),
                    quote=quote,
                    normalized_quote=quote,
                    evidence_hash=sha256((evidence_id + "|" + quote).encode("utf-8")).hexdigest(),
                    acl_scope=("acceptance",),
                    source_type=str(raw["source_type"]),
                    source_trust="reviewed" if evidence_id == "ev-primary" else "derived",
                    is_primary=evidence_id == "ev-primary",
                    created_at=_UTC,
                    expires_at=None,
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise AcceptanceRunError("FIXTURE_INVALID") from exc
    versions = VersionSet(
        schema_id="graphrag.fmea.v1",
        data_version="fixture-data-v1",
        graph_version="fixture-graph-v1",
        evidence_pack_version="1.0.0",
        profile_version=retrieval_mode,
        template_version="1.0.0",
        scoring_version="fuel-sod-rpn@1.0.0",
        prompt_version="offline-v1",
        model_version="deterministic-offline-model",
        input_snapshot_hash=sha256((retrieval_mode + "|fixture-v1").encode("utf-8")).hexdigest(),
    )
    return EvidencePack.build(
        pack_id=f"pack-fuel-combustion-{retrieval_mode}",
        workspace_id=_WORKSPACE_ID,
        acl_scope=("acceptance",),
        versions=versions,
        refs=tuple(refs),
        created_at=_UTC,
        expires_at=None,
    )


def _dimension(name: str, value: int | None, evidence_ids: tuple[str, ...], reason: str) -> ScoreDimension:
    return ScoreDimension(
        name=name,
        value=value,
        evidence_ids=evidence_ids,
        reason=reason,
        uncertainty=None if value is not None else "required score is unresolved",
    )


def _proposal(
    *,
    case: str,
    evidence_pack: EvidencePack,
    dimensions: tuple[ScoreDimension, ...],
    uncertainty: str | None = None,
) -> RiskProposal:
    return RiskProposal(
        proposal_id=f"proposal-{case}-1",
        workspace_id=_WORKSPACE_ID,
        row_id="row-fuel-filter-1",
        source_record_version=1,
        evidence_pack_id=evidence_pack.pack_id,
        dimensions=dimensions,
        domain_pack_id="fuel-combustion",
        domain_pack_version="1.0.0",
        rule_pack_id="fuel-sod-rpn",
        rule_pack_version="1.0.0",
        reason="Evidence-bound fuel pressure and combustion stability assessment.",
        created_at=_UTC,
        assistance_suggestion_id=f"suggestion-proposal-{case}-1",
        uncertainty=uncertainty,
    )


def _record(
    proposal: RiskProposal,
    *,
    status: RiskStatus,
    record_version: int,
    derived: object | None,
    confirmer_actor_id: str | None = None,
    invalidated_reason: str | None = None,
    assessment_id: str | None = None,
) -> RiskAssessmentRecord:
    return RiskAssessmentRecord(
        assessment_id=assessment_id or f"assessment-{proposal.proposal_id}",
        workspace_id=proposal.workspace_id,
        row_id=proposal.row_id,
        source_record_version=proposal.source_record_version,
        evidence_pack_id=proposal.evidence_pack_id,
        domain_pack_id=proposal.domain_pack_id,
        domain_pack_version=proposal.domain_pack_version,
        rule_pack_id=proposal.rule_pack_id,
        rule_pack_version=proposal.rule_pack_version,
        status=status,
        dimensions=proposal.dimensions,
        derived=derived,
        proposal_id=proposal.proposal_id,
        assistance_suggestion_id=proposal.assistance_suggestion_id,
        confirmer_actor_id=confirmer_actor_id,
        invalidated_reason=invalidated_reason,
        record_version=record_version,
        created_at=_UTC,
        updated_at=_UTC,
    )


def _build_artifacts(retrieval_mode: str) -> dict[str, dict[str, object]]:
    fixture = _load_fixture()
    evidence_pack = _evidence_pack(fixture, retrieval_mode)
    evidence_ids = tuple(ref.evidence_id for ref in evidence_pack.refs)
    primary_id = "ev-primary"
    supporting_id = next(item for item in evidence_ids if item != primary_id)
    rule_pack = load_scoring_rule_pack(_RULE_PATH.read_bytes())

    confirmed_dimensions = (
        _dimension("severity", 9, (primary_id, supporting_id), "Potential protection trip and severe consequence."),
        _dimension("occurrence", 3, (supporting_id,), "Restriction is occasional in the fixture history."),
        _dimension("detection", 4, (primary_id, supporting_id), "Trend monitoring requires engineering interpretation."),
    )
    confirmed_proposal = _proposal(case="confirmed", evidence_pack=evidence_pack, dimensions=confirmed_dimensions)
    derived = validate_risk_confirmation(
        confirmed_proposal,
        rule_pack=rule_pack,
        evidence_pack=evidence_pack,
    )
    confirmed_record = _record(
        confirmed_proposal,
        status=RiskStatus.CONFIRMED,
        record_version=2,
        derived=derived,
        confirmer_actor_id="reviewer-1",
    )

    unknown_dimensions = (
        _dimension("severity", 9, (primary_id,), "Potential severe consequence."),
        _dimension("occurrence", None, (), "No bounded occurrence evidence."),
        _dimension("detection", 4, (supporting_id,), "Monitoring evidence is available."),
    )
    unknown_proposal = _proposal(
        case="unknown",
        evidence_pack=evidence_pack,
        dimensions=unknown_dimensions,
        uncertainty="occurrence is unknown",
    )
    unknown_record = _record(unknown_proposal, status=RiskStatus.PROPOSED, record_version=1, derived=None)

    conflict_dimensions = (
        _dimension("severity", None, (primary_id, supporting_id), "Sources conflict on consequence severity."),
        _dimension("occurrence", 3, (supporting_id,), "Occurrence estimate remains usable."),
        _dimension("detection", 4, (primary_id,), "Detection basis remains usable."),
    )
    conflict_proposal = _proposal(
        case="conflict",
        evidence_pack=evidence_pack,
        dimensions=conflict_dimensions,
        uncertainty="severity evidence conflicts",
    )
    conflict_record = _record(conflict_proposal, status=RiskStatus.PROPOSED, record_version=1, derived=None)

    invalidated_record = _record(
        confirmed_proposal,
        status=RiskStatus.INVALIDATED,
        record_version=3,
        derived=None,
        invalidated_reason="stale dependencies: evidence pack version changed",
        assessment_id="assessment-invalidated-1",
    )

    suggestion = {
        "schema_version": SCHEMA_VERSION,
        "resource_type": "assistance_suggestion",
        "suggestion_id": "suggestion-analysis-scope-1",
        "kind": "analysis_scope_draft",
        "target_type": "fmea_analysis",
        "target_id": "analysis-fuel-combustion-1",
        "target_record_version": 1,
        "workspace_id": _WORKSPACE_ID,
        "actor": {"actor_id": "fmea-model-assistant", "actor_type": "model"},
        "applied": False,
        "evidence_pack_ids": [evidence_pack.pack_id],
        "scope": "Fuel filter inlet through burner-manifold combustion response.",
        "system_boundary": "Fuel train to combustion stability signals.",
        "domain_pack": {"id": "fuel-combustion", "version": "1.0.0"},
        "rule_pack": {"id": "fuel-sod-rpn", "version": "1.0.0"},
        "template": {"id": "fuel-combustion-fmea", "version": "1.0.0"},
        "created_at": _UTC,
    }
    proposal_payload = {
        "schema_version": SCHEMA_VERSION,
        "resource_type": "risk_proposal_matrix",
        "analysis_type": "system_fmea",
        "rule_applicable_analysis_types": list(rule_pack.applicable_analysis_types),
        "evidence_pack": {
            **_json_value(evidence_pack),
            "retrieval_mode": retrieval_mode,
        },
        "actor": {"actor_id": "fmea-model-assistant", "actor_type": "model"},
        "proposals": [
            {
                "case": "confirmed",
                **_json_value(confirmed_proposal),
                "derived": _json_value(derived),
                "conflict_ids": [],
            },
            {
                "case": "unknown",
                **_json_value(unknown_proposal),
                "derived": None,
                "conflict_ids": [],
            },
            {
                "case": "conflict",
                **_json_value(conflict_proposal),
                "derived": None,
                "conflict_ids": ["conflict-severity-1"],
            },
        ],
        "assessments": [
            _json_value(confirmed_record),
            _json_value(unknown_record),
            _json_value(conflict_record),
        ],
    }
    decision_id = "confirmation-" + _stable_uuid("confirmation|fuel-filter")
    confirmation = {
        "schema_version": SCHEMA_VERSION,
        "resource_type": "risk_confirmation",
        "decision_id": decision_id,
        "proposal_id": confirmed_proposal.proposal_id,
        "actor": {"actor_id": "reviewer-1", "actor_type": "human", "roles": ["risk_reviewer"]},
        "expected_assessment_version": 1,
        "assessment": _json_value(confirmed_record),
        "idempotency_key_hash": _hash_bytes(_stable_uuid("confirmation-key").encode("utf-8")),
        "replay": {"decision_id": decision_id, "replayed": True, "record_version": 2},
        "created_at": _UTC,
    }
    invalidation = {
        "schema_version": SCHEMA_VERSION,
        "resource_type": "risk_invalidation",
        "decision_id": "invalidation-" + _stable_uuid("invalidation|fuel-filter"),
        "actor": {"actor_id": "dependency-monitor", "actor_type": "system"},
        "previous_assessment": _json_value(confirmed_record),
        "assessment": _json_value(invalidated_record),
        "dependency_change": {
            "field": "evidence_pack_version",
            "before": "1.0.0",
            "after": "1.0.1",
        },
        "created_at": _UTC,
    }
    events = [
        {"event_type": "assistance.suggested", "actor_type": "model", "resource_id": suggestion["suggestion_id"]},
        {"event_type": "risk.proposed", "actor_type": "model", "resource_id": confirmed_proposal.proposal_id},
        {"event_type": "risk.confirmed", "actor_type": "human", "resource_id": decision_id},
        {"event_type": "risk.invalidated", "actor_type": "system", "resource_id": invalidation["decision_id"]},
    ]
    audit = {
        "schema_version": SCHEMA_VERSION,
        "resource_type": "risk_audit_summary",
        "events": [
            {**event, "sequence": index, "event_hash": _hash_bytes(_canonical_bytes(event))}
            for index, event in enumerate(events, start=1)
        ],
        "model_proposal_count": 1,
        "model_confirmation_count": 0,
        "human_confirmation_count": 1,
        "system_invalidation_count": 1,
    }
    return {
        "analysis-scope-suggestion.json": suggestion,
        "proposal.json": proposal_payload,
        "confirmation.json": confirmation,
        "invalidation.json": invalidation,
        "audit-summary.json": audit,
    }


def _safe_output_root(output_root: str | Path) -> Path:
    root = Path(output_root).expanduser().resolve()
    if root.exists() and (root.is_symlink() or not root.is_dir()):
        raise AcceptanceRunError("OUTPUT_ROOT_INVALID")
    root.mkdir(parents=True, exist_ok=True)
    return root


def run_acceptance(
    output_root: str | Path,
    *,
    retrieval_mode: str = "combined",
) -> AcceptanceRun:
    if retrieval_mode not in RETRIEVAL_MODES:
        raise AcceptanceRunError("RETRIEVAL_MODE_INVALID")
    root = _safe_output_root(output_root)
    final_directory = root / retrieval_mode
    if final_directory.exists():
        raise AcceptanceRunError("OUTPUT_EXISTS")
    temp_directory = Path(tempfile.mkdtemp(prefix=f".{retrieval_mode}-", dir=root))
    try:
        artifacts = _build_artifacts(retrieval_mode)
        backend_imports = _assert_backend_isolation()
        for filename, payload in artifacts.items():
            (temp_directory / filename).write_bytes(_canonical_bytes(payload))
        hashes = {
            filename: _hash_bytes((temp_directory / filename).read_bytes())
            for filename in ARTIFACT_NAMES[:-1]
        }
        proposal = artifacts["proposal.json"]
        evidence_pack = proposal["evidence_pack"]
        proposals = proposal["proposals"]
        summary = {
            "schema_version": SCHEMA_VERSION,
            "status": "passed",
            "cases": list(CASES),
            "retrieval_mode": retrieval_mode,
            "evidence_pack": {
                "pack_id": evidence_pack["pack_id"],
                "pack_hash": evidence_pack["pack_hash"],
                "retrieval_mode": retrieval_mode,
                "evidence_ids": [item["evidence_id"] for item in evidence_pack["refs"]],
            },
            "risk": {
                "confirmed_rpn": proposals[0]["derived"]["rpn"],
                "unknown_rpn": proposals[1]["derived"],
                "conflict_rpn": proposals[2]["derived"],
                "rule_applicable": True,
            },
            "model_confirmation_count": 0,
            "fmea_backend_import_count": len(backend_imports),
            "fmea_backend_imports": backend_imports,
            "artifact_hashes": hashes,
        }
        (temp_directory / "acceptance-summary.json").write_bytes(_canonical_bytes(summary))
        os.replace(temp_directory, final_directory)
    except Exception:
        shutil.rmtree(temp_directory, ignore_errors=True)
        raise
    artifact_bytes = tuple((final_directory / name).read_bytes() for name in ARTIFACT_NAMES)
    return AcceptanceRun(final_directory, summary, artifact_bytes)


def _default_output_root() -> Path:
    return ROOT / ".local" / "fmea-risk-acceptance"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--output-root", default=str(_default_output_root()))
    parser.add_argument("--retrieval-mode", choices=RETRIEVAL_MODES, default="combined")
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        result = run_acceptance(Path(args.output_root) / timestamp, retrieval_mode=args.retrieval_mode)
        payload = {"status": "passed", "output_directory": str(result.artifact_dir)}
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
    except Exception:
        sys.stdout.write(
            json.dumps(
                {"status": "failed", "error": {"code": "FMEA_RISK_ACCEPTANCE_FAILED"}},
                separators=(",", ":"),
            )
            + "\n"
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ARTIFACT_NAMES",
    "RETRIEVAL_MODES",
    "SCHEMA_VERSION",
    "AcceptanceRun",
    "AcceptanceRunError",
    "main",
    "run_acceptance",
]
