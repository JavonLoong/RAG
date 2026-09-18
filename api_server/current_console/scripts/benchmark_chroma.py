"""
纪文龙 — ChromaDB 性能基准测试 v1.0
测试维度：插入性能、检索延迟、并发查询、存储空间
"""

import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import time
import random
import string
import os
import shutil
import json
import argparse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

DEFAULT_EMBEDDING_MODEL = os.environ.get("RAG_EMBEDDING_MODEL", "Qwen/Qwen3-Embedding-0.6B")


# ============================================================
# 中文随机文本生成
# ============================================================

# 动力装备领域常用词汇，模拟真实场景
VOCAB = [
    "燃气轮机", "柴油发动机", "压气机", "涡轮", "燃烧室", "轴承",
    "齿轮箱", "发电机", "变压器", "冷却系统", "润滑系统", "燃油系统",
    "排气温度", "振动监测", "故障诊断", "健康管理", "知识图谱",
    "传感器", "控制系统", "喘振", "效率", "功率", "转速", "压力",
    "船舶", "风力发电", "锅炉", "蒸汽", "热交换器", "阀门",
    "维护保养", "定期检查", "内窥镜", "无损检测", "超声波",
    "叶片", "密封", "管道", "泵", "过滤器", "冷却水", "滑油",
    "安全规程", "操作手册", "技术规范", "设计参数", "额定工况",
    "启动程序", "停机程序", "紧急处置", "报警系统", "保护装置",
    "数据采集", "状态监测", "趋势分析", "预测性维护", "寿命评估",
    "材料疲劳", "蠕变", "腐蚀", "磨损", "裂纹", "变形",
    "图谱构建", "实体抽取", "关系识别", "三元组", "向量检索",
    "语义搜索", "混合检索", "BM25", "嵌入模型", "BGE",
]

CONNECTORS = [
    "的", "与", "和", "进行", "通过", "采用", "实现",
    "需要", "应当", "包括", "以及", "基于", "利用",
    "确保", "维持", "降低", "提高", "监测", "分析",
    "，", "。", "；", "、",
]


def random_chinese_text(min_chars: int = 100, max_chars: int = 500) -> str:
    """生成指定长度范围内的随机中文文本"""
    target_len = random.randint(min_chars, max_chars)
    parts = []
    current_len = 0
    while current_len < target_len:
        word = random.choice(VOCAB)
        conn = random.choice(CONNECTORS)
        segment = word + conn
        parts.append(segment)
        current_len += len(segment)
        # 随机加句号
        if random.random() < 0.15:
            parts.append("。")
            current_len += 1
    text = "".join(parts)
    return text[:target_len]


# ============================================================
# 基准测试核心类
# ============================================================


