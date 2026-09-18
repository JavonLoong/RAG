from __future__ import annotations

import inspect
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from .graphrag_qa import (
    EMPTY_QUESTION_ERROR,
    INVALID_TOP_K_ERROR,
    EvidenceItem,
    GraphRagConfigurationError,
    build_context,
    _as_items,
    _call_llm,
    _call_retriever,
    _format_global_context,
    _global_source_evidence_items,
    _normalize_graph_evidence,
    _normalize_text_evidence,
)
from .query_understanding import QueryRouteName, TaskSpec

ADVANCED_QUERY_ROUTES = {
    QueryRouteName.MULTI_HOP,
    QueryRouteName.COMPARE_SYNTHESIS,
    QueryRouteName.COMPREHENSIVE_ANALYSIS,
}

ADVANCED_MISSING_LLM_ERROR = (
    "LLM client is required for advanced query synthesis; pass llm=... "
    "or use context_only=True for retrieval debugging."
)


@dataclass(slots=True)
class AdvancedQueryExecutionResult:
    question: str
    answer: str | None
    context: str
    citations: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    context_only: bool
    task_spec: dict[str, Any]
    advanced_mode: str
    steps: list[dict[str, Any]] = field(default_factory=list)
    coverage_report: dict[str, Any] = field(default_factory=dict)
    comparison_table: list[dict[str, Any]] = field(default_factory=list)
    prompt: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "answer": self.answer,
            "context": self.context,
            "citations": self.citations,
            "evidence": self.evidence,
            "context_only": self.context_only,
            "prompt": self.prompt,
            "task_spec": self.task_spec,
            "advanced_mode": self.advanced_mode,
            "steps": self.steps,
            "coverage_report": self.coverage_report,
            "comparison_table": self.comparison_table,
        }


