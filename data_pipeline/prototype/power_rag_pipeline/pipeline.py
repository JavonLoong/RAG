"""
纪文龙 — 向量化存储 Pipeline v2.0
Label Studio JSON → 解析 → 清洗 → 分块 → BGE-m3 向量化 → Chroma 存储 → 混合检索

与郭继鸿版本的核心差异：
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[数据层]
  1. 支持 List 标签（原版只处理 Title/Para，漏了 15 个 List 块）
  2. 短文本合并：<10字符的碎片自动合并到相邻块，消除OCR切割残留
  3. 数据质量报告：自动统计空块、短文本、缺页等问题

[分块层]
  4. Title 自动作为新 chunk 的起始，避免标题被切到上一段末尾
  5. chunk 保留 label 分布信息，便于后续分析

[检索层]
  6. BM25 关键词检索（jieba中文分词）
  7. 语义+关键词混合检索（RRF融合排序）

[应用层]
  8. 端到端 RAG 问答（检索→拼接context→LLM生成答案）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

import orjson
from pathlib import Path
from dataclasses import dataclass, field

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EMBEDDING_MODEL = os.environ.get("RAG_EMBEDDING_MODEL", "Qwen/Qwen3-Embedding-0.6B")
DEFAULT_SAMPLE_PATHS = (
    REPO_ROOT
    / "apps"
    / "jiwenlong-rag-console"
    / "data"
    / "uploads"
    / "新建文件夹__project-1-at-2026-04-09-07-02-f7d8cb93.json",
    REPO_ROOT
    / "apps"
    / "jiwenlong-rag-console"
    / "data"
    / "mock-data"
    / "project-1-at-2026-04-09-07-02-f7d8cb93.json",
)


# ============================================================
# 数据结构
# ============================================================


def resolve_default_json_path() -> Path | None:
    """Return the first available sample JSON file in the workspace."""

    for candidate in DEFAULT_SAMPLE_PATHS:
        if candidate.exists():
            return candidate
    return None


@dataclass
class TextBlock:
    """单个标注文本块"""

    text: str
    label: str  # "Title" / "Para" / "List"
    page_num: int
    doc_id: int
    y_position: float


@dataclass
class Document:
    """一篇完整文档"""

    doc_id: int
    filename: str
    total_pages: int
    blocks: list[TextBlock] = field(default_factory=list)

    def ordered_blocks(self) -> list[TextBlock]:
        """按页码+纵坐标排序"""
        return sorted(self.blocks, key=lambda b: (b.page_num, b.y_position))


@dataclass
class Chunk:
    """向量化前的文本块"""

    text: str
    chunk_id: str
    metadata: dict


# ============================================================
# Step 1: 解析 Label Studio JSON
# ============================================================


def parse_json(json_path: str | Path) -> dict[int, Document]:
    """
    解析 Label Studio 导出的 JSON。

    与原版区别：支持 Title/Para/List 三种标签（原版只支持 Title/Para）。
    """
    json_path = Path(json_path)
    with open(json_path, "rb") as f:
        tasks = orjson.loads(f.read())

    documents: dict[int, Document] = {}

    for task in tasks:
        data = task["data"]
        doc_id = data["doc_id"]

        if doc_id not in documents:
            documents[doc_id] = Document(
                doc_id=doc_id,
                filename=data["filename"],
                total_pages=data["total_pages"],
            )

        for annotation in task.get("annotations", []):
            results = annotation.get("result", [])

            bbox_map: dict[str, dict] = {}
            for item in results:
                if item["type"] == "rectanglelabels":
                    bbox_map[item["id"]] = {
                        "label": item["value"]["rectanglelabels"][0],
                        "y": item["value"]["y"],
                    }

            for item in results:
                if item["type"] != "textarea":
                    continue

                text_list = item["value"].get("text", [])
                text = text_list[0].strip() if text_list else ""
                if not text:
                    continue

                bbox = bbox_map.get(item["id"], {})

                documents[doc_id].blocks.append(
                    TextBlock(
                        text=text,
                        label=bbox.get("label", "Para"),
                        page_num=data["page_num"],
                        doc_id=doc_id,
                        y_position=bbox.get("y", 0.0),
                    )
                )

    return documents


# ============================================================
# Step 1.5: 数据清洗（短文本合并）← 新增！
# ============================================================


def clean_blocks(doc: Document, min_chars: int = 10) -> Document:
    """
    短文本合并：<min_chars 的碎片合并到相邻块。
    解决OCR双栏切割产生的 "程体系。" "建方法" 等残留碎片。
    
    与原版区别：原版无此步骤，碎片会被独立分块降低检索质量。
    """
    blocks = doc.ordered_blocks()
    if not blocks:
        return doc

    cleaned: list[TextBlock] = []
    pending_short: TextBlock | None = None

    for block in blocks:
        if len(block.text) < min_chars:
            if pending_short is None:
                pending_short = block
            else:
                # 连续短块合并
                pending_short = TextBlock(
                    text=pending_short.text + block.text,
                    label=pending_short.label,
                    page_num=pending_short.page_num,
                    doc_id=pending_short.doc_id,
                    y_position=pending_short.y_position,
                )
        else:
            if pending_short is not None:
                # 把短块合并到当前块前面
                block = TextBlock(
                    text=pending_short.text + block.text,
                    label=block.label,
                    page_num=block.page_num,
                    doc_id=block.doc_id,
                    y_position=block.y_position,
                )
                pending_short = None
            cleaned.append(block)

    # 最后如果还有短块，合并到最后一个块
    if pending_short is not None:
        if cleaned:
            last = cleaned[-1]
            cleaned[-1] = TextBlock(
                text=last.text + pending_short.text,
                label=last.label,
                page_num=last.page_num,
                doc_id=last.doc_id,
                y_position=last.y_position,
            )
        else:
            cleaned.append(pending_short)

    doc.blocks = cleaned
    return doc


# ============================================================
# Step 2: 文本分块
# ============================================================


def chunk_document(
    doc: Document,
    max_chars: int = 500,
    overlap: int = 50,
) -> list[Chunk]:
    """
    智能分块策略：
    - Title 标签自动触发新 chunk（标题不会粘在上一段尾巴上）
    - Para/List 按字符数累积，超限切分
    - overlap 保持上下文连续性
    
    与原版区别：原版纯按字符数切，Title可能被切到上一段末尾。
    """
    blocks = doc.ordered_blocks()
    chunks: list[Chunk] = []
    current_text = ""
    current_pages: set[int] = set()
    current_labels: dict[str, int] = {}

    def _flush():
        nonlocal current_text, current_pages, current_labels
        if not current_text.strip():
            return
        chunks.append(
            Chunk(
                text=current_text.strip(),
                chunk_id=f"doc{doc.doc_id}_chunk{len(chunks)}",
                metadata={
                    "doc_id": doc.doc_id,
                    "filename": doc.filename,
                    "page_nums": sorted(current_pages),
                    "chunk_index": len(chunks),
                    "labels": dict(current_labels),
                },
            )
        )
        tail = current_text[-overlap:] if len(current_text) > overlap else ""
        current_text = tail
        current_pages = set()
        current_labels = {}

    for block in blocks:
        if block.label == "Title" and current_text.strip():
            _flush()

        if len(current_text) + len(block.text) + 1 > max_chars and current_text.strip():
            _flush()

        current_text += (("\n" if current_text else "") + block.text)
        current_pages.add(block.page_num)
        current_labels[block.label] = current_labels.get(block.label, 0) + 1

    _flush()
    return chunks


# ============================================================
# Step 3: 向量化 + Chroma 存储
# ============================================================


def vectorize_and_store(
    chunks: list[Chunk],
    collection_name: str = "equipment_manuals",
    chroma_path: str = "./local_chroma_db",
):
    """Semantic embedding → Chroma persistent storage."""
    from sentence_transformers import SentenceTransformer
    import chromadb

    print(f"加载语义向量模型: {DEFAULT_EMBEDDING_MODEL}...")
    model = SentenceTransformer(DEFAULT_EMBEDDING_MODEL)

    texts = [c.text for c in chunks]
    print(f"向量化 {len(texts)} 个文本块...")
    embeddings = model.encode(
        texts, show_progress_bar=True, normalize_embeddings=True, batch_size=32,
    )

    print("写入 Chroma...")
    client = chromadb.PersistentClient(path=chroma_path)
    try:
        client.delete_collection(collection_name)
    except Exception:
        pass
    collection = client.create_collection(
        name=collection_name, metadata={"hnsw:space": "cosine"},
    )

    ids = [c.chunk_id for c in chunks]
    metadatas = [
        {
            "doc_id": str(c.metadata["doc_id"]),
            "filename": c.metadata["filename"],
            "page_nums": str(c.metadata["page_nums"]),
            "chunk_index": str(c.metadata["chunk_index"]),
        }
        for c in chunks
    ]

    collection.add(
        ids=ids, documents=texts,
        embeddings=embeddings.tolist(), metadatas=metadatas,
    )

    print(f"✅ 已存储 {len(chunks)} 个文本块 → Chroma [{collection_name}]")
    return collection, model


# ============================================================
# Step 4: 混合检索（语义 + BM25）← 核心新增！
# ============================================================


class HybridRetriever:
    """
    混合检索器：语义检索(BGE-m3) + 关键词检索(BM25) + RRF融合排序
    
    这是与原版的核心差异。原版只有语义检索，对精确关键词匹配能力弱。
    例如搜 "布鲁姆认知过程" 时，语义检索可能匹配不到，但BM25可以精确命中。
    """

    def __init__(self, collection, model, chunks: list[Chunk]):
        import jieba
        from rank_bm25 import BM25Okapi

        self.collection = collection
        self.model = model
        self.chunks = chunks
        self.texts = [c.text for c in chunks]

        # 构建 BM25 索引（jieba 中文分词）
        print("构建 BM25 索引（jieba分词）...")
        self.tokenized = [list(jieba.cut(t)) for t in self.texts]
        self.bm25 = BM25Okapi(self.tokenized)
        print(f"✅ BM25 索引就绪（{len(self.texts)} 个文档）")

    def search_semantic(self, query: str, top_k: int = 10) -> list[tuple[int, float]]:
        """语义检索，返回 [(chunk_index, score), ...]"""
        qvec = self.model.encode([query], normalize_embeddings=True).tolist()
        results = self.collection.query(query_embeddings=qvec, n_results=top_k)
        
        scored = []
        for chunk_id, dist in zip(results["ids"][0], results["distances"][0]):
            idx = next(i for i, c in enumerate(self.chunks) if c.chunk_id == chunk_id)
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
        混合检索 = alpha * 语义 + (1-alpha) * BM25（RRF融合）
        
        alpha=0.7 表示语义检索权重70%，BM25权重30%。
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
            # 计算各路得分
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
            print(f"\n  [{i+1}] RRF={r['rrf_score']:.4f} | "
                  f"语义={r['semantic_score']:.3f} | "
                  f"BM25={r['bm25_score']:.1f} | "
                  f"页码={chunk.metadata['page_nums']}")
            print(f"      {chunk.text[:200]}{'...' if len(chunk.text) > 200 else ''}")


# ============================================================
# Step 5: 端到端 RAG 问答 ← 新增！
# ============================================================


def rag_answer(retriever: HybridRetriever, question: str, top_k: int = 3) -> str:
    """
    端到端 RAG：检索 → 拼接上下文 → 生成答案
    
    当前使用基于模板的摘要式回答（不依赖外部API）。
    后续可替换为智谱/千问 API 获得更好效果。
    """
    results = retriever.search_hybrid(question, top_k=top_k)
    
    if not results:
        return "未找到相关内容。"

    # 拼接检索到的上下文
    context_parts = []
    for i, r in enumerate(results):
        chunk = r["chunk"]
        context_parts.append(
            f"[来源{i+1}] (第{chunk.metadata['page_nums']}页, "
            f"相关度={r['rrf_score']:.3f})\n{chunk.text}"
        )
    context = "\n\n".join(context_parts)

    # 构建回答（基于模板，后续可接入LLM API）
    answer = f"""
