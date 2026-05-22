from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
import sys
import time
import traceback
import unicodedata
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8")


REPO_ROOT = Path(__file__).resolve().parents[1]
SITE_PACKAGES = REPO_ROOT / ".venv" / "Lib" / "site-packages"

if str(SITE_PACKAGES) not in sys.path:
    sys.path.insert(0, str(SITE_PACKAGES))

try:
    from pypdf import PdfReader
except ImportError as exc:  # pragma: no cover - reported by the CLI path.
    raise ImportError(  # noqa: TRY003
        f"pypdf is required. Expected it in the current virtualenv at {SITE_PACKAGES}. "
        "Run with .venv\\Scripts\\python.exe -S scripts\\audit_pdf_text_extractability.py"
    ) from exc


RAW_DIR = REPO_ROOT / "data_pipeline" / "raw" / "tsinghua_gas_turbine_books"
REPORT_DIR = REPO_ROOT / "data_pipeline" / "reports"
LOG_DIR = REPO_ROOT / "observability" / "logs" / "pdf_extractability"

PDF_CLASS_DIRECT = "direct_text"
PDF_CLASS_PARTIAL = "partial_text"
PDF_CLASS_NEEDS_OCR = "needs_ocr"
PDF_CLASS_ERROR = "error"

MOJIBAKE_MARKERS = {
    "\u9415",
    "\u51a9",
    "\u76b5",
    "\u6e80",
    "\u95c2",
    "\u7edb",
    "\u9482",
    "\u82ef",
    "\ue50d",
    "\ue57d",
    "\ue21e",
    "\ue046",
    "\ue1bc",
    "\u20ac",
}


@dataclass(slots=True)
class PageSample:
    page_number: int
    char_count: int
    has_text: bool
    gibberish_score: float
    text_preview: str
    error: str = ""


@dataclass(slots=True)
class PdfAuditResult:
    file_name: str
    file_path: str
    size_bytes: int
    size_mb: float
    total_pages: int
    sampled_pages: int
    pages_with_text: int
    extracted_chars: int
    avg_chars_per_sampled_page: float
    avg_chars_per_text_page: float
    text_page_ratio: float
    gibberish_risk: str
    low_text_risk: bool
    risk_reasons: list[str]
    classification: str
    page_samples: list[PageSample]
    error: str = ""


class JsonLogger:
    def __init__(self, log_path: Path) -> None:
        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, event: str, **fields: Any) -> None:
        payload = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "event": event,
            **fields,
        }
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        print(f"[{payload['ts']}] {event} {fields}")


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def text_preview(text: str, limit: int = 180) -> str:
    normalized = normalize_space(text)
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "..."


def gibberish_score(text: str) -> float:
    normalized = normalize_space(text)
    if not normalized:
        return 0.0

    suspicious = 0
    useful = 0
    for char in normalized:
        category = unicodedata.category(char)
        if category.startswith("L") or category.startswith("N"):
            useful += 1
        if char == "\ufffd" or char in MOJIBAKE_MARKERS or category in {"Co", "Cs"} or (category.startswith("C") and char not in {"\t", "\n", "\r"}):
            suspicious += 1

    punctuation_ratio = sum(1 for char in normalized if unicodedata.category(char).startswith("P")) / len(normalized)
    useful_ratio = useful / len(normalized)
    suspicious_ratio = suspicious / len(normalized)
    return min(1.0, suspicious_ratio + max(0.0, punctuation_ratio - 0.45) + max(0.0, 0.18 - useful_ratio))


def risk_level(scores: list[float], combined_text: str) -> str:
    if not combined_text:
        return "none"
    average = statistics.fmean(scores) if scores else 0.0
    max_score = max(scores) if scores else 0.0
    marker_hits = sum(combined_text.count(marker) for marker in MOJIBAKE_MARKERS)
    marker_ratio = marker_hits / max(1, len(combined_text))
    if average >= 0.16 or max_score >= 0.30 or marker_ratio >= 0.025:
        return "high"
    if average >= 0.07 or max_score >= 0.16 or marker_ratio >= 0.01:
        return "medium"
    return "low"


