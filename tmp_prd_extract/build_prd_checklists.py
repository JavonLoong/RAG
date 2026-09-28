# -*- coding: utf-8 -*-
"""Build annotated PRD checklists for meeting markup (checkmarks + wiring net)."""

from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn, nsmap
from docx.shared import Cm, Pt, RGBColor

DONE = "☑"
PART = "◐"
OPEN = "☐"

NAVY = RGBColor(0x1F, 0x3A, 0x5F)
GREEN = RGBColor(0x1B, 0x6B, 0x3A)
AMBER = RGBColor(0x9A, 0x5B, 0x00)
RED = RGBColor(0x8B, 0x1E, 0x1E)
GRAY = RGBColor(0x55, 0x55, 0x55)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)

OUT_MAIN = Path(r"D:\虚拟C盘\PowerRAG PRD_勾选核对.docx")
OUT_V10 = Path(r"D:\虚拟C盘\PowerRAG_工作台PRD_v1.0_勾选核对.docx")


def set_run_font(run, size=11, bold=False, color=None, name="微软雅黑"):
    run.font.name = name
    run.font.size = Pt(size)
    run.bold = bold
    if color is not None:
        run.font.color.rgb = color
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.get_or_add_rFonts()
    rfonts.set(qn("w:eastAsia"), name)
    rfonts.set(qn("w:ascii"), name)
    rfonts.set(qn("w:hAnsi"), name)


def shade_cell(cell, hex_color):
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:fill"), hex_color)
    shd.set(qn("w:val"), "clear")
    tcPr.append(shd)


def set_cell_border(cell, **kwargs):
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    tcBorders = OxmlElement("w:tcBorders")
    for edge in ("top", "left", "bottom", "right"):
        if edge in kwargs:
            element = OxmlElement(f"w:{edge}")
            element.set(qn("w:val"), kwargs[edge].get("val", "single"))
            element.set(qn("w:sz"), str(kwargs[edge].get("sz", 8)))
            element.set(qn("w:color"), kwargs[edge].get("color", "1F3A5F"))
            tcBorders.append(element)
    tcPr.append(tcBorders)


def clear_cell(cell):
    cell.text = ""
    return cell.paragraphs[0]


def write_cell(cell, text, size=10, bold=False, color=NAVY, align="left", fill=None):
    if fill:
        shade_cell(cell, fill)
    p = cell.paragraphs[0]
    p.alignment = {
        "left": WD_ALIGN_PARAGRAPH.LEFT,
        "center": WD_ALIGN_PARAGRAPH.CENTER,
        "right": WD_ALIGN_PARAGRAPH.RIGHT,
    }[align]
    p.clear()
    run = p.add_run(text)
    set_run_font(run, size=size, bold=bold, color=color)
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(2)
    return p


def mark_color(mark):
    if mark == DONE:
        return GREEN
    if mark == PART:
        return AMBER
    return RED


def add_heading(doc, text, level=1):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(12 if level == 1 else 8)
    p.paragraph_format.space_after = Pt(6)
    run = p.add_run(text)
    set_run_font(run, size=16 if level == 1 else 13, bold=True, color=NAVY)
    return p


def add_body(doc, text, size=11, color=GRAY, bold=False):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(6)
    run = p.add_run(text)
    set_run_font(run, size=size, bold=bold, color=color)
    return p


def add_legend(doc):
    add_body(
        doc,
        f"{DONE} 已实现（代码已接到产品链路）    {PART} 部分（有能力，缺配置/签字/金标准）    {OPEN} 未完成或未通过验收",
        size=11,
        color=NAVY,
        bold=True,
    )
    add_body(
        doc,
        "口径：对勾只表示实现，不表示现场已验收。验收章（AC-）多数仍是空框。可在「搭线网」页用笔把需求连到模块。",
        size=10,
        color=GRAY,
    )


def set_narrow_margins(doc, left=1.6, right=1.6, top=1.5, bottom=1.5):
    for section in doc.sections:
        section.left_margin = Cm(left)
        section.right_margin = Cm(right)
        section.top_margin = Cm(top)
        section.bottom_margin = Cm(bottom)


