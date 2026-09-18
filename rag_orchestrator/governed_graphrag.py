"""Version-aware, evidence-governed GraphRAG answering and evaluation."""

# ruff: noqa: C901, RUF001, TRY003

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from core_domain.delivery import ContentStatus, GraphStatement, GraphVersion
from storage_layer.governance_store import GovernanceError, GovernanceStore

_RELATION_INTENTS: dict[str, tuple[str, ...]] = {
    "CAUSED_BY": ("原因", "根因", "为什么", "caused", "cause"),
    "HAS_EFFECT": ("影响", "后果", "导致什么", "effect", "impact"),
    "DETECTED_BY": ("检测", "发现", "监测", "识别", "detect", "monitor"),
    "MITIGATED_BY": ("措施", "处理", "维修", "缓解", "如何", "action", "mitigate"),
    "PART_OF": ("属于", "层级", "组成", "部件", "part of", "hierarchy"),
    "HAS_FAILURE_MODE": ("故障", "故障模式", "failure mode"),
}

_GENERIC_BIGRAMS = {
    "燃气",
    "气轮",
    "轮机",
    "燃机",
    "压气",
    "气机",
    "什么",
    "如何",
    "是否",
    "通过",
    "影响",
    "原因",
    "措施",
    "维修",
    "多少",
    "哪些",
    "型号",
}


@dataclass(frozen=True, slots=True)
class GovernedQAResult:
    question: str
    requested_mode: str
    mode_used: str
    graph_version_id: str | None
    answer: str
    citations: tuple[dict[str, Any], ...]
    paths: tuple[dict[str, Any], ...] = ()
    quality: dict[str, Any] | None = None
    fallback: dict[str, Any] | None = None
    no_answer: bool = False
    prompt: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "requested_mode": self.requested_mode,
            "mode_used": self.mode_used,
            "graph_version_id": self.graph_version_id,
            "answer": self.answer,
            "citations": list(self.citations),
            "evidence": list(self.citations),
            "paths": list(self.paths),
            "quality": self.quality or {},
            "fallback": self.fallback,
            "no_answer": self.no_answer,
            "prompt": self.prompt,
        }


