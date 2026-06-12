import { C, bg, title, footer, label, box, metric, bar, stage, smallNote } from "./common.mjs";

export async function slide04(presentation, ctx) {
  const slide = presentation.slides.add();

      bg(slide, ctx);
      title(slide, ctx, "System architecture", "系统采用普通 RAG 与 GraphRAG 双线并行架构", 4);
      label(slide, ctx, "离线构建", 84, 164, 160, 26, { size: 17, bold: true, color: C.blue });
      label(slide, ctx, "在线检索", 84, 394, 160, 26, { size: 17, bold: true, color: C.green });
      box(slide, ctx, 190, 156, 980, 140, C.paleBlue, "#BFD1EA");
      label(slide, ctx, "Standard RAG", 214, 178, 180, 24, { size: 18, bold: true, color: C.blue });
      stage(slide, ctx, 1, "PDF / OCR / JSON", 220, 220, 170, 52, C.white);
      stage(slide, ctx, 2, "clean + chunk", 430, 220, 170, 52, C.white);
      stage(slide, ctx, 3, "BM25 / vector", 640, 220, 170, 52, C.white);
      stage(slide, ctx, 4, "Top-K evidence", 850, 220, 170, 52, C.white);
      box(slide, ctx, 190, 342, 980, 140, C.paleGreen, "#B9DBC7");
      label(slide, ctx, "KG / GraphRAG", 214, 364, 180, 24, { size: 18, bold: true, color: C.green });
      stage(slide, ctx, 1, "Label Studio JSON", 220, 406, 170, 52, C.white);
      stage(slide, ctx, 2, "schema triples", 430, 406, 170, 52, C.white);
      stage(slide, ctx, 3, "evidence review", 640, 406, 170, 52, C.white);
      stage(slide, ctx, 4, "community/global", 850, 406, 170, 52, C.white);
      box(slide, ctx, 266, 542, 820, 54, "#F0F3F8", "#C9D2DF");
      label(slide, ctx, "Shared infrastructure: model adapters · evaluation runner · reports · local console", 294, 558, 760, 28, { size: 17, bold: true, color: C.ink });

  return slide;
}
