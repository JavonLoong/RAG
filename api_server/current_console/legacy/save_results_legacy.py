"""将Pipeline运行结果保存为UTF-8文本文件"""
import sys, io, os
from pathlib import Path

# 先设置编码
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

script_dir = Path(__file__).resolve().parent
app_dir = script_dir.parent
repo_dir = app_dir.parents[1]
output_path = str(app_dir / "data" / "legacy_run_results.txt")

# 直接用orjson和底层函数，不导入整个pipeline模块（避免stdout冲突）
import orjson
from dataclasses import dataclass, field

json_path = str(repo_dir / "06_成果展示" / "project-1-at-2026-04-09-07-02-f7d8cb93.json")

# 打开输出文件
f = open(output_path, 'w', encoding='utf-8')

def p(text=""):
    print(text)
    f.write(text + "\n")

# ---- Step 1: 解析 ----
p("=" * 60)
p("Step 1: 解析 Label Studio JSON")
p("=" * 60)

with open(json_path, "rb") as jf:
    tasks = orjson.loads(jf.read())

# 统计
doc_info = {}
all_blocks = []

for task in tasks:
    d = task["data"]
    did = d["doc_id"]
    if did not in doc_info:
        doc_info[did] = {
            "filename": d["filename"],
            "total_pages": d["total_pages"],
            "pages": set(),
            "blocks": [],
            "labels": {},
        }
    doc_info[did]["pages"].add(d["page_num"])

    bbox_map = {}
    for ann in task.get("annotations", []):
        for r in ann.get("result", []):
            if r["type"] == "rectanglelabels":
                bbox_map[r["id"]] = {
                    "label": r["value"]["rectanglelabels"][0],
                    "y": r["value"]["y"],
                }
            elif r["type"] == "textarea":
                text_list = r["value"].get("text", [])
                text = text_list[0].strip() if text_list else ""
                if not text:
                    continue
                bbox = bbox_map.get(r["id"], {})
                label = bbox.get("label", "Para")
                block = {
                    "text": text,
                    "label": label,
                    "page_num": d["page_num"],
                    "doc_id": did,
                    "y": bbox.get("y", 0.0),
                }
                doc_info[did]["blocks"].append(block)
                doc_info[did]["labels"][label] = doc_info[did]["labels"].get(label, 0) + 1

p(f"\n总 task 数: {len(tasks)}")
p(f"文档数量: {len(doc_info)}")

for did in sorted(doc_info.keys()):
    info = doc_info[did]
    blocks = sorted(info["blocks"], key=lambda b: (b["page_num"], b["y"]))
    p(f"\n📄 文档 {did}: {info['filename']}")
    p(f"   总页数: {info['total_pages']}, 已标注页: {len(info['pages'])}")
    p(f"   文本块: {len(blocks)}")
    p(f"   标签分布: {info['labels']}")
    p(f"\n   前5个文本块预览:")
    for b in blocks[:5]:
        p(f"   [{b['label']}] 第{b['page_num']}页: {b['text'][:80]}...")

# ---- Step 2: 分块 ----
p("\n" + "=" * 60)
p("Step 2: 文本分块")
p("=" * 60)

MAX_CHARS = 500
OVERLAP = 50
all_chunks = []

for did in sorted(doc_info.keys()):
    info = doc_info[did]
    blocks = sorted(info["blocks"], key=lambda b: (b["page_num"], b["y"]))

    chunks = []
    current_text = ""
    current_pages = set()

    for block in blocks:
        # Title → 新chunk
        if block["label"] == "Title" and current_text.strip():
            chunks.append({
                "text": current_text.strip(),
                "id": f"doc{did}_chunk{len(chunks)}",
                "pages": sorted(current_pages),
            })
            tail = current_text[-OVERLAP:] if len(current_text) > OVERLAP else ""
            current_text = tail
            current_pages = set()

        sep = "\n" if current_text else ""
        line = sep + block["text"]

        if len(current_text) + len(line) > MAX_CHARS and current_text.strip():
            chunks.append({
                "text": current_text.strip(),
                "id": f"doc{did}_chunk{len(chunks)}",
                "pages": sorted(current_pages),
            })
            tail = current_text[-OVERLAP:] if len(current_text) > OVERLAP else ""
            current_text = tail
            current_pages = set()

        current_text += ("\n" if current_text else "") + block["text"]
        current_pages.add(block["page_num"])

    if current_text.strip():
        chunks.append({
            "text": current_text.strip(),
            "id": f"doc{did}_chunk{len(chunks)}",
            "pages": sorted(current_pages),
        })

    p(f"\n📄 文档 {did}: {len(chunks)} 个 chunk")
    all_chunks.extend(chunks)

    for i, ch in enumerate(chunks[:3]):
        p(f"\n  --- Chunk {i} [{ch['id']}] ---")
        p(f"  页码: {ch['pages']}")
        p(f"  {ch['text'][:300]}")

