from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8")


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
DEFAULT_DATASET = REPO_ROOT / "evaluation" / "system_eval_questions.jsonl"
DEFAULT_REPORT_DIR = REPO_ROOT / "evaluation" / "reports"
DEFAULT_DOCS_SUMMARY = (
    REPO_ROOT
    / "docs"
    / "project_deliverables"
    / "06_汇报材料_发群和组会"
    / "第三天检索评测结果.md"
)

TOKEN_RE = re.compile(r"[A-Za-z0-9_.-]+|[\u4e00-\u9fff]+", re.UNICODE)
PAGE_MARK_RE = re.compile(r"(?:^|\n)\s*(?:第\s*)?(\d{1,4})\s*(?:页|/|\n)")
METHODS = ("keyword", "dense_hashing", "hybrid_rrf")


@dataclass(slots=True)
class CorpusChunk:
    chunk_id: str
    text: str
    source_file: str
    source_scope: str
    chunk_index: int


@dataclass(slots=True)
class ScoredHit:
    chunk: CorpusChunk
    score: float
    component_scores: dict[str, float]


@dataclass(slots=True)
class RetrievalIndex:
    chunks: list[CorpusChunk]
    chunk_tokens: list[list[str]]
    token_counters: list[Counter[str]]
    doc_freq: Counter[str]
    avg_len: float
    dense_vectors: list[list[float]]


def compact_text(value: Any, limit: int = 240) -> str:
    text = "" if value is None else str(value)
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "..."


def normalize_text(value: Any) -> str:
    return " ".join(str(value or "").lower().split())


def tokenize(text: str) -> list[str]:
    """Tokenize mixed Chinese/English text with char n-grams for Chinese spans."""
    tokens: list[str] = []
    for match in TOKEN_RE.finditer(normalize_text(text)):
        token = match.group(0)
        if not token:
            continue
        if re.fullmatch(r"[\u4e00-\u9fff]+", token):
            if len(token) == 1:
                tokens.append(token)
                continue
            tokens.extend(token[index : index + 2] for index in range(len(token) - 1))
            if len(token) >= 3:
                tokens.extend(token[index : index + 3] for index in range(len(token) - 2))
        else:
            tokens.append(token)
    return tokens


def stable_id(*parts: str) -> str:
    digest = hashlib.sha1("\n".join(parts).encode("utf-8")).hexdigest()
    return digest[:16]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            records.append(json.loads(stripped))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSONL at {path}:{line_number}: {exc}") from exc
    return records


def iter_source_files() -> list[tuple[Path, str]]:
    sources: list[tuple[Path, str]] = []

    ocr_root = REPO_ROOT / "data_pipeline" / "ocr_processing_stages" / "ocr_text_cleaned" / "tsinghua_gas_turbine_books"
    if ocr_root.exists():
        for path in sorted(ocr_root.glob("*/document.txt")):
            sources.append((path, "ocr_text_cleaned"))

    direct_files = [
        (REPO_ROOT / "README.md", "project_overview"),
        (REPO_ROOT / "TECH_STACK.md", "project_overview"),
        (REPO_ROOT / "docs" / "project_deliverables" / "RAG技术架构与背景资料梳理.md", "rag_system_design_docs"),
        (
            REPO_ROOT
            / "docs"
            / "project_deliverables"
            / "06_汇报材料_发群和组会"
            / "组会展示要点.md",
            "kg_poc_outputs",
        ),
        (REPO_ROOT / "data_pipeline" / "reports" / "ocr_quality_audit.md", "ocr_quality_reports"),
        (
            REPO_ROOT / "data_pipeline" / "reports" / "public_books_json_audit_20260522.md",
            "public_books_json_audit_reports",
        ),
        (
            REPO_ROOT / "data_pipeline" / "datasets" / "goldwind_decoded" / "analysis_report.md",
            "goldwind_decoded_reports",
        ),
        (
            REPO_ROOT / "RAG_JSON_Files" / "storage_layer" / "runtime" / "ocr_enriched_rag_chroma" / "build_summary.json",
            "rag_build_summary",
        ),
        (
            REPO_ROOT
            / "RAG_JSON_Files"
            / "storage_layer"
            / "runtime"
            / "representative_rag_chroma"
            / "build_summary.json",
            "rag_build_summary",
        ),
        (REPO_ROOT / "evaluation" / "README.md", "evaluation_framework"),
        (REPO_ROOT / "evaluation" / "metrics.py", "evaluation_framework"),
        (REPO_ROOT / "scripts" / "run_system_evaluation.py", "evaluation_framework"),
    ]
    for path, scope in direct_files:
        if path.exists():
            sources.append((path, scope))

    reports_root = REPO_ROOT / "data_pipeline" / "reports"
    if reports_root.exists():
        for path in sorted(reports_root.glob("*.md")):
            if path.name not in {item[0].name for item in direct_files}:
                sources.append((path, "data_pipeline_reports"))

    kg_poc_root = REPO_ROOT / "kg_pipeline" / "poc"
    if kg_poc_root.exists():
        for path in sorted(kg_poc_root.rglob("*")):
            if path.suffix.lower() in {".md", ".csv", ".json", ".html", ".svg"} and path.is_file():
                if path.stat().st_size <= 1_500_000:
                    sources.append((path, "kg_poc_outputs"))

    return sources


