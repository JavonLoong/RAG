# 挑战杯项目成果入口

生成时间：2026-06-05 21:06

本目录是“知燃知维：面向动力装备运维知识的可信 GraphRAG 系统”的结项与挑战杯评审入口。先看本页，再按顺序阅读项目一页纸、项目书、技术白皮书、实验评测报告、演示脚本和答辩问答手册。

## 评委三分钟速览

| 时间 | 看什么 | 证据入口 |
| --- | --- | --- |
| 0:00-0:30 | 项目定位：知燃知维 GraphRAG 面向动力装备运维知识，先确认问题、场景、贡献和边界。 | `00_项目一页纸.md`; `13_评委现场速览卡.md` |
| 0:30-1:30 | 证据链：从 60 题评测、GT-07 固定场景、GraphRAG 证据组织和失败整改看完成度。 | `03_实验评测报告.md`; `07_评审主张证据矩阵.md`; `reproducibility/readiness_gate_report.md` |
| 1:30-2:30 | 现场演示：按固定脚本看浏览器控制台、检索结果、KG 证据和离线兜底。 | `04_系统演示脚本.md`; `defense_console/index.html`; `reproducibility/browser_demo_smoke_report.md` |
| 2:30-3:00 | 边界与缺口：包可复核，但真实专家反馈和真实计时彩排尚未归档，不能标记目标完成。 | `reproducibility/goal_completion_report.md`; `reproducibility/external_evidence_execution_kit.md` |

## 当前硬证据状态

- 状态：`package_ready_awaiting_external_hard_evidence`。
- 真实专家反馈尚未归档；真实计时彩排尚未归档；不能标记目标完成。
- 外部硬证据补齐入口：`reproducibility/external_evidence_execution_kit.md`。

## 推荐阅读顺序

1. `00_项目一页纸.md`
2. `01_挑战杯项目书.md`
3. `02_技术白皮书.md`
4. `03_实验评测报告.md`
5. `04_系统演示脚本.md`
6. `05_答辩问答手册.md`
7. `06_结项验收清单.md`
8. `07_评审主张证据矩阵.md`
9. `08_特等奖评审自评表.md`
10. `09_专家快速审阅索引.md`
11. `10_答辩攻防与彩排卡.md`
12. `11_应用场景与专家验证.md`
13. `12_专家反馈采集与整改闭环.md`
14. `13_评委现场速览卡.md`
15. `14_现场答辩操作Runbook.md`
16. `15_结项交付移交清单.md`
17. `16_现场问辩记录与整改台账.md`
18. `17_评审风险控制与应急预案.md`
19. `18_特等奖打分模拟与整改清单.md`
20. `19_作品展墙报问辩与展台脚本.md`
21. `20_成果转化与持续迭代路线图.md`
22. `21_知识产权与开源合规说明.md`
23. `22_同类方案对比与创新性证据卡.md`
24. `23_终审提交总目录与签收页.md`
25. `poster/challenge_cup_a0_poster.html`
26. `defense_console/index.html`
27. `defense_deck/challenge_cup_defense_deck.pptx`
28. `defense_deck/challenge_cup_defense_speaker_notes.md`
29. `reproducibility/application_validation_report.md`
30. `reproducibility/application_value_quantification.md`
31. `reproducibility/numeric_traceability_report.md`
32. `reproducibility/no_answer_boundary_evaluation.md`
33. `reproducibility/claim_integrity_report.md`
34. `reproducibility/runtime_reproducibility_snapshot.md`
35. `reproducibility/verification_transcript.md`
36. `reproducibility/rubric_defense_coverage.md`
37. `reproducibility/defense_slide_traceability.md`
38. `evaluation/reports/challenge_cup_failure_remediation_before_after.md`
39. `reproducibility/expert_feedback_form.md`
40. `reproducibility/runbook.md`
41. `reproducibility/dataset_manifest.md`
42. `reproducibility/readiness_gate_report.md`
43. `reproducibility/goal_completion_report.md`
44. `reproducibility/defense_rehearsal_scorecard.md`
45. `reproducibility/defense_rehearsal_result_packet.md`
46. `reproducibility/expert_feedback_request_packet.md`
47. `reproducibility/expert_feedback_outreach_ledger.md`
48. `reproducibility/timed_rehearsal_schedule_ledger.md`
49. `reproducibility/official_rubric_alignment.md`
50. `reproducibility/judge_objection_response_matrix.md`
51. `reproducibility/special_prize_readiness_dashboard.md`
52. `reproducibility/hard_evidence_closure_board.md`
53. `reproducibility/hard_evidence_action_pack.md`
54. `reproducibility/external_evidence_execution_kit.md`
55. `reproducibility/hard_evidence_ledger.md`
56. `reproducibility/challenge_cup_submission_archive_manifest.json`
57. `reproducibility/challenge_cup_submission_package.zip`
58. `reproducibility/verify_submission_package.py`
59. `reproducibility/final_acceptance_audit.md`
60. `reproducibility/submission_integrity_card.md`

## 当前核心数字

- 普通 RAG 数据库：9080 个 chunk。
- 系统评测集：60 题。
- 知识图谱 POC：27 条候选三元组，26 条正确，1 条待讨论，0 条明确错误。
- 已有课程交付包：PPT、讲稿、评测说明、失败分析、演示脚本、备用证据包和答辩口径。