def add_table(doc, headers, rows, col_widths=None, header_fill="1F3A5F"):
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, h in enumerate(headers):
        write_cell(table.rows[0].cells[i], h, size=10, bold=True, color=WHITE, align="center", fill=header_fill)
    for r_i, row in enumerate(rows, start=1):
        fill = "F4F7FB" if r_i % 2 == 0 else "FFFFFF"
        for c_i, value in enumerate(row):
            text = value if isinstance(value, str) else value[0]
            color = value[1] if isinstance(value, tuple) else NAVY
            bold = c_i == 0 or (isinstance(value, str) and value[:1] in {DONE, PART, OPEN})
            if isinstance(value, str) and value[:1] in {DONE, PART, OPEN}:
                color = mark_color(value[:1])
                bold = True
            align = "center" if c_i in (0, 1) and len(headers) > 2 else "left"
            if c_i == 1 and headers[1] in ("勾", "状态"):
                align = "center"
            write_cell(table.rows[r_i].cells[c_i], text, size=9, bold=bold, color=color, fill=fill, align=align)
    if col_widths:
        for row in table.rows:
            for i, w in enumerate(col_widths):
                row.cells[i].width = Cm(w)
    return table


def count_marks(items):
    d = p = o = 0
    for item in items:
        mark = item[1] if not isinstance(item[1], tuple) else item[1][0]
        if mark == DONE:
            d += 1
        elif mark == PART:
            p += 1
        else:
            o += 1
    return d, p, o


# --- Main PRD (PowerRAG PRD.docx) items ---

MAIN_FLOW = [
    ("建立项目与数据基线", DONE, "project_id、独立目录、清单已有；试点资料包与 SHA-256 基线仍要人确认"),
    ("资料接入、解析和质检", DONE, "上传/解析/OCR/阻断页已接通；现场扫描件与外部 parser 看部署"),
    ("正式资料发布与检索", DONE, "审核发布、索引同步、默认只用已发布版已接通；正式嵌入未锁定"),
    ("普通 RAG 与证据回答", PART, "检索+引用+无答案门禁已有；完整 LLM 答案要配模型"),
    ("图谱构建与 GraphRAG", PART, "受控抽取/审核/发布/回退已接通；自动抽质量与 100 条金标准未过"),
    ("FMEA 生成与交付", DONE, "从已发布图生成、字段证据、JSON/CSV/DOCX 已接通；RPN 无政策不编"),
    ("问题反馈与重验证", DONE, "按根因回流并重建下游已有代码；缺一次真实试点闭环签字"),
]

MAIN_P0 = [
    ("PR-P0-01", DONE, "项目隔离", "对象带 project_id，跨项目默认不可互查"),
    ("PR-P0-02", DONE, "任务中心", "资料/OCR/索引/图谱/FMEA/评测/反馈任务列表"),
    ("PR-P0-03", DONE, "状态统一", "queued/running/needs_review/completed/failed/cancelled"),
    ("PR-P0-04", DONE, "文件接入", "multipart 主路径；Base64 仅兼容；Electron 路径未单独验收"),
    ("PR-P0-05", DONE, "源资产", "MIME/大小/SHA-256/页数/时间/项目；重复不覆盖"),
    ("PR-P0-06", DONE, "解析路由", "native/OCR/外部 parser；未安装显示依赖状态"),
    ("PR-P0-07", DONE, "结构证据", "heading/table/image/caption/bbox/reading_order"),
    ("PR-P0-08", DONE, "页级恢复", "单页失败不丢其他页；失败页可重试"),
    ("PR-P0-09", DONE, "原页对照", "原图+解析块；改完出新版本。DOCX 预览看 Office"),
    ("PR-P0-10", DONE, "资料台账", "按项目/状态/文件名/document_id/版本分页"),
    ("PR-P0-11", DONE, "发布门禁", "证据+阻断已解+approve；actor/幂等/expected_version"),
    ("PR-P0-12", PART, "索引快照", "快照字段齐；hashing 仅测试，正式嵌入未锁定"),
    ("PR-P0-13", DONE, "检索模式", "关键词 / 语义 / 混合（RRF）"),
    ("PR-P0-14", DONE, "引用打开", "可打开源页/块/表/图；失败 409"),
    ("PR-P0-15", DONE, "Schema 版本", "项目级不可变 Schema；待领域负责人批正式燃机版"),
    ("PR-P0-16", DONE, "抽取后端", "rules 基线；LLM 必须注册 Provider，未配置不伪造成功"),
    ("PR-P0-17", DONE, "图谱审核", "按关系/类型/型号/证据筛选，逐语句审核"),
    ("PR-P0-18", DONE, "图谱发布", "类型/端点/证据/冲突门禁；同步 GraphStore"),
    ("PR-P0-19", DONE, "GraphRAG 回答", "路径、证据、版本、回退；LLM 答案未配时用证据摘要"),
    ("PR-P0-20", DONE, "模板管理", "gas_turbine_minimum_v1；改模板必须出新版本"),
    ("PR-P0-21", DONE, "字段级证据", "七类专业字段各自 evidence_id"),
    ("PR-P0-22", DONE, "人工修订", "改字段必须带证据；无证据不能发布"),
    ("PR-P0-23", DONE, "发布与导出", "JSON/CSV/DOCX 一致性；DOCX 视觉 QA 未做"),
    ("PR-P0-24", DONE, "统一身份", "actor 来自后端上下文，不信前端字符串"),
    ("PR-P0-25", DONE, "职责分离", "审核人/发布人分记；同人兼任写入审计"),
    ("PR-P0-26", DONE, "审计记录", "对象/版本/动作/操作者/原因/结果"),
    ("PR-P0-27", DONE, "统一错误", "code/message/stage/retryable/correlation_id"),
    ("PR-P0-28", DONE, "反馈回流", "按根因路由并重建下游；缺试点签字"),
    ("PR-P0-29", DONE, "验收工作台", "12 个门禁+证据包；金标准签字未齐"),
]