class GovernedGraphRAGService:
    """Query one governed graph version without losing evidence or fallback lineage."""

    def __init__(self, store: GovernanceStore, document_index: Any, *, llm: Any | None = None) -> None:
        self.store = store
        self.document_index = document_index
        self.llm = llm

    def ordinary_rag(
        self,
        question: str,
        *,
        document_version_ids: Sequence[str],
        top_k: int = 5,
    ) -> GovernedQAResult:
        clean_question = _required_question(question)
        retrieval = self.document_index.query(
            clean_question,
            top_k=top_k,
            document_version_ids=document_version_ids,
        )
        raw_results = list(retrieval.get("results") or [])
        relevant_results = [item for item in raw_results if _text_relevance(clean_question, str(item.get("text") or ""))]
        citations = tuple(
            {
                "id": f"T{index}",
                "source_type": "ordinary_rag",
                "evidence_id": str(item.get("evidence_id") or ""),
                "text": str(item.get("text") or ""),
                "score": item.get("score"),
                "source": (item.get("locator") or {}).get("source_file"),
                "page": (item.get("locator") or {}).get("page"),
                "locator": dict(item.get("locator") or {}),
            }
            for index, item in enumerate(relevant_results, start=1)
        )
        prompt = _ordinary_prompt(clean_question, citations)
        if not citations:
            return GovernedQAResult(
                question=clean_question,
                requested_mode="ordinary_rag",
                mode_used="ordinary_rag",
                graph_version_id=None,
                answer="当前已发布资料中没有足够的原文证据回答该问题。",
                citations=(),
                quality={
                    "retrieved_count": len(raw_results),
                    "relevant_count": 0,
                    "evidence_coverage": 0.0,
                },
                no_answer=True,
                prompt=prompt,
            )
        answer = _answer_with_optional_llm(
            self.llm,
            prompt,
            fallback=_ordinary_extract_answer(citations),
        )
        return GovernedQAResult(
            question=clean_question,
            requested_mode="ordinary_rag",
            mode_used="ordinary_rag",
            graph_version_id=None,
            answer=answer,
            citations=citations,
            quality={
                "retrieved_count": len(raw_results),
                "relevant_count": len(citations),
                "evidence_coverage": 1.0,
            },
            prompt=prompt,
        )

    def graph_rag(
        self,
        graph_version_id: str,
        question: str,
        *,
        top_k: int = 8,
        max_hops: int = 4,
        allow_fallback: bool = True,
    ) -> GovernedQAResult:
        clean_question = _required_question(question)
        graph = self.store.get_graph_version(graph_version_id)
        if graph.status is not ContentStatus.PUBLISHED:
            raise GovernanceError("GraphRAG requires a published graph version")

        selected = _select_graph_statements(graph, clean_question, top_k=top_k)
        citations = self._graph_citations(selected)
        paths = self._query_paths(graph, clean_question, selected, max_hops=max_hops)
        evidence_bound = sum(1 for item in selected if item.evidence_ids)
        confidences = [float(item.confidence) for item in selected if item.confidence is not None]
        quality = {
            "graph_statement_count": len(graph.statements),
            "matched_statement_count": len(selected),
            "graph_evidence_coverage": evidence_bound / len(selected) if selected else 0.0,
            "average_confidence": sum(confidences) / len(confidences) if confidences else 0.0,
            "path_count": len(paths),
            "evidence_audit": self.store.audit_graph_evidence(graph_version_id),
        }
        sufficient = bool(selected) and quality["graph_evidence_coverage"] == 1.0 and bool(citations)
        quality["sufficient_for_answer"] = sufficient
        quality["decision"] = "use_graphrag" if sufficient else "fallback_to_ordinary_rag"

        if not sufficient and allow_fallback:
            ordinary = self.ordinary_rag(
                clean_question,
                document_version_ids=graph.source_document_version_ids,
                top_k=top_k,
            )
            return GovernedQAResult(
                question=clean_question,
                requested_mode="graphrag",
                mode_used="ordinary_rag",
                graph_version_id=graph_version_id,
                answer=ordinary.answer,
                citations=ordinary.citations,
                paths=(),
                quality=quality,
                fallback={
                    "triggered": True,
                    "from": "graphrag",
                    "to": "ordinary_rag",
                    "reason": "no_relevant_evidence_bound_graph_path",
                },
                no_answer=ordinary.no_answer,
                prompt=ordinary.prompt,
            )

        prompt = _graph_prompt(clean_question, citations, paths)
        if not sufficient:
            return GovernedQAResult(
                question=clean_question,
                requested_mode="graphrag",
                mode_used="graphrag",
                graph_version_id=graph_version_id,
                answer="当前图版本中没有足够的相关证据路径回答该问题。",
                citations=(),
                paths=(),
                quality=quality,
                no_answer=True,
                prompt=prompt,
            )
        answer = _answer_with_optional_llm(
            self.llm,
            prompt,
            fallback=_graph_extract_answer(citations, paths),
        )
        return GovernedQAResult(
            question=clean_question,
            requested_mode="graphrag",
            mode_used="graphrag",
            graph_version_id=graph_version_id,
            answer=answer,
            citations=citations,
            paths=paths,
            quality=quality,
            prompt=prompt,
        )

    def compare_same_questions(
        self,
        graph_version_id: str,
        questions: Sequence[Mapping[str, Any] | str],
        *,
        top_k: int = 8,
    ) -> dict[str, Any]:
        graph = self.store.get_graph_version(graph_version_id)
        if graph.status is not ContentStatus.PUBLISHED:
            raise GovernanceError("RAG comparison requires a published graph version")
        cases: list[dict[str, Any]] = []
        winners = {"ordinary_rag": 0, "graphrag": 0, "tie": 0}
        for index, raw in enumerate(questions, start=1):
            payload = {"question": raw} if isinstance(raw, str) else dict(raw)
            question = _required_question(str(payload.get("question") or ""))
            expected = tuple(str(item) for item in payload.get("expected_keywords") or () if str(item))
            ordinary = self.ordinary_rag(
                question,
                document_version_ids=graph.source_document_version_ids,
                top_k=top_k,
            )
            graph_result = self.graph_rag(
                graph_version_id,
                question,
                top_k=top_k,
                allow_fallback=False,
            )
            ordinary_recall = _keyword_recall(expected, ordinary)
            graph_recall = _keyword_recall(expected, graph_result)
            if graph_recall > ordinary_recall:
                winner = "graphrag"
            elif ordinary_recall > graph_recall:
                winner = "ordinary_rag"
            elif graph_result.paths and not ordinary.no_answer:
                winner = "graphrag"
            else:
                winner = "tie"
            winners[winner] += 1
            fallback_recommended = bool(graph_result.no_answer or not (graph_result.quality or {}).get("sufficient_for_answer"))
            cases.append({
                "id": str(payload.get("id") or f"Q{index}"),
                "question": question,
                "expected_keywords": list(expected),
                "expected_no_answer": bool(payload.get("expected_no_answer", False)),
                "ordinary_rag": ordinary.to_dict(),
                "graphrag": graph_result.to_dict(),
                "metrics": {
                    "ordinary_keyword_recall": ordinary_recall,
                    "graphrag_keyword_recall": graph_recall,
                    "ordinary_citation_count": len(ordinary.citations),
                    "graphrag_citation_count": len(graph_result.citations),
                    "graphrag_path_count": len(graph_result.paths),
                },
                "winner": winner,
                "fallback_recommended": fallback_recommended,
            })
        return {
            "evaluation_type": "ordinary_rag_vs_graphrag_same_questions",
            "graph_version_id": graph_version_id,
            "document_version_ids": list(graph.source_document_version_ids),
            "case_count": len(cases),
            "winner_counts": winners,
            "cases": cases,
        }

    def _graph_citations(self, statements: Sequence[GraphStatement]) -> tuple[dict[str, Any], ...]:
        citations: list[dict[str, Any]] = []
        for index, statement in enumerate(statements, start=1):
            locators = [self.store.get_evidence(item) for item in statement.evidence_ids]
            citations.append({
                "id": f"G{index}",
                "source_type": "governed_graph",
                "statement_id": statement.statement_id,
                "subject": statement.subject,
                "predicate": statement.predicate,
                "object": statement.object_name,
                "knowledge_type": statement.knowledge_type,
                "model_scope": list(statement.model_scope),
                "confidence": statement.confidence,
                "evidence_ids": list(statement.evidence_ids),
                "text": "\n".join(item.text for item in locators),
                "source": locators[0].source_file if locators else None,
                "page": locators[0].page if locators else None,
                "locators": [item.to_dict() for item in locators],
            })
        return tuple(citations)

    def _query_paths(
        self,
        graph: GraphVersion,
        question: str,
        statements: Sequence[GraphStatement],
        *,
        max_hops: int,
    ) -> tuple[dict[str, Any], ...]:
        node_types = _node_types(graph.statements)
        explicit_nodes = [
            node
            for node, entity_type in node_types.items()
            if node.casefold() in question.casefold() and entity_type not in {"MODEL"}
        ]
        target_nodes = list(
            dict.fromkeys(
                node
                for item in statements
                for node in (item.subject, item.object_name)
                if node not in explicit_nodes
            )
        )
        paths: list[dict[str, Any]] = []
        for source in explicit_nodes[:2]:
            for target in target_nodes[:6]:
                result = self.store.find_graph_path(
                    graph.graph_version_id,
                    source,
                    target,
                    max_hops=max_hops,
                )
                if result.get("found") and result.get("hop_count", 0) >= 1:
                    signature = tuple(result.get("nodes") or ())
                    if signature and all(tuple(item.get("nodes") or ()) != signature for item in paths):
                        paths.append(result)
                if len(paths) >= 3:
                    return tuple(paths)
        return tuple(paths)


