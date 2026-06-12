import { renderSlide } from "./common.mjs";

const spec = {"number": 3, "kicker": "Architecture", "title": "工程闭环覆盖资料导入、检索增强、图谱证据和评测门禁", "subtitle": "这页回答“项目完成度是否只是前端包装”的问题。", "metrics": [{"value": "OCR", "label": "扫描资料结构化", "color": "#2457A6"}, {"value": "RAG", "label": "文本证据召回", "color": "#1499A5"}, {"value": "KG", "label": "关系证据组织", "color": "#2F7D59"}, {"value": "Gate", "label": "机器验收门禁", "color": "#B7791F"}], "metricY": 212, "cards": [{"x": 84, "y": 365, "w": 250, "h": 120, "title": "资料层", "body": "课程资料、维修案例、JSON 问答和浏览器演示快照。"}, {"x": 378, "y": 365, "w": 250, "h": 120, "title": "检索层", "body": "keyword / hybrid / GraphRAG context，对同题子集做证据覆盖审计。"}, {"x": 672, "y": 365, "w": 250, "h": 120, "title": "评测层", "body": "60 题评测集、baseline、失败归因、manual evidence supplement。"}, {"x": 966, "y": 365, "w": 250, "h": 120, "title": "交付层", "body": "README、项目书、答辩材料、归档包、readiness gate。"}]};

export async function slide03(presentation, ctx) {
  const slide = presentation.slides.add();
  await renderSlide(slide, ctx, spec);
  return slide;
}
