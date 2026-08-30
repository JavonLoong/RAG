"""Deterministic assembly and readiness evaluation for FMEA revisions.

Task 2 deliberately stops at immutable application contracts.  Loading from a
repository, mutating governance state, and publication/export orchestration
belong to later tasks.  The assembler therefore accepts a server-owned input
bundle and turns it into the already-established :class:`FmeaRevision`
contract; it does not accept client-selected resource identities.
"""

# The repository's application modules use ValueError/TypeError as their
# contract boundary; keep ruff's exception-message rule aligned with them.
# ruff: noqa: TRY003

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, fields
from datetime import datetime, timezone
from enum import Enum
from types import MappingProxyType
from typing import Any, Final, Literal
from uuid import uuid4

from core_domain.fmea.domain_pack import DomainPackManifest
from core_domain.fmea.entities import FmeaAnalysis, FmeaRow
from core_domain.fmea.governance import (
    FmeaRevision,
    ReadinessIssue,
    RetrievalProvenanceSnapshot,
    canonical_hash,
    canonical_json_value,
)
from core_domain.fmea.propagation import PropagationGraphRevision
from core_domain.fmea.scoring import RiskAssessmentRecord
from core_domain.fmea.states import PropagationStatus, ReviewStatus, RiskStatus
from core_domain.fmea.value_objects import EvidencePack, validate_evidence_lineage
from fmea_application.governance_contracts import RevisionAssemblyRequest

Identity = tuple[str, str, str]
RecordVersion = tuple[str, int, str]
Clock = Callable[[], str]
IdFactory = Callable[[], str]

_HASH_LENGTH: Final = 64
_ACTIVE_RUN_BLOCKER: Final = "ACTIVE_MUTATION_RUN"
_SEVERITY_ORDER: Final = {"info": 0, "warning": 1, "blocking": 2, "critical": 3}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _stable_id() -> str:
    return f"revision-{uuid4().hex}"


def _text(value: object, label: str) -> str:
    if isinstance(value, Enum):
        value = value.value
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must not be empty")
    return value.strip()


