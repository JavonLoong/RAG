"""
动力装备知识库 RAG Pipeline — 一键控制台

组会演示用：所有功能入口集中在一个菜单里，选数字就能用。
"""
import sys
import io
import os
import time
import json
from pathlib import Path

# 修复 Windows 终端编码
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# 把新模块加入路径
_src_dir = Path(__file__).resolve().parent.parent / "chroma_rag_poc" / "src"
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

BASE_DIR = Path(__file__).resolve().parent.parent
LEGACY_DATA_DIR = BASE_DIR.parents[1] / "03_数据" / "标注数据"
UPLOAD_DIR = BASE_DIR / "data" / "uploads"
DATA_DIR = LEGACY_DATA_DIR if LEGACY_DATA_DIR.exists() else UPLOAD_DIR
PERSIST_DIR = BASE_DIR / "data" / "chroma"


# ============================================================
# 颜色工具
# ============================================================

class C:
    """终端颜色"""
    BOLD = "\033[1m"
    DIM = "\033[2m"
    BLUE = "\033[38;5;75m"
    GREEN = "\033[38;5;114m"
    YELLOW = "\033[38;5;221m"
    RED = "\033[38;5;203m"
    PURPLE = "\033[38;5;141m"
    CYAN = "\033[38;5;80m"
    WHITE = "\033[97m"
    RESET = "\033[0m"
    BG_BLUE = "\033[48;5;24m"
    BG_GREEN = "\033[48;5;22m"


def banner():
    print(f"""
{C.BLUE}{C.BOLD}╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║      ⚡  动力装备知识库 RAG Pipeline v2.0  ⚡               ║
║                                                              ║
║      模块化架构 · 混合检索 · 智能分块 · 向量化存储           ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝{C.RESET}
""")


def menu():
    print(f"""
{C.CYAN}{'─' * 60}{C.RESET}
{C.BOLD}{C.WHITE}  功能菜单{C.RESET}
{C.CYAN}{'─' * 60}{C.RESET}

  {C.YELLOW}[1]{C.RESET} 🌐 启动管理面板        {C.DIM}— 浏览器操作上传/搜索{C.RESET}
  {C.YELLOW}[2]{C.RESET} 📊 查看数据库统计       {C.DIM}— ChromaDB 当前状态{C.RESET}
  {C.YELLOW}[3]{C.RESET} 🔍 交互式检索           {C.DIM}— 输入问题即时搜索{C.RESET}
  {C.YELLOW}[4]{C.RESET} 📂 解析JSON文件         {C.DIM}— 展示解析→清洗→分块过程{C.RESET}
  {C.YELLOW}[5]{C.RESET} ⚡ 一键入库              {C.DIM}— 解析+清洗+分块+向量化+存储{C.RESET}
  {C.YELLOW}[6]{C.RESET} 🏆 性能基准测试          {C.DIM}— 插入/查询性能评测{C.RESET}
  {C.YELLOW}[7]{C.RESET} 📋 数据质量报告          {C.DIM}— 自动检测数据问题{C.RESET}
  {C.YELLOW}[8]{C.RESET} 🏗️  查看项目架构          {C.DIM}— 模块化代码结构{C.RESET}
  {C.YELLOW}[9]{C.RESET} 📖 打开API文档           {C.DIM}— Swagger UI 自动文档{C.RESET}

  {C.RED}[0]{C.RESET} 退出

{C.CYAN}{'─' * 60}{C.RESET}""")


def wait_enter():
    input(f"\n{C.DIM}按回车返回菜单...{C.RESET}")


def section(title):
    print(f"\n{C.BG_BLUE}{C.WHITE}{C.BOLD}  {title}  {C.RESET}\n")


# ============================================================
# 功能实现
# ============================================================


def do_serve():
    """[1] 启动管理面板"""
    section("启动管理面板")
    print(f"  {C.GREEN}→{C.RESET} 前端面板: {C.BOLD}http://localhost:8000{C.RESET}")
    print(f"  {C.GREEN}→{C.RESET} API 文档: {C.BOLD}http://localhost:8000/docs{C.RESET}")
    print(f"  {C.DIM}  按 Ctrl+C 停止服务器{C.RESET}\n")

    # 浏览器自动打开
    import webbrowser
    webbrowser.open("http://localhost:8000")

    import uvicorn
    from chroma_rag_poc.api import create_app
    app = create_app(persist_dir=PERSIST_DIR, upload_dir=UPLOAD_DIR)
    uvicorn.run(app, host="0.0.0.0", port=8000)


