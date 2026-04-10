"""
纪文龙 — 向量化存储 Pipeline
Label Studio JSON → 解析 → 分块 → BGE-m3 向量化 → Chroma 存储 → 检索验证

与郭继鸿版本的主要改进：
1. 支持 List 标签（原版只处理 Title/Para，漏了 15 个 List 块）
2. 分块策略改进：Title 自动作为新 chunk 的起始，避免标题被切到上一段末尾
3. 更完整的元数据：chunk 保留了 label 分布信息，便于后续分析
4. 数据质量报告：自动统计空块、短文本等质量问题
"""

import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import orjson
from pathlib import Path
from dataclasses import dataclass, field


# ============================================================
# 数据结构
# ============================================================


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

    JSON 结构:
      task.data        → doc_id, page_num, filename, total_pages
      task.annotations → result[] 中成对出现 rectanglelabels + textarea (共享同一个 id)
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

            # 先收集所有 bbox 的标签和位置信息
            bbox_map: dict[str, dict] = {}
            for item in results:
                if item["type"] == "rectanglelabels":
                    bbox_map[item["id"]] = {
                        "label": item["value"]["rectanglelabels"][0],
                        "y": item["value"]["y"],
                    }

            # 再收集文本，与 bbox 配对
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
    """
    blocks = doc.ordered_blocks()
    chunks: list[Chunk] = []
    current_text = ""
    current_pages: set[int] = set()
    current_labels: dict[str, int] = {}

    def _flush():
        """把当前累积的文本作为一个 chunk 保存"""
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
        # overlap: 保留尾部文本
        tail = current_text[-overlap:] if len(current_text) > overlap else ""
        current_text = tail
        current_pages = set()
        current_labels = {}

    for block in blocks:
        # Title 标签 → 强制起新 chunk（标题属于下一段）
        if block.label == "Title" and current_text.strip():
            _flush()

        separator = "\n" if current_text else ""
        line = separator + block.text

        # 超长 → 先切
        if len(current_text) + len(line) > max_chars and current_text.strip():
            _flush()

        current_text += (("\n" if current_text else "") + block.text)
        current_pages.add(block.page_num)
        current_labels[block.label] = current_labels.get(block.label, 0) + 1

    _flush()  # 最后一块
    return chunks


# ============================================================
# Step 3: 向量化 + Chroma 存储
# ============================================================


def vectorize_and_store(
    chunks: list[Chunk],
    collection_name: str = "equipment_manuals",
    chroma_path: str = "./向量数据库",
):
    """
    BGE-m3 向量化 → Chroma 持久化存储。

    首次运行会从 HuggingFace 下载 BGE-m3（~2GB）。
    """
    from sentence_transformers import SentenceTransformer
    import chromadb

    print("加载 BGE-m3 模型...")
    model = SentenceTransformer("BAAI/bge-m3")

    texts = [c.text for c in chunks]
    print(f"向量化 {len(texts)} 个文本块...")
    embeddings = model.encode(
        texts,
        show_progress_bar=True,
        normalize_embeddings=True,
        batch_size=32,
    )

    print("写入 Chroma...")
    client = chromadb.PersistentClient(path=chroma_path)
    # 清除旧数据，避免重复
    try:
        client.delete_collection(collection_name)
    except Exception:
        pass
    collection = client.create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
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
        ids=ids,
        documents=texts,
        embeddings=embeddings.tolist(),
        metadatas=metadatas,
    )

    print(f"✅ 已存储 {len(chunks)} 个文本块 → Chroma [{collection_name}]")
    return collection, model


# ============================================================
# Step 4: 检索验证
# ============================================================


def search(collection, model, query: str, top_k: int = 5):
    """语义检索"""
    query_vec = model.encode([query], normalize_embeddings=True).tolist()
    results = collection.query(query_embeddings=query_vec, n_results=top_k)

    print(f"\n🔍 查询: \"{query}\"")
    print("-" * 60)
    for i, (doc, meta, dist) in enumerate(
        zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        )
    ):
        sim = 1 - dist
        print(f"\n  [{i+1}] 相似度: {sim:.4f} | 来源: {meta['filename']}")
        print(f"      页码: {meta['page_nums']}")
        print(f"      内容: {doc[:200]}{'...' if len(doc) > 200 else ''}")


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

        # 标签分布
        label_counts: dict[str, int] = {}
        for b in blocks:
            label_counts[b.label] = label_counts.get(b.label, 0) + 1
        print(f"   标签分布: {label_counts}")

        # 质量检查
        short_blocks = [b for b in blocks if len(b.text) < 5]
        if short_blocks:
            issues.append(f"doc{doc_id}: {len(short_blocks)} 个极短文本块（<5字符）")
            for b in short_blocks[:3]:
                print(f"   ⚠️ 极短块 p{b.page_num} [{b.label}]: \"{b.text}\"")

        long_blocks = [b for b in blocks if len(b.text) > 2000]
        if long_blocks:
            issues.append(f"doc{doc_id}: {len(long_blocks)} 个超长文本块（>2000字符）")

        # 页码覆盖
        annotated_pages = set(b.page_num for b in blocks)
        missing_pages = set(range(1, doc.total_pages + 1)) - annotated_pages
        if missing_pages:
            issues.append(f"doc{doc_id}: 缺失页 {sorted(missing_pages)}")

    # chunk 统计
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

    parser = argparse.ArgumentParser(description="纪文龙 — 向量化存储 Pipeline")
    parser.add_argument(
        "--json",
        default=str(
            Path(__file__).parent.parent.parent
            / "数据"
            / "project-1-at-2026-04-09-07-02-f7d8cb93.json"
        ),
        help="Label Studio JSON 文件路径",
    )
    parser.add_argument("--max-chars", type=int, default=500, help="分块最大字符数")
    parser.add_argument("--overlap", type=int, default=50, help="分块重叠字符数")
    parser.add_argument("--vectorize", action="store_true", help="启用向量化+存储")
    parser.add_argument("--search", action="store_true", help="启用检索Demo")
    parser.add_argument("--query", type=str, default=None, help="自定义查询")
    args = parser.parse_args()

    # Step 1: 解析
    print("=" * 60)
    print("Step 1: 解析 Label Studio JSON")
    print("=" * 60)
    documents = parse_json(args.json)

    for doc_id, doc in documents.items():
        blocks = doc.ordered_blocks()
        print(f"\n📄 文档 {doc_id}: {doc.filename}")
        print(f"   总页数: {doc.total_pages}, 标注块: {len(blocks)}")
        for b in blocks[:3]:
            print(f"   [{b.label}] p{b.page_num}: {b.text[:60]}...")

    # Step 2: 分块
    print("\n" + "=" * 60)
    print("Step 2: 文本分块")
    print("=" * 60)
    all_chunks: list[Chunk] = []
    for doc in documents.values():
        chunks = chunk_document(doc, max_chars=args.max_chars, overlap=args.overlap)
        all_chunks.extend(chunks)
        print(f"📄 {doc.filename}: {len(chunks)} 个 chunk")

    # 预览
    for i, chunk in enumerate(all_chunks[:3]):
        print(f"\n--- Chunk {i} [{chunk.chunk_id}] ---")
        print(f"元数据: {chunk.metadata}")
        print(chunk.text[:200])

    # 数据质量报告
    quality_report(documents, all_chunks)

    # Step 3: 向量化 + 存储
    if args.vectorize:
        print("\n" + "=" * 60)
        print("Step 3: BGE-m3 向量化 + Chroma 存储")
        print("=" * 60)
        collection, model = vectorize_and_store(all_chunks)

        # Step 4: 检索
        if args.search:
            print("\n" + "=" * 60)
            print("Step 4: 语义检索验证")
            print("=" * 60)
            test_queries = [
                "燃气轮机健康管理",
                "故障诊断方法",
                "船舶动力装置",
            ]
            if args.query:
                test_queries.insert(0, args.query)
            for q in test_queries:
                search(collection, model, q)
    else:
        print("\n💡 提示: 添加 --vectorize 启用向量化, --search 启用检索Demo")
        print("   完整运行: python 源代码/纪文龙/向量化存储.py --vectorize --search")


if __name__ == "__main__":
    main()
