from __future__ import annotations

from pathlib import Path
from math import atan2, cos, sin, pi
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "PowerRAG_GraphRAG_module_flow_2026-07-06.png"


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        Path("C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/simhei.ttf"),
        Path("C:/Windows/Fonts/simsun.ttc"),
    ]
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


FONT_TITLE = load_font(52, True)
FONT_SUBTITLE = load_font(25)
FONT_LANE = load_font(28, True)
FONT_BOX_TITLE = load_font(25, True)
FONT_BOX = load_font(20)
FONT_LABEL = load_font(18)


def text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> int:
    if not text:
        return 0
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0]


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for char in text:
        trial = current + char
        if text_width(draw, trial, font) <= max_width or not current:
            current = trial
        else:
            lines.append(current)
            current = char
    if current:
        lines.append(current)
    return lines


def rounded(draw: ImageDraw.ImageDraw, rect: tuple[int, int, int, int], fill: str, outline: str, width: int = 3, radius: int = 18) -> None:
    draw.rounded_rectangle(rect, radius=radius, fill=fill, outline=outline, width=width)


def draw_lane(draw: ImageDraw.ImageDraw, rect: tuple[int, int, int, int], title: str, fill: str, outline: str) -> None:
    rounded(draw, rect, fill, outline, width=3, radius=26)
    draw.text((rect[0] + 24, rect[1] + 18), title, font=FONT_LANE, fill="#172033")


def draw_box(
    draw: ImageDraw.ImageDraw,
    rect: tuple[int, int, int, int],
    title: str,
    body: str,
    fill: str,
    outline: str,
    accent: str,
) -> tuple[int, int, int, int]:
    rounded(draw, rect, fill, outline, width=3, radius=18)
    draw.rectangle((rect[0], rect[1], rect[0] + 12, rect[3]), fill=accent)
    tx = rect[0] + 26
    ty = rect[1] + 16
    draw.text((tx, ty), title, font=FONT_BOX_TITLE, fill="#111827")
    for line in wrap_text(draw, body, FONT_BOX, rect[2] - rect[0] - 48)[:3]:
        ty += 30
        draw.text((tx, ty), line, font=FONT_BOX, fill="#374151")
    return rect