class AdvancedQueryExecutor:
    """Executes the higher-level RAG branches over existing retrievers.

    The executor deliberately keeps the old answer/context/citation response
    surface intact while adding structured artifacts for planning, comparison,
    and coverage reporting.
    """

    def __init__(
        self,
        *,
        text_retriever: Any,
        graph_retriever: Any,
        global_searcher: Any | None = None,
        llm: Any | None = None,
        full_scan_limit: int = 2000,
        prompt_builder: Callable[[TaskSpec, str, list[dict[str, Any]], dict[str, Any]], str] | None = None,
    ) -> None:
        self.text_retriever = text_retriever
        self.graph_retriever = graph_retriever
        self.global_searcher = global_searcher
        self.llm = llm
        self.full_scan_limit = max(1, int(full_scan_limit))
        self.prompt_builder = prompt_builder or build_advanced_prompt

    def execute(
        self,
        task_spec: TaskSpec,
        *,
        top_k: int = 5,
        context_only: bool = False,
    ) -> AdvancedQueryExecutionResult:
        question = (task_spec.rewritten_question or task_spec.original_question or "").strip()
        if not question:
            raise ValueError(EMPTY_QUESTION_ERROR)
        if top_k < 1:
            raise ValueError(INVALID_TOP_K_ERROR)
        if self.llm is None and not context_only:
            raise GraphRagConfigurationError(ADVANCED_MISSING_LLM_ERROR)

        if task_spec.route == QueryRouteName.MULTI_HOP:
            return self._execute_multi_hop(task_spec, top_k=top_k, context_only=context_only)
        if task_spec.route == QueryRouteName.COMPARE_SYNTHESIS:
            return self._execute_compare(task_spec, top_k=top_k, context_only=context_only)
        if task_spec.route == QueryRouteName.COMPREHENSIVE_ANALYSIS:
            return self._execute_comprehensive(task_spec, top_k=top_k, context_only=context_only)
        raise ValueError(f"Unsupported advanced route: {task_spec.route}")

    def _execute_multi_hop(
        self,
        task_spec: TaskSpec,
        *,
        top_k: int,
        context_only: bool,
    ) -> AdvancedQueryExecutionResult:
        queries = task_spec.sub_questions or [task_spec.rewritten_question or task_spec.original_question]
        run = _EvidenceRun(question=task_spec.original_question)
        steps: list[dict[str, Any]] = []
        for index, query in enumerate(queries, start=1):
            batch = self._retrieve_query(query, top_k=top_k, run=run)
            steps.append(_step_payload(index=index, query=query, step_type="sub_question", batch=batch))

        artifacts = {"steps": steps, "coverage_report": _coverage_report(steps)}
        return self._finalize(
            task_spec,
            run=run,
            steps=steps,
            context_only=context_only,
            artifacts=artifacts,
        )

    def _execute_compare(
        self,
        task_spec: TaskSpec,
        *,
        top_k: int,
        context_only: bool,
    ) -> AdvancedQueryExecutionResult:
        objects = task_spec.objects or _fallback_objects(task_spec)
        run = _EvidenceRun(question=task_spec.original_question)
        steps: list[dict[str, Any]] = []
        rows: list[dict[str, Any]] = []
        for index, obj in enumerate(objects, start=1):
            query = _object_query(obj, task_spec)
            batch = self._retrieve_query(query, top_k=top_k, run=run)
            citations = [item.citation_id for item in [*batch.text_evidence, *batch.graph_evidence]]
            rows.append(
                {
                    "object": obj,
                    "query": query,
                    "evidence_count": len(citations),
                    "key_evidence": _join_key_evidence([*batch.text_evidence, *batch.graph_evidence]),
                    "citations": citations,
                }
            )
            steps.append(_step_payload(index=index, query=query, step_type="compare_object", batch=batch, obj=obj))

        artifacts = {
            "steps": steps,
            "comparison_table": rows,
            "coverage_report": _coverage_report(steps, object_count=len(objects)),
        }
        return self._finalize(
            task_spec,
            run=run,
            steps=steps,
            comparison_table=rows,
            context_only=context_only,
            artifacts=artifacts,
        )

    def _execute_comprehensive(
        self,
        task_spec: TaskSpec,
        *,
        top_k: int,
        context_only: bool,
    ) -> AdvancedQueryExecutionResult:
        queries = task_spec.sub_questions or _default_comprehensive_queries(task_spec)
        run = _EvidenceRun(question=task_spec.original_question)
        steps: list[dict[str, Any]] = []
        for index, query in enumerate(queries, start=1):
            batch = self._retrieve_query(query, top_k=top_k, run=run)
            steps.append(_step_payload(index=index, query=query, step_type="planned_query", batch=batch))

        scan_report = self._add_full_scan_sample(run)
        global_report = self._add_global_context(task_spec.original_question, run)
        coverage = _coverage_report(
            steps,
            object_count=len(task_spec.objects),
            full_scan=scan_report,
            global_search=global_report,
        )
        artifacts = {
            "steps": steps,
            "coverage_report": coverage,
            "full_scan_items": [item.to_dict() for item in run.full_scan_evidence],
        }
        return self._finalize(
            task_spec,
            run=run,
            steps=steps,
            coverage_report=coverage,
            context_only=context_only,
            artifacts=artifacts,
        )

    def _retrieve_query(self, query: str, *, top_k: int, run: _EvidenceRun) -> _EvidenceBatch:
        text_items = _safe_retrieve_text(self.text_retriever, query, top_k, run.next_text_rank)
        run.next_text_rank += len(text_items)
        graph_items = _safe_retrieve_graph(self.graph_retriever, query, top_k, run.next_graph_rank)
        run.next_graph_rank += len(graph_items)
        run.text_evidence.extend(text_items)
        run.graph_evidence.extend(graph_items)
        return _EvidenceBatch(text_evidence=text_items, graph_evidence=graph_items)

    def _add_full_scan_sample(self, run: _EvidenceRun) -> dict[str, Any]:
        scan_result = _call_full_scan(self.text_retriever, limit=self.full_scan_limit)
        if scan_result.error:
            return {"available": False, "limit": self.full_scan_limit, "scanned_chunks": 0, "error": scan_result.error}
        items: list[EvidenceItem] = []
        for raw in _as_items(scan_result.raw):
            item = _normalize_text_evidence(raw, rank=run.next_text_rank + len(items))
            item.source_type = "text_full_scan"
            item.metadata["retrieval_path"] = "full_scan"
            items.append(item)
        run.next_text_rank += len(items)
        run.text_evidence.extend(items)
        run.full_scan_evidence.extend(items)
        return {"available": bool(items), "limit": self.full_scan_limit, "scanned_chunks": len(items)}

    def _add_global_context(self, question: str, run: _EvidenceRun) -> dict[str, Any]:
        if self.global_searcher is None:
            return {"available": False, "partial_answer_count": 0}
        try:
            result = _call_global_search(self.global_searcher, question)
        except Exception as exc:  # noqa: BLE001
            return {"available": False, "partial_answer_count": 0, "error": f"{exc.__class__.__name__}: {exc}"}
        partial_answers = getattr(result, "partial_answers", []) or []
        if partial_answers:
            run.global_context = _format_global_context(result)
            global_items = _global_source_evidence_items(result)
            for offset, item in enumerate(global_items, start=run.next_graph_rank):
                item.citation_id = f"C{offset}"
                item.rank = offset
            run.next_graph_rank += len(global_items)
            run.graph_evidence.extend(global_items)
            run.global_source_evidence.extend(global_items)
        return {
            "available": True,
            "partial_answer_count": len(partial_answers),
            "communities_searched": int(getattr(result, "communities_searched", 0) or 0),
            "communities_relevant": int(getattr(result, "communities_relevant", 0) or 0),
        }

    def _finalize(
        self,
        task_spec: TaskSpec,
        *,
        run: _EvidenceRun,
        steps: list[dict[str, Any]],
        context_only: bool,
        artifacts: dict[str, Any],
        coverage_report: dict[str, Any] | None = None,
        comparison_table: list[dict[str, Any]] | None = None,
    ) -> AdvancedQueryExecutionResult:
        context = _build_advanced_context(
            task_spec,
            run=run,
            steps=steps,
            comparison_table=comparison_table or artifacts.get("comparison_table") or [],
        )
        citations = [item.to_dict() for item in [*run.text_evidence, *run.graph_evidence]]
        prompt = None
        answer = None
        if not context_only:
            prompt = self.prompt_builder(task_spec, context, citations, artifacts)
            answer = _call_llm(self.llm, prompt, task_spec=task_spec.to_dict(), context=context, citations=citations)
        return AdvancedQueryExecutionResult(
            question=task_spec.original_question,
            answer=answer,
            context=context,
            citations=citations,
            evidence=citations,
            context_only=context_only,
            prompt=prompt,
            task_spec=task_spec.to_dict(),
            advanced_mode=task_spec.route.value,
            steps=steps,
            coverage_report=coverage_report or artifacts.get("coverage_report") or _coverage_report(steps),
            comparison_table=comparison_table or artifacts.get("comparison_table") or [],
        )