MAIN_P1 = [
    ("PR-P1-01", DONE, "批量增强", "批量审核/重试/模板复制/指派评论；不绕门禁"),
    ("PR-P1-02", PART, "多领域模板", "燃机+电动机都有；电动机无独立金标准"),
    ("PR-P1-03", DONE, "前端拆分", "页面模块+API client+状态；交付走浏览器不是 Electron"),
]

MAIN_TECH = [
    ("TECH-01", DONE, "核心对象齐全"),
    ("TECH-02", DONE, "下游对象带项目/版本/哈希"),
    ("TECH-03", DONE, "每项目独立目录"),
    ("TECH-04", DONE, "发布同步投影，失败可审计"),
    ("TECH-05", DONE, "长任务进后台，租约/心跳/取消"),
    ("TECH-06", DONE, "/api/delivery 列表与血缘"),
    ("TECH-07", DONE, "大文件 multipart，写接口幂等"),
    ("TECH-08", DONE, "Provider 注册与 health"),
    ("TECH-09", DONE, "外发前数据策略"),
    ("TECH-10", DONE, "本地身份 + OIDC 槽位；IdP 未联调"),
    ("TECH-11", DONE, "预览/导出限制在项目根"),
    ("TECH-12", DONE, "correlation 与去敏日志"),
    ("TECH-13", DONE, "运行健康检查"),
    ("TECH-14", DONE, "备份恢复包；缺试点演练签字"),
    ("TECH-15", PART, "有测量接口，无 14 本 P95 报告"),
    ("TECH-16", DONE, "60MB 异步上传测试过；界面“不卡死”待观察"),
    ("TECH-17", DONE, "Schema/模板不可变版本"),
    ("TECH-18", DONE, "验收包路径与 SHA-256 清单"),
]

MAIN_AC = [
    ("AC-M2-01", OPEN, "页覆盖 100% + 五类逐页签字", "13 本有 OCR 报告，缺五类人工签字"),
    ("AC-M2-02", OPEN, "金标准 CER / 关键字段", "无分层抽样正式签字包"),
    ("AC-M3-01", OPEN, "10 问 Recall@5≥80%", "旧 10 问不是专家相关块标注"),
    ("AC-M3-02", PART, "无答案/冲突/回滚题", "代码有，缺专家题集签字"),
    ("AC-M4-01", OPEN, "≥100 条金标准关系", "现有 POC 仅 27 条"),
    ("AC-M4-02", PART, "证据绑定 100% + 同题比较", "门禁代码有，缺 100 条真实集"),
    ("AC-M5-01", OPEN, "专家接受/改/拒统计", "字段门禁有，无专家统计"),
    ("AC-M5-02", PART, "导出一致且无政策不编 RPN", "代码已过；真实任务未签字"),
    ("AC-E2E-01", PART, "两人只走界面闭环", "界面有，缺双人走查签字"),
    ("AC-E2E-02", PART, "重建/回滚/恢复进验收包", "能力有，缺试点恢复演练"),
]

