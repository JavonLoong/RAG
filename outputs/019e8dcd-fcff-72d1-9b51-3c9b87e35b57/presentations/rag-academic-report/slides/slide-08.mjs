import { C, bg, title, footer, label, box, metric, bar, stage, smallNote } from "./common.mjs";

export async function slide08(presentation, ctx) {
  const slide = presentation.slides.add();

      bg(slide, ctx);
      title(slide, ctx, "Failure analysis", "15 个弱/失败案例被归为 6 类可操作优化项", 8);
      const rows = [["evaluation_concept_gap", 4, "评测术语源不集中"], ["hybrid_dilution", 5, "弱 hashing 稀释排序"], ["structured_fact_routing", 2, "结构化事实未路由"], ["partial_ranking_gap", 2, "Top-K 排序/粒度不足"], ["terminology_alias_gap", 1, "术语别名未扩展"], ["exact_number_fact", 1, "精确数字事实需短卡片"]];
      let y = 174;
      for (const [cat, count, note] of rows) {
        bar(slide, ctx, cat, count, 5, 74, y, 420, count >= 4 ? C.red : count >= 2 ? C.amber : C.blue, "");
        label(slide, ctx, note, 770, y - 2, 330, 26, { size: 15, color: C.sub });
        y += 58;
      }
      box(slide, ctx, 740, 504, 390, 94, C.white, C.line);
      label(slide, ctx, "下一步不是堆功能，而是修检索假设", 770, 526, 320, 26, { size: 18, bold: true, color: C.ink });
      label(slide, ctx, "同义词扩展 · 事实卡片 · source_scope 路由 · 更好的 embedding/reranker", 770, 560, 320, 34, { size: 15, color: C.sub });

  return slide;
}
