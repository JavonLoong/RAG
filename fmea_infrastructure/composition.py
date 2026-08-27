"""Concrete, workspace-owned composition for the FMEA review service."""

# Composition validation exposes concise local ValueError messages.
# ruff: noqa: TRY003

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from fmea_application import (
    ReviewRunExecutor,
    ReviewService,
    ReviewSuggestionGenerator,
    build_review_service,
)
from fmea_application.analysis_assistance_service import AnalysisAssistanceService
from fmea_application.assistance_contracts import AssistanceDecisionAction
from fmea_application.assistance_service import AssistanceDecisionService, AssistanceHandler
from fmea_application.ports import (
    AnalysisAssistanceGenerator,
    DomainPackRegistry,
    RiskSuggestionGenerator,
    ScoringRuleRegistry,
)
from fmea_application.risk_service import RiskAssessmentService, RiskContextProvider
from fmea_application.service_factory import (
    build_analysis_assistance_service,
    build_assistance_decision_service,
    build_risk_assessment_service,
)
from fmea_infrastructure.analysis_assistance_generator import EnvironmentAnalysisAssistanceGenerator
from fmea_infrastructure.assistance_repository_sqlite import SqliteAssistanceRepository
from fmea_infrastructure.repository_sqlite import SqliteFmeaRepository
from fmea_infrastructure.review_executor import ThreadPoolReviewRunExecutor
from fmea_infrastructure.review_generator import EnvironmentReviewSuggestionGenerator
from fmea_infrastructure.risk_generator import EnvironmentRiskSuggestionGenerator
from fmea_infrastructure.risk_repository_sqlite import SqliteRiskRepository
from structured_output_application import TemplateCompiler
from structured_output_infrastructure import Draft202012SchemaAdapter, FileTemplateRegistry, load_template_source

if TYPE_CHECKING:
    from chroma_rag_poc.workspace_registry import WorkspaceConfig

_TEMPLATE_ID = "fmea-row-review"
_TEMPLATE_VERSION = "1.0.0"
_TEMPLATE_SOURCE = Path(__file__).resolve().parents[1] / "templates" / "examples" / "fmea-row-review.yaml"


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

    review_generator = generator if generator is not None else EnvironmentReviewSuggestionGenerator(
        registry_root=template_registry_root
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
    )
    resolved_risk_generator = risk_generator or EnvironmentRiskSuggestionGenerator(
        registry_root=template_registry_root / "assistance"
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


__all__ = [
    "ReviewRuntime",
    "RiskRuntime",
    "build_workspace_review_runtime",
    "build_workspace_risk_runtime",
    "new_prefixed_uuid",
    "utc_now",
]