# 统计
lengths = [len(c["text"]) for c in all_chunks]
p(f"\n📦 分块统计:")
p(f"   总 chunk 数: {len(all_chunks)}")
p(f"   平均长度: {sum(lengths)/len(lengths):.0f} 字符")
p(f"   最短: {min(lengths)} 字符 | 最长: {max(lengths)} 字符")

# 质量问题
p("\n⚠️ 数据质量检查:")
for did in sorted(doc_info.keys()):
    blocks = doc_info[did]["blocks"]
    short = [b for b in blocks if len(b["text"]) < 5]
    if short:
        p(f"   doc{did}: {len(short)} 个极短文本块（<5字符）")
        for b in short[:5]:
            p(f"     第{b['page_num']}页 [{b['label']}]: \"{b['text']}\"")

# ---- Step 3: 向量化 + 存储 ----
p("\n" + "=" * 60)
p("Step 3: BGE-m3 向量化 + Chroma 存储")
p("=" * 60)

from sentence_transformers import SentenceTransformer
import chromadb

p("加载 BGE-m3 模型...")
model = SentenceTransformer("BAAI/bge-m3")

texts = [c["text"] for c in all_chunks]
p(f"向量化 {len(texts)} 个文本块...")
embeddings = model.encode(texts, show_progress_bar=True, normalize_embeddings=True, batch_size=32)

chroma_path = str(app_dir / "data" / "chroma")
p(f"写入 Chroma 数据库 ({chroma_path})...")
client = chromadb.PersistentClient(path=chroma_path)
try:
    client.delete_collection("equipment_manuals")
except Exception:
    pass
collection = client.create_collection(
    name="equipment_manuals",
    metadata={"hnsw:space": "cosine"},
)

ids = [c["id"] for c in all_chunks]
metadatas = [
    {"doc_id": str(next(did for did in doc_info)), "filename": doc_info[next(iter(doc_info))]["filename"], "page_nums": str(c["pages"])}
    for c in all_chunks
]

collection.add(ids=ids, documents=texts, embeddings=embeddings.tolist(), metadatas=metadatas)
p(f"✅ 已存储 {len(all_chunks)} 个文本块到 Chroma")

# ---- Step 4: 检索 ----
p("\n" + "=" * 60)
p("Step 4: 语义检索验证")
p("=" * 60)

test_queries = [
    "燃气轮机健康管理",
    "故障诊断方法",
    "船舶动力装置",
    "知识图谱构建",
    "课程体系设计",
]

for query in test_queries:
    qvec = model.encode([query], normalize_embeddings=True).tolist()
    results = collection.query(query_embeddings=qvec, n_results=3)

    p(f"\n🔍 查询: \"{query}\"")
    p("-" * 60)
    for i, (doc, meta, dist) in enumerate(zip(
        results["documents"][0], results["metadatas"][0], results["distances"][0]
    )):
        sim = 1 - dist
        p(f"\n  [{i+1}] 相似度: {sim:.4f} | 来源: 第{meta['page_nums']}页")
        p(f"      内容: {doc[:200]}{'...' if len(doc) > 200 else ''}")

p("\n" + "=" * 60)
p("✅ Pipeline 全流程完成！")
p("=" * 60)

f.close()
print(f"\n结果已保存至: {output_path}")
