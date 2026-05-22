from __future__ import annotations

import json
import sys
import argparse
from pathlib import Path


for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parents[1]
REPORT = REPO_ROOT / "data_pipeline" / "reports" / "pdf_extractability_report.json"
DEFAULT_OCR_ROOT = REPO_ROOT / "data_pipeline" / "ocr" / "tsinghua_gas_turbine_books"


def stable_id(value: str, length: int = 12) -> str:
    import hashlib

    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:length]


def count_pages(path: Path) -> int:
    if not path.exists():
        return 0
    pages: set[int] = set()
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            page_num = payload.get("page_num")
            if isinstance(page_num, int):
                pages.add(page_num)
            elif isinstance(page_num, str) and page_num.isdigit():
                pages.add(int(page_num))
    return len(pages)


def resolve_repo_path(value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Show OCR progress for scanned PDFs.")
    parser.add_argument("--output-root", default=str(DEFAULT_OCR_ROOT))
    args = parser.parse_args()
    ocr_root = resolve_repo_path(args.output_root)
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    queue = sorted(
        [item for item in report["pdfs"] if item["classification"] == "needs_ocr"],
        key=lambda item: item["file_name"],
    )
    rows = []
    for index, item in enumerate(queue, start=1):
        doc_dir = ocr_root / f"{index:02d}_{stable_id(item['file_name'])}"
        pages_done = count_pages(doc_dir / "pages.jsonl")
        target = int(item["total_pages"])
        rows.append(
            {
                "index": index,
                "pages_done": pages_done,
                "target_pages": target,
                "remaining": max(target - pages_done, 0),
                "complete": pages_done >= target,
                "dir": doc_dir.name,
                "file_name": item["file_name"],
            }
        )
    total_done = sum(row["pages_done"] for row in rows)
    total_target = sum(row["target_pages"] for row in rows)
    print(json.dumps({"ocr_root": str(ocr_root), "done": total_done, "target": total_target, "rows": rows}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