def read_source_text(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="ignore")
    if path.suffix.lower() == ".json":
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return text
        return json.dumps(parsed, ensure_ascii=False, indent=2)
    return text


def split_text(text: str, *, chunk_size: int, overlap: int) -> list[str]:
    normalized = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    if not normalized:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(len(normalized), start + chunk_size)
        chunk = normalized[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(normalized):
            break
        start = max(0, end - overlap)
    return chunks


def build_corpus(*, chunk_size: int, overlap: int, max_chunks: int | None = None) -> list[CorpusChunk]:
    chunks: list[CorpusChunk] = []
    for path, scope in iter_source_files():
        try:
            text = read_source_text(path)
        except OSError:
            continue
        relative = str(path.relative_to(REPO_ROOT))
        for index, chunk_text in enumerate(split_text(text, chunk_size=chunk_size, overlap=overlap), start=1):
            chunk_id = stable_id(relative, str(index), chunk_text[:120])
            chunks.append(
                CorpusChunk(
                    chunk_id=chunk_id,
                    text=chunk_text,
                    source_file=relative,
                    source_scope=scope,
                    chunk_index=index,
                )
            )
            if max_chunks is not None and len(chunks) >= max_chunks:
                return chunks
    return chunks


def build_chunk_tokens(chunks: list[CorpusChunk]) -> list[list[str]]:
    return [tokenize(chunk.text) for chunk in chunks]


def build_retrieval_index(chunks: list[CorpusChunk], *, dense_dimension: int) -> RetrievalIndex:
    chunk_tokens = build_chunk_tokens(chunks)
    token_counters = [Counter(tokens) for tokens in chunk_tokens]
    doc_freq: Counter[str] = Counter()
    for tokens in chunk_tokens:
        doc_freq.update(set(tokens))
    avg_len = sum(len(tokens) for tokens in chunk_tokens) / max(len(chunk_tokens), 1)
    dense_vectors = [hash_vector(tokens, dense_dimension) for tokens in chunk_tokens]
    return RetrievalIndex(
        chunks=chunks,
        chunk_tokens=chunk_tokens,
        token_counters=token_counters,
        doc_freq=doc_freq,
        avg_len=avg_len,
        dense_vectors=dense_vectors,
    )


def keyword_scores(query: str, index: RetrievalIndex) -> list[ScoredHit]:
    query_tokens = tokenize(query)
    if not query_tokens:
        return []
    query_counter = Counter(query_tokens)
    total_docs = len(index.chunks)
    scored: list[ScoredHit] = []
    k1 = 1.5
    b = 0.75
    for chunk, tokens, token_counter in zip(index.chunks, index.chunk_tokens, index.token_counters):
        if not tokens:
            continue
        score = 0.0
        matched = 0
        for token, query_count in query_counter.items():
            freq = token_counter.get(token, 0)
            if not freq:
                continue
            matched += 1
            idf = math.log(1 + (total_docs - index.doc_freq[token] + 0.5) / (index.doc_freq[token] + 0.5))
            denom = freq + k1 * (1 - b + b * len(tokens) / max(index.avg_len, 1))
            score += idf * (freq * (k1 + 1) / max(denom, 1e-9)) * query_count
        if score <= 0:
            continue
        coverage = matched / max(len(query_counter), 1)
        score *= 1.0 + coverage
        scored.append(ScoredHit(chunk=chunk, score=score, component_scores={"keyword": score}))

    scored.sort(key=lambda hit: (-hit.score, hit.chunk.chunk_id))
    return scored


def hash_vector(tokens: list[str], dimension: int) -> list[float]:
    vector = [0.0] * dimension
    for token in tokens:
        digest = hashlib.md5(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], byteorder="little") % dimension
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[index] += sign * (1.0 + min(len(token), 8) / 8)
    norm = math.sqrt(sum(value * value for value in vector))
    if norm <= 0:
        return vector
    return [value / norm for value in vector]


