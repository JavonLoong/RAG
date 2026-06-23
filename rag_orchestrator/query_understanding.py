from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class QueryIntent(StrEnum):
    FACT = "fact"
    RELATIONSHIP = "relationship"
    GLOBAL_SUMMARY = "global_summary"
    CAUSAL = "causal"
    COMPARE = "compare"
    COMPREHENSIVE = "comprehensive"


class QueryRouteName(StrEnum):
    LOCAL_RAG = "LOCAL_RAG"
    GRAPH_PATH = "GRAPH_PATH"
    GLOBAL_SUMMARY = "GLOBAL_SUMMARY"
    MULTI_HOP = "MULTI_HOP"
    COMPARE_SYNTHESIS = "COMPARE_SYNTHESIS"
    COMPREHENSIVE_ANALYSIS = "COMPREHENSIVE_ANALYSIS"


class QueryCoverageScope(StrEnum):
    LOCAL = "local"
    PARTITIONED = "partitioned"
    FULL_CORPUS = "full_corpus"


class QueryAbstractionLevel(StrEnum):
    CONCRETE = "concrete"
    ABSTRACT = "abstract"
    MIXED = "mixed"


@dataclass(slots=True)
class EvidenceRequirements:
    must_cite: bool = True
    require_source_span: bool = True
    no_evidence_policy: str = "return_insufficient_evidence"
    coverage_report: bool = False
    min_sources: int = 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class OutputContract:
    format: str = "grounded_answer"
    include_citations: bool = True
    include_uncertainty: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class TaskSpec:
    original_question: str
    rewritten_question: str
    intent: QueryIntent
    route: QueryRouteName
    objects: list[str] = field(default_factory=list)
    fuzzy_terms: list[str] = field(default_factory=list)
    high_level_keywords: list[str] = field(default_factory=list)
    low_level_keywords: list[str] = field(default_factory=list)
    evidence_terms: list[str] = field(default_factory=list)
    metadata_filters: list[dict[str, str]] = field(default_factory=list)
    coverage_scope: QueryCoverageScope = QueryCoverageScope.LOCAL
    abstraction_level: QueryAbstractionLevel = QueryAbstractionLevel.CONCRETE
    preferred_capabilities: list[str] = field(default_factory=list)
    evidence_requirements: EvidenceRequirements = field(default_factory=EvidenceRequirements)
    output_contract: OutputContract = field(default_factory=OutputContract)
    sub_questions: list[str] = field(default_factory=list)
    requires_planning: bool = False
    route_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["intent"] = self.intent.value
        data["route"] = self.route.value
        data["coverage_scope"] = self.coverage_scope.value
        data["abstraction_level"] = self.abstraction_level.value
        return data

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


TASK_SPEC_PROMPT = """You are the query understanding module for PowerRAG.
Analyze the user question before retrieval and return ONLY strict JSON for a TaskSpec.

Allowed routes:
- LOCAL_RAG: local factual question over a short passage or specific fact.
- GRAPH_PATH: entity relationship or path question.
- GLOBAL_SUMMARY: high-level summary over communities or the corpus.
- MULTI_HOP: causal, why/how, or step-by-step reasoning requiring multiple evidence hops.
- COMPARE_SYNTHESIS: comparison across entities, files, periods, versions, or options.
- COMPREHENSIVE_ANALYSIS: full-corpus analysis requiring planning, sweep, map-reduce, and coverage report.

abstraction_level:
- concrete: asks for a specific fact, object, page, date, ID, or named item.
- abstract: asks about a class, category, trend, cause, risk, quality, relationship type, or fuzzy concept.
- mixed: combines named objects or filters with abstract criteria.

Required JSON fields:
original_question, rewritten_question, intent, route, objects, fuzzy_terms,
high_level_keywords, low_level_keywords, evidence_terms, metadata_filters,
coverage_scope, abstraction_level, preferred_capabilities,
evidence_requirements, output_contract, sub_questions, requires_planning, route_reason.

Evidence rules:
- evidence_requirements.must_cite must be true unless the user explicitly asks for brainstorming.
- evidence_requirements.no_evidence_policy must be "return_insufficient_evidence".
- metadata_filters must use objects like {{"field": "year", "operator": "=", "value": "2024"}}.

Question:
{question}
"""