def _positive(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{label} must be positive")
    return value


def _sequence(value: object, label: str) -> tuple[Any, ...]:
    if isinstance(value, str | bytes) or value is None:
        raise TypeError(f"{label} must be a sequence")
    try:
        return tuple(value)  # type: ignore[arg-type]
    except TypeError as exc:
        raise TypeError(f"{label} must be a sequence") from exc


def _sorted_texts(value: object, label: str) -> tuple[str, ...]:
    result = tuple(sorted({_text(item, label) for item in _sequence(value, label)}))
    return result


def _hash_for(value: object) -> str:
    if isinstance(value, str) and len(value.removeprefix("sha256:")) == _HASH_LENGTH:
        candidate = value.removeprefix("sha256:")
        if all(char in "0123456789abcdef" for char in candidate):
            return value
    return canonical_hash(value)


def _record_hash(value: object) -> str:
    for name in ("content_hash", "record_hash", "row_hash", "assessment_hash", "graph_hash"):
        candidate = getattr(value, name, None)
        if isinstance(candidate, str) and len(candidate.removeprefix("sha256:")) == _HASH_LENGTH:
            normalized = candidate.removeprefix("sha256:")
            if all(char in "0123456789abcdef" for char in normalized):
                return candidate
    return canonical_hash(value)


def _identity(value: object, label: str) -> Identity:
    if not isinstance(value, tuple | list) or len(value) != 3:
        raise ValueError(f"{label} must be an id/version/hash triple")
    identifier, version, content_hash = (_text(item, label) for item in value)
    normalized_hash = content_hash.removeprefix("sha256:")
    if len(normalized_hash) != _HASH_LENGTH or any(char not in "0123456789abcdef" for char in normalized_hash):
        raise ValueError(f"{label} hash must be lowercase SHA-256")
    return identifier, version, content_hash


def _identity_list(value: object, label: str) -> tuple[Identity, ...]:
    result = tuple(sorted({_identity(item, label) for item in _sequence(value, label)}))
    return result


def _issue(
    code: str,
    *,
    severity: Literal["info", "warning", "blocking", "critical"] = "blocking",
    source_type: str = "governance",
    source_id: str = "governance",
    evidence_ids: Iterable[str] = (),
    acknowledgement_decision_id: str | None = None,
) -> ReadinessIssue:
    return ReadinessIssue(
        code=code,
        severity=severity,
        source_type=source_type,
        source_id=source_id,
        evidence_ids=tuple(sorted({_text(item, "evidence_id") for item in evidence_ids})),
        acknowledgement_decision_id=acknowledgement_decision_id,
    )


@dataclass(frozen=True, slots=True)
class GovernanceInputs:
    """Server-owned, already accepted/confirmed state for one analysis."""

    workspace_id: str
    analysis_id: str
    rows: tuple[FmeaRow, ...] = ()
    risk_records: tuple[RiskAssessmentRecord, ...] = ()
    propagation_graph_revision: PropagationGraphRevision | None = None
    evidence_packs: tuple[EvidencePack, ...] = ()
    domain_pack: DomainPackManifest | Mapping[str, object] | None = None
    version_identities: tuple[Identity, ...] = ()
    analysis: FmeaAnalysis | None = None
    analysis_record_version: int = 1
    analysis_hash: str | None = None
    domain_pack_identity: Identity | None = None
    template_identities: tuple[Identity, ...] = ()
    scoring_rule_identities: tuple[Identity, ...] = ()
    propagation_rule_identity: Identity | None = None
    requested_profile: str = "combined"
    resolved_profile: str = "combined"
    evidence_types: tuple[str, ...] = ()
    source_counts: tuple[tuple[str, int], ...] = ()
    retrieval_warnings: tuple[str, ...] = ()
    unresolved_items: tuple[ReadinessIssue, ...] = ()
    human_decision_ids: tuple[str, ...] = ()
    acknowledgement_decision_ids: tuple[str, ...] = ()
    active_run_ids: tuple[str, ...] = ()
    created_at: str | None = None
    parent_revision: FmeaRevision | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "workspace_id", _text(self.workspace_id, "workspace_id"))
        object.__setattr__(self, "analysis_id", _text(self.analysis_id, "analysis_id"))
        object.__setattr__(self, "rows", tuple(self.rows))
        object.__setattr__(self, "risk_records", tuple(self.risk_records))
        object.__setattr__(self, "evidence_packs", tuple(self.evidence_packs))
        if isinstance(self.domain_pack, Mapping):
            object.__setattr__(self, "domain_pack", MappingProxyType(dict(self.domain_pack)))
        object.__setattr__(self, "version_identities", _identity_list(self.version_identities, "version_identities"))
        object.__setattr__(self, "analysis_record_version", _positive(self.analysis_record_version, "analysis_record_version"))
        if self.analysis_hash is not None:
            object.__setattr__(self, "analysis_hash", _hash_for(self.analysis_hash))
        object.__setattr__(self, "domain_pack_identity", None if self.domain_pack_identity is None else _identity(self.domain_pack_identity, "domain_pack_identity"))
        object.__setattr__(self, "template_identities", _identity_list(self.template_identities, "template_identities"))
        object.__setattr__(self, "scoring_rule_identities", _identity_list(self.scoring_rule_identities, "scoring_rule_identities"))
        object.__setattr__(self, "propagation_rule_identity", None if self.propagation_rule_identity is None else _identity(self.propagation_rule_identity, "propagation_rule_identity"))
        object.__setattr__(self, "requested_profile", _text(self.requested_profile, "requested_profile"))
        object.__setattr__(self, "resolved_profile", _text(self.resolved_profile, "resolved_profile"))
        object.__setattr__(self, "evidence_types", _sorted_texts(self.evidence_types, "evidence_types"))
        counts: list[tuple[str, int]] = []
        for source_type, count in _sequence(self.source_counts, "source_counts"):
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                raise ValueError("source_counts values must be non-negative integers")
            counts.append((_text(source_type, "source_type"), count))
        if len({source_type for source_type, _ in counts}) != len(counts):
            raise ValueError("source_counts must not contain duplicate source types")
        object.__setattr__(self, "source_counts", tuple(sorted(set(counts))))
        object.__setattr__(self, "retrieval_warnings", _sorted_texts(self.retrieval_warnings, "retrieval_warnings"))
        object.__setattr__(self, "unresolved_items", _issue_tuple(self.unresolved_items))
        object.__setattr__(self, "human_decision_ids", _sorted_texts(self.human_decision_ids, "human_decision_id"))
        object.__setattr__(self, "acknowledgement_decision_ids", _sorted_texts(self.acknowledgement_decision_ids, "acknowledgement_decision_id"))
        object.__setattr__(self, "active_run_ids", _sorted_texts(self.active_run_ids, "active_run_id"))


