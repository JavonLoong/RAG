# 官方评审口径对齐表

本表把清华“挑战杯”公开报道和制度文件中的评审口径转化为本项目的可核验证据路线。它不承诺获奖，只用于倒逼材料、演示和边界表达贴近官方尺度。

- report_type: `challenge_cup_official_rubric_alignment`
- checked_at: `2026-06-06`
- official_source_count: `5`
- 第44届（2026）主赛道公开结果：特等奖7项；历史制度口径可能变化；本项目不承诺获奖。

## 官方来源

### tsinghua_44th_2026
- Title: 清华大学第44届“挑战杯”学生课外学术科技作品竞赛颁奖仪式暨作品展开幕式举行
- URL: https://www.tsinghua.edu.cn/info/1177/125861.htm
- Checked at: 2026-06-06
- Claim: 2026年4月25日开展终审答辩
- Claim: 主赛道共产生114项获奖作品，其中特等奖7项
- Claim: 本届挑战杯共收到报名作品337件
- Claim: 200余件学生科创作品参展

### tsinghua_43rd_2025
- Title: 清华大学第43届“挑战杯”学生课外学术科技作品竞赛颁奖仪式暨作品展开幕式
- URL: https://www.tsinghua.edu.cn/info/1176/118626.htm
- Checked at: 2026-06-06
- Claim: 2025年4月10日开展终审答辩
- Claim: 主赛道特等奖6项
- Claim: 清华挑战杯是学校历史最长、规模最大、水平最高的综合性学生课外学术科技作品竞赛
- Claim: 鼓励立足重要领域的关键应用场景，做勇于创新、善于创新的清华青年

### tsinghua_39th_2021
- Title: 清华大学第39届“挑战杯”学生课外学术科技作品竞赛校级终审落幕
- URL: https://www.tsinghua.edu.cn/info/1175/82720.htm
- Checked at: 2026-06-06
- Claim: 评分维度包括学术/实用价值、创新性、作品完成度、现场答辩及墙报问辩表现
- Claim: 每个分场至多推荐一项作品参加特等奖评比
- Claim: 本届最终评选出特等奖6项

### tsinghua_37th_2019
- Title: 清华大学第37届“挑战杯”学生课外学术科技作品竞赛校级终审落幕
- URL: https://www.tsinghua.edu.cn/info/1181/35383.htm
- Checked at: 2026-06-06
- Claim: 强调遵守比赛规则、恪守学术规范和学术成果表述严谨性
- Claim: 评委从学术价值或实用性、创新性、作品完成情况和现场答辩表现四个方面评分
- Claim: 特等奖候选作品参与公开答辩并由评委综合评定

### tsinghua_rules_pdf_2017
- Title: 清华大学课外创新人才培养体系制度文件汇编
- URL: https://qiyuan.tsinghua.edu.cn/intro/2018/11024/%E6%94%AF%E6%92%91%E6%9D%90%E6%96%993-%E6%B8%85%E5%8D%8E%E5%A4%A7%E5%AD%A6%E8%AF%BE%E5%A4%96%E5%88%9B%E6%96%B0%E4%BA%BA%E6%89%8D%E5%9F%B9%E5%85%BB%E4%BD%93%E7%B3%BB%E5%88%B6%E5%BA%A6%E6%96%87%E4%BB%B6%E6%B1%87%E7%BC%96.pdf
- Checked at: 2026-06-06
- Claim: 评审应考虑作品实用性、创新性和学术价值
- Claim: 特等奖不超过6件，可空缺
- Claim: 竞赛规程由清华相关部门和学生科协共同发布

## 维度对齐

| 官方维度 | 项目主张 | 证据文件 |
| --- | --- | --- |
| 学术/实用价值 | 面向动力装备运维资料知识化，用固定 GT-07 场景证明证据链整理价值。 | `docs/challenge_cup/00_项目一页纸.md`<br>`docs/challenge_cup/03_实验评测报告.md`<br>`docs/challenge_cup/11_应用场景与专家验证.md`<br>`docs/challenge_cup/reproducibility/application_validation_report.md`<br>`docs/challenge_cup/reproducibility/browser_demo_smoke_report.json` |
| 创新性 | 不是普通 RAG 页面，而是 evidence-bound GraphRAG、人工补证和失败归因闭环。 | `docs/challenge_cup/02_技术白皮书.md`<br>`docs/challenge_cup/07_评审主张证据矩阵.md`<br>`evaluation/reports/challenge_cup_graphrag_same_question_report.md`<br>`evaluation/reports/challenge_cup_graphrag_context_demo.md`<br>`evaluation/reports/challenge_cup_graphrag_answer_benchmark.md` |
| 作品完成度 | 已形成项目书、实验评测、浏览器演示、答辩材料、归档包和机器门禁。 | `docs/challenge_cup/package_manifest.json`<br>`docs/challenge_cup/reproducibility/readiness_gate_report.md`<br>`docs/challenge_cup/reproducibility/challenge_cup_submission_package.zip`<br>`docs/challenge_cup/reproducibility/challenge_cup_submission_archive_manifest.json`<br>`docs/challenge_cup/reproducibility/runbook.md` |
| 现场答辩 | 用 10 页终审 deck、讲稿、彩排计分卡和硬证据台账支撑现场表达。 | `docs/challenge_cup/defense_deck/challenge_cup_defense_deck.pptx`<br>`docs/challenge_cup/defense_deck/challenge_cup_defense_speaker_notes.md`<br>`docs/challenge_cup/reproducibility/defense_rehearsal_scorecard.md`<br>`docs/challenge_cup/reproducibility/defense_rehearsal_result_packet.md`<br>`docs/challenge_cup/reproducibility/hard_evidence_ledger.md` |
| 学术规范与严谨表述 | 所有高水平主张绑定证据和边界，不把 readiness gate、内部自评或准备包说成获奖保证/外部背书。 | `docs/challenge_cup/05_答辩问答手册.md`<br>`docs/challenge_cup/08_特等奖评审自评表.md`<br>`docs/challenge_cup/reproducibility/expert_feedback_request_packet.md`<br>`docs/challenge_cup/reproducibility/hard_evidence_ledger.json` |

## 诚信边界

- 不承诺获奖，不把 readiness gate 说成获奖保证。
- 不伪造外部验证，不把内部自评写成专家背书。
- 未归档真实专家反馈和真实计时彩排前，必须在答辩中主动说明。