def build_query_understanding_prompt(question: str) -> str:
    return TASK_SPEC_PROMPT.format(question=str(question or "").strip())


class SemanticQueryAnalyzer:
    """Dependency-free query parser for the first PowerRAG planning step.

    The analyzer intentionally stays domain-neutral: it classifies the question,
    estimates abstraction, extracts evidence hints, and declares which retrieval
    capabilities should be used. Dataset-specific tasks must be handled by data
    profiles, not hard-coded here.
    """

    def analyze(self, question: str) -> TaskSpec:
        original = str(question or "").strip()
        if not original:
            return TaskSpec(
                original_question="",
                rewritten_question="",
                intent=QueryIntent.FACT,
                route=QueryRouteName.LOCAL_RAG,
                route_reason="empty question fallback",
            )

        objects = _extract_objects(original)
        filters = _extract_metadata_filters(original)
        coverage_scope = _coverage_scope(original)
        abstraction_level = _detect_abstraction_level(original, objects, filters)
        semantic_high_level = _extract_semantic_high_level_keywords(original)
        evidence_terms = _extract_semantic_evidence_terms(original)
        high_level = _merge_unique(_extract_high_level_keywords(original) + semantic_high_level)
        low_level = _merge_unique(objects + evidence_terms + _extract_low_level_keywords(original))
        fuzzy_terms = _merge_unique(_extract_fuzzy_terms(original) + ([] if abstraction_level == QueryAbstractionLevel.CONCRETE else high_level))
        intent, route, reason = _classify(original, coverage_scope, abstraction_level)
        output = _output_contract(intent, route)
        evidence = _evidence_requirements(original, route)
        sub_questions = _build_sub_questions(original, intent, route, objects, high_level)

        return TaskSpec(
            original_question=original,
            rewritten_question=_rewrite_question(original),
            intent=intent,
            route=route,
            objects=objects,
            fuzzy_terms=fuzzy_terms,
            high_level_keywords=high_level,
            low_level_keywords=low_level,
            evidence_terms=evidence_terms,
            metadata_filters=filters,
            coverage_scope=coverage_scope,
            abstraction_level=abstraction_level,
            preferred_capabilities=_preferred_capabilities(
                route,
                coverage_scope,
                abstraction_level=abstraction_level,
                evidence_terms=evidence_terms,
            ),
            evidence_requirements=evidence,
            output_contract=output,
            sub_questions=sub_questions,
            requires_planning=route == QueryRouteName.COMPREHENSIVE_ANALYSIS,
            route_reason=reason,
        )


def _classify(
    question: str,
    coverage_scope: QueryCoverageScope = QueryCoverageScope.LOCAL,
    abstraction_level: QueryAbstractionLevel = QueryAbstractionLevel.CONCRETE,
) -> tuple[QueryIntent, QueryRouteName, str]:
    q = question.casefold()
    compact = _compact(question)
    if coverage_scope in {QueryCoverageScope.PARTITIONED, QueryCoverageScope.FULL_CORPUS}:
        return QueryIntent.COMPREHENSIVE, QueryRouteName.COMPREHENSIVE_ANALYSIS, f"{coverage_scope.value} coverage marker"
    if _has_any(q, _FULL_CORPUS_MARKERS) or any(marker in compact for marker in ("全量", "所有资料", "全部资料", "综合分析", "全面分析", "整体分析")):
        return QueryIntent.COMPREHENSIVE, QueryRouteName.COMPREHENSIVE_ANALYSIS, "full-corpus analysis marker"
    if _has_any(q, _COMPARE_MARKERS) or any(marker in compact for marker in ("对比", "比较", "差异", "区别", "优劣")):
        return QueryIntent.COMPARE, QueryRouteName.COMPARE_SYNTHESIS, "comparison marker"
    if _has_any(q, _CAUSAL_MARKERS) or any(marker in compact for marker in ("为什么", "为何", "导致", "原因", "影响", "一步一步", "链路", "推理")):
        return QueryIntent.CAUSAL, QueryRouteName.MULTI_HOP, "causal or multi-hop marker"
    if any(marker in compact for marker in ("关系", "路径", "关联", "联系")) and any(marker in compact for marker in ("之间", "如何", "什么")):
        return QueryIntent.RELATIONSHIP, QueryRouteName.GRAPH_PATH, "entity relationship marker"
    if _has_any(q, _GLOBAL_MARKERS) or any(marker in compact for marker in ("总结", "概括", "主要类别", "主题", "趋势", "整体")):
        return QueryIntent.GLOBAL_SUMMARY, QueryRouteName.GLOBAL_SUMMARY, "global summary marker"
    if abstraction_level != QueryAbstractionLevel.CONCRETE:
        return QueryIntent.GLOBAL_SUMMARY, QueryRouteName.GLOBAL_SUMMARY, "abstract question marker"
    return QueryIntent.FACT, QueryRouteName.LOCAL_RAG, "local factual fallback"