def dot(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right))


def dense_scores(query: str, index: RetrievalIndex) -> list[ScoredHit]:
    dimension = len(index.dense_vectors[0]) if index.dense_vectors else 384
    query_vector = hash_vector(tokenize(query), dimension)
    if not any(query_vector):
        return []
    scored: list[ScoredHit] = []
    for chunk, chunk_vector in zip(index.chunks, index.dense_vectors):
        score = dot(query_vector, chunk_vector)
        if score <= 0:
            continue
        scored.append(ScoredHit(chunk=chunk, score=score, component_scores={"dense_hashing": score}))
    scored.sort(key=lambda hit: (-hit.score, hit.chunk.chunk_id))
    return scored


def reciprocal_rank_fusion(
    rankings: list[tuple[str, list[ScoredHit]]],
    *,
    rrf_k: int = 60,
) -> list[ScoredHit]:
    merged: dict[str, ScoredHit] = {}
    for method_name, hits in rankings:
        for rank, hit in enumerate(hits, start=1):
            fused_score = 1.0 / (rrf_k + rank)
            if hit.chunk.chunk_id not in merged:
                merged[hit.chunk.chunk_id] = ScoredHit(
                    chunk=hit.chunk,
                    score=0.0,
                    component_scores={},
                )
            merged_hit = merged[hit.chunk.chunk_id]
            merged_hit.score += fused_score
            merged_hit.component_scores[method_name] = fused_score
    results = list(merged.values())
    results.sort(key=lambda hit: (-hit.score, hit.chunk.chunk_id))
    return results


def hit_to_output(hit: ScoredHit, rank: int) -> dict[str, Any]:
    return {
        "rank": rank,
        "id": hit.chunk.chunk_id,
        "score": round(hit.score, 6),
        "source_file": hit.chunk.source_file,
        "source_scope": hit.chunk.source_scope,
        "chunk_index": hit.chunk.chunk_index,
        "component_scores": {key: round(value, 6) for key, value in hit.component_scores.items()},
        "text": hit.chunk.text,
        "preview": compact_text(hit.chunk.text, 300),
    }


