import { renderSlide } from "./common.mjs";

const spec = {"number": 8, "kicker": "Special prize angle", "title": "特等奖争取点：创新性、完成度、可复现和边界严谨同时成立", "subtitle": "这页用于回答“为什么不只是一个普通 RAG demo”。", "cards": [{"x": 70, "y": 210, "w": 260, "h": 230, "title": "创新性", "body": "Evidence-bound RAG + GraphRAG 子集 + 失败归因 + 补证闭环。", "fill": "#EAF1FB"}, {"x": 360, "y": 210, "w": 260, "h": 230, "title": "完成度", "body": "项目书、白皮书、验收清单、固定演示、归档包和门禁报告齐备。", "fill": "#EAF6EF"}, {"x": 650, "y": 210, "w": 260, "h": 230, "title": "可复现", "body": "60 题评测集、baseline、smoke、hashes、readiness gate 可重新运行。", "fill": "#FFF4DA"}, {"x": 940, "y": 210, "w": 260, "h": 230, "title": "边界", "body": "不夸大生产替代、不伪造专家反馈、不把 gate 说成获奖保证。", "fill": "#FBEAEA", "color": "#B54747"}], "callout": {"x": 115, "y": 536, "w": 1030, "h": 70, "text": "现场表达策略：主动展示失败案例和边界，比回避问题更能体现科学性和工程可信度。"}};

export async function slide08(presentation, ctx) {
  const slide = presentation.slides.add();
  await renderSlide(slide, ctx, spec);
  return slide;
}