def _issue_tuple(value: object) -> tuple[ReadinessIssue, ...]:
    items = tuple(_sequence(value, "unresolved_items"))
    if any(not isinstance(item, ReadinessIssue) for item in items):
        raise TypeError("unresolved_items must contain ReadinessIssue objects")
    unique = {(item.code, item.source_type, item.source_id): item for item in items}
    if len(unique) != len(items):
        raise ValueError("unresolved_items must not contain duplicate identities")
    return tuple(sorted(unique.values(), key=lambda item: (item.code, item.source_type, item.source_id)))


def _input_field_names() -> frozenset[str]:
    return frozenset(field.name for field in fields(GovernanceInputs))


def coerce_governance_inputs(value: GovernanceInputs | Mapping[str, object]) -> GovernanceInputs:
    """Convert a source-port mapping without allowing client resource overrides."""

    if isinstance(value, GovernanceInputs):
        return value
    if not isinstance(value, Mapping):
        raise TypeError("governance source must return GovernanceInputs or a mapping")
    unknown = set(value).difference(_input_field_names())
    if unknown:
        names = ", ".join(sorted(str(item) for item in unknown))
        raise TypeError(f"GovernanceInputs contains unsupported fields: {names}")
    return GovernanceInputs(**dict(value))


def _domain_identity(inputs: GovernanceInputs, issues: list[ReadinessIssue]) -> Identity:
    if inputs.domain_pack_identity is not None:
        return inputs.domain_pack_identity
    pack = inputs.domain_pack
    if isinstance(pack, DomainPackManifest):
        return pack.pack_id, pack.version, pack.content_hash
    if isinstance(pack, Mapping) and {"pack_id", "version", "content_hash"}.issubset(pack):
        return _identity((pack["pack_id"], pack["version"], pack["content_hash"]), "domain_pack_identity")
    issues.append(_issue("DOMAIN_PACK_IDENTITY_UNRESOLVED", source_type="domain_pack"))
    return "domain-pack-unresolved", "unresolved", "0" * _HASH_LENGTH


def _derived_identity_hash(*, kind: str, identifier: str, version: str, domain_pack: Identity) -> str:
    return canonical_hash({"kind": kind, "identifier": identifier, "version": version, "domain_pack": domain_pack})


def _version_identities(inputs: GovernanceInputs, domain_identity: Identity, issues: list[ReadinessIssue]) -> tuple[tuple[Identity, ...], tuple[Identity, ...], Identity | None]:  # noqa: C901
    templates = inputs.template_identities
    scoring = inputs.scoring_rule_identities
    propagation = inputs.propagation_rule_identity
    unclassified = list(inputs.version_identities)
    if not templates:
        templates = tuple(item for item in unclassified if "template" in item[0].casefold())
    if not scoring:
        scoring = tuple(item for item in unclassified if any(token in item[0].casefold() for token in ("scoring", "score")))
    if propagation is None:
        propagation_items = tuple(item for item in unclassified if "propagation" in item[0].casefold())
        propagation = propagation_items[0] if propagation_items else None
    classified = set(templates) | set(scoring) | ({propagation} if propagation else set())
    remaining = [item for item in unclassified if item not in classified]
    if not templates and remaining:
        templates = (remaining.pop(0),)
    if not scoring and remaining:
        scoring = (remaining.pop(0),)
    domain_pack = inputs.domain_pack
    if isinstance(domain_pack, DomainPackManifest):
        if not templates:
            if domain_pack.template_identities:
                issues.append(_issue("TEMPLATE_IDENTITY_HASH_UNRESOLVED", source_type="template"))
            templates = tuple(
                (identifier, version, _derived_identity_hash(kind="template", identifier=identifier, version=version, domain_pack=domain_identity))
                for identifier, version in domain_pack.template_identities
            )
        if not scoring:
            if domain_pack.scoring_rule_identities:
                issues.append(_issue("SCORING_RULE_IDENTITY_HASH_UNRESOLVED", source_type="scoring_rule"))
            scoring = tuple(
                (identifier, version, _derived_identity_hash(kind="scoring", identifier=identifier, version=version, domain_pack=domain_identity))
                for identifier, version in domain_pack.scoring_rule_identities
            )
        if propagation is None and domain_pack.propagation_rule_identities:
            identifier, version = domain_pack.propagation_rule_identities[0]
            issues.append(_issue("PROPAGATION_RULE_IDENTITY_HASH_UNRESOLVED", source_type="propagation_rule"))
            propagation = (identifier, version, _derived_identity_hash(kind="propagation", identifier=identifier, version=version, domain_pack=domain_identity))
    if not templates:
        issues.append(_issue("TEMPLATE_IDENTITY_UNRESOLVED", source_type="template"))
    if not scoring:
        issues.append(_issue("SCORING_RULE_IDENTITY_UNRESOLVED", source_type="scoring_rule"))
    if propagation is None:
        issues.append(_issue("PROPAGATION_RULE_IDENTITY_UNRESOLVED", source_type="propagation_rule"))
    return tuple(sorted(templates)), tuple(sorted(scoring)), propagation


