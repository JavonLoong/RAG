import { renderSlide } from "./common.mjs";

const spec = {"number": 1, "dark": true, "kicker": "Opening", "title": "知燃知维：面向动力装备运维知识的可信 GraphRAG 系统", "subtitle": "目标不是展示一个问答页，而是交付可结项、可复核、可答辩的证据型知识工程项目。", "metrics": [{"value": "60", "label": "系统评测问题", "color": "#F5C56B"}, {"value": "11", "label": "任务类型覆盖", "color": "#76D6E2"}, {"value": "17", "label": "资料范围覆盖", "color": "#A9E3BF"}, {"value": "Archive", "label": "manifest 记录", "color": "#FFFFFF"}, {"value": "GT-07", "label": "固定演示场景", "color": "#F2A6A6"}], "metricY": 242, "bullets": [{"text": "评审主线：真实资料处理 + RAG/GraphRAG + 自动评测 + 可复现门禁 + 清晰边界", "bold": true}, {"text": "现场策略：先证明完成度，再用 GT-07 异常振动场景展示应用价值。"}, {"text": "诚信边界：专家反馈与真实彩排未归档前，不把准备材料说成外部背书。"}], "bulletY": 420, "bulletW": 980};

export async function slide01(presentation, ctx) {
  const slide = presentation.slides.add();
  await renderSlide(slide, ctx, spec);
  return slide;
}