def do_stats():
    """[2] 查看数据库统计"""
    section("ChromaDB 数据库统计")
    from chroma_rag_poc.pipeline import get_all_stats
    stats = get_all_stats(persist_dir=PERSIST_DIR)

    print(f"  {C.BLUE}📦 总文档块数{C.RESET}    {C.BOLD}{stats['total_documents']}{C.RESET}")
    print(f"  {C.GREEN}🔤 总 Tokens{C.RESET}     {C.BOLD}{stats['total_tokens_estimate']:,}{C.RESET}")
    print(f"  {C.YELLOW}💾 存储空间{C.RESET}      {C.BOLD}{stats['storage_size_mb']} MB{C.RESET}")
    print(f"  {C.PURPLE}📐 向量维度{C.RESET}      {C.BOLD}{stats.get('embedding_dim', 'N/A')}{C.RESET}")
    print(f"  {C.RED}📚 集合数{C.RESET}        {C.BOLD}{len(stats.get('collections', []))}{C.RESET}")

    for coll in stats.get("collections", []):
        print(f"\n  {C.CYAN}┌─ 集合: {C.BOLD}{coll['name']}{C.RESET}")
        print(f"  {C.CYAN}│{C.RESET}  记录数: {coll['count']}")
        print(f"  {C.CYAN}│{C.RESET}  估算字符: {coll['estimated_chars']:,}")
        print(f"  {C.CYAN}│{C.RESET}  估算 tokens: {coll['estimated_tokens']:,}")
        if coll.get("sources"):
            print(f"  {C.CYAN}│{C.RESET}  来源文件:")
            for src in coll["sources"]:
                print(f"  {C.CYAN}│{C.RESET}    📄 {src}")
        print(f"  {C.CYAN}└{'─' * 40}{C.RESET}")

    wait_enter()


def do_search():
    """[3] 交互式检索"""
    section("交互式语义检索")
    print(f"  {C.DIM}输入查询内容，输入 q 退出{C.RESET}\n")
    print(f"  {C.DIM}示例查询:{C.RESET}")
    print(f"    • 燃气轮机故障诊断")
    print(f"    • 压气机喘振原因和处理方法")
    print(f"    • 叶片裂纹检测方法")
    print(f"    • 锅炉安全操作规程")
    print()

    from chroma_rag_poc.pipeline import query_collection, get_all_stats

    # 自动找有数据的集合
    all_stats = get_all_stats(persist_dir=PERSIST_DIR)
    collection_name = None
    for coll in all_stats.get("collections", []):
        if coll["count"] > 0:
            collection_name = coll["name"]
            break

    if not collection_name:
        print(f"  {C.RED}❌ 数据库为空，请先使用 [5] 入库数据{C.RESET}")
        wait_enter()
        return

    print(f"  {C.GREEN}✓ 使用集合: {collection_name} ({all_stats['total_documents']} 条记录){C.RESET}\n")

    while True:
        query = input(f"  {C.YELLOW}🔍 查询 > {C.RESET}").strip()
        if query.lower() in ("q", "quit", "exit", ""):
            break

        t0 = time.time()
        result = query_collection(
            query_text=query,
            persist_dir=PERSIST_DIR,
            collection_name=collection_name,
            top_k=5,
        )
        elapsed = (time.time() - t0) * 1000

        results = result.get("results", [])
        if not results:
            print(f"\n  {C.RED}未找到相关结果{C.RESET}\n")
            continue

        print(f"\n  {C.GREEN}找到 {len(results)} 条结果{C.RESET} {C.DIM}({elapsed:.0f}ms){C.RESET}\n")

        for i, r in enumerate(results):
            similarity = r.get("similarity", 0) * 100
            color = C.GREEN if similarity > 60 else C.YELLOW if similarity > 40 else C.RED

            print(f"  {C.BOLD}[{i+1}]{C.RESET} {color}相似度 {similarity:.1f}%{C.RESET}")

            meta = r.get("metadata", {})
            filename = meta.get("filename", "—")
            page = meta.get("page_nums", "—")
            print(f"      {C.DIM}📄 {filename} · 第{page}页{C.RESET}")

            text = r.get("text", "")
            preview = text[:250].replace("\n", " ")
            print(f"      {preview}{'...' if len(text) > 250 else ''}")
            print()

    print(f"\n  {C.DIM}退出检索{C.RESET}")
    wait_enter()


