from __future__ import annotations

from rag_orchestrator.query_understanding import (
    QueryAbstractionLevel,
    QueryIntent,
    QueryRouteName,
    SemanticQueryAnalyzer,
    build_query_understanding_prompt,
)
from rag_orchestrator.router import AdaptiveQueryRouter, RoutingDecision


class FakeTaskSpecLLM:
    def generate(self, prompt: str) -> str:
        return '{"strategy": "COMPREHENSIVE_ANALYSIS", "reason": "needs full sweep"}'


class BrokenRouterLLM:
    def generate(self, prompt: str) -> str:
        raise RuntimeError("llm unavailable")


class MisleadingRouterLLM:
    def generate(self, prompt: str) -> str:
        return '{"strategy": "LOCAL_RAG", "reason": "incorrectly treat as local"}'


def test_analyzer_builds_task_spec_for_comparison_with_metadata_and_evidence() -> None:
    analyzer = SemanticQueryAnalyzer()

    spec = analyzer.analyze("对比 2024 年「对象A」和「对象B」的主要风险，必须引用原文证据")

    assert spec.route == QueryRouteName.COMPARE_SYNTHESIS
    assert spec.intent == QueryIntent.COMPARE
    assert spec.abstraction_level == QueryAbstractionLevel.MIXED
    assert "对象A" in spec.objects
    assert "对象B" in spec.objects
    assert "风险" in spec.high_level_keywords
    assert {"field": "year", "operator": "=", "value": "2024"} in spec.metadata_filters
    assert spec.evidence_requirements.must_cite is True
    assert spec.evidence_requirements.no_evidence_policy == "return_insufficient_evidence"
    assert spec.output_contract.format == "comparison_table"
    assert spec.rewritten_question.startswith("对比")


def test_analyzer_routes_global_comprehensive_questions_to_planner_branch() -> None:
    analyzer = SemanticQueryAnalyzer()

    spec = analyzer.analyze("全量分析所有资料里「系统X」维护问题的类别、原因和处理措施")

    assert spec.route == QueryRouteName.COMPREHENSIVE_ANALYSIS
    assert spec.intent == QueryIntent.COMPREHENSIVE
    assert spec.requires_planning is True
    assert "系统X" in spec.objects
    assert "维护问题" in spec.high_level_keywords
    assert len(spec.sub_questions) >= 3
    assert any("类别" in question for question in spec.sub_questions)
    assert spec.evidence_requirements.coverage_report is True


def test_analyzer_routes_corpus_wide_partition_questions_to_comprehensive_planner() -> None:
    analyzer = SemanticQueryAnalyzer()

    spec = analyzer.analyze("Which documents mention bearing overheating, and what evidence supports each document?")

    assert spec.route == QueryRouteName.COMPREHENSIVE_ANALYSIS
    assert spec.intent == QueryIntent.COMPREHENSIVE
    assert spec.requires_planning is True
    assert spec.coverage_scope.value in {"partitioned", "full_corpus"}
    assert "text_full_scan" in spec.preferred_capabilities
    assert "bearing" in spec.low_level_keywords
    assert "overheating" in spec.low_level_keywords


def test_analyzer_marks_class_level_problem_as_abstract() -> None:
    analyzer = SemanticQueryAnalyzer()

    spec = analyzer.analyze("哪些故障类型会导致「状态Y」异常？")

    assert spec.abstraction_level == QueryAbstractionLevel.MIXED
    assert spec.route in {QueryRouteName.MULTI_HOP, QueryRouteName.COMPREHENSIVE_ANALYSIS}
    assert "故障" in spec.high_level_keywords
    assert "semantic_query_expansion" in spec.preferred_capabilities
    assert "故障" in spec.evidence_terms


def test_analyzer_expands_general_concepts_to_evidence_terms() -> None:
    analyzer = SemanticQueryAnalyzer()

    spec = analyzer.analyze("总结系统运行风险和维护措施")

    assert "风险" in spec.high_level_keywords
    assert "维护" in spec.high_level_keywords
    assert "故障" in spec.evidence_terms
    assert "检修" in spec.evidence_terms
    assert "semantic_query_expansion" in spec.preferred_capabilities


