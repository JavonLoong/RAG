# PRD 验收候选材料

本目录只保存可复核、尚未签字的机器候选材料；验收器不会把这里的记录当作正式输入，也不会因为候选指标达标而自动放行。

## 当前候选

- `performance_candidate.json`：当前 Windows 主机、14 份合成资料、`hashing-384@1` 的性能演练。它不能替代指定参考设备、真实试点资料和固定生产 embedding provider。
- `large_file_candidate.json`：真实 60 MiB multipart 上传、后台任务、进度界面和浏览器响应的自动观察。它仍须由具名 UI 观察者复核截图与任务快照。
- `ocr_spotcheck_candidate.json`：清晰、低质量、表格、疑似两栏风险和图片页的五类原页候选。每页必须由人工核对；疑似两栏页尤其不得仅凭自动审计结论通过。
- `ocr_gold_candidate.jsonl`：五类原页的逐字金标准录入表。`gold_text`、实际 OCR 文本、关键字段和审核身份故意留空，防止机器冒充逐字人工标注。
- `retrieval_gold_candidate.jsonl`：10 个真实燃机问题的 Top-5 检索结果以及无答案、跨型号、冲突来源、版本回滚四类边界用例。相关证据 ID 只是关键词重合建议，必须逐题人工确认。
- `graph_gold_candidate.json`：240 条带原文、源文件、页码和块 ID 的关系审核包，其中 120 条列为金标准候选；`gold_relations` 保持空数组，须由图谱工程师和领域专家逐条转入。
- `fmea_expert_candidate.jsonl`：3 条已发布 FMEA 的逐字段证据包；专家结论仍为 `pending`，S/O/D/RPN 在没有批准评分策略时保持空值。
- `fmea_export_verification_candidate.json`：FMEA JSON/CSV/DOCX 回读、行数和血缘机器核对结果；交付负责人仍须核对呈现内容并签字。
- `e2e_signoff_candidate.json`：主闭环和恢复闭环 12 项操作清单。服务级自动演练不等于 UI 验收，只有两个不同角色在正式界面复现并签字后才可转正式。
- `candidate_index.json`：上述候选包的机器可读索引，不参与门禁判断。

## 转正式输入的规则

1. 责任人先打开 `evidence/` 中的原始记录与图片，核对来源、SHA-256、页面和结论。
2. 在候选副本中填写真实 `reviewer`、`reviewer_role`、`reviewed_at`、`decision` 和复核意见；禁止代签或使用虚构身份。
3. TECH-15 只有在指定参考设备、真实 14 份试点资料、固定 provider 上重跑后，才可保存为根目录 `performance.json`。
4. TECH-16 由具名观察者确认后，才可保存为根目录 `large_file.json`。
5. OCR 五类逐页通过后，只把已签字的 `spotchecks` 合并进根目录 `ocr_coverage.json`；若疑似两栏页不成立，应换用真实两栏页，不能强行通过。
6. OCR 金标准必须由审核人逐字录入；检索相关性、图谱金标准和 FMEA 专家结论必须由对应领域人员判断，禁止直接接受机器建议。
7. 图谱候选至少审核 100 条关系，并把接受的关系明确复制到 `gold_relations`；同题对比的每一题都要填写专家判断。
8. E2E 必须由两个不同具名角色只通过正式界面完成；自动化测试、API 演练或同一账号切换名称不能代替双方签字。
9. 通过验收工作台上传正式文件，保留 expected SHA 与 Idempotency-Key，再重建验收包。
