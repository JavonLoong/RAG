from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_SRC = REPO_ROOT / "api_server" / "current_console" / "chroma_rag_poc" / "src"
SITE_PACKAGES = REPO_ROOT / ".venv" / "Lib" / "site-packages"
for import_path in (SITE_PACKAGES, PACKAGE_SRC):
    if import_path.exists() and str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from chroma_rag_poc.pipeline import get_all_stats, get_collection_stats, query_collection
from chroma_rag_poc.public_books_json import export_chroma_database, ingest_latest_snapshot_to_chroma


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest every public-books Label Studio JSON snapshot separately.")
    parser.add_argument("--input-root", required=True, help="Directory containing JSON snapshots.")
    parser.add_argument("--output-root", required=True, help="Desktop/report output directory.")
    parser.add_argument("--persist-dir", required=True, help="ASCII-path ChromaDB persistence directory.")
    parser.add_argument("--collection-prefix", default="json", help="Collection name prefix.")
    parser.add_argument("--chunk-size", type=int, default=900)
    parser.add_argument("--overlap", type=int, default=120)
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--query", default="燃气轮机", help="Smoke-test query for each collection.")
    parser.add_argument("--reset", action="store_true", help="Delete persist-dir before ingesting.")
    return parser.parse_args()


def collection_name_for(prefix: str, index: int, path: Path) -> str:
    stem = path.stem.lower()
    match = re.search(r"at-(\d{4})-(\d{2})-(\d{2})-(\d{2})-(\d{2})(?:-(\d{2}))?-([a-z0-9]+)", stem)
    if match:
        year, month, day, hour, minute, second, suffix = match.groups()
        second = second or "00"
        return f"{prefix}_{index:02d}_{year}{month}{day}_{hour}{minute}{second}_{suffix[:8]}"
    safe = re.sub(r"[^a-z0-9_]+", "_", stem).strip("_")[:40]
    return f"{prefix}_{index:02d}_{safe}"