# Module wiring nodes for the net page
WIRE_NODES = [
    ("M1", "资料获取", PART, "上传/登记/去重", "抓取、版权、密级补齐"),
    ("M2", "解析与标注", PART, "解析/OCR/审核/重试", "现场扫描件、五类签字"),
    ("M3", "正式资料库", PART, "版本/发布/检索", "正式嵌入、专家题集"),
    ("M4", "治理图谱", PART, "抽取/审核/发布/回退", "100 条金标准"),
    ("M5", "FMEA 交付", PART, "生成/证据/导出", "专家接受率统计"),
]


def build_main():
    doc = Document()
    set_narrow_margins(doc)
    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title.add_run("PowerRAG PRD 勾选核对稿")
    set_run_font(run, size=22, bold=True, color=NAVY)
    sub = doc.add_paragraph()
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = sub.add_run("源文件：PowerRAG PRD.docx    对照日期：2026-09-23    分支：release/customer-20260922")
    set_run_font(run, size=10, color=GRAY)
    add_legend(doc)

    add_heading(doc, "〇、模块搭线网（可打印后用笔连线）", 1)
    add_body(
        doc,
        "下面是交付主链。方框已标当前状态。开会时用笔把左侧需求 ID 连到右侧模块，或在空格里补线。箭头表示强制顺序：未发布资料不能构图，未发布图谱不能出 FMEA。",
        size=10,
    )

    net = doc.add_table(rows=3, cols=9)
    net.alignment = WD_TABLE_ALIGNMENT.CENTER
    # row0 labels, row1 boxes, row2 leftover
    cells_spec = [
        (0, "M1\n资料获取\n◐ 部分"),
        (2, "M2\n解析标注\n◐ 部分"),
        (4, "M3\n资料库\n◐ 部分"),
        (6, "M4\n图谱\n◐ 部分"),
        (8, "M5\nFMEA\n◐ 部分"),
    ]
    arrows = [(1, "——→"), (3, "——→"), (5, "——→"), (7, "——→")]
    for col, text in cells_spec:
        cell = net.rows[0].cells[col]
        write_cell(cell, text, size=11, bold=True, color=NAVY, align="center", fill="D9E4F3")
        set_cell_border(cell, top={"sz": 16, "color": "1F3A5F"}, left={"sz": 16, "color": "1F3A5F"},
                        bottom={"sz": 16, "color": "1F3A5F"}, right={"sz": 16, "color": "1F3A5F"})
    for col, text in arrows:
        write_cell(net.rows[0].cells[col], text, size=14, bold=True, color=NAVY, align="center", fill="FFFFFF")
    write_cell(net.rows[1].cells[0], "上传登记\nSHA-256\n☐ 抓取版权", size=8, color=GRAY, align="center", fill="FFF4E0")
    write_cell(net.rows[1].cells[2], "☑ 路由/OCR\n☑ 原页对照\n☐ AC-M2 签字", size=8, color=GRAY, align="center", fill="E8F5EA")
    write_cell(net.rows[1].cells[4], "☑ 发布门禁\n☑ 三模检索\n☐ AC-M3 题集", size=8, color=GRAY, align="center", fill="E8F5EA")
    write_cell(net.rows[1].cells[6], "☑ Schema门禁\n☑ 回退RAG\n☐ 100条金标", size=8, color=GRAY, align="center", fill="FFF4E0")
    write_cell(net.rows[1].cells[8], "☑ 字段证据\n☑ 导出一致\n☐ 专家统计", size=8, color=GRAY, align="center", fill="FFF4E0")
    for col in (1, 3, 5, 7):
        write_cell(net.rows[1].cells[col], "", size=8, fill="FFFFFF")
    write_cell(
        net.rows[2].cells[0],
        "手画备注 / 搭线区：________________________________________________________________\n"
        "________________________________________________________________________________\n"
        "________________________________________________________________________________",
        size=10,
        color=GRAY,
        fill="FAFBFD",
    )
    # merge bottom row across
    net.rows[2].cells[0].merge(net.rows[2].cells[8])

    add_heading(doc, "需求 ↔ 模块 对照（方便搭线）", 2)
    add_table(
        doc,
        ["勾", "需求", "主要落点", "可连到"],
        [
            (DONE, "PR-P0-01～03 项目/任务/状态", "控制面", "M1 / 全链"),
            (DONE, "PR-P0-04～09 接入与解析", "data_pipeline", "M2"),
            (DONE, "PR-P0-10～14 台账检索", "资料库/检索", "M3"),
            (PART, "PR-P0-12 正式嵌入", "索引快照", "M3"),
            (DONE, "PR-P0-15～19 图谱/GraphRAG", "kg + GraphStore", "M4"),
            (DONE, "PR-P0-20～23 FMEA", "FMEA 模板/导出", "M5"),
            (DONE, "PR-P0-24～29 身份审计验收台", "delivery 中间件", "全链"),
            (OPEN, "AC-M2-01/02 OCR 金标准", "验收包", "M2"),
            (OPEN, "AC-M3-01 检索金标准", "验收包", "M3"),
            (OPEN, "AC-M4-01 关系金标准", "验收包", "M4"),
            (OPEN, "AC-M5-01 专家 FMEA", "验收包", "M5"),
            (PART, "AC-E2E-01/02 界面闭环", "工作台", "全链"),
        ],
        col_widths=[1.4, 6.2, 4.2, 3.6],
    )

    add_heading(doc, "一、端到端流程", 1)
    add_table(
        doc,
        ["勾", "环节", "说明"],
        [(m, name, note) for name, m, note in MAIN_FLOW],
        col_widths=[1.4, 5.0, 11.0],
    )

    add_heading(doc, "二、P0 产品功能", 1)
    d, p, o = count_marks([(a, b, c) for a, b, c, *_ in [(x[0], x[1], x[2]) for x in MAIN_P0]])
    add_body(doc, f"本表 {len(MAIN_P0)} 条：{DONE} {sum(1 for x in MAIN_P0 if x[1]==DONE)}    {PART} {sum(1 for x in MAIN_P0 if x[1]==PART)}    {OPEN} {sum(1 for x in MAIN_P0 if x[1]==OPEN)}", size=10)
    add_table(
        doc,
        ["勾", "编号", "名称", "核对说明"],
        [(m, i, n, note) for i, m, n, note in MAIN_P0],
        col_widths=[1.3, 2.6, 3.4, 10.2],
    )

    add_heading(doc, "三、P1 产品化增强", 1)
    add_table(
        doc,
        ["勾", "编号", "名称", "核对说明"],
        [(m, i, n, note) for i, m, n, note in MAIN_P1],
        col_widths=[1.3, 2.6, 3.4, 10.2],
    )

    add_heading(doc, "四、技术要求 TECH", 1)
    add_table(
        doc,
        ["勾", "编号", "核对说明"],
        [(m, i, n) for i, m, n in MAIN_TECH],
        col_widths=[1.3, 2.6, 13.6],
    )

    add_heading(doc, "五、验收标准 AC（多数不能打勾）", 1)
    add_body(doc, "这些是现场/金标准门禁。代码过了不等于这里能勾。", size=10, color=RED, bold=True)
    add_table(
        doc,
        ["勾", "编号", "门槛", "现状"],
        [(m, i, n, note) for i, m, n, note in MAIN_AC],
        col_widths=[1.3, 2.6, 5.5, 8.1],
    )

    add_heading(doc, "六、1.0 阶段清单（原文第八章）", 1)
    add_table(
        doc,
        ["勾", "阶段", "说明"],
        [
            (PART, "阶段 0 冻结基线", "交付分支已收拢；14 本真实包与 SHA-256 清单仍要人确认"),
            (DONE, "阶段 1 产品主链集成", "project_id、任务、列表、身份、异步、界面已接到 /api/delivery"),
            (OPEN, "阶段 2 真实数据质量验收", "OCR/检索/图谱/FMEA 金标准未签字"),
            (PART, "阶段 3 稳定性与交付", "有启动器与说明；性能/恢复演练未签字。现交付走浏览器"),
            (OPEN, "1.0 之后", "多项目协作、企业集成明确不在本交付"),
        ],
        col_widths=[1.3, 5.0, 11.2],
    )

    add_heading(doc, "七、待项目组确认（保持空框，会上勾）", 1)
    add_table(
        doc,
        ["勾", "待确认"],
        [
            (OPEN, "1.0 是否只锁定燃气轮机资料和 FMEA 作为验收领域"),
            (OPEN, "14 本资料、13 本扫描 PDF、10 问、人工 FMEA 的最终文件与责任人"),
            (OPEN, "指定 OCR / 嵌入 / LLM Provider，以及哪些资料允许外发"),
            (OPEN, "金标准标注人、复核人和可接受指标"),
            (OPEN, "正式交付要 JSON / CSV / XLSX / DOCX 中的哪些格式"),
            (OPEN, "运行范围：个人电脑 / 局域网 / 内网服务器（决定认证要求）"),
        ],
        col_widths=[1.4, 16.0],
    )

    p0_done = sum(1 for x in MAIN_P0 if x[1] == DONE)
    add_heading(doc, "八、一句话结论", 1)
    add_body(
        doc,
        f"P0 功能 {p0_done}/{len(MAIN_P0)} 条已实现（另有 1 条部分）。技术项大体已接通。验收 AC 10 条里没有一条可以对外说「现场通过」。"
        "开会请在搭线网上手画责任线和补勾，不要改已填的验收空框。",
        size=11,
        color=NAVY,
        bold=True,
    )
    doc.save(OUT_MAIN)
    return OUT_MAIN


