"""Inventory Label Studio material JSON without copying it into git."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

SRC = Path(r"C:\Users\15410\AppData\Local\PowerRAG\current_console\uploads\project-1-at-2026-05-21-06-17-203caed5.json")

SKIP = re.compile(r"wechat|private_chunks|affection|强基|清华招生|北大|清北|校测|报考指南", re.I)
TEXTBOOK = re.compile(r"Ran_Qi_Lun_Ji|Qing_Hua_Da_Xue_Re_Neng|联合循环装置|燃气轮机与燃气", re.I)
FIELD = re.compile(
    r"Gu_Zhang|Yan_Dun|Wu_Zhou|Xiu_Fu|Ri_Bao|Lou_Qi|Chuan_Dong|Fang_Qi|Ke_Diao|Dong_Li_Wo_Lun|Xian_Chang",
    re.I,
)


def file_name(task: dict) -> str:
    data = task.get("data") or {}
    name = data.get("filename") or data.get("file") or data.get("document")
    if name:
        return Path(str(name).split("?")[0]).name
    for key in ("ocr", "image", "pdf"):
        val = data.get(key)
        if isinstance(val, str) and val:
            return Path(val.split("?")[0]).name
    return "unknown"


def texts(task: dict) -> list[str]:
    out = []
    for ann in task.get("annotations") or []:
        for res in ann.get("result") or []:
            val = (res.get("value") or {}).get("text")
            if isinstance(val, list):
                out.extend(str(x).strip() for x in val if str(x).strip())
            elif isinstance(val, str) and val.strip():
                out.append(val.strip())
    return out


def main() -> None:
    tasks = json.loads(SRC.read_text(encoding="utf-8"))
    if isinstance(tasks, dict):
        tasks = tasks.get("tasks") or tasks.get("data") or []
    by_file = defaultdict(lambda: {"pages": 0, "chars": 0, "blocks": 0})
    for task in tasks:
        name = file_name(task)
        if SKIP.search(name):
            continue
        chunks = texts(task)
        rec = by_file[name]
        rec["pages"] += 1
        rec["blocks"] += len(chunks)
        rec["chars"] += sum(len(x) for x in chunks)

    rows = sorted(by_file.items(), key=lambda kv: -kv[1]["chars"])
    field = [(n, s) for n, s in rows if FIELD.search(n) and not TEXTBOOK.search(n)]
    book = [(n, s) for n, s in rows if TEXTBOOK.search(n)]
    other = [(n, s) for n, s in rows if n not in {x[0] for x in field + book}]

    def pack(items):
        return {
            "files": len(items),
            "pages": sum(s["pages"] for _, s in items),
            "blocks": sum(s["blocks"] for _, s in items),
            "chars": sum(s["chars"] for _, s in items),
            "top": [{"file": n, **s} for n, s in items[:12]],
        }

    report = {
        "source": str(SRC),
        "bytes": SRC.stat().st_size,
        "tasks": len(tasks),
        "field_reports": pack(field),
        "gt_textbook_slices": pack(book),
        "other": pack(other),
        "note": "Do not commit the 64MB JSON. Field reports are the preferred long-text pack.",
    }
    out = Path(__file__).with_name("labelstudio_json_inventory_20260923.json")
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "source"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