def classify_result(
    sampled_pages: int,
    pages_with_text: int,
    extracted_chars: int,
    avg_chars_per_sampled_page: float,
    gibberish: str,
    page_error_count: int,
) -> tuple[str, bool, list[str]]:
    risk_reasons: list[str] = []
    text_page_ratio = pages_with_text / sampled_pages if sampled_pages else 0.0

    if sampled_pages == 0:
        return PDF_CLASS_ERROR, True, ["no_pages_sampled"]

    if pages_with_text == 0 or extracted_chars == 0:
        return PDF_CLASS_NEEDS_OCR, True, ["no_extractable_text_in_sample"]

    if text_page_ratio < 0.25:
        risk_reasons.append(f"low_text_page_ratio={text_page_ratio:.2f}")
    if avg_chars_per_sampled_page < 120:
        risk_reasons.append(f"low_avg_chars_per_page={avg_chars_per_sampled_page:.1f}")
    if gibberish in {"medium", "high"}:
        risk_reasons.append(f"gibberish_risk={gibberish}")
    if page_error_count:
        risk_reasons.append(f"page_extract_errors={page_error_count}")

    low_text_risk = text_page_ratio < 0.60 or avg_chars_per_sampled_page < 350

    if avg_chars_per_sampled_page < 80 and text_page_ratio < 0.35:
        return PDF_CLASS_NEEDS_OCR, True, risk_reasons or ["very_sparse_extractable_text"]

    if text_page_ratio >= 0.75 and avg_chars_per_sampled_page >= 350 and gibberish != "high" and page_error_count == 0:
        return PDF_CLASS_DIRECT, False, risk_reasons

    return PDF_CLASS_PARTIAL, low_text_risk or bool(risk_reasons), risk_reasons or ["mixed_or_sparse_extractable_text"]


def audit_pdf(pdf_path: Path, sample_pages: int, min_page_chars: int, logger: JsonLogger) -> PdfAuditResult:
    file_size = pdf_path.stat().st_size
    logger.write("pdf_start", file_name=pdf_path.name, size_bytes=file_size)
    page_samples: list[PageSample] = []

    reader = PdfReader(str(pdf_path))
    if reader.is_encrypted:
        try:
            reader.decrypt("")
            logger.write("pdf_decrypt_attempt", file_name=pdf_path.name, method="empty_password")
        except Exception as exc:
            raise RuntimeError(f"PDF is encrypted and empty-password decrypt failed: {exc}") from exc  # noqa: TRY003

    total_pages = len(reader.pages)
    pages_to_scan = min(sample_pages, total_pages)
    page_texts: list[str] = []
    page_error_count = 0

    for page_index in range(pages_to_scan):
        page_number = page_index + 1
        try:
            extracted = reader.pages[page_index].extract_text() or ""
            normalized = normalize_space(extracted)
            score = gibberish_score(normalized)
            page_samples.append(
                PageSample(
                    page_number=page_number,
                    char_count=len(normalized),
                    has_text=len(normalized) >= min_page_chars,
                    gibberish_score=round(score, 4),
                    text_preview=text_preview(normalized),
                )
            )
            page_texts.append(normalized)
        except Exception as exc:
            page_error_count += 1
            error_summary = f"{type(exc).__name__}: {exc}"
            page_samples.append(
                PageSample(
                    page_number=page_number,
                    char_count=0,
                    has_text=False,
                    gibberish_score=0.0,
                    text_preview="",
                    error=error_summary,
                )
            )
            logger.write("page_error", file_name=pdf_path.name, page_number=page_number, error=error_summary)

    extracted_chars = sum(page.char_count for page in page_samples)
    pages_with_text = sum(1 for page in page_samples if page.has_text)
    text_page_ratio = pages_with_text / pages_to_scan if pages_to_scan else 0.0
    avg_sampled = extracted_chars / pages_to_scan if pages_to_scan else 0.0
    avg_text = extracted_chars / pages_with_text if pages_with_text else 0.0
    combined_text = "\n".join(page_texts)
    gibberish = risk_level([page.gibberish_score for page in page_samples], combined_text)
    classification, low_text_risk, risk_reasons = classify_result(
        sampled_pages=pages_to_scan,
        pages_with_text=pages_with_text,
        extracted_chars=extracted_chars,
        avg_chars_per_sampled_page=avg_sampled,
        gibberish=gibberish,
        page_error_count=page_error_count,
    )

    result = PdfAuditResult(
        file_name=pdf_path.name,
        file_path=str(pdf_path),
        size_bytes=file_size,
        size_mb=round(file_size / (1024 * 1024), 3),
        total_pages=total_pages,
        sampled_pages=pages_to_scan,
        pages_with_text=pages_with_text,
        extracted_chars=extracted_chars,
        avg_chars_per_sampled_page=round(avg_sampled, 1),
        avg_chars_per_text_page=round(avg_text, 1),
        text_page_ratio=round(text_page_ratio, 3),
        gibberish_risk=gibberish,
        low_text_risk=low_text_risk,
        risk_reasons=risk_reasons,
        classification=classification,
        page_samples=page_samples,
    )
    logger.write(
        "pdf_result",
        file_name=pdf_path.name,
        total_pages=total_pages,
        sampled_pages=pages_to_scan,
        pages_with_text=pages_with_text,
        extracted_chars=extracted_chars,
        avg_chars_per_sampled_page=result.avg_chars_per_sampled_page,
        gibberish_risk=gibberish,
        classification=classification,
        risk_reasons=risk_reasons,
    )
    return result


