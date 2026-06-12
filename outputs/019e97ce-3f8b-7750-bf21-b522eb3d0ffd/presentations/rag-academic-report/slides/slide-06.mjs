import { C, bg, title, footer, label, box, metric, bar, stage, smallNote } from "./common.mjs";

export async function slide06(presentation, ctx) {
  const slide = presentation.slides.add();

      bg(slide, ctx);
      title(slide, ctx, "Baseline results", "专业术语场景下，keyword baseline 暂时强于 hashing 向量", 6);
      label(slide, ctx, "Question recall@K", 88, 166, 300, 26, { size: 19, bold: true });
      bar(slide, ctx, "keyword", 0.833333, 1, 98, 218, 420, C.blue);
      bar(slide, ctx, "dense_hashing", 0.583333, 1, 98, 276, 420, C.cyan);
      bar(slide, ctx, "hybrid_rrf", 0.816667, 1, 98, 334, 420, C.green);
      label(slide, ctx, "Avg keyword coverage", 88, 438, 300, 26, { size: 19, bold: true });
      bar(slide, ctx, "keyword", 0.563056, 1, 98, 490, 420, C.blue);
      bar(slide, ctx, "dense_hashing", 0.299722, 1, 98, 548, 420, C.cyan);
      bar(slide, ctx, "hybrid_rrf", 0.519722, 1, 98, 606, 420, C.green);
      box(slide, ctx, 790, 202, 330, 220, C.white, C.line);
      label(slide, ctx, "汇报结论", 820, 232, 240, 28, { size: 20, bold: true, color: C.blue });
      label(slide, ctx, "当前 hashing embedding 只是离线可复现 baseline，不代表最终语义检索质量。专业词汇和报告编号更依赖关键词召回。", 820, 276, 258, 118, { size: 17, color: C.ink });
      metric(slide, ctx, "25", "keyword 强命中题", 802, 474, C.blue);
      metric(slide, ctx, "10", "keyword 未命中题", 1000, 474, C.red);

  return slide;
}
