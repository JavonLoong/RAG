# 答辩彩排计分卡

本计分卡把现场答辩准备状态转成可复核的时间、证据和边界要求，用于正式答辩前的限时 rehearsal。

- Boundary: This scorecard proves rehearsal readiness and evidence anchors; it does not prove a live defense has already happened or guarantee an award.
- Status: `ready_for_timed_rehearsal`
- 90秒开场：覆盖 问题、方法、完成度、边界
- 三分钟演示节奏：180 秒内完成 5 个固定节点
- 离线兜底：现场异常时 20 秒内切换到离线证据；20 秒内切换必须完成
- 杀手问题：每题 30 秒内回答；30 秒内回答必须落到证据锚点

## 三分钟演示节奏

| 时间 | 焦点 | 通过条件 | 证据锚点 |
| --- | --- | --- | --- |
| 0:00-0:30 | 项目一页纸 | 问题、用户和交付物在半分钟内讲清。 | `docs/challenge_cup/00_项目一页纸.md` |
| 0:30-1:20 | 浏览器检索演示 | 展示真实可运行页面和检索证据，不停留在口头描述。 | `docs/challenge_cup/reproducibility/browser_demo_smoke_report.md` |
| 1:20-2:10 | GraphRAG 关系证据 | 讲清文本证据与图谱证据如何共同支撑同一问题。 | `evaluation/reports/challenge_cup_graphrag_context_demo.md` |
| 2:10-2:40 | readiness gate | 展示机器校验通过项，同时不把 readiness gate 说成获奖保证。 | `docs/challenge_cup/reproducibility/readiness_gate_report.md` |
| 2:40-3:00 | 边界与下一步 | 明确当前验证边界和后续扩展，不夸大生产级覆盖。 | `docs/challenge_cup/08_特等奖评审自评表.md` |

## 杀手问题

| 问题 | 30 秒回答框架 | 证据锚点 |
| --- | --- | --- |
| 这和普通 RAG 的本质差异是什么？ | 先承认普通 RAG 是强基线，再说明本项目多了可审计关系证据和同题对照。 | `docs/challenge_cup/03_实验评测报告.md`<br>`docs/challenge_cup/07_评审主张证据矩阵.md`<br>`evaluation/reports/challenge_cup_graphrag_same_question_report.md` |
| GraphRAG 是否一定全面优于 keyword 或 hybrid？ | 不做绝对化表述，只主张在需要关系解释和证据追踪的问题上有可展示优势。 | `docs/challenge_cup/03_实验评测报告.md`<br>`docs/challenge_cup/05_答辩问答手册.md`<br>`evaluation/reports/challenge_cup_graphrag_context_demo.md` |
| 当前数据规模是否足以支撑真实生产级运维？ | 把范围限定为教学科研验证集，强调已完成数据、索引、评测、演示闭环。 | `docs/challenge_cup/reproducibility/dataset_manifest.md`<br>`docs/challenge_cup/reproducibility/application_validation_report.md`<br>`docs/challenge_cup/08_特等奖评审自评表.md` |
| 如果现场服务、浏览器或网络出问题怎么办？ | 20 秒内切换到离线截图、smoke report 和固定演示脚本，避免现场阻塞。 | `docs/challenge_cup/04_系统演示脚本.md`<br>`docs/challenge_cup/reproducibility/browser_demo_smoke_report.md`<br>`docs/challenge_cup/reproducibility/runbook.md` |
| 为什么这个项目具备冲击特等奖的完整度？ | 用一页纸、证据矩阵和 readiness gate 串起创新性、工程性、可复现性与边界。 | `docs/challenge_cup/00_项目一页纸.md`<br>`docs/challenge_cup/reproducibility/readiness_gate_report.md`<br>`docs/challenge_cup/10_答辩攻防与彩排卡.md` |

## 不可夸大边界

- 不说已经替代工程师
- 不说 GraphRAG 对所有问题都更强
- 不说当前数据覆盖真实生产全场景
- 不把 readiness gate 说成获奖保证
- 不伪造专家反馈或现场彩排记录

## 证据文件

- `docs/challenge_cup/00_项目一页纸.md`
- `docs/challenge_cup/03_实验评测报告.md`
- `docs/challenge_cup/04_系统演示脚本.md`
- `docs/challenge_cup/05_答辩问答手册.md`
- `docs/challenge_cup/07_评审主张证据矩阵.md`
- `docs/challenge_cup/08_特等奖评审自评表.md`
- `docs/challenge_cup/10_答辩攻防与彩排卡.md`
- `docs/challenge_cup/reproducibility/browser_demo_smoke_report.md`
- `docs/challenge_cup/reproducibility/application_validation_report.md`
- `docs/challenge_cup/reproducibility/readiness_gate_report.md`
- `evaluation/reports/challenge_cup_graphrag_context_demo.md`
- `evaluation/reports/challenge_cup_graphrag_same_question_report.md`