def _analysis_identity(inputs: GovernanceInputs) -> tuple[int, str]:
    version = inputs.analysis.record_version if inputs.analysis is not None else inputs.analysis_record_version
    if inputs.analysis is not None and inputs.analysis_hash is None:
        return version, canonical_hash(inputs.analysis)
    if inputs.analysis_hash is not None:
        return version, inputs.analysis_hash
    return version, canonical_hash({"analysis_id": inputs.analysis_id, "record_version": version})


def _row_evidence_ids(row: FmeaRow) -> tuple[str, ...]:
    return tuple(sorted({evidence_id for _, evidence_ids in row.field_evidence for evidence_id in evidence_ids}))


class RevisionAssembler:
    """Assemble one immutable, canonical FMEA revision from server-owned state."""

    def __init__(self, clock: Clock = _utc_now, id_factory: IdFactory | None = None) -> None:
        self._clock = clock
        self._id_factory = id_factory or _stable_id

    def assemble(
        self,
        request: RevisionAssemblyRequest,
        inputs: GovernanceInputs | Mapping[str, object],
    ) -> FmeaRevision:
        if not isinstance(request, RevisionAssemblyRequest):
            raise TypeError("request must be a RevisionAssemblyRequest")
        source = coerce_governance_inputs(inputs)
        if source.analysis_id != request.analysis_id:
            raise ValueError("request analysis_id does not match governance inputs")
        analysis_version, analysis_hash = _analysis_identity(source)
        if analysis_version != request.expected_analysis_version:
            raise ValueError("expected analysis version does not match governance inputs")
        issues: list[ReadinessIssue] = list(source.unresolved_items)
        self._validate_source_scope(source)
        domain_identity = _domain_identity(source, issues)
        templates, scoring, propagation_rule = _version_identities(source, domain_identity, issues)
        packs = self._validate_evidence(source, issues)
        rows = self._assemble_rows(source.rows, packs, issues)
        risks = self._assemble_risks(source.risk_records, source, packs, issues)
        graph_id, graph_hash = self._assemble_graph(source, analysis_version, packs, issues)
        if source.active_run_ids:
            for run_id in source.active_run_ids:
                issues.append(_issue(_ACTIVE_RUN_BLOCKER, source_type="run", source_id=run_id))
        known_acknowledgements = set(source.human_decision_ids) | set(source.acknowledgement_decision_ids)
        for item in tuple(issues):
            if known_acknowledgements and item.acknowledgement_decision_id is not None and item.acknowledgement_decision_id not in known_acknowledgements:
                issues.append(
                    _issue(
                        "ACKNOWLEDGEMENT_REFERENCE_UNRESOLVED",
                        source_type="acknowledgement",
                        source_id=item.acknowledgement_decision_id,
                    )
                )
        parent_id, parent_hash = self._parent_identity(request, source)
        provenance = RetrievalProvenanceSnapshot(
            requested_profile=source.requested_profile,
            resolved_profile=source.resolved_profile,
            evidence_types=source.evidence_types,
            source_counts=source.source_counts,
            warnings=source.retrieval_warnings,
        )
        revision_id = self._revision_id(
            request=request,
            workspace_id=source.workspace_id,
            analysis_id=source.analysis_id,
            analysis_version=analysis_version,
            analysis_hash=analysis_hash,
            parent_id=parent_id,
            parent_hash=parent_hash,
            row_versions=rows,
            risk_versions=risks,
            graph_id=graph_id,
            graph_hash=graph_hash,
            pack_hashes=tuple((pack.pack_id, pack.pack_hash) for pack in packs),
            provenance=provenance,
            domain_identity=domain_identity,
            templates=templates,
            scoring=scoring,
            propagation_rule=propagation_rule,
            issues=issues,
        )
        body = {
            "revision_id": revision_id,
            "workspace_id": source.workspace_id,
            "analysis_id": source.analysis_id,
            "analysis_record_version": analysis_version,
            "analysis_hash": analysis_hash,
            "parent_revision_id": parent_id,
            "parent_revision_hash": parent_hash,
            "row_versions": rows,
            "risk_versions": risks,
            "propagation_graph_revision_id": graph_id,
            "propagation_graph_hash": graph_hash,
            "evidence_pack_hashes": tuple((pack.pack_id, pack.pack_hash) for pack in packs),
            "retrieval_provenance": provenance,
            "domain_pack_identity": domain_identity,
            "template_identities": templates,
            "scoring_rule_identities": scoring,
            "propagation_rule_identity": propagation_rule,
            "unresolved_items": _issue_tuple(issues),
        }
        revision_hash = canonical_hash(canonical_json_value(body), max_array_items=10_000)
        return FmeaRevision(
            **body,
            revision_hash=revision_hash,
            created_at=source.created_at or self._clock(),
        )

    @staticmethod
    def _validate_source_scope(source: GovernanceInputs) -> None:  # noqa: C901
        for row in source.rows:
            if not isinstance(row, FmeaRow):
                raise TypeError("governance rows must contain FmeaRow objects")
            if row.analysis_id != source.analysis_id:
                raise ValueError("row analysis_id does not match governance analysis")
        for risk in source.risk_records:
            if not isinstance(risk, RiskAssessmentRecord):
                raise TypeError("risk_records must contain RiskAssessmentRecord objects")
            if risk.workspace_id != source.workspace_id:
                raise ValueError("risk workspace_id does not match governance workspace")
        graph = source.propagation_graph_revision
        if graph is not None and (graph.workspace_id != source.workspace_id or graph.analysis_id != source.analysis_id):
            raise ValueError("propagation graph workspace/analysis does not match governance scope")
        for pack in source.evidence_packs:
            if not isinstance(pack, EvidencePack):
                raise TypeError("evidence_packs must contain EvidencePack objects")
            if pack.workspace_id != source.workspace_id:
                raise ValueError("evidence pack workspace_id does not match governance workspace")

    @staticmethod
    def _validate_evidence(source: GovernanceInputs, issues: list[ReadinessIssue]) -> tuple[EvidencePack, ...]:
        packs = tuple(sorted(source.evidence_packs, key=lambda pack: pack.pack_id))
        by_id = {pack.pack_id: pack for pack in packs}
        if len(by_id) != len(packs):
            raise ValueError("evidence pack IDs must be unique")
        for pack in packs:
            try:
                validate_evidence_lineage(pack, by_id)
            except ValueError as exc:
                issues.append(_issue("INVALID_EVIDENCE_LINEAGE", source_type="evidence_pack", source_id=pack.pack_id))
                raise ValueError(f"invalid evidence lineage for {pack.pack_id}") from exc
        return packs

    @staticmethod
    def _assemble_rows(rows: Sequence[FmeaRow], packs: Sequence[EvidencePack], issues: list[ReadinessIssue]) -> tuple[RecordVersion, ...]:
        pack_ids = {pack.pack_id for pack in packs}
        result: list[RecordVersion] = []
        seen: set[str] = set()
        for row in sorted(rows, key=lambda item: item.row_id):
            if row.row_id in seen:
                raise ValueError("row IDs must be unique")
            seen.add(row.row_id)
            evidence_ids = _row_evidence_ids(row)
            if row.evidence_pack_id not in pack_ids:
                issues.append(_issue("MISSING_REQUIRED_EVIDENCE", source_type="row", source_id=row.row_id, evidence_ids=evidence_ids))
            if row.review_status is not ReviewStatus.ACCEPTED:
                issues.append(_issue("ROW_NOT_ACCEPTED", source_type="row", source_id=row.row_id, evidence_ids=evidence_ids))
            result.append((row.row_id, row.record_version, _record_hash(row)))
        return tuple(result)

    @staticmethod
    def _assemble_risks(
        risk_records: Sequence[RiskAssessmentRecord],
        source: GovernanceInputs,
        packs: Sequence[EvidencePack],
        issues: list[ReadinessIssue],
    ) -> tuple[RecordVersion, ...]:
        row_versions = {row.row_id: row.record_version for row in source.rows}
        pack_ids = {pack.pack_id for pack in packs}
        result: list[RecordVersion] = []
        seen: set[str] = set()
        for risk in sorted(risk_records, key=lambda item: item.assessment_id):
            if risk.assessment_id in seen:
                raise ValueError("risk assessment IDs must be unique")
            seen.add(risk.assessment_id)
            evidence_ids = tuple(sorted({evidence_id for dimension in risk.dimensions for evidence_id in dimension.evidence_ids}))
            if risk.evidence_pack_id not in pack_ids:
                issues.append(_issue("MISSING_REQUIRED_EVIDENCE", source_type="risk", source_id=risk.assessment_id, evidence_ids=evidence_ids))
            if risk.status is not RiskStatus.CONFIRMED:
                issues.append(_issue("RISK_NOT_CONFIRMED", source_type="risk", source_id=risk.assessment_id, evidence_ids=evidence_ids))
            expected_row_version = row_versions.get(risk.row_id)
            if expected_row_version is None or expected_row_version != risk.source_record_version:
                issues.append(_issue("STALE_RISK_VERSION", source_type="risk", source_id=risk.assessment_id, evidence_ids=evidence_ids))
            result.append((risk.assessment_id, risk.record_version, _record_hash(risk)))
        return tuple(result)

    @staticmethod
    def _assemble_graph(
        source: GovernanceInputs,
        analysis_version: int,
        packs: Sequence[EvidencePack],
        issues: list[ReadinessIssue],
    ) -> tuple[str | None, str | None]:
        graph = source.propagation_graph_revision
        if graph is None:
            issues.append(_issue("PROPAGATION_NOT_CONFIRMED", source_type="propagation_graph", source_id=source.analysis_id))
            return None, None
        pack_ids = {pack.pack_id for pack in packs}
        missing = tuple(sorted(set(graph.evidence_pack_ids).difference(pack_ids)))
        if missing:
            issues.append(_issue("MISSING_REQUIRED_EVIDENCE", source_type="propagation_graph", source_id=graph.graph_revision_id, evidence_ids=missing))
        if graph.status is not PropagationStatus.CONFIRMED:
            issues.append(_issue("PROPAGATION_NOT_CONFIRMED", source_type="propagation_graph", source_id=graph.graph_revision_id, evidence_ids=graph.evidence_pack_ids))
        if graph.analysis_record_version != analysis_version:
            issues.append(_issue("STALE_PROPAGATION_VERSION", source_type="propagation_graph", source_id=graph.graph_revision_id, evidence_ids=graph.evidence_pack_ids))
        for code in graph.unresolved_issue_codes:
            severity: Literal["blocking", "critical"] = "critical" if "HIGH" in code.upper() or "CRITICAL" in code.upper() else "blocking"
            issues.append(_issue(code, severity=severity, source_type="propagation_graph", source_id=graph.graph_revision_id, evidence_ids=graph.evidence_pack_ids))
        return graph.graph_revision_id, _record_hash(graph)

    def _parent_identity(self, request: RevisionAssemblyRequest, source: GovernanceInputs) -> tuple[str | None, str | None]:
        parent = source.parent_revision
        if request.parent_revision_id is None:
            if parent is not None:
                raise ValueError("parent revision supplied when request has no parent_revision_id")
            return None, None
        if parent is None:
            raise ValueError("parent revision is required for the requested parent_revision_id")
        if parent.revision_id != request.parent_revision_id:
            raise ValueError("parent revision ID does not match request")
        return parent.revision_id, parent.revision_hash

    @staticmethod
    def _revision_id(**values: object) -> str:
        return f"revision-{canonical_hash(canonical_json_value(values))[:32]}"


