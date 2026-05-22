from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8")


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_ROOT = REPO_ROOT / "data_pipeline" / "ocr_layout_aware_tesseract_night_corrected" / "tsinghua_gas_turbine_books"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "data_pipeline" / "ocr_text_cleaned" / "tsinghua_gas_turbine_books"
REPORT_DIR = REPO_ROOT / "data_pipeline" / "reports"
TSV_PREFIX = re.compile(r"^[1-5]\t")
CLOSING_PUNCTUATION = ".,;:!?)]}%\u2103\uff0c\u3002\uff1b\uff1a\uff01\uff1f\u3001"
DELIVERY_TEXT_NAME = "OCR纯文本_已清洗.txt"
DELIVERY_SUMMARY_NAME = "OCR清洗摘要.json"


@dataclass(frozen=True)
class TsvRow:
    level: int
    block_num: int
    par_num: int
    line_num: int
    word_num: int
    text: str

    @property
    def line_key(self) -> tuple[int, int, int]:
        return (self.block_num, self.par_num, self.line_num)


def resolve_repo_path(value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def manifest_pages_path(manifest_path: Path, manifest: dict[str, Any]) -> Path:
    raw_path = Path(str(manifest["pages_jsonl"]))
    if raw_path.exists():
        return raw_path
    fallback = manifest_path.parent / "pages.jsonl"
    if fallback.exists():
        return fallback
    return raw_path


def parse_tesseract_tsv_row(line: str) -> TsvRow | None:
    if not TSV_PREFIX.match(line):
        return None
    parts = line.split("\t")
    if len(parts) < 11:
        return None
    try:
        level = int(parts[0])
        int(parts[1])
        block_num = int(parts[2])
        par_num = int(parts[3])
        line_num = int(parts[4])
        word_num = int(parts[5])
        int(parts[6])
        int(parts[7])
        int(parts[8])
        int(parts[9])
        float(parts[10])
    except ValueError:
        return None
    text = "\t".join(parts[11:]) if len(parts) > 11 else ""
    return TsvRow(
        level=level,
        block_num=block_num,
        par_num=par_num,
        line_num=line_num,
        word_num=word_num,
        text=text,
    )


def is_cjk(char: str) -> bool:
    code = ord(char)
    return 0x3400 <= code <= 0x4DBF or 0x4E00 <= code <= 0x9FFF or 0xF900 <= code <= 0xFAFF


def has_ascii_alnum(text: str) -> bool:
    return any(char.isascii() and char.isalnum() for char in text)


def needs_space_between(left: str, right: str) -> bool:
    if not left or not right:
        return False
    if right[0] in CLOSING_PUNCTUATION:
        return False
    if left[-1] in "([{":
        return False
    if is_cjk(left[-1]) or is_cjk(right[0]):
        return False
    return has_ascii_alnum(left) and has_ascii_alnum(right)


def join_ocr_words(words: list[str]) -> str:
    output = ""
    for word in words:
        if not word:
            continue
        if output and needs_space_between(output, word):
            output += " "
        output += word
    return output.strip()


def fallback_line_texts(page: dict[str, Any]) -> list[str]:
    lines = page.get("lines") or []
    if lines and isinstance(lines[0], dict):
        return [str(item.get("text") or "").strip() for item in lines if str(item.get("text") or "").strip()]
    return [str(item).strip() for item in lines if str(item).strip()]


def clean_text_payload(text: str, *, fallback_lines: list[str] | None = None) -> tuple[str, dict[str, Any]]:
    cleaned_lines: list[str] = []
    pending_key: tuple[int, int, int] | None = None
    pending_words: list[str] = []
    tsv_rows_removed = 0
    tsv_word_rows_used = 0

    def flush_pending_words() -> None:
        nonlocal pending_key, pending_words
        if pending_words:
            line = join_ocr_words(pending_words)
            if line:
                cleaned_lines.append(line)
        pending_key = None
        pending_words = []

    for raw_line in str(text or "").splitlines():
        row = parse_tesseract_tsv_row(raw_line)
        if row is not None:
            tsv_rows_removed += 1
            if row.level == 5 and row.text.strip():
                if pending_key is not None and row.line_key != pending_key:
                    flush_pending_words()
                pending_key = row.line_key
                pending_words.append(row.text.strip())
                tsv_word_rows_used += 1
            continue
        flush_pending_words()
        line = raw_line.strip()
        if line:
            cleaned_lines.append(line)

    flush_pending_words()

    fallback_used = False
    if not cleaned_lines and fallback_lines:
        cleaned_lines = [line.strip() for line in fallback_lines if line.strip()]
        fallback_used = True

    cleaned = "\n".join(cleaned_lines).strip()
    return cleaned, {
        "original_line_count": len(str(text or "").splitlines()),
        "cleaned_line_count": len(cleaned.splitlines()) if cleaned else 0,
        "tsv_rows_removed": tsv_rows_removed,
        "tsv_word_rows_used": tsv_word_rows_used,
        "fallback_lines_used": fallback_used,
    }


def clean_page(page: dict[str, Any]) -> dict[str, Any]:
    original_text = str(page.get("text") or "")
    cleaned_text, stats = clean_text_payload(original_text, fallback_lines=fallback_line_texts(page))
    cleaned = dict(page)
    cleaned["text"] = cleaned_text
    cleaned["char_count"] = len(cleaned_text)
    cleaned["line_count"] = len(cleaned_text.splitlines()) if cleaned_text else 0
    cleaned["clean_line_texts"] = cleaned_text.splitlines()
    cleaned["cleaning"] = {
        **stats,
        "original_char_count": len(original_text),
        "cleaned_char_count": len(cleaned_text),
        "method": "strip_tesseract_tsv_keep_recognized_text",
    }
    return cleaned


def document_text(pages: list[dict[str, Any]], pdf_name: str) -> str:
    lines = [f"# {pdf_name}", ""]
    for page in pages:
        lines.extend([f"## Page {page['page_num']}", "", str(page.get("text") or "").strip(), ""])
    return "\n".join(lines).rstrip() + "\n"


def summarize_pages(source_file: str, pages: list[dict[str, Any]]) -> dict[str, Any]:
    cleanings = [page.get("cleaning") or {} for page in pages]
    return {
        "source_file": source_file,
        "pages": len(pages),
        "pages_with_text": sum(1 for page in pages if str(page.get("text") or "").strip()),
        "char_count": sum(int(page.get("char_count") or 0) for page in pages),
        "line_count": sum(int(page.get("line_count") or 0) for page in pages),
        "pages_with_tsv_removed": sum(1 for item in cleanings if int(item.get("tsv_rows_removed") or 0) > 0),
        "tsv_rows_removed": sum(int(item.get("tsv_rows_removed") or 0) for item in cleanings),
        "tsv_word_rows_used": sum(int(item.get("tsv_word_rows_used") or 0) for item in cleanings),
        "original_char_count": sum(int(item.get("original_char_count") or 0) for item in cleanings),
        "cleaned_char_count": sum(int(item.get("cleaned_char_count") or 0) for item in cleanings),
    }


def process_document_dir(input_dir: Path, output_dir: Path) -> dict[str, Any]:
    manifest_path = input_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    pages_path = manifest_pages_path(manifest_path, manifest)
    pages = [clean_page(page) for page in load_jsonl(pages_path)]
    source_file = str(manifest.get("source_file") or input_dir.name)

    output_dir.mkdir(parents=True, exist_ok=True)
    output_pages_path = output_dir / "pages.jsonl"
    output_document_path = output_dir / "document.txt"
    output_manifest_path = output_dir / "manifest.json"

    write_jsonl(output_pages_path, pages)
    output_document_path.write_text(document_text(pages, source_file), encoding="utf-8")

    summary = summarize_pages(source_file, pages)
    cleaned_manifest = {
        **manifest,
        "output_dir": str(output_dir),
        "pages_jsonl": str(output_pages_path),
        "document_txt": str(output_document_path),
        "pages_with_text": summary["pages_with_text"],
        "char_count": summary["char_count"],
        "line_count": summary["line_count"],
        "cleaned_from": str(input_dir),
        "cleaning": {
            "method": "strip_tesseract_tsv_keep_recognized_text",
            "pages_with_tsv_removed": summary["pages_with_tsv_removed"],
            "tsv_rows_removed": summary["tsv_rows_removed"],
            "tsv_word_rows_used": summary["tsv_word_rows_used"],
            "original_char_count": summary["original_char_count"],
            "cleaned_char_count": summary["cleaned_char_count"],
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        },
    }
    output_manifest_path.write_text(json.dumps(cleaned_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        **summary,
        "input_dir": str(input_dir),
        "output_dir": str(output_dir),
        "pages_jsonl": str(output_pages_path),
        "document_txt": str(output_document_path),
        "manifest": str(output_manifest_path),
    }


def process_root(input_root: Path, output_root: Path) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for manifest_path in sorted(input_root.glob("*/manifest.json")):
        input_dir = manifest_path.parent
        output_dir = output_root / input_dir.name
        summaries.append(process_document_dir(input_dir, output_dir))
    return summaries


def find_default_delivery_root() -> Path | None:
    roots = sorted(REPO_ROOT.glob("00_*"))
    for root in roots:
        for child in root.glob("02_OCR*"):
            if child.is_dir():
                return child
    return None


def write_delivery_sidecars(delivery_root: Path, summaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_source = {str(summary["source_file"]): summary for summary in summaries}
    by_dir = {Path(str(summary["output_dir"])).name: summary for summary in summaries}
    written: list[dict[str, Any]] = []
    for manifest_path in sorted(delivery_root.glob("**/manifest.json")):
        parent = manifest_path.parent
        if not (parent / "OCR全文.txt").exists():
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        summary = by_source.get(str(manifest.get("source_file") or "")) or by_dir.get(parent.name)
        if not summary:
            continue
        clean_text = Path(str(summary["document_txt"])).read_text(encoding="utf-8")
        sidecar_text = parent / DELIVERY_TEXT_NAME
        sidecar_summary = parent / DELIVERY_SUMMARY_NAME
        sidecar_text.write_text(clean_text, encoding="utf-8")
        sidecar_summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        written.append(
            {
                "source_file": summary["source_file"],
                "delivery_dir": str(parent),
                "text": str(sidecar_text),
                "summary": str(sidecar_summary),
            }
        )
    return written


def write_report(summaries: list[dict[str, Any]], sidecars: list[dict[str, Any]], report_stem: str) -> dict[str, Path]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now().isoformat(timespec="seconds")
    totals = {
        "documents": len(summaries),
        "pages": sum(int(item["pages"]) for item in summaries),
        "pages_with_tsv_removed": sum(int(item["pages_with_tsv_removed"]) for item in summaries),
        "tsv_rows_removed": sum(int(item["tsv_rows_removed"]) for item in summaries),
        "tsv_word_rows_used": sum(int(item["tsv_word_rows_used"]) for item in summaries),
        "original_char_count": sum(int(item["original_char_count"]) for item in summaries),
        "cleaned_char_count": sum(int(item["cleaned_char_count"]) for item in summaries),
        "delivery_sidecars": len(sidecars),
    }
    payload = {
        "generated_at": generated_at,
        "totals": totals,
        "documents": summaries,
        "delivery_sidecars": sidecars,
    }
    json_path = REPORT_DIR / f"{report_stem}.json"
    md_path = REPORT_DIR / f"{report_stem}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# OCR Clean Text Report",
        "",
        f"- Generated at: `{generated_at}`",
        f"- Documents: {totals['documents']}",
        f"- Pages: {totals['pages']}",
        f"- Pages with TSV removed: {totals['pages_with_tsv_removed']}",
        f"- TSV rows removed: {totals['tsv_rows_removed']}",
        f"- TSV word rows used: {totals['tsv_word_rows_used']}",
        f"- Original text chars: {totals['original_char_count']}",
        f"- Cleaned text chars: {totals['cleaned_char_count']}",
        f"- Delivery sidecars: {totals['delivery_sidecars']}",
        "",
        "| Document | Pages | TSV pages | TSV rows removed | Clean chars | Output |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for item in summaries:
        name = str(item["source_file"]).replace("|", " ")
        if len(name) > 80:
            name = name[:79] + "..."
        lines.append(
            f"| {name} | {item['pages']} | {item['pages_with_tsv_removed']} | "
            f"{item['tsv_rows_removed']} | {item['cleaned_char_count']} | `{item['document_txt']}` |"
        )
    md_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return {"json": json_path, "markdown": md_path}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Clean OCR document text polluted by Tesseract TSV rows.")
    parser.add_argument("--input-root", default=str(DEFAULT_INPUT_ROOT), help="OCR root with document manifest folders.")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT), help="Destination root for clean OCR text.")
    parser.add_argument("--report-stem", default="ocr_text_cleaning_20260522", help="Report filename stem.")
    parser.add_argument("--write-delivery-sidecars", action="store_true", help="Write clean text next to delivered OCR files.")
    parser.add_argument("--delivery-root", default="", help="Delivery root. Defaults to the first 00_*/02_OCR* folder.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    input_root = resolve_repo_path(args.input_root)
    output_root = resolve_repo_path(args.output_root)
    summaries = process_root(input_root, output_root)
    sidecars: list[dict[str, Any]] = []
    if args.write_delivery_sidecars:
        delivery_root = resolve_repo_path(args.delivery_root) if args.delivery_root else find_default_delivery_root()
        if delivery_root is not None and delivery_root.exists():
            sidecars = write_delivery_sidecars(delivery_root, summaries)
    reports = write_report(summaries, sidecars, args.report_stem)
    print(
        json.dumps(
            {
                "event": "ocr_text_cleaning_done",
                "input_root": str(input_root),
                "output_root": str(output_root),
                "documents": len(summaries),
                "tsv_rows_removed": sum(int(item["tsv_rows_removed"]) for item in summaries),
                "delivery_sidecars": len(sidecars),
                "reports": {key: str(value) for key, value in reports.items()},
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
