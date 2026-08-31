"""Concrete, workspace-owned composition for the FMEA review service."""

# Composition validation exposes concise local ValueError messages.
# ruff: noqa: TRY003

from __future__ import annotations

import hmac
import os
import secrets
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from core_domain.fmea.domain_pack import DomainPackManifest
from core_domain.fmea.governance import FmeaRevision, canonical_hash
from core_domain.fmea.states import ActorType
from fmea_application import (
    ReviewRunExecutor,
    ReviewService,
    ReviewSuggestionGenerator,
    build_review_service,
)
from fmea_application.analysis_assistance_service import AnalysisAssistanceService
from fmea_application.assistance_contracts import AssistanceDecisionAction
from fmea_application.assistance_service import AssistanceDecisionService, AssistanceHandler
from fmea_application.governance_assistance_service import GovernanceAssistanceService
from fmea_application.ports import (
    AnalysisAssistanceGenerator,
    DomainPackRegistry,
    GovernanceAssistanceGenerator,
    GovernanceRepositoryProviders,
    GovernanceSourcePort,
    PropagationRuleRegistry,
    RiskSuggestionGenerator,
    ScoringRuleRegistry,
    SystemTopologyPort,
)
from fmea_application.propagation_service import (
    PropagationReviewService,
    PropagationSuggestionGenerator,
)
from fmea_application.review_errors import ReviewError
from fmea_application.revision_assembler import (
    GovernanceAcknowledgementRecord,
    GovernanceArtifactSet,
    GovernanceDomainPolicy,
    GovernanceInputs,
    GovernanceRetrievalProvenance,
    HumanAcknowledgementReference,
    PublicationReadinessPolicy,
    ResolvedAnalysisRecord,
    ResolvedArtifactIdentity,
    RevisionAssembler,
)
from fmea_application.risk_service import RiskAssessmentService, RiskContextProvider
from fmea_application.service_factory import (
    build_analysis_assistance_service,
    build_assistance_decision_service,
    build_risk_assessment_service,
)
from fmea_infrastructure.analysis_assistance_generator import EnvironmentAnalysisAssistanceGenerator
from fmea_infrastructure.assistance_repository_sqlite import SqliteAssistanceRepository
from fmea_infrastructure.domain_pack_registry import (
    FileDomainPackRegistry,
    FileScoringRuleRegistry,
    domain_pack_content_hash,
    load_domain_pack_manifest,
    load_scoring_rule_pack,
    scoring_rule_content_hash,
)
from fmea_infrastructure.governance_assistance_generator import OfflineGovernanceAssistanceGenerator
from fmea_infrastructure.propagation_generator import EnvironmentPropagationSuggestionGenerator
from fmea_infrastructure.propagation_repository_sqlite import SqlitePropagationRepository
from fmea_infrastructure.propagation_rule_registry import (
    FilePropagationRuleRegistry,
    load_propagation_rule_pack,
    propagation_rule_content_hash,
)
from fmea_infrastructure.repository_sqlite import SqliteFmeaRepository
from fmea_infrastructure.review_executor import ThreadPoolReviewRunExecutor
from fmea_infrastructure.review_generator import EnvironmentReviewSuggestionGenerator
from fmea_infrastructure.risk_generator import EnvironmentRiskSuggestionGenerator
from fmea_infrastructure.risk_repository_sqlite import SqliteRiskRepository
from fmea_infrastructure.topology_json import JsonTopologyRepository
from structured_output_application import TemplateCompiler
from structured_output_infrastructure import (
    Draft202012SchemaAdapter,
    FileTemplateRegistry,
    load_template_source,
    load_template_source_bytes,
)

if TYPE_CHECKING:
    from chroma_rag_poc.workspace_registry import WorkspaceConfig