def do_parse():
    """[4] 解析JSON文件"""
    section("JSON 解析演示")

    from chroma_rag_poc.parsing import load_json_directory, load_json_file
    from chroma_rag_poc.cleaning import clean_records
    from chroma_rag_poc.chunking import chunk_records

    # 找数据目录
    if DATA_DIR.exists():
        json_dir = DATA_DIR
    elif UPLOAD_DIR.exists() and list(UPLOAD_DIR.glob("*.json")):
        json_dir = UPLOAD_DIR
    else:
        print(f"  {C.RED}❌ 未找到数据目录{C.RESET}")
        print(f"  {C.DIM}尝试查找: {DATA_DIR}{C.RESET}")
        wait_enter()
        return

    print(f"  {C.GREEN}📂 数据目录: {json_dir}{C.RESET}\n")

    # Step 1: 解析
    print(f"  {C.BLUE}━━━ Step 1: 解析 JSON ━━━{C.RESET}")
    t0 = time.time()
    records = load_json_directory(str(json_dir))
    t1 = time.time()
    total_blocks = sum(len(r.blocks) for r in records)
    print(f"\n  {C.GREEN}✓{C.RESET} 解析完成: {len(records)} 条记录, {total_blocks} 个文本块 ({t1-t0:.1f}s)")

    # Step 1.5: 清洗
    print(f"\n  {C.BLUE}━━━ Step 1.5: 数据清洗（短文本合并）━━━{C.RESET}")
    t0 = time.time()
    before_blocks = total_blocks
    records = clean_records(records)
    after_blocks = sum(len(r.blocks) for r in records)
    t1 = time.time()
    merged = before_blocks - after_blocks
    print(f"  {C.GREEN}✓{C.RESET} 清洗完成: {before_blocks} → {after_blocks} 块 (合并了 {merged} 个碎片) ({t1-t0:.1f}s)")

    # Step 2: 分块
    print(f"\n  {C.BLUE}━━━ Step 2: 智能分块（Title触发 + 多级断点）━━━{C.RESET}")
    t0 = time.time()
    chunks = chunk_records(records, chunk_size=500, overlap=50)
    t1 = time.time()

    chunk_lengths = [len(c.text) for c in chunks]
    avg_len = sum(chunk_lengths) / len(chunk_lengths) if chunk_lengths else 0
    print(f"  {C.GREEN}✓{C.RESET} 分块完成: {len(chunks)} 个 chunk ({t1-t0:.1f}s)")
    print(f"    平均长度: {avg_len:.0f} 字符")
    print(f"    最短: {min(chunk_lengths) if chunk_lengths else 0} 字符")
    print(f"    最长: {max(chunk_lengths) if chunk_lengths else 0} 字符")

    # 展示前3个chunk
    print(f"\n  {C.PURPLE}示例 Chunk 预览:{C.RESET}")
    for i, chunk in enumerate(chunks[:3]):
        preview = chunk.text[:120].replace("\n", " ")
        print(f"    [{i+1}] {C.DIM}{preview}...{C.RESET}")

    wait_enter()


