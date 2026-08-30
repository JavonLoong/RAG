"""Deterministic assembly and readiness evaluation for FMEA revisions.

This module is deliberately a typed application boundary. Repository code
resolves the inputs first; this module never treats a mapping, a caller
supplied hash, or a retrieval profile as governance authority.
"""

# The application contracts use concise ValueError/TypeError boundaries.
# ruff: noqa: TRY003

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from types import MappingProxyType
from typing import Final, Literal
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
from core_domain.fmea.policies import validate_evidence_ids, validate_propagation_edge, validate_row_evidence
from core_domain.fmea.propagation import PropagationGraphRevision
from core_domain.fmea.scoring import RiskAssessmentRecord
from core_domain.fmea.states import ActorType, PropagationStatus, ReviewStatus, RiskStatus
from core_domain.fmea.value_objects import EvidencePack, EvidenceRef, validate_evidence_lineage
from fmea_application.governance_contracts import RevisionAssemblyRequest

Identity = tuple[str, str, str]
RecordVersion = tuple[str, int, str]
Clock = Callable[[], str]
IdFactory = Callable[[], str]

_HASH_LENGTH: Final = 64
_ACTIVE_RUN_BLOCKER: Final = "ACTIVE_MUTATION_RUN"
_SEVERITY_ORDER: Final = {"info": 0, "warning": 1, "blocking": 2, "critical": 3}
_ARTIFACT_TYPES: Final = {"domain_pack", "template", "scoring_rule", "propagation_rule"}


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


def _sequence(value: object, label: str) -> tuple[object, ...]:
    if isinstance(value, str | bytes) or value is None:
        raise TypeError(f"{label} must be a sequence")
    try:
        return tuple(value)  # type: ignore[arg-type]
    except TypeError as exc:
        raise TypeError(f"{label} must be a sequence") from exc


def _sorted_texts(value: object, label: str) -> tuple[str, ...]:
    return tuple(sorted({_text(item, label) for item in _sequence(value, label)}))


def _strict_hash(value: object, label: str, *, nonzero: bool = False) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a lowercase SHA-256 hash")
    candidate = value.removeprefix("sha256:")
    if len(candidate) != _HASH_LENGTH or any(char not in "0123456789abcdef" for char in candidate):
        raise ValueError(f"{label} must be a lowercase SHA-256 hash")
    if nonzero and set(candidate) == {"0"}:
        raise ValueError(f"{label} cannot be an unresolved zero hash")
    return value


def _hash_for(value: object) -> str:
    if isinstance(value, str):
        candidate = value.removeprefix("sha256:")
        if len(candidate) == _HASH_LENGTH and all(char in "0123456789abcdef" for char in candidate):
            return value
    return canonical_hash(value)


def _record_hash(value: object) -> str:
    for name in ("content_hash", "record_hash", "row_hash", "assessment_hash", "graph_hash"):
        candidate = getattr(value, name, None)
        if isinstance(candidate, str):
            normalized = candidate.removeprefix("sha256:")
            if len(normalized) == _HASH_LENGTH and all(char in "0123456789abcdef" for char in normalized):
                return candidate
    return canonical_hash(value)


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


def _issue_tuple(value: object) -> tuple[ReadinessIssue, ...]:
    items = tuple(_sequence(value, "unresolved_items"))
    if any(not isinstance(item, ReadinessIssue) for item in items):
        raise TypeError("unresolved_items must contain ReadinessIssue objects")
    unique = {(item.code, item.source_type, item.source_id): item for item in items}
    if len(unique) != len(items):
        raise ValueError("unresolved_items must not contain duplicate identities")
    return tuple(sorted(unique.values(), key=lambda item: (item.code, item.source_type, item.source_id)))


@dataclass(frozen=True, slots=True)
class ResolvedArtifactIdentity:
    """An identity proven by a server registry lookup."""

    artifact_type: str
    artifact_id: str
    version: str
    content_hash: str
    registry_verified: bool
    registry_source: str = "server_registry"

    def __post_init__(self) -> None:
        object.__setattr__(self, "artifact_type", _text(self.artifact_type, "artifact_type"))
        if self.artifact_type not in _ARTIFACT_TYPES:
            raise ValueError("artifact_type is unsupported")
        object.__setattr__(self, "artifact_id", _text(self.artifact_id, "artifact_id"))
        object.__setattr__(self, "version", _text(self.version, "version"))
        object.__setattr__(
            self, "content_hash", _strict_hash(self.content_hash, "content_hash", nonzero=True).removeprefix("sha256:")
        )
        if type(self.registry_verified) is not bool or not self.registry_verified:
            raise ValueError("artifact identity must be verified by a server registry")
        object.__setattr__(self, "registry_source", _text(self.registry_source, "registry_source"))

    @property
    def identity(self) -> Identity:
        return self.artifact_id, self.version, self.content_hash