def _coverage_scope(question: str) -> QueryCoverageScope:
    q = re.sub(r"\s+", " ", str(question or "").strip().casefold())
    compact = _compact(q)
    full_ascii = (
        "full corpus",
        "entire corpus",
        "whole corpus",
        "all documents",
        "all docs",
        "all files",
        "all records",
        "all chunks",
        "across the corpus",
        "across all",
    )
    if _has_any(q, full_ascii) or any(marker in compact for marker in ("全量", "所有", "全部")):
        return QueryCoverageScope.FULL_CORPUS

    partition_ascii = (
        "which documents",
        "which docs",
        "which files",
        "which records",
        "which chunks",
        "which sources",
        "what documents",
        "what files",
        "per document",
        "per file",
        "for each document",
        "for each file",
        "each document",
        "each file",
        "list documents",
        "list files",
        "count by",
        "group by",
        "rank",
    )
    partition_cjk = (
        "哪些文档",
        "哪些文件",
        "哪些资料",
        "哪些记录",
        "每个文档",
        "每个文件",
        "逐个",
        "分别",
        "统计",
        "列出",
        "排名",
        "分组",
    )
    if _has_any(q, partition_ascii) or any(marker in compact for marker in partition_cjk):
        return QueryCoverageScope.PARTITIONED
    entity_set_markers = ("哪些人", "哪些对象", "哪些实体", "哪些设备", "哪些项目", "谁")
    if any(marker in compact for marker in entity_set_markers) and any(marker in compact for marker in _ABSTRACT_CJK_MARKERS):
        return QueryCoverageScope.PARTITIONED
    if re.search(r"\bwhich\s+\w+s\b", q) and _has_any(q, ("evidence", "support", "mention", "contain", "include")):
        return QueryCoverageScope.PARTITIONED
    return QueryCoverageScope.LOCAL


def _detect_abstraction_level(
    question: str,
    objects: list[str],
    filters: list[dict[str, str]],
) -> QueryAbstractionLevel:
    q = question.casefold()
    compact = _compact(question)
    has_abstract = _has_any(q, _ABSTRACT_ASCII_MARKERS) or any(marker in compact for marker in _ABSTRACT_CJK_MARKERS)
    has_concrete_filter = bool(filters) or bool(re.search(r"\b(?:id|message_id|chunk_id|page|section)\s*[:=]?\s*[\w.-]+", q))
    has_quote = bool(re.search(r"[\"'“”‘’「」『』《》].+?[\"'“”‘’「」『』《》]", question))
    has_specific_comparison = (any(marker in compact for marker in ("对比", "比较", "差异", "区别")) or _has_any(q, ("compare", "versus", " vs "))) and len(objects) >= 2
    if has_abstract and (has_concrete_filter or has_quote or has_specific_comparison):
        return QueryAbstractionLevel.MIXED
    if has_abstract:
        return QueryAbstractionLevel.ABSTRACT
    return QueryAbstractionLevel.CONCRETE


def _preferred_capabilities(
    route: QueryRouteName,
    coverage_scope: QueryCoverageScope,
    *,
    abstraction_level: QueryAbstractionLevel = QueryAbstractionLevel.CONCRETE,
    evidence_terms: list[str] | None = None,
) -> list[str]:
    def with_semantic(capabilities: list[str]) -> list[str]:
        if abstraction_level != QueryAbstractionLevel.CONCRETE or evidence_terms:
            capabilities.append("semantic_query_expansion")
        return _merge_unique(capabilities)

    if route == QueryRouteName.LOCAL_RAG:
        return with_semantic(["text_search"])
    if route == QueryRouteName.GRAPH_PATH:
        return with_semantic(["graph_search", "text_search"])
    if route == QueryRouteName.GLOBAL_SUMMARY:
        return with_semantic(["global_summary", "graph_search", "text_search"])
    if route == QueryRouteName.MULTI_HOP:
        return with_semantic(["text_search", "graph_search", "rerank"])
    if route == QueryRouteName.COMPARE_SYNTHESIS:
        return with_semantic(["text_search", "graph_search", "rerank"])
    if route == QueryRouteName.COMPREHENSIVE_ANALYSIS:
        capabilities = ["text_full_scan", "text_search"]
        if coverage_scope != QueryCoverageScope.LOCAL:
            capabilities.extend(["partition_scan", "coverage_report"])
        capabilities.extend(["graph_search", "global_summary"])
        return with_semantic(capabilities)
    return with_semantic(["text_search"])