def do_ingest():
    """[5] 一键入库"""
    section("一键入库（解析→清洗→分块→向量化→存储）")

    if not DATA_DIR.exists() and not list(UPLOAD_DIR.glob("*.json")):
        print(f"  {C.RED}❌ 未找到 JSON 数据文件{C.RESET}")
        wait_enter()
        return

    json_dir = DATA_DIR if DATA_DIR.exists() else UPLOAD_DIR
    json_files = sorted(json_dir.glob("*.json"))
    print(f"  {C.GREEN}📂 数据目录: {json_dir}{C.RESET}")
    print(f"  {C.GREEN}📄 文件数: {len(json_files)}{C.RESET}\n")

    confirm = input(f"  {C.YELLOW}确认开始入库？(y/n) > {C.RESET}").strip().lower()
    if confirm != "y":
        print(f"  {C.DIM}已取消{C.RESET}")
        wait_enter()
        return

    from chroma_rag_poc.pipeline import ingest_json_payloads

    payloads = [(f.name, f.read_bytes()) for f in json_files]

    print(f"\n  {C.BLUE}正在处理...{C.RESET}")
    t0 = time.time()

    result = ingest_json_payloads(
        payloads=payloads,
        persist_dir=PERSIST_DIR,
        collection_name="power_equipment",
    )

    elapsed = time.time() - t0
    print(f"\n  {C.GREEN}{C.BOLD}✅ 入库成功!{C.RESET}")
    print(f"  ├─ 处理文件: {result['files_processed']}")
    print(f"  ├─ 解析记录: {result['records_processed']}")
    print(f"  ├─ 写入 chunk: {result['chunks_written']}")
    print(f"  ├─ 耗时: {elapsed:.1f}s")
    if result.get("cleaning"):
        c = result["cleaning"]
        print(f"  └─ 清洗: 合并了 {c['fragments_merged']} 个碎片")

    wait_enter()


def do_benchmark():
    """[6] 性能基准测试"""
    section("性能基准测试")
    print(f"  {C.DIM}使用合成数据测试 ChromaDB 写入/查询性能...{C.RESET}\n")

    from chroma_rag_poc.benchmark import run_synthetic_benchmark

    t0 = time.time()
    result = run_synthetic_benchmark(
        persist_dir=PERSIST_DIR,
        document_count=500,
        batch_size=100,
        query_count=50,
        backend="hashing",
        cleanup=True,
    )
    elapsed = time.time() - t0

    print(f"  {C.BLUE}━━━ 插入性能 ━━━{C.RESET}")
    print(f"  文档数: {result['document_count']}")
    print(f"  耗时: {result['insert_seconds']:.2f}s")
    print(f"  吞吐: {C.GREEN}{C.BOLD}{result['insert_docs_per_second']:.0f} docs/s{C.RESET}")

    print(f"\n  {C.BLUE}━━━ 查询性能 ━━━{C.RESET}")
    print(f"  查询数: {result['query_count']}")
    print(f"  QPS: {C.GREEN}{C.BOLD}{result['query_qps']:.1f}{C.RESET}")
    print(f"  平均延迟: {C.YELLOW}{result['avg_query_latency_ms']:.1f}ms{C.RESET}")
    print(f"  P95延迟: {C.YELLOW}{result['p95_query_latency_ms']:.1f}ms{C.RESET}")
    print(f"\n  总耗时: {elapsed:.1f}s")

    # 保存报告
    report_path = BASE_DIR / "data" / "benchmark_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"  {C.DIM}报告已保存: {report_path}{C.RESET}")

    wait_enter()


def do_quality():
    """[7] 数据质量报告"""
    section("数据质量报告")

    from chroma_rag_poc.parsing import load_json_directory
    from chroma_rag_poc.cleaning import clean_records
    from chroma_rag_poc.chunking import chunk_records
    from chroma_rag_poc.pipeline import quality_report

    json_dir = DATA_DIR if DATA_DIR.exists() else UPLOAD_DIR
    if not json_dir.exists() or not list(json_dir.glob("*.json")):
        print(f"  {C.RED}❌ 未找到数据文件{C.RESET}")
        wait_enter()
        return

    records = load_json_directory(str(json_dir))
    records = clean_records(records)
    chunks = chunk_records(records)
    report = quality_report(records, chunks)

    print(f"\n  {C.BLUE}━━━ 文档概览 ━━━{C.RESET}")
    for doc in report["documents"]:
        print(f"\n  {C.CYAN}doc_id={doc['doc_id']}{C.RESET}")
        for fn in doc["filenames"]:
            print(f"    📄 {fn}")
        print(f"    文本块: {doc['block_count']}")
        print(f"    标签分布: {doc['label_distribution']}")
        if doc["short_blocks"] > 0:
            print(f"    {C.YELLOW}⚠️ 极短块: {doc['short_blocks']}{C.RESET}")

    if report.get("chunks"):
        cs = report["chunks"]
        print(f"\n  {C.BLUE}━━━ Chunk 统计 ━━━{C.RESET}")
        print(f"    总数: {cs['total_chunks']}")
        print(f"    平均长度: {cs['avg_length']} 字符")
        print(f"    范围: {cs['min_length']} ~ {cs['max_length']} 字符")

    print(f"\n  {C.BLUE}━━━ 问题检测 ━━━{C.RESET}")
    if report["issues"]:
        for issue in report["issues"]:
            print(f"    {C.YELLOW}⚠️ {issue}{C.RESET}")
    else:
        print(f"    {C.GREEN}✅ 未发现明显问题{C.RESET}")

    wait_enter()