@dataclass(frozen=True, slots=True)
class HumanAcknowledgementReference:
    """Server-resolved human decision reference for one exact issue."""

    decision_id: str
    workspace_id: str
    analysis_id: str
    issue_code: str
    issue_source_type: str
    issue_source_id: str
    actor_id: str
    actor_type: ActorType
    revision_id: str
    revision_record_version: int
    evidence_ids: tuple[str, ...]
    decision_record_version: int = 1

    def __post_init__(self) -> None:
        for field_name in (
            "decision_id",
            "workspace_id",
            "analysis_id",
            "issue_code",
            "issue_source_type",
            "issue_source_id",
            "actor_id",
            "revision_id",
        ):
            object.__setattr__(self, field_name, _text(getattr(self, field_name), field_name))
        if self.actor_type is not ActorType.HUMAN:
            raise ValueError("acknowledgement actor must be HUMAN")
        object.__setattr__(
            self, "revision_record_version", _positive(self.revision_record_version, "revision_record_version")
        )
        object.__setattr__(
            self, "decision_record_version", _positive(self.decision_record_version, "decision_record_version")
        )
        object.__setattr__(self, "evidence_ids", _sorted_texts(self.evidence_ids, "evidence_id"))

    def matches(self, revision: FmeaRevision, issue: ReadinessIssue) -> bool:
        return (
            self.decision_id == issue.acknowledgement_decision_id
            and self.workspace_id == revision.workspace_id
            and self.analysis_id == revision.analysis_id
            and self.issue_code == issue.code
            and self.issue_source_type == issue.source_type
            and self.issue_source_id == issue.source_id
            and self.revision_id == revision.revision_id
            and self.revision_record_version == revision.analysis_record_version
            and self.evidence_ids == issue.evidence_ids
            and self.actor_type is ActorType.HUMAN
        )


@dataclass(frozen=True, slots=True)
class GovernanceDomainPolicy:
    """Typed server policy controlling which artifacts are required."""

    required_risk: bool = True
    required_propagation: bool = True
    required_template: bool = True
    required_scoring_rule: bool = True
    required_propagation_rule: bool = True
    required_evidence: bool = True
    allow_acknowledged_blocking: bool = False

    def __post_init__(self) -> None:
        for field_name in (
            "required_risk",
            "required_propagation",
            "required_template",
            "required_scoring_rule",
            "required_propagation_rule",
            "required_evidence",
            "allow_acknowledged_blocking",
        ):
            if type(getattr(self, field_name)) is not bool:
                raise TypeError(f"{field_name} must be a boolean")

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> GovernanceDomainPolicy:
        allowed = set(cls.__dataclass_fields__)
        unknown = set(value).difference(allowed)
        if unknown:
            raise TypeError(f"GovernanceDomainPolicy contains unsupported fields: {sorted(unknown)}")
        return cls(**dict(value))


@dataclass(frozen=True, slots=True)
class GovernanceArtifactSet:
    """Registry-resolved artifact manifests used to construct GovernanceInputs."""

    domain_pack: DomainPackManifest
    domain_pack_identity: ResolvedArtifactIdentity
    template_identities: tuple[ResolvedArtifactIdentity, ...]
    scoring_rule_identities: tuple[ResolvedArtifactIdentity, ...]
    propagation_rule_identity: ResolvedArtifactIdentity | None

    def __post_init__(self) -> None:
        if not isinstance(self.domain_pack, DomainPackManifest):
            raise TypeError("domain_pack must be a DomainPackManifest")
        if not isinstance(self.domain_pack_identity, ResolvedArtifactIdentity):
            raise TypeError("domain_pack_identity must be a ResolvedArtifactIdentity")
        self._check_identity(
            self.domain_pack_identity,
            "domain_pack",
            (self.domain_pack.pack_id, self.domain_pack.version),
            self.domain_pack.content_hash,
        )
        self._check_identities(self.template_identities, "template", set(self.domain_pack.template_identities))
        self._check_identities(
            self.scoring_rule_identities, "scoring_rule", set(self.domain_pack.scoring_rule_identities)
        )
        if self.propagation_rule_identity is not None:
            self._check_identity(
                self.propagation_rule_identity, "propagation_rule", set(self.domain_pack.propagation_rule_identities)
            )

    @staticmethod
    def _check_identity(
        identity: ResolvedArtifactIdentity,
        expected_type: str,
        expected_pair: tuple[str, str] | set[tuple[str, str]],
        expected_hash: str | None = None,
    ) -> None:
        if not isinstance(identity, ResolvedArtifactIdentity) or identity.artifact_type != expected_type:
            raise ValueError(f"{expected_type} identity has the wrong type")
        pair = (identity.artifact_id, identity.version)
        valid = pair in expected_pair if isinstance(expected_pair, set) else pair == expected_pair
        if not valid:
            raise ValueError(f"{expected_type} identity is not declared by the domain pack")
        if expected_hash is not None and identity.content_hash != expected_hash:
            raise ValueError(f"{expected_type} identity hash does not match its manifest")

    @classmethod
    def _check_identities(
        cls,
        identities: tuple[ResolvedArtifactIdentity, ...],
        expected_type: str,
        expected_pairs: set[tuple[str, str]],
    ) -> None:
        if any(not isinstance(item, ResolvedArtifactIdentity) for item in identities):
            raise TypeError(f"{expected_type}_identities must contain ResolvedArtifactIdentity objects")
        pairs = {(item.artifact_id, item.version) for item in identities}
        if len(pairs) != len(identities):
            raise ValueError(f"duplicate {expected_type} identity")
        for item in identities:
            cls._check_identity(item, expected_type, expected_pairs)