def _rewrite_question(question: str) -> str:
    text = re.sub(r"\s+", " ", question).strip()
    return text.replace("queyrout", "query router").replace("quy", "query")


def _extract_objects(question: str) -> list[str]:
    candidates: list[str] = []
    for match in re.finditer(r"[「『《“\"]([^」』》”\"]+)[」』》”\"]", question):
        candidates.append(match.group(1).strip())
    for match in re.finditer(r"\b([A-Za-z][A-Za-z0-9_.-]{2,})\b", question):
        token = match.group(1).strip()
        if token.casefold() not in _LOW_LEVEL_STOPWORDS:
            candidates.append(token)
    candidates.extend(_extract_cjk_object_phrases(question))
    return _merge_unique(candidates)


def _extract_cjk_object_phrases(question: str) -> list[str]:
    text = re.sub(r"\d{2,4}\s*年?", " ", question)
    phrases: list[str] = []
    for chunk in re.split(r"[^\u4e00-\u9fffA-Za-z0-9_]+", text):
        if not chunk or not re.search(r"[\u4e00-\u9fff]", chunk):
            continue
        for part in _CJK_OBJECT_SPLIT_RE.split(chunk):
            item = part.strip()
            if not (2 <= len(item) <= 16):
                continue
            if item in _CJK_OBJECT_STOPWORDS:
                continue
            if item.casefold() in _LOW_LEVEL_STOPWORDS:
                continue
            phrases.append(item)
    return phrases


_GENERIC_SEMANTIC_CONCEPTS: tuple[tuple[tuple[str, ...], tuple[str, ...], str], ...] = (
    (
        ("风险", "隐患", "安全", "可靠性", "risk", "hazard", "safety", "reliability"),
        ("风险", "隐患", "失效", "故障", "异常", "安全", "可靠性", "报警", "超限"),
        "风险",
    ),
    (
        ("故障", "问题", "异常", "失效", "failure", "fault", "issue", "abnormal"),
        ("故障", "异常", "报警", "失效", "损坏", "磨损", "裂纹", "过热", "振动", "温度"),
        "故障",
    ),
    (
        ("原因", "导致", "影响因素", "为什么", "因果", "cause", "why", "factor"),
        ("因为", "由于", "导致", "造成", "影响", "相关", "原因", "因素", "结果"),
        "原因",
    ),
    (
        ("维护", "检修", "处理措施", "措施", "方案", "maintenance", "repair", "mitigation"),
        ("维护", "检修", "保养", "更换", "清洗", "调整", "检查", "处理", "措施", "方案"),
        "维护",
    ),
    (
        ("性能", "效率", "功率", "指标", "performance", "efficiency", "metric"),
        ("性能", "效率", "功率", "压比", "温度", "流量", "压力", "指标", "变化"),
        "性能",
    ),
    (
        ("类别", "类型", "分类", "模式", "kind", "type", "category", "class"),
        ("类型", "类别", "模式", "分类", "场景", "表现", "特征"),
        "类别",
    ),
    (
        ("趋势", "变化", "规律", "trend", "pattern", "change"),
        ("上升", "下降", "波动", "变化", "趋势", "规律", "阶段", "周期"),
        "趋势",
    ),
    (
        ("争执", "争议", "冲突", "矛盾", "纠纷", "conflict", "dispute"),
        ("争执", "争议", "冲突", "矛盾", "纠纷", "分歧", "投诉", "拒绝", "反对", "道歉"),
        "冲突",
    ),
    (
        ("对比", "比较", "差异", "区别", "优劣", "compare", "versus", "difference"),
        ("优点", "缺点", "差异", "相同", "不同", "适用", "限制", "优势", "劣势"),
        "对比",
    ),
)


