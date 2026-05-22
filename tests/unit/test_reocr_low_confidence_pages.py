from __future__ import annotations

import json
from pathlib import Path

from scripts.reocr_low_confidence_pages import collect_reocr_targets, choose_page_result


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def test_collect_reocr_targets_selects_nonblank_low_confidence_pages(tmp_path: Path) -> None:
    doc_dir = tmp_path / "01_demo"
    doc_dir.mkdir()
    pages_path = doc_dir / "pages.jsonl"
    write_jsonl(
        pages_path,
        [
            {"source_file": "demo.pdf", "page_num": 1, "avg_confidence": 0.2, "char_count": 100, "text": "低置信文本"},
            {"source_file": "demo.pdf", "page_num": 2, "avg_confidence": 0.9, "char_count": 100, "text": "高置信文本"},
            {"source_file": "demo.pdf", "page_num": 3, "avg_confidence": 0.0, "char_count": 0, "text": ""},
        ],
    )
    (doc_dir / "manifest.json").write_text(
        json.dumps({"source_file": "demo.pdf", "pages_jsonl": str(pages_path)}, ensure_ascii=False),
        encoding="utf-8",
    )

    targets = collect_reocr_targets(tmp_path, threshold=0.45, include_empty=False)

    assert [target.page_num for target in targets] == [1]


def test_choose_page_result_accepts_improvement_without_large_text_loss() -> None:
    original = {"avg_confidence": 0.3, "char_count": 100, "text": "原文本"}
    improved = {"avg_confidence": 0.55, "char_count": 110, "text": "新文本"}
    worse = {"avg_confidence": 0.25, "char_count": 120, "text": "差文本"}
    too_short = {"avg_confidence": 0.7, "char_count": 20, "text": "短"}

    accepted, _reason, chosen = choose_page_result(original, improved)
    assert accepted is True
    assert chosen["text"] == "新文本"

    accepted, _reason, chosen = choose_page_result(original, worse)
    assert accepted is False
    assert chosen["text"] == "原文本"

    accepted, _reason, chosen = choose_page_result(original, too_short)
    assert accepted is False
    assert chosen["text"] == "原文本"