# --- v1.0 workbench PRD ---

V10_GAPS = [
    (DONE, "能力可操作", "主控制台已接 /api/delivery；资料、图谱、FMEA、验收台可点"),
    (DONE, "上下文血缘", "交付任务/版本/证据可回溯；批次页仍可再加粗"),
    (DONE, "发布风险可见", "门禁与阻断原因在审核/发布路径上"),
    (DONE, "任务可管理", "资料/FMEA/任务分页列表与队列已有"),
    (PART, "交付价值显性化", "工作台在，部分界面改动若未提交则客户检出旧壳"),
]

V10_NAV = [
    (DONE, "交付总览", "待办、健康、进入各阶段"),
    (DONE, "资料审核", "列表、原页对照、修订/批准/发布/回滚"),
    (DONE, "图谱审核", "语句表、筛选、证据、发布、同题对比入口"),
    (DONE, "FMEA 交付", "任务、逐字段证据、批准、导出"),
    (DONE, "审计与反馈", "审计事件、反馈回流、重验证"),
    (DONE, "系统配置 / 验收", "Provider/健康；另有验收工作台"),
]

V10_FR = [
    ("FR-001", "P0", DONE, "统一审核队列", "按阶段/状态/严重度筛，展示下一步与阻断"),
    ("FR-002", "P0", DONE, "交付批次与血缘", "源资产→资料→图→FMEA→反馈可查"),
    ("FR-003", "P0", DONE, "资料接入", "文件类型+解析/OCR；异步进度与失败页重试"),
    ("FR-004", "P0", DONE, "原页对照审核", "源页与解析块同屏，问题可定位"),
    ("FR-005", "P0", DONE, "资料修订与决策", "修改出新版本；approve/reject/modify 留审计"),
    ("FR-006", "P0", DONE, "资料发布、比较与回滚", "门禁清单、索引同步、版本比较"),
    ("FR-007", "P0", DONE, "图谱候选生成", "已发布资料；未配置 LLM 时 blocked，不伪造"),
    ("FR-008", "P0", DONE, "图谱语句审核", "表格、筛选、证据、修订"),
    ("FR-009", "P0", DONE, "图谱证据审计", "覆盖、越界、缺失、冲突、Schema 违规"),
    ("FR-010", "P0", DONE, "图谱发布与同步", "仅合规可发布；同步 GraphStore"),
    ("FR-011", "P1", PART, "RAG/GraphRAG 同题对比", "代码与界面入口有；缺 100 条真实集报告"),
    ("FR-012", "P0", DONE, "FMEA 任务创建", "必须选已发布图、资料、模板"),
    ("FR-013", "P0", DONE, "FMEA 逐字段审核", "七字段+evidence_id；空/冲突标出"),
    ("FR-014", "P0", DONE, "FMEA 决策与发布", "approve 且门禁过才能发布"),
    ("FR-015", "P0", DONE, "导出与一致性验证", "JSON/CSV/DOCX；不一致不能当交付完成"),
    ("FR-016", "P0", DONE, "问题反馈与回流", "按根因阶段修复并重验证"),
    ("FR-017", "P0", DONE, "审计时间线", "审核/发布/回滚/反馈可按对象查"),
    ("FR-018", "P0", DONE, "可靠状态反馈", "loading/blocked/failed；错误可复制 code"),
    ("FR-019", "P1", DONE, "批量审核辅助", "批量筛+逐项确认；无一键全过发布"),
    ("FR-020", "P2", OPEN, "多人协作", "本地单用户可用；OIDC 多人未实测"),
]