def _extract_semantic_evidence_terms(question: str) -> list[str]:
    compact = _compact(question)
    q = question.casefold()
    terms: list[str] = []
    for triggers, evidence_terms, _concept in _GENERIC_SEMANTIC_CONCEPTS:
        if any(trigger.casefold() in q or trigger.casefold() in compact for trigger in triggers):
            terms.extend(evidence_terms)
    return _merge_unique(terms)


def _extract_semantic_high_level_keywords(question: str) -> list[str]:
    compact = _compact(question)
    q = question.casefold()
    concepts: list[str] = []
    for triggers, _evidence_terms, concept in _GENERIC_SEMANTIC_CONCEPTS:
        if any(trigger.casefold() in q or trigger.casefold() in compact for trigger in triggers):
            concepts.append(concept)
    return _merge_unique(concepts)


def _extract_high_level_keywords(question: str) -> list[str]:
    keywords: list[str] = []
    mapping = {
        "风险": ("风险",),
        "故障": ("故障", "故障模式"),
        "问题": ("问题",),
        "维护": ("维护问题",),
        "原因": ("原因",),
        "导致": ("因果链路",),
        "关系": ("关系",),
        "类别": ("类别",),
        "类型": ("类别",),
        "处理措施": ("处理措施",),
        "措施": ("处理措施",),
        "总结": ("总结",),
        "全量": ("全量分析",),
        "所有资料": ("全量分析",),
        "对比": ("对比",),
        "比较": ("对比",),
        "趋势": ("趋势",),
        "质量": ("质量",),
        "性能": ("性能",),
    }
    compact = _compact(question)
    for marker, values in mapping.items():
        if marker in compact:
            keywords.extend(values)
    if not keywords:
        keywords.extend(_extract_objects(question)[:3])
    return _merge_unique(keywords)


def _extract_low_level_keywords(question: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9_.-]{2,}|\d{4}|[\u4e00-\u9fff]{2,}", question)
    return _merge_unique(token for token in tokens if token.casefold() not in _LOW_LEVEL_STOPWORDS and len(token) >= 2)


def _extract_fuzzy_terms(question: str) -> list[str]:
    compact = _compact(question)
    fuzzy_markers = ("主要", "常见", "重要", "严重", "风险", "趋势", "类别", "类型", "整体", "相关", "可能", "大概")
    return [term for term in fuzzy_markers if term in compact]


def _extract_metadata_filters(question: str) -> list[dict[str, str]]:
    filters: list[dict[str, str]] = []
    for year in re.findall(r"(?<!\d)(20\d{2}|19\d{2})(?!\d)", question):
        filters.append({"field": "year", "operator": "=", "value": year})
    for page in re.findall(r"第\s*(\d+)\s*页", question):
        filters.append({"field": "page", "operator": "=", "value": page})
    for chapter in re.findall(r"第\s*([一二三四五六七八九十\d]+)\s*[章节]", question):
        filters.append({"field": "chapter", "operator": "=", "value": chapter})
    if "pdf" in question.casefold():
        filters.append({"field": "file_type", "operator": "=", "value": "pdf"})
    if "docx" in question.casefold() or "word" in question.casefold():
        filters.append({"field": "file_type", "operator": "=", "value": "docx"})
    return filters


def _evidence_requirements(question: str, route: QueryRouteName) -> EvidenceRequirements:
    explicit_citation = any(marker in question for marker in ("引用", "证据", "来源", "原文", "出处")) or _has_any(
        question.casefold(), ("cite", "citation", "source", "evidence")
    )
    return EvidenceRequirements(
        must_cite=True if explicit_citation or route != QueryRouteName.LOCAL_RAG else True,
        require_source_span=True,
        no_evidence_policy="return_insufficient_evidence",
        coverage_report=route == QueryRouteName.COMPREHENSIVE_ANALYSIS,
        min_sources=2 if route in {QueryRouteName.COMPARE_SYNTHESIS, QueryRouteName.COMPREHENSIVE_ANALYSIS} else 1,
    )