def error_result(pdf_path: Path, error: BaseException, logger: JsonLogger) -> PdfAuditResult:
    file_size = pdf_path.stat().st_size if pdf_path.exists() else 0
    error_summary = f"{type(error).__name__}: {error}"
    logger.write(
        "pdf_error",
        file_name=pdf_path.name,
        error=error_summary,
        traceback=traceback.format_exc(),
    )
    return PdfAuditResult(
        file_name=pdf_path.name,
        file_path=str(pdf_path),
        size_bytes=file_size,
        size_mb=round(file_size / (1024 * 1024), 3),
        total_pages=0,
        sampled_pages=0,
        pages_with_text=0,
        extracted_chars=0,
        avg_chars_per_sampled_page=0.0,
        avg_chars_per_text_page=0.0,
        text_page_ratio=0.0,
        gibberish_risk="unknown",
        low_text_risk=True,
        risk_reasons=["pdf_read_error"],
        classification=PDF_CLASS_ERROR,
        page_samples=[],
        error=error_summary,
    )


def sort_for_representative(result: PdfAuditResult) -> tuple[int, float, int]:
    class_weight = {PDF_CLASS_DIRECT: 3, PDF_CLASS_PARTIAL: 2}.get(result.classification, 0)
    return (class_weight, result.text_page_ratio, result.extracted_chars)


def build_recommendations(results: list[PdfAuditResult]) -> dict[str, Any]:
    candidates = [
        result
        for result in results
        if result.classification in {PDF_CLASS_DIRECT, PDF_CLASS_PARTIAL}
        and result.pages_with_text > 0
        and result.gibberish_risk != "high"
    ]
    candidates = sorted(candidates, key=sort_for_representative, reverse=True)
    representative = candidates[: max(2, min(4, len(candidates)))]

    ocr_queue = [
        {
            "file_name": result.file_name,
            "classification": result.classification,
            "priority": "high" if result.classification == PDF_CLASS_NEEDS_OCR else "medium",
            "reason": "; ".join(result.risk_reasons) or "partial extraction needs OCR for full-book ingestion",
        }
        for result in sorted(results, key=lambda item: (item.classification != PDF_CLASS_NEEDS_OCR, item.extracted_chars))
        if result.classification in {PDF_CLASS_NEEDS_OCR, PDF_CLASS_PARTIAL}
    ]

    error_queue = [
        {
            "file_name": result.file_name,
            "error": result.error,
            "reason": "; ".join(result.risk_reasons),
        }
        for result in results
        if result.classification == PDF_CLASS_ERROR
    ]

    return {
        "target_representative_count": 2,
        "representative_requirement_met": len(representative) >= 2,
        "representative_gap": max(0, 2 - len(representative)),
        "representative_note": (
            "Only one direct/partial PDF was found by pypdf in the sampled pages; "
            "a second representative PDF should not be selected until OCR creates usable text."
            if len(representative) < 2
            else "At least two direct/partial PDFs are available for representative indexing."
        ),
        "representative_build_candidates": [
            {
                "file_name": result.file_name,
                "classification": result.classification,
                "why": (
                    f"{result.pages_with_text}/{result.sampled_pages} sampled pages have text, "
                    f"{result.extracted_chars} chars extracted, avg {result.avg_chars_per_sampled_page} chars/page"
                ),
            }
            for result in representative
        ],
        "ocr_queue": ocr_queue,
        "error_queue": error_queue,
    }