def run_method(
    method: str,
    questions: list[dict[str, Any]],
    index: RetrievalIndex,
    *,
    top_k: int,
) -> list[dict[str, Any]]:
    outputs: list[dict[str, Any]] = []
    for question in questions:
        query = str(question["question"])
        keyword_hits = keyword_scores(query, index)
        dense_hits = dense_scores(query, index)
        if method == "keyword":
            hits = keyword_hits
        elif method == "dense_hashing":
            hits = dense_hits
        elif method == "hybrid_rrf":
            hits = reciprocal_rank_fusion(
                [
                    ("keyword", keyword_hits[: max(top_k * 12, 60)]),
                    ("dense_hashing", dense_hits[: max(top_k * 12, 60)]),
                ]
            )
        else:
            raise ValueError(f"Unsupported method: {method}")

        outputs.append(
            {
                "id": question["id"],
                "question": query,
                "method": method,
                "hits": [hit_to_output(hit, rank) for rank, hit in enumerate(hits[:top_k], start=1)],
            }
        )
    return outputs


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.write_text(
        "\n".join(json.dumps(record, ensure_ascii=False) for record in records).rstrip() + "\n",
        encoding="utf-8",
    )


def summarize_payload(method: str, payload: dict[str, Any]) -> dict[str, Any]:
    retrieval = payload["metrics"]["retrieval"]
    summary = payload["summary"]
    return {
        "method": method,
        "total_questions": summary["total_questions"],
        "matched_outputs": summary["matched_outputs"],
        "question_recall_at_k": retrieval["question_recall_at_k"],
        "keyword_recall_at_k": retrieval["keyword_recall_at_k"],
        "avg_retrieval_keyword_coverage": retrieval["average_keyword_coverage"],
        "zero_hit_questions": sum(1 for result in payload["results"] if not result["retrieved_count_at_k"]),
        "strong_questions": sum(1 for result in payload["results"] if result["retrieval_keyword_coverage"] >= 0.75),
        "weak_questions": sum(
            1 for result in payload["results"] if 0 < result["retrieval_keyword_coverage"] < 0.75
        ),
        "missed_questions": sum(1 for result in payload["results"] if result["retrieval_keyword_coverage"] == 0),
    }


def pick_cases(method_payloads: dict[str, dict[str, Any]], preferred_method: str) -> dict[str, list[dict[str, Any]]]:
    payload = method_payloads[preferred_method]
    results = payload["results"]
    successes = [
        result for result in results if result["retrieval_keyword_coverage"] >= 0.75 and result["retrieved_count_at_k"]
    ][:3]
    failures = [
        result for result in results if result["retrieval_keyword_coverage"] == 0 or not result["retrieved_count_at_k"]
    ][:3]
    partial = [
        result
        for result in results
        if 0 < result["retrieval_keyword_coverage"] < 0.75 and result["retrieved_count_at_k"]
    ][:3]
    return {"successes": successes, "partial": partial, "failures": failures}


def markdown_cell(value: Any) -> str:
    if isinstance(value, float):
        text = f"{value:.6f}"
    else:
        text = compact_text(value, 160)
    return text.replace("|", "\\|").replace("\n", " ")


