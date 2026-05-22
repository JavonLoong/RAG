from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
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

import fitz  # noqa: E402
from rapidocr_onnxruntime import RapidOCR  # noqa: E402


RAW_DIR = REPO_ROOT / "data_pipeline" / "raw" / "tsinghua_gas_turbine_books"
EXTRACTABILITY_REPORT = REPO_ROOT / "data_pipeline" / "reports" / "pdf_extractability_report.json"
DEFAULT_OCR_ROOT = REPO_ROOT / "data_pipeline" / "ocr" / "tsinghua_gas_turbine_books"
REPORT_DIR = REPO_ROOT / "data_pipeline" / "reports"
LOG_DIR = REPO_ROOT / "observability" / "logs" / "ocr_scanned_pdfs"
TESSERACT_EXE = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
TESSDATA_DIR = Path(r"C:\Users\15410\tessdata-local")


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
        print(json.dumps(payload, ensure_ascii=False))


def stable_id(value: str, length: int = 12) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:length]


def safe_doc_dir(index: int, pdf_name: str) -> str:
    return f"{index:02d}_{stable_id(pdf_name)}"


def resolve_repo_path(value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path


def load_ocr_queue() -> list[dict[str, Any]]:
    if not EXTRACTABILITY_REPORT.exists():
        raise FileNotFoundError(f"PDF extractability report not found: {EXTRACTABILITY_REPORT}")
    report = json.loads(EXTRACTABILITY_REPORT.read_text(encoding="utf-8"))
    pdfs = report.get("pdfs") or []
    queue = [item for item in pdfs if item.get("classification") == "needs_ocr"]
    if not queue:
        raise RuntimeError("No needs_ocr PDF entries found in pdf_extractability_report.json.")
    sorted_queue = sorted(queue, key=lambda item: str(item.get("file_name", "")))
    for index, item in enumerate(sorted_queue, start=1):
        item["_queue_index"] = index
    return sorted_queue


def parse_pdf_indexes(value: str) -> set[int]:
    indexes: set[int] = set()
    if not value.strip():
        return indexes
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_text, end_text = part.split("-", 1)
            start = int(start_text)
            end = int(end_text)
            if end < start:
                raise ValueError(f"Invalid --pdf-indexes range: {part}")
            indexes.update(range(start, end + 1))
        else:
            indexes.add(int(part))
    return indexes


def read_existing_pages(path: Path) -> dict[int, dict[str, Any]]:
    pages: dict[int, dict[str, Any]] = {}
    if not path.exists():
        return pages
    with path.open("r", encoding="utf-8") as handle:
        for line_num, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid OCR JSONL at {path}:{line_num}: {exc}") from exc
            page_num = int(payload["page_num"])
            pages[page_num] = payload
    return pages


def normalize_box(raw_box: Any) -> tuple[float, float, float, float]:
    points = raw_box or []
    xs = [float(point[0]) for point in points if len(point) >= 2]
    ys = [float(point[1]) for point in points if len(point) >= 2]
    if not xs or not ys:
        return (0.0, 0.0, 0.0, 0.0)
    return (min(xs), min(ys), max(xs), max(ys))


def make_line_payload(raw_item: Any, image_width: int) -> dict[str, Any] | None:
    text = str(raw_item[1]).strip() if len(raw_item) > 1 else ""
    if not text:
        return None
    raw_box = raw_item[0] if len(raw_item) > 0 else []
    x0, y0, x1, y1 = normalize_box(raw_box)
    confidence = float(raw_item[2]) if len(raw_item) > 2 else 0.0
    center_x = (x0 + x1) / 2
    if x1 < image_width * 0.52:
        original_zone = "left"
    elif x0 > image_width * 0.48:
        original_zone = "right"
    else:
        original_zone = "wide"
    return {
        "text": text,
        "box": raw_box,
        "x0": round(x0, 2),
        "y0": round(y0, 2),
        "x1": round(x1, 2),
        "y1": round(y1, 2),
        "center_x": round(center_x, 2),
        "original_zone": original_zone,
        "confidence": round(confidence, 4),
    }


def order_lines_layout_aware(lines: list[dict[str, Any]], image_width: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not lines:
        return [], {
            "mode": "layout_aware",
            "reading_order": "empty",
            "two_column_candidate": False,
            "layout_order_risk": "low",
        }

    narrow_lines = [
        line
        for line in lines
        if float(line["x1"]) - float(line["x0"]) < image_width * 0.72
        and len(str(line["text"]).strip()) > 1
    ]
    left_lines = [line for line in narrow_lines if float(line["center_x"]) < image_width * 0.48]
    right_lines = [line for line in narrow_lines if float(line["center_x"]) > image_width * 0.52]
    zones = [line["original_zone"] for line in lines if line["original_zone"] in {"left", "right"}]
    transitions = sum(1 for before, after in zip(zones, zones[1:]) if before != after)
    two_column = len(left_lines) >= 5 and len(right_lines) >= 5

    ordered: list[dict[str, Any]]
    reading_order = "single_column_top_to_bottom"
    wide_body_count = 0
    if two_column:
        body_lines = left_lines + right_lines
        body_top = min(float(line["y0"]) for line in body_lines)
        body_bottom = max(float(line["y1"]) for line in body_lines)
        top_lines: list[dict[str, Any]] = []
        bottom_lines: list[dict[str, Any]] = []
        wide_body_lines: list[dict[str, Any]] = []
        for line in lines:
            if line in left_lines or line in right_lines:
                continue
            y0 = float(line["y0"])
            y1 = float(line["y1"])
            if y1 < body_top:
                top_lines.append(line)
            elif y0 > body_bottom:
                bottom_lines.append(line)
            else:
                wide_body_lines.append(line)
        wide_body_count = len(wide_body_lines)
        for line in top_lines:
            line["layout_column"] = "top"
        for line in left_lines:
            line["layout_column"] = "left"
        for line in right_lines:
            line["layout_column"] = "right"
        for line in wide_body_lines:
            line["layout_column"] = "wide_body"
        for line in bottom_lines:
            line["layout_column"] = "bottom"
        ordered = (
            sorted(top_lines, key=lambda line: (float(line["y0"]), float(line["x0"])))
            + sorted(left_lines, key=lambda line: (float(line["y0"]), float(line["x0"])))
            + sorted(wide_body_lines, key=lambda line: (float(line["y0"]), float(line["x0"])))
            + sorted(right_lines, key=lambda line: (float(line["y0"]), float(line["x0"])))
            + sorted(bottom_lines, key=lambda line: (float(line["y0"]), float(line["x0"])))
        )
        reading_order = "top_then_left_column_then_wide_body_then_right_column_then_bottom"
    else:
        ordered = sorted(lines, key=lambda line: (float(line["y0"]), float(line["x0"])))
        for line in ordered:
            line["layout_column"] = "single"

    if two_column and (transitions >= 4 or wide_body_count > 3):
        risk = "high"
    elif two_column:
        risk = "medium"
    else:
        risk = "low"

    for index, line in enumerate(ordered):
        line["reading_order_index"] = index

    return ordered, {
        "mode": "layout_aware",
        "reading_order": reading_order,
        "two_column_candidate": two_column,
        "layout_order_risk": risk,
        "left_line_count": len(left_lines),
        "right_line_count": len(right_lines),
        "wide_body_line_count": wide_body_count,
        "original_left_right_transitions": transitions,
        "original_zone_sequence": "".join(zone[0].upper() for zone in zones[:120]),
    }


def order_lines_visual(lines: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    ordered = sorted(lines, key=lambda line: (float(line["y0"]), float(line["x0"])))
    for index, line in enumerate(ordered):
        line["layout_column"] = "visual"
        line["reading_order_index"] = index
    return ordered, {
        "mode": "visual",
        "reading_order": "top_to_bottom_left_to_right",
        "two_column_candidate": False,
        "layout_order_risk": "unknown",
    }


def ocr_page_rapidocr(ocr: RapidOCR, page: fitz.Page, scale: float, layout_aware: bool) -> dict[str, Any]:
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
    image_bytes = pix.tobytes("png")
    result, timings = ocr(image_bytes)
    lines: list[dict[str, Any]] = []
    if result:
        for item in result:
            line = make_line_payload(item, pix.width)
            if line:
                lines.append(line)

    if layout_aware:
        ordered_lines, layout = order_lines_layout_aware(lines, pix.width)
    else:
        ordered_lines, layout = order_lines_visual(lines)

    page_text = "\n".join(line["text"] for line in ordered_lines).strip()
    avg_confidence = (
        round(sum(float(line["confidence"]) for line in ordered_lines) / len(ordered_lines), 4)
        if ordered_lines
        else 0.0
    )
    return {
        "text": page_text,
        "char_count": len(page_text),
        "line_count": len(ordered_lines),
        "avg_confidence": avg_confidence,
        "timings": timings or [],
        "lines": ordered_lines,
        "raw_lines": lines,
        "layout": layout,
        "image_width": pix.width,
        "image_height": pix.height,
    }


def ocr_page_tesseract(page: fitz.Page, scale: float, language: str, psm: int) -> dict[str, Any]:
    if not TESSERACT_EXE.exists():
        raise FileNotFoundError(f"Tesseract executable not found: {TESSERACT_EXE}")
    if not TESSDATA_DIR.exists():
        raise FileNotFoundError(f"Tesseract tessdata directory not found: {TESSDATA_DIR}")

    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
    with tempfile.TemporaryDirectory(prefix="rag_tess_") as temp_dir:
        temp_path = Path(temp_dir)
        image_path = temp_path / "page.png"
        output_base = temp_path / "out"
        pix.save(image_path)
        completed = subprocess.run(
            [
                str(TESSERACT_EXE),
                str(image_path),
                str(output_base),
                "--tessdata-dir",
                str(TESSDATA_DIR),
                "-l",
                language,
                "--psm",
                str(psm),
                "-c",
                "tessedit_create_tsv=1",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f"tesseract failed with code {completed.returncode}: {completed.stderr.strip()}"
            )
        output_tsv = output_base.with_suffix(".tsv")
        rows: list[dict[str, str]] = []
        with output_tsv.open("r", encoding="utf-8", errors="replace", newline="") as handle:
            rows = list(csv.DictReader(handle, delimiter="\t"))

    grouped: dict[tuple[str, str, str], list[dict[str, str]]] = {}
    for row in rows:
        text = str(row.get("text") or "").strip()
        if not text or row.get("level") != "5":
            continue
        key = (str(row.get("block_num") or ""), str(row.get("par_num") or ""), str(row.get("line_num") or ""))
        grouped.setdefault(key, []).append(row)

    def join_tokens(tokens: list[str]) -> str:
        value = ""
        for token in tokens:
            if value and value[-1].isascii() and value[-1].isalnum() and token[:1].isascii() and token[:1].isalnum():
                value += " "
            value += token
        return value.strip()

    lines: list[dict[str, Any]] = []
    for words in grouped.values():
        boxes = []
        confidences = []
        tokens = []
        for word in words:
            left = int(float(word.get("left") or 0))
            top = int(float(word.get("top") or 0))
            width = int(float(word.get("width") or 0))
            height = int(float(word.get("height") or 0))
            boxes.append((left, top, left + width, top + height))
            try:
                conf = float(word.get("conf") or 0)
                if conf >= 0:
                    confidences.append(conf / 100)
            except ValueError:
                pass
            tokens.append(str(word.get("text") or "").strip())
        if not boxes:
            continue
        x0 = min(box[0] for box in boxes)
        y0 = min(box[1] for box in boxes)
        x1 = max(box[2] for box in boxes)
        y1 = max(box[3] for box in boxes)
        center_x = (x0 + x1) / 2
        if x1 < pix.width * 0.52:
            original_zone = "left"
        elif x0 > pix.width * 0.48:
            original_zone = "right"
        else:
            original_zone = "wide"
        text = join_tokens(tokens)
        if text:
            lines.append(
                {
                    "text": text,
                    "box": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]],
                    "x0": x0,
                    "y0": y0,
                    "x1": x1,
                    "y1": y1,
                    "center_x": round(center_x, 2),
                    "original_zone": original_zone,
                    "confidence": round(sum(confidences) / len(confidences), 4) if confidences else 0.0,
                }
            )

    ordered_lines, layout = order_lines_layout_aware(lines, pix.width)
    page_text = "\n".join(line["text"] for line in ordered_lines).strip()
    avg_confidence = (
        round(sum(float(line["confidence"]) for line in ordered_lines) / len(ordered_lines), 4)
        if ordered_lines
        else 0.0
    )
    return {
        "text": page_text,
        "char_count": len(page_text),
        "line_count": len(ordered_lines),
        "avg_confidence": avg_confidence,
        "timings": [],
        "lines": ordered_lines,
        "raw_lines": lines,
        "layout": layout,
        "image_width": pix.width,
        "image_height": pix.height,
    }


def write_document_text(path: Path, pages: list[dict[str, Any]], pdf_name: str) -> None:
    lines = [f"# {pdf_name}", ""]
    for page in pages:
        lines.extend(
            [
                f"## Page {page['page_num']}",
                "",
                page.get("text", "").strip(),
                "",
            ]
        )
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def process_pdf(
    *,
    ocr: RapidOCR | None,
    pdf_item: dict[str, Any],
    index: int,
    args: argparse.Namespace,
    logger: JsonLogger,
) -> dict[str, Any]:
    pdf_name = str(pdf_item["file_name"])
    pdf_path = RAW_DIR / pdf_name
    if not pdf_path.exists():
        raise FileNotFoundError(f"OCR source PDF not found: {pdf_path}")

    output_root = args.output_root_path
    output_dir = output_root / safe_doc_dir(index, pdf_name)
    output_dir.mkdir(parents=True, exist_ok=True)
    pages_jsonl = output_dir / "pages.jsonl"
    document_txt = output_dir / "document.txt"
    manifest_json = output_dir / "manifest.json"

    doc = fitz.open(pdf_path)
    total_pages = len(doc)
    target_pages = min(total_pages, args.max_pages_per_pdf) if args.max_pages_per_pdf else total_pages
    existing_pages = read_existing_pages(pages_jsonl) if args.resume else {}
    processed_before = len(existing_pages)

    logger.write(
        "ocr_pdf_start",
        source_file=pdf_name,
        total_pages=total_pages,
        target_pages=target_pages,
        output_dir=str(output_dir),
        processed_before=processed_before,
        scale=args.render_scale,
    )

    started = time.perf_counter()
    append_mode = "a" if existing_pages else "w"
    with pages_jsonl.open(append_mode, encoding="utf-8") as handle:
        for page_index in range(target_pages):
            page_num = page_index + 1
            if page_num in existing_pages:
                continue
            page_started = time.perf_counter()
            try:
                if args.engine == "tesseract":
                    page_result = ocr_page_tesseract(
                        doc.load_page(page_index),
                        args.render_scale,
                        args.tesseract_lang,
                        args.tesseract_psm,
                    )
                else:
                    if ocr is None:
                        raise RuntimeError("RapidOCR engine was not initialized.")
                    page_result = ocr_page_rapidocr(
                        ocr,
                        doc.load_page(page_index),
                        args.render_scale,
                        args.layout_aware,
                    )
                payload = {
                    "source_file": pdf_name,
                    "page_num": page_num,
                    **page_result,
                    "elapsed_s": round(time.perf_counter() - page_started, 3),
                    "status": "ok",
                }
            except Exception as exc:
                payload = {
                    "source_file": pdf_name,
                    "page_num": page_num,
                    "text": "",
                    "char_count": 0,
                    "line_count": 0,
                    "avg_confidence": 0.0,
                    "elapsed_s": round(time.perf_counter() - page_started, 3),
                    "status": "error",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
                logger.write("ocr_page_failed", **payload)
                if not args.continue_on_error:
                    raise

            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
            handle.flush()
            existing_pages[page_num] = payload
            if page_num % args.progress_every == 0 or page_num == target_pages:
                logger.write(
                    "ocr_pdf_progress",
                    source_file=pdf_name,
                    page_num=page_num,
                    target_pages=target_pages,
                    chars_so_far=sum(int(p.get("char_count") or 0) for p in existing_pages.values()),
                )

    ordered_pages = [existing_pages[num] for num in sorted(existing_pages) if num <= target_pages]
    char_count = sum(int(page.get("char_count") or 0) for page in ordered_pages)
    line_count = sum(int(page.get("line_count") or 0) for page in ordered_pages)
    pages_with_text = sum(1 for page in ordered_pages if int(page.get("char_count") or 0) > 0)
    errors = [page for page in ordered_pages if page.get("status") == "error"]
    elapsed_s = round(time.perf_counter() - started, 3)

    write_document_text(document_txt, ordered_pages, pdf_name)
    manifest = {
        "source_file": pdf_name,
        "source_path": str(pdf_path),
        "output_dir": str(output_dir),
        "pages_jsonl": str(pages_jsonl),
        "document_txt": str(document_txt),
        "total_pages": total_pages,
        "target_pages": target_pages,
        "pages_ocr_done": len(ordered_pages),
        "pages_with_text": pages_with_text,
        "char_count": char_count,
        "line_count": line_count,
        "error_count": len(errors),
        "render_scale": args.render_scale,
        "engine": args.engine,
        "layout_aware": bool(args.layout_aware),
        "elapsed_s": elapsed_s,
        "status": "success" if len(ordered_pages) >= target_pages and not errors else "partial",
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    manifest_json.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.write("ocr_pdf_done", **manifest)
    return manifest


def write_reports(manifests: list[dict[str, Any]], log_path: Path, output_root: Path) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    output_root.mkdir(parents=True, exist_ok=True)
    suffix = "layout_aware" if "ocr_layout_aware" in str(output_root) else "scanned_pdfs"
    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "ocr_root": str(output_root),
        "log_path": str(log_path),
        "pdf_count": len(manifests),
        "success_count": sum(1 for item in manifests if item.get("status") == "success"),
        "partial_count": sum(1 for item in manifests if item.get("status") == "partial"),
        "total_pages": sum(int(item.get("total_pages") or 0) for item in manifests),
        "pages_ocr_done": sum(int(item.get("pages_ocr_done") or 0) for item in manifests),
        "pages_with_text": sum(int(item.get("pages_with_text") or 0) for item in manifests),
        "char_count": sum(int(item.get("char_count") or 0) for item in manifests),
        "line_count": sum(int(item.get("line_count") or 0) for item in manifests),
        "error_count": sum(int(item.get("error_count") or 0) for item in manifests),
        "documents": manifests,
    }
    (REPORT_DIR / f"ocr_{suffix}_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    with (REPORT_DIR / f"ocr_{suffix}_summary.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "source_file",
                "status",
                "total_pages",
                "target_pages",
                "pages_ocr_done",
                "pages_with_text",
                "char_count",
                "line_count",
                "error_count",
                "elapsed_s",
                "document_txt",
            ],
        )
        writer.writeheader()
        for item in manifests:
            writer.writerow({field: item.get(field, "") for field in writer.fieldnames})

    lines = [
        "# OCR Scanned PDFs Summary",
        "",
        f"- Generated at: `{summary['generated_at']}`",
        f"- OCR root: `{summary['ocr_root']}`",
        f"- PDFs processed: {summary['pdf_count']}",
        f"- Success: {summary['success_count']}",
        f"- Partial: {summary['partial_count']}",
        f"- Pages OCR done: {summary['pages_ocr_done']} / {summary['total_pages']}",
        f"- Pages with text: {summary['pages_with_text']}",
        f"- OCR chars: {summary['char_count']}",
        f"- Errors: {summary['error_count']}",
        "",
        "| PDF | Status | Pages | Text pages | Chars | Errors | Text file |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for item in manifests:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(item.get("source_file", "")).replace("|", "\\|"),
                    str(item.get("status", "")),
                    f"{item.get('pages_ocr_done', 0)}/{item.get('target_pages', 0)}",
                    str(item.get("pages_with_text", 0)),
                    str(item.get("char_count", 0)),
                    str(item.get("error_count", 0)),
                    f"`{item.get('document_txt', '')}`",
                ]
            )
            + " |"
        )
    (REPORT_DIR / f"ocr_{suffix}_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="OCR PDFs that were classified as needs_ocr.")
    parser.add_argument("--max-pdfs", type=int, default=0, help="Limit number of PDFs for a probe run. 0 means all.")
    parser.add_argument("--pdf-indexes", default="", help="1-based PDF indexes to process, e.g. 1,3,5-7.")
    parser.add_argument("--max-pages-per-pdf", type=int, default=0, help="Limit pages per PDF. 0 means all pages.")
    parser.add_argument("--output-root", default=str(DEFAULT_OCR_ROOT), help="OCR output root directory.")
    parser.add_argument("--layout-aware", action="store_true", help="Store OCR boxes and reorder two-column pages by column.")
    parser.add_argument("--render-scale", type=float, default=1.35, help="PyMuPDF render scale for OCR.")
    parser.add_argument("--engine", choices=["rapidocr", "tesseract"], default="rapidocr")
    parser.add_argument("--tesseract-lang", default="chi_sim+eng")
    parser.add_argument("--tesseract-psm", type=int, default=6)
    parser.add_argument("--progress-every", type=int, default=20)
    parser.add_argument("--onnx-threads", type=int, default=1, help="ONNXRuntime intra/inter threads per OCR process.")
    parser.add_argument("--use-cls", action="store_true", help="Enable orientation classifier. Disabled by default for speed.")
    parser.add_argument("--resume", action="store_true", default=True, help="Resume from existing pages.jsonl.")
    parser.add_argument("--no-resume", action="store_false", dest="resume")
    parser.add_argument("--continue-on-error", action="store_true", default=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.output_root_path = resolve_repo_path(args.output_root)
    os.environ.setdefault("OMP_NUM_THREADS", str(args.onnx_threads))
    os.environ.setdefault("OPENBLAS_NUM_THREADS", str(args.onnx_threads))
    os.environ.setdefault("MKL_NUM_THREADS", str(args.onnx_threads))
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = JsonLogger(LOG_DIR / f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-ocr-scanned-pdfs-{os.getpid()}.jsonl")
    queue = load_ocr_queue()
    pdf_indexes = parse_pdf_indexes(args.pdf_indexes)
    if pdf_indexes:
        queue = [item for item in queue if int(item.get("_queue_index") or 0) in pdf_indexes]
    if args.max_pdfs:
        queue = queue[: args.max_pdfs]

    logger.write(
        "ocr_run_start",
        pdf_count=len(queue),
        raw_dir=str(RAW_DIR),
        ocr_root=str(args.output_root_path),
        max_pages_per_pdf=args.max_pages_per_pdf,
        render_scale=args.render_scale,
        engine=args.engine,
    )
    ocr: RapidOCR | None = None
    if args.engine == "rapidocr":
        thread_count = max(1, args.onnx_threads)
        ocr = RapidOCR(
            use_cls=args.use_cls,
            **{
                "Det.intra_op_num_threads": thread_count,
                "Det.inter_op_num_threads": thread_count,
                "Cls.intra_op_num_threads": thread_count,
                "Cls.inter_op_num_threads": thread_count,
                "Rec.intra_op_num_threads": thread_count,
                "Rec.inter_op_num_threads": thread_count,
            },
        )
    manifests: list[dict[str, Any]] = []
    started = time.perf_counter()
    for item in queue:
        manifests.append(
            process_pdf(
                ocr=ocr,
                pdf_item=item,
                index=int(item.get("_queue_index") or 0),
                args=args,
                logger=logger,
            )
        )

    write_reports(manifests, logger.log_path, args.output_root_path)
    logger.write(
        "ocr_run_done",
        pdf_count=len(manifests),
        elapsed_s=round(time.perf_counter() - started, 3),
        pages_ocr_done=sum(int(item.get("pages_ocr_done") or 0) for item in manifests),
        char_count=sum(int(item.get("char_count") or 0) for item in manifests),
        summary=str(REPORT_DIR / ("ocr_layout_aware_summary.json" if args.layout_aware else "ocr_scanned_pdfs_summary.json")),
    )


if __name__ == "__main__":
    main()
