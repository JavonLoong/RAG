import { C, bg, title, footer, label, box, metric, bar, stage, smallNote } from "./common.mjs";

export async function slide05(presentation, ctx) {
  const slide = presentation.slides.add();

      bg(slide, ctx);
      title(slide, ctx, "Evaluation design", "60 题评测集覆盖事实、流程、OCR 风险和 GraphRAG", 5);
      const rows = [
        ["基础系统评测 se001-se030", 30, C.blue],
        ["挑战杯扩展 cc031-cc060", 30, C.green],
        ["GraphRAG 同题子集", 10, C.red],
        ["graph context/global 题", 10, C.cyan],
      ];
      let y = 174;
      for (const [name, value, color] of rows) {
        bar(slide, ctx, name, value, 30, 90, y, 420, color, " 题");
        y += 72;
      }
      box(slide, ctx, 760, 174, 350, 286, C.white, C.line);
      label(slide, ctx, "每题包含", 790, 204, 240, 28, { size: 20, bold: true });
      label(slide, ctx, "question · reference_answer · expected_evidence_keywords · task_type · source_scope · grading_notes", 790, 248, 280, 128, { size: 17, color: C.ink });
      label(slide, ctx, "评分口径", 790, 402, 240, 28, { size: 20, bold: true });
      label(slide, ctx, "先看检索证据覆盖，再看回答是否忠实。", 790, 442, 278, 50, { size: 17, color: C.sub });
      smallNote(slide, ctx, "这页回答老师最关心的问题：不是随便问几个问题，而是有分组、有标准答案、有证据关键词。", 88, 612, 980, 34);

  return slide;
}