def _output_contract(intent: QueryIntent, route: QueryRouteName) -> OutputContract:
    if route == QueryRouteName.COMPARE_SYNTHESIS:
        return OutputContract(format="comparison_table")
    if route == QueryRouteName.COMPREHENSIVE_ANALYSIS:
        return OutputContract(format="structured_report")
    if intent == QueryIntent.CAUSAL:
        return OutputContract(format="reasoning_chain")
    return OutputContract(format="grounded_answer")


def _build_sub_questions(
    question: str,
    intent: QueryIntent,
    route: QueryRouteName,
    objects: list[str],
    high_level_keywords: list[str],
) -> list[str]:
    if route == QueryRouteName.COMPREHENSIVE_ANALYSIS:
        target = objects[0] if objects else "目标对象"
        return [
            f"{target}涉及哪些主要类别？",
            f"{target}的原因、影响因素或风险链路有哪些？",
            f"{target}对应的处理措施和原文证据是什么？",
            "哪些资料、对象或时间段尚未被证据覆盖？",
        ]
    if route == QueryRouteName.COMPARE_SYNTHESIS and len(objects) >= 2:
        focus = "、".join(high_level_keywords[:2]) or "关键信息"
        return [f"{obj}的{focus}是什么？" for obj in objects[:4]]
    if route == QueryRouteName.MULTI_HOP:
        left = objects[0] if objects else "前置现象"
        right = objects[-1] if len(objects) > 1 else "结果"
        return [
            f"{left}的直接证据是什么？",
            f"{left}如何影响{right}？",
            f"是否有原文证据支持完整链路：{question}",
        ]
    return []


def _has_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker.casefold() in text for marker in markers)


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", str(text or "").casefold())


def _merge_unique(values: Any) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        output.append(text)
    return output


_FULL_CORPUS_MARKERS = (
    "full corpus",
    "whole corpus",
    "entire corpus",
    "all documents",
    "all files",
    "comprehensive analysis",
)
_COMPARE_MARKERS = ("compare", "comparison", "versus", " vs ", "difference", "pros and cons")
_CAUSAL_MARKERS = ("why", "cause", "caused by", "lead to", "result in", "impact", "step by step")
_GLOBAL_MARKERS = ("summary", "summarize", "overview", "theme", "trend", "overall", "main categories")
_ABSTRACT_ASCII_MARKERS = (
    "why",
    "how",
    "cause",
    "factor",
    "risk",
    "trend",
    "pattern",
    "category",
    "type",
    "class",
    "quality",
    "performance",
    "relationship",
    "summary",
    "compare",
    "which",
    "what kinds",
)
_ABSTRACT_CJK_MARKERS = (
    "哪些",
    "哪类",
    "类型",
    "类别",
    "为什么",
    "如何",
    "原因",
    "导致",
    "影响",
    "风险",
    "趋势",
    "规律",
    "模式",
    "质量",
    "性能",
    "关系",
    "总结",
    "概括",
    "对比",
    "比较",
    "程度",
    "指标",
    "争执",
    "争议",
    "冲突",
    "矛盾",
    "纠纷",
)
_CJK_OBJECT_SPLIT_RE = re.compile(
    r"(?:哪些|哪个|什么|如何|为什么|是否|所有|全部|全量|整体|主要|具体|"
    r"分析|总结|对比|比较|区别|差异|原因|风险|问题|故障|异常|类别|类型|"
    r"趋势|关系|影响|证据|原文|资料|文件|记录|里面|里的|之间|关于|有关|相关|"
    r"导致|造成|引起|发生|发生过|支持|提到|包含|引用|必须|给出|找|一步一步|"
    r"处理|措施|维护|运行|会|能|可以|应该|需要|请|帮我|和|与|及|以及|或|的|了|是|有|没有|在|里|中)"
)
_CJK_OBJECT_STOPWORDS = {
    "我",
    "我们",
    "你",
    "它",
    "他们",
    "这些",
    "那些",
    "当前",
    "系统",
    "知识库",
    "结果",
    "答案",
    "结论",
}
_LOW_LEVEL_STOPWORDS = {
    "对比",
    "比较",
    "全量",
    "分析",
    "所有",
    "资料",
    "里面",
    "之间",
    "什么",
    "为什么",
    "如何",
    "必须",
    "引用",
    "原文",
    "证据",
    "主要",
    "一步一步",
    "which",
    "what",
    "when",
    "where",
    "documents",
    "document",
    "mention",
    "evidence",
    "supports",
    "support",
    "each",
}
