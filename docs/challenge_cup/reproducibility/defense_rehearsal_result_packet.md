# 答辩计时彩排结果归档包

本包用于记录一次真实计时彩排的用时、遗漏点和归档证据。当前状态是尚未记录真实计时彩排；不伪造现场彩排记录。

- Boundary: This packet prepares actual timed rehearsal recording; it does not claim a timed rehearsal has already been completed.
- Status: `ready_to_record_actual_rehearsal`
- actual_rehearsal_completed: `False`

## 通过阈值

- 90 秒开场：opening_actual_seconds <= 90
- 三分钟演示：demo_actual_seconds <= 180
- 离线兜底切换：offline_fallback_actual_seconds <= 20
- 杀手问题：每题 actual_seconds <= 30

## 待填写字段

- rehearsal_date
- recorder
- observer
- opening_actual_seconds
- demo_actual_seconds
- offline_fallback_actual_seconds
- killer_question_results
- archive_evidence_paths
- issue_list
- overall_result

## killer_question_results 模板

| # | Question | actual_seconds | missed_evidence_anchor | needs_revision |
| --- | --- | --- | --- | --- |
| 1 | 这和普通 RAG 的本质差异是什么？ | None | None | None |
| 2 | GraphRAG 是否一定全面优于 keyword 或 hybrid？ | None | None | None |
| 3 | 当前数据规模是否足以支撑真实生产级运维？ | None | None | None |
| 4 | 如果现场服务、浏览器或网络出问题怎么办？ | None | None | None |
| 5 | 为什么这个项目具备冲击特等奖的完整度？ | None | None | None |

## 归档证据类型

- 计时截图
- 彩排录屏
- 观察员签字或备注
- 问题遗漏清单

## 后续动作

- 填写所有 actual_seconds 字段并归档计时截图或录屏。
- 把每个超时项和遗漏证据锚点写入 issue_list。
- 更新 overall_result 为 pass 或 needs_revision。
- 重新运行 scripts/check_challenge_cup_readiness.py。

## 证据文件

- `docs/challenge_cup/04_系统演示脚本.md`
- `docs/challenge_cup/05_答辩问答手册.md`
- `docs/challenge_cup/08_特等奖评审自评表.md`
- `docs/challenge_cup/10_答辩攻防与彩排卡.md`
- `docs/challenge_cup/reproducibility/defense_rehearsal_scorecard.md`
- `docs/challenge_cup/reproducibility/readiness_gate_report.md`