@dataclass(frozen=True, slots=True)
class GovernanceInputs:
    """Typed server-owned accepted/confirmed state for one analysis."""

    workspace_id: str
    analysis_id: str
    analysis: FmeaAnalysis
    domain_pack: DomainPackManifest
    domain_pack_identity: ResolvedArtifactIdentity
    rows: tuple[FmeaRow, ...] = ()
    risk_records: tuple[RiskAssessmentRecord, ...] = ()
    propagation_graph_revision: PropagationGraphRevision | None = None
    evidence_packs: tuple[EvidencePack, ...] = ()
    template_identities: tuple[ResolvedArtifactIdentity, ...] = ()
    scoring_rule_identities: tuple[ResolvedArtifactIdentity, ...] = ()
    propagation_rule_identity: ResolvedArtifactIdentity | None = None
    requested_profile: str = "combined"
    resolved_profile: str = "combined"
    evidence_types: tuple[str, ...] = ()
    source_counts: tuple[tuple[str, int], ...] = ()
    retrieval_warnings: tuple[str, ...] = ()
    unresolved_items: tuple[ReadinessIssue, ...] = ()
    acknowledgement_references: tuple[HumanAcknowledgementReference, ...] = ()
    active_run_ids: tuple[str, ...] = ()
    created_at: str | None = None
    parent_revision: FmeaRevision | None = None

    def __post_init__(self) -> None:  # noqa: C901
        object.__setattr__(self, "workspace_id", _text(self.workspace_id, "workspace_id"))
        object.__setattr__(self, "analysis_id", _text(self.analysis_id, "analysis_id"))
        if not isinstance(self.analysis, FmeaAnalysis):
            raise TypeError("analysis must be a FmeaAnalysis")
        if self.analysis.analysis_id != self.analysis_id:
            raise ValueError("analysis_id does not match the authoritative analysis object")
        if hasattr(self.analysis, "workspace_id") and self.analysis.workspace_id != self.workspace_id:
            raise ValueError("analysis workspace_id does not match governance workspace")
        if not isinstance(self.domain_pack, DomainPackManifest):
            raise TypeError("domain_pack must be a DomainPackManifest")
        if self.analysis.analysis_type not in self.domain_pack.analysis_types:
            raise ValueError("domain pack does not support the authoritative analysis type")
        if not isinstance(self.domain_pack_identity, ResolvedArtifactIdentity):
            raise TypeError("domain_pack_identity must be a ResolvedArtifactIdentity")
        GovernanceArtifactSet._check_identity(
            self.domain_pack_identity,
            "domain_pack",
            (self.domain_pack.pack_id, self.domain_pack.version),
            self.domain_pack.content_hash,
        )
        object.__setattr__(self, "rows", tuple(self.rows))
        object.__setattr__(self, "risk_records", tuple(self.risk_records))
        object.__setattr__(self, "evidence_packs", tuple(self.evidence_packs))
        if any(not isinstance(item, FmeaRow) for item in self.rows):
            raise TypeError("rows must contain FmeaRow objects")
        if any(not isinstance(item, RiskAssessmentRecord) for item in self.risk_records):
            raise TypeError("risk_records must contain RiskAssessmentRecord objects")
        if self.propagation_graph_revision is not None and not isinstance(
            self.propagation_graph_revision, PropagationGraphRevision
        ):
            raise TypeError("propagation_graph_revision must be a PropagationGraphRevision")
        if any(not isinstance(item, EvidencePack) for item in self.evidence_packs):
            raise TypeError("evidence_packs must contain EvidencePack objects")
        object.__setattr__(self, "template_identities", tuple(self.template_identities))
        object.__setattr__(self, "scoring_rule_identities", tuple(self.scoring_rule_identities))
        GovernanceArtifactSet._check_identities(
            self.template_identities, "template", set(self.domain_pack.template_identities)
        )
        GovernanceArtifactSet._check_identities(
            self.scoring_rule_identities, "scoring_rule", set(self.domain_pack.scoring_rule_identities)
        )
        if self.propagation_rule_identity is not None:
            GovernanceArtifactSet._check_identity(
                self.propagation_rule_identity, "propagation_rule", set(self.domain_pack.propagation_rule_identities)
            )
        object.__setattr__(self, "requested_profile", _text(self.requested_profile, "requested_profile"))
        object.__setattr__(self, "resolved_profile", _text(self.resolved_profile, "resolved_profile"))
        object.__setattr__(self, "evidence_types", _sorted_texts(self.evidence_types, "evidence_type"))
        counts: list[tuple[str, int]] = []
        for source_type, count in _sequence(self.source_counts, "source_counts"):
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                raise ValueError("source_counts values must be non-negative integers")
            counts.append((_text(source_type, "source_type"), count))
        if len({source_type for source_type, _ in counts}) != len(counts):
            raise ValueError("source_counts must not contain duplicate source types")
        object.__setattr__(self, "source_counts", tuple(sorted(counts)))
        object.__setattr__(self, "retrieval_warnings", _sorted_texts(self.retrieval_warnings, "retrieval_warning"))
        object.__setattr__(self, "unresolved_items", _issue_tuple(self.unresolved_items))
        acknowledgements = tuple(self.acknowledgement_references)
        if any(not isinstance(item, HumanAcknowledgementReference) for item in acknowledgements):
            raise TypeError("acknowledgement_references must contain HumanAcknowledgementReference objects")
        if len({item.decision_id for item in acknowledgements}) != len(acknowledgements):
            raise ValueError("acknowledgement_references must not contain duplicate decision IDs")
        if any(
            item.workspace_id != self.workspace_id or item.analysis_id != self.analysis_id for item in acknowledgements
        ):
            raise ValueError("acknowledgement reference is outside governance scope")
        object.__setattr__(
            self, "acknowledgement_references", tuple(sorted(acknowledgements, key=lambda item: item.decision_id))
        )
        object.__setattr__(self, "active_run_ids", _sorted_texts(self.active_run_ids, "active_run_id"))
        if self.parent_revision is not None and not isinstance(self.parent_revision, FmeaRevision):
            raise TypeError("parent_revision must be an FmeaRevision")


