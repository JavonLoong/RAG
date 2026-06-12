import { renderSlide } from "./common.mjs";

const spec = {"number": 4, "kicker": "Evaluation", "title": "60 题评测集把“能演示”压实为“能复核”", "subtitle": "11 类任务、17 类资料范围、10 道 GraphRAG 标记问题。", "metrics": [{"value": "60", "label": "评测题", "color": "#2457A6"}, {"value": "11", "label": "task_type", "color": "#1499A5"}, {"value": "17", "label": "source_scope", "color": "#2F7D59"}, {"value": "10", "label": "GraphRAG 子集", "color": "#B7791F"}, {"value": "0", "label": "剩余补证任务", "color": "#B54747"}], "metricY": 210, "bullets": [{"text": "每题包含标准答案、证据关键词、任务类型、资料范围和评分说明。"}, {"text": "GraphRAG 子集当前本地证据状态为 supported=10, partial=0, missing=0。"}, {"text": "边界：本地证据覆盖不等于在线 LLM 胜率，也不等于外部专家认可。"}], "bulletY": 390, "bulletW": 980};

export async function slide04(presentation, ctx) {
  const slide = presentation.slides.add();
  await renderSlide(slide, ctx, spec);
  return slide;
}
