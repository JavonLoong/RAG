import { renderSlide } from "./common.mjs";

const spec = {"number": 9, "kicker": "External validation", "title": "专家反馈与彩排是最后硬证据：已准备采集，不伪造结果", "subtitle": "当前状态是 ready-to-send / ready-to-record，而不是已获得专家背书。", "cards": [{"x": 86, "y": 210, "w": 500, "h": 170, "title": "专家反馈", "body": "外发包、反馈表、归档类型和整改闭环已准备；收到真实签字、邮件、会议纪要或聊天记录后再更新。", "fill": "#EAF1FB"}, {"x": 674, "y": 210, "w": 500, "h": 170, "title": "真实彩排", "body": "90 秒开场、3 分钟演示、20 秒离线切换和杀手问题均有计分卡；真实计时完成前不宣称通过。", "fill": "#EAF6EF"}, {"x": 86, "y": 430, "w": 500, "h": 138, "title": "必须补的外部证据", "body": "至少 1 份外部/导师反馈原件 + 1 次真实计时彩排记录 + 现场问答遗漏清单。", "fill": "#FFF4DA"}, {"x": 674, "y": 430, "w": 500, "h": 138, "title": "补完后的动作", "body": "更新反馈闭环与彩排结果包，重新生成 package、submission archive 和 readiness gate。", "fill": "#FBEAEA", "color": "#B54747"}]};

export async function slide09(presentation, ctx) {
  const slide = presentation.slides.add();
  await renderSlide(slide, ctx, spec);
  return slide;
}
