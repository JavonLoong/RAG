from __future__ import annotations

import hashlib
import io
import json
import shutil
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from pypdf import PdfReader, PdfWriter


REPO_ROOT = Path(__file__).resolve().parents[1]
ACCEPTANCE_ROOT = REPO_ROOT / "evaluation" / "prd_acceptance_current_inputs"
EVIDENCE_DIR = ACCEPTANCE_ROOT / "evidence" / "AC-M2-01"
CANDIDATES_DIR = ACCEPTANCE_ROOT / "candidates"
PDF_TMP_DIR = REPO_ROOT / "tmp" / "pdfs"
SOURCE_PACK = (
    REPO_ROOT
    / "docs"
    / "project_deliverables"
    / "02_OCR结果_13本扫描PDF"
    / "OCR质量高的4本.zip"
)
SAMPLE_DIR = (
    REPO_ROOT
    / "docs"
    / "project_deliverables"
    / "02_OCR结果_13本扫描PDF"
    / "OCR人工抽检样本包_高分辨率修正版"
)
PDFTOPPM = Path(
    r"C:\Users\15410\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\poppler\Library\bin\pdftoppm.exe"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def copy_sample(source_name: str, output_name: str) -> Path:
    source = SAMPLE_DIR / source_name
    if not source.is_file():
        raise FileNotFoundError(source)
    target = EVIDENCE_DIR / output_name
    shutil.copy2(source, target)
    return target


def render_dual_column_page() -> dict[str, object]:
    if not SOURCE_PACK.is_file():
        raise FileNotFoundError(SOURCE_PACK)
    PDF_TMP_DIR.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(SOURCE_PACK) as archive:
        pdf_members = [name for name in archive.namelist() if name.lower().endswith(".pdf")]
        if len(pdf_members) != 4:
            raise RuntimeError(f"Expected four source PDFs, found {len(pdf_members)}")
        source_pdf_bytes = archive.read(pdf_members[2])

    source_pdf = PDF_TMP_DIR / "prd_ocr_dual_column_source_book_03.pdf"
    source_pdf.write_bytes(source_pdf_bytes)
    reader = PdfReader(io.BytesIO(source_pdf_bytes))
    if len(reader.pages) < 243:
        raise RuntimeError(f"Source PDF has only {len(reader.pages)} pages")
    writer = PdfWriter()
    writer.add_page(reader.pages[242])
    page_pdf = PDF_TMP_DIR / "prd_ocr_dual_column_page_243.pdf"
    with page_pdf.open("wb") as stream:
        writer.write(stream)

    output_prefix = EVIDENCE_DIR / "dual_column_risk_page_243"
    subprocess.run(
        [
            str(PDFTOPPM),
            "-f",
            "1",
            "-singlefile",
            "-png",
            "-r",
            "180",
            str(page_pdf),
            str(output_prefix),
        ],
        check=True,
    )
    rendered = output_prefix.with_suffix(".png")
    if not rendered.is_file() or rendered.stat().st_size == 0:
        raise RuntimeError("Dual-column page rendering failed")
    return {
        "source_pack": str(SOURCE_PACK.relative_to(REPO_ROOT)).replace("\\", "/"),
        "source_member_index": 3,
        "source_pdf_sha256": sha256(source_pdf),
        "source_pdf_pages": len(reader.pages),
        "extracted_page_pdf_sha256": sha256(page_pdf),
        "rendered_page_sha256": sha256(rendered),
        "rendered_page": "evidence/AC-M2-01/dual_column_risk_page_243.png",
    }


def main() -> int:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    CANDIDATES_DIR.mkdir(parents=True, exist_ok=True)
    samples = {
        "clear": copy_sample(
            "18_0004_燃气轮机原理_结构与应用_上_沈阳黎明航空发动机_集团_有限责任公司编著_z.png",
            "clear_page_0004.png",
        ),
        "low_quality": copy_sample(
            "08_0045_燃气蒸汽轮机动力装置热工基础_清华大学燃气轮机教研组_z-library.s.png",
            "low_quality_page_0045.png",
        ),
        "table": copy_sample(
            "01_0562_先进燃气轮机燃烧室_ADVANCED_GAS_TURBINE_COMBUST.png",
            "table_page_0562.png",
        ),
        "image": copy_sample(
            "04_0375_大型燃气-蒸汽联合循环电厂培训教材_M701F燃气轮机汽轮机分册_深圳能源集.png",
            "image_page_0375.png",
        ),
    }
    dual_column = render_dual_column_page()
    rows = [
        {
            "category": "clear",
            "source_file": "燃气轮机原理、结构与应用 上.pdf",
            "page_num": 4,
            "decision": "pending",
            "reviewer": "",
            "reviewed_at": "",
            "evidence_ref": "evidence/AC-M2-01/clear_page_0004.png",
            "visual_basis": "正文、出版信息与页边界清楚，作为清晰页候选。",
        },
        {
            "category": "low_quality",
            "source_file": "燃气蒸汽轮机动力装置热工基础.pdf",
            "page_num": 45,
            "decision": "pending",
            "reviewer": "",
            "reviewed_at": "",
            "evidence_ref": "evidence/AC-M2-01/low_quality_page_0045.png",
            "visual_basis": "底色、淡字、公式和污点明显，作为低质量页候选。",
        },
        {
            "category": "table",
            "source_file": "先进燃气轮机燃烧室.pdf",
            "page_num": 562,
            "decision": "pending",
            "reviewer": "",
            "reviewed_at": "",
            "evidence_ref": "evidence/AC-M2-01/table_page_0562.png",
            "visual_basis": "跨行跨列参数表，作为表格页候选。",
        },
        {
            "category": "dual_column",
            "source_file": "燃气轮机原理、结构与应用 上.pdf",
            "page_num": 243,
            "decision": "pending",
            "reviewer": "",
            "reviewed_at": "",
            "evidence_ref": "evidence/AC-M2-01/dual_column_risk_page_243.png",
            "visual_basis": "既有审计将该页标为疑似两栏高风险；原页为图文与公式混排，须人工决定是否可作为 dual_column 类别，自动化不作通过判断。",
        },
        {
            "category": "image",
            "source_file": "大型燃气-蒸汽联合循环电厂培训教材 M701F 燃气轮机汽轮机分册.pdf",
            "page_num": 375,
            "decision": "pending",
            "reviewer": "",
            "reviewed_at": "",
            "evidence_ref": "evidence/AC-M2-01/image_page_0375.png",
            "visual_basis": "整页系统原理图与少量标注，作为图片页候选。",
        },
    ]
    evidence_inventory = [
        {
            "category": category,
            "path": f"evidence/AC-M2-01/{path.name}",
            "byte_size": path.stat().st_size,
            "sha256": sha256(path),
        }
        for category, path in samples.items()
    ]
    dual_path = ACCEPTANCE_ROOT / str(dual_column["rendered_page"])
    evidence_inventory.append(
        {
            "category": "dual_column",
            "path": dual_column["rendered_page"],
            "byte_size": dual_path.stat().st_size,
            "sha256": sha256(dual_path),
        }
    )
    payload = {
        "_status": "pending_human_review",
        "_formal_acceptance": False,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "purpose": "Five-category OCR spotcheck review roster; this file is not a signed acceptance record.",
        "promotion_rule": "A named reviewer must inspect each original-page image, set decision to pass/accepted, and add reviewed_at before copying records into ocr_coverage.json.",
        "source_risk_report": "docs/project_deliverables/02_OCR结果_13本扫描PDF/OCR两栏版面风险审计.md",
        "dual_column_source": dual_column,
        "evidence_inventory": evidence_inventory,
        "spotchecks": rows,
    }
    output = CANDIDATES_DIR / "ocr_spotcheck_candidate.json"
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"candidate": str(output), "evidence": evidence_inventory}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