@dataclass(slots=True)
class _EvidenceBatch:
    text_evidence: list[EvidenceItem] = field(default_factory=list)
    graph_evidence: list[EvidenceItem] = field(default_factory=list)


@dataclass(slots=True)
class _EvidenceRun:
    question: str
    text_evidence: list[EvidenceItem] = field(default_factory=list)
    graph_evidence: list[EvidenceItem] = field(default_factory=list)
    full_scan_evidence: list[EvidenceItem] = field(default_factory=list)
    global_source_evidence: list[EvidenceItem] = field(default_factory=list)
    global_context: str = ""
    next_text_rank: int = 1
    next_graph_rank: int = 1


@dataclass(slots=True)
class _FullScanResult:
    raw: Any = None
    error: str | None = None


def build_advanced_prompt(
    task_spec: TaskSpec,
    context: str,
    citations: list[dict[str, Any]],
    artifacts: dict[str, Any],
) -> str:
    citation_ids = ", ".join(citation["id"] for citation in citations) or "none"
    return f"""You are an advanced RAG / GraphRAG synthesis assistant.

Use only the retrieved evidence. If evidence is missing for a planned step, say that directly.
Preserve citation IDs such as [T1], [G1], and [C1].

Advanced mode: {task_spec.route.value}
Available citation IDs: {citation_ids}

TaskSpec:
{json.dumps(task_spec.to_dict(), ensure_ascii=False, indent=2)}

Execution artifacts:
{json.dumps(artifacts, ensure_ascii=False, indent=2)}

Retrieved context:
{context}

Answer:
"""


