import { C, bg, title, footer, label, box, metric, bar, stage, smallNote } from "./common.mjs";

export async function slide02(presentation, ctx) {
  const slide = presentation.slides.add();

      bg(slide, ctx);
      title(slide, ctx, "Research question", "汇报重点不是“能不能问答”，而是系统是否可被评估", 2);
      label(slide, ctx, "课程作业常见风险", 76, 170, 300, 32, { size: 18, bold: true, color: C.red });
      label(slide, ctx, "只演示一个问答页面，缺少数据规模、检索证据、失败分析和复现实验。", 76, 208, 310, 92, { size: 17, color: C.ink });
      label(slide, ctx, "本项目转化目标", 476, 170, 300, 32, { size: 18, bold: true, color: C.green });
      label(slide, ctx, "把真实资料、OCR、RAG、Graph POC 与评测脚本连接成一条可解释链路。", 476, 208, 330, 92, { size: 17, color: C.ink });
      label(slide, ctx, "学术汇报标准", 876, 170, 300, 32, { size: 18, bold: true, color: C.blue });
      label(slide, ctx, "问题定义、方法设计、实验指标、成功样例、失败原因、下一步优化。", 876, 208, 320, 92, { size: 17, color: C.ink });
      stage(slide, ctx, 1, "真实资料进入系统", 104, 382, 220, 82, C.white);
      stage(slide, ctx, 2, "检索链路跑通", 386, 382, 220, 82, C.white);
      stage(slide, ctx, 3, "30 题评测集", 668, 382, 220, 82, C.white);
      stage(slide, ctx, 4, "失败案例归因", 950, 382, 220, 82, C.white);
      ctx.addShape(slide, { x: 330, y: 420, w: 48, h: 4, fill: C.cyan, line: ctx.line("#00000000", 0) });
      ctx.addShape(slide, { x: 612, y: 420, w: 48, h: 4, fill: C.cyan, line: ctx.line("#00000000", 0) });
      ctx.addShape(slide, { x: 894, y: 420, w: 48, h: 4, fill: C.cyan, line: ctx.line("#00000000", 0) });

  return slide;
}
