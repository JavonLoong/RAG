import { renderSlide } from "./common.mjs";

const spec = {"number": 5, "kicker": "Scenario", "title": "固定应用场景：GT-07 燃气轮机异常振动诊断流程", "subtitle": "用真实浏览器烟测截图证明现场演示不是口头描述。", "image": {"path": "D:/虚拟C盘/RAG/docs/challenge_cup/reproducibility/browser_screenshots/desktop_search_results.png", "x": 612, "y": 196, "w": 520, "h": 360, "fit": "contain"}, "bullets": [{"text": "固定查询：燃气轮机异常振动诊断流程", "bold": true}, {"text": "浏览器可见记录数：5；集合 gas_turbine_ocr_demo_snapshot · 延迟 41.80 ms · 结果 5 · 后端 public-demo"}, {"text": "证据链覆盖阈值、叶片、滤网、传感器、检修和人工确认边界。"}, {"text": "高风险维修仍需人工确认；系统定位为证据型辅助。"}], "bulletY": 210, "bulletW": 480};

export async function slide05(presentation, ctx) {
  const slide = presentation.slides.add();
  await renderSlide(slide, ctx, spec);
  return slide;
}
