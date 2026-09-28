# -*- coding: utf-8 -*-
"""Copy original docx bytes. Insert a visible 仿宋-safe check run."""

from io import BytesIO
from pathlib import Path
import re
from zipfile import ZipFile

# 仿宋没有 ☑（U+2611），Word 会显示空白。用 微软雅黑 的 √。
MARK = "√ "
CHECK_RUN = (
    "<w:r><w:rPr>"
    '<w:rFonts w:ascii="微软雅黑" w:hAnsi="微软雅黑" w:eastAsia="微软雅黑"/>'
    '<w:b w:val="0"/><w:color w:val="000000"/><w:sz w:val="32"/>'
    '</w:rPr><w:t xml:space="preserve">' + MARK + "</w:t></w:r>"
)

MAIN_SRC = Path(r"D:\虚拟C盘\PowerRAG PRD.docx")
MAIN_DST = Path(r"D:\虚拟C盘\PowerRAG PRD_勾选核对.docx")
V10_SRC = Path(r"D:\虚拟C盘\PowerRAG-latest\docs\PowerRAG_GraphRAG_Governance_Workbench_PRD_v1.0_2026-08-09.docx")
V10_DST = Path(r"D:\虚拟C盘\PowerRAG_工作台PRD_v1.0_勾选核对.docx")

# Replace the opening of these <w:t> values. Each needle must be unique / exact.
MAIN_OPENERS = [
    "PR-P0-01 ",
    "PR-P0-02 ",
    "PR-P0-03 ",
    "PR-P0-04 ",
    "PR-P0-05 ",
    "PR-P0-06 ",
    "PR-P0-07 ",
    "PR-P0-08 ",
    "PR-P0-09 ",
    "PR-P0-10 ",
    "PR-P0-11 ",
    "PR-P0-13 ",
    "PR-P0-14 ",
    "PR-P0-15 ",
    "PR-P0-16 ",
    "PR-P0-17 ",
    "PR-P0-18 ",
    "PR-P0-19 ",
    "PR-P0-20 ",
    "PR-P0-21 ",
    "PR-P0-22 ",
    "PR-P0-23 ",
    "PR-P0-24 ",
    "PR-P0-25 ",
    "PR-P0-26 ",
    "PR-P0-27 ",
    "PR-P1-01 ",
    "PR-P1-03 ",
    "TECH-01 ",
    "TECH-02 ",
    "TECH-03 ",
    "TECH-04 ",
    "TECH-05 ",
    "TECH-06 ",
    "TECH-07 ",
    "TECH-08 ",
    "TECH-09 ",
    "TECH-10 ",
    "TECH-11 ",
    "TECH-12 ",
    "TECH-13 ",
    "TECH-14 ",
    "TECH-16 ",
    "（一）建立项目与数据基线",
    "（二）资料接入、解析和质检",
    "（三）正式资料发布与检索",
    "（六）FMEA 生成与交付",
    "（七）问题反馈与重验证",
    "（二）阶段 1：产品主链集成",
]

V10_EXACT = [
    "FR-001",
    "FR-002",
    "FR-003",
    "FR-004",
    "FR-005",
    "FR-006",
    "FR-007",
    "FR-008",
    "FR-009",
    "FR-010",
    "FR-012",
    "FR-013",
    "FR-014",
    "FR-015",
    "FR-016",
    "FR-017",
    "FR-018",
    "FR-019",
    "AC-01",
    "AC-02",
    "AC-03",
    "AC-04",
    "AC-05",
    "AC-06",
    "AC-07",
    "AC-08",
    "AC-09",
    "AC-10",
    "AC-11",
    "NFR-02",
    "NFR-03",
    "NFR-04",
    "NFR-05",
    "NFR-07",
    "GET /api/delivery/review-queue",
    "GET /api/delivery/documents",
    "GET /api/delivery/fmea/tasks",
    "GET /api/delivery/audit/events",
    "GET /api/delivery/batches/{id}",
    "发布接口请求体",
    "统一错误结构",
    "交付总览",
    "资料审核",
    "图谱审核",
    "FMEA 交付",
    "审计与反馈",
    "系统配置",
    "阶段 1：资料审核 MVP",
    "阶段 2：图谱与 FMEA",
    "1",
    "2",
    "3",
    "4",
    "5",
    "6",
    "7",
]


WT_OPEN = re.compile(r"<w:t(?:\s[^>]*)?>")


def _insert_run_before_t(xml, t_start):
    r_start = xml.rfind("<w:r>", 0, t_start)
    if r_start < 0:
        return xml, False
    prelude = xml[max(0, r_start - len(CHECK_RUN)) : r_start]
    if prelude.endswith(CHECK_RUN):
        return xml, False
    return xml[:r_start] + CHECK_RUN + xml[r_start:], True


def insert_check_openers(xml, openers):
    n = 0
    missing = []
    for opener in openers:
        m = re.search(r"<w:t(?:\s[^>]*)?>" + re.escape(opener), xml)
        if not m:
            missing.append(opener)
            continue
        xml, ok = _insert_run_before_t(xml, m.start())
        if ok:
            n += 1
        else:
            missing.append(opener)
    return xml, n, missing


def insert_check_exact(xml, values):
    n = 0
    missing = []
    for value in values:
        pattern = re.compile(r"<w:t(?:\s[^>]*)?>" + re.escape(value) + r"</w:t>")
        matches = list(pattern.finditer(xml))
        if not matches:
            missing.append(value)
            continue
        for m in reversed(matches):
            xml, ok = _insert_run_before_t(xml, m.start())
            if ok:
                n += 1
    return xml, n, missing


def rewrite_docx(src, dst, xml):
    buf = BytesIO()
    with ZipFile(src, "r") as zin, ZipFile(buf, "w") as zout:
        for info in zin.infolist():
            data = xml.encode("utf-8") if info.filename == "word/document.xml" else zin.read(info.filename)
            zout.writestr(info, data)
    try:
        dst.write_bytes(buf.getvalue())
    except PermissionError:
        alt = dst.with_name(dst.stem + "_可见对勾" + dst.suffix)
        alt.write_bytes(buf.getvalue())
        print("locked, wrote", alt)
        return


def other_files_identical(src, dst):
    with ZipFile(src) as a, ZipFile(dst) as b:
        names = set(a.namelist()) | set(b.namelist())
        diffs = []
        for name in sorted(names):
            if name == "word/document.xml":
                continue
            if a.read(name) != b.read(name):
                diffs.append(name)
        return diffs


def main():
    main_xml = ZipFile(MAIN_SRC).read("word/document.xml").decode("utf-8")
    main_xml, main_n, main_miss = insert_check_openers(main_xml, MAIN_OPENERS)
    rewrite_docx(MAIN_SRC, MAIN_DST, main_xml)

    v10_xml = ZipFile(V10_SRC).read("word/document.xml").decode("utf-8")
    v10_xml, v10_n, v10_miss = insert_check_exact(v10_xml, V10_EXACT)
    rewrite_docx(V10_SRC, V10_DST, v10_xml)

    print("main marks", main_n, "missing", main_miss)
    print("v10 marks", v10_n, "missing", v10_miss)
    print("main other-file diffs", other_files_identical(MAIN_SRC, MAIN_DST))
    print("v10 other-file diffs", other_files_identical(V10_SRC, V10_DST))
    print("sizes", MAIN_SRC.stat().st_size, MAIN_DST.stat().st_size, V10_SRC.stat().st_size, V10_DST.stat().st_size)


if __name__ == "__main__":
    main()
