import { C, bg, title, footer, label, box, metric, bar, stage, smallNote } from "./common.mjs";

export async function slide10(presentation, ctx) {
  const slide = presentation.slides.add();

      bg(slide, ctx, "#F4F6F9");
      title(slide, ctx, "Final week plan", "剩余时间聚焦可汇报质量，而不是临时扩功能", 10);
      stage(slide, ctx, 6, "第六天：PPT 排练、截图、失败案例讲稿", 102, 190, 320, 92, C.white);
      stage(slide, ctx, 7, "第七天：现场演示检查、备用文件、时间控制", 486, 190, 320, 92, C.white);
      stage(slide, ctx, 8, "汇报后：替换真实 embedding、接入 reranker、补结构化事实路由", 870, 190, 320, 92, C.white);
      label(slide, ctx, "最终可交付", 110, 386, 240, 30, { size: 22, bold: true, color: C.blue });
      label(slide, ctx, "1. 可编辑 PPTX\n2. 30 题评测集\n3. baseline 对比报告\n4. 失败案例分析\n5. Graph POC 证据链", 112, 438, 360, 150, { size: 20, color: C.ink });
      label(slide, ctx, "核心收束", 676, 386, 240, 30, { size: 22, bold: true, color: C.green });
      label(slide, ctx, "这个项目的价值不是“会调用大模型”，而是把动力装备资料处理、检索、图谱化和评测组织成了一个可以继续研究的工程实验系统。", 676, 438, 420, 116, { size: 20, color: C.ink });

  return slide;
}