def result_to_jsonable(result: PdfAuditResult) -> dict[str, Any]:
    payload = asdict(result)
    payload["page_samples"] = [asdict(page) for page in result.page_samples]
    return payload


def write_json_report(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_csv_report(path: Path, results: list[PdfAuditResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "file_name",
        "size_mb",
        "total_pages",
        "sampled_pages",
        "pages_with_text",
        "extracted_chars",
        "avg_chars_per_sampled_page",
        "avg_chars_per_text_page",
        "text_page_ratio",
        "gibberish_risk",
        "low_text_risk",
        "classification",
        "risk_reasons",
        "error",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for result in results:
            row = {field: getattr(result, field) for field in fieldnames if field not in {"risk_reasons"}}
            row["risk_reasons"] = "; ".join(result.risk_reasons)
            writer.writerow(row)


def write_markdown_report(path: Path, payload: dict[str, Any], results: list[PdfAuditResult]) -> None:
    recommendations = payload["recommendations"]
    summary = payload["summary"]
    criteria = payload["criteria"]

    lines = [
        "# PDF Text Extractability Audit",
        "",
        f"- Generated at: `{payload['generated_at']}`",
        f"- Raw directory: `{payload['raw_dir']}`",
        f"- Programmatic extractor: `pypdf {payload['pypdf_version']}`",
        f"- Sample policy: first `{criteria['sample_first_pages']}` pages per PDF; text page threshold `{criteria['min_page_chars']}` chars.",
        "",
        "## Summary",
        "",
        f"- PDFs audited: {summary['pdf_count']}",
        f"- direct_text: {summary['by_classification'].get(PDF_CLASS_DIRECT, 0)}",
        f"- partial_text: {summary['by_classification'].get(PDF_CLASS_PARTIAL, 0)}",
        f"- needs_ocr: {summary['by_classification'].get(PDF_CLASS_NEEDS_OCR, 0)}",
        f"- error: {summary['by_classification'].get(PDF_CLASS_ERROR, 0)}",
        "",
        "## Representative Build Candidates",
        "",
    ]

    if recommendations["representative_build_candidates"]:
        for item in recommendations["representative_build_candidates"]:
            lines.append(f"- `{item['file_name']}` ({item['classification']}): {item['why']}.")
    else:
        lines.append("- No direct/partial candidate was found in the sampled pages.")
    if not recommendations["representative_requirement_met"]:
        lines.append(f"- Gap: {recommendations['representative_note']}")

    lines.extend(["", "## OCR Queue", ""])
    if recommendations["ocr_queue"]:
        for item in recommendations["ocr_queue"]:
            lines.append(f"- `{item['file_name']}` ({item['priority']}, {item['classification']}): {item['reason']}.")
    else:
        lines.append("- No PDF was classified as needs_ocr or partial_text.")

    if recommendations["error_queue"]:
        lines.extend(["", "## Error Queue", ""])
        for item in recommendations["error_queue"]:
            lines.append(f"- `{item['file_name']}`: {item['error']}")

    lines.extend(
        [
            "",
            "## Per-PDF Results",
            "",
            "| File | Pages | Sampled | Text Pages | Chars | Avg chars/page | Gibberish risk | Classification | Reasons |",
            "| --- | ---: | ---: | ---: | ---: | ---: | --- | --- | --- |",
        ]
    )
    for result in results:
        reasons = "; ".join(result.risk_reasons) if result.risk_reasons else "-"
        lines.append(
            f"| {result.file_name} | {result.total_pages} | {result.sampled_pages} | "
            f"{result.pages_with_text} | {result.extracted_chars} | {result.avg_chars_per_sampled_page} | "
            f"{result.gibberish_risk} | {result.classification} | {reasons} |"
        )

    lines.extend(
        [
            "",
            "## Classification Rules",
            "",
            "- `direct_text`: most sampled pages have extractable text, average text density is usable, and gibberish risk is not high.",
            "- `partial_text`: pypdf extracts some text, but coverage, density, page errors, or gibberish risk make it unsafe as a full-book text source.",
            "- `needs_ocr`: sampled pages have no or extremely sparse extractable text.",
            "- `error`: pypdf could not read or sample the file; inspect the log before retrying.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def summarize(results: list[PdfAuditResult]) -> dict[str, Any]:
    by_classification: dict[str, int] = {}
    for result in results:
        by_classification[result.classification] = by_classification.get(result.classification, 0) + 1
    return {
        "pdf_count": len(results),
        "by_classification": by_classification,
        "total_pages": sum(result.total_pages for result in results),
        "total_sampled_pages": sum(result.sampled_pages for result in results),
        "total_extracted_chars": sum(result.extracted_chars for result in results),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit whether downloaded PDF books have programmatically extractable text.")
    parser.add_argument("--raw-dir", type=Path, default=RAW_DIR)
    parser.add_argument("--report-dir", type=Path, default=REPORT_DIR)
    parser.add_argument("--log-dir", type=Path, default=LOG_DIR)
    parser.add_argument("--sample-pages", type=int, default=80, help="Scan the first N pages of each PDF.")
    parser.add_argument("--min-page-chars", type=int, default=30, help="Minimum normalized chars for a sampled page to count as text.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    started = time.perf_counter()

    if args.sample_pages < 1:
        raise ValueError("--sample-pages must be >= 1")  # noqa: TRY003
    if args.min_page_chars < 1:
        raise ValueError("--min-page-chars must be >= 1")  # noqa: TRY003
    if not args.raw_dir.exists():
        raise FileNotFoundError(f"Raw directory does not exist: {args.raw_dir}")  # noqa: TRY003

    log_path = args.log_dir / f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-pdf-extractability.log"
    logger = JsonLogger(log_path)
    pdf_paths = sorted(args.raw_dir.glob("*.pdf"), key=lambda path: path.name)
    if not pdf_paths:
        raise FileNotFoundError(f"No PDF files found in {args.raw_dir}")  # noqa: TRY003

    logger.write(
        "audit_start",
        raw_dir=str(args.raw_dir),
        report_dir=str(args.report_dir),
        log_path=str(log_path),
        pdf_count=len(pdf_paths),
        sample_pages=args.sample_pages,
        min_page_chars=args.min_page_chars,
    )

    results: list[PdfAuditResult] = []
    for pdf_path in pdf_paths:
        try:
            results.append(audit_pdf(pdf_path, args.sample_pages, args.min_page_chars, logger))
        except Exception as exc:
            results.append(error_result(pdf_path, exc, logger))

    import pypdf

    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "raw_dir": str(args.raw_dir),
        "pypdf_version": pypdf.__version__,
        "criteria": {
            "sample_first_pages": args.sample_pages,
            "min_page_chars": args.min_page_chars,
            "direct_text": "text_page_ratio >= 0.75 and avg_chars_per_sampled_page >= 350 and gibberish_risk != high",
            "needs_ocr": "no text in sample, or very sparse extraction with text_page_ratio < 0.35 and avg < 80",
            "partial_text": "some extractable text but below direct_text confidence or with extraction/gibberish risk",
        },
        "summary": summarize(results),
        "recommendations": build_recommendations(results),
        "pdfs": [result_to_jsonable(result) for result in results],
        "log_path": str(log_path),
    }

    json_path = args.report_dir / "pdf_extractability_report.json"
    csv_path = args.report_dir / "pdf_extractability_report.csv"
    md_path = args.report_dir / "pdf_extractability_report.md"
    write_json_report(json_path, payload)
    write_csv_report(csv_path, results)
    write_markdown_report(md_path, payload, results)

    logger.write(
        "reports_written",
        json_path=str(json_path),
        csv_path=str(csv_path),
        md_path=str(md_path),
    )
    logger.write("audit_done", elapsed_s=round(time.perf_counter() - started, 3), summary=payload["summary"])
    print(json.dumps({"summary": payload["summary"], "reports": [str(json_path), str(csv_path), str(md_path)]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
