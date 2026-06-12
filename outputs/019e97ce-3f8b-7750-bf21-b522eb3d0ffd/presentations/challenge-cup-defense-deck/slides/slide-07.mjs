import { renderSlide } from "./common.mjs";

const spec = {"number": 7, "kicker": "Submission readiness", "title": "结项提交不是散文件：已形成归档包、哈希和机器门禁", "subtitle": "readiness gate 已纳入材料、证据、归档和答辩门禁", "metrics": [{"value": "56", "label": "归档文件", "color": "#2457A6"}, {"value": "2355KB", "label": "zip 大小", "color": "#1499A5"}, {"value": "SHA256", "label": "完整性校验", "color": "#2F7D59"}, {"value": "README", "label": "评审入口", "color": "#B7791F"}], "metricY": 220, "bullets": [{"text": "package_manifest.json 记录证据文件、评测覆盖画像和归档清单。"}, {"text": "evidence_hashes.json 与 submission archive manifest 支撑复核。"}, {"text": "readiness gate 覆盖材料、评测、浏览器烟测、GraphRAG、答辩和归档。"}], "bulletY": 412, "bulletW": 980};

export async function slide07(presentation, ctx) {
  const slide = presentation.slides.add();
  await renderSlide(slide, ctx, spec);
  return slide;
}
