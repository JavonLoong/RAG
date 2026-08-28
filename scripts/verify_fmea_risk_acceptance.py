"""Independent fail-closed verifier for FMEA risk acceptance artifacts."""

from __future__ import annotations

import argparse
import json
import re
import sys
from hashlib import sha256
from pathlib import Path
from typing import NoReturn, cast

SCHEMA_VERSION = "graphrag.fmea.risk.acceptance.v1"
RETRIEVAL_MODES = {
    "rag_only",
    "graphrag_local",
    "graphrag_global",
    "graphrag_only",
    "combined",
    "auto",
    "custom",
}
ARTIFACT_NAMES = {
    "analysis-scope-suggestion.json",
    "proposal.json",
    "confirmation.json",
    "invalidation.json",
    "audit-summary.json",
    "acceptance-summary.json",
}
CASES = ["analysis_scope", "confirmed", "unknown", "conflict", "invalidated"]

_MAX_ARTIFACT_BYTES = 2 * 1024 * 1024
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_PRIVATE_MARKERS = tuple(
    marker.encode("utf-8")
    for marker in (
        "Authorization",
        "Bearer ",
        "DEEPSEEK_API_KEY",
        "sk-",
        "C:\\private",
        "REQUEST_PRIVATE_MARKER",
        "EVIDENCE_PRIVATE_MARKER",
    )
)


class AcceptanceVerificationError(ValueError):
    """Stable verifier failure that never contains artifact or path content."""

    def __init__(self, code: str) -> None:
        super().__init__("FMEA risk acceptance verification failed.")
        self.code = code


def _fail(code: str) -> NoReturn:
    raise AcceptanceVerificationError(code)


def _canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _hash_bytes(value: bytes) -> str:
    return "sha256:" + sha256(value).hexdigest()


def _strict_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            _fail("JSON_DUPLICATE_KEY")
        value[key] = item
    return value


def _reject_constant(value: str) -> NoReturn:
    del value
    _fail("JSON_INVALID")


def _load(path: Path) -> tuple[dict[str, object], bytes]:
    try:
        raw = path.read_bytes()
    except OSError:
        _fail("ARTIFACT_SET_INVALID")
    if len(raw) > _MAX_ARTIFACT_BYTES:
        _fail("ARTIFACT_TOO_LARGE")
    if any(marker in raw for marker in _PRIVATE_MARKERS):
        _fail("OUTPUT_PRIVATE_MARKER")
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_strict_pairs,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, TypeError, ValueError, json.JSONDecodeError):
        _fail("JSON_INVALID")
    if not isinstance(value, dict):
        _fail("JSON_SHAPE_INVALID")
    if _canonical_bytes(value) != raw:
        _fail("JSON_NOT_CANONICAL")
    return value, raw


def _mapping(value: object, code: str) -> dict[str, object]:
    if not isinstance(value, dict):
        _fail(code)
    return cast(dict[str, object], value)


def _list(value: object, code: str) -> list[object]:
    if not isinstance(value, list):
        _fail(code)
    return cast(list[object], value)


def _schema(value: dict[str, object]) -> None:
    if value.get("schema_version") != SCHEMA_VERSION:
        _fail("SCHEMA_VERSION_INVALID")