_TEMPLATE_ID = "fmea-row-review"
_TEMPLATE_VERSION = "1.0.0"
_TEMPLATE_SOURCE = Path(__file__).resolve().parents[1] / "templates" / "examples" / "fmea-row-review.yaml"
_BUNDLED_DOMAIN_PACK_ROOT = Path(__file__).resolve().parents[1] / "domain_packs"
_PROPAGATION_REQUIRED_ENV = (
    "FMEA_PROPAGATION_TOPOLOGY_ROOT",
    "FMEA_PROPAGATION_TOPOLOGY_ID",
    "FMEA_PROPAGATION_TOPOLOGY_VERSION",
    "FMEA_PROPAGATION_TOPOLOGY_SHA256",
    "FMEA_PROPAGATION_DOMAIN_PACK_ID",
    "FMEA_PROPAGATION_DOMAIN_PACK_VERSION",
    "FMEA_PROPAGATION_RULE_PACK_ID",
    "FMEA_PROPAGATION_RULE_PACK_VERSION",
)
_PROPAGATION_OPTIONAL_ENV = (
    "FMEA_PROPAGATION_SOURCE_ROW_IDS",
    "FMEA_PROPAGATION_EVIDENCE_PACK_ID",
)
_ADOPTION_ACTIONS = {
    AssistanceDecisionAction.ADOPT,
    AssistanceDecisionAction.PARTIAL_ADOPT,
    AssistanceDecisionAction.EDIT_AND_ADOPT,
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def new_prefixed_uuid(prefix: str) -> str:
    return f"{prefix}-{uuid4()}"


@dataclass(frozen=True, slots=True)
class ReviewRuntime:
    service: ReviewService
    repository: SqliteFmeaRepository
    executor: ReviewRunExecutor
    template_registry_root: Path


@dataclass(frozen=True, slots=True)
class RiskRuntime:
    analysis_service: AnalysisAssistanceService
    decision_service: AssistanceDecisionService
    risk_service: RiskAssessmentService
    assistance_repository: SqliteAssistanceRepository
    risk_repository: SqliteRiskRepository
    template_registry_root: Path


@dataclass(frozen=True, slots=True)
class PropagationRuntime:
    service: PropagationReviewService
    repository: SqlitePropagationRepository
    assistance_repository: SqliteAssistanceRepository
    risk_repository: SqliteRiskRepository | None
    template_registry_root: Path
    start_defaults: Mapping[str, object] | None = None


@dataclass(frozen=True, slots=True)
class GovernanceRuntime:
    source: GovernanceSourcePort
    assembler: RevisionAssembler
    readiness_policy: PublicationReadinessPolicy
    assistance_service: GovernanceAssistanceService


class RegistryGovernanceArtifactProvider:
    """Resolve domain/template/scoring/propagation artifacts through registries."""

    def __init__(
        self,
        *,
        domain_pack: DomainPackManifest,
        domain_pack_registry: DomainPackRegistry,
        template_registry: FileTemplateRegistry,
        scoring_rule_registry: ScoringRuleRegistry,
        propagation_rule_registry: PropagationRuleRegistry,
    ) -> None:
        if not isinstance(domain_pack, DomainPackManifest):
            raise TypeError("domain_pack must be a server-owned DomainPackManifest")
        self._domain_pack = domain_pack
        self._domain_registry = domain_pack_registry
        self._template_registry = template_registry
        self._scoring_registry = scoring_rule_registry
        self._propagation_registry = propagation_rule_registry

    def get_artifacts(  # noqa: C901
        self, analysis_id: str, workspace_id: str, analysis: ResolvedAnalysisRecord
    ) -> GovernanceArtifactSet:
        if not isinstance(analysis, ResolvedAnalysisRecord):
            raise TypeError("artifact lookup requires a ResolvedAnalysisRecord")
        analysis.verify()
        if analysis.analysis_id != analysis_id or analysis.workspace_id != workspace_id:
            raise ValueError("artifact lookup analysis scope is invalid")
        if analysis.analysis_type not in self._domain_pack.analysis_types:
            raise ValueError("domain pack does not support the authoritative analysis type")

        def source_bytes(registry: object, artifact_type: str, artifact_id: str, version: str) -> bytes:
            getter = getattr(registry, "get_source_bytes", None)
            if not callable(getter):
                raise TypeError(f"{artifact_type} registry source bytes are unavailable")
            raw = getter(artifact_id, version)
            if not isinstance(raw, bytes) or not raw:
                raise ValueError(f"{artifact_type} registry source bytes are invalid")
            return raw

        def resolved_identity(
            artifact_type: str,
            artifact_id: str,
            version: str,
            registry: object,
            source_loader: Callable[[bytes], object],
            content_hash: Callable[[object], str],
        ) -> tuple[ResolvedArtifactIdentity, object]:
            raw = source_bytes(registry, artifact_type, artifact_id, version)
            try:
                resolved_model = source_loader(raw)
            except Exception as exc:
                raise ValueError(f"{artifact_type} registry source is invalid") from exc
            if (
                getattr(resolved_model, "__class__", None) is object
                or getattr(resolved_model, "version", None) != version
                or getattr(resolved_model, "pack_id", getattr(resolved_model, "rule_pack_id", None)) != artifact_id
            ) and artifact_type != "template":
                raise ValueError(f"{artifact_type} registry source identity is invalid")
            source_hash = sha256(raw).hexdigest()
            return (
                ResolvedArtifactIdentity(
                    artifact_type, artifact_id, version, content_hash(resolved_model), source_hash
                ),
                resolved_model,
            )

        template_compiler = TemplateCompiler(
            schema_validator=Draft202012SchemaAdapter(),
            source_loader=load_template_source,
        )

        domain_identity, registered_domain = resolved_identity(
            "domain_pack",
            self._domain_pack.pack_id,
            self._domain_pack.version,
            self._domain_registry,
            load_domain_pack_manifest,
            lambda model: domain_pack_content_hash(model),
        )
        if registered_domain != self._domain_pack or domain_identity.content_hash != registered_domain.content_hash:
            raise ValueError("domain pack registry identity does not match the server manifest")

        templates_list: list[ResolvedArtifactIdentity] = []
        for template_id, version in self._domain_pack.template_identities:
            template_identity, template = resolved_identity(
                "template",
                template_id,
                version,
                self._template_registry,
                lambda raw: template_compiler.compile(load_template_source_bytes(raw)),
                lambda model: sha256(model.canonical_json.encode("utf-8")).hexdigest(),
            )
            if template.metadata.template_id != template_id or template.metadata.version != version:
                raise ValueError("template registry identity does not match the domain pack")
            if template_identity.content_hash != template.template_hash:
                raise ValueError("template registry content hash does not match its source")
            templates_list.append(template_identity)
        templates = tuple(templates_list)
        scoring_list: list[ResolvedArtifactIdentity] = []
        for rule_id, version in self._domain_pack.scoring_rule_identities:
            scoring_identity, rule = resolved_identity(
                "scoring_rule",
                rule_id,
                version,
                self._scoring_registry,
                load_scoring_rule_pack,
                scoring_rule_content_hash,
            )
            if rule.rule_pack_id != rule_id or rule.version != version:
                raise ValueError("scoring rule registry identity does not match the domain pack")
            scoring_list.append(scoring_identity)
        scoring = tuple(scoring_list)
        propagation = None
        if self._domain_pack.propagation_rule_identities:
            rule_id, version = self._domain_pack.propagation_rule_identities[0]
            propagation_identity, rule = resolved_identity(
                "propagation_rule",
                rule_id,
                version,
                self._propagation_registry,
                load_propagation_rule_pack,
                propagation_rule_content_hash,
            )
            if rule.rule_pack_id != rule_id or rule.version != version:
                raise ValueError("propagation rule registry identity does not match the domain pack")
            propagation = propagation_identity
        return GovernanceArtifactSet(
            domain_pack=registered_domain,
            domain_pack_identity=domain_identity,
            template_identities=templates,
            scoring_rule_identities=scoring,
            propagation_rule_identity=propagation,
        )


class RepositoryGovernanceSource:
    """Compose existing query repositories behind the server-owned source port."""

    __slots__ = ("_providers",)

    def __init__(self, providers: GovernanceRepositoryProviders) -> None:
        if not isinstance(providers, GovernanceRepositoryProviders):
            raise TypeError("providers must be GovernanceRepositoryProviders")
        self._providers = providers

    def load_inputs(self, analysis_id: str, workspace_id: str) -> GovernanceInputs:
        raise TypeError("RepositoryGovernanceSource must be obtained from build_workspace_governance_runtime")

    def _load_unattested_inputs(self, analysis_id: str, workspace_id: str) -> GovernanceInputs:  # noqa: C901
        if (
            not isinstance(analysis_id, str)
            or not analysis_id.strip()
            or not isinstance(workspace_id, str)
            or not workspace_id.strip()
        ):
            raise ValueError("analysis_id and workspace_id must be non-empty strings")
        analysis_id = analysis_id.strip()
        workspace_id = workspace_id.strip()
        analysis = self._providers.analysis.get_analysis(analysis_id, workspace_id)
        if analysis is None or not isinstance(analysis, ResolvedAnalysisRecord):
            raise TypeError("analysis provider must return a ResolvedAnalysisRecord")
        analysis.verify()
        if analysis.analysis_id != analysis_id or analysis.workspace_id != workspace_id:
            raise ValueError("analysis was not found in the requested workspace")
        rows = tuple(self._providers.review.list_rows(analysis_id, workspace_id))
        risks = tuple(self._providers.risk.list_risk_records(analysis_id, workspace_id))
        graph = self._providers.propagation.get_current_graph(analysis_id, workspace_id)
        packs = tuple(self._providers.evidence.list_evidence_packs(analysis_id, workspace_id))
        artifacts = self._providers.artifacts.get_artifacts(analysis_id, workspace_id, analysis)
        raw_acknowledgements = tuple(
            self._providers.acknowledgements.list_human_acknowledgements(analysis_id, workspace_id)
        )

        def resolve_acknowledgement(record: object) -> HumanAcknowledgementReference:
            if not isinstance(record, GovernanceAcknowledgementRecord):
                raise TypeError("acknowledgement provider returned an invalid decision record")
            if record.status != "accepted":
                raise ValueError("acknowledgement decision is not accepted")
            if record.actor_type is not ActorType.HUMAN:
                raise ValueError("acknowledgement decision actor must be HUMAN")
            if record.decision_hash != record.canonical_hash:
                raise ValueError("acknowledgement decision hash does not match its record")
            reference = object.__new__(HumanAcknowledgementReference)
            for field_name, value in {
                "decision_id": record.decision_id,
                "decision_hash": record.decision_hash,
                "decision_record_version": record.decision_record_version,
                "decision_status": record.status,
                "workspace_id": record.workspace_id,
                "analysis_id": record.analysis_id,
                "issue_code": record.issue_code,
                "issue_source_type": record.issue_source_type,
                "issue_source_id": record.issue_source_id,
                "actor_id": record.actor_id,
                "actor_type": record.actor_type,
                "revision_id": record.revision_id,
                "revision_record_version": record.revision_record_version,
                "evidence_ids": record.evidence_ids,
            }.items():
                object.__setattr__(reference, field_name, value)
            return reference

        acknowledgements = tuple(resolve_acknowledgement(record) for record in raw_acknowledgements)
        for reference in acknowledgements:
            if reference.workspace_id != workspace_id or reference.analysis_id != analysis_id:
                raise ValueError("acknowledgement reference is outside the requested scope")
        provenance = self._providers.retrieval.get_provenance(analysis_id, workspace_id)
        if not isinstance(provenance, GovernanceRetrievalProvenance):
            raise TypeError("retrieval provider must return GovernanceRetrievalProvenance")
        if provenance.workspace_id != workspace_id or provenance.analysis_id != analysis_id:
            raise ValueError("retrieval provenance is outside the requested scope")
        parent_revision = (
            None
            if self._providers.parent is None
            else self._providers.parent.get_parent_revision(analysis_id, workspace_id)
        )
        if parent_revision is not None:
            if not isinstance(parent_revision, FmeaRevision):
                raise TypeError("parent provider must return an FmeaRevision")
            if parent_revision.workspace_id != workspace_id or parent_revision.analysis_id != analysis_id:
                raise ValueError("parent revision is outside the requested scope")
        inputs = GovernanceInputs(
            workspace_id=workspace_id,
            analysis_id=analysis_id,
            analysis=analysis,
            domain_pack=artifacts.domain_pack,
            domain_pack_identity=artifacts.domain_pack_identity,
            retrieval_provenance=provenance,
            rows=rows,
            risk_records=risks,
            propagation_graph_revision=graph,
            evidence_packs=packs,
            template_identities=artifacts.template_identities,
            scoring_rule_identities=artifacts.scoring_rule_identities,
            propagation_rule_identity=artifacts.propagation_rule_identity,
            acknowledgement_references=acknowledgements,
            active_run_ids=tuple(self._providers.runs.list_active_run_ids(analysis_id, workspace_id)),
            parent_revision=parent_revision,
            _source_attestation=object(),
        )
        RevisionAssembler._validate_source_scope(inputs)
        return inputs


ServerGovernanceSourceAdapter = RepositoryGovernanceSource


def _resolved_path(path: Path) -> Path:
    return Path(path).expanduser().resolve()


def _reject_parent_collisions(path: Path, *, expected: str) -> None:
    if path.exists():
        if expected == "file" and path.is_dir():
            raise ValueError("FMEA review database path must be a file")
        if expected == "directory" and not path.is_dir():
            raise ValueError("FMEA review template registry path must be a directory")
    for parent in path.parents:
        if parent.exists() and not parent.is_dir():
            raise ValueError("FMEA review path has a file/directory collision")


def _is_contained(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    else:
        return True


def _paths_overlap(first: Path, second: Path) -> bool:
    return _is_contained(first, second) or _is_contained(second, first)


def _workspace_review_paths(workspace: WorkspaceConfig) -> tuple[Path, Path]:
    default_root = _resolved_path(workspace.chroma_persist_dir).parent
    database_path = _resolved_path(workspace.fmea_db_path or default_root / "fmea" / "fmea.sqlite3")
    template_registry_root = _resolved_path(
        workspace.fmea_template_registry_path or default_root / "fmea" / "template_registry"
    )
    graph_db_path = None if workspace.graph_db_path is None else _resolved_path(workspace.graph_db_path)
    if graph_db_path is not None and database_path == graph_db_path:
        raise ValueError("FMEA review database must be separate from the graph database")
    if _paths_overlap(database_path, template_registry_root):
        raise ValueError("FMEA review database and template registry must be separate paths")
    _reject_parent_collisions(database_path, expected="file")
    _reject_parent_collisions(template_registry_root, expected="directory")
    return database_path, template_registry_root


def _register_review_template(template_registry_root: Path) -> None:
    schema = Draft202012SchemaAdapter()
    compiler = TemplateCompiler(schema_validator=schema, source_loader=load_template_source)
    compiled = compiler.compile_path(_TEMPLATE_SOURCE)
    if compiled.metadata.template_id != _TEMPLATE_ID or compiled.metadata.version != _TEMPLATE_VERSION:
        raise ValueError("built-in FMEA review template identity is invalid")
    registry = FileTemplateRegistry(template_registry_root)
    registry.register(compiled, _TEMPLATE_SOURCE.read_bytes(), _TEMPLATE_SOURCE.suffix.lower())


def build_workspace_governance_runtime(  # noqa: C901 - authority remains factory-local
    providers: GovernanceRepositoryProviders,
    *,
    domain_policy: GovernanceDomainPolicy | None = None,
    assistance_generator: GovernanceAssistanceGenerator | None = None,
    clock: Callable[[], str] = utc_now,
) -> GovernanceRuntime:
    """Compose Task 2 around typed repository query providers."""

    signing_secret = secrets.token_bytes(32)
    issuance_nonce = object()
    runtime_marker = object()

    class OpaqueGovernanceAttestation:
        __slots__ = ("_digest", "_signature")

        def __init__(self, nonce: object, digest: str, signature: str) -> None:
            if nonce is not issuance_nonce:
                raise TypeError("governance attestation can only be issued by its runtime")
            object.__setattr__(self, "_digest", digest)
            object.__setattr__(self, "_signature", signature)

        @property
        def digest(self) -> str:
            return self._digest

        @property
        def signature(self) -> str:
            return self._signature

        def __setattr__(self, _name: str, _value: object) -> None:
            raise AttributeError("governance attestations are immutable")

    def issue(inputs: GovernanceInputs) -> OpaqueGovernanceAttestation:
        digest = canonical_hash(inputs.attestation_body, max_array_items=10_000)
        signature = hmac.new(signing_secret, digest.encode("ascii"), sha256).hexdigest()
        return OpaqueGovernanceAttestation(issuance_nonce, digest, signature)

    def verify(inputs: object) -> None:
        if not isinstance(inputs, GovernanceInputs):
            raise TypeError("trusted governance authority requires GovernanceInputs")
        proof = getattr(inputs, "_source_attestation", None)
        if not isinstance(proof, OpaqueGovernanceAttestation):
            raise ValueError(  # noqa: TRY004 - object type is valid; authority is not
                "governance inputs do not have a runtime attestation"
            )
        digest = canonical_hash(inputs.attestation_body, max_array_items=10_000)
        expected_signature = hmac.new(signing_secret, digest.encode("ascii"), sha256).hexdigest()
        if not hmac.compare_digest(proof.digest, digest) or not hmac.compare_digest(
            proof.signature, expected_signature
        ):
            raise ValueError("governance inputs source attestation is invalid")

    class RuntimeGovernanceSource(RepositoryGovernanceSource):
        __slots__ = ()

        def load_inputs(self, analysis_id: str, workspace_id: str) -> GovernanceInputs:
            inputs = self._load_unattested_inputs(analysis_id, workspace_id)
            return replace(inputs, _source_attestation=issue(inputs))

    class RuntimeRevisionAssembler(RevisionAssembler):
        __slots__ = ()

        def __init__(self) -> None:
            super().__init__()
            object.__setattr__(self, "_clock", clock)
            object.__setattr__(self, "_runtime_marker", runtime_marker)

        def assemble(self, request, inputs):  # type: ignore[no-untyped-def]
            verify(inputs)
            return super().assemble(request, inputs)

    class RuntimePublicationReadinessPolicy(PublicationReadinessPolicy):
        __slots__ = ()

        def __init__(self) -> None:
            super().__init__(domain_policy)
            object.__setattr__(self, "_runtime_marker", runtime_marker)

        def evaluate(self, revision, context):  # type: ignore[no-untyped-def]
            if context.governance_inputs is None:
                return self._unverified_report(revision)
            try:
                verify(context.governance_inputs)
            except (TypeError, ValueError):
                return self._unverified_report(revision)
            return self._evaluate_authoritative(revision, context)

    resolved_source = RuntimeGovernanceSource(providers)
    generator = assistance_generator or OfflineGovernanceAssistanceGenerator()
    return GovernanceRuntime(
        source=resolved_source,
        assembler=RuntimeRevisionAssembler(),
        readiness_policy=RuntimePublicationReadinessPolicy(),
        assistance_service=GovernanceAssistanceService(generator=generator, clock=clock),
    )


def build_governance_runtime(
    providers: GovernanceRepositoryProviders,
    *,
    domain_policy: GovernanceDomainPolicy | None = None,
    assistance_generator: GovernanceAssistanceGenerator | None = None,
    clock: Callable[[], str] = utc_now,
) -> GovernanceRuntime:
    """Compatibility alias for callers that do not use workspace in the name."""

    return build_workspace_governance_runtime(
        providers,
        domain_policy=domain_policy,
        assistance_generator=assistance_generator,
        clock=clock,
    )


def build_workspace_review_runtime(
    workspace: WorkspaceConfig,
    *,
    generator: ReviewSuggestionGenerator | None = None,
    executor: ReviewRunExecutor | None = None,
    clock: Callable[[], str] = utc_now,
    id_factory: Callable[[str], str] = new_prefixed_uuid,
) -> ReviewRuntime:
    database_path, template_registry_root = _workspace_review_paths(workspace)
    repository = SqliteFmeaRepository(database_path)
    repository.initialize()
    _register_review_template(template_registry_root)

    review_generator = (
        generator
        if generator is not None
        else EnvironmentReviewSuggestionGenerator(registry_root=template_registry_root)
    )
    review_executor = executor if executor is not None else ThreadPoolReviewRunExecutor()
    service = build_review_service(
        repository,
        review_generator,
        review_executor,
        clock=clock,
        id_factory=id_factory,
    )
    return ReviewRuntime(
        service=service,
        repository=repository,
        executor=review_executor,
        template_registry_root=template_registry_root,
    )


def build_workspace_risk_runtime(
    workspace: WorkspaceConfig,
    *,
    domain_pack_registry: DomainPackRegistry,
    scoring_rule_registry: ScoringRuleRegistry,
    context_provider: RiskContextProvider,
    assistance_handlers: Mapping[AssistanceDecisionAction, AssistanceHandler],
    analysis_generator: AnalysisAssistanceGenerator | None = None,
    risk_generator: RiskSuggestionGenerator | None = None,
    clock: Callable[[], str] = utc_now,
    id_factory: Callable[[str], str] = new_prefixed_uuid,
) -> RiskRuntime:
    database_path, template_registry_root = _workspace_review_paths(workspace)
    assistance_repository = SqliteAssistanceRepository(database_path)
    risk_repository = SqliteRiskRepository(database_path)
    assistance_repository.initialize()
    risk_repository.initialize()

    resolved_analysis_generator = analysis_generator or EnvironmentAnalysisAssistanceGenerator(
        evidence_loader=risk_repository.get_evidence_pack,
        registry_root=template_registry_root / "assistance",
        clock=clock,
    )
    resolved_risk_generator = risk_generator or EnvironmentRiskSuggestionGenerator(
        registry_root=template_registry_root / "assistance",
        clock=clock,
    )
    analysis_service = build_analysis_assistance_service(
        assistance_repository,
        resolved_analysis_generator,
        clock=clock,
        id_factory=id_factory,
    )
    decision_service = build_assistance_decision_service(
        assistance_repository,
        handlers=dict(assistance_handlers),
        clock=clock,
        id_factory=id_factory,
    )
    risk_service = build_risk_assessment_service(
        risk_repository,
        assistance_repository=assistance_repository,
        domain_pack_registry=domain_pack_registry,
        scoring_rule_registry=scoring_rule_registry,
        generator=resolved_risk_generator,
        context_provider=context_provider,
        clock=clock,
    )
    return RiskRuntime(
        analysis_service=analysis_service,
        decision_service=decision_service,
        risk_service=risk_service,
        assistance_repository=assistance_repository,
        risk_repository=risk_repository,
        template_registry_root=template_registry_root,
    )


def build_workspace_propagation_runtime(
    workspace: WorkspaceConfig,
    *,
    topology_port: SystemTopologyPort,
    domain_pack_registry: DomainPackRegistry,
    propagation_rule_registry: PropagationRuleRegistry,
    generator: PropagationSuggestionGenerator | None = None,
    risk_repository: SqliteRiskRepository | None = None,
    start_defaults: Mapping[str, object] | None = None,
    clock: Callable[[], str] = utc_now,
) -> PropagationRuntime:
    """Compose the workspace-scoped proposal and human-review propagation path."""

    database_path, template_registry_root = _workspace_review_paths(workspace)
    repository = SqlitePropagationRepository(database_path)
    assistance_repository = SqliteAssistanceRepository(database_path)
    repository.initialize()
    assistance_repository.initialize()
    if risk_repository is not None:
        risk_repository.initialize()
    resolved_generator = generator or EnvironmentPropagationSuggestionGenerator(clock=clock)
    service = PropagationReviewService(
        repository,
        assistance_repository=assistance_repository,
        topology_port=topology_port,
        domain_pack_registry=domain_pack_registry,
        propagation_rule_registry=propagation_rule_registry,
        generator=resolved_generator,
        risk_repository=risk_repository,
        clock=clock,
    )
    return PropagationRuntime(
        service=service,
        repository=repository,
        assistance_repository=assistance_repository,
        risk_repository=risk_repository,
        template_registry_root=template_registry_root,
        start_defaults=start_defaults,
    )


def propagation_server_environment_present(environ: Mapping[str, str] | None = None) -> bool:
    """Return whether an operator supplied any propagation server configuration."""

    source = os.environ if environ is None else environ
    return any(source.get(key) for key in (*_PROPAGATION_REQUIRED_ENV, *_PROPAGATION_OPTIONAL_ENV))


def _propagation_server_defaults(environ: Mapping[str, str]) -> tuple[Path, str, Mapping[str, object]]:
    configured: dict[str, str] = {}
    for key in _PROPAGATION_REQUIRED_ENV:
        value = environ.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ReviewError(
                "FMEA_WORKSPACE_CONFIGURATION_INVALID",
                "FMEA propagation server configuration is incomplete",
            )
        configured[key] = value.strip()
    source_rows = tuple(
        item.strip() for item in environ.get("FMEA_PROPAGATION_SOURCE_ROW_IDS", "").split(",") if item.strip()
    )
    if len(source_rows) != len(set(source_rows)):
        raise ReviewError(
            "FMEA_WORKSPACE_CONFIGURATION_INVALID",
            "FMEA propagation source-row configuration is invalid",
        )
    defaults: Mapping[str, object] = {
        "source_row_ids": source_rows,
        "evidence_pack_id": environ.get("FMEA_PROPAGATION_EVIDENCE_PACK_ID", "").strip(),
        "topology_id": configured["FMEA_PROPAGATION_TOPOLOGY_ID"],
        "topology_version": configured["FMEA_PROPAGATION_TOPOLOGY_VERSION"],
        "domain_pack_id": configured["FMEA_PROPAGATION_DOMAIN_PACK_ID"],
        "domain_pack_version": configured["FMEA_PROPAGATION_DOMAIN_PACK_VERSION"],
        "rule_pack_id": configured["FMEA_PROPAGATION_RULE_PACK_ID"],
        "rule_pack_version": configured["FMEA_PROPAGATION_RULE_PACK_VERSION"],
    }
    return (
        Path(configured["FMEA_PROPAGATION_TOPOLOGY_ROOT"]),
        configured["FMEA_PROPAGATION_TOPOLOGY_SHA256"],
        defaults,
    )


def build_default_workspace_propagation_runtime(
    workspace: WorkspaceConfig,
    *,
    risk_repository: SqliteRiskRepository | None = None,
    environ: Mapping[str, str] | None = None,
) -> PropagationRuntime:
    """Compose propagation from server-owned environment pins for one workspace."""

    source = os.environ if environ is None else environ
    topology_root, topology_sha256, defaults = _propagation_server_defaults(source)
    _, template_registry_root = _workspace_review_paths(workspace)
    domain_registry = FileDomainPackRegistry(template_registry_root / "domain-packs")
    for manifest_path in sorted(_BUNDLED_DOMAIN_PACK_ROOT.glob("*/manifest.yaml")):
        manifest_source = manifest_path.read_bytes()
        domain_registry.register(load_domain_pack_manifest(manifest_source), manifest_source)
    rule_registry = FilePropagationRuleRegistry(template_registry_root / "propagation-rules")
    for rule_path in sorted(_BUNDLED_DOMAIN_PACK_ROOT.glob("*/propagation/*.yaml")):
        rule_source = rule_path.read_bytes()
        rule_registry.register(load_propagation_rule_pack(rule_source), rule_source)
    topology_port = JsonTopologyRepository(
        topology_root,
        source_hashes={
            (str(defaults["topology_id"]), str(defaults["topology_version"])): topology_sha256,
        },
    )
    try:
        snapshot = topology_port.load_snapshot(
            str(defaults["topology_id"]),
            str(defaults["topology_version"]),
        )
        domain_pack = domain_registry.get(
            str(defaults["domain_pack_id"]),
            str(defaults["domain_pack_version"]),
        )
        rule_pack = rule_registry.get(
            str(defaults["rule_pack_id"]),
            str(defaults["rule_pack_version"]),
        )
    except Exception as exc:
        raise ReviewError(
            "FMEA_WORKSPACE_CONFIGURATION_INVALID",
            "FMEA propagation server configuration is invalid",
        ) from exc
    if snapshot.workspace_id != workspace.workspace_id or domain_pack is None or rule_pack is None:
        raise ReviewError(
            "FMEA_WORKSPACE_CONFIGURATION_INVALID",
            "FMEA propagation resources are not bound to the workspace",
        )
    resolved_risk_repository = risk_repository
    if resolved_risk_repository is None:
        database_path, _ = _workspace_review_paths(workspace)
        resolved_risk_repository = SqliteRiskRepository(database_path)
    return build_workspace_propagation_runtime(
        workspace,
        topology_port=topology_port,
        domain_pack_registry=domain_registry,
        propagation_rule_registry=rule_registry,
        risk_repository=resolved_risk_repository,
        start_defaults=defaults,
    )


def _default_assistance_handler(request: object) -> None:
    command = getattr(request, "command", None)
    if getattr(command, "action", None) in _ADOPTION_ACTIONS:
        raise ReviewError(
            "FMEA_REVIEW_ACTION_INVALID",
            "assistance adoption requires a configured domain write handler",
        )
    return None


def _register_bundled_domain_packs(
    domain_registry: FileDomainPackRegistry,
    scoring_registry: FileScoringRuleRegistry,
) -> None:
    for manifest_path in sorted(_BUNDLED_DOMAIN_PACK_ROOT.glob("*/manifest.yaml")):
        source = manifest_path.read_bytes()
        domain_registry.register(load_domain_pack_manifest(source), source)
    for scoring_path in sorted(_BUNDLED_DOMAIN_PACK_ROOT.glob("*/scoring/*.yaml")):
        source = scoring_path.read_bytes()
        scoring_registry.register(load_scoring_rule_pack(source), source)


def build_default_workspace_risk_runtime(
    workspace: WorkspaceConfig,
    *,
    context_provider: RiskContextProvider,
) -> RiskRuntime:
    """Compose the provider-neutral risk runtime and register bundled immutable packs."""

    _, template_registry_root = _workspace_review_paths(workspace)
    domain_registry = FileDomainPackRegistry(template_registry_root / "domain-packs")
    scoring_registry = FileScoringRuleRegistry(template_registry_root / "scoring-rules")
    _register_bundled_domain_packs(domain_registry, scoring_registry)
    handlers = dict.fromkeys(AssistanceDecisionAction, _default_assistance_handler)
    return build_workspace_risk_runtime(
        workspace,
        domain_pack_registry=domain_registry,
        scoring_rule_registry=scoring_registry,
        context_provider=context_provider,
        assistance_handlers=handlers,
    )


__all__ = [
    "GovernanceRuntime",
    "PropagationRuntime",
    "RegistryGovernanceArtifactProvider",
    "RepositoryGovernanceSource",
    "ReviewRuntime",
    "RiskRuntime",
    "ServerGovernanceSourceAdapter",
    "build_default_workspace_propagation_runtime",
    "build_default_workspace_risk_runtime",
    "build_governance_runtime",
    "build_workspace_governance_runtime",
    "build_workspace_propagation_runtime",
    "build_workspace_review_runtime",
    "build_workspace_risk_runtime",
    "new_prefixed_uuid",
    "propagation_server_environment_present",
    "utc_now",
]