class ChromaBenchmark:
    """ChromaDB 性能基准测试"""

    def __init__(self, chroma_path: str = "./benchmark_db"):
        self.chroma_path = chroma_path
        self.results: dict = {}
        self._model = None

    def _get_model(self):
        """懒加载嵌入模型"""
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            print(f"加载语义向量模型 {DEFAULT_EMBEDDING_MODEL}（首次加载较慢）...")
            t0 = time.time()
            self._model = SentenceTransformer(DEFAULT_EMBEDDING_MODEL)
            print(f"   模型加载耗时: {time.time() - t0:.1f}s")
        return self._model

    def _get_client(self):
        import chromadb
        return chromadb.PersistentClient(path=self.chroma_path)

    def _cleanup(self):
        """清理测试数据库"""
        if os.path.exists(self.chroma_path):
            try:
                client = self._get_client()
                for coll in client.list_collections():
                    client.delete_collection(coll.name)
            except Exception:
                pass
            shutil.rmtree(self.chroma_path, ignore_errors=True)
        # 确保目录干净后等文件系统同步
        import time as _t
        _t.sleep(0.2)

    # ========================
    # 插入性能测试
    # ========================

    def bench_insert(self, sizes: list[int] = None):
        """批量插入性能测试"""
        if sizes is None:
            sizes = [100, 500, 1000, 5000]

        print("\n" + "=" * 60)
        print("📊 测试 1: 插入性能")
        print("=" * 60)

        model = self._get_model()
        insert_results = []

        for n in sizes:
            # 清理
            self._cleanup()

            print(f"\n  🔸 测试 N={n}...")

            # 生成测试数据
            texts = [random_chinese_text() for _ in range(n)]
            ids = [f"bench_{i}" for i in range(n)]

            # 向量化
            t0 = time.time()
            embeddings = model.encode(
                texts, show_progress_bar=False, normalize_embeddings=True, batch_size=64,
            )
            encode_time = time.time() - t0

            # 插入 ChromaDB
            client = self._get_client()
            collection = client.create_collection(
                name="benchmark", metadata={"hnsw:space": "cosine"},
            )

            t1 = time.time()
            BATCH_SIZE = 200
            emb_list = embeddings.tolist()
            for i in range(0, n, BATCH_SIZE):
                end = min(i + BATCH_SIZE, n)
                collection.add(
                    ids=ids[i:end],
                    documents=texts[i:end],
                    embeddings=emb_list[i:end],
                )
            insert_time = time.time() - t1

            result = {
                "n": n,
                "encode_time_s": round(encode_time, 2),
                "insert_time_s": round(insert_time, 3),
                "total_time_s": round(encode_time + insert_time, 2),
                "insert_rate": round(n / insert_time, 1),
                "total_rate": round(n / (encode_time + insert_time), 1),
            }
            insert_results.append(result)

            print(f"     向量化: {encode_time:.2f}s | "
                  f"插入: {insert_time:.3f}s | "
                  f"速率: {result['insert_rate']:.0f} 条/s (纯插入) | "
                  f"{result['total_rate']:.0f} 条/s (含向量化)")

        self.results["insert"] = insert_results
        return insert_results

    # ========================
    # 检索延迟测试
    # ========================

    def bench_query_latency(self, db_size: int = 1000, n_queries: int = 50,
                            top_k_list: list[int] = None):
        """检索延迟测试"""
        if top_k_list is None:
            top_k_list = [5, 10, 20]

        print("\n" + "=" * 60)
        print("📊 测试 2: 检索延迟")
        print("=" * 60)

        model = self._get_model()

        # 准备数据库
        self._cleanup()
        print(f"  准备 {db_size} 条数据库记录...")
        texts = [random_chinese_text() for _ in range(db_size)]
        ids = [f"bench_{i}" for i in range(db_size)]
        embeddings = model.encode(
            texts, show_progress_bar=False, normalize_embeddings=True, batch_size=64,
        )

        client = self._get_client()
        collection = client.create_collection(
            name="benchmark", metadata={"hnsw:space": "cosine"},
        )
        emb_list = embeddings.tolist()
        for i in range(0, db_size, 200):
            end = min(i + 200, db_size)
            collection.add(ids=ids[i:end], documents=texts[i:end], embeddings=emb_list[i:end])

        # 生成查询向量
        queries = [random_chinese_text(20, 80) for _ in range(n_queries)]
        query_embeddings = model.encode(
            queries, show_progress_bar=False, normalize_embeddings=True,
        ).tolist()

        latency_results = []

        for top_k in top_k_list:
            latencies = []
            for qvec in query_embeddings:
                t0 = time.perf_counter()
                collection.query(query_embeddings=[qvec], n_results=top_k)
                latencies.append((time.perf_counter() - t0) * 1000)  # ms

            latencies.sort()
            result = {
                "top_k": top_k,
                "db_size": db_size,
                "n_queries": n_queries,
                "avg_ms": round(sum(latencies) / len(latencies), 2),
                "p50_ms": round(latencies[len(latencies) // 2], 2),
                "p95_ms": round(latencies[int(len(latencies) * 0.95)], 2),
                "p99_ms": round(latencies[int(len(latencies) * 0.99)], 2),
                "min_ms": round(latencies[0], 2),
                "max_ms": round(latencies[-1], 2),
            }
            latency_results.append(result)

            print(f"\n  🔹 top_k={top_k} (db={db_size}, queries={n_queries})")
            print(f"     AVG={result['avg_ms']:.2f}ms | "
                  f"P50={result['p50_ms']:.2f}ms | "
                  f"P95={result['p95_ms']:.2f}ms | "
                  f"P99={result['p99_ms']:.2f}ms")

        self.results["query_latency"] = latency_results
        return latency_results

    # ========================
    # 并发检索测试
    # ========================

    def bench_concurrent(self, db_size: int = 1000, worker_counts: list[int] = None,
                         queries_per_worker: int = 20):
        """多线程并发检索测试"""
        if worker_counts is None:
            worker_counts = [1, 5, 10, 20]

        print("\n" + "=" * 60)
        print("📊 测试 3: 并发检索")
        print("=" * 60)

        model = self._get_model()

        # 复用已有数据库或重建
        self._cleanup()
        print(f"  准备 {db_size} 条数据库记录...")
        texts = [random_chinese_text() for _ in range(db_size)]
        ids = [f"bench_{i}" for i in range(db_size)]
        embeddings = model.encode(
            texts, show_progress_bar=False, normalize_embeddings=True, batch_size=64,
        )
        client = self._get_client()
        collection = client.create_collection(
            name="benchmark", metadata={"hnsw:space": "cosine"},
        )
        emb_list = embeddings.tolist()
        for i in range(0, db_size, 200):
            end = min(i + 200, db_size)
            collection.add(ids=ids[i:end], documents=texts[i:end], embeddings=emb_list[i:end])

        # 预生成查询向量
        total_queries_needed = max(worker_counts) * queries_per_worker
        query_texts = [random_chinese_text(20, 80) for _ in range(total_queries_needed)]
        all_query_vecs = model.encode(
            query_texts, show_progress_bar=False, normalize_embeddings=True,
        ).tolist()

        concurrent_results = []

        for n_workers in worker_counts:
            import chromadb as _chromadb

            def worker_fn(worker_id):
                """单个工作线程：执行 queries_per_worker 次查询"""
                _client = _chromadb.PersistentClient(path=self.chroma_path)
                _coll = _client.get_collection("benchmark")
                latencies = []
                start_idx = worker_id * queries_per_worker
                for i in range(queries_per_worker):
                    qvec = all_query_vecs[start_idx + i]
                    t0 = time.perf_counter()
                    _coll.query(query_embeddings=[qvec], n_results=5)
                    latencies.append((time.perf_counter() - t0) * 1000)
                return latencies

            t_start = time.time()
            all_latencies = []

            with ThreadPoolExecutor(max_workers=n_workers) as executor:
                futures = [executor.submit(worker_fn, w) for w in range(n_workers)]
                for fut in as_completed(futures):
                    all_latencies.extend(fut.result())

            wall_time = time.time() - t_start
            total_q = n_workers * queries_per_worker
            all_latencies.sort()

            result = {
                "workers": n_workers,
                "total_queries": total_q,
                "wall_time_s": round(wall_time, 2),
                "qps": round(total_q / wall_time, 1),
                "avg_ms": round(sum(all_latencies) / len(all_latencies), 2),
                "p95_ms": round(all_latencies[int(len(all_latencies) * 0.95)], 2),
            }
            concurrent_results.append(result)

            print(f"\n  🔹 workers={n_workers} | "
                  f"总查询={total_q} | "
                  f"耗时={wall_time:.2f}s | "
                  f"QPS={result['qps']:.1f} | "
                  f"AVG={result['avg_ms']:.1f}ms | "
                  f"P95={result['p95_ms']:.1f}ms")

        self.results["concurrent"] = concurrent_results
        return concurrent_results

    # ========================
    # 存储空间测试
    # ========================

    def bench_storage(self, sizes: list[int] = None):
        """不同数据量下的磁盘占用测试"""
        if sizes is None:
            sizes = [100, 500, 1000, 5000]

        print("\n" + "=" * 60)
        print("📊 测试 4: 存储空间")
        print("=" * 60)

        model = self._get_model()
        storage_results = []

        for n in sizes:
            self._cleanup()

            texts = [random_chinese_text() for _ in range(n)]
            ids = [f"bench_{i}" for i in range(n)]
            embeddings = model.encode(
                texts, show_progress_bar=False, normalize_embeddings=True, batch_size=64,
            )

            client = self._get_client()
            collection = client.create_collection(
                name="benchmark", metadata={"hnsw:space": "cosine"},
            )
            emb_list = embeddings.tolist()
            for i in range(0, n, 200):
                end = min(i + 200, n)
                collection.add(ids=ids[i:end], documents=texts[i:end], embeddings=emb_list[i:end])

            # 计算磁盘占用
            total_bytes = 0
            for dirpath, dirnames, filenames in os.walk(self.chroma_path):
                for f in filenames:
                    total_bytes += os.path.getsize(os.path.join(dirpath, f))

            total_chars = sum(len(t) for t in texts)
            avg_chars = total_chars // n

            result = {
                "n": n,
                "storage_mb": round(total_bytes / (1024 * 1024), 2),
                "storage_bytes": total_bytes,
                "per_record_kb": round(total_bytes / n / 1024, 2),
                "total_chars": total_chars,
                "avg_chars_per_doc": avg_chars,
            }
            storage_results.append(result)

            print(f"  🔹 N={n:>5} | "
                  f"磁盘: {result['storage_mb']:.2f} MB | "
                  f"每条: {result['per_record_kb']:.1f} KB | "
                  f"平均文本: {avg_chars} 字符")

        self.results["storage"] = storage_results
        return storage_results

    # ========================
    # 汇总报告
    # ========================

    def report(self, output_path: str = None):
        """生成性能报告"""
        print("\n" + "=" * 60)
        print("📋 性能测试汇总报告")
        print("=" * 60)

        if "insert" in self.results:
            print("\n▎插入性能:")
            print(f"  {'N':>8} | {'向量化':>8} | {'插入':>8} | {'纯插入速率':>10} | {'总速率':>8}")
            print("  " + "-" * 55)
            for r in self.results["insert"]:
                print(f"  {r['n']:>8} | {r['encode_time_s']:>7.2f}s | "
                      f"{r['insert_time_s']:>7.3f}s | "
                      f"{r['insert_rate']:>9.0f}/s | {r['total_rate']:>7.0f}/s")

        if "query_latency" in self.results:
            print("\n▎检索延迟:")
            print(f"  {'top_k':>6} | {'AVG':>8} | {'P50':>8} | {'P95':>8} | {'P99':>8}")
            print("  " + "-" * 48)
            for r in self.results["query_latency"]:
                print(f"  {r['top_k']:>6} | {r['avg_ms']:>7.2f}ms | "
                      f"{r['p50_ms']:>7.2f}ms | {r['p95_ms']:>7.2f}ms | "
                      f"{r['p99_ms']:>7.2f}ms")

        if "concurrent" in self.results:
            print("\n▎并发检索:")
            print(f"  {'Workers':>8} | {'总查询':>6} | {'耗时':>6} | {'QPS':>8} | {'P95延迟':>8}")
            print("  " + "-" * 50)
            for r in self.results["concurrent"]:
                print(f"  {r['workers']:>8} | {r['total_queries']:>6} | "
                      f"{r['wall_time_s']:>5.2f}s | {r['qps']:>7.1f} | "
                      f"{r['p95_ms']:>7.1f}ms")

        if "storage" in self.results:
            print("\n▎存储空间:")
            print(f"  {'N':>8} | {'磁盘占用':>10} | {'每条':>8} | {'文本均长':>8}")
            print("  " + "-" * 45)
            for r in self.results["storage"]:
                print(f"  {r['n']:>8} | {r['storage_mb']:>9.2f}MB | "
                      f"{r['per_record_kb']:>7.1f}KB | {r['avg_chars_per_doc']:>7}字符")

        # 保存 JSON 报告
        runtime_dir = Path(__file__).resolve().parents[3] / "storage_layer" / "runtime" / "current_console"
        if output_path is None:
            output_path = str(runtime_dir / "benchmark_report.json")

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(self.results, f, ensure_ascii=False, indent=2)
        print(f"\n💾 详细报告已保存: {output_path}")


# ============================================================
# 主入口
# ============================================================


def main():
    parser = argparse.ArgumentParser(description="ChromaDB 性能基准测试")
    parser.add_argument(
        "--sizes", default="100,500,1000",
        help="插入测试的数据量（逗号分隔）",
    )
    parser.add_argument(
        "--db-size", type=int, default=1000,
        help="检索/并发测试的数据库大小",
    )
    parser.add_argument(
        "--queries", type=int, default=50,
        help="检索延迟测试的查询次数",
    )
    parser.add_argument(
        "--skip-insert", action="store_true",
        help="跳过插入测试",
    )
    parser.add_argument(
        "--skip-concurrent", action="store_true",
        help="跳过并发测试",
    )
    parser.add_argument(
        "--skip-storage", action="store_true",
        help="跳过存储测试",
    )
    args = parser.parse_args()

    sizes = [int(x.strip()) for x in args.sizes.split(",")]

    runtime_dir = Path(__file__).resolve().parents[3] / "storage_layer" / "runtime" / "current_console"
    bench = ChromaBenchmark(chroma_path=str(runtime_dir / "benchmark-db"))

    t_total = time.time()

    try:
        if not args.skip_insert:
            bench.bench_insert(sizes=sizes)

        bench.bench_query_latency(db_size=args.db_size, n_queries=args.queries)

        if not args.skip_concurrent:
            bench.bench_concurrent(db_size=args.db_size)

        if not args.skip_storage:
            bench.bench_storage(sizes=sizes)

        bench.report()
    finally:
        # 清理测试数据库
        bench._cleanup()

    print(f"\n⏱️ 基准测试总耗时: {time.time() - t_total:.1f}s")


if __name__ == "__main__":
    main()
