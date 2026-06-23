"""Run promoted GraphRAG triage cases as a regression gate."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from .harness import EvaluationThresholds, RAGEvaluationCase, RAGEvaluationHarness

REPO_ROOT = Path(__file__).resolve().parents[1]
CONSOLE_SRC = REPO_ROOT / "api_server" / "current_console" / "chroma_rag_poc" / "src"


class LocalChromaRegressionRag:
    """Small evaluation adapter that runs promoted cases against the local Chroma pipeline."""

    def __init__(
        self,
        *,
        persist_dir: str | Path,
        collection_name: str = "",
        top_k: int = 5,
        backend: str | None = None,
        model_name: str | None = None,
        reranker: str | None = None,
    ) -> None:
        self.persist_dir = Path(persist_dir)
        self.collection_name = collection_name.strip()
        self.top_k = top_k
        self.backend = backend
        self.model_name = model_name
        self.reranker = reranker

    def query(self, question: str) -> dict[str, Any]:
        return self._query(question, filters=None)

    def query_case(self, case: dict[str, Any]) -> dict[str, Any]:
        source_scope = str(case.get("source_scope") or "").strip()
        filters = None
        if source_scope and source_scope.lower().endswith((".txt", ".json", ".jsonl", ".md", ".pdf", ".docx")):
            filters = {"field": "meta.source_file", "operator": "==", "value": source_scope}
        return self._query(str(case.get("question") or ""), filters=filters)

    def _query(self, question: str, *, filters: dict[str, Any] | None) -> dict[str, Any]:
        query_collection, get_all_stats = _load_console_pipeline()
        collection_name = self.collection_name or _resolve_first_nonempty_collection(
            get_all_stats,
            persist_dir=self.persist_dir,
        )
        if not collection_name:
            raise RuntimeError(f"No non-empty Chroma collection found at {self.persist_dir}")

        search = query_collection(
            query_text=question,
            persist_dir=self.persist_dir,
            collection_name=collection_name,
            top_k=self.top_k,
            backend=self.backend,
            model_name=self.model_name,
            reranker=self.reranker,
            filters=filters,
        )
        hits = list(search.get("results") or [])
        context = "\n\n".join(str(hit.get("text") or "") for hit in hits)
        citations = []
        for hit in hits:
            metadata = hit.get("metadata") or {}
            citations.append(
                {
                    "source": metadata.get("source_file") or metadata.get("filename") or collection_name,
                    "text": hit.get("text") or "",
                    "metadata": metadata,
                }
            )
        return {
            "answer": context,
            "retrieval_results": hits,
            "citations": citations,
            "collection": collection_name,
            "embedding_backend": search.get("embedding_backend"),
            "embedding_model": search.get("embedding_model"),
        }


def load_graphrag_triage_regression_cases(dataset_path: str | Path) -> list[RAGEvaluationCase]:
    path = Path(dataset_path)
    if not path.exists():
        return []
    cases: list[RAGEvaluationCase] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise ValueError(f"{path}:{line_number} must contain a JSON object")
        cases.append(
            RAGEvaluationCase(
                id=str(payload.get("id") or f"graphrag-triage-{line_number}"),
                question=str(payload.get("question") or ""),
                reference_answer=str(payload.get("reference_answer") or ""),
                expected_evidence_keywords=[str(item) for item in payload.get("expected_evidence_keywords") or []],
                task_type=str(payload.get("task_type") or "graphrag_triage"),
                source_scope=payload.get("source_scope") or "graphrag",
                grading_notes=str(payload.get("grading_notes") or ""),
                expected_modes=[str(item) for item in payload.get("expected_modes") or []],
            )
        )
    return cases


def run_graphrag_triage_regression(
    *,
    rag_system: Any,
    dataset_path: str | Path,
    report_dir: str | Path,
    thresholds: EvaluationThresholds | None = None,
    top_k: int = 5,
) -> dict[str, Any]:
    cases = load_graphrag_triage_regression_cases(dataset_path)
    if not cases:
        return {
            "status": "skipped",
            "gate_status": "pass",
            "case_count": 0,
            "dataset_path": str(dataset_path),
            "reason": "no promoted GraphRAG triage regression cases",
        }

    harness = RAGEvaluationHarness(
        rag_system,
        thresholds=thresholds
        or EvaluationThresholds(
            min_keyword_recall_at_k=0.7,
            min_answer_completeness=0.7,
            max_missing_citation_rate=0.2,
            max_medium_or_high_risk_rate=0.4,
            max_no_result_rate=0.05,
        ),
        top_k=top_k,
    )
    report = harness.run(cases, run_name="graphrag_triage_regression")
    paths = report.save(report_dir)
    return {
        "status": report.gate_status,
        "gate_status": report.gate_status,
        "case_count": len(cases),
        "dataset_path": str(dataset_path),
        "reports": {name: str(path) for name, path in paths.items()},
        "gate_failures": report.gate_failures,
        "failure_cases": report.failure_cases,
    }


def _load_console_pipeline() -> tuple[Any, Any]:
    if str(CONSOLE_SRC) not in sys.path:
        sys.path.insert(0, str(CONSOLE_SRC))
    from chroma_rag_poc.pipeline import get_all_stats, query_collection

    return query_collection, get_all_stats


def _resolve_first_nonempty_collection(get_all_stats: Any, *, persist_dir: Path) -> str | None:
    stats = get_all_stats(persist_dir=persist_dir)
    for collection in stats.get("collections", []):
        if int(collection.get("count") or 0) > 0:
            return str(collection.get("name") or "")
    return None