@dataclass(frozen=True, slots=True)
class PublicationReadinessContext:
    active_run_ids: tuple[str, ...] = ()
    current_analysis_version: int = 1
    current_child_hashes: tuple[tuple[str, str], ...] = ()
    required_fields_accepted: bool = True
    required_risk_confirmed: bool = True
    propagation_confirmed: bool = True
    required_evidence_present: bool = True
    acknowledgement_decision_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "active_run_ids", _sorted_texts(self.active_run_ids, "active_run_id"))
        object.__setattr__(self, "current_analysis_version", _positive(self.current_analysis_version, "current_analysis_version"))
        children: list[tuple[str, str]] = []
        for child_id, child_hash in _sequence(self.current_child_hashes, "current_child_hashes"):
            children.append((_text(child_id, "child_id"), _hash_for(child_hash)))
        if len({child_id for child_id, _ in children}) != len(children):
            raise ValueError("current_child_hashes must not contain duplicate child IDs")
        object.__setattr__(self, "current_child_hashes", tuple(sorted(children)))
        for field_name in ("required_fields_accepted", "required_risk_confirmed", "propagation_confirmed", "required_evidence_present"):
            if not isinstance(getattr(self, field_name), bool):
                raise TypeError(f"{field_name} must be a boolean")
        object.__setattr__(self, "acknowledgement_decision_ids", _sorted_texts(self.acknowledgement_decision_ids, "acknowledgement_decision_id"))


