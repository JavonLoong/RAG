"""Pure application composition for the review service."""

from __future__ import annotations

from collections.abc import Callable

from .analysis_assistance_service import AnalysisAssistanceService
from .assistance_contracts import AssistanceDecisionAction
from .assistance_service import AssistanceDecisionService, AssistanceHandler
from .ports import (
    AnalysisAssistanceGenerator,
    AssistanceRepository,
    DomainPackRegistry,
    PropagationRuleRegistry,
    ReviewRepository,
    ReviewRunExecutor,
    ReviewSuggestionGenerator,
    RiskRepository,
    RiskSuggestionGenerator,
    ScoringRuleRegistry,
    SystemTopologyPort,
)
from .propagation_service import PropagationAnalysisService, PropagationRepository, PropagationSuggestionGenerator
from .review_service import ReviewService
from .risk_service import RiskAssessmentService, RiskContextProvider


def build_review_service(
    repository: ReviewRepository,
    generator: ReviewSuggestionGenerator,
    executor: ReviewRunExecutor,
    *,
    clock: Callable[[], str],
    id_factory: Callable[[str], str],
) -> ReviewService:
    return ReviewService(
        repository,
        generator,
        executor,
        clock=clock,
        id_factory=id_factory,
    )


def build_analysis_assistance_service(
    repository: AssistanceRepository,
    generator: AnalysisAssistanceGenerator,
    *,
    clock: Callable[[], str],
    id_factory: Callable[[str], str],
) -> AnalysisAssistanceService:
    return AnalysisAssistanceService(generator, repository, clock=clock, id_factory=id_factory)


def build_assistance_decision_service(
    repository: AssistanceRepository,
    *,
    handlers: dict[AssistanceDecisionAction, AssistanceHandler],
    clock: Callable[[], str],
    id_factory: Callable[[str], str],
) -> AssistanceDecisionService:
    return AssistanceDecisionService(repository, handlers=handlers, clock=clock, id_factory=id_factory)


def build_risk_assessment_service(
    repository: RiskRepository,
    *,
    assistance_repository: AssistanceRepository,
    domain_pack_registry: DomainPackRegistry,
    scoring_rule_registry: ScoringRuleRegistry,
    generator: RiskSuggestionGenerator,
    context_provider: RiskContextProvider,
    clock: Callable[[], str],
) -> RiskAssessmentService:
    return RiskAssessmentService(
        repository,
        assistance_repository=assistance_repository,
        domain_pack_registry=domain_pack_registry,
        scoring_rule_registry=scoring_rule_registry,
        generator=generator,
        context_provider=context_provider,
        clock=clock,
    )


def build_propagation_analysis_service(
    repository: PropagationRepository,
    *,
    assistance_repository: AssistanceRepository,
    topology_port: SystemTopologyPort,
    domain_pack_registry: DomainPackRegistry,
    propagation_rule_registry: PropagationRuleRegistry,
    generator: PropagationSuggestionGenerator,
    risk_repository: RiskRepository | None = None,
    clock: Callable[[], str],
) -> PropagationAnalysisService:
    return PropagationAnalysisService(
        repository,
        assistance_repository=assistance_repository,
        topology_port=topology_port,
        domain_pack_registry=domain_pack_registry,
        propagation_rule_registry=propagation_rule_registry,
        generator=generator,
        risk_repository=risk_repository,
        clock=clock,
    )


__all__ = [
    "build_analysis_assistance_service",
    "build_assistance_decision_service",
    "build_propagation_analysis_service",
    "build_review_service",
    "build_risk_assessment_service",
]