def _build_advanced_context(
    task_spec: TaskSpec,
    *,
    run: _EvidenceRun,
    steps: list[dict[str, Any]],
    comparison_table: list[dict[str, Any]],
) -> str:
    sections = [
        build_context(task_spec.original_question, run.text_evidence, run.graph_evidence, run.global_context),
        "## Advanced execution plan",
        json.dumps(steps, ensure_ascii=False, indent=2),
    ]
    if comparison_table:
        sections.append("## Comparison table draft")
        sections.append(_comparison_markdown(comparison_table))
    if run.full_scan_evidence:
        sections.append("## Full-corpus scan sample")
        sections.append(
            "\n".join(
                f"[{item.citation_id}] {item.source or 'unknown source'}\n{item.text}"
                for item in run.full_scan_evidence
            )
        )
    return "\n\n".join(sections)


def _safe_retrieve_text(retriever: Any, query: str, top_k: int, start_rank: int) -> list[EvidenceItem]:
    if retriever is None:
        return []
    raw = _call_retriever(retriever, query, top_k)
    return [
        _normalize_text_evidence(item, rank=start_rank + offset)
        for offset, item in enumerate(_as_items(raw))
    ]


def _safe_retrieve_graph(retriever: Any, query: str, top_k: int, start_rank: int) -> list[EvidenceItem]:
    if retriever is None:
        return []
    raw = _call_retriever(retriever, query, top_k)
    return [
        _normalize_graph_evidence(item, rank=start_rank + offset)
        for offset, item in enumerate(_as_items(raw))
    ]


def _call_full_scan(retriever: Any, *, limit: int) -> _FullScanResult:
    if retriever is None:
        return _FullScanResult(error="text retriever unavailable")
    for method_name in ("scan_all", "all_documents", "iter_documents", "list_documents"):
        method = getattr(retriever, method_name, None)
        if callable(method):
            try:
                return _FullScanResult(raw=_call_scan_method(method, limit=limit))
            except Exception as exc:  # noqa: BLE001
                return _FullScanResult(error=f"{exc.__class__.__name__}: {exc}")
    return _FullScanResult(error="text retriever does not expose scan_all/all_documents")