@dataclass(frozen=True, slots=True)
class PublicationReadinessReport:
    revision_id: str
    workspace_id: str
    analysis_id: str
    revision_hash: str
    target_record_version: int
    evidence_pack_ids: tuple[str, ...]
    ready: bool
    issues: tuple[ReadinessIssue, ...]
    blocking_codes: tuple[str, ...]
    deterministic: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "revision_id", _text(self.revision_id, "revision_id"))
        object.__setattr__(self, "workspace_id", _text(self.workspace_id, "workspace_id"))
        object.__setattr__(self, "analysis_id", _text(self.analysis_id, "analysis_id"))
        object.__setattr__(self, "revision_hash", _hash_for(self.revision_hash))
        object.__setattr__(self, "target_record_version", _positive(self.target_record_version, "target_record_version"))
        object.__setattr__(self, "evidence_pack_ids", _sorted_texts(self.evidence_pack_ids, "evidence_pack_id"))
        if not isinstance(self.ready, bool):
            raise TypeError("ready must be a boolean")
        object.__setattr__(self, "issues", _issue_tuple(self.issues))
        object.__setattr__(self, "blocking_codes", _sorted_texts(self.blocking_codes, "blocking_code"))
        if not isinstance(self.deterministic, bool) or not self.deterministic:
            raise ValueError("publication readiness must be deterministic")
        if self.ready == bool(self.blocking_codes):
            raise ValueError("ready must be false exactly when blocking_codes is non-empty")