def write_csv(path: Path, rows: list[dict]) -> None:
    fieldnames = [
        "index",
        "json_file",
        "json_size_mb",
        "collection",
        "status",
        "tasks",
        "blocks_total",
        "records_written",
        "chunks_written",
        "final_chunk_count",
        "query_results",
        "elapsed_s",
        "error",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_report(path: Path, summary: dict) -> None:
    rows = summary["rows"]
    lines = [
        "# 27 个 JSON 逐个入库结果",
        "",
        "## 结论",
        "",
        f"- JSON 文件数：{summary['json_count']}",
        f"- 成功入库：{sum(1 for row in rows if row['status'] == 'ok')}",
        f"- ChromaDB collection 数：{summary['collections_count']}",
        f"- 总 chunk 数：{summary['total_chunks']}",
        f"- 总记录数：{summary['total_records']}",
        f"- 实际 ChromaDB 目录：`{summary['runtime_chromadb']}`",
        f"- 导出压缩包：`{summary['export_zip']}`",
        "",
        "## 入库方式",
        "",
        "按要求 27 个 JSON 全部逐个入库。每个 JSON 建一个独立 ChromaDB collection，避免连续快照互相覆盖或混成一个集合。",
        "",
        "## 文件说明",
        "",
        "- `ChromaDB_27个JSON逐个入库_可交付包.zip`：完整 ChromaDB 导出包。",
        "- `27个JSON逐个入库清单.csv`：每个 JSON 对应 collection、chunk 数和检索验证。",
        "- `27个JSON逐个入库_summary.json`：机器可读完整结果。",
        "- `逐个入库运行日志.txt`：逐个入库过程日志。",
        "",
        "## 逐个结果",
        "",
    ]
    for row in rows:
        lines.append(
            f"- {row['index']:02d}. `{row['json_file']}` -> `{row['collection']}`："
            f"{row['status']}，chunks={row['final_chunk_count']}，检索返回={row['query_results']}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    input_root = Path(args.input_root)
    output_root = Path(args.output_root)
    persist_dir = Path(args.persist_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    persist_dir.parent.mkdir(parents=True, exist_ok=True)

    log_path = output_root / "逐个入库运行日志.txt"
    log_path.write_text("", encoding="utf-8")

    def log(message: str) -> None:
        line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}"
        print(line, flush=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    files = sorted(input_root.glob("*.json"), key=lambda path: path.name)
    if not files:
        raise FileNotFoundError(f"No JSON files found under {input_root}")

    if args.reset and persist_dir.exists():
        shutil.rmtree(persist_dir)
    persist_dir.mkdir(parents=True, exist_ok=True)

    log(f"开始逐个入库：{len(files)} 个 JSON")
    log(f"JSON 源目录：{input_root}")
    log(f"ChromaDB 实际目录：{persist_dir}")

    rows: list[dict] = []
    started_all = time.time()
    for index, path in enumerate(files, start=1):
        collection = collection_name_for(args.collection_prefix, index, path)
        started = time.time()
        log(f"[{index}/{len(files)}] 入库开始：{path.name} -> {collection}")
        row = {
            "index": index,
            "json_file": path.name,
            "json_size_mb": round(path.stat().st_size / 1024 / 1024, 3),
            "collection": collection,
            "status": "running",
        }
        try:
            result = ingest_latest_snapshot_to_chroma(
                input_root=path,
                persist_dir=persist_dir,
                collection_name=collection,
                mode="create",
                chunk_size=args.chunk_size,
                overlap=args.overlap,
                batch_size=args.batch_size,
            )
            stats = get_collection_stats(persist_dir, collection)
            search = query_collection(args.query, persist_dir, collection, top_k=3, backend="hashing")
            row.update(
                {
                    "status": "ok",
                    "tasks": result.get("tasks"),
                    "blocks_total": result.get("blocks_total"),
                    "records_written": result.get("records_written"),
                    "chunks_written": result.get("chunks_written"),
                    "final_chunk_count": stats.get("chunk_count"),
                    "query_results": len(search.get("results") or []),
                    "elapsed_s": round(time.time() - started, 3),
                    "error": "",
                }
            )
            log(
                f"[{index}/{len(files)}] 入库完成：chunks={row['chunks_written']}，"
                f"检索返回={row['query_results']}，耗时={row['elapsed_s']}s"
            )
        except Exception as exc:  # noqa: BLE001 - keep batch running and report per-file errors.
            row.update(
                {
                    "status": "error",
                    "tasks": 0,
                    "blocks_total": 0,
                    "records_written": 0,
                    "chunks_written": 0,
                    "final_chunk_count": 0,
                    "query_results": 0,
                    "elapsed_s": round(time.time() - started, 3),
                    "error": str(exc),
                }
            )
            log(f"[{index}/{len(files)}] 入库失败：{path.name} -> {exc}")
            log(traceback.format_exc())
        rows.append(row)
        write_csv(output_root / "27个JSON逐个入库清单.csv", rows)

    all_stats = get_all_stats(persist_dir)
    zip_path = output_root / "ChromaDB_27个JSON逐个入库_可交付包.zip"
    log("开始导出 ChromaDB 压缩包")
    export_chroma_database(persist_dir, zip_path)

    summary = {
        "status": "ok" if all(row["status"] == "ok" for row in rows) else "partial_error",
        "json_root": str(input_root),
        "desktop_output": str(output_root),
        "runtime_chromadb": str(persist_dir),
        "json_count": len(files),
        "collections_count": len(all_stats.get("collections") or []),
        "total_chunks": sum(int(row.get("final_chunk_count") or 0) for row in rows),
        "total_records": sum(int(row.get("records_written") or 0) for row in rows),
        "elapsed_s": round(time.time() - started_all, 3),
        "export_zip": str(zip_path),
        "export_zip_size_mb": round(zip_path.stat().st_size / 1024 / 1024, 3),
        "rows": rows,
        "all_stats": all_stats,
    }
    (output_root / "27个JSON逐个入库_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_report(output_root / "README_27个JSON逐个入库.md", summary)
    log(f"全部完成：成功 {sum(1 for row in rows if row['status'] == 'ok')}/{len(files)}，总 chunks={summary['total_chunks']}，zip={zip_path}")
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
