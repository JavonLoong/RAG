"""测试前端 API 接口"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import requests
import os
import glob
import time

BASE = "http://localhost:8000"

# 1. 上传模拟文件
print("=" * 50)
print("Step 1: 上传模拟 JSON 文件")
print("=" * 50)
files = glob.glob(r"d:\虚拟C盘\RAG项目_动力装备知识库\03_数据\标注数据\mock_*.json")
for fpath in files:
    fname = os.path.basename(fpath)
    with open(fpath, "rb") as f:
        resp = requests.post(
            f"{BASE}/api/upload",
            files={"file": (fname, f, "application/json")}
        )
    data = resp.json()
    print(f"  ✅ {fname}: {data.get('task_count', '?')} tasks, {data.get('size_kb', '?')} KB")

# 2. 列出已上传文件
resp = requests.get(f"{BASE}/api/uploads")
uploads = resp.json()
print(f"\n📁 已上传文件: {uploads['count']} 个")

# 3. 触发处理
print("\n" + "=" * 50)
print("Step 2: 触发处理（解析→分块→向量化→存储）")
print("=" * 50)
print("⏳ 处理中...")
t0 = time.time()
resp = requests.post(f"{BASE}/api/process?mode=replace", timeout=600)
elapsed = time.time() - t0
data = resp.json()
if resp.status_code == 200:
    print(f"  ✅ 处理完成!")
    print(f"     文件数: {data.get('files_processed', '?')}")
    print(f"     文档数: {data.get('documents', '?')}")
    print(f"     Chunks: {data.get('chunks', '?')}")
    print(f"     数据库总计: {data.get('total_in_db', '?')}")
    print(f"     耗时: {elapsed:.1f}s")
else:
    print(f"  ❌ 处理失败: {data}")

# 4. 获取统计
print("\n" + "=" * 50)
print("Step 3: ChromaDB 统计信息")
print("=" * 50)
resp = requests.get(f"{BASE}/api/stats")
stats = resp.json()
print(f"  文档块数: {stats.get('total_documents', 0)}")
print(f"  总字符数: {stats.get('total_chars', 0)}")
print(f"  Tokens估: {stats.get('total_tokens_estimate', 0)}")
print(f"  存储空间: {stats.get('storage_size_mb', 0)} MB")
print(f"  向量维度: {stats.get('embedding_dim', '?')}")
print(f"  集合数量: {len(stats.get('collections', []))}")
for coll in stats.get("collections", []):
    print(f"    📁 {coll['name']}: {coll['count']} 条, ~{coll['estimated_tokens']} tokens")
    for src in coll.get("sources", []):
        print(f"       📄 {src}")

# 5. 测试检索
print("\n" + "=" * 50)
print("Step 4: 语义检索测试")
print("=" * 50)
queries = ["燃气轮机故障诊断", "船舶柴油发动机燃油系统", "风力发电叶片检查"]
for q in queries:
    resp = requests.get(f"{BASE}/api/search", params={"q": q, "top_k": 3})
    data = resp.json()
    print(f"\n🔍 查询: {q}")
    print(f"   延迟: {data.get('latency_ms', '?')}ms")
    for r in data.get("results", []):
        txt = r["text"][:80].replace("\n", " ")
        print(f"   [{r['rank']}] sim={r['similarity']:.3f} | {txt}...")

print("\n✅ 全部 API 测试完成!")
