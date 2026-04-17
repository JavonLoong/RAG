"""
性能基准测试 — 来自项目2

合成数据插入+查询性能测试。
"""
from __future__ import annotations

import random
import statistics
import time
from pathlib import Path

from .pipeline import DEFAULT_PERSIST_DIR, _close_client, get_collection_handle
from .text_utils import estimate_token_count, safe_collection_name

BASE_SENTENCES = [
    "燃气轮机健康管理需要同时关注振动、温度、压力与润滑状态。",
    "压气机喘振通常与进气畸变、叶片污染和控制策略不稳定有关。",
    "状态监测数据可以支撑故障诊断、寿命评估和检修计划优化。",
    "知识库检索链路应兼顾召回率、响应时间和批量查询稳定性。",
    "面向动力装备场景，设备型号、部件结构和故障模式需要统一建模。",
    "向量数据库在批量写入时通常受 embedding 耗时和索引刷新频率影响。",
    "检索性能评估建议同时观察平均延迟、P95 延迟与吞吐量。",
]

BASE_QUERIES = [
    "燃气轮机故障诊断",
    "压气机喘振原因",
    "状态监测与维护",
    "向量检索响应时间",
    "设备部件参数查询",
]


def run_synthetic_benchmark(
    persist_dir: Path = DEFAULT_PERSIST_DIR,
    collection_name: str | None = None,
    document_count: int = 500,
    batch_size: int = 100,
    query_count: int = 50,
    top_k: int = 5,
    backend: str | None = None,
    model_name: str | None = None,
    cleanup: bool = True,
) -> dict:
    """运行合成数据性能基准测试"""
    benchmark_name = safe_collection_name(collection_name or f"benchmark-{int(time.time())}")
    client, collection, resolved_backend = get_collection_handle(
        persist_dir=persist_dir,
        collection_name=benchmark_name,
        backend=backend,
        model_name=model_name,
    )

    corpus = _build_synthetic_corpus(document_count=document_count)
    try:
        # 插入测试
        insert_started = time.perf_counter()
        for start in range(0, len(corpus), batch_size):
            batch = corpus[start:start + batch_size]
            collection.upsert(
                ids=[item["id"] for item in batch],
                documents=[item["text"] for item in batch],
                metadatas=[item["metadata"] for item in batch],
            )
        insert_elapsed = time.perf_counter() - insert_started

        # 查询测试
        query_latencies_ms: list[float] = []
        query_started = time.perf_counter()
        for index in range(query_count):
            query_text = BASE_QUERIES[index % len(BASE_QUERIES)]
            started = time.perf_counter()
            collection.query(query_texts=[query_text], n_results=top_k, include=["distances"])
            query_latencies_ms.append((time.perf_counter() - started) * 1000)
        query_elapsed = time.perf_counter() - query_started

        result = {
            "collection": benchmark_name,
            "document_count": document_count,
            "batch_size": batch_size,
            "query_count": query_count,
            "top_k": top_k,
            "insert_seconds": round(insert_elapsed, 4),
            "insert_docs_per_second": round(document_count / insert_elapsed, 2) if insert_elapsed else 0.0,
            "query_seconds": round(query_elapsed, 4),
            "query_qps": round(query_count / query_elapsed, 2) if query_elapsed else 0.0,
            "avg_query_latency_ms": round(statistics.fmean(query_latencies_ms), 3) if query_latencies_ms else 0.0,
            "p95_query_latency_ms": round(_percentile(query_latencies_ms, 0.95), 3) if query_latencies_ms else 0.0,
            "embedding_backend": resolved_backend.name,
            "embedding_model": resolved_backend.model_name,
            "embedding_warning": resolved_backend.warning,
        }

        if cleanup:
            client.delete_collection(name=benchmark_name)

        return result
    finally:
        _close_client(client)


def _build_synthetic_corpus(document_count: int) -> list[dict]:
    rng = random.Random(42)
    corpus: list[dict] = []
    for index in range(document_count):
        sentence_count = rng.randint(4, 6)
        sentences = rng.sample(BASE_SENTENCES, k=sentence_count)
        equipment = ["LM2500", "GT25000", "QC185", "MAN-9L32", "MT30"][index % 5]
        fault = ["喘振", "高温", "异常振动", "润滑不足", "叶片污染"][index % 5]
        extra = f"文档编号 {index}，设备 {equipment}，重点关注 {fault}、维护策略、性能参数与检索测试。"
        text = " ".join(sentences + [extra])
        corpus.append({
            "id": f"bench-{index}",
            "text": text,
            "metadata": {
                "source_file": "synthetic-benchmark",
                "record_id": f"synthetic-{index}",
                "filename": f"synthetic-{index}.txt",
                "page_nums": str([-1]),
                "chunk_index": 0,
                "block_count": 1,
                "char_count": len(text),
                "estimated_tokens": estimate_token_count(text),
            },
        })
    return corpus


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * q))))
    return ordered[index]