def _call_scan_method(method: Callable[..., Any], *, limit: int) -> Any:
    try:
        signature = inspect.signature(method)
    except (TypeError, ValueError):
        return method(limit=limit)
    params = signature.parameters
    if any(param.kind == inspect.Parameter.VAR_KEYWORD for param in params.values()) or "limit" in params:
        return method(limit=limit)
    if "top_k" in params:
        return method(top_k=limit)
    if "count" in params:
        return method(count=limit)
    positional = [
        param
        for param in params.values()
        if param.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    if positional:
        return method(limit)
    return method()


def _call_global_search(global_searcher: Any, question: str) -> Any:
    method = getattr(global_searcher, "search", None)
    if not callable(method):
        raise TypeError("global_searcher must expose search(question, context_only=True)")
    try:
        signature = inspect.signature(method)
    except (TypeError, ValueError):
        return method(question, context_only=True)
    if "context_only" in signature.parameters or any(
        param.kind == inspect.Parameter.VAR_KEYWORD for param in signature.parameters.values()
    ):
        return method(question, context_only=True)
    return method(question)


def _step_payload(
    *,
    index: int,
    query: str,
    step_type: str,
    batch: _EvidenceBatch,
    obj: str | None = None,
) -> dict[str, Any]:
    text_ids = [item.citation_id for item in batch.text_evidence]
    graph_ids = [item.citation_id for item in batch.graph_evidence]
    payload: dict[str, Any] = {
        "index": index,
        "type": step_type,
        "query": query,
        "text_citations": text_ids,
        "graph_citations": graph_ids,
        "citations": [*text_ids, *graph_ids],
        "evidence_count": len(text_ids) + len(graph_ids),
    }
    if obj is not None:
        payload["object"] = obj
    return payload


def _coverage_report(
    steps: list[dict[str, Any]],
    *,
    object_count: int = 0,
    full_scan: dict[str, Any] | None = None,
    global_search: dict[str, Any] | None = None,
) -> dict[str, Any]:
    missing_queries = [step["query"] for step in steps if int(step.get("evidence_count") or 0) == 0]
    return {
        "planned_queries": len(steps),
        "answered_queries": len(steps) - len(missing_queries),
        "missing_queries": missing_queries,
        "object_count": object_count,
        "evidence_count": sum(int(step.get("evidence_count") or 0) for step in steps),
        "full_scan": full_scan or {"available": False, "scanned_chunks": 0},
        "global_search": global_search or {"available": False, "partial_answer_count": 0},
    }


def _object_query(obj: str, task_spec: TaskSpec) -> str:
    keywords = [kw for kw in task_spec.high_level_keywords if kw and kw != obj]
    parts = [obj, *keywords[:4]]
    return " ".join(part for part in parts if part).strip() or task_spec.original_question


def _fallback_objects(task_spec: TaskSpec) -> list[str]:
    candidates = [*task_spec.low_level_keywords[:4], *task_spec.high_level_keywords[:4]]
    seen: set[str] = set()
    objects: list[str] = []
    for candidate in candidates:
        text = str(candidate or "").strip()
        if text and text not in seen:
            seen.add(text)
            objects.append(text)
    return objects or [task_spec.rewritten_question or task_spec.original_question]


def _default_comprehensive_queries(task_spec: TaskSpec) -> list[str]:
    base = task_spec.rewritten_question or task_spec.original_question
    targets = task_spec.objects or task_spec.high_level_keywords or [base]
    target = targets[0]
    return [
        f"{target} main categories",
        f"{target} causes and impacts",
        f"{target} mitigation measures and evidence",
        f"{target} uncovered sources or missing evidence",
    ]


def _join_key_evidence(items: list[EvidenceItem], *, max_items: int = 2, max_chars: int = 220) -> str:
    snippets = [item.text for item in items if item.text][:max_items]
    text = " / ".join(snippets)
    if len(text) > max_chars:
        return text[: max_chars - 3].rstrip() + "..."
    return text


def _comparison_markdown(rows: list[dict[str, Any]]) -> str:
    lines = ["| Object | Evidence count | Key evidence | Citations |", "|---|---:|---|---|"]
    for row in rows:
        citations = ", ".join(row.get("citations") or [])
        lines.append(
            "| {object} | {count} | {evidence} | {citations} |".format(
                object=_escape_table_cell(row.get("object")),
                count=int(row.get("evidence_count") or 0),
                evidence=_escape_table_cell(row.get("key_evidence")),
                citations=_escape_table_cell(citations),
            )
        )
    return "\n".join(lines)


def _escape_table_cell(value: Any) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ").strip()
