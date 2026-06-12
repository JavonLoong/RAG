import { renderSlide } from "./common.mjs";

const spec = {"number": 6, "kicker": "GraphRAG proof", "title": "GraphRAG 价值不靠泛化承诺，而靠关系证据可视化", "subtitle": "答辩时只主张固定子集证据覆盖，不宣称所有问题全面优于 baseline。", "image": {"path": "D:/虚拟C盘/RAG/docs/challenge_cup/reproducibility/browser_screenshots/desktop_kg_artifacts.png", "x": 625, "y": 188, "w": 520, "h": 368, "fit": "contain"}, "bullets": [{"text": "GraphRAG 用于部件、故障、检查项和处理措施之间的关系解释。"}, {"text": "manual evidence supplement 已关闭 P0 missing 与 relation schema gap。"}, {"text": "可指向报告：evaluation/reports/challenge_cup_graphrag_same_question_report.md"}], "bulletY": 220, "bulletW": 500, "callout": {"x": 78, "y": 548, "w": 495, "h": 64, "text": "关键答法：GraphRAG 是关系证据组织能力，不是“所有题都一定赢”的口号。", "fill": "#EAF6EF", "line": "#B9DBC7"}};

export async function slide06(presentation, ctx) {
  const slide = presentation.slides.add();
  await renderSlide(slide, ctx, spec);
  return slide;
}