def write_comparison_report(
    path: Path,
    *,
    generated_at: str,
    corpus_count: int,
    chunk_size: int,
    overlap: int,
    top_k: int,
    summaries: list[dict[str, Any]],
    cases: dict[str, list[dict[str, Any]]],
    report_paths: dict[str, dict[str, str]],
    best_method: str,
) -> None:
    lines = [
        "# Day 3 Retrieval Baseline Comparison",
        "",
        f"- Generated at: {generated_at}",
        f"- Corpus chunks: {corpus_count}",
        f"- Chunk size / overlap: {chunk_size} / {overlap}",
        f"- Top K: {top_k}",
        "",
        "## Method Summary",
        "",
        "| Method | Questions | Matched outputs | Question recall@K | Keyword recall@K | Avg keyword coverage | Strong | Weak | Missed | Zero-hit |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in summaries:
        lines.append(
            "| "
            + " | ".join(
                [
                    markdown_cell(item["method"]),
                    markdown_cell(item["total_questions"]),
                    markdown_cell(item["matched_outputs"]),
                    markdown_cell(item["question_recall_at_k"]),
                    markdown_cell(item["keyword_recall_at_k"]),
                    markdown_cell(item["avg_retrieval_keyword_coverage"]),
                    markdown_cell(item["strong_questions"]),
                    markdown_cell(item["weak_questions"]),
                    markdown_cell(item["missed_questions"]),
                    markdown_cell(item["zero_hit_questions"]),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- `keyword` is the sparse baseline. It is good at explicit terms such as equipment names, fields, and report numbers.",
            "- `dense_hashing` is an offline deterministic dense-style baseline. It does not represent final embedding quality, but it gives a reproducible semantic-ish baseline without model downloads.",
            "- `hybrid_rrf` fuses keyword and dense hashing with reciprocal rank fusion.",
            f"- Best Day 3 baseline by average keyword coverage: `{best_method}`.",
            "",
            "## Case Picks",
            "",
        ]
    )

    for title, records in (
        ("Successes", cases["successes"]),
        ("Partial", cases["partial"]),
        ("Failures", cases["failures"]),
    ):
        lines.extend(
            [
                f"### {title}",
                "",
                "| ID | Type | Question | Retrieval coverage | Notes |",
                "| --- | --- | --- | ---: | --- |",
            ]
        )
        if not records:
            lines.append("| - | - | - | - | - |")
        for result in records:
            lines.append(
                "| "
                + " | ".join(
                    [
                        markdown_cell(result["id"]),
                        markdown_cell(result["task_type"]),
                        markdown_cell(result["question"]),
                        markdown_cell(result["retrieval_keyword_coverage"]),
                        markdown_cell(result["grading_notes"]),
                    ]
                )
                + " |"
            )
        lines.append("")

    lines.extend(["## Generated Files", ""])
    for method, paths in report_paths.items():
        lines.append(f"- {method} outputs: `{paths['outputs']}`")
        lines.append(f"- {method} report JSON: `{paths['report_json']}`")
        lines.append(f"- {method} report Markdown: `{paths['report_md']}`")

    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def write_presentation_summary(
    path: Path,
    comparison_path: Path,
    summaries: list[dict[str, Any]],
    *,
    question_count: int,
) -> None:
    best = max(summaries, key=lambda item: item["avg_retrieval_keyword_coverage"] or 0)
    lines = [
        "# 第三天检索评测结果",
        "",
        "## 一句话结论",
        "",
        (
            f"已基于 {question_count} 题评测集完成 keyword、dense_hashing、hybrid_rrf 三组离线检索 baseline；"
            f"当前推荐汇报使用 `{best['method']}` 作为第三天主结果，"
            f"平均关键词覆盖率为 {best['avg_retrieval_keyword_coverage']:.6f}。"
        ),
        "",
        "## 对比表",
        "",
        "| 方法 | question recall@K | keyword recall@K | 平均关键词覆盖率 | 强命中 | 弱命中 | 未命中 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in summaries:
        lines.append(
            "| "
            + " | ".join(
                [
                    markdown_cell(item["method"]),
                    markdown_cell(item["question_recall_at_k"]),
                    markdown_cell(item["keyword_recall_at_k"]),
                    markdown_cell(item["avg_retrieval_keyword_coverage"]),
                    markdown_cell(item["strong_questions"]),
                    markdown_cell(item["weak_questions"]),
                    markdown_cell(item["missed_questions"]),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## 汇报口径",
            "",
            "可以这样讲：",
            "",
            f"> 第三天我没有继续堆功能，而是把整理好的 {question_count} 题评测集接到检索 baseline 上。当前跑了关键词检索、离线哈希向量检索和 Hybrid RRF 三组方法，并用统一脚本统计 question recall、关键词覆盖率和未命中问题。这个结果可以作为后续替换更好 embedding、接入 reranker 和做失败案例分析的基线。",
            "",
            "## 详细报告",
            "",
            f"详见 `{comparison_path}`。",
        ]
    )
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Day 3 retrieval baselines for the system eval set.")
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET))
    parser.add_argument("--output-dir", default=str(DEFAULT_REPORT_DIR))
    parser.add_argument("--docs-summary", default=str(DEFAULT_DOCS_SUMMARY))
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--chunk-size", type=int, default=900)
    parser.add_argument("--overlap", type=int, default=120)
    parser.add_argument("--dense-dimension", type=int, default=384)
    parser.add_argument("--max-chunks", type=int, default=0, help="Optional corpus chunk cap for debugging.")
    args = parser.parse_args(argv)

    dataset_path = Path(args.dataset)
    if not dataset_path.is_absolute():
        dataset_path = REPO_ROOT / dataset_path
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = REPO_ROOT / output_dir
    docs_summary = Path(args.docs_summary)
    if not docs_summary.is_absolute():
        docs_summary = REPO_ROOT / docs_summary

    if args.top_k <= 0:
        raise ValueError("--top-k must be greater than 0.")
    if args.chunk_size <= args.overlap:
        raise ValueError("--chunk-size must be greater than --overlap.")

    questions = read_jsonl(dataset_path)
    chunks = build_corpus(
        chunk_size=args.chunk_size,
        overlap=args.overlap,
        max_chunks=args.max_chunks or None,
    )
    if not chunks:
        raise RuntimeError("No corpus chunks were built.")
    index = build_retrieval_index(chunks, dense_dimension=args.dense_dimension)

    from scripts.run_system_evaluation import evaluate_records, write_reports

    generated_at = datetime.now()
    stamp = generated_at.strftime("%Y%m%d_%H%M%S")
    output_dir.mkdir(parents=True, exist_ok=True)

    method_payloads: dict[str, dict[str, Any]] = {}
    report_paths: dict[str, dict[str, str]] = {}
    summaries: list[dict[str, Any]] = []

    for method in METHODS:
        outputs = run_method(
            method,
            questions,
            index,
            top_k=args.top_k,
        )
        outputs_path = output_dir / f"day3_retrieval_outputs_{method}_{stamp}.jsonl"
        write_jsonl(outputs_path, outputs)
        payload = evaluate_records(questions, outputs, top_k=args.top_k, retrieval_only=True)
        payload["dataset"] = str(dataset_path)
        payload["input"] = str(outputs_path)
        payload["corpus_chunks"] = len(chunks)
        payload["method"] = method
        report = write_reports(payload, output_dir, run_name=f"day3_{method}", generated_at=generated_at)
        method_payloads[method] = payload
        summaries.append(summarize_payload(method, payload))
        report_paths[method] = {
            "outputs": str(outputs_path),
            "report_json": str(report["json"]),
            "report_md": str(report["md"]),
        }

    comparison_json = output_dir / f"day3_retrieval_baseline_comparison_{stamp}.json"
    comparison_md = output_dir / f"day3_retrieval_baseline_comparison_{stamp}.md"
    best_summary = max(summaries, key=lambda item: item["avg_retrieval_keyword_coverage"] or 0)
    best_method = str(best_summary["method"])
    cases = pick_cases(method_payloads, best_method)
    comparison_payload = {
        "generated_at": generated_at.isoformat(timespec="seconds"),
        "dataset": str(dataset_path),
        "corpus_chunks": len(chunks),
        "chunk_size": args.chunk_size,
        "overlap": args.overlap,
        "top_k": args.top_k,
        "summaries": summaries,
        "case_picks": cases,
        "files": report_paths,
    }
    comparison_json.write_text(json.dumps(comparison_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_comparison_report(
        comparison_md,
        generated_at=generated_at.isoformat(timespec="seconds"),
        corpus_count=len(chunks),
        chunk_size=args.chunk_size,
        overlap=args.overlap,
        top_k=args.top_k,
        summaries=summaries,
        cases=cases,
        report_paths=report_paths,
        best_method=best_method,
    )
    docs_summary.parent.mkdir(parents=True, exist_ok=True)
    write_presentation_summary(docs_summary, comparison_md, summaries, question_count=len(questions))

    print(f"Corpus chunks: {len(chunks)}")
    print(f"Wrote comparison JSON: {comparison_json}")
    print(f"Wrote comparison Markdown: {comparison_md}")
    print(f"Wrote presentation summary: {docs_summary}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