def center(rect: tuple[int, int, int, int]) -> tuple[int, int]:
    return ((rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2)


def point(rect: tuple[int, int, int, int], side: str) -> tuple[int, int]:
    cx, cy = center(rect)
    if side == "left":
        return rect[0], cy
    if side == "right":
        return rect[2], cy
    if side == "top":
        return cx, rect[1]
    if side == "bottom":
        return cx, rect[3]
    return cx, cy


def arrow(draw: ImageDraw.ImageDraw, start: tuple[int, int], end: tuple[int, int], color: str = "#6B7280", width: int = 4, label: str | None = None) -> None:
    draw.line([start, end], fill=color, width=width)
    angle = atan2(end[1] - start[1], end[0] - start[0])
    length = 18
    spread = pi / 7
    p1 = (end[0] - length * cos(angle - spread), end[1] - length * sin(angle - spread))
    p2 = (end[0] - length * cos(angle + spread), end[1] - length * sin(angle + spread))
    draw.polygon([end, p1, p2], fill=color)
    if label:
        mx = (start[0] + end[0]) // 2
        my = (start[1] + end[1]) // 2
        pad_x = 10
        pad_y = 5
        w = text_width(draw, label, FONT_LABEL)
        bg = (mx - w // 2 - pad_x, my - 16, mx + w // 2 + pad_x, my + 18)
        draw.rounded_rectangle(bg, radius=10, fill="#FFFFFF", outline="#D1D5DB", width=1)
        draw.text((mx - w // 2, my - 12), label, font=FONT_LABEL, fill="#4B5563")


def path_arrow(
    draw: ImageDraw.ImageDraw,
    points: list[tuple[int, int]],
    color: str = "#6B7280",
    width: int = 4,
    label: str | None = None,
) -> None:
    draw.line(points, fill=color, width=width)
    start = points[-2]
    end = points[-1]
    angle = atan2(end[1] - start[1], end[0] - start[0])
    length = 18
    spread = pi / 7
    p1 = (end[0] - length * cos(angle - spread), end[1] - length * sin(angle - spread))
    p2 = (end[0] - length * cos(angle + spread), end[1] - length * sin(angle + spread))
    draw.polygon([end, p1, p2], fill=color)
    if label:
        if len(points) >= 4:
            mx = (points[1][0] + points[2][0]) // 2
            my = (points[1][1] + points[2][1]) // 2
        else:
            mx = (points[0][0] + points[-1][0]) // 2
            my = (points[0][1] + points[-1][1]) // 2
        pad_x = 10
        w = text_width(draw, label, FONT_LABEL)
        bg = (mx - w // 2 - pad_x, my - 16, mx + w // 2 + pad_x, my + 18)
        draw.rounded_rectangle(bg, radius=10, fill="#FFFFFF", outline="#D1D5DB", width=1)
        draw.text((mx - w // 2, my - 12), label, font=FONT_LABEL, fill="#4B5563")


def main() -> None:
    width, height = 3000, 2100
    image = Image.new("RGB", (width, height), "#F8FAFC")
    draw = ImageDraw.Draw(image)

    draw.text((90, 48), "PowerRAG / GraphRAG 模块流程图", font=FONT_TITLE, fill="#0F172A")
    draw.text((92, 112), "从资料获取、入库清洗、图谱抽取、检索编排到可追溯回答与评测闭环", font=FONT_SUBTITLE, fill="#475569")

    # Lanes
    draw_lane(draw, (70, 170, 2930, 370), "用户入口与前端展示层", "#EFF6FF", "#93C5FD")
    draw_lane(draw, (70, 405, 2930, 585), "后端接口与服务编排层", "#F5F3FF", "#C4B5FD")
    draw_lane(draw, (70, 635, 2930, 1075), "主链路：数据治理 -> 知识存储 -> 检索编排 -> 输出", "#FFF7ED", "#FDBA74")
    draw_lane(draw, (70, 1125, 1870, 1580), "GraphRAG 知识图谱构建链路", "#ECFDF5", "#86EFAC")
    draw_lane(draw, (1910, 1125, 2930, 1580), "模型适配与暑期增强方向", "#FDF2F8", "#F9A8D4")
    draw_lane(draw, (70, 1630, 2930, 1985), "评测、观测与过程结果沉淀", "#F1F5F9", "#CBD5E1")

    blue = ("#DBEAFE", "#60A5FA", "#2563EB")
    purple = ("#EDE9FE", "#A78BFA", "#7C3AED")
    orange = ("#FFEDD5", "#FB923C", "#EA580C")
    green = ("#DCFCE7", "#4ADE80", "#16A34A")
    pink = ("#FCE7F3", "#F472B6", "#DB2777")
    gray = ("#FFFFFF", "#CBD5E1", "#64748B")

    # Frontend
    web = draw_box(draw, (170, 245, 520, 345), "Web 控制台", "数据接入、语义检索、GraphRAG 工作台", *blue)
    upload = draw_box(draw, (620, 245, 970, 345), "资料接入页", "上传文件、查看解析状态、导出结果", *blue)
    search = draw_box(draw, (1070, 245, 1420, 345), "检索问答页", "TopK 证据、来源、相似度和回答", *blue)
    kg_ui = draw_box(draw, (1520, 245, 1870, 345), "GraphRAG 页", "图谱构建、图谱问答、质量观察", *blue)
    eval_ui = draw_box(draw, (1970, 245, 2320, 345), "开源评测台", "RAG / GraphRAG 开源系统对比", *blue)
    doc_out = draw_box(draw, (2420, 245, 2810, 345), "汇报与文档", "WPS 文档、截图、过程报告、PPT", *blue)

    # API
    files_api = draw_box(draw, (130, 465, 460, 555), "/api/files", "文件导入、解析、状态查询", *purple)
    app_api = draw_box(draw, (620, 465, 970, 555), "FastAPI 核心应用", "鉴权、路由、任务状态、运行日志", *purple)
    graph_api = draw_box(draw, (1010, 465, 1340, 555), "/api/graph", "图谱构建、实体关系、图谱问答", *purple)
    query_api = draw_box(draw, (1890, 465, 2220, 555), "/api/query", "普通 RAG 检索与问答", *purple)
    eval_api = draw_box(draw, (2330, 465, 2700, 555), "/api/evaluation", "评测、质量门禁、失败归因", *purple)

    # Main flow
    sources = draw_box(draw, (130, 780, 460, 910), "输入源", "本地 PDF / Word / JSON / TXT；网页资源；图片与图纸", *orange)
    parse = draw_box(draw, (570, 780, 900, 910), "解析与 OCR", "文档解析、扫描件 OCR、多模态预处理", *orange)
    clean = draw_box(draw, (1010, 780, 1340, 910), "清洗与分块", "去噪、表格转文本、chunking、metadata", *orange)
    store = draw_box(draw, (1450, 780, 1780, 910), "知识存储", "ChromaDB 向量库、GraphStore、会话记忆", *orange)
    retrieve = draw_box(draw, (1890, 780, 2220, 910), "检索编排", "Query 理解、BM25 / Dense / Hybrid、Rerank", *orange)
    answer = draw_box(draw, (2330, 780, 2700, 910), "答案与输出", "证据引用、专题文档、图谱可视化、导出", *orange)

    # GraphRAG
    schema = draw_box(draw, (150, 1225, 500, 1355), "专业 Schema", "设备层级、故障模式、参数体系、因果链", *green)
    extract = draw_box(draw, (610, 1225, 960, 1355), "实体关系抽取", "实体、关系、三元组、LLM 辅助校验", *green)
    evidence = draw_box(draw, (1070, 1225, 1420, 1355), "Evidence 绑定", "来源文件、页码、chunk_id、原文片段", *green)
    review = draw_box(draw, (1530, 1225, 1810, 1355), "人工审核", "三元组判断、实体合并、关系纠错", *green)

    community = draw_box(draw, (390, 1410, 740, 1520), "社区划分与摘要", "Leiden / 社区摘要 / 全局上下文", *green)
    graph_qa = draw_box(draw, (880, 1410, 1230, 1520), "图谱问答增强", "Local / Global / Hybrid GraphRAG", *green)
    graph_store = draw_box(draw, (1370, 1410, 1720, 1520), "图谱存储", "NetworkX / JSON / 后续 Neo4j 方向", *green)

    # Model and summer
    embed = draw_box(draw, (1980, 1225, 2300, 1335), "Embedding Adapter", "sentence-transformers / OpenAI-compatible", *pink)
    llm = draw_box(draw, (2390, 1225, 2730, 1335), "LLM Client", "OpenAI-compatible / 本地模型 / Prompt 模板", *pink)
    skill = draw_box(draw, (1980, 1410, 2300, 1520), "流程固化为 Skill", "关键词 -> 抓取 -> 入库 -> 图谱 -> 文档", *pink)
    multimodal = draw_box(draw, (2390, 1410, 2730, 1520), "图片图纸识别", "OCR、多模态识别、图纸结构化", *pink)

    # Evaluation
    qa = draw_box(draw, (160, 1740, 500, 1860), "问题集与同题评测", "普通 RAG vs GraphRAG，对比证据覆盖", *gray)
    gate = draw_box(draw, (610, 1740, 950, 1860), "质量门禁", "引用完整性、无证据回答、失败归因", *gray)
    log = draw_box(draw, (1060, 1740, 1400, 1860), "运行日志", "入库、检索、图谱构建、评测记录", *gray)
    report = draw_box(draw, (1510, 1740, 1850, 1860), "过程结果文档", "WPS 收集、截图、表格、结论沉淀", *gray)
    improve = draw_box(draw, (1960, 1740, 2320, 1860), "反馈改进", "Schema 调整、分块优化、路由策略迭代", *gray)
    topic = draw_box(draw, (2430, 1740, 2790, 1860), "暑期课题出口", "可复用流程、专业图谱、样例数据集", *gray)

    # API -> main flow
    arrow(draw, point(files_api, "bottom"), point(sources, "top"), "#7C3AED", 4, "导入任务")
    arrow(draw, point(query_api, "bottom"), point(retrieve, "top"), "#7C3AED", 4, "查询请求")
    arrow(draw, point(graph_api, "bottom"), point(clean, "top"), "#7C3AED", 4, "图谱任务")
    path_arrow(draw, [point(eval_api, "bottom"), (2860, 625), (2860, 1700), (330, 1700), point(qa, "top")], "#7C3AED", 4, "评测任务")

    # Main chain
    for a, b in [(sources, parse), (parse, clean), (clean, store), (store, retrieve), (retrieve, answer)]:
        arrow(draw, point(a, "right"), point(b, "left"), "#EA580C", 5)

    # Graph chain
    arrow(draw, point(clean, "bottom"), point(extract, "top"), "#16A34A", 4, "文本证据")
    for a, b in [(schema, extract), (extract, evidence), (evidence, review)]:
        arrow(draw, point(a, "right"), point(b, "left"), "#16A34A", 4)
    arrow(draw, point(review, "bottom"), point(graph_store, "top"), "#16A34A", 4)
    arrow(draw, point(graph_store, "left"), point(graph_qa, "right"), "#16A34A", 4)
    arrow(draw, point(graph_qa, "left"), point(community, "right"), "#16A34A", 4)
    path_arrow(draw, [point(graph_qa, "top"), (1055, 1100), (2055, 1100), point(retrieve, "bottom")], "#16A34A", 4, "图谱上下文")

    # Model feeds
    path_arrow(draw, [point(embed, "left"), (1850, 1280), (1850, 1100), (1615, 1100), point(store, "bottom")], "#DB2777", 4, "向量化")
    path_arrow(draw, [point(llm, "top"), (2560, 1100), (2515, 1100), point(answer, "bottom")], "#DB2777", 4, "生成")

    # Evaluation loop
    path_arrow(draw, [point(answer, "right"), (2860, 845), (2860, 1620), (330, 1620), point(qa, "top")], "#64748B", 4, "输出进入评测")
    for a, b in [(qa, gate), (gate, log), (log, report), (report, improve), (improve, topic)]:
        arrow(draw, point(a, "right"), point(b, "left"), "#64748B", 4)

    # Footnote
    draw.text((90, 2025), "说明：图中实线为当前基础链路，粉色模块为暑期可增强方向；所有结论应回到原文 evidence 和评测记录。", font=FONT_SUBTITLE, fill="#475569")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    image.save(OUT, quality=95)
    print(OUT)


if __name__ == "__main__":
    main()