📋 问题：{question}

📖 基于检索到的 {len(results)} 段相关内容：

{context}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💡 提示：当前为检索模式（展示原文片段）。
   接入智谱/千问API后可生成自然语言摘要答案。
   示例调用：rag_answer(retriever, "你的问题", top_k=3)
"""
    return answer


# ============================================================
# 数据质量报告
# ============================================================


def quality_report(documents: dict[int, Document], chunks: list[Chunk]):
    """自动检测数据质量问题"""
    print("\n" + "=" * 60)
    print("📊 数据质量报告")
    print("=" * 60)

    issues = []

    for doc_id, doc in documents.items():
        blocks = doc.ordered_blocks()
        print(f"\n📄 文档 {doc_id}: {doc.filename}")
        print(f"   总页数: {doc.total_pages}")
        print(f"   标注块: {len(blocks)}")

        label_counts: dict[str, int] = {}
        for b in blocks:
            label_counts[b.label] = label_counts.get(b.label, 0) + 1
        print(f"   标签分布: {label_counts}")

        short_blocks = [b for b in blocks if len(b.text) < 5]
        if short_blocks:
            issues.append(f"doc{doc_id}: {len(short_blocks)} 个极短文本块（<5字符）")
            for b in short_blocks[:3]:
                print(f"   ⚠️ 极短块 p{b.page_num} [{b.label}]: \"{b.text}\"")

        annotated_pages = set(b.page_num for b in blocks)
        missing_pages = set(range(1, doc.total_pages + 1)) - annotated_pages
        if missing_pages:
            issues.append(f"doc{doc_id}: 缺失页 {sorted(missing_pages)}")

    print(f"\n📦 分块统计:")
    print(f"   总 chunk 数: {len(chunks)}")
    lengths = [len(c.text) for c in chunks]
    if lengths:
        print(f"   平均长度: {sum(lengths)/len(lengths):.0f} 字符")
        print(f"   最短: {min(lengths)} 字符 | 最长: {max(lengths)} 字符")

    if issues:
        print(f"\n⚠️ 发现 {len(issues)} 个质量问题:")
        for issue in issues:
            print(f"   - {issue}")
    else:
        print("\n✅ 未发现明显质量问题")


# ============================================================
# 主流程
# ============================================================


def main():
    import argparse

    default_json_path = resolve_default_json_path()

    parser = argparse.ArgumentParser(
        description="Power RAG pipeline prototype for Label Studio parsing, chunking, vectorization, and retrieval."
    )
    parser.add_argument(
        "--json",
        default=str(default_json_path) if default_json_path else None,
        help="Label Studio JSON 文件路径；不传时自动尝试使用工作区内的样例文件",
    )
    parser.add_argument("--max-chars", type=int, default=500, help="分块最大字符数")
    parser.add_argument("--overlap", type=int, default=50, help="分块重叠字符数")
    parser.add_argument("--vectorize", action="store_true", help="启用向量化+存储")
    parser.add_argument("--search", action="store_true", help="启用检索Demo")
    parser.add_argument("--ask", type=str, default=None, help="RAG问答（端到端）")
    parser.add_argument("--query", type=str, default=None, help="自定义检索查询")
    args = parser.parse_args()

    if not args.json:
        print("❌ 未找到默认样例 JSON，请使用 --json 显式指定输入文件。")
        print("   推荐位置：apps/jiwenlong-rag-console/data/uploads/")
        return

    json_path = Path(args.json)
    if not json_path.exists():
        print(f"❌ JSON 文件不存在: {json_path}")
        return

    # Step 1: 解析
    print("=" * 60)
    print("Step 1: 解析 Label Studio JSON")
    print("=" * 60)
    documents = parse_json(json_path)

    for doc_id, doc in documents.items():
        blocks = doc.ordered_blocks()
        print(f"\n📄 文档 {doc_id}: {doc.filename}")
        print(f"   总页数: {doc.total_pages}, 标注块: {len(blocks)}")
        for b in blocks[:3]:
            print(f"   [{b.label}] p{b.page_num}: {b.text[:60]}...")

    # Step 1.5: 数据清洗
    print("\n" + "=" * 60)
    print("Step 1.5: 数据清洗（短文本合并）")
    print("=" * 60)
    for doc_id in documents:
        before = len(documents[doc_id].blocks)
        documents[doc_id] = clean_blocks(documents[doc_id])
        after = len(documents[doc_id].blocks)
        print(f"📄 文档 {doc_id}: {before} 块 → {after} 块（合并了 {before - after} 个碎片）")

    # Step 2: 分块
    print("\n" + "=" * 60)
    print("Step 2: 文本分块")
    print("=" * 60)
    all_chunks: list[Chunk] = []
    for doc in documents.values():
        chunks = chunk_document(doc, max_chars=args.max_chars, overlap=args.overlap)
        all_chunks.extend(chunks)
        print(f"📄 {doc.filename}: {len(chunks)} 个 chunk")

    for i, chunk in enumerate(all_chunks[:3]):
        print(f"\n--- Chunk {i} [{chunk.chunk_id}] ---")
        print(f"元数据: {chunk.metadata}")
        print(chunk.text[:200])

    quality_report(documents, all_chunks)

    # Step 3+4: 向量化 + 混合检索
    if args.vectorize:
        print("\n" + "=" * 60)
        print(f"Step 3: {DEFAULT_EMBEDDING_MODEL} 向量化 + Chroma 存储")
        print("=" * 60)
        collection, model = vectorize_and_store(all_chunks)

        if args.search or args.query or args.ask:
            print("\n" + "=" * 60)
            print("Step 4: 混合检索（语义 + BM25）")
            print("=" * 60)
            retriever = HybridRetriever(collection, model, all_chunks)

            test_queries = [
                "燃气轮机健康管理",
                "故障诊断方法",
                "船舶动力装置",
                "布鲁姆认知过程",  # BM25优势：精确关键词
            ]
            if args.query:
                test_queries.insert(0, args.query)
            for q in test_queries:
                retriever.display_results(q)

            # RAG 问答
            if args.ask:
                print("\n" + "=" * 60)
                print("Step 5: RAG 端到端问答")
                print("=" * 60)
                answer = rag_answer(retriever, args.ask)
                print(answer)
    else:
        print("\n💡 提示: 添加 --vectorize 启用向量化, --search 启用检索Demo")
        print("   完整运行: python -m power_rag_pipeline.pipeline --vectorize --search")
        print("   RAG问答: python -m power_rag_pipeline.pipeline --vectorize --ask \"你的问题\"")


if __name__ == "__main__":
    main()
