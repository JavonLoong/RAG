# PowerRAG PRD 正式验收补证指南

本目录的验收器只读取 `evaluation/prd_acceptance_current_inputs/` 中的正式证据。自动化测试、演示数据和模型自评不得替代人工金标准或角色签字。

自动化演练产生但尚未签字的材料统一放在 `evaluation/prd_acceptance_current_inputs/candidates/`。该目录不参与正式门禁判断；当前 12 个门禁均有可复核候选，覆盖 OCR、检索、图谱、FMEA、角色化 E2E、性能和 60 MB 上传，具体复核与转正式规则见 `candidates/README.md`。

## 必需文件与责任人

| 文件 | 最低要求 | 责任人 |
| --- | --- | --- |
| `ocr_coverage.json` | 5483/5483 页均有文本、结构或页面级明确阻断；包含 clear、low_quality、table、dual_column、image 五类逐页人工抽检 | 知识工程师、OCR 审核人 |
| `ocr_gold.jsonl` | 每行含 `id`、`category`、`gold_text`、`predicted_text`、`critical_fields`；清晰页和关键字段满足 PRD 阈值 | OCR 审核人 |
| `retrieval_gold.jsonl` | 不少于 10 个专家问题；每行含相关/召回 evidence_id、可解析引用和 `case_type`；覆盖 ordinary、no_answer、cross_model、source_conflict、version_rollback | 领域专家、知识工程师 |
| `graph_gold.json` | 不少于 100 条人工金标准关系、候选关系、已发布语句证据审计和同题集专家判断 | 图谱工程师、领域专家 |
| `fmea_expert.jsonl` | 每个 FMEA 项含字段、字段证据、专家结论 accepted/minor/major/rejected；未批准评分保持空值 | 领域专家 |
| `fmea_export_verification.json` | JSON/CSV/DOCX 行数与内容一致，`consistent=true`、`docx_verified=true`、`lineage_consistent=true` | 交付负责人 |
| `e2e_signoff.json` | 知识工程师和领域审核人两个不同角色，仅通过正式界面完成主闭环和恢复闭环，并写入签字与时间 | 两名试点角色 |
| `performance.json` | 约定 Windows 参考设备、14 本正式资料、固定嵌入模型下的检索/图路径/预览逐次耗时 | 测试负责人 |
| `large_file.json` | 至少 60 MB 实传；异步、进度可见、浏览器不卡死、请求不超时 | 测试负责人 |

字段样例和完整格式见 `tests/unit/test_prd_acceptance.py`。填写后运行：

## 正式控制台工作台

启动 PowerRAG 后端后，在控制台进入“验收工作台”。工作台通过 `/api/delivery/acceptance` 完成以下操作：

1. 实时读取 12 项门禁、责任角色、当前指标和开放工作项。
2. 按验收 ID 上传原页、截图、日志、导出文件等原始证据，服务器计算 SHA-256 并返回包内 `evidence_ref`。
3. 每个开放工作项可一键把对应候选载入正确的正式证据编辑器；界面同时保留“未签字”警告，候选不会自动保存或自动通过。
4. 载入九类责任文件模板，保存前检查 JSON/JSONL 类型；已有文件必须携带当前 SHA-256，防止多人覆盖。
5. 一键生成 `acceptance.json`、`acceptance.md`、`work_items.json`、`human_review_handoff.md` 和 `manifest.json`。其中交接包按责任角色汇总 12 项复核清单与签署栏；证据、审计日志和结构化输入均递归进入哈希清单。
6. 在工作台直接预览、复制或下载 `human_review_handoff.md`；下载接口只允许验收包白名单文件，并继续执行验收管理员权限校验。

OIDC 模式下只有 `acceptance-managers`、`admin`、`owner`（或 `POWER_RAG_ACCEPTANCE_GROUPS` 配置的组）可以操作；本地单机模式使用本机身份。上传文件限制为允许的审阅格式和 25 MB，60 MB 原始资料本身不需要复制到验收包，记录其任务 ID、源 SHA 和界面观察证据即可。

`ocr_coverage.json` 不能只填写 `blocked_pages` 数字或 `spotcheck_categories` 名称。每个阻断页必须在 `blocked_page_records` 中提供 `source_file`、`page_num`、`failure_code`、`reason`、`attempt_count`、`downstream_publish_blocked=true` 和 `evidence_refs`。每类人工抽检必须在 `spotchecks` 中提供具体页面、`decision=passed/accepted`、审核人、审核时间和原页证据引用；缺任一项都不会计入正式验收。证据引用必须是 `evaluation/prd_acceptance_current_inputs/` 内真实存在的相对路径，绝对路径、目录穿越和缺失文件都会被拒绝，并由最终 manifest 一并计算 SHA-256。

每次运行还会生成 `work_items.json`，按验收 ID 给出当前状态、责任角色、应提交的输入文件、具体缺口和当前指标；通过项自动从工作队列移除。`human_review_handoff.md` 从同一工作队列生成角色分工、候选文件导航、逐项勾选清单和空白签署记录，但不会替代正式结构化证据。

## 统一证据元数据

- `ocr_gold.jsonl`、`retrieval_gold.jsonl`、`fmea_expert.jsonl` 的每一行都必须包含 `reviewer`、`reviewed_at`、`evidence_ref`。
- `graph_gold.json`、`fmea_export_verification.json`、`performance.json`、`large_file.json` 必须包含 `review`，其中有 `reviewer`、`reviewed_at`、非空 `evidence_refs`；FMEA 导出还必须提供一致的 `json_rows`、`csv_rows`、`docx_rows` 和 `docx_verified=true`。
- `e2e_signoff.json` 必须由知识工程师和领域审核人两个不同角色共同签字，`signatures` 必须覆盖两人，并提供 `evidence_refs`。
- `performance.json` 的检索、图路径、预览各至少 3 次原始耗时；`large_file.json` 还必须提供真实后台 `task_id` 和 64 位 `source_sha256`。
- 所有 `evidence_ref(s)` 都必须指向当前验收输入目录内的真实文件。只写“已通过”、布尔值、截图路径字符串或分类名称，不构成可验收证据。

```powershell
$env:PYTHONPATH='.'
python scripts/run_prd_acceptance.py `
  --input-dir evaluation/prd_acceptance_current_inputs `
  --output-dir build/prd_acceptance_current
```

只有 `build/prd_acceptance_current/acceptance.json` 的 `overall_status` 为 `passed`，并且 `manifest.json` 中输入、递归证据与输出 SHA-256 完整，才可签署整份 PRD 完成。