def _select_graph_statements(graph: GraphVersion, question: str, *, top_k: int) -> tuple[GraphStatement, ...]:
    folded = question.casefold()
    node_types = _node_types(graph.statements)
    meaningful_matches = {
        node
        for node, entity_type in node_types.items()
        if node.casefold() in folded and entity_type not in {"EQUIPMENT", "MODEL"}
    }
    intent_relations = {
        relation
        for relation, markers in _RELATION_INTENTS.items()
        if any(marker.casefold() in folded for marker in markers)
    }
    scored: list[tuple[float, GraphStatement]] = []
    for item in graph.statements:
        text = f"{item.subject} {item.predicate} {item.object_name}".casefold()
        score = 0.0
        if item.subject in meaningful_matches or item.object_name in meaningful_matches:
            score += 10.0
        if item.predicate in intent_relations:
            score += 4.0
        if item.model_scope and any(model.casefold() in folded for model in item.model_scope):
            score += 1.0
        score += min(3.0, float(_meaningful_bigram_overlap(question, text)))
        if score >= 4.0 and (meaningful_matches or _meaningful_bigram_overlap(question, text) >= 2):
            scored.append((score, item))
    scored.sort(key=lambda row: (-row[0], row[1].statement_id))
    seeds = [item for _score, item in scored[: max(1, top_k)]]
    if not seeds:
        return ()

    selected: list[GraphStatement] = list(seeds)
    frontier = {node for item in seeds for node in (item.subject, item.object_name)}
    for _ in range(2):
        added_nodes: set[str] = set()
        for item in graph.statements:
            if item in selected:
                continue
            if item.subject in frontier or item.object_name in frontier:
                selected.append(item)
                added_nodes.update((item.subject, item.object_name))
                if len(selected) >= top_k:
                    break
        frontier = added_nodes
        if not frontier or len(selected) >= top_k:
            break
    return tuple(selected[:top_k])


