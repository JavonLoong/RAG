from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8")


REPO_ROOT = Path(__file__).resolve().parents[1]
CONSOLE_SRC = REPO_ROOT / "api_server" / "current_console" / "chroma_rag_poc" / "src"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(CONSOLE_SRC) not in sys.path:
    sys.path.insert(0, str(CONSOLE_SRC))

from chroma_rag_poc.pipeline import ingest_source_payloads  # noqa: E402
from evaluation import EvaluationThresholds, LocalChromaRegressionRag, RAGEvaluationCase, RAGEvaluationReport  # noqa: E402
from evaluation.external_benchmark_loader import ExternalBenchmarkSuite  # noqa: E402
from model_adapters.llm import LLMConfigurationError, OpenAICompatibleLLMClient  # noqa: E402
from rag_orchestrator.adapters import CommandLLM  # noqa: E402
from scripts.run_external_benchmark_evaluation import (  # noqa: E402
    DEFAULT_BENCHMARKS,
    DEFAULT_PERSIST_ROOT,
    DEFAULT_REPORT_DIR,
    build_suite,
    repo_relative_path,
    score_band,
)
from scripts.run_system_evaluation import evaluate_records  # noqa: E402


DEFAULT_GEMINI_MODEL = "gemini-3.5-flash"
DEFAULT_GEMINI_OPENAI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
DEFAULT_KEY_ENVS = ("GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY")


