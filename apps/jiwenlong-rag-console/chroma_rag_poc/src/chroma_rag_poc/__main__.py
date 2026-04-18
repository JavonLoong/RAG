"""
CLI 入口 — 合并两版

项目2: subcommand 模式 (serve/ingest/stats/search/benchmark)
项目1: 单命令模式 (--json/--vectorize/--search/--ask)

合并后保留两种使用方式。
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import uvicorn

from .benchmark import run_synthetic_benchmark
from .chunking import chunk_records
from .cleaning import clean_records
from .pipeline import (
    DEFAULT_PERSIST_DIR,
    get_collection_stats,
    ingest_json_payloads,
    ingest_from_directory,
    query_collection,
    quality_report,
)
from .parsing import load_json_file, load_json_directory


def main() -> None:
    parser = argparse.ArgumentParser(
        description="动力装备知识库 RAG Pipeline v2.0（合并优化版）"
    )
    subparsers = parser.add_subparsers(dest="command")

    # ========== serve ==========
    serve_parser = subparsers.add_parser("serve", help="启动管理面板 Web 服务")
    serve_parser.add_argument("--host", default="0.0.0.0")
    serve_parser.add_argument("--port", type=int, default=8000)

    # ========== ingest ==========
    ingest_parser = subparsers.add_parser("ingest", help="入库 JSON 文件")
    ingest_parser.add_argument("files", nargs="*", help="JSON 文件路径")
    ingest_parser.add_argument("--dir", default=None, help="JSON 文件目录（批量）")
    ingest_parser.add_argument("--collection", default="power_equipment")
    ingest_parser.add_argument("--chunk-size", type=int, default=500)
    ingest_parser.add_argument("--overlap", type=int, default=50)
    ingest_parser.add_argument("--backend", default="hashing")
    ingest_parser.add_argument("--model-name", default="BAAI/bge-m3")
    ingest_parser.add_argument("--persist-dir", default=str(DEFAULT_PERSIST_DIR))
    ingest_parser.add_argument("--no-clean", action="store_true", help="跳过短文本合并")

    # ========== stats ==========
    stats_parser = subparsers.add_parser("stats", help="查看 ChromaDB 统计")
    stats_parser.add_argument("--collection", default="power_equipment")
    stats_parser.add_argument("--persist-dir", default=str(DEFAULT_PERSIST_DIR))

    # ========== search ==========
    search_parser = subparsers.add_parser("search", help="检索查询")
    search_parser.add_argument("--collection", default="power_equipment")
    search_parser.add_argument("--query", required=True)
    search_parser.add_argument("--top-k", type=int, default=5)
    search_parser.add_argument("--persist-dir", default=str(DEFAULT_PERSIST_DIR))

    # ========== benchmark ==========
    bench_parser = subparsers.add_parser("benchmark", help="性能基准测试")
    bench_parser.add_argument("--collection", default="benchmark_power_equipment")
    bench_parser.add_argument("--document-count", type=int, default=500)
    bench_parser.add_argument("--batch-size", type=int, default=100)
    bench_parser.add_argument("--query-count", type=int, default=50)
    bench_parser.add_argument("--top-k", type=int, default=5)
    bench_parser.add_argument("--backend", default="hashing")
    bench_parser.add_argument("--model-name", default=None)
    bench_parser.add_argument("--persist-dir", default=str(DEFAULT_PERSIST_DIR))
    bench_parser.add_argument("--keep", action="store_true")

    # ========== demo (项目1兼容模式) ==========
    demo_parser = subparsers.add_parser("demo", help="完整演示流程")
    demo_parser.add_argument("--json", default=None, help="单个 JSON 文件")
    demo_parser.add_argument("--json-dir", default=None, help="JSON 目录")
    demo_parser.add_argument("--chunk-size", type=int, default=500)
    demo_parser.add_argument("--overlap", type=int, default=50)

    args = parser.parse_args()

    # 无子命令时默认启动 serve
    if not args.command:
        print("=" * 60)
        print("🚀 动力装备知识库 RAG Pipeline v2.0")
        print("   合并优化版：项目2架构 + 项目1核心功能")
        print(f"   前端: http://localhost:8000")
        print(f"   API 文档: http://localhost:8000/docs")
        print("=" * 60)
        uvicorn.run("chroma_rag_poc.api:app", host="0.0.0.0", port=8000, reload=False)
        return

    if args.command == "serve":
        print("=" * 60)
        print("🚀 动力装备知识库管理系统")
        print(f"   前端: http://{args.host}:{args.port}")
        print(f"   API 文档: http://{args.host}:{args.port}/docs")
        print("=" * 60)
        uvicorn.run("chroma_rag_poc.api:app", host=args.host, port=args.port, reload=False)
        return

    if args.command == "ingest":
        if args.dir:
            result = ingest_from_directory(
                json_dir=args.dir,
                persist_dir=Path(args.persist_dir),
                collection_name=args.collection,
                chunk_size=args.chunk_size,
                overlap=args.overlap,
                backend=args.backend,
                model_name=args.model_name,
                clean=not args.no_clean,
            )
        elif args.files:
            payloads = [(Path(f).name, Path(f).read_bytes()) for f in args.files]
            result = ingest_json_payloads(
                payloads=payloads,
                persist_dir=Path(args.persist_dir),
                collection_name=args.collection,
                chunk_size=args.chunk_size,
                overlap=args.overlap,
                backend=args.backend,
                model_name=args.model_name,
                clean=not args.no_clean,
            )
        else:
            print("❌ 请指定文件路径或 --dir 目录")
            return
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.command == "stats":
        result = get_collection_stats(
            persist_dir=Path(args.persist_dir),
            collection_name=args.collection,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.command == "search":
        result = query_collection(
            query_text=args.query,
            persist_dir=Path(args.persist_dir),
            collection_name=args.collection,
            top_k=args.top_k,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.command == "benchmark":
        result = run_synthetic_benchmark(
            persist_dir=Path(args.persist_dir),
            collection_name=args.collection,
            document_count=args.document_count,
            batch_size=args.batch_size,
            query_count=args.query_count,
            top_k=args.top_k,
            backend=args.backend,
            model_name=args.model_name,
            cleanup=not args.keep,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.command == "demo":
        _run_demo(args)


def _run_demo(args):
    """项目1风格的完整演示流程"""
    t_start = time.time()

    # 确定数据源
    if args.json:
        print(f"📄 单文件模式: {args.json}")
        records = load_json_file(args.json)
    elif args.json_dir:
        print(f"📂 批量模式: {args.json_dir}")
        records = load_json_directory(args.json_dir)
    else:
        # 默认查找数据目录
        default_dir = Path(__file__).resolve().parents[5] / "03_数据" / "标注数据"
        if default_dir.exists():
            print(f"📂 自动发现数据目录: {default_dir}")
            records = load_json_directory(str(default_dir))
        else:
            print("❌ 未指定数据源，请使用 --json 或 --json-dir")
            return

    # 清洗
    print("\n" + "=" * 60)
    print("Step 1.5: 数据清洗（短文本合并）")
    print("=" * 60)
    before = sum(len(r.blocks) for r in records)
    records = clean_records(records)
    after = sum(len(r.blocks) for r in records)
    print(f"   {before} 块 → {after} 块（合并了 {before - after} 个碎片）")

    # 分块
    print("\n" + "=" * 60)
    print("Step 2: 文本分块")
    print("=" * 60)
    chunks = chunk_records(records, chunk_size=args.chunk_size, overlap=args.overlap)
    print(f"   生成 {len(chunks)} 个 chunk")

    # 质量报告
    report = quality_report(records, chunks)
    print(f"\n📊 质量报告: {report['issue_count']} 个问题")
    for issue in report["issues"]:
        print(f"   ⚠️ {issue}")

    print(f"\n⏱️ 总耗时: {time.time() - t_start:.1f}s")
    print("\n💡 使用 'python -m chroma_rag_poc serve' 启动管理面板")
    print("   使用 'python -m chroma_rag_poc ingest ...' 入库数据")


if __name__ == "__main__":
    main()
