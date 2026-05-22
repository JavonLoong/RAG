from __future__ import annotations

import argparse
import html
import json
import re
import shutil
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = REPO_ROOT / "data_pipeline" / "raw" / "tsinghua_gas_turbine_books"
OCR_ROOT = REPO_ROOT / "data_pipeline" / "ocr_layout_aware_tesseract" / "tsinghua_gas_turbine_books"
ACCEPTANCE_JSON = REPO_ROOT / "data_pipeline" / "reports" / "ocr_delivery_acceptance_20260517.json"
HUMAN_DIR = REPO_ROOT / "00_项目成果总览_先看这里" / "02_OCR结果_13本扫描PDF"
OUT_DIR = HUMAN_DIR / "OCR人工抽检样本包"


def safe_name(value: str, limit: int = 60) -> str:
    value = re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", value, flags=re.UNICODE).strip("_")
    return value[:limit] or "sample"


def compact(value: Any, limit: int = 900) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "..."


def load_pages(path: Path) -> dict[int, dict[str, Any]]:
    pages: dict[int, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                page = json.loads(line)
                pages[int(page["page_num"])] = page
    return pages


def resolve_repo_path(value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path


def risk_score(row: dict[str, Any]) -> int:
    risks = row.get("risks") or []
    score = 0
    if "版面顺序high" in risks:
        score += 100
    if "平均置信度偏低" in risks:
        score += 30
    if "无文字" in risks:
        score += 20
    if "版面顺序medium" in risks:
        score += 15
    return score


def choose_samples(payload: dict[str, Any], max_per_doc: int) -> list[dict[str, Any]]:
    by_doc: dict[str, list[dict[str, Any]]] = {}
    for row in payload["risk_pages"]:
        by_doc.setdefault(row["source_file"], []).append(row)

    samples: list[dict[str, Any]] = []
    for doc in payload["documents"]:
        source_file = doc["source_file"]
        risks = sorted(by_doc.get(source_file, []), key=lambda row: (-risk_score(row), row["page_num"]))
        selected = risks[:max_per_doc]
        if not selected:
            selected = [
                {
                    "source_file": source_file,
                    "page_num": max(1, doc["target_pages"] // 2),
                    "risks": ["代表性普通页"],
                    "layout_risk": "unknown",
                    "avg_confidence": doc.get("avg_confidence_mean", 0.0),
                    "char_count": 0,
                    "line_count": 0,
                    "preview": "",
                }
            ]
        samples.extend(selected)
    return samples


def main() -> int:
    parser = argparse.ArgumentParser(description="Build an OCR spot-check HTML pack.")
    parser.add_argument("--acceptance-json", default=str(ACCEPTANCE_JSON))
    parser.add_argument("--ocr-root", default=str(OCR_ROOT))
    parser.add_argument("--out-dir", default=str(OUT_DIR))
    parser.add_argument("--title", default="OCR 人工抽检样本包")
    parser.add_argument("--max-per-doc", type=int, default=2)
    parser.add_argument("--render-scale", type=float, default=0.7)
    args = parser.parse_args()

    import fitz

    acceptance_json = resolve_repo_path(args.acceptance_json)
    ocr_root = resolve_repo_path(args.ocr_root)
    out_dir = resolve_repo_path(args.out_dir)
    payload = json.loads(acceptance_json.read_text(encoding="utf-8"))
    samples = choose_samples(payload, args.max_per_doc)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest_by_source = {}
    for manifest_path in sorted(ocr_root.glob("*/manifest.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest_by_source[manifest["source_file"]] = manifest

    rows = []
    for index, sample in enumerate(samples, start=1):
        source_file = sample["source_file"]
        page_num = int(sample["page_num"])
        pdf_path = RAW_DIR / source_file
        manifest = manifest_by_source[source_file]
        pages = load_pages(Path(manifest["pages_jsonl"]))
        page = pages.get(page_num) or {}

        doc = fitz.open(pdf_path)
        pdf_page = doc.load_page(page_num - 1)
        pix = pdf_page.get_pixmap(matrix=fitz.Matrix(args.render_scale, args.render_scale), alpha=False)
        image_name = f"{index:02d}_{page_num:04d}_{safe_name(source_file, 38)}.png"
        image_path = out_dir / image_name
        pix.save(image_path)

        rows.append(
            {
                "index": index,
                "source_file": source_file,
                "page_num": page_num,
                "risks": sample.get("risks") or [],
                "layout_risk": sample.get("layout_risk"),
                "avg_confidence": sample.get("avg_confidence"),
                "char_count": page.get("char_count", sample.get("char_count")),
                "line_count": page.get("line_count", sample.get("line_count")),
                "image_name": image_name,
                "ocr_text": compact(page.get("text") or sample.get("preview"), 1200),
            }
        )

    html_lines = [
        "<!doctype html>",
        "<html lang=\"zh-CN\">",
        "<head>",
        "<meta charset=\"utf-8\">",
        f"<title>{html.escape(args.title)}</title>",
        "<style>",
        "body{font-family:Arial,'Microsoft YaHei',sans-serif;margin:24px;background:#f7f7f3;color:#202421}",
        "h1{font-size:28px} .item{display:grid;grid-template-columns:minmax(320px,48%) 1fr;gap:18px;margin:22px 0;padding:16px;background:white;border:1px solid #ddd}",
        "img{width:100%;border:1px solid #ccc;background:#fafafa} pre{white-space:pre-wrap;line-height:1.55;font-size:14px;background:#f4f4f4;padding:12px;max-height:520px;overflow:auto}",
        ".meta{font-size:14px;color:#555}.risk{font-weight:bold;color:#9a3412}",
        "</style>",
        "</head><body>",
        f"<h1>{html.escape(args.title)}</h1>",
        "<p>左侧是原 PDF 页面渲染图，右侧是对应 OCR 文本。用于交付前快速肉眼核对，不代表全量人工校对。</p>",
    ]
    for row in rows:
        risks = "、".join(row["risks"])
        html_lines.extend(
            [
                "<section class=\"item\">",
                f"<div><img src=\"{html.escape(row['image_name'])}\" alt=\"sample {row['index']}\"></div>",
                "<div>",
                f"<h2>{row['index']:02d}. Page {row['page_num']}</h2>",
                f"<p class=\"meta\">{html.escape(row['source_file'])}</p>",
                f"<p class=\"risk\">风险：{html.escape(risks)}；版面：{html.escape(str(row['layout_risk']))}；置信度：{row['avg_confidence']}</p>",
                f"<p class=\"meta\">字符数：{row['char_count']}；行数：{row['line_count']}</p>",
                f"<pre>{html.escape(row['ocr_text'])}</pre>",
                "</div></section>",
            ]
        )
    html_lines.append("</body></html>")
    html_path = out_dir / "OCR人工抽检样本.html"
    html_path.write_text("\n".join(html_lines), encoding="utf-8")
    (out_dir / "sample_manifest.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"html": str(html_path), "samples": len(rows)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
