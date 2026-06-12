import { C, bg, title, footer, label, box, metric, bar, stage, smallNote } from "./common.mjs";

export async function slide07(presentation, ctx) {
  const slide = presentation.slides.add();

      bg(slide, ctx);
      title(slide, ctx, "Case diagnostics", "成功、弱命中和失败案例共同说明系统边界", 7);
      box(slide, ctx, 70, 170, 330, 370, C.paleGreen, "#B9DBC7");
      label(slide, ctx, "成功案例", 96, 196, 220, 28, { size: 21, bold: true, color: C.green });
      label(slide, ctx, "se001 联合循环效率\nse002 压气机作用\nse004 涡轮输出机械功", 96, 246, 260, 118, { size: 18, color: C.ink });
      label(slide, ctx, "说明：基础领域事实可以从 OCR 书籍中召回可用证据。", 96, 416, 260, 78, { size: 16, color: C.sub });
      box(slide, ctx, 465, 170, 330, 370, C.paleAmber, "#E6CC91");
      label(slide, ctx, "弱命中案例", 491, 196, 220, 28, { size: 21, bold: true, color: C.amber });
      label(slide, ctx, "se003 燃烧室功能\nse010 维修报告证据片段\nse021 schema 约束", 491, 246, 260, 118, { size: 18, color: C.ink });
      label(slide, ctx, "说明：Top-K 有相关片段，但关键词覆盖不完整，需要调 chunk 和 reranker。", 491, 416, 260, 78, { size: 16, color: C.sub });
      box(slide, ctx, 860, 170, 330, 370, C.paleRed, "#E1B7B7");
      label(slide, ctx, "失败案例", 886, 196, 220, 28, { size: 21, bold: true, color: C.red });
      label(slide, ctx, "se013 Reranker 术语\nse024 POC 数字事实\nse027 Goldwind 数据规模", 886, 246, 260, 118, { size: 18, color: C.ink });
      label(slide, ctx, "说明：别名、精确数字和结构化字段需要专门索引或事实卡片。", 886, 416, 260, 78, { size: 16, color: C.sub });

  return slide;
}
