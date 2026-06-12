import { renderSlide } from "./common.mjs";

const spec = {"number": 10, "kicker": "Close", "title": "90 秒讲清项目，3 分钟证明它能被复核", "subtitle": "终审答辩只保留一条主线：问题、方法、证据、边界、下一步。", "metrics": [{"value": "90s", "label": "开场定位", "color": "#2457A6"}, {"value": "180s", "label": "固定演示", "color": "#1499A5"}, {"value": "20s", "label": "离线切换", "color": "#2F7D59"}, {"value": "30s", "label": "杀手问题", "color": "#B7791F"}, {"value": "0", "label": "夸大承诺", "color": "#B54747"}], "metricY": 220, "bullets": [{"text": "结论：项目已经从 RAG 页面升级为可结项、可审计、可答辩的知识工程系统。", "bold": true}, {"text": "特等奖冲刺仍需真实专家反馈和真实彩排证据；这两项不能用内部材料替代。"}, {"text": "最终动作：带着 submission archive、PPT、讲稿和 readiness report 进入现场。"}], "bulletY": 424, "bulletW": 990};

export async function slide10(presentation, ctx) {
  const slide = presentation.slides.add();
  await renderSlide(slide, ctx, spec);
  return slide;
}