def _node_types(statements: Sequence[GraphStatement]) -> dict[str, str]:
    output: dict[str, str] = {}
    for item in statements:
        output.setdefault(item.subject, item.subject_type)
        output.setdefault(item.object_name, item.object_type)
    return output


def _question_bigrams(value: str) -> set[str]:
    output: set[str] = set()
    for sequence in re.findall(r"[\u4e00-\u9fff]{2,}", str(value)):
        for index in range(len(sequence) - 1):
            token = sequence[index : index + 2]
            if token not in _GENERIC_BIGRAMS:
                output.add(token)
    output.update(
        token.casefold()
        for token in re.findall(r"[A-Za-z][A-Za-z0-9_-]{1,}", str(value))
        if not re.fullmatch(r"M?\d+[A-Za-z]*", token, re.I)
    )
    return output


def _meaningful_bigram_overlap(question: str, text: str) -> int:
    terms = _question_bigrams(question)
    folded = text.casefold()
    return sum(1 for term in terms if term in folded)


def _text_relevance(question: str, text: str) -> bool:
    terms = _question_bigrams(question)
    if not terms:
        return bool(text.strip())
    matched = sum(1 for term in terms if term in text.casefold())
    return matched >= 2 and matched / len(terms) >= 0.25


def _ordinary_prompt(question: str, citations: Sequence[Mapping[str, Any]]) -> str:
    evidence = "\n".join(f"[{item['id']}] {item.get('text') or ''}" for item in citations)
    return (
        "你是普通RAG问答助手。只能根据给定原文证据回答；每个专业陈述必须引用[T#]。"
        "证据不足时明确回答无答案。\n"
        f"问题：{question}\n原文证据：\n{evidence}\n回答："
    )


def _graph_prompt(
    question: str,
    citations: Sequence[Mapping[str, Any]],
    paths: Sequence[Mapping[str, Any]],
) -> str:
    evidence = "\n".join(
        f"[{item['id']}] {item.get('subject')} --{item.get('predicate')}--> {item.get('object')}；"
        f"原文：{item.get('text') or ''}"
        for item in citations
    )
    path_text = "\n".join(" -> ".join(str(node) for node in item.get("nodes") or ()) for item in paths)
    return (
        "你是燃气轮机GraphRAG问答助手。只能使用给定图关系、图路径和原文证据回答；"
        "每个专业陈述必须引用[G#]，不得虚构。\n"
        f"问题：{question}\n图证据：\n{evidence}\n图路径：\n{path_text}\n回答："
    )


def _ordinary_extract_answer(citations: Sequence[Mapping[str, Any]]) -> str:
    lines = ["根据已发布资料的原文检索结果："]
    for item in citations[:5]:
        lines.append(f"- {str(item.get('text') or '').strip()} [{item['id']}]")
    return "\n".join(lines)


def _graph_extract_answer(
    citations: Sequence[Mapping[str, Any]],
    paths: Sequence[Mapping[str, Any]],
) -> str:
    lines = ["根据已发布图谱及其原文证据："]
    for item in citations[:8]:
        lines.append(
            f"- {item.get('subject')} --{item.get('predicate')}--> {item.get('object')} [{item['id']}]"
        )
    if paths:
        lines.append("图路径：" + "；".join(" → ".join(item.get("nodes") or ()) for item in paths[:3]))
    return "\n".join(lines)


def _answer_with_optional_llm(llm: Any | None, prompt: str, *, fallback: str) -> str:
    if llm is None:
        return fallback
    for method_name in ("complete", "generate", "invoke"):
        method = getattr(llm, method_name, None)
        if callable(method):
            raw = method(prompt)
            return _response_text(raw)
    if callable(llm):
        return _response_text(llm(prompt))
    raise TypeError("Configured governed GraphRAG LLM must be callable or expose complete/generate/invoke")


def _response_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        for key in ("answer", "content", "text", "output"):
            if value.get(key) is not None:
                return str(value[key])
    for attr in ("content", "text", "answer"):
        if getattr(value, attr, None) is not None:
            return str(getattr(value, attr))
    return str(value)


def _keyword_recall(expected: Sequence[str], result: GovernedQAResult) -> float:
    if not expected:
        return 1.0 if result.no_answer else 0.0
    haystack = "\n".join(
        [result.answer, *(str(item.get("text") or "") for item in result.citations)]
    ).casefold()
    return sum(1 for item in expected if item.casefold() in haystack) / len(expected)


def _required_question(question: str) -> str:
    clean = str(question).strip()
    if not clean:
        raise ValueError("question must not be empty")
    return clean