V10_API = [
    (DONE, "GET /review-queue", "统一分页审核队列"),
    (DONE, "GET /documents 列表", "不必先握 version_id"),
    (DONE, "GET /fmea/tasks 列表", "按状态/图版本分页"),
    (DONE, "GET /audit/events", "跨对象审计"),
    (DONE, "血缘 / batches", "轻量版本链，不复制全文"),
    (DONE, "publish 带 actor", "comment / idempotency / expected_version"),
    (DONE, "统一错误结构", "code/message/stage/retryable/correlation_id"),
]

V10_AC = [
    ("AC-01", DONE, "待审资料可发现", "列表进入审核，不必手输 version_id"),
    ("AC-02", DONE, "原页对照", "点问题同时定位源页和解析块"),
    ("AC-03", DONE, "资料发布门禁", "未批准/有阻断不能改状态"),
    ("AC-04", DONE, "资料修订", "modify 出新版本，旧版保留"),
    ("AC-05", DONE, "图谱证据审核", "违规语句阻止发布"),
    ("AC-06", DONE, "图谱同步", "发布后 GraphStore 活动版本更新"),
    ("AC-07", DONE, "FMEA 字段证据", "非空字段能打开证据与血缘"),
    ("AC-08", DONE, "未知字段", "保持 null，不伪造评分"),
    ("AC-09", DONE, "交付导出", "JSON/CSV 一致；已加 DOCX"),
    ("AC-10", DONE, "问题回流", "修复运行可审计，下游再过人工门禁"),
    ("AC-11", DONE, "并发冲突", "旧 expected_version 返回 409"),
    ("AC-12", PART, "完整闭环仅 UI", "界面能走通；缺两人试点签字"),
]