def _verify_evidence_pack(pack: dict[str, object], retrieval_mode: str) -> None:
    if pack.get("retrieval_mode") != retrieval_mode or retrieval_mode not in RETRIEVAL_MODES:
        _fail("RETRIEVAL_MODE_INVALID")
    refs = _list(pack.get("refs"), "EVIDENCE_PACK_INVALID")
    if len(refs) < 2:
        _fail("EVIDENCE_PACK_INVALID")
    evidence_payload: list[dict[str, object]] = []
    evidence_ids: set[str] = set()
    for item in refs:
        ref = _mapping(item, "EVIDENCE_PACK_INVALID")
        evidence_id = ref.get("evidence_id")
        quote = ref.get("quote")
        if not isinstance(evidence_id, str) or not isinstance(quote, str) or evidence_id in evidence_ids:
            _fail("EVIDENCE_PACK_INVALID")
        evidence_ids.add(evidence_id)
        if ref.get("normalized_quote") != quote:
            _fail("EVIDENCE_BINDING_INVALID")
        if ref.get("content_hash") != sha256(quote.encode("utf-8")).hexdigest():
            _fail("EVIDENCE_BINDING_INVALID")
        if ref.get("evidence_hash") != sha256((evidence_id + "|" + quote).encode("utf-8")).hexdigest():
            _fail("EVIDENCE_BINDING_INVALID")
        evidence_payload.append(
            {
                "evidence_id": evidence_id,
                "evidence_hash": ref.get("evidence_hash"),
                "locator": ref.get("locator"),
            }
        )
    expected_pack_hash = sha256(
        json.dumps(
            sorted(evidence_payload, key=lambda item: cast(str, item["evidence_id"])),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    if pack.get("pack_hash") != expected_pack_hash:
        _fail("EVIDENCE_PACK_HASH_INVALID")


def _dimension_map(proposal: dict[str, object]) -> dict[str, dict[str, object]]:
    dimensions = _list(proposal.get("dimensions"), "RISK_PROPOSAL_INVALID")
    result: dict[str, dict[str, object]] = {}
    for item in dimensions:
        dimension = _mapping(item, "RISK_PROPOSAL_INVALID")
        name = dimension.get("name")
        if not isinstance(name, str) or name in result:
            _fail("RISK_PROPOSAL_INVALID")
        result[name] = dimension
    if set(result) != {"severity", "occurrence", "detection"}:
        _fail("RISK_PROPOSAL_INVALID")
    return result


def _proposal_cases(payload: dict[str, object], summary: dict[str, object]) -> dict[str, dict[str, object]]:
    proposals = _list(payload.get("proposals"), "RISK_PROPOSAL_INVALID")
    if len(proposals) != 3:
        _fail("RISK_PROPOSAL_INVALID")
    by_case: dict[str, dict[str, object]] = {}
    for item in proposals:
        proposal = _mapping(item, "RISK_PROPOSAL_INVALID")
        case = proposal.get("case")
        if not isinstance(case, str) or case in by_case:
            _fail("RISK_PROPOSAL_INVALID")
        by_case[case] = proposal
        if proposal.get("evidence_pack_id") != _mapping(summary["evidence_pack"], "SUMMARY_INVALID").get("pack_id"):
            _fail("EVIDENCE_BINDING_INVALID")
        if proposal.get("rule_pack_id") != "fuel-sod-rpn" or proposal.get("rule_pack_version") != "1.0.0":
            _fail("RULE_BINDING_INVALID")
    if set(by_case) != {"confirmed", "unknown", "conflict"}:
        _fail("RISK_PROPOSAL_INVALID")
    return by_case


def _verify_confirmed_proposal(confirmed: dict[str, object]) -> None:
    confirmed_dimensions = _dimension_map(confirmed)
    values = [confirmed_dimensions[name].get("value") for name in ("severity", "occurrence", "detection")]
    if values != [9, 3, 4]:
        _fail("RISK_SCORE_INVALID")
    derived = _mapping(confirmed.get("derived"), "RISK_SCORE_INVALID")
    if derived.get("rpn") != 108 or derived.get("decision_priority") != "critical":
        _fail("RISK_SCORE_INVALID")


def _verify_unresolved_proposals(
    unknown: dict[str, object],
    conflict: dict[str, object],
) -> None:
    if _dimension_map(unknown)["occurrence"].get("value") is not None or unknown.get("derived") is not None:
        _fail("UNKNOWN_POLICY_INVALID")

    if _dimension_map(conflict)["severity"].get("value") is not None or conflict.get("derived") is not None:
        _fail("CONFLICT_POLICY_INVALID")
    conflict_ids = _list(conflict.get("conflict_ids"), "CONFLICT_POLICY_INVALID")
    if conflict_ids != ["conflict-severity-1"]:
        _fail("CONFLICT_POLICY_INVALID")


def _verify_proposals(payload: dict[str, object], summary: dict[str, object]) -> None:
    analysis_type = payload.get("analysis_type")
    applicable_types = _list(payload.get("rule_applicable_analysis_types"), "RULE_APPLICABILITY_INVALID")
    if analysis_type != "system_fmea" or analysis_type not in applicable_types:
        _fail("RULE_APPLICABILITY_INVALID")
    by_case = _proposal_cases(payload, summary)
    _verify_confirmed_proposal(by_case["confirmed"])
    _verify_unresolved_proposals(by_case["unknown"], by_case["conflict"])


def _verify_assistance(
    suggestion: dict[str, object],
    proposal: dict[str, object],
    pack: dict[str, object],
) -> None:
    suggestion_actor = _mapping(suggestion.get("actor"), "ASSISTANCE_BINDING_INVALID")
    if (
        suggestion.get("applied") is not False
        or suggestion.get("target_record_version") != 1
        or suggestion_actor.get("actor_type") != "model"
        or suggestion.get("evidence_pack_ids") != [pack.get("pack_id")]
    ):
        _fail("ASSISTANCE_BINDING_INVALID")
    proposal_actor = _mapping(proposal.get("actor"), "RISK_PROPOSAL_INVALID")
    if proposal_actor.get("actor_type") != "model":
        _fail("RISK_PROPOSAL_INVALID")


def _verify_confirmation(confirmation: dict[str, object]) -> dict[str, object]:
    actor = _mapping(confirmation.get("actor"), "CONFIRMATION_INVALID")
    assessment = _mapping(confirmation.get("assessment"), "CONFIRMATION_INVALID")
    replay = _mapping(confirmation.get("replay"), "CONFIRMATION_INVALID")
    if (
        actor.get("actor_type") != "human"
        or assessment.get("status") != "confirmed"
        or assessment.get("record_version") != 2
        or confirmation.get("expected_assessment_version") != 1
        or replay.get("decision_id") != confirmation.get("decision_id")
        or replay.get("replayed") is not True
    ):
        _fail("CONFIRMATION_INVALID")
    return assessment


def _verify_invalidation(invalidation: dict[str, object], confirmed: dict[str, object]) -> None:
    actor = _mapping(invalidation.get("actor"), "INVALIDATION_INVALID")
    previous = _mapping(invalidation.get("previous_assessment"), "INVALIDATION_INVALID")
    invalidated = _mapping(invalidation.get("assessment"), "INVALIDATION_INVALID")
    if (
        actor.get("actor_type") != "system"
        or previous.get("assessment_id") != confirmed.get("assessment_id")
        or previous.get("status") != "confirmed"
        or invalidated.get("status") != "invalidated"
        or invalidated.get("record_version") != 3
        or invalidated.get("derived") is not None
        or invalidated.get("confirmer_actor_id") is not None
    ):
        _fail("INVALIDATION_INVALID")


def _verify_audit(audit: dict[str, object], summary: dict[str, object]) -> None:
    events = _list(audit.get("events"), "AUDIT_INVALID")
    actor_types = [_mapping(event, "AUDIT_INVALID").get("actor_type") for event in events]
    if actor_types != ["model", "model", "human", "system"]:
        _fail("AUDIT_INVALID")
    if audit.get("model_confirmation_count") != 0 or summary.get("model_confirmation_count") != 0:
        _fail("MODEL_AUTHORITY_INVALID")
    for event in events:
        item = _mapping(event, "AUDIT_INVALID")
        body = {key: value for key, value in item.items() if key not in {"sequence", "event_hash"}}
        if item.get("event_hash") != _hash_bytes(_canonical_bytes(body)):
            _fail("AUDIT_HASH_INVALID")


def _verify_summary(summary: dict[str, object]) -> None:
    risk = _mapping(summary.get("risk"), "SUMMARY_INVALID")
    if risk != {
        "confirmed_rpn": 108,
        "unknown_rpn": None,
        "conflict_rpn": None,
        "rule_applicable": True,
    }:
        _fail("SUMMARY_INVALID")
    if summary.get("fmea_backend_import_count") != 0 or summary.get("fmea_backend_imports") != []:
        _fail("BACKEND_ISOLATION_INVALID")


def _verify_cross_resource_bindings(artifacts: dict[str, dict[str, object]]) -> None:
    summary = artifacts["acceptance-summary.json"]
    suggestion = artifacts["analysis-scope-suggestion.json"]
    proposal = artifacts["proposal.json"]
    confirmation = artifacts["confirmation.json"]
    invalidation = artifacts["invalidation.json"]
    audit = artifacts["audit-summary.json"]

    if summary.get("cases") != CASES or len(set(cast(list[str], summary.get("cases")))) != len(CASES):
        _fail("CASE_MATRIX_INVALID")
    retrieval_mode = summary.get("retrieval_mode")
    if not isinstance(retrieval_mode, str):
        _fail("RETRIEVAL_MODE_INVALID")
    pack = _mapping(proposal.get("evidence_pack"), "EVIDENCE_PACK_INVALID")
    _verify_evidence_pack(pack, retrieval_mode)
    summary_pack = _mapping(summary.get("evidence_pack"), "SUMMARY_INVALID")
    if (
        summary_pack.get("pack_id") != pack.get("pack_id")
        or summary_pack.get("pack_hash") != pack.get("pack_hash")
        or summary_pack.get("retrieval_mode") != retrieval_mode
    ):
        _fail("EVIDENCE_BINDING_INVALID")

    _verify_assistance(suggestion, proposal, pack)
    _verify_proposals(proposal, summary)
    confirmed = _verify_confirmation(confirmation)
    _verify_invalidation(invalidation, confirmed)
    _verify_audit(audit, summary)
    _verify_summary(summary)


def verify_acceptance_directory(directory: str | Path) -> dict[str, object]:
    root = Path(directory).expanduser().resolve()
    if not root.is_dir() or root.is_symlink():
        _fail("ARTIFACT_SET_INVALID")
    try:
        names = {path.name for path in root.iterdir() if path.is_file()}
        non_files = [path for path in root.iterdir() if not path.is_file()]
    except OSError:
        _fail("ARTIFACT_SET_INVALID")
    if names != ARTIFACT_NAMES or non_files:
        _fail("ARTIFACT_SET_INVALID")
    loaded = {name: _load(root / name) for name in ARTIFACT_NAMES}
    artifacts = {name: value for name, (value, _) in loaded.items()}
    for value in artifacts.values():
        _schema(value)
    summary = artifacts["acceptance-summary.json"]
    if summary.get("status") != "passed":
        _fail("SUMMARY_INVALID")
    hashes = _mapping(summary.get("artifact_hashes"), "SUMMARY_INVALID")
    expected_hash_names = ARTIFACT_NAMES - {"acceptance-summary.json"}
    if set(hashes) != expected_hash_names:
        _fail("SUMMARY_INVALID")
    for name in expected_hash_names:
        if hashes.get(name) != _hash_bytes(loaded[name][1]) or _SHA256.fullmatch(cast(str, hashes.get(name))) is None:
            _fail("ARTIFACT_HASH_MISMATCH")
    _verify_cross_resource_bindings(artifacts)
    return summary


def _default_root() -> Path:
    return Path(__file__).resolve().parents[1] / ".local" / "fmea-risk-acceptance"


def _latest_directory(root: Path) -> Path:
    try:
        candidates = [path.parent for path in root.rglob("acceptance-summary.json") if path.is_file()]
    except OSError:
        _fail("ARTIFACT_SET_INVALID")
    if not candidates:
        _fail("ARTIFACT_SET_INVALID")
    return max(candidates, key=lambda path: str(path))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--artifact-dir")
    target.add_argument("--latest", action="store_true")
    parser.add_argument("--output-root", default=str(_default_root()))
    return parser


def _fmea_module_count() -> int:
    prefixes = ("core_domain.fmea", "fmea_application", "fmea_infrastructure", "chroma_rag_poc")
    return sum(name.startswith(prefixes) for name in sys.modules)


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        directory = _latest_directory(Path(args.output_root)) if args.latest else Path(args.artifact_dir)
        summary = verify_acceptance_directory(directory)
        payload = {
            "fmea_module_import_count": _fmea_module_count(),
            "schema_version": summary["schema_version"],
            "status": "passed",
        }
        if payload["fmea_module_import_count"] != 0:
            _fail("VERIFIER_NOT_INDEPENDENT")
        sys.stdout.write(json.dumps(payload, separators=(",", ":")) + "\n")
    except Exception as exc:
        code = exc.code if isinstance(exc, AcceptanceVerificationError) else "FMEA_RISK_VERIFICATION_FAILED"
        sys.stdout.write(json.dumps({"status": "failed", "error": {"code": code}}, separators=(",", ":")) + "\n")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["SCHEMA_VERSION", "AcceptanceVerificationError", "main", "verify_acceptance_directory"]
