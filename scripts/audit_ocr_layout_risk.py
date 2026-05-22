from __future__ import annotations

import argparse
import json
import os
import sys
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
REPORT_DIR = REPO_ROOT / "data_pipeline" / "reports"
HUMAN_DIR = REPO_ROOT / "00_项目成果总览_先看这里" / "02_OCR结果_13本扫描PDF"


def load_ocr_pdf_names() -> list[str]:
    report = json.loads(EXTRACTABILITY_REPORT.read_text(encoding="utf-8"))
    pdfs = report.get("pdfs") or []
    names = [str(item["file_name"]) for item in pdfs if item.get("classification") == "needs_ocr"]
    return sorted(names)


def sample_page_indexes(total_pages: int, samples: int) -> list[int]:
    if total_pages <= 0:
        return []
    if samples <= 1:
        return [min(total_pages - 1, max(0, total_pages // 2))]
    # Skip cover-ish first pages when possible, then spread samples across the book.
    start = min(max(5, total_pages // 20), max(total_pages - 1, 0))
    end = max(start, total_pages - 1)
    indexes = {
        round(start + (end - start) * i / max(samples - 1, 1))
        for i in range(samples)
    }
    return sorted(min(total_pages - 1, max(0, index)) for index in indexes)


def normalize_box(raw_box: Any) -> tuple[float, float, float, float]:
    points = raw_box or []
    xs = [float(point[0]) for point in points if len(point) >= 2]
    ys = [float(point[1]) for point in points if len(point) >= 2]
    if not xs or not ys:
        return (0.0, 0.0, 0.0, 0.0)
    return (min(xs), min(ys), max(xs), max(ys))


def classify_page(result: list[Any] | None, width: int, height: int) -> dict[str, Any]:
    zones: list[str] = []
    left_only = 0
    right_only = 0
    wide_or_center = 0
    text_boxes = 0
    previews: list[str] = []

    for item in result or []:
        if len(item) < 2:
            continue
        text = str(item[1]).strip()
        if not text:
            continue
        x0, _y0, x1, _y1 = normalize_box(item[0])
        text_boxes += 1
        if x1 < width * 0.52:
            left_only += 1
            zones.append("L")
        elif x0 > width * 0.48:
            right_only += 1
            zones.append("R")
        else:
            wide_or_center += 1
            zones.append("W")
        if len(previews) < 8:
            previews.append(text)

    compact_zones = [zone for zone in zones if zone in {"L", "R"}]
    transitions = sum(
        1 for before, after in zip(compact_zones, compact_zones[1:]) if before != after
    )
    two_column_candidate = left_only >= 5 and right_only >= 5
    if not two_column_candidate:
        risk = "低"
    elif transitions >= 4:
        risk = "高"
    elif transitions >= 2:
        risk = "中"
    else:
        risk = "中"

    return {
        "text_boxes": text_boxes,
        "left_only_boxes": left_only,
        "right_only_boxes": right_only,
        "wide_or_center_boxes": wide_or_center,
        "two_column_candidate": two_column_candidate,
        "left_right_transitions": transitions,
        "layout_order_risk": risk,
        "zone_sequence_preview": "".join(compact_zones[:80]),
        "text_preview": previews,
        "image_width": width,
        "image_height": height,
    }


def audit(args: argparse.Namespace) -> dict[str, Any]:
    os.environ.setdefault("OMP_NUM_THREADS", str(args.onnx_threads))
    os.environ.setdefault("OPENBLAS_NUM_THREADS", str(args.onnx_threads))
    os.environ.setdefault("MKL_NUM_THREADS", str(args.onnx_threads))
    thread_count = max(1, args.onnx_threads)
    ocr = RapidOCR(
        use_cls=False,
        **{
            "Det.intra_op_num_threads": thread_count,
            "Det.inter_op_num_threads": thread_count,
            "Cls.intra_op_num_threads": thread_count,
            "Cls.inter_op_num_threads": thread_count,
            "Rec.intra_op_num_threads": thread_count,
            "Rec.inter_op_num_threads": thread_count,
        },
    )

    documents: list[dict[str, Any]] = []
    pdf_names = load_ocr_pdf_names()
    if args.max_pdfs:
        pdf_names = pdf_names[: args.max_pdfs]
    for pdf_number, pdf_name in enumerate(pdf_names, start=1):
        print(json.dumps({"event": "layout_audit_pdf_start", "index": pdf_number, "source_file": pdf_name}, ensure_ascii=False))
        pdf_path = RAW_DIR / pdf_name
        doc = fitz.open(pdf_path)
        pages: list[dict[str, Any]] = []
        for page_index in sample_page_indexes(len(doc), args.samples_per_pdf):
            page = doc.load_page(page_index)
            pix = page.get_pixmap(matrix=fitz.Matrix(args.render_scale, args.render_scale), alpha=False)
            result, _timings = ocr(pix.tobytes("png"))
            page_payload = classify_page(result, pix.width, pix.height)
            page_payload["page_num"] = page_index + 1
            pages.append(page_payload)
        risk_counts: dict[str, int] = {}
        for page in pages:
            risk = str(page["layout_order_risk"])
            risk_counts[risk] = risk_counts.get(risk, 0) + 1
        two_column_pages = sum(1 for page in pages if page["two_column_candidate"])
        documents.append(
            {
                "source_file": pdf_name,
                "total_pages": len(doc),
                "sampled_pages": len(pages),
                "two_column_sample_pages": two_column_pages,
                "risk_counts": risk_counts,
                "pages": pages,
            }
        )

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "samples_per_pdf": args.samples_per_pdf,
        "render_scale": args.render_scale,
        "note": "This is a sampled layout audit. It re-runs OCR on sampled pages and uses OCR boxes to estimate two-column reading-order risk.",
        "documents": documents,
    }


def write_markdown(path: Path, payload: dict[str, Any]) -> None:
    total_samples = sum(item["sampled_pages"] for item in payload["documents"])
    two_column_samples = sum(item["two_column_sample_pages"] for item in payload["documents"])
    high_pages = sum(item["risk_counts"].get("高", 0) for item in payload["documents"])
    medium_pages = sum(item["risk_counts"].get("中", 0) for item in payload["documents"])
    lines = [
        "# OCR 两栏版面风险审计",
        "",
        "## 结论",
        "",
        "你的担心是成立的：如果 PDF 是左右两栏，普通 OCR 文本可能把阅读顺序搞错。",
        "",
        "现有全量 OCR 结果只保存了文字行，没有保存坐标框；因此旧结果不能可靠恢复“左栏先读完，再读右栏”的真实顺序。",
        "",
        "这份报告重新抽样跑了一遍带坐标的 OCR，用来估计两栏风险。",
        "",
        "## 抽样结果",
        "",
        f"- 抽样页数：{total_samples}",
        f"- 疑似两栏页：{two_column_samples}",
        f"- 高风险页：{high_pages}",
        f"- 中风险页：{medium_pages}",
        "",
        "## 对当前项目的影响",
        "",
        "- 做普通 RAG 粗检索：仍然可以用，因为它主要需要找候选证据。",
        "- 做知识图谱抽取：风险较高，因为关系抽取依赖句子和段落顺序。",
        "- 做论文引用：不能直接信 OCR 文本，必须回看原 PDF 页图。",
        "",
        "## 修复方向",
        "",
        "1. 以后 OCR 必须保存每一行的坐标框。",
        "2. 对疑似两栏页面，按列重排：先左栏从上到下，再右栏从上到下。",
        "3. 对表格、公式、图注页，单独标记为高风险，不直接用于知识图谱抽取。",
        "4. RAG chunk metadata 里保留 `page_num` 和 layout 风险，回答时能回到原 PDF 复核。",
        "",
        "## 分书结果",
        "",
        "| 文件 | 抽样页 | 疑似两栏页 | 高风险 | 中风险 |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for item in payload["documents"]:
        source = str(item["source_file"]).replace("|", "\\|")[:60]
        lines.append(
            f"| {source} | {item['sampled_pages']} | {item['two_column_sample_pages']} | "
            f"{item['risk_counts'].get('高', 0)} | {item['risk_counts'].get('中', 0)} |"
        )
    lines.extend(["", "## 风险页样例", ""])
    for item in payload["documents"]:
        risky = [page for page in item["pages"] if page["layout_order_risk"] in {"高", "中"}]
        if not risky:
            continue
        lines.append(f"### {item['source_file'][:80]}")
        lines.append("")
        for page in risky[:3]:
            lines.append(
                f"- Page {page['page_num']}: 风险 {page['layout_order_risk']}，"
                f"左栏框 {page['left_only_boxes']}，右栏框 {page['right_only_boxes']}，"
                f"左右切换 {page['left_right_transitions']}，顺序预览 `{page['zone_sequence_preview'][:60]}`"
            )
        lines.append("")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Sample OCR boxes to audit two-column layout risk.")
    parser.add_argument("--max-pdfs", type=int, default=0)
    parser.add_argument("--samples-per-pdf", type=int, default=5)
    parser.add_argument("--render-scale", type=float, default=1.0)
    parser.add_argument("--onnx-threads", type=int, default=1)
    args = parser.parse_args()

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    payload = audit(args)
    json_path = REPORT_DIR / "ocr_layout_risk_audit.json"
    md_path = REPORT_DIR / "ocr_layout_risk_audit.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown(md_path, payload)
    if HUMAN_DIR.exists():
        (HUMAN_DIR / "OCR两栏版面风险审计.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        write_markdown(HUMAN_DIR / "OCR两栏版面风险审计.md", payload)
    print(json.dumps({"markdown": str(md_path), "json": str(json_path)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