V10_NFR = [
    ("NFR-01", PART, "性能", "有测量接口；无约定设备 P95 报告"),
    ("NFR-02", DONE, "可靠性", "写操作幂等，任务可恢复/明确 failed"),
    ("NFR-03", DONE, "一致性", "版本不一致阻断发布"),
    ("NFR-04", DONE, "审计", "决定/发布/回滚/回流可查"),
    ("NFR-05", DONE, "安全", "默认本地；密钥不进前端。交付不走 Electron"),
    ("NFR-06", PART, "可访问性", "有文字状态；完整键盘验收未做"),
    ("NFR-07", DONE, "可观测性", "correlation_id 与阶段耗时"),
    ("NFR-08", PART, "可测试性", "合成夹具回归有；代表性质检包未齐"),
    ("NFR-09", PART, "兼容性", "本机 Web 是交付主路径；Electron 不作为交付"),
]


def build_v10():
    doc = Document()
    set_narrow_margins(doc)
    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title.add_run("PowerRAG 工作台 PRD v1.0 勾选核对稿")
    set_run_font(run, size=20, bold=True, color=NAVY)
    sub = doc.add_paragraph()
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = sub.add_run("源文件：PowerRAG_GraphRAG_Governance_Workbench_PRD_v1.0_2026-08-09.docx")
    set_run_font(run, size=10, color=GRAY)
    sub2 = doc.add_paragraph()
    sub2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = sub2.add_run("原文日期 2026-08-09（当时控制台未接 /api/delivery）    本次按 2026-09-23 产品线重勾")
    set_run_font(run, size=10, color=GRAY)
    add_legend(doc)

    add_heading(doc, "〇、相对 8 月原文，断层还在不在", 1)
    add_table(
        doc,
        ["勾", "原文问题", "2026-09 核对"],
        [(m, n, note) for m, n, note in V10_GAPS],
        col_widths=[1.3, 4.2, 12.0],
    )

    add_heading(doc, "一、一级导航 / 页面", 1)
    add_table(
        doc,
        ["勾", "页面", "核对说明"],
        [(m, n, note) for m, n, note in V10_NAV],
        col_widths=[1.3, 4.2, 12.0],
    )

    add_heading(doc, "二、功能需求 FR-001～FR-020", 1)
    fr_done = sum(1 for x in V10_FR if x[2] == DONE)
    fr_part = sum(1 for x in V10_FR if x[2] == PART)
    fr_open = sum(1 for x in V10_FR if x[2] == OPEN)
    add_body(doc, f"{len(V10_FR)} 条：{DONE} {fr_done}    {PART} {fr_part}    {OPEN} {fr_open}。P0 除试点签字外均已接到工作台。", size=10)
    add_table(
        doc,
        ["勾", "编号", "优先级", "需求", "核对说明"],
        [(m, i, pri, n, note) for i, pri, m, n, note in V10_FR],
        col_widths=[1.2, 2.2, 1.6, 4.2, 8.3],
    )

    add_heading(doc, "三、MVP 必须补的接口（原文 8.2）", 1)
    add_table(
        doc,
        ["勾", "接口/调整", "核对说明"],
        [(m, n, note) for m, n, note in V10_API],
        col_widths=[1.3, 5.0, 11.2],
    )

    add_heading(doc, "四、MVP 验收 AC-01～AC-12", 1)
    add_body(doc, "这里的勾表示「界面/API 能按场景跑」；AC-12 和金标准签字仍不算现场通过。", size=10)
    add_table(
        doc,
        ["勾", "编号", "场景", "核对说明"],
        [(m, i, n, note) for i, m, n, note in V10_AC],
        col_widths=[1.3, 2.2, 4.2, 9.8],
    )

    add_heading(doc, "五、非功能 NFR", 1)
    add_table(
        doc,
        ["勾", "编号", "类别", "核对说明"],
        [(m, i, n, note) for i, m, n, note in V10_NFR],
        col_widths=[1.3, 2.4, 2.6, 11.2],
    )

    add_heading(doc, "六、原文阶段退出条件", 1)
    add_table(
        doc,
        ["勾", "阶段", "说明"],
        [
            (DONE, "阶段 0 合同与样式", "队列/列表/审计合同与错误规范已在 /api/delivery"),
            (DONE, "阶段 1 资料审核 MVP", "扫描/原生 PDF 可走 UI 发布（代表性质检仍待现场件）"),
            (DONE, "阶段 2 图谱与 FMEA", "代表性夹具可走完 M2–M5；真实资料质量另算"),
            (PART, "阶段 3 硬化", "回流/并发/日志有；AC-01～12 代码向通过，缺试点包"),
            (OPEN, "阶段 4 试点 10 任务", "周期、回流、用户问题未签"),
        ],
        col_widths=[1.3, 5.2, 11.0],
    )

    add_heading(doc, "七、一句话结论", 1)
    add_body(
        doc,
        f"v1.0 工作台 PRD 的 P0 功能基本做完（FR 已勾 {fr_done} 条，部分 {fr_part}，未做 {fr_open}）。"
        "8 月说的「主控制台没接 /api/delivery」已经过时。还空着的主要是 FR-020 多人协作、性能/无障碍签字，以及 10 个试点任务。"
        "请在打印稿上继续画对勾或把 FR 连到页面。",
        size=11,
        color=NAVY,
        bold=True,
    )
    doc.save(OUT_V10)
    return OUT_V10


if __name__ == "__main__":
    a = build_main()
    b = build_v10()
    print(a)
    print(b)
    print("ok", a.exists(), b.exists(), a.stat().st_size, b.stat().st_size)