def _coerce_context(value: PublicationReadinessContext | Mapping[str, object], revision: FmeaRevision) -> PublicationReadinessContext:
    if isinstance(value, PublicationReadinessContext):
        return value
    if not isinstance(value, Mapping):
        raise TypeError("readiness context must be a PublicationReadinessContext or mapping")
    allowed = {field.name for field in fields(PublicationReadinessContext)}
    unknown = set(value).difference(allowed)
    if unknown:
        raise TypeError(f"readiness context contains unsupported fields: {sorted(unknown)}")
    payload = dict(value)
    payload.setdefault("current_analysis_version", revision.analysis_record_version)
    return PublicationReadinessContext(**payload)


def _readiness_issue_key(issue: ReadinessIssue) -> tuple[str, str, str]:
    return issue.code, issue.source_type, issue.source_id


class PublicationReadinessPolicy:
    """Evaluate publication readiness using deterministic state only."""

    def __init__(self, domain_policy: Mapping[str, object] | None = None) -> None:
        policy = dict(domain_policy or {})
        self._allow_acknowledged_blocking = bool(policy.get("allow_acknowledged_blocking", False))
        self._required_risk = bool(policy.get("required_risk", True))
        self._required_propagation = bool(policy.get("required_propagation", True))

    def evaluate(  # noqa: C901
        self,
        revision: FmeaRevision,
        context: PublicationReadinessContext | Mapping[str, object],
    ) -> PublicationReadinessReport:
        if not isinstance(revision, FmeaRevision):
            raise TypeError("revision must be an FmeaRevision")
        current = _coerce_context(context, revision)
        issues = list(revision.unresolved_items)
        if current.active_run_ids:
            issues.extend(_issue(_ACTIVE_RUN_BLOCKER, source_type="run", source_id=run_id) for run_id in current.active_run_ids)
        if revision.analysis_record_version != current.current_analysis_version:
            issues.append(_issue("STALE_ANALYSIS_VERSION", source_type="analysis", source_id=revision.analysis_id))
        expected_children = dict(current.current_child_hashes)
        actual_children = self._revision_children(revision)
        for child_id, expected_hash in expected_children.items():
            if actual_children.get(child_id) != expected_hash:
                issues.append(_issue("STALE_CHILD_VERSION", source_type="child", source_id=child_id))
        if not current.required_fields_accepted:
            issues.append(_issue("REQUIRED_FIELDS_NOT_ACCEPTED", source_type="analysis", source_id=revision.analysis_id))
        if not revision.template_identities:
            issues.append(_issue("TEMPLATE_IDENTITY_UNRESOLVED", source_type="template", source_id=revision.analysis_id))
        if not revision.scoring_rule_identities:
            issues.append(_issue("SCORING_RULE_IDENTITY_UNRESOLVED", source_type="scoring_rule", source_id=revision.analysis_id))
        if revision.propagation_rule_identity is None:
            issues.append(_issue("PROPAGATION_RULE_IDENTITY_UNRESOLVED", source_type="propagation_rule", source_id=revision.analysis_id))
        if self._required_risk and (not current.required_risk_confirmed or not revision.risk_versions):
            issues.append(_issue("REQUIRED_RISK_NOT_CONFIRMED", source_type="risk", source_id=revision.analysis_id))
        if self._required_propagation and (not current.propagation_confirmed or revision.propagation_graph_revision_id is None):
            issues.append(_issue("REQUIRED_PROPAGATION_NOT_CONFIRMED", source_type="propagation_graph", source_id=revision.analysis_id))
        if not current.required_evidence_present or not revision.evidence_pack_hashes:
            issues.append(_issue("MISSING_REQUIRED_EVIDENCE", source_type="evidence", source_id=revision.analysis_id))
        deduplicated = {_readiness_issue_key(issue): issue for issue in issues}
        ordered = tuple(sorted(deduplicated.values(), key=lambda item: (_SEVERITY_ORDER[item.severity], _readiness_issue_key(item))))
        acknowledged = set(current.acknowledgement_decision_ids)
        blockers = tuple(
            sorted(
                {
                    issue.code
                    for issue in ordered
                    if _SEVERITY_ORDER[issue.severity] >= _SEVERITY_ORDER["blocking"]
                    and not (
                        self._allow_acknowledged_blocking
                        and issue.acknowledgement_decision_id is not None
                        and (
                            not acknowledged
                            or issue.acknowledgement_decision_id in acknowledged
                        )
                    )
                }
            )
        )
        return PublicationReadinessReport(
            revision_id=revision.revision_id,
            workspace_id=revision.workspace_id,
            analysis_id=revision.analysis_id,
            revision_hash=revision.revision_hash,
            target_record_version=revision.analysis_record_version,
            evidence_pack_ids=tuple(pack_id for pack_id, _ in revision.evidence_pack_hashes),
            ready=not blockers,
            issues=ordered,
            blocking_codes=blockers,
        )

    @staticmethod
    def _revision_children(revision: FmeaRevision) -> dict[str, str]:
        children = {record_id: record_hash for record_id, _, record_hash in revision.row_versions}
        children.update({record_id: record_hash for record_id, _, record_hash in revision.risk_versions})
        if revision.propagation_graph_revision_id is not None and revision.propagation_graph_hash is not None:
            children[revision.propagation_graph_revision_id] = revision.propagation_graph_hash
        children.update(dict(revision.evidence_pack_hashes))
        return children


@dataclass(frozen=True, slots=True)
class ReadinessChecklistDraft:
    ready: bool
    blocking_codes: tuple[str, ...]
    checklist: tuple[Mapping[str, object], ...]
    revision_id: str
    revision_hash: str

    def __post_init__(self) -> None:
        if not isinstance(self.ready, bool):
            raise TypeError("ready must be a boolean")
        object.__setattr__(self, "blocking_codes", _sorted_texts(self.blocking_codes, "blocking_code"))
        object.__setattr__(self, "checklist", tuple(MappingProxyType(dict(item)) for item in self.checklist))
        object.__setattr__(self, "revision_id", _text(self.revision_id, "revision_id"))
        object.__setattr__(self, "revision_hash", _hash_for(self.revision_hash))


__all__ = [
    "GovernanceInputs",
    "PublicationReadinessContext",
    "PublicationReadinessPolicy",
    "PublicationReadinessReport",
    "ReadinessChecklistDraft",
    "RevisionAssembler",
    "coerce_governance_inputs",
]
