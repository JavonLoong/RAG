import { C, bg, title, footer, label, box, metric, bar, stage, smallNote } from "./common.mjs";

export async function slide01(presentation, ctx) {
  const slide = presentation.slides.add();

      bg(slide, ctx, C.navy);
      label(slide, ctx, "动力装备 RAG / GraphRAG 阶段汇报", 70, 86, 860, 70, { size: 38, bold: true, color: C.white });
      label(slide, ctx, "从 Python 课程项目，到可评测、可复现、可解释的检索增强系统", 72, 166, 900, 42, { size: 20, color: "#C8D3E4" });
      ctx.addShape(slide, { x: 70, y: 260, w: 1080, h: 1, fill: "#38506F", line: ctx.line("#00000000", 0) });
      metric(slide, ctx, "14", "资料输入 PDF/JSON", 76, 302, "#76D6E2");
      metric(slide, ctx, "13", "扫描 PDF 已 OCR", 270, 302, "#A9E3BF");
      metric(slide, ctx, "30", "系统评测问题", 464, 302, "#F5C56B");
      metric(slide, ctx, "6494", "离线评测 chunks", 658, 302, "#9CC3FF");
      metric(slide, ctx, "0.833", "最佳 question recall@K", 872, 302, "#FFFFFF");
      label(slide, ctx, "第五天产物：架构图 · 实验表 · 成功/失败案例 · 可编辑 PPTX", 72, 595, 980, 32, { size: 18, color: "#DCE6F6" });
      footer(slide, ctx, 1);

  return slide;
}
