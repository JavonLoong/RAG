from __future__ import annotations

from types import SimpleNamespace

from fmea_application.analysis_assistance_service import AnalysisAssistanceService
from fmea_application.assistance_contracts import AssistanceDecisionAction
from fmea_application.assistance_service import AssistanceDecisionService
from fmea_application.risk_service import RiskAssessmentService
from fmea_infrastructure.composition import RiskRuntime, build_workspace_risk_runtime


class _NeverCalled:
    def __getattr__(self, name):
        raise AssertionError(name)


def test_task_4_runtime_wires_provider_neutral_services_to_one_workspace_database(tmp_path) -> None:
    workspace = SimpleNamespace(
        chroma_persist_dir=tmp_path / "chroma",
        fmea_db_path=tmp_path / "fmea" / "fmea.sqlite3",
        fmea_template_registry_path=tmp_path / "fmea" / "templates",
        graph_db_path=tmp_path / "graph.sqlite3",
    )
    handlers = {action: (lambda _request: None) for action in AssistanceDecisionAction}

    runtime = build_workspace_risk_runtime(
        workspace,
        domain_pack_registry=_NeverCalled(),
        scoring_rule_registry=_NeverCalled(),
        context_provider=_NeverCalled(),
        analysis_generator=_NeverCalled(),
        risk_generator=_NeverCalled(),
        assistance_handlers=handlers,
    )

    assert isinstance(runtime, RiskRuntime)
    assert isinstance(runtime.analysis_service, AnalysisAssistanceService)
    assert isinstance(runtime.decision_service, AssistanceDecisionService)
    assert isinstance(runtime.risk_service, RiskAssessmentService)
    assert runtime.risk_repository.database_path == runtime.assistance_repository.database_path
