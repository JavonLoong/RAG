import { C, bg, title, footer, label, box, metric, bar, stage, smallNote } from "./common.mjs";

export async function slide03(presentation, ctx) {
  const slide = presentation.slides.add();

      bg(slide, ctx);
      title(slide, ctx, "Data pipeline", "数据链路已经从资料导入扩展到评测语料", 3);
      stage(slide, ctx, 1, "14 本资料 + 问答 JSON", 70, 176, 190, 78, C.paleBlue);
      stage(slide, ctx, 2, "13 本扫描 PDF OCR", 292, 176, 190, 78, C.paleGreen);
      stage(slide, ctx, 3, "OCR 清洗与 chunk", 514, 176, 190, 78, C.paleAmber);
      stage(slide, ctx, 4, "普通 RAG / Graph POC", 736, 176, 210, 78, C.white);
      stage(slide, ctx, 5, "60 题系统评测", 978, 176, 190, 78, C.white);
      for (const x of [266, 488, 710, 952]) ctx.addShape(slide, { x, y: 214, w: 22, h: 4, fill: C.cyan, line: ctx.line("#00000000", 0) });
      label(slide, ctx, "OCR 审计证据", 92, 340, 260, 28, { size: 18, bold: true });
      metric(slide, ctx, "5483", "OCR 页数", 96, 384, C.blue);
      metric(slide, ctx, "5472", "有文字页", 272, 384, C.green);
      metric(slide, ctx, "0", "运行错误数", 448, 384, C.amber);
      label(slide, ctx, "评测语料证据", 720, 340, 260, 28, { size: 18, bold: true });
      metric(slide, ctx, "6494", "离线 chunks", 724, 384, C.blue);
      metric(slide, ctx, "60", "评测问题", 900, 384, C.green);
      metric(slide, ctx, "8", "题型分组", 1076, 384, C.amber);
      smallNote(slide, ctx, "注：当前第五天 PPT 使用本地 OCR 文本、工程报告和 Graph POC 材料构建离线评测 corpus。", 74, 594, 1040, 44);

  return slide;
}