def test_analyzer_routes_entity_set_event_questions_to_partition_scan() -> None:
    analyzer = SemanticQueryAnalyzer()

    spec = analyzer.analyze("我和哪些人发生过争执？")

    assert spec.route == QueryRouteName.COMPREHENSIVE_ANALYSIS
    assert spec.coverage_scope.value == "partitioned"
    assert "冲突" in spec.high_level_keywords
    assert "争执" in spec.evidence_terms
    assert "partition_scan" in spec.preferred_capabilities


def test_analyzer_routes_entity_relation_questions_to_graph_path() -> None:
    analyzer = SemanticQueryAnalyzer()

    spec = analyzer.analyze("「流程A」和「流程B」之间有什么关系？给出原文证据")

    assert spec.route == QueryRouteName.GRAPH_PATH
    assert spec.intent == QueryIntent.RELATIONSHIP
    assert "流程A" in spec.objects
    assert "流程B" in spec.objects
    assert "关系" in spec.high_level_keywords
    assert "流程A" in spec.low_level_keywords
    assert spec.evidence_requirements.must_cite is True


def test_analyzer_routes_multi_hop_questions_and_generates_sub_questions() -> None:
    analyzer = SemanticQueryAnalyzer()

    spec = analyzer.analyze("为什么「指标A异常」会导致「结果B下降」？一步一步找证据")

    assert spec.route == QueryRouteName.MULTI_HOP
    assert spec.intent == QueryIntent.CAUSAL
    assert "指标A异常" in spec.objects
    assert "结果B下降" in spec.objects
    assert len(spec.sub_questions) >= 2
    assert spec.evidence_requirements.must_cite is True


def test_prompt_contract_requires_strict_task_spec_json() -> None:
    prompt = build_query_understanding_prompt("总结系统维护风险")

    assert "TaskSpec" in prompt
    assert "abstraction_level" in prompt
    assert "high_level_keywords" in prompt
    assert "low_level_keywords" in prompt
    assert "evidence_terms" in prompt
    assert "metadata_filters" in prompt
    assert "evidence_requirements" in prompt
    assert "COMPREHENSIVE_ANALYSIS" in prompt


def test_package_exports_semantic_query_analyzer() -> None:
    from rag_orchestrator import SemanticQueryAnalyzer as ExportedAnalyzer

    assert ExportedAnalyzer is SemanticQueryAnalyzer


def test_adaptive_router_maps_new_task_routes_to_existing_api_strategies() -> None:
    route = AdaptiveQueryRouter(FakeTaskSpecLLM()).route_query("全量分析所有资料")

    assert route.strategy == RoutingDecision.GLOBAL_SEARCH
    assert route.task_route == QueryRouteName.COMPREHENSIVE_ANALYSIS
    assert "semantic analyzer preflight" in route.reason


def test_adaptive_router_falls_back_to_local_semantic_analyzer_when_llm_fails() -> None:
    route = AdaptiveQueryRouter(BrokenRouterLLM()).route_query("对比对象A和对象B风险")

    assert route.strategy == RoutingDecision.GLOBAL_SEARCH
    assert route.task_route == QueryRouteName.COMPARE_SYNTHESIS
    assert "semantic analyzer fallback" in route.reason


def test_adaptive_router_semantic_preflight_overrides_llm_for_corpus_wide_questions() -> None:
    route = AdaptiveQueryRouter(MisleadingRouterLLM()).route_query(
        "Which documents mention bearing overheating, and what evidence supports each document?"
    )

    assert route.strategy == RoutingDecision.GLOBAL_SEARCH
    assert route.task_route == QueryRouteName.COMPREHENSIVE_ANALYSIS
    assert "semantic analyzer preflight" in route.reason


def test_router_has_no_dataset_specific_fast_path() -> None:
    route = AdaptiveQueryRouter(MisleadingRouterLLM()).route_query("全量分析所有资料中的风险类别")

    assert route.strategy == RoutingDecision.GLOBAL_SEARCH
    assert route.task_route == QueryRouteName.COMPREHENSIVE_ANALYSIS
