"""
混合检索器 — 来自项目1（核心竞争力）

语义检索(BGE-m3) + BM25关键词检索(jieba) + RRF融合排序
项目2 只有纯语义检索，这是项目1 的独有优势。
"""
from __future__ import annotations

from typing import Any

from .schemas import ChunkRecord


class HybridRetriever:
    """
    混合检索器：语义检索 + BM25 关键词检索 + RRF 融合排序

    核心差异：项目2 只有纯语义检索，对精确关键词匹配能力弱。
    例如搜 "QC185型号参数" 时，语义检索可能匹配不到，但 BM25 可以精确命中。
    """

    def __init__(self, collection: Any, model: Any, chunks: list[ChunkRecord]):
        import jieba
        from rank_bm25 import BM25Okapi

        self.collection = collection
        self.model = model
        self.chunks = chunks
        self.texts = [c.text for c in chunks]
        self._chunk_id_to_index = {c.chunk_id: i for i, c in enumerate(chunks)}

        # 构建 BM25 索引（jieba 中文分词）
        print("构建 BM25 索引（jieba分词）...")
        self.tokenized = [list(jieba.cut(t)) for t in self.texts]
        self.bm25 = BM25Okapi(self.tokenized)
        print(f"✅ BM25 索引就绪（{len(self.texts)} 个文档）")

    def search_semantic(self, query: str, top_k: int = 10) -> list[tuple[int, float]]:
        """语义检索，返回 [(chunk_index, score), ...]"""
        qvec = self.model.encode([query], normalize_embeddings=True).tolist()
        n_results = min(top_k, len(self.chunks))
        if n_results == 0:
            return []
        results = self.collection.query(query_embeddings=qvec, n_results=n_results)

        scored = []
        for chunk_id, dist in zip(results["ids"][0], results["distances"][0]):
            idx = self._chunk_id_to_index.get(chunk_id)
            if idx is not None:
                scored.append((idx, 1 - dist))  # cosine distance → similarity
        return scored

    def search_bm25(self, query: str, top_k: int = 10) -> list[tuple[int, float]]:
        """BM25 关键词检索"""
        import jieba
        tokens = list(jieba.cut(query))
        scores = self.bm25.get_scores(tokens)

        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
        return [(idx, score) for idx, score in ranked[:top_k] if score > 0]

    def search_hybrid(self, query: str, top_k: int = 5, alpha: float = 0.7) -> list[dict]:
        """
        混合检索 = alpha * 语义 + (1-alpha) * BM25 (RRF 融合)

        alpha=0.7 表示语义检索权重 70%，BM25 权重 30%。
        """
        sem_results = self.search_semantic(query, top_k=top_k * 2)
        bm25_results = self.search_bm25(query, top_k=top_k * 2)

        # RRF (Reciprocal Rank Fusion)
        rrf_k = 60
        scores: dict[int, float] = {}

        for rank, (idx, _) in enumerate(sem_results):
            scores[idx] = scores.get(idx, 0) + alpha / (rrf_k + rank + 1)

        for rank, (idx, _) in enumerate(bm25_results):
            scores[idx] = scores.get(idx, 0) + (1 - alpha) / (rrf_k + rank + 1)

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]

        results = []
        for idx, score in ranked:
            chunk = self.chunks[idx]
            sem_score = next((s for i, s in sem_results if i == idx), 0.0)
            bm25_score = next((s for i, s in bm25_results if i == idx), 0.0)
            results.append({
                "chunk": chunk,
                "rrf_score": score,
                "semantic_score": sem_score,
                "bm25_score": bm25_score,
            })
        return results

    def display_results(self, query: str, top_k: int = 5):
        """格式化展示混合检索结果"""
        results = self.search_hybrid(query, top_k=top_k)

        print(f"\n🔍 查询: \"{query}\"")
        print("-" * 70)
        for i, r in enumerate(results):
            chunk = r["chunk"]
            page_nums = chunk.metadata.get("page_nums", "N/A")
            print(f"\n  [{i+1}] RRF={r['rrf_score']:.4f} | "
                  f"语义={r['semantic_score']:.3f} | "
                  f"BM25={r['bm25_score']:.1f} | "
                  f"页码={page_nums}")
            text_preview = chunk.text[:200]
            print(f"      {text_preview}{'...' if len(chunk.text) > 200 else ''}")
