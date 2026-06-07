# 现场答辩操作Runbook

本 Runbook 面向答辩当天的操作者、主讲人和计时观察员。它不声明已经完成真实计时彩排，也不声明已经获得真实专家反馈；它只规定现场如何稳定地展示已经归档的材料、何时切换离线证据、以及追问时打开哪个证据锚点。

## Preflight

| 时间点 | 负责人 | 动作 | 验收口径 |
| --- | --- | --- | --- |
| 答辩前 30 分钟 | 操作者 | 打开 `docs/challenge_cup/13_评委现场速览卡.md`、`docs/challenge_cup/09_专家快速审阅索引.md`、`docs/challenge_cup/reproducibility/final_acceptance_audit.md`。 | 三个留存入口均可打开。 |
| 答辩前 20 分钟 | 操作者 | 打开 `docs/challenge_cup/reproducibility/browser_demo_smoke_report.md` 和 `docs/challenge_cup/reproducibility/browser_screenshots/desktop_search_results.png`。 | 离线证据可在 20 秒内展示。 |
| 答辩前 15 分钟 | 主讲人 | 复读 `docs/challenge_cup/04_系统演示脚本.md` 的 GT-07 固定场景。 | 能说出五个 record id 和人工确认边界。 |
| 答辩前 10 分钟 | 计时观察员 | 打开 `docs/challenge_cup/10_答辩攻防与彩排卡.md`。 | 90 秒开场、3 分钟演示、20 秒离线切换、30 秒追问回答规则清楚。 |

## 标签页顺序

1. `docs/challenge_cup/13_评委现场速览卡.md`
2. `docs/challenge_cup/00_项目一页纸.md`
3. `docs/challenge_cup/07_评审主张证据矩阵.md`
4. `docs/challenge_cup/reproducibility/application_validation_report.md`
5. `docs/challenge_cup/reproducibility/browser_demo_smoke_report.md`
6. `docs/challenge_cup/reproducibility/browser_screenshots/desktop_search_results.png`
7. `docs/challenge_cup/reproducibility/special_prize_readiness_dashboard.md`
8. `docs/challenge_cup/reproducibility/readiness_gate_report.md`
9. `docs/challenge_cup/reproducibility/final_acceptance_audit.md`
10. `docs/challenge_cup/reproducibility/goal_completion_report.md`

## 离线切换触发条件

| 触发条件 | 最大等待 | 切换动作 | 说明 |
| --- | ---: | --- | --- |
| 浏览器服务打不开 | 20 秒 | 打开 `docs/challenge_cup/reproducibility/browser_demo_smoke_report.md`。 | 不在现场排查环境。 |
| 搜索结果未出现 | 20 秒 | 打开 `docs/challenge_cup/reproducibility/browser_screenshots/desktop_search_results.png`。 | 用已归档截图继续说明 GT-07 五段证据链。 |
| KG artifact 无法打开 | 20 秒 | 打开 `docs/challenge_cup/07_评审主张证据矩阵.md`。 | 用矩阵说明 GraphRAG 证据组织价值。 |
| 评委要求复核包完整性 | 30 秒 | 打开 `docs/challenge_cup/reproducibility/readiness_gate_report.md` 和 `docs/challenge_cup/reproducibility/verify_submission_package.py`。 | 只解释门禁范围，不把门禁说成获奖保证。 |

## Q&A 证据映射

| 追问 | 先答一句 | 立即打开 |
| --- | --- | --- |
| 为什么不是普通 RAG？ | 普通 RAG 做片段召回，本项目还做 evidence-bound GraphRAG、失败归因和人工补证闭环。 | `docs/challenge_cup/02_技术白皮书.md`; `evaluation/reports/challenge_cup_graphrag_same_question_report.md` |
| 固定场景证据在哪里？ | GT-07 场景有阈值、机理、现象、检修、建议五段证据链。 | `docs/challenge_cup/reproducibility/application_validation_report.md`; `docs/challenge_cup/reproducibility/browser_demo_smoke_report.json` |
| 如何证明材料完整？ | 先看 package manifest、hash、zip manifest，再看 65 项 readiness gate。 | `docs/challenge_cup/package_manifest.json`; `docs/challenge_cup/reproducibility/readiness_gate_report.md` |
| 是否已经有专家认可？ | 还没有归档真实专家反馈；当前只有外发包、采集表和硬证据行动包。 | `docs/challenge_cup/reproducibility/goal_completion_report.md`; `docs/challenge_cup/reproducibility/hard_evidence_action_pack.md` |
| 是否已经完成彩排？ | 还没有归档真实计时彩排；当前只有计分卡、结果包模板和操作 Runbook。 | `docs/challenge_cup/10_答辩攻防与彩排卡.md`; `docs/challenge_cup/reproducibility/defense_rehearsal_result_packet.md` |

## 留存材料

- 递交给评委的第一份文件：`docs/challenge_cup/13_评委现场速览卡.md`。
- 评委想快速审阅时：`docs/challenge_cup/09_专家快速审阅索引.md`。
- 评委想看特等奖维度时：`docs/challenge_cup/reproducibility/special_prize_readiness_dashboard.md`。
- 评委想看结项状态时：`docs/challenge_cup/reproducibility/final_acceptance_audit.md`。
- 评委想看未完成边界时：`docs/challenge_cup/reproducibility/goal_completion_report.md`。

## 禁止现场调试

- 不在评委面前安装依赖、改代码、改端口或现场修复服务。
- 不把临时打不开解释成项目不可复现；直接切到已归档 smoke 报告、截图和 zip verifier。
- 不口头声称真实专家反馈或真实计时彩排已经完成；只有硬证据归档后才能改变这个口径。
- 不把 readiness gate 说成获奖保证；它只证明结项包和演示证据可复核。
