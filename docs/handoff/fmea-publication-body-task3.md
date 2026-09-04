# FMEA 正文发布：Task 3 模板报告视图交接

日期：2026-09-04。分支：`feat/interface-output-v1`。

状态：**Task 3 已完成。** 独立 Luna xhigh 复审结论为规格 PASS、质量 Approved，无 Critical/Important/Minor；报告视图自定义列序限制见下文，不代表 Task 4/5 完成。

## 本次实现

1. 新增 `build_report_view(snapshot)`：从已保存的规范化快照生成列、行和详情，不读取当前业务表或最新模板。
2. 发布时把模板身份、字段键、显示名、类型、取值路径和固定列序写入 `version_manifest.report_layout`，纳入快照哈希。
3. 私有发布绑定保留全部批准模板的规范化内容。SQLite 提交事务中重新编译、核对完整身份集合、重新选择模板，再比较布局。只改布局后重算导出层哈希不能通过。
4. 燃料领域同时包含 FMEA 和传播模板：只选择唯一直接声明 `failure_mode`、`effects` 的行模板；没有候选、多个候选或漏传模板都拒绝，不按名称/首位/最新版猜选。
5. 中文显示名来自模板 `title`，canonical 字段键保持不变；缺失核心列使用原生字段与稳定键名。扩展字段、decimal 字符串、未知状态、原文证据、风险和审核详情保留，不重新计算风险或补写事实。
6. 旧摘要快照只显示摘要；Task 2 已保存但未带 layout 的正文快照使用稳定键名。两者均不改历史字节或哈希；新发布必须带经过模板内容核验的布局。

## 接口及接力

- `FmeaReportView.columns`：冻结的 `ReportColumn(field_key, label, value_type)`。
- `rows`：用于显示的字段值映射。
- `details`：逐行原始正文、风险、证据、审核与传播。`details[i]["row"]` 保存完整原始行，避免与详情区名字冲突时丢失未知字段。
- `select_report_template` 核对全部模板的身份/哈希与唯一候选；`compile_report_layout` 只生成声明式显示配置。运行时和提交端还必须调用现有模板编译器，不能仅靠辅助函数声称来源可信。
- 模板规范化内容只在内部 `PublicationSourceBinding` 携带，不进入公开快照、HTTP 请求或 Office 导出。没有 SQL migration，也没有新服务、付费模型调用。

Task 4 用该视图增加 Word/Excel 阅读正文，保留现有机器可解码类型表。详情中的全局证据与传播引用应按身份去重展示，不能每行重复打印整份证据库。评分关联仍按原生行 ID/版本，不按风险数组位置。

## 当前限制

- 新模板布局当前按 canonical 字段键稳定排序。现有通用编译器拒绝 `x-report-order`，本次没有修改它；不能声称支持任意人工配置列序。读取视图会遵守已保存布局的序列。
- 无映射的非原生字段保持不可用，不把 `item` 猜成 `item_id`，不根据显示名生成含义。
- 模板选择要求直接声明核心字段；其他结构需要后续显式选择合同，不会自动猜测。
- 旧治理验收器验证布局结构及批准模板身份，不是完整原生模板内容重建器。完整三格式独立证明仍在 Task 5。
- 本次没有验证 Word/Excel 排版，没有新增检索器或改动评分/传播算法，也没有进行真实工程安全认证。

## 已取得的验证证据

代码提交：

- `3579f295`：通用报告视图。
- `71327562`：完整批准模板集合与唯一候选选择。
- `4277b31d`：旧精简模板的核心列保留。
- `f595fcb0`：真实发布、事务模板绑定和旧治理验收接入。

主代理在 `f595fcb0` 上执行：

```powershell
.venv/Scripts/python.exe -m pytest tests/unit/test_fmea_report_view.py tests/unit/test_fmea_publication_body.py tests/unit/test_fmea_snapshot_contracts.py tests/unit/test_fmea_governance_source.py tests/unit/test_fmea_governance_contracts.py tests/integration/test_fmea_publication_body_sqlite.py tests/integration/test_fmea_governance_acceptance.py tests/regression/test_fmea_governance_atomic_publish.py tests/regression/test_fmea_governance_idempotency.py -q --tb=short -k 'not ten_thousand'
```

结果：**216 passed，1 deselected，31.53s**。未重复未改动的万行规模测试。12 个改动的生产/脚本/测试文件 Ruff 通过。

关键反例覆盖：改显示名、改列序、删除布局、删除/伪造/非规范化选中模板内容、删除/伪造完整模板来源集合；拒绝后检查发布相关表没有半提交。另有字段/证据无损、旧历史重放、发布后模板不可读仍能读取保存视图的验证。

测试先失败后实现：提交篡改组最初 6 failed，随后通过；旧治理样例的多模板和版本清单兼容问题均通过真实失败定位后修正。纯视图细节与单项证据见同任务执行记录。

## 复审结论与尚待完成

- Task 3 独立复审通过，未发现阻断项。不能从本范围验证的 Office 排版/三格式原生数据证明已明确归入下两项。
- Task 4：Word/Excel 可读正文和实际版式检查。
- Task 5：三格式完整验收、原生数据独立反例和整体交接。

本次仅本地提交，未推送、未创建 PR。