class GeneratedAnswerRag:
    """Wrap a retriever with an LLM answer generation step for end-to-end RAG evaluation."""

    def __init__(
        self,
        *,
        retriever: Any,
        llm: Any,
        top_k: int,
        context_char_limit: int = 12000,
        chunk_char_limit: int = 1800,
        temperature: float = 0.0,
        max_output_tokens: int = 900,
        delay_seconds: float = 0.0,
    ) -> None:
        self.retriever = retriever
        self.llm = llm
        self.top_k = top_k
        self.context_char_limit = context_char_limit
        self.chunk_char_limit = chunk_char_limit
        self.temperature = temperature
        self.max_output_tokens = max_output_tokens
        self.delay_seconds = delay_seconds

    def query(self, question: str) -> dict[str, Any]:
        retrieval = self.retriever.query(question)
        hits = list(retrieval.get("retrieval_results") or [])[: self.top_k]
        context = build_prompt_context(hits, context_char_limit=self.context_char_limit, chunk_char_limit=self.chunk_char_limit)
        prompt = build_answer_prompt(question=question, context=context)
        answer = call_llm(
            self.llm,
            prompt,
            temperature=self.temperature,
            max_tokens=self.max_output_tokens,
        ).strip()
        if self.delay_seconds > 0:
            time.sleep(self.delay_seconds)
        return {
            "answer": answer,
            "context": context,
            "retrieval_results": hits,
            "citations": retrieval.get("citations") or build_citations_from_hits(hits),
            "retrieval_metadata": {
                "collection": retrieval.get("collection"),
                "embedding_backend": retrieval.get("embedding_backend"),
                "embedding_model": retrieval.get("embedding_model"),
            },
        }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run downloaded external RAG/GraphRAG benchmarks end to end: ingest documents, retrieve with the local "
            "pipeline, generate answers with Gemini, then compare generated answers with gold references."
        )
    )
    parser.add_argument("--benchmarks", nargs="+", default=list(DEFAULT_BENCHMARKS))
    parser.add_argument("--case-limit", type=int, default=0, help="Max cases per benchmark. <=0 means all cases.")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--chunk-size", type=int, default=900)
    parser.add_argument("--overlap", type=int, default=120)
    parser.add_argument("--backend", default="hashing", help="Embedding backend for this benchmark run.")
    parser.add_argument("--model-name", default="", help="Optional embedding model name.")
    parser.add_argument("--persist-root", type=Path, default=DEFAULT_PERSIST_ROOT)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--run-name", default="", help="Optional run name. Defaults to timestamp.")
    parser.add_argument("--resume", action="store_true", help="Reuse per-case JSONL outputs already written for this run.")
    parser.add_argument(
        "--llm-provider",
        choices=("gemini-openai", "command"),
        default="gemini-openai",
        help="Use Gemini's OpenAI-compatible API by default, or a local command that reads prompt from stdin.",
    )
    parser.add_argument("--gemini-model", default=DEFAULT_GEMINI_MODEL)
    parser.add_argument("--gemini-base-url", default=DEFAULT_GEMINI_OPENAI_BASE_URL)
    parser.add_argument(
        "--gemini-api-key-envs",
        default=",".join(DEFAULT_KEY_ENVS),
        help="Comma-separated env vars to try for the Gemini API key.",
    )
    parser.add_argument("--llm-command", default="", help="Command LLM adapter; prompt is sent on stdin.")
    parser.add_argument("--llm-timeout", type=int, default=180)
    parser.add_argument("--context-char-limit", type=int, default=12000)
    parser.add_argument("--chunk-char-limit", type=int, default=1800)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-output-tokens", type=int, default=900)
    parser.add_argument("--delay-seconds", type=float, default=0.0, help="Optional delay after each LLM call.")
    parser.add_argument(
        "--max-new-cases",
        type=int,
        default=0,
        help="Generate at most this many new cases per suite, then stop cleanly. <=0 means no checkpoint limit.",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Record failed per-case generation errors and continue. Auth/config errors still fail fast.",
    )
    parser.add_argument("--json", action="store_true", help="Print full aggregate JSON.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run_id = safe_name(args.run_name) if args.run_name else datetime.now().strftime("%Y%m%d_%H%M%S")
    persist_dir = args.persist_root / run_id
    report_dir = args.report_dir
    case_limit = None if args.case_limit <= 0 else args.case_limit

    try:
        llm = build_llm(args)
    except LLMConfigurationError as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2

    summaries: list[dict[str, Any]] = []
    for benchmark in args.benchmarks:
        suite = build_suite(benchmark, case_limit=case_limit)
        summary = run_suite(
            suite,
            persist_dir=persist_dir,
            report_dir=report_dir,
            collection_name=f"full_external_{safe_name(suite.name)}_{run_id}",
            top_k=args.top_k,
            backend=args.backend,
            model_name=args.model_name or None,
            chunk_size=args.chunk_size,
            overlap=args.overlap,
            llm=llm,
            context_char_limit=args.context_char_limit,
            chunk_char_limit=args.chunk_char_limit,
            temperature=args.temperature,
            max_output_tokens=args.max_output_tokens,
            delay_seconds=args.delay_seconds,
            max_new_cases=args.max_new_cases,
            resume=args.resume,
            continue_on_error=args.continue_on_error,
        )
        summaries.append(summary)

    aggregate = build_aggregate_payload(
        run_id=run_id,
        summaries=summaries,
        persist_dir=persist_dir,
        report_dir=report_dir,
        top_k=args.top_k,
        case_limit=case_limit,
        llm_provider=args.llm_provider,
        llm_model=args.gemini_model if args.llm_provider == "gemini-openai" else args.llm_command,
    )
    paths = write_aggregate_report(report_dir, aggregate)
    aggregate["aggregate_reports"] = {name: str(path) for name, path in paths.items()}

    if args.json:
        print(json.dumps(aggregate, ensure_ascii=False, indent=2))
    else:
        print(
            "full_external_benchmark_score={score} cases={cases} benchmarks={benchmarks} report={report}".format(
                score=aggregate["overall_score_100"],
                cases=aggregate["total_cases"],
                benchmarks=len(summaries),
                report=aggregate["aggregate_reports"]["md"],
            )
        )
    return 0


def build_llm(args: argparse.Namespace) -> Any:
    if args.llm_provider == "command":
        if not args.llm_command.strip():
            raise LLMConfigurationError("--llm-command is required when --llm-provider command is used.")
        return CommandLLM(args.llm_command, timeout_seconds=args.llm_timeout)

    api_key_envs = tuple(item.strip() for item in str(args.gemini_api_key_envs).split(",") if item.strip())
    api_key, source_env = resolve_api_key(api_key_envs)
    if not api_key:
        joined = ", ".join(api_key_envs)
        raise LLMConfigurationError(
            f"Gemini API key is missing. Set one of: {joined}. "
            f"Default model: {args.gemini_model}; base URL: {args.gemini_base_url}."
        )
    client = OpenAICompatibleLLMClient(
        api_key=api_key,
        base_url=args.gemini_base_url,
        model=args.gemini_model,
        timeout=float(args.llm_timeout),
    )
    client.key_source_env = source_env  # type: ignore[attr-defined]
    return client


def resolve_api_key(env_names: Iterable[str]) -> tuple[str, str | None]:
    for name in env_names:
        value = os.environ.get(name, "").strip()
        if value:
            return value, name
    return "", None


def run_suite(
    suite: ExternalBenchmarkSuite,
    *,
    persist_dir: Path,
    report_dir: Path,
    collection_name: str,
    top_k: int,
    backend: str,
    model_name: str | None,
    chunk_size: int,
    overlap: int,
    llm: Any,
    context_char_limit: int,
    chunk_char_limit: int,
    temperature: float,
    max_output_tokens: int,
    delay_seconds: float,
    max_new_cases: int,
    resume: bool,
    continue_on_error: bool,
) -> dict[str, Any]:
    chroma_persist_dir = repo_relative_path(persist_dir)
    print(f"[{suite.name}] ingest payloads={len(suite.payloads)} cases={len(suite.cases)} collection={collection_name}")
    ingest = ingest_source_payloads(
        payloads=suite.payloads,
        persist_dir=chroma_persist_dir,
        collection_name=collection_name,
        chunk_size=chunk_size,
        overlap=overlap,
        backend=backend,
        model_name=model_name,
        clean=False,
        parser_backend="auto",
    )
    retriever = LocalChromaRegressionRag(
        persist_dir=chroma_persist_dir,
        collection_name=collection_name,
        top_k=top_k,
        backend=backend,
        model_name=model_name,
    )
    rag = GeneratedAnswerRag(
        retriever=retriever,
        llm=llm,
        top_k=top_k,
        context_char_limit=context_char_limit,
        chunk_char_limit=chunk_char_limit,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        delay_seconds=delay_seconds,
    )
    output_path = persist_dir / "case_outputs" / f"{safe_name(suite.name)}.jsonl"
    outputs, complete = run_cases_with_cache(
        suite.cases,
        rag=rag,
        output_path=output_path,
        resume=resume,
        continue_on_error=continue_on_error,
        max_new_cases=max_new_cases,
    )
    if not complete:
        return {
            "benchmark": suite.name,
            "status": "partial",
            "score_100": None,
            "score_band": "partial",
            "case_count": len(suite.cases),
            "completed_case_count": len(outputs),
            "remaining_case_count": max(0, len(suite.cases) - len(outputs)),
            "payload_count": len(suite.payloads),
            "collection_name": collection_name,
            "case_output_path": str(output_path),
            "ingest": {
                "chunks_written": ingest.get("chunks_written"),
                "records_extracted": ingest.get("records_extracted"),
                "embedding_backend": ingest.get("embedding_backend"),
                "embedding_model": ingest.get("embedding_model"),
                "quality_gate_status": (ingest.get("quality") or {}).get("quality_gate_status"),
            },
            "gate_status": "partial",
            "gate_failures": [],
            "metrics": {},
            "reports": {},
            "notes": suite.notes,
        }

    dataset = [case.to_dataset_record() for case in suite.cases]
    payload = evaluate_records(dataset, outputs, top_k=top_k, retrieval_only=False)
    payload["reference_match"] = build_reference_match_payload(suite.cases, outputs)
    payload.setdefault("metrics", {})["reference_match"] = payload["reference_match"]["metrics"]
    payload["output_path"] = str(output_path)

    thresholds = EvaluationThresholds(
        min_keyword_recall_at_k=0.60,
        min_answer_completeness=0.60,
        max_missing_citation_rate=0.10,
        max_medium_or_high_risk_rate=0.50,
        max_no_result_rate=0.05,
    )
    gate_failures = thresholds.check(payload)
    failure_cases = select_failure_cases(payload, thresholds)
    report = RAGEvaluationReport(
        payload=payload,
        thresholds=thresholds,
        gate_failures=gate_failures,
        failure_cases=failure_cases,
        run_name=f"full_external_{suite.name}",
    )
    paths = report.save(report_dir)
    score = score_full_suite_payload(payload)

    return {
        "benchmark": suite.name,
        "score_100": score,
        "score_band": score_band(score),
        "case_count": len(suite.cases),
        "payload_count": len(suite.payloads),
        "collection_name": collection_name,
        "case_output_path": str(output_path),
        "ingest": {
            "chunks_written": ingest.get("chunks_written"),
            "records_extracted": ingest.get("records_extracted"),
            "embedding_backend": ingest.get("embedding_backend"),
            "embedding_model": ingest.get("embedding_model"),
            "quality_gate_status": (ingest.get("quality") or {}).get("quality_gate_status"),
        },
        "gate_status": report.gate_status,
        "gate_failures": report.gate_failures,
        "metrics": payload.get("metrics", {}),
        "reports": {name: str(path) for name, path in paths.items()},
        "notes": suite.notes,
    }


def run_cases_with_cache(
    cases: list[RAGEvaluationCase],
    *,
    rag: GeneratedAnswerRag,
    output_path: Path,
    resume: bool,
    continue_on_error: bool,
    max_new_cases: int = 0,
) -> tuple[list[dict[str, Any]], bool]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cached = load_cached_outputs(output_path) if resume else {}
    outputs_by_id: dict[str, dict[str, Any]] = dict(cached)
    mode = "a" if resume else "w"
    with output_path.open(mode, encoding="utf-8") as handle:
        new_case_count = 0
        for index, case in enumerate(cases, start=1):
            if case.id in outputs_by_id:
                if index == 1 or index % 25 == 0 or index == len(cases):
                    print(f"  [{index}/{len(cases)}] reused cached output")
                continue
            if max_new_cases > 0 and new_case_count >= max_new_cases:
                print(
                    f"  checkpoint limit reached: generated {new_case_count} new cases; "
                    f"completed {len(outputs_by_id)}/{len(cases)}"
                )
                return [outputs_by_id[case.id] for case in cases if case.id in outputs_by_id], False
            started = time.time()
            try:
                output = rag.query(case.question)
                output["generation_error"] = None
            except Exception as exc:
                if not continue_on_error:
                    raise
                output = {
                    "answer": "",
                    "context": "",
                    "retrieval_results": [],
                    "citations": [],
                    "generation_error": str(exc),
                }
            output["id"] = case.id
            output["question"] = case.question
            output["elapsed_seconds"] = round(time.time() - started, 3)
            outputs_by_id[case.id] = output
            new_case_count += 1
            handle.write(json.dumps(output, ensure_ascii=False) + "\n")
            handle.flush()
            if index == 1 or index % 10 == 0 or index == len(cases):
                print(f"  [{index}/{len(cases)}] generated id={case.id} elapsed={output['elapsed_seconds']}s")
    return [outputs_by_id[case.id] for case in cases if case.id in outputs_by_id], len(outputs_by_id) >= len(cases)


def load_cached_outputs(output_path: Path) -> dict[str, dict[str, Any]]:
    if not output_path.exists():
        return {}
    cached: dict[str, dict[str, Any]] = {}
    for line_number, line in enumerate(output_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise ValueError(f"{output_path}:{line_number} must contain a JSON object.")
        case_id = str(payload.get("id") or "")
        if case_id:
            cached[case_id] = payload
    return cached


def build_answer_prompt(*, question: str, context: str) -> str:
    return f"""You are evaluating a retrieval-augmented generation system.

Answer the question using ONLY the retrieved context below.
If the context is insufficient, say that the provided context is insufficient and explain what is missing.
Keep the answer concise, factual, and cite evidence with bracketed source numbers like [1] or [2].
Do not mention any gold/reference answer.

Question:
{question}

Retrieved context:
{context}

Answer:"""


def build_prompt_context(
    hits: list[dict[str, Any]],
    *,
    context_char_limit: int,
    chunk_char_limit: int,
) -> str:
    sections: list[str] = []
    total = 0
    for index, hit in enumerate(hits, start=1):
        metadata = hit.get("metadata") if isinstance(hit.get("metadata"), dict) else {}
        source = metadata.get("source_file") or metadata.get("filename") or metadata.get("source") or "retrieved_context"
        text = str(hit.get("text") or hit.get("content") or "")
        text = " ".join(text.split())
        if chunk_char_limit > 0 and len(text) > chunk_char_limit:
            text = text[: chunk_char_limit - 1].rstrip() + "..."
        section = f"[{index}] Source: {source}\n{text}"
        if context_char_limit > 0 and total + len(section) > context_char_limit:
            break
        sections.append(section)
        total += len(section)
    return "\n\n".join(sections) if sections else "[no retrieved context]"


def build_citations_from_hits(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    citations: list[dict[str, Any]] = []
    for index, hit in enumerate(hits, start=1):
        metadata = hit.get("metadata") if isinstance(hit.get("metadata"), dict) else {}
        citations.append(
            {
                "id": str(index),
                "source": metadata.get("source_file") or metadata.get("filename") or "retrieved_context",
                "text": hit.get("text") or "",
                "metadata": metadata,
            }
        )
    return citations


def call_llm(llm: Any, prompt: str, **kwargs: Any) -> str:
    for method_name in ("generate", "complete", "invoke"):
        method = getattr(llm, method_name, None)
        if callable(method):
            return str(method(prompt, **kwargs))
    if callable(llm):
        return str(llm(prompt))
    raise TypeError("LLM client must be callable or expose generate/complete/invoke.")


def build_reference_match_payload(
    cases: list[RAGEvaluationCase],
    outputs: list[dict[str, Any]],
) -> dict[str, Any]:
    output_by_id = {str(output.get("id")): output for output in outputs}
    results: list[dict[str, Any]] = []
    f1_values: list[float] = []
    exact_count = 0
    evaluated = 0
    for case in cases:
        reference = case.reference_answer.strip()
        if not reference:
            continue
        output = output_by_id.get(case.id) or {}
        answer = str(output.get("answer") or "")
        exact = normalize_for_match(answer) == normalize_for_match(reference)
        f1 = token_f1(answer, reference)
        evaluated += 1
        exact_count += int(exact)
        f1_values.append(f1)
        results.append(
            {
                "id": case.id,
                "exact_match": exact,
                "token_f1": f1,
                "answer_preview": compact(answer, 240),
                "reference_preview": compact(reference, 240),
            }
        )
    return {
        "metrics": {
            "evaluated_questions": evaluated,
            "exact_match_rate": round(exact_count / evaluated, 6) if evaluated else None,
            "average_token_f1": round(sum(f1_values) / len(f1_values), 6) if f1_values else None,
        },
        "results": results,
    }


def score_full_suite_payload(payload: dict[str, Any]) -> float:
    metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
    retrieval = metrics.get("retrieval") if isinstance(metrics.get("retrieval"), dict) else {}
    answer = metrics.get("answer") if isinstance(metrics.get("answer"), dict) else {}
    citation = metrics.get("citation") if isinstance(metrics.get("citation"), dict) else {}
    reference_match = metrics.get("reference_match") if isinstance(metrics.get("reference_match"), dict) else {}

    answer_completeness = coerce_rate(answer.get("answer_completeness_avg"))
    reference_f1 = coerce_rate(reference_match.get("average_token_f1"))
    retrieval_recall = coerce_rate(retrieval.get("keyword_recall_at_k"))
    citation_score = 1.0 - coerce_rate(citation.get("missing_citation_rate"))
    no_result_score = 1.0 - coerce_rate(retrieval.get("no_result_rate"))

    score = 100.0 * (
        0.35 * answer_completeness
        + 0.25 * reference_f1
        + 0.25 * retrieval_recall
        + 0.10 * citation_score
        + 0.05 * no_result_score
    )
    return round(max(0.0, min(100.0, score)), 2)


def build_aggregate_payload(
    *,
    run_id: str,
    summaries: list[dict[str, Any]],
    persist_dir: Path,
    report_dir: Path,
    top_k: int,
    case_limit: int | None,
    llm_provider: str,
    llm_model: str,
) -> dict[str, Any]:
    total_cases = sum(int(summary["case_count"]) for summary in summaries)
    completed_cases = sum(int(summary.get("completed_case_count", summary["case_count"])) for summary in summaries)
    complete_summaries = [summary for summary in summaries if summary.get("status") != "partial"]
    has_partial = any(summary.get("status") == "partial" for summary in summaries)
    scored_cases = sum(int(summary["case_count"]) for summary in complete_summaries)
    weighted_score: float | None = None
    if scored_cases:
        weighted_score = (
            sum(float(summary["score_100"]) * int(summary["case_count"]) for summary in complete_summaries)
            / scored_cases
        )
    return {
        "run_id": run_id,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "score_type": "full_rag_generation_score",
        "score_formula": (
            "100 * (0.35 * answer_completeness_avg + 0.25 * average_token_f1_against_reference + "
            "0.25 * keyword_recall_at_k + 0.10 * (1 - missing_citation_rate) + 0.05 * (1 - no_result_rate))"
        ),
        "overall_score_100": round(weighted_score, 2) if weighted_score is not None and not has_partial else None,
        "overall_score_band": "partial" if has_partial else score_band(weighted_score or 0.0),
        "total_cases": total_cases,
        "completed_cases": completed_cases,
        "top_k": top_k,
        "case_limit_per_benchmark": case_limit,
        "persist_dir": str(persist_dir),
        "report_dir": str(report_dir),
        "llm_provider": llm_provider,
        "llm_model": llm_model,
        "benchmarks": summaries,
        "limitations": [
            "Generated answers are compared with gold references using deterministic keyword coverage and token F1.",
            "This does not use the gold answer in the answer-generation prompt.",
            "Token F1 can penalize correct paraphrases, so answer_completeness and retrieval metrics are reported together.",
        ],
    }


def write_aggregate_report(report_dir: Path, payload: dict[str, Any]) -> dict[str, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    stem = f"full_external_benchmark_eval_{payload['run_id']}"
    json_path = report_dir / f"{stem}.json"
    md_path = report_dir / f"{stem}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(aggregate_markdown(payload), encoding="utf-8")
    return {"json": json_path, "md": md_path}


def aggregate_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Full External RAG Benchmark Evaluation",
        "",
        f"- Run: `{payload['run_id']}`",
        f"- Score type: `{payload['score_type']}`",
        f"- Overall score: **{md_cell(payload['overall_score_100'])} / 100** ({payload['overall_score_band']})",
        f"- Total cases: {payload['total_cases']}",
        f"- Completed cases: {payload.get('completed_cases', payload['total_cases'])}",
        f"- Top K: {payload['top_k']}",
        f"- LLM: `{payload['llm_provider']}:{payload['llm_model']}`",
        "",
        "## Benchmark Scores",
        "",
        "| Benchmark | Cases | Score | Band | Gate | Answer completeness | Ref F1 | Retrieval recall | Missing citation | Report |",
        "| --- | ---: | ---: | --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for summary in payload["benchmarks"]:
        metrics = summary.get("metrics") or {}
        answer = metrics.get("answer") or {}
        reference_match = metrics.get("reference_match") or {}
        retrieval = metrics.get("retrieval") or {}
        citation = metrics.get("citation") or {}
        lines.append(
            "| {benchmark} | {cases} | {score} | {band} | {gate} | {answer_score} | {ref_f1} | {recall} | {missing} | {report} |".format(
                benchmark=md_cell(summary["benchmark"]),
                cases=summary["case_count"],
                score=summary["score_100"],
                band=md_cell(summary["score_band"]),
                gate=md_cell(summary["gate_status"]),
                answer_score=md_cell(answer.get("answer_completeness_avg")),
                ref_f1=md_cell(reference_match.get("average_token_f1")),
                recall=md_cell(retrieval.get("keyword_recall_at_k")),
                missing=md_cell(citation.get("missing_citation_rate")),
                report=md_cell((summary.get("reports") or {}).get("md", "")),
            )
        )
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {item}" for item in payload["limitations"])
    return "\n".join(lines).rstrip() + "\n"


def select_failure_cases(payload: dict[str, Any], thresholds: EvaluationThresholds) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for result in payload.get("results", []):
        coverage = result.get("retrieval_keyword_coverage")
        answer_coverage = result.get("answer_keyword_coverage")
        risk = result.get("hallucination_risk")
        failed = (
            coverage is not None
            and coverage < thresholds.min_keyword_recall_at_k
            or answer_coverage is not None
            and answer_coverage < thresholds.min_answer_completeness
            or bool(result.get("missing_citation"))
            or risk in {"medium", "high"}
            or not result.get("has_retrieval_result")
        )
        if failed:
            failures.append(result)
    return failures


def normalize_for_match(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]", value.casefold()))


def tokenize_for_f1(value: str) -> list[str]:
    return re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]", value.casefold())


def token_f1(prediction: str, reference: str) -> float:
    pred_tokens = tokenize_for_f1(prediction)
    ref_tokens = tokenize_for_f1(reference)
    if not pred_tokens and not ref_tokens:
        return 1.0
    if not pred_tokens or not ref_tokens:
        return 0.0
    pred_counts = Counter(pred_tokens)
    ref_counts = Counter(ref_tokens)
    common = sum((pred_counts & ref_counts).values())
    if common == 0:
        return 0.0
    precision = common / len(pred_tokens)
    recall = common / len(ref_tokens)
    return round((2 * precision * recall) / (precision + recall), 6)


def coerce_rate(value: Any) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, numeric))


def safe_name(value: str) -> str:
    safe = re.sub(r"[^0-9A-Za-z_.-]+", "_", value.strip())
    return safe.strip("._-") or "run"


def compact(value: Any, limit: int = 180) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)] + "..."


def md_cell(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", " ")


if __name__ == "__main__":
    raise SystemExit(main())
