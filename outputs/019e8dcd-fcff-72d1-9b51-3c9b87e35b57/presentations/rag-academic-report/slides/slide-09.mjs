import { C, bg, title, footer, label, box, metric, bar, stage, smallNote } from "./common.mjs";

export async function slide09(presentation, ctx) {
  const slide = presentation.slides.add();

      bg(slide, ctx);
      title(slide, ctx, "Live demo plan", "现场演示只走一条稳定链路，再展示 Graph POC 证据", 9);
      stage(slide, ctx, 1, "打开成果总览：说明资料规模与入口", 94, 174, 480, 66, C.white);
      stage(slide, ctx, 2, "展示 30 题评测集：说明不是随机提问", 94, 260, 480, 66, C.white);
      stage(slide, ctx, 3, "展示第三天 baseline 表：keyword / dense / hybrid", 94, 346, 480, 66, C.white);
      stage(slide, ctx, 4, "展示一个成功案例和一个失败案例", 94, 432, 480, 66, C.white);
      stage(slide, ctx, 5, "打开 Graph POC：schema / 三元组 / evidence / 人工评审", 94, 518, 480, 66, C.white);
      box(slide, ctx, 720, 190, 360, 240, C.paleBlue, "#BFD1EA");
      label(slide, ctx, "备用策略", 748, 222, 240, 28, { size: 21, bold: true, color: C.blue });
      label(slide, ctx, "如果现场系统启动不稳定，直接展示已生成的 Markdown 报告、PPT 表格和 Graph POC SVG/HTML。", 748, 272, 280, 96, { size: 18, color: C.ink });
      box(slide, ctx, 720, 468, 360, 88, C.white, C.line);
      label(slide, ctx, "演示原则：少讲技术名词，多讲证据链和评测结论。", 748, 492, 300, 38, { size: 18, bold: true, color: C.ink });

  return slide;
}
