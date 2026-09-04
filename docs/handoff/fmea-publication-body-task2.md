# FMEA 正文发布：Task 2 交接

日期：2026-09-04。工作分支：`feat/interface-output-v1`。

## 状态

Task 2 已完成，代码至 `7d702fc6`。主代理最终定向验证通过，独立 Luna xhigh 规格/质量复审及两轮修复复核均已关闭，Spec ✅ / Quality Approved，无新增 Critical/Important。Task 3–5 未开始；未推送、未创建 PR。

代码提交：`1416b32c`（真实正文发布接入）、`7f6c6ecd`（测试文件更名）、`7d702fc6`（多行凭据排序与验收结构校验）。

## 本次实现

- 新发布使用运行时验证过的正文，保存行、评分、传播、证据、复核/批准摘要，并带正文版本标记；不再仅保存身份摘要。
- SQLite 从真实复核决定及绑定审计解析人工复核来源；内部凭据绑定决定、审核者及角色、事件、版本和 canonical 内容哈希，公开报告不携带这些私有身份。
- 提交时使用同一 `BEGIN IMMEDIATE` 事务连接重查原生分析、行、风险、图、证据与复核记录，并将正文与权威内容核对；不是只校验一套自洽的导出哈希。
- 来源不完整或过期拒绝新发布；失败回滚；新无正文标记提交不能冒充历史格式。已保存的旧快照及幂等回放保留读取路径。
- 正文过期/不完整返回不可重试的 409，不安全返回不可重试的 400，不再被归为临时存储故障。

## 实施调整及原因

1. 增加最小错误映射：原映射不认识正文错误，会回退为可重试 503。代价是新增错误码/状态映射，不改变请求格式。
2. 适配旧治理验收 runner/verifier：计划指定的四项原子文件交付测试直接调用它们；原内存样例没有新发布需要的真实 SQLite 审核、评分与传播记录。改为复用既有服务，不造审计、不绕过约束。代价是扩大验收兼容性审查面，不增加业务算法。
3. 私有审核凭据随正文进入提交准备：公开的决定/行/版本/哈希四元组不能固定完整审核身份。代价是内部 DTO 衔接，外部快照及接口不变。
4. 新集成测试命名为 `test_fmea_publication_body_sqlite.py`：与单元测试同名时，默认 pytest 合并收集会冲突。只更改测试路径，不更改全仓 pytest 模式或删除缓存。

## 验证记录

- 初始 RED：4 failed、6 passed；证明旧正文入口和错误映射缺失。
- 实现中真实 SQLite 发布与回放单项通过；旧内存验收来源导致过 4 项回归失败，随后适配至 17 passed。
- 第一轮生产复审发现审核身份绑定不完整、缺失审核测试使用假来源、缺少发布后源变更验证；另要求实际持久化旧快照回放证据。这四项已获独立复核关闭。
- `1416b32c` 实现者报告 Task 2 三文件 19 passed、正文/来源/治理契约三文件 97 passed，Ruff 通过。97 项不是 Task 1 之前的 100 项集合，不可直接比较数量或相加。
- 主代理合并收集发现上述文件同名冲突，已用 100% 内容不变的文件更名解决。
- 后续差异复核发现多行审核决定顺序不一致，以及旧验收验证器对新正文检查不足。第二轮先复现 1 项多行失败和 4 项结构反例失败，再修正统一排序与既有公开快照 schema/精确集合/关联检查；独立第二轮复核确认两项均已关闭，无新增 Critical/Important。

主代理在最终代码 `7d702fc6` 上运行：

```powershell
.venv/Scripts/python.exe -m pytest tests/unit/test_fmea_publication_body.py tests/unit/test_fmea_snapshot_contracts.py tests/unit/test_fmea_governance_source.py tests/unit/test_fmea_governance_contracts.py tests/integration/test_fmea_publication_body_sqlite.py tests/integration/test_fmea_governance_acceptance.py tests/regression/test_fmea_governance_atomic_publish.py tests/regression/test_fmea_governance_idempotency.py -q
```

结果：**165 passed in 28.61s**。全部 10 个本轮改动的代码/脚本/测试文件 Ruff 通过；`git diff 39a718af..HEAD --check` 通过。此前各阶段计数不累加，不代表全仓测试、浏览器或大型 Office 压测。

旧治理验收验证器增加的是正文结构、精确集合、版本与关联检查，并保持独立的文件/内容身份校验；不导入生产正文投影器或 runner。它不替代 Task 5 基于原生批准数据的完整三格式独立验证。

## 后续边界

Task 3 接入固定模板驱动的报告视图，布局须与批准版本绑定且纳入提交检查。Task 4 才接通易读的 Word/Excel 正文与版式验证；Task 5 扩充完整三格式验收和独立篡改验证器。本轮不能称三格式正式报告已经验收。

没有新增迁移、上游检索算法、评分/传播规则、模型权限、前端或外部付费调用。真实工程资料、外部 DeepSeek 与行业认证均未在本轮验证。

相关：[实施计划](../superpowers/plans/2026-09-04-fmea-publication-body.md)、[Task 1 交接](fmea-publication-body-task1.md)。