def _row_evidence_ids(row: FmeaRow) -> tuple[str, ...]:
    return tuple(sorted({evidence_id for _, evidence_ids in row.field_evidence for evidence_id in evidence_ids}))


def _append_issue(issues: list[ReadinessIssue], issue: ReadinessIssue) -> None:
    if (issue.code, issue.source_type, issue.source_id) not in {
        (item.code, item.source_type, item.source_id) for item in issues
    }:
        issues.append(issue)


class RevisionAssembler:
    """Assemble one immutable, canonical FMEA revision from typed state."""

    def __init__(self, clock: Clock = _utc_now, id_factory: IdFactory | None = None) -> None:
        self._clock = clock
        self._id_factory = id_factory or _stable_id

    def assemble(self, request: RevisionAssemblyRequest, inputs: GovernanceInputs) -> FmeaRevision:
        if not isinstance(request, RevisionAssemblyRequest):
            raise TypeError("request must be a RevisionAssemblyRequest")
        if not isinstance(inputs, GovernanceInputs):
            raise TypeError("inputs must be a GovernanceInputs")
        if inputs.analysis_id != request.analysis_id:
            raise ValueError("request analysis_id does not match governance inputs")
        analysis_version = inputs.analysis.record_version
        if analysis_version != request.expected_analysis_version:
            raise ValueError("expected analysis version does not match authoritative analysis")
        analysis_hash = canonical_hash(inputs.analysis)
        issues: list[ReadinessIssue] = list(inputs.unresolved_items)
        self._validate_source_scope(inputs)
        packs = self._validate_evidence(inputs, issues)
        rows = self._assemble_rows(inputs.rows, packs, issues)
        risks = self._assemble_risks(inputs.risk_records, inputs, packs, issues)
        graph_id, graph_hash = self._assemble_graph(inputs, analysis_version, packs, issues)
        for run_id in inputs.active_run_ids:
            _append_issue(issues, _issue(_ACTIVE_RUN_BLOCKER, source_type="run", source_id=run_id))
        for item in tuple(issues):
            if item.acknowledgement_decision_id is not None and not any(
                ref.decision_id == item.acknowledgement_decision_id for ref in inputs.acknowledgement_references
            ):
                _append_issue(
                    issues,
                    _issue(
                        "ACKNOWLEDGEMENT_REFERENCE_UNRESOLVED",
                        source_type="acknowledgement",
                        source_id=item.acknowledgement_decision_id,
                    ),
                )
        parent_id, parent_hash = self._parent_identity(request, inputs)
        provenance = RetrievalProvenanceSnapshot(
            requested_profile=inputs.requested_profile,
            resolved_profile=inputs.resolved_profile,
            evidence_types=inputs.evidence_types,
            source_counts=inputs.source_counts,
            warnings=inputs.retrieval_warnings,
        )
        domain_identity = inputs.domain_pack_identity.identity
        templates = tuple(sorted(item.identity for item in inputs.template_identities))
        scoring = tuple(sorted(item.identity for item in inputs.scoring_rule_identities))
        propagation_rule = (
            None if inputs.propagation_rule_identity is None else inputs.propagation_rule_identity.identity
        )
        revision_id = self._revision_id(
            analysis_id=inputs.analysis_id,
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
            issues=_issue_tuple(issues),
        )
        body = {
            "revision_id": revision_id,
            "workspace_id": inputs.workspace_id,
            "analysis_id": inputs.analysis_id,
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
        return FmeaRevision(
            **body,
            revision_hash=canonical_hash(canonical_json_value(body), max_array_items=10_000),
            created_at=inputs.created_at or self._clock(),
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

    def _validate_evidence(self, source: GovernanceInputs, issues: list[ReadinessIssue]) -> tuple[EvidencePack, ...]:  # noqa: C901
        packs = tuple(sorted(source.evidence_packs, key=lambda pack: pack.pack_id))
        by_id = {pack.pack_id: pack for pack in packs}
        if len(by_id) != len(packs):
            raise ValueError("evidence pack IDs must be unique")
        now = self._parse_time(self._clock(), issues, source.analysis_id)
        for pack in packs:
            pack_created_at = self._parse_time(pack.created_at, issues, pack.pack_id)
            try:
                validate_evidence_lineage(pack, by_id)
            except ValueError:
                _append_issue(
                    issues, _issue("INVALID_EVIDENCE_LINEAGE", source_type="evidence_pack", source_id=pack.pack_id)
                )
            if not isinstance(pack.pack_hash, str) or set(pack.pack_hash.removeprefix("sha256:")) == {"0"}:
                _append_issue(
                    issues, _issue("INVALID_EVIDENCE_PACK", source_type="evidence_pack", source_id=pack.pack_id)
                )
            if pack.expires_at is not None and self._expired(pack.expires_at, now):
                _append_issue(issues, _issue("EXPIRED_EVIDENCE", source_type="evidence_pack", source_id=pack.pack_id))
            if pack_created_at is not None and now is not None and pack_created_at > now:
                _append_issue(
                    issues, _issue("INVALID_EVIDENCE_PACK", source_type="evidence_pack", source_id=pack.pack_id)
                )
            for ref in pack.refs:
                if not isinstance(ref, EvidenceRef):
                    _append_issue(
                        issues, _issue("INVALID_EVIDENCE_PACK", source_type="evidence_pack", source_id=pack.pack_id)
                    )
                    continue
                if ref.workspace_id != source.workspace_id or not set(ref.acl_scope).issubset(set(pack.acl_scope)):
                    _append_issue(
                        issues, _issue("INVALID_EVIDENCE_PACK", source_type="evidence", source_id=ref.evidence_id)
                    )
                ref_created_at = self._parse_time(ref.created_at, issues, ref.evidence_id)
                if ref_created_at is not None and now is not None and ref_created_at > now:
                    _append_issue(
                        issues, _issue("INVALID_EVIDENCE_PACK", source_type="evidence", source_id=ref.evidence_id)
                    )
                if ref.expires_at is not None and self._expired(ref.expires_at, now):
                    _append_issue(issues, _issue("EXPIRED_EVIDENCE", source_type="evidence", source_id=ref.evidence_id))
        return packs

    @staticmethod
    def _parse_time(value: object, issues: list[ReadinessIssue], source_id: str) -> datetime | None:
        if not isinstance(value, str):
            _append_issue(issues, _issue("INVALID_EVIDENCE_PACK", source_type="evidence", source_id=source_id))
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            _append_issue(issues, _issue("INVALID_EVIDENCE_PACK", source_type="evidence", source_id=source_id))
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _expired(value: str, now: datetime | None) -> bool:
        if now is None:
            return True
        try:
            expiry = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return True
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        return expiry.astimezone(timezone.utc) <= now

    @staticmethod
    def _assemble_rows(
        rows: Sequence[FmeaRow], packs: Sequence[EvidencePack], issues: list[ReadinessIssue]
    ) -> tuple[RecordVersion, ...]:
        by_id = {pack.pack_id: pack for pack in packs}
        result: list[RecordVersion] = []
        seen: set[str] = set()
        for row in sorted(rows, key=lambda item: item.row_id):
            if row.row_id in seen:
                raise ValueError("row IDs must be unique")
            seen.add(row.row_id)
            evidence_ids = _row_evidence_ids(row)
            pack = by_id.get(row.evidence_pack_id)
            if pack is None:
                _append_issue(
                    issues,
                    _issue(
                        "MISSING_REQUIRED_EVIDENCE", source_type="row", source_id=row.row_id, evidence_ids=evidence_ids
                    ),
                )
            else:
                try:
                    validate_row_evidence(row, pack)
                except ValueError:
                    _append_issue(
                        issues,
                        _issue(
                            "INVALID_EVIDENCE_REFERENCE",
                            source_type="row",
                            source_id=row.row_id,
                            evidence_ids=evidence_ids,
                        ),
                    )
            if row.review_status is not ReviewStatus.ACCEPTED:
                _append_issue(
                    issues,
                    _issue("ROW_NOT_ACCEPTED", source_type="row", source_id=row.row_id, evidence_ids=evidence_ids),
                )
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
        by_id = {pack.pack_id: pack for pack in packs}
        scoring_pairs = {(item.artifact_id, item.version) for item in source.scoring_rule_identities}
        domain_pair = (source.domain_pack.pack_id, source.domain_pack.version)
        result: list[RecordVersion] = []
        seen: set[str] = set()
        for risk in sorted(risk_records, key=lambda item: item.assessment_id):
            if risk.assessment_id in seen:
                raise ValueError("risk assessment IDs must be unique")
            seen.add(risk.assessment_id)
            evidence_ids = tuple(
                sorted({evidence_id for dimension in risk.dimensions for evidence_id in dimension.evidence_ids})
            )
            pack = by_id.get(risk.evidence_pack_id)
            if pack is None:
                _append_issue(
                    issues,
                    _issue(
                        "MISSING_REQUIRED_EVIDENCE",
                        source_type="risk",
                        source_id=risk.assessment_id,
                        evidence_ids=evidence_ids,
                    ),
                )
            else:
                try:
                    for dimension in risk.dimensions:
                        validate_evidence_ids(dimension.evidence_ids, pack)
                except ValueError:
                    _append_issue(
                        issues,
                        _issue(
                            "INVALID_EVIDENCE_REFERENCE",
                            source_type="risk",
                            source_id=risk.assessment_id,
                            evidence_ids=evidence_ids,
                        ),
                    )
            if (risk.domain_pack_id, risk.domain_pack_version) != domain_pair or (
                risk.rule_pack_id,
                risk.rule_pack_version,
            ) not in scoring_pairs:
                _append_issue(
                    issues,
                    _issue(
                        "RISK_ARTIFACT_IDENTITY_MISMATCH",
                        source_type="risk",
                        source_id=risk.assessment_id,
                        evidence_ids=evidence_ids,
                    ),
                )
            if risk.status is not RiskStatus.CONFIRMED:
                _append_issue(
                    issues,
                    _issue(
                        "RISK_NOT_CONFIRMED",
                        source_type="risk",
                        source_id=risk.assessment_id,
                        evidence_ids=evidence_ids,
                    ),
                )
            expected_row_version = row_versions.get(risk.row_id)
            if expected_row_version is None or expected_row_version != risk.source_record_version:
                _append_issue(
                    issues,
                    _issue(
                        "STALE_RISK_VERSION",
                        source_type="risk",
                        source_id=risk.assessment_id,
                        evidence_ids=evidence_ids,
                    ),
                )
            result.append((risk.assessment_id, risk.record_version, _record_hash(risk)))
        return tuple(result)

    @staticmethod
    def _assemble_graph(  # noqa: C901
        source: GovernanceInputs,
        analysis_version: int,
        packs: Sequence[EvidencePack],
        issues: list[ReadinessIssue],
    ) -> tuple[str | None, str | None]:
        graph = source.propagation_graph_revision
        if graph is None:
            return None, None
        by_id = {pack.pack_id: pack for pack in packs}
        if (graph.domain_pack_id, graph.domain_pack_version) != (
            source.domain_pack.pack_id,
            source.domain_pack.version,
        ):
            _append_issue(
                issues,
                _issue(
                    "PROPAGATION_ARTIFACT_IDENTITY_MISMATCH",
                    source_type="propagation_graph",
                    source_id=graph.graph_revision_id,
                ),
            )
        graph_rule = (graph.rule_pack_id, graph.rule_pack_version)
        if graph_rule not in set(source.domain_pack.propagation_rule_identities):
            _append_issue(
                issues,
                _issue(
                    "PROPAGATION_RULE_IDENTITY_MISMATCH",
                    source_type="propagation_graph",
                    source_id=graph.graph_revision_id,
                ),
            )
        if source.propagation_rule_identity is not None and source.propagation_rule_identity.identity[:2] != graph_rule:
            _append_issue(
                issues,
                _issue(
                    "PROPAGATION_RULE_IDENTITY_MISMATCH",
                    source_type="propagation_graph",
                    source_id=graph.graph_revision_id,
                ),
            )
        if graph.status is not PropagationStatus.CONFIRMED:
            _append_issue(
                issues,
                _issue(
                    "PROPAGATION_NOT_CONFIRMED",
                    source_type="propagation_graph",
                    source_id=graph.graph_revision_id,
                    evidence_ids=graph.evidence_pack_ids,
                ),
            )
        if graph.analysis_record_version != analysis_version:
            _append_issue(
                issues,
                _issue(
                    "STALE_PROPAGATION_VERSION",
                    source_type="propagation_graph",
                    source_id=graph.graph_revision_id,
                    evidence_ids=graph.evidence_pack_ids,
                ),
            )
        for code in graph.unresolved_issue_codes:
            severity: Literal["blocking", "critical"] = (
                "critical" if "HIGH" in code.upper() or "CRITICAL" in code.upper() else "blocking"
            )
            _append_issue(
                issues,
                _issue(
                    code,
                    severity=severity,
                    source_type="propagation_graph",
                    source_id=graph.graph_revision_id,
                    evidence_ids=graph.evidence_pack_ids,
                ),
            )
        for path in graph.paths:
            if path.analysis_id != source.analysis_id:
                raise ValueError("propagation path analysis_id does not match governance analysis")
        for edge in (*graph.edges, *(path_edge for path in graph.paths for path_edge in path.edges)):
            if edge.analysis_id != source.analysis_id:
                raise ValueError("propagation edge analysis_id does not match governance analysis")
            pack = by_id.get(edge.evidence_pack_id)
            if pack is None:
                _append_issue(
                    issues,
                    _issue(
                        "MISSING_REQUIRED_EVIDENCE",
                        source_type="propagation_edge",
                        source_id=edge.edge_id,
                        evidence_ids=edge.evidence_ids,
                    ),
                )
                continue
            try:
                validate_propagation_edge(edge, pack)
            except ValueError:
                _append_issue(
                    issues,
                    _issue(
                        "INVALID_EVIDENCE_REFERENCE",
                        source_type="propagation_edge",
                        source_id=edge.edge_id,
                        evidence_ids=edge.evidence_ids,
                    ),
                )
        missing = tuple(sorted(set(graph.evidence_pack_ids).difference(by_id)))
        if missing:
            _append_issue(
                issues,
                _issue(
                    "MISSING_REQUIRED_EVIDENCE",
                    source_type="propagation_graph",
                    source_id=graph.graph_revision_id,
                    evidence_ids=missing,
                ),
            )
        return graph.graph_revision_id, _record_hash(graph)

    @staticmethod
    def _parent_identity(request: RevisionAssemblyRequest, source: GovernanceInputs) -> tuple[str | None, str | None]:
        parent = source.parent_revision
        if request.parent_revision_id is None:
            if parent is not None or request.parent_revision_hash is not None:
                raise ValueError("parent revision supplied when request has no parent_revision_id")
            return None, None
        if parent is None:
            raise ValueError("parent revision is required for the requested parent_revision_id")
        if parent.revision_id != request.parent_revision_id:
            raise ValueError("parent revision ID does not match request")
        if request.parent_revision_hash is None or parent.revision_hash != request.parent_revision_hash:
            raise ValueError("parent revision hash does not match request")
        if parent.workspace_id != source.workspace_id or parent.analysis_id != source.analysis_id:
            raise ValueError("parent revision workspace/analysis does not match governance scope")
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
    acknowledgement_references: tuple[HumanAcknowledgementReference, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "active_run_ids", _sorted_texts(self.active_run_ids, "active_run_id"))
        object.__setattr__(
            self, "current_analysis_version", _positive(self.current_analysis_version, "current_analysis_version")
        )
        children: list[tuple[str, str]] = []
        for child_id, child_hash in _sequence(self.current_child_hashes, "current_child_hashes"):
            children.append((_text(child_id, "child_id"), _hash_for(child_hash)))
        if len({child_id for child_id, _ in children}) != len(children):
            raise ValueError("current_child_hashes must not contain duplicate child IDs")
        object.__setattr__(self, "current_child_hashes", tuple(sorted(children)))
        for field_name in (
            "required_fields_accepted",
            "required_risk_confirmed",
            "propagation_confirmed",
            "required_evidence_present",
        ):
            if type(getattr(self, field_name)) is not bool:
                raise TypeError(f"{field_name} must be a boolean")
        acknowledgements = tuple(self.acknowledgement_references)
        if any(not isinstance(item, HumanAcknowledgementReference) for item in acknowledgements):
            raise TypeError("acknowledgement_references must contain HumanAcknowledgementReference objects")
        object.__setattr__(
            self, "acknowledgement_references", tuple(sorted(acknowledgements, key=lambda item: item.decision_id))
        )


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
        object.__setattr__(
            self, "target_record_version", _positive(self.target_record_version, "target_record_version")
        )
        object.__setattr__(self, "evidence_pack_ids", _sorted_texts(self.evidence_pack_ids, "evidence_pack_id"))
        if type(self.ready) is not bool:
            raise TypeError("ready must be a boolean")
        object.__setattr__(self, "issues", _issue_tuple(self.issues))
        object.__setattr__(self, "blocking_codes", _sorted_texts(self.blocking_codes, "blocking_code"))
        if type(self.deterministic) is not bool or not self.deterministic:
            raise ValueError("publication readiness must be deterministic")
        if self.ready == bool(self.blocking_codes):
            raise ValueError("ready must be false exactly when blocking_codes is non-empty")


def _readiness_issue_key(issue: ReadinessIssue) -> tuple[str, str, str]:
    return issue.code, issue.source_type, issue.source_id


def _identity_hash_is_resolved(identity: object) -> bool:
    if not isinstance(identity, tuple) or len(identity) != 3 or not all(isinstance(item, str) for item in identity):
        return False
    candidate = identity[2].removeprefix("sha256:")
    return (
        len(candidate) == _HASH_LENGTH
        and all(char in "0123456789abcdef" for char in candidate)
        and set(candidate) != {"0"}
    )


class PublicationReadinessPolicy:
    """Evaluate readiness deterministically from a typed domain policy."""

    def __init__(self, domain_policy: GovernanceDomainPolicy | None = None) -> None:
        if domain_policy is not None and not isinstance(domain_policy, GovernanceDomainPolicy):
            raise TypeError("domain_policy must be a GovernanceDomainPolicy")
        self._domain_policy = domain_policy or GovernanceDomainPolicy()

    def evaluate(self, revision: FmeaRevision, context: PublicationReadinessContext) -> PublicationReadinessReport:  # noqa: C901
        if not isinstance(revision, FmeaRevision):
            raise TypeError("revision must be an FmeaRevision")
        if not isinstance(context, PublicationReadinessContext):
            raise TypeError("context must be a PublicationReadinessContext")
        issues = list(revision.unresolved_items)
        policy = self._domain_policy
        if context.active_run_ids:
            issues.extend(
                _issue(_ACTIVE_RUN_BLOCKER, source_type="run", source_id=run_id) for run_id in context.active_run_ids
            )
        if revision.analysis_record_version != context.current_analysis_version:
            issues.append(_issue("STALE_ANALYSIS_VERSION", source_type="analysis", source_id=revision.analysis_id))
        actual_children = self._revision_children(revision)
        for child_id, expected_hash in context.current_child_hashes:
            if actual_children.get(child_id) != expected_hash:
                issues.append(_issue("STALE_CHILD_VERSION", source_type="child", source_id=child_id))
        if not context.required_fields_accepted:
            issues.append(
                _issue("REQUIRED_FIELDS_NOT_ACCEPTED", source_type="analysis", source_id=revision.analysis_id)
            )
        self._artifact_readiness_issues(revision, policy, issues)
        if policy.required_risk and (not context.required_risk_confirmed or not revision.risk_versions):
            issues.append(_issue("REQUIRED_RISK_NOT_CONFIRMED", source_type="risk", source_id=revision.analysis_id))
        if policy.required_propagation and (
            not context.propagation_confirmed or revision.propagation_graph_revision_id is None
        ):
            issues.append(
                _issue(
                    "REQUIRED_PROPAGATION_NOT_CONFIRMED",
                    source_type="propagation_graph",
                    source_id=revision.analysis_id,
                )
            )
        if policy.required_evidence and (not context.required_evidence_present or not revision.evidence_pack_hashes):
            issues.append(_issue("MISSING_REQUIRED_EVIDENCE", source_type="evidence", source_id=revision.analysis_id))
        deduplicated = {_readiness_issue_key(issue): issue for issue in issues}
        ordered = tuple(
            sorted(deduplicated.values(), key=lambda item: (_SEVERITY_ORDER[item.severity], _readiness_issue_key(item)))
        )
        blockers: set[str] = set()
        for issue in ordered:
            if _SEVERITY_ORDER[issue.severity] < _SEVERITY_ORDER["blocking"]:
                continue
            if not (
                policy.allow_acknowledged_blocking
                and issue.acknowledgement_decision_id is not None
                and any(reference.matches(revision, issue) for reference in context.acknowledgement_references)
            ):
                blockers.add(issue.code)
        return PublicationReadinessReport(
            revision_id=revision.revision_id,
            workspace_id=revision.workspace_id,
            analysis_id=revision.analysis_id,
            revision_hash=revision.revision_hash,
            target_record_version=revision.analysis_record_version,
            evidence_pack_ids=tuple(pack_id for pack_id, _ in revision.evidence_pack_hashes),
            ready=not blockers,
            issues=ordered,
            blocking_codes=tuple(sorted(blockers)),
        )

    @staticmethod
    def _artifact_readiness_issues(
        revision: FmeaRevision, policy: GovernanceDomainPolicy, issues: list[ReadinessIssue]
    ) -> None:
        identities: tuple[tuple[str, object, bool], ...] = (
            ("domain_pack", revision.domain_pack_identity, True),
            ("template", revision.template_identities, policy.required_template),
            ("scoring_rule", revision.scoring_rule_identities, policy.required_scoring_rule),
            ("propagation_rule", revision.propagation_rule_identity, policy.required_propagation_rule),
        )
        for artifact_type, raw_values, required in identities:
            if artifact_type == "propagation_rule":
                values = () if raw_values is None else (raw_values,)
            elif artifact_type == "domain_pack":
                values = (raw_values,)
            else:
                values = raw_values
            if required and not values:
                issues.append(
                    _issue(
                        f"{artifact_type.upper()}_IDENTITY_UNRESOLVED",
                        source_type=artifact_type,
                        source_id=revision.analysis_id,
                    )
                )
            for identity in values:
                if not _identity_hash_is_resolved(identity):
                    issues.append(
                        _issue(
                            "UNRESOLVED_ARTIFACT_IDENTITY", source_type=artifact_type, source_id=revision.analysis_id
                        )
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
class ReadinessIssueProjection:
    code: str
    severity: Literal["info", "warning", "blocking", "critical"]
    source_type: str
    source_id: str
    evidence_ids: tuple[str, ...]
    acknowledgement_decision_id: str | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", _text(self.code, "code"))
        if self.severity not in _SEVERITY_ORDER:
            raise ValueError("projection issue severity is invalid")
        object.__setattr__(self, "source_type", _text(self.source_type, "source_type"))
        object.__setattr__(self, "source_id", _text(self.source_id, "source_id"))
        object.__setattr__(self, "evidence_ids", _sorted_texts(self.evidence_ids, "evidence_id"))
        if self.acknowledgement_decision_id is not None:
            object.__setattr__(
                self,
                "acknowledgement_decision_id",
                _text(self.acknowledgement_decision_id, "acknowledgement_decision_id"),
            )


@dataclass(frozen=True, slots=True)
class ReadinessChecklistProjection:
    """Allowlisted, bounded readiness data safe to send to an assistance model."""

    revision_id: str
    revision_hash: str
    target_record_version: int
    ready: bool
    blocking_codes: tuple[str, ...]
    issues: tuple[ReadinessIssueProjection, ...]
    evidence_pack_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "revision_id", _text(self.revision_id, "revision_id"))
        object.__setattr__(self, "revision_hash", _hash_for(self.revision_hash))
        object.__setattr__(
            self, "target_record_version", _positive(self.target_record_version, "target_record_version")
        )
        if type(self.ready) is not bool:
            raise TypeError("ready must be a boolean")
        object.__setattr__(self, "blocking_codes", _sorted_texts(self.blocking_codes, "blocking_code"))
        issues = tuple(self.issues)
        if len(issues) > 256 or any(not isinstance(issue, ReadinessIssueProjection) for issue in issues):
            raise TypeError("projection issues are invalid or too large")
        object.__setattr__(self, "issues", issues)
        object.__setattr__(self, "evidence_pack_ids", _sorted_texts(self.evidence_pack_ids, "evidence_pack_id"))


@dataclass(frozen=True, slots=True)
class ReadinessChecklistDraft:
    ready: bool
    blocking_codes: tuple[str, ...]
    checklist: tuple[Mapping[str, object], ...]
    revision_id: str
    revision_hash: str

    def __post_init__(self) -> None:
        if type(self.ready) is not bool:
            raise TypeError("ready must be a boolean")
        object.__setattr__(self, "blocking_codes", _sorted_texts(self.blocking_codes, "blocking_code"))
        if len(self.checklist) > 64:
            raise ValueError("checklist is too large")
        object.__setattr__(self, "checklist", tuple(MappingProxyType(dict(item)) for item in self.checklist))
        object.__setattr__(self, "revision_id", _text(self.revision_id, "revision_id"))
        object.__setattr__(self, "revision_hash", _hash_for(self.revision_hash))


__all__ = [
    "GovernanceArtifactSet",
    "GovernanceDomainPolicy",
    "GovernanceInputs",
    "HumanAcknowledgementReference",
    "PublicationReadinessContext",
    "PublicationReadinessPolicy",
    "PublicationReadinessReport",
    "ReadinessChecklistDraft",
    "ReadinessChecklistProjection",
    "ReadinessIssueProjection",
    "ResolvedArtifactIdentity",
    "RevisionAssembler",
]
