"""Adapters for turning downloaded external RAG benchmarks into local eval cases."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .harness import RAGEvaluationCase


@dataclass(frozen=True, slots=True)
class ExternalBenchmarkSuite:
    name: str
    payloads: list[tuple[str, bytes]]
    cases: list[RAGEvaluationCase]
    source_path: Path
    notes: str = ""


_STOP_WORDS = {
    "a",
    "after",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "both",
    "by",
    "can",
    "for",
    "from",
    "has",
    "have",
    "if",
    "in",
    "into",
    "is",
    "it",
    "may",
    "most",
    "not",
    "of",
    "on",
    "or",
    "that",
    "the",
    "their",
    "this",
    "to",
    "was",
    "were",
    "what",
    "when",
    "which",
    "while",
    "who",
    "will",
    "with",
}


def build_legal_rag_bench_suite(root: str | Path, *, case_limit: int | None = None) -> ExternalBenchmarkSuite:
    root_path = Path(root)
    corpus_records = _read_jsonl(root_path / "corpus.jsonl")
    qa_records = _limited(_read_jsonl(root_path / "qa.jsonl"), case_limit)
    corpus_by_id = {str(record.get("id")): record for record in corpus_records}

    corpus_text = "\n\n".join(_format_legal_passage(record) for record in corpus_records)
    payloads = [("legal-rag-bench-corpus.txt", corpus_text.encode("utf-8"))]

    cases: list[RAGEvaluationCase] = []
    for index, record in enumerate(qa_records, start=1):
        passage_id = str(record.get("relevant_passage_id") or "").strip()
        passage = corpus_by_id.get(passage_id, {})
        evidence_texts = [
            str(passage.get("title") or ""),
            str(passage.get("text") or ""),
            str(record.get("answer") or ""),
        ]
        cases.append(
            RAGEvaluationCase(
                id=f"legal-{record.get('id') or index}",
                question=str(record.get("question") or "").strip(),
                reference_answer=str(record.get("answer") or "").strip(),
                expected_evidence_keywords=_evidence_keywords(evidence_texts, required=[passage_id]),
                task_type="legal_rag_qa",
                source_scope="legal-rag-bench",
                grading_notes=f"Relevant passage id: {passage_id}",
                expected_modes=["hybrid", "semantic", "keyword"],
            )
        )

    return ExternalBenchmarkSuite(
        name="legal-rag-bench",
        payloads=payloads,
        cases=cases,
        source_path=root_path,
        notes="Legal QA with gold answer and relevant passage id.",
    )


def build_graphrag_bench_suite(
    root: str | Path,
    *,
    domain: str,
    case_limit: int | None = None,
) -> ExternalBenchmarkSuite:
    root_path = Path(root)
    normalized_domain = domain.strip().lower()
    corpus_path = root_path / "Datasets" / "Corpus" / f"{normalized_domain}.json"
    questions_path = root_path / "Datasets" / "Questions" / f"{normalized_domain}_questions.json"
    corpus_records = json.loads(corpus_path.read_text(encoding="utf-8"))
    question_records = _limited(json.loads(questions_path.read_text(encoding="utf-8")), case_limit)

    payloads: list[tuple[str, bytes]] = []
    for index, record in enumerate(corpus_records, start=1):
        corpus_name = str(record.get("corpus_name") or f"{normalized_domain}-{index}")
        context = record.get("context")
        if not isinstance(context, str):
            context = json.dumps(context, ensure_ascii=False)
        text = f"CORPUS_NAME: {corpus_name}\nDOMAIN: {normalized_domain}\n\n{context}"
        payloads.append((f"graphrag-bench-{normalized_domain}-{_safe_filename(corpus_name)}.txt", text.encode("utf-8")))

    cases: list[RAGEvaluationCase] = []
    for index, record in enumerate(question_records, start=1):
        evidence_items = [str(item) for item in record.get("evidence") or [] if str(item).strip()]
        if record.get("evidence_relations"):
            evidence_items.append(str(record["evidence_relations"]))
        if record.get("evidence_triple"):
            evidence_items.extend(str(item) for item in record["evidence_triple"])
        answer = str(record.get("answer") or "").strip()
        case_id = str(record.get("id") or index)
        cases.append(
            RAGEvaluationCase(
                id=f"graphrag-{normalized_domain}-{case_id}",
                question=str(record.get("question") or "").strip(),
                reference_answer=answer,
                expected_evidence_keywords=_evidence_keywords([answer, *evidence_items]),
                task_type=str(record.get("question_type") or "graphrag_bench"),
                source_scope=str(record.get("source") or f"graphrag-bench-{normalized_domain}"),
                grading_notes="Gold evidence is supplied by GraphRAG-Bench.",
                expected_modes=["hybrid", "graph", "semantic"],
            )
        )

    return ExternalBenchmarkSuite(
        name=f"graphrag-bench-{normalized_domain}",
        payloads=payloads,
        cases=cases,
        source_path=root_path,
        notes="GraphRAG benchmark with answer and evidence fields.",
    )


def build_ragbench_suite(
    root: str | Path,
    *,
    dataset: str,
    split: str,
    case_limit: int | None = None,
) -> ExternalBenchmarkSuite:
    root_path = Path(root)
    dataset_name = dataset.strip().lower()
    split_name = split.strip().lower()
    dataset_dir = root_path / dataset_name
    matches = sorted(dataset_dir.glob(f"{split_name}-*.jsonl"))
    if not matches:
        raise FileNotFoundError(f"No RAGBench JSONL file found for {dataset_name}/{split_name} under {root_path}")
    records = _limited(_read_jsonl(matches[0]), case_limit)

    payloads: list[tuple[str, bytes]] = []
    cases: list[RAGEvaluationCase] = []
    for index, record in enumerate(records, start=1):
        record_id = str(record.get("id") or index)
        sentence_map = _ragbench_sentence_map(record)
        relevant_keys = [str(item) for item in record.get("all_relevant_sentence_keys") or []]
        relevant_texts = [sentence_map[key] for key in relevant_keys if key in sentence_map]
        response = str(record.get("response") or "").strip()
        payload_text = _format_ragbench_documents(record, sentence_map=sentence_map)
        source_name = f"ragbench-{dataset_name}-{split_name}-{_safe_filename(record_id)}.txt"
        payloads.append((source_name, payload_text.encode("utf-8")))
        cases.append(
            RAGEvaluationCase(
                id=f"ragbench-{dataset_name}-{split_name}-{record_id}",
                question=str(record.get("question") or "").strip(),
                reference_answer=response,
                expected_evidence_keywords=_evidence_keywords([response, *relevant_texts]),
                task_type=f"ragbench_{dataset_name}",
                source_scope=source_name,
                grading_notes=(
                    f"RAGBench support sentence ids: {', '.join(relevant_keys) or 'none'}; "
                    "support labels: "
                    f"relevance={record.get('relevance_score')}, "
                    f"utilization={record.get('utilization_score')}, "
                    f"completeness={record.get('completeness_score')}"
                ),
                expected_modes=["hybrid", "semantic"],
            )
        )

    return ExternalBenchmarkSuite(
        name=f"ragbench-{dataset_name}-{split_name}",
        payloads=payloads,
        cases=cases,
        source_path=matches[0],
        notes="RAGBench JSONL converted from Parquet, with sentence support annotations.",
    )


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{line_number} must contain a JSON object.")
        records.append(value)
    return records


def _limited(records: list[dict[str, Any]], limit: int | None) -> list[dict[str, Any]]:
    if limit is None or limit <= 0:
        return list(records)
    return list(records[:limit])


def _format_legal_passage(record: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"PASSAGE_ID: {record.get('id')}",
            f"TITLE: {record.get('title') or ''}",
            "TEXT:",
            str(record.get("text") or ""),
        ]
    )


def _ragbench_sentence_map(record: dict[str, Any]) -> dict[str, str]:
    sentence_map: dict[str, str] = {}
    for document_sentences in record.get("documents_sentences") or []:
        for item in document_sentences or []:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                sentence_map[str(item[0])] = str(item[1])
    return sentence_map


def _format_ragbench_documents(record: dict[str, Any], *, sentence_map: dict[str, str]) -> str:
    lines = [
        f"RAGBENCH_ID: {record.get('id')}",
        f"QUESTION: {record.get('question') or ''}",
    ]
    if sentence_map:
        lines.append("SENTENCES:")
        for sentence_id, sentence in sorted(sentence_map.items()):
            lines.append(f"SENTENCE_ID: {sentence_id}")
            lines.append(sentence)
    else:
        lines.append("DOCUMENTS:")
        for index, document in enumerate(record.get("documents") or []):
            lines.append(f"DOCUMENT_INDEX: {index}")
            lines.append(str(document))
    return "\n".join(lines)


def _evidence_keywords(texts: Iterable[str], *, required: Iterable[str] = (), max_keywords: int = 12) -> list[str]:
    keywords: list[str] = []
    for item in required:
        _append_keyword(keywords, item)
    for text in texts:
        for candidate in _keyword_candidates(str(text or "")):
            _append_keyword(keywords, candidate)
            if len(keywords) >= max_keywords:
                return keywords
    return keywords or ["evidence"]


def _keyword_candidates(text: str) -> list[str]:
    cleaned = re.sub(r"\([^)]{1,80}\)", " ", text)
    cleaned = re.sub(r"(?m)(^|\n)\s*#{0,6}\s*\d+(?:\.\d+)+\s+", r"\1", cleaned)
    tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9'’-]*", cleaned)
    if not tokens:
        return []

    candidates: list[str] = []
    meaningful_segments: list[list[str]] = []
    current: list[str] = []
    for token in tokens:
        normalized = token.strip("'’").casefold()
        if normalized in _STOP_WORDS:
            if current:
                meaningful_segments.append(current)
                current = []
            continue
        current.append(token.strip("'’"))
    if current:
        meaningful_segments.append(current)

    for segment in meaningful_segments:
        if 1 <= len(segment) <= 5:
            _append_candidate(candidates, segment)
        for size in (2, 3):
            for start in range(0, max(0, len(segment) - size + 1)):
                phrase_tokens = segment[start : start + size]
                if any(char.isdigit() for token in phrase_tokens for char in token) or size == 2:
                    _append_candidate(candidates, phrase_tokens)
        for token in segment:
            if len(token) >= 4 or token[:1].isupper() or any(char.isdigit() for char in token):
                _append_candidate(candidates, [token])

    return candidates


def _append_candidate(candidates: list[str], tokens: list[str]) -> None:
    normalized_tokens = _normalize_candidate_tokens(tokens)
    if normalized_tokens:
        candidates.append(" ".join(normalized_tokens))


def _normalize_candidate_tokens(tokens: list[str]) -> list[str]:
    cleaned = [token.strip("'鈥?") for token in tokens if token.strip("'鈥?")]
    if len(cleaned) > 1:
        cleaned = [
            token
            for token in cleaned
            if not (token.isdigit() and int(token) < 10)
        ]
    if not cleaned:
        return []

    has_large_number = any(token.isdigit() and int(token) >= 10 for token in cleaned)
    has_id_like_token = any(any(char.isdigit() for char in token) and any(char.isalpha() for char in token) for token in cleaned)
    meaningful_alpha = [
        token
        for token in cleaned
        if any(char.isalpha() for char in token)
        and token.casefold() not in _STOP_WORDS
        and (len(token) >= 4 or token[:1].isupper())
    ]
    if not meaningful_alpha and not has_large_number and not has_id_like_token:
        return []
    if len(cleaned) == 1:
        token = cleaned[0]
        if token.isdigit() and int(token) < 10:
            return []
        if token.casefold() in _STOP_WORDS:
            return []
    return cleaned


def _append_keyword(keywords: list[str], value: Any) -> None:
    text = str(value or "").strip().strip(".。,:; ")
    if not text:
        return
    if len(text) > 90:
        return
    normalized = text.casefold()
    if normalized in {item.casefold() for item in keywords}:
        return
    keywords.append(text)


def _safe_filename(value: str) -> str:
    safe = re.sub(r"[^0-9A-Za-z_.-]+", "_", value.strip())
    return safe.strip("._-") or "item"
