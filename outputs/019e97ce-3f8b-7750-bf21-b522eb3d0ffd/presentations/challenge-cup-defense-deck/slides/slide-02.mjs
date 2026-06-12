import { renderSlide } from "./common.mjs";

const spec = {"number": 2, "kicker": "Problem", "title": "动力装备资料难点不在问答，而在证据链能否被追溯", "subtitle": "扫描件、术语、部件关系和维修流程混在一起，普通检索容易回答但难以解释。", "cards": [{"x": 70, "y": 210, "w": 330, "h": 230, "title": "真实痛点", "body": "资料分散、扫描件多、术语密集；评委最关心系统是否能稳定定位证据，而不是一句流畅回答。", "fill": "#FBEAEA", "color": "#B54747"}, {"x": 465, "y": 210, "w": 330, "h": 230, "title": "方法创新", "body": "把 OCR、chunk、RAG、知识图谱、GraphRAG 子集和人工补证串成 evidence-bound 工作流。", "fill": "#EAF1FB", "color": "#2457A6"}, {"x": 860, "y": 210, "w": 330, "h": 230, "title": "结项价值", "body": "材料包、readiness gate、submission archive 和固定演示场景让项目能被验收，而不是只能口头展示。", "fill": "#EAF6EF", "color": "#2F7D59"}], "callout": {"x": 140, "y": 542, "w": 980, "h": 68, "text": "一句话答辩：我们做的是“证据型辅助和知识资产整理”，不是替代工程师做高风险维修决策。"}};

export async function slide02(presentation, ctx) {
  const slide = presentation.slides.add();
  await renderSlide(slide, ctx, spec);
  return slide;
}
