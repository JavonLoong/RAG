from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PACKAGE_SRC = Path(__file__).resolve().parents[2] / "api_server" / "current_console" / "chroma_rag_poc" / "src"
if str(PACKAGE_SRC) not in sys.path:
    sys.path.insert(0, str(PACKAGE_SRC))

from chroma_rag_poc.public_books_json import (  # noqa: E402
    choose_latest_snapshot,
    filter_blocks,
    load_latest_labelstudio_snapshot,
    merge_blocks_to_records,
    parse_labelstudio_export,
)
from chroma_rag_poc import pipeline  # noqa: E402


def _labelstudio_task(task_id: int, filename: str = "book-a.pdf") -> dict:
    return {
        "id": task_id,
        "data": {
            "filename": filename,
            "doc_id": "book-a",
            "page_num": 12,
            "total_pages": 200,
        },
        "annotations": [
            {
                "result": [
                    {
                        "id": "body-1",
                        "type": "rectanglelabels",
                        "value": {"rectanglelabels": ["Para"], "x": 10, "y": 20, "width": 80, "height": 8},
                    },
                    {
                        "id": "body-1",
                        "type": "textarea",
                        "value": {"text": ["燃气轮机燃烧室需要控制温度分布，避免局部过热造成叶片寿命下降。"]},
                    },
                    {
                        "id": "page-noise",
                        "type": "rectanglelabels",
                        "value": {"rectanglelabels": ["Para"], "x": 50, "y": 95, "width": 10, "height": 4},
                    },
                    {
                        "id": "page-noise",
                        "type": "textarea",
                        "value": {"text": ["12"]},
                    },
                ]
            }
        ],
    }


def test_choose_latest_snapshot_uses_latest_export_name(tmp_path: Path) -> None:
    older = tmp_path / "project-1-at-2026-05-20-06-17-old.json"
    newer = tmp_path / "project-1-at-2026-05-21-06-17-new.json"
    older.write_text("[]", encoding="utf-8")
    newer.write_text("[]", encoding="utf-8")

    assert choose_latest_snapshot(tmp_path) == newer


def test_parse_labelstudio_export_pairs_text_and_box_by_result_id() -> None:
    blocks = parse_labelstudio_export([_labelstudio_task(1)], source_file="snapshot.json")

    assert len(blocks) == 2
    assert blocks[0].label == "Para"
    assert blocks[0].text.startswith("燃气轮机燃烧室")
    assert blocks[0].page_num == 12
    assert blocks[0].x == 10
    assert blocks[0].y == 20


def test_filter_blocks_accepts_body_text_and_rejects_page_noise() -> None:
    blocks = parse_labelstudio_export([_labelstudio_task(1)], source_file="snapshot.json")
    decision = filter_blocks(blocks)

    assert [item.decision for item in decision] == ["accept", "reject"]
    assert decision[0].reason == "main_text"
    assert decision[1].reason == "page_or_tiny_noise"


def test_merge_blocks_to_records_keeps_page_reading_order() -> None:
    task = _labelstudio_task(1)
    task["annotations"][0]["result"].extend(
        [
            {
                "id": "body-0",
                "type": "rectanglelabels",
                "value": {"rectanglelabels": ["Title"], "x": 10, "y": 5, "width": 70, "height": 8},
            },
            {
                "id": "body-0",
                "type": "textarea",
                "value": {"text": ["燃烧室温度控制"]},
            },
        ]
    )
    filtered = filter_blocks(parse_labelstudio_export([task], source_file="snapshot.json"))

    records = merge_blocks_to_records(filtered)

    assert len(records) == 1
    assert records[0].filename == "book-a.pdf"
    assert records[0].page_num == 12
    assert records[0].text.startswith("燃烧室温度控制\n燃气轮机燃烧室")
    assert records[0].metadata["accepted_block_count"] == 2


def test_parse_labelstudio_export_rejects_non_list_payload() -> None:
    with pytest.raises(ValueError, match="top-level JSON must be a list"):
        parse_labelstudio_export({"data": []}, source_file="bad.json")


def test_latest_snapshot_round_trip_from_file(tmp_path: Path) -> None:
    snapshot = tmp_path / "project-1-at-2026-05-21-06-17-new.json"
    snapshot.write_text(json.dumps([_labelstudio_task(7)], ensure_ascii=False), encoding="utf-8")

    latest = choose_latest_snapshot(tmp_path)
    payload = json.loads(latest.read_text(encoding="utf-8"))
    filtered = filter_blocks(parse_labelstudio_export(payload, source_file=latest.name))
    records = merge_blocks_to_records(filtered)

    assert latest.name == snapshot.name
    assert records[0].record_id.startswith("book-a:12")


def test_load_latest_snapshot_accepts_utf8_bom(tmp_path: Path) -> None:
    snapshot = tmp_path / "project-1-at-2026-05-21-06-17-bom.json"
    snapshot.write_bytes(("\ufeff" + json.dumps([_labelstudio_task(8)], ensure_ascii=False)).encode("utf-8"))

    latest, payload = load_latest_labelstudio_snapshot(tmp_path)

    assert latest == snapshot
    assert payload[0]["id"] == 8


def test_default_runtime_dir_moves_windows_chroma_out_of_non_ascii_repo_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("POWER_RAG_RUNTIME_DIR", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\15410\AppData\Local")
    monkeypatch.setattr(pipeline.os, "name", "nt", raising=False)

    runtime_dir = pipeline.resolve_default_runtime_dir(Path(r"D:\虚拟C盘\RAG"))

    assert runtime_dir == Path(r"C:\Users\15410\AppData\Local\PowerRAG\current_console")


def test_explicit_runtime_dir_is_respected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POWER_RAG_RUNTIME_DIR", r"D:\RAG_RUNTIME")

    runtime_dir = pipeline.resolve_default_runtime_dir(Path(r"D:\虚拟C盘\RAG"))

    assert runtime_dir == Path(r"D:\RAG_RUNTIME")
