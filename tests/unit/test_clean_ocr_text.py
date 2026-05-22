from __future__ import annotations

import json
from pathlib import Path

from scripts.clean_ocr_text import clean_page, clean_text_payload, process_document_dir


def test_clean_text_payload_removes_tesseract_tsv_rows_and_rebuilds_text() -> None:
    dirty = "\n".join(
        [
            "Preface line",
            "5\t1\t1\t1\t1\t1\t10\t10\t16\t12\t95.5\t燃气",
            "5\t1\t1\t1\t1\t2\t30\t10\t16\t12\t96.0\t轮机",
            "4\t1\t1\t1\t2\t0\t10\t28\t70\t12\t-1\t",
            "5\t1\t1\t1\t2\t1\t10\t28\t22\t12\t91.0\tGas",
            "5\t1\t1\t1\t2\t2\t40\t28\t42\t12\t92.0\tTurbine",
        ]
    )

    cleaned, stats = clean_text_payload(dirty)

    assert cleaned.splitlines() == ["Preface line", "燃气轮机", "Gas Turbine"]
    assert stats["tsv_rows_removed"] == 5
    assert stats["tsv_word_rows_used"] == 4


def test_clean_page_falls_back_to_structured_lines_when_text_is_blank() -> None:
    page = {
        "page_num": 1,
        "text": "",
        "lines": [{"text": "第一行"}, {"text": "Second line"}],
    }

    cleaned = clean_page(page)

    assert cleaned["text"] == "第一行\nSecond line"
    assert cleaned["char_count"] == len("第一行\nSecond line")
    assert cleaned["line_count"] == 2
    assert cleaned["cleaning"]["fallback_lines_used"] is True


def test_process_document_dir_writes_clean_pages_and_document(tmp_path: Path) -> None:
    input_dir = tmp_path / "input" / "01_demo"
    output_dir = tmp_path / "output" / "01_demo"
    input_dir.mkdir(parents=True)
    pages_path = input_dir / "pages.jsonl"
    pages = [
        {
            "source_file": "demo.pdf",
            "page_num": 1,
            "text": "5\t1\t1\t1\t1\t1\t10\t10\t16\t12\t95.5\t燃气\n"
            "5\t1\t1\t1\t1\t2\t30\t10\t16\t12\t96.0\t轮机",
        }
    ]
    pages_path.write_text(
        "\n".join(json.dumps(page, ensure_ascii=False) for page in pages) + "\n",
        encoding="utf-8",
    )
    (input_dir / "manifest.json").write_text(
        json.dumps(
            {
                "source_file": "demo.pdf",
                "pages_jsonl": str(pages_path),
                "document_txt": str(input_dir / "document.txt"),
                "total_pages": 1,
                "target_pages": 1,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    summary = process_document_dir(input_dir, output_dir)

    clean_doc = (output_dir / "document.txt").read_text(encoding="utf-8")
    clean_pages = [
        json.loads(line)
        for line in (output_dir / "pages.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert "5\t1\t" not in clean_doc
    assert "燃气轮机" in clean_doc
    assert clean_pages[0]["text"] == "燃气轮机"
    assert summary["tsv_rows_removed"] == 2