def do_architecture():
    """[8] 查看项目架构"""
    section("项目模块化架构")
    print(f"""
  {C.BLUE}┌────────────────────────────────────────────────────────┐{C.RESET}
  {C.BLUE}│{C.RESET}                  {C.BOLD}数据流全景{C.RESET}                          {C.BLUE}│{C.RESET}
  {C.BLUE}├────────────────────────────────────────────────────────┤{C.RESET}
  {C.BLUE}│{C.RESET}                                                        {C.BLUE}│{C.RESET}
  {C.BLUE}│{C.RESET}  {C.YELLOW}PDF 技术手册{C.RESET}                                       {C.BLUE}│{C.RESET}
  {C.BLUE}│{C.RESET}       ↓  Label Studio 标注                             {C.BLUE}│{C.RESET}
  {C.BLUE}│{C.RESET}  {C.YELLOW}JSON 标注文件{C.RESET}                                       {C.BLUE}│{C.RESET}
  {C.BLUE}│{C.RESET}       ↓  {C.GREEN}parsing.py{C.RESET}  解析 + 格式检测 + 去重           {C.BLUE}│{C.RESET}
  {C.BLUE}│{C.RESET}  {C.YELLOW}结构化文本 (Title/Para/List){C.RESET}                        {C.BLUE}│{C.RESET}
  {C.BLUE}│{C.RESET}       ↓  {C.GREEN}cleaning.py{C.RESET}  OCR碎片短文本合并               {C.BLUE}│{C.RESET}
  {C.BLUE}│{C.RESET}  {C.YELLOW}干净文本块{C.RESET}                                          {C.BLUE}│{C.RESET}
  {C.BLUE}│{C.RESET}       ↓  {C.GREEN}chunking.py{C.RESET}  Title触发 + 多级断点            {C.BLUE}│{C.RESET}
  {C.BLUE}│{C.RESET}  {C.YELLOW}Chunks (500字/块){C.RESET}                                   {C.BLUE}│{C.RESET}
  {C.BLUE}│{C.RESET}       ↓  {C.GREEN}embeddings.py{C.RESET}  BGE-m3 → 1024维向量           {C.BLUE}│{C.RESET}
  {C.BLUE}│{C.RESET}  {C.YELLOW}向量数据库 (ChromaDB){C.RESET}                               {C.BLUE}│{C.RESET}
  {C.BLUE}│{C.RESET}       ↓  {C.GREEN}retrieval.py{C.RESET}  语义 + BM25 + RRF 融合         {C.BLUE}│{C.RESET}
  {C.BLUE}│{C.RESET}  {C.YELLOW}检索结果{C.RESET}                                             {C.BLUE}│{C.RESET}
  {C.BLUE}│{C.RESET}       ↓  {C.GREEN}rag.py{C.RESET}  （未来接大模型 API）                  {C.BLUE}│{C.RESET}
  {C.BLUE}│{C.RESET}  {C.YELLOW}自然语言回答{C.RESET}                                        {C.BLUE}│{C.RESET}
  {C.BLUE}│{C.RESET}                                                        {C.BLUE}│{C.RESET}
  {C.BLUE}└────────────────────────────────────────────────────────┘{C.RESET}

  {C.PURPLE}{C.BOLD}模块列表 (12个):{C.RESET}

  {C.GREEN}schemas.py{C.RESET}      数据结构定义 (TextBlock / ChunkRecord)
  {C.GREEN}text_utils.py{C.RESET}   文本规范化 / SHA256哈希 / Token估算
  {C.GREEN}parsing.py{C.RESET}      JSON解析 + 自动格式检测 + 内容去重
  {C.GREEN}cleaning.py{C.RESET}     OCR碎片短文本合并
  {C.GREEN}chunking.py{C.RESET}     Title触发分块 + 多级语义断点
  {C.GREEN}embeddings.py{C.RESET}   BGE-m3向量化 (hashing降级)
  {C.GREEN}retrieval.py{C.RESET}    BM25 + 语义混合检索 + RRF融合排序
  {C.GREEN}rag.py{C.RESET}          端到端RAG问答 (预留LLM接口)
  {C.GREEN}pipeline.py{C.RESET}     流程编排 + ChromaDB管理
  {C.GREEN}api.py{C.RESET}          FastAPI后端 + Pydantic校验
  {C.GREEN}benchmark.py{C.RESET}    合成数据性能基准测试
  {C.GREEN}__main__.py{C.RESET}     CLI入口 (6个子命令)
""")
    wait_enter()


