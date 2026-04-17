"""
Label Studio JSON -> 文本提取 -> 分块 -> BGE向量化 -> Chroma存储
完整的 Phase 1 Pipeline Demo
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import orjson
from pathlib import Path
from dataclasses import dataclass, field


# ============================================================
# 1. 解析 Label Studio JSON，提取结构化文本
# ============================================================

@dataclass
class TextBlock:
    """一个标注文本块"""
    text: str
    label: str          # "Title" 或 "Para"
    page_num: int
    doc_id: int
    y_position: float   # 纵坐标，用于排序

@dataclass
class Document:
    """一篇完整文档"""
    doc_id: int
    filename: str
    total_pages: int
    blocks: list[TextBlock] = field(default_factory=list)

    def get_full_text(self) -> str:
        """按页码和纵坐标排序，拼接全文"""
        sorted_blocks = sorted(self.blocks, key=lambda b: (b.page_num, b.y_position))
        lines = []
        for block in sorted_blocks:
            prefix = "\n## " if block.label == "Title" else ""
            lines.append(f"{prefix}{block.text}")
        return "\n".join(lines)


def parse_labelstudio_json(json_path: str | Path) -> dict[int, Document]:
    """
    解析 Label Studio 导出的 JSON 文件。
    
    返回: {doc_id: Document} 字典
    """
    json_path = Path(json_path)
    with open(json_path, "rb") as f:
        tasks = orjson.loads(f.read())

    documents: dict[int, Document] = {}

    for task in tasks:
        data = task["data"]
        doc_id = data["doc_id"]
        page_num = data["page_num"]
        filename = data["filename"]
        total_pages = data["total_pages"]

        # 如果是新文档，创建 Document
        if doc_id not in documents:
            documents[doc_id] = Document(
                doc_id=doc_id,
                filename=filename,
                total_pages=total_pages,
            )

        # 从 annotations 中提取文本
        for annotation in task.get("annotations", []):
            results = annotation.get("result", [])
            
            # result 是成对出现的: bbox + transcription 共享同一个 id
            # 我们只需要 transcription 类型的结果
            bbox_map = {}  # id -> label 映射
            
            for item in results:
                item_id = item["id"]
                item_type = item["type"]
                value = item["value"]

                if item_type == "rectanglelabels":
                    bbox_map[item_id] = {
                        "label": value["rectanglelabels"][0],
                        "y": value["y"],
                    }
                elif item_type == "textarea":
                    text = value["text"][0] if value.get("text") else ""
                    if not text.strip():
                        continue
                    
                    bbox_info = bbox_map.get(item_id, {})
                    label = bbox_info.get("label", "Para")
                    y_pos = bbox_info.get("y", 0.0)

                    documents[doc_id].blocks.append(TextBlock(
                        text=text.strip(),
                        label=label,
                        page_num=page_num,
                        doc_id=doc_id,
                        y_position=y_pos,
                    ))

    return documents


# ============================================================
# 2. 文本分块 (Chunking)
# ============================================================

@dataclass
class TextChunk:
    """一个准备向量化的文本块"""
    text: str
    metadata: dict  # doc_id, filename, page_nums, chunk_index

def chunk_document(doc: Document, max_chars: int = 500, overlap: int = 50) -> list[TextChunk]:
    """
    将文档按字符数切分，保持语义连贯。
    
    策略：按段落累积，超过 max_chars 时切分。
    """
    sorted_blocks = sorted(doc.blocks, key=lambda b: (b.page_num, b.y_position))
    
    chunks = []
    current_text = ""
    current_pages = set()
    
    for block in sorted_blocks:
        line = f"\n{block.text}" if current_text else block.text
        
        if len(current_text) + len(line) > max_chars and current_text:
            # 切分
            chunks.append(TextChunk(
                text=current_text.strip(),
                metadata={
                    "doc_id": doc.doc_id,
                    "filename": doc.filename,
                    "page_nums": sorted(current_pages),
                    "chunk_index": len(chunks),
                },
            ))
            # 保留 overlap
            current_text = current_text[-overlap:] + line
            current_pages = {block.page_num}
        else:
            current_text += line
            current_pages.add(block.page_num)
    
    # 最后一块
    if current_text.strip():
        chunks.append(TextChunk(
            text=current_text.strip(),
            metadata={
                "doc_id": doc.doc_id,
                "filename": doc.filename,
                "page_nums": sorted(current_pages),
                "chunk_index": len(chunks),
            },
        ))
    
    return chunks


# ============================================================
# 3. 向量化 + 存储 (BGE-m3 + Chroma)
# ============================================================

def vectorize_and_store(chunks: list[TextChunk], collection_name: str = "equipment_manuals"):
    """
    使用 BGE-m3 向量化，存入 Chroma。
    
    注意：首次运行会下载 BGE-m3 模型（约 2GB）。
    """
    from sentence_transformers import SentenceTransformer
    import chromadb

    print("正在加载 BGE-m3 模型...")
    model = SentenceTransformer("BAAI/bge-m3")

    texts = [c.text for c in chunks]
    print(f"正在向量化 {len(texts)} 个文本块...")
    embeddings = model.encode(texts, show_progress_bar=True, normalize_embeddings=True)

    # 存入 Chroma
    print("正在写入 Chroma 数据库...")
    client = chromadb.PersistentClient(path="./chroma_db")
    collection = client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )

    ids = [f"doc{c.metadata['doc_id']}_chunk{c.metadata['chunk_index']}" for c in chunks]
    metadatas = [
        {
            "doc_id": str(c.metadata["doc_id"]),
            "filename": c.metadata["filename"],
            "page_nums": str(c.metadata["page_nums"]),
        }
        for c in chunks
    ]

    collection.add(
        ids=ids,
        documents=texts,
        embeddings=embeddings.tolist(),
        metadatas=metadatas,
    )

    print(f"✅ 已存储 {len(chunks)} 个文本块到 Chroma (collection: {collection_name})")
    return collection


def search_demo(collection, query: str, n_results: int = 3):
    """简单的检索 Demo"""
    from sentence_transformers import SentenceTransformer
    
    model = SentenceTransformer("BAAI/bge-m3")
    query_embedding = model.encode([query], normalize_embeddings=True).tolist()

    results = collection.query(
        query_embeddings=query_embedding,
        n_results=n_results,
    )

    print(f"\n🔍 查询: \"{query}\"")
    print("-" * 60)
    for i, (doc, meta, dist) in enumerate(zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    )):
        print(f"\n[{i+1}] 相似度: {1-dist:.4f} | 来源: {meta['filename']} {meta['page_nums']}")
        print(f"    {doc[:150]}...")


# ============================================================
# 主流程
# ============================================================

if __name__ == "__main__":
    import sys

    JSON_PATH = Path(__file__).parent / "project-1-at-2026-04-09-07-02-f7d8cb93.json"

    # Step 1: 解析
    print("=" * 60)
    print("Step 1: 解析 Label Studio JSON")
    print("=" * 60)
    documents = parse_labelstudio_json(JSON_PATH)
    
    for doc_id, doc in documents.items():
        print(f"\n📄 文档 {doc_id}: {doc.filename}")
        print(f"   总页数: {doc.total_pages}, 标注块数: {len(doc.blocks)}")
        # 打印前3个文本块预览
        preview_blocks = sorted(doc.blocks, key=lambda b: (b.page_num, b.y_position))[:3]
        for b in preview_blocks:
            print(f"   [{b.label}] p{b.page_num}: {b.text[:60]}...")

    # Step 2: 分块
    print("\n" + "=" * 60)
    print("Step 2: 文本分块")
    print("=" * 60)
    all_chunks = []
    for doc in documents.values():
        chunks = chunk_document(doc, max_chars=500, overlap=50)
        all_chunks.extend(chunks)
        print(f"📄 {doc.filename}: {len(chunks)} 个文本块")
    
    # 预览前2个chunk
    for i, chunk in enumerate(all_chunks[:2]):
        print(f"\n--- Chunk {i} (来自 {chunk.metadata['filename']}) ---")
        print(chunk.text[:200])

    # Step 3: 向量化 + 存储 (可选，需要依赖)
    if "--vectorize" in sys.argv:
        print("\n" + "=" * 60)
        print("Step 3: BGE-m3 向量化 + Chroma 存储")
        print("=" * 60)
        collection = vectorize_and_store(all_chunks)

        # Step 4: 检索 Demo
        if "--search" in sys.argv:
            search_demo(collection, "燃气轮机健康管理技术")
            search_demo(collection, "知识图谱构建方法")
    else:
        print("\n💡 提示: 添加 --vectorize 参数启用向量化存储")
        print("   完整运行: python parse_labelstudio.py --vectorize --search")