def do_api_docs():
    """[9] 打开API文档"""
    section("API 文档")
    print(f"  {C.DIM}需要先启动服务 [1]，然后打开浏览器:{C.RESET}")
    print(f"  {C.BOLD}http://localhost:8000/docs{C.RESET}\n")
    print(f"  {C.BLUE}API 端点列表:{C.RESET}")
    print(f"  ┌─────────────┬──────────────────────┬──────────────────────┐")
    print(f"  │ {C.BOLD}方法{C.RESET}        │ {C.BOLD}路径{C.RESET}                 │ {C.BOLD}说明{C.RESET}                 │")
    print(f"  ├─────────────┼──────────────────────┼──────────────────────┤")
    print(f"  │ {C.GREEN}GET{C.RESET}         │ /                    │ 前端管理面板           │")
    print(f"  │ {C.GREEN}GET{C.RESET}         │ /api/health          │ 健康检查               │")
    print(f"  │ {C.YELLOW}POST{C.RESET}        │ /api/upload          │ 上传JSON文件           │")
    print(f"  │ {C.GREEN}GET{C.RESET}         │ /api/uploads         │ 列出已上传文件         │")
    print(f"  │ {C.RED}DELETE{C.RESET}      │ /api/uploads/{{name}}  │ 删除文件               │")
    print(f"  │ {C.YELLOW}POST{C.RESET}        │ /api/process         │ 批量处理入库           │")
    print(f"  │ {C.YELLOW}POST{C.RESET}        │ /api/ingest          │ 一步式入库             │")
    print(f"  │ {C.GREEN}GET{C.RESET}         │ /api/stats           │ 数据库统计             │")
    print(f"  │ {C.GREEN}GET{C.RESET}/{C.YELLOW}POST{C.RESET}    │ /api/search          │ 语义检索               │")
    print(f"  │ {C.YELLOW}POST{C.RESET}        │ /api/benchmark       │ 性能基准测试           │")
    print(f"  └─────────────┴──────────────────────┴──────────────────────┘")

    open_it = input(f"\n  {C.YELLOW}是否启动服务并打开？(y/n) > {C.RESET}").strip().lower()
    if open_it == "y":
        do_serve()
    else:
        wait_enter()


# ============================================================
# 主循环
# ============================================================


def main():
    os.system("")  # 启用 Windows 终端 ANSI 支持

    while True:
        os.system("cls" if os.name == "nt" else "clear")
        banner()
        menu()

        choice = input(f"  {C.YELLOW}请选择 > {C.RESET}").strip()

        try:
            if choice == "1":
                do_serve()
            elif choice == "2":
                do_stats()
            elif choice == "3":
                do_search()
            elif choice == "4":
                do_parse()
            elif choice == "5":
                do_ingest()
            elif choice == "6":
                do_benchmark()
            elif choice == "7":
                do_quality()
            elif choice == "8":
                do_architecture()
            elif choice == "9":
                do_api_docs()
            elif choice == "0":
                print(f"\n  {C.GREEN}再见！{C.RESET}\n")
                break
            else:
                print(f"\n  {C.RED}无效选项，请输入 0-9{C.RESET}")
                time.sleep(1)
        except KeyboardInterrupt:
            print(f"\n\n  {C.DIM}已中断，返回菜单...{C.RESET}")
            time.sleep(1)
        except Exception as e:
            print(f"\n  {C.RED}❌ 出错: {e}{C.RESET}")
            wait_enter()


if __name__ == "__main__":
    main()
