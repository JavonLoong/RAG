# FMEA 正文发布与三格式交付 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 从批准版本生成不可变的完整 FMEA 正文，并通过现有 JSON/XLSX/DOCX 链路交付可读且可核验的报告。

**Architecture:** 增加独立的正文安全投影组件，复用治理来源与发布事务。三个导出器消费同一已保存快照；Office 可读正文由绑定模板驱动，机器可验证的类型表保留。

**Tech Stack:** Python `>=3.11,<4.0`、现有 dataclass/SQLite、openpyxl `>=3.1.5,<4`、python-docx `>=1.2.0`、pytest。无需新增第三方依赖。

**Spec:** [正文发布设计](../specs/2026-09-04-fmea-publication-body-design.md)。同时遵循 [完整 FMEA 产品设计](../specs/2026-08-27-full-fmea-modular-product-design.md)。

**Status:** APPROVED / IMPLEMENTING。用户于 2026-09-04 确认，从 Task 1 开始。实现起点 `d1040fcf`（文档提交），代码基线 `9fca984e`，工作树 `C:/Users/35551/Desktop/RAG/.worktrees/interface-output-v1`，分支 `feat/interface-output-v1`。不切 main，不推送，不创建 PR。

**进度（2026-09-04）：Task 1 已完成；Task 2–5 未开始。** Task 1 提交 `75d1cb98` → `c4cdfc4b` → `7bd0c69b`。最终定向测试 100 passed（主代理复验 0.79s），范围 Ruff 与差异空白检查通过；Luna xhigh 规格/质量审查发现五项缺口，经 round 1 修正；其引入的两项兼容性回归经 round 2 关闭，PASS / CLOSED。该结论不表示真实发布与三格式正文报告已经接通。[Task 1 交接](../../handoff/fmea-publication-body-task1.md)。

## Global Constraints

- 新内容标记：`body_schema_version: "graphrag.fmea.body.v1"`；无标记的既有快照保持旧读取路径。
- 导出只读取已保存快照；已发布后当前行变化不改变报告。
- 模型建议不提升为人工确认、批准或发布权限。
- 不修改上游 RAG/GraphRAG 算法、EvidencePack 对外合同及领域评分规则。
- 复用现有安全限制：禁止凭证、私有路径、URL 获取、模板脚本执行；超限明确拒绝，不截断或解除限制。
- 燃料、电气、软件使用同一内核；不存在的值保持缺失/未知，不能按显示需求生成事实。
- 测试按风险定向覆盖；本轮文档不运行业务测试，实施时先 RED 后 GREEN，收尾只跑一次相关集合。
- 每 Task 独立实现与复审；Luna xhigh 是用户指定偏好，执行时先检查实际子智能体工具和模型可用性；不可用须说明，不能假称已委派或另建用户任务替代。

## 文件与职责

| 文件 | 变更及职责 |
| --- | --- |
| `fmea_application/publication_body.py`（新增） | 类型明确的正文、审核引用契约；源绑定、安全投影、稳定排序 |
| `fmea_application/governance_service.py` | 用单次输入构建正文；沿用授权、批准、幂等和发布门禁 |
| `fmea_application/governance_contracts.py` | 在 PreparedPublication 中携带提交核对所需的内部绑定数据，不增加公共请求信任面 |
| `fmea_infrastructure/composition.py` | 接入最小只读复核记录来源和固定模板视图 |
| `fmea_infrastructure/governance_repository_sqlite.py` | 事务内正文源校验、原子持久化与旧快照读取兼容 |
| `fmea_application/snapshot_contracts.py` | 新标记及正文结构验证，保留原冻结/安全/大小限制 |
| `fmea_application/report_view.py`（新增） | 从已保存正文与固定显示配置生成通用可读视图，不访问当前业务表 |
| `fmea_infrastructure/export_json.py` / `export_xlsx.py` / `export_docx.py` | 保留统一内容身份；Office 增加可读正文，不另算业务结论 |
| `scripts/verify_fmea_full_acceptance.py` | 独立核对正文与批准原生数据，不能导入生产投影函数 |
| `examples/fmea/full-acceptance/governance_delivery_slice.py` | 现有真实离线样例衔接，仅扩充必要正文证据 |

不提前新增 SQL migration。Task 2 若证明现有 JSON 存储不能承载内部绑定或历史读取，先提出具体迁移设计和影响，再批准扩大。

## Task 1：正文投影与版本绑定契约

**Files:** Create `fmea_application/publication_body.py`, `tests/unit/test_fmea_publication_body.py`; Modify `fmea_application/snapshot_contracts.py`, `fmea_infrastructure/composition.py`（仅运行时正文入口）, `fmea_application/ports.py`（可选只读 publication_reviews provider）; Test `tests/unit/test_fmea_snapshot_contracts.py`, `tests/unit/test_fmea_governance_source.py`; `tests/fmea_governance_fixtures.py` 仅按需添加测试专用 runtime source 与复核来源辅助。

**Interfaces:** 输入 `FmeaRevision`、`GovernanceInputs`；输出下列新类型。复核来源只能由服务端仓储解析，公开内容为白名单。

```python
@dataclass(frozen=True, slots=True)
class PublicationReviewRecord:
    decision_id: str
    workspace_id: str
    analysis_id: str
    row_id: str
    record_version: int
    row_hash: str
    public_fields: Mapping[str, object]

@dataclass(frozen=True, slots=True)
class PublicationBody:
    rows: tuple[Mapping[str, object], ...]
    risk_records: tuple[Mapping[str, object], ...]
    propagation: Mapping[str, object] | None
    evidence_summary: tuple[Mapping[str, object], ...]
    decision_summary: tuple[Mapping[str, object], ...]

```

实施核对及 Task 1 复审后采用运行时入口：`source.build_publication_body(revision: FmeaRevision, inputs: GovernanceInputs) -> PublicationBody`。基础 `RepositoryGovernanceSource` 拒绝未配置调用；`RuntimeGovernanceSource` 复用闭包内 HMAC verify，内部调用 `publication_reviews.load_publication_reviews(revision)` 后，将这些记录传给应用层内部 `_project_publication_body(..., review_records=records)`。`GovernanceRepositoryProviders.publication_reviews` 为可选配置；旧来源的其他功能兼容，但新正文入口缺少复核来源时拒绝。实现顺序为验证来源证明及范围、读取服务端复核、重算绑定、白名单投影、冻结排序。不得通过 proof 非空、调用方提供的复核记录或 verifier 回调声称可信。上述代码仅定义合同类型；下面断言是测试片段，不是可直接执行的完整测试文件。

- [x] 先增加最小定向测试：完整字段保留；稳定排序；扩展值类型；未知/不适用；错误行哈希/版本/范围；证据正文篡改；缺失或错版本审核；不安全路径/超限。复用 `tests/fmea_governance_fixtures.py` 的 `make_governance_inputs` 与 `make_governance_assembler`，通过真实 assembler 建立对应 revision，不能用随机 hash 凑绑定。
- [x] 为新标记增加明确的新/旧兼容断言：旧快照仍接受，新标记配摘要行拒绝。测试示例断言如下，`body`、`inputs` 由本 Task 的真实来源夹具提供。

```python
assert body.rows[0]["failure_mode"] == inputs.rows[0].failure_mode
assert body.rows[0]["record_version"] == inputs.rows[0].record_version
assert body.rows[0]["row_hash"].removeprefix("sha256:") == revision.row_versions[0][2].removeprefix("sha256:")
assert body.rows[0]["field_claims"]
assert body.evidence_summary[0]["pack_hash"]
```

- [x] 执行 `.venv/Scripts/python.exe -m pytest tests/unit/test_fmea_publication_body.py tests/unit/test_fmea_snapshot_contracts.py -q`；确认 RED 来自缺少正文行为。
- [x] 实现上述契约：显式投影原生字段；重算行/风险/图/证据身份并比对 revision；审核必须精确命中版本。安全过滤应拒绝不允许的值，不能悄悄删除必需证据后发布。
- [x] 执行同一测试命令到 GREEN；复核仅看正文绑定、类型和兼容性；显式暂存上述文件并本地提交 `feat(fmea): add version-bound publication body projection`。

## Task 2：真实发布接入与事务内核验

**Files:** Modify `fmea_application/governance_service.py`, `fmea_application/governance_contracts.py`, `fmea_infrastructure/governance_repository_sqlite.py`, `fmea_infrastructure/composition.py`; Create `tests/integration/test_fmea_publication_body.py`; Test `tests/regression/test_fmea_governance_atomic_publish.py`, `tests/regression/test_fmea_governance_idempotency.py`。

**Interfaces:** 消费 Task 1 的运行时 `source.build_publication_body` 及只读 `publication_reviews` port。实现 `load_publication_reviews(revision: FmeaRevision) -> tuple[PublicationReviewRecord, ...]` 的真实仓储适配并配置进运行时；不能由 HTTP/CLI 调用者提供。`PreparedPublication` 内部保存提交校验需要的源绑定，外部 PublishCommand 保持不变。

- [ ] 增加真实 SQLite 测试：批准后发布有正文；原始复核缺失会失败；准备正文后改源行会失败且无半发布；伪造正文并重算整个导出哈希链仍拒绝；故障注入回滚；重放返回同一快照；发布后改行不改变保存快照。
- [ ] 测试明确比较 publication/snapshot/manifest/eligibility/audit/outbox 写入前后状态，而非只断言抛异常。使用现有 atomic publish 的故障注入入口和治理 idempotency 夹具，不构造第二套提交器。
- [ ] 执行 `.venv/Scripts/python.exe -m pytest tests/integration/test_fmea_publication_body.py tests/regression/test_fmea_governance_atomic_publish.py tests/regression/test_fmea_governance_idempotency.py -q`，保存 RED。
- [ ] 将 `_snapshot()` 原摘要生成替换为单份输入的正文投影，批准摘要在已有 approval 对象上构建：

```python
inputs = self._inputs(revision.analysis_id, revision.workspace_id)
body = self._source.build_publication_body(revision, inputs)
# NormalizedSnapshotInput 使用 body 的五个部分；version_manifest 写入正文标记。
# 原有 publication_id、manifest_id、revision_hash、created_at 不改变生成规则。
```

- [ ] 同一事务内核对可变业务源；按固定内容身份验证独立来源；把正文与权威源核对后才能执行原写入序列。保留撤销检查和早期幂等回放。来源若无法保证版本一致性，报告具体缺口并暂停 Task，不将测试夹具当作生产保证。
- [ ] 同一命令 GREEN；独立复审并发窗口、伪造自洽哈希、错误映射和原子性；本地提交 `feat(fmea): publish immutable body with authoritative source checks`。

## Task 3：模板驱动的通用报告视图

**Files:** Create `fmea_application/report_view.py`, `tests/unit/test_fmea_report_view.py`; Modify `fmea_infrastructure/composition.py`, `fmea_application/governance_service.py`, `fmea_application/snapshot_contracts.py`, `fmea_infrastructure/governance_repository_sqlite.py`（仅固定显示配置接入及提交绑定校验，与 Task 2 串行整合）。

**Interfaces:** `build_report_view(snapshot: NormalizedFmeaSnapshot) -> FmeaReportView`。新类型 `FmeaReportView` 是冻结 dataclass：`columns: tuple[ReportColumn, ...]`、`rows: tuple[Mapping[str, object], ...]`、`details: tuple[Mapping[str, object], ...]`；`ReportColumn` 字段为 `field_key/label/value_type: str`。固定模板编译得到的显示配置保存于 `version_manifest.report_layout`，包含模板身份、column 的字段键/显示名/类型/取值路径，并纳入 snapshot_hash，导出时不读取最新模板。提交时将配置与批准 revision 的固定模板内容核对；有多个模板而无法确定显示布局时明确阻断，不任取最新一个。

- [ ] 增加定向测试：中文显示名但键不变；字段重排；多原因/长证据转详情；decimal 无损；非 RPN 评分不冒充 RPN；不认识的扩展保留；非法映射路径拒绝；模板升级不改变已发布视图；旧摘要快照只显示摘要。
- [ ] 执行 `.venv/Scripts/python.exe -m pytest tests/unit/test_fmea_report_view.py -q`，确认 RED。
- [ ] 实现白名单取值路径和稳定字段布局，沿用现有编译模板字段定义，不解析用户表达式。核心行为断言：

```python
view = build_report_view(snapshot)
assert {column.field_key for column in view.columns} >= {"failure_mode", "causes", "effects"}
assert view.rows[0]["failure_mode"] == snapshot.rows[0]["failure_mode"]
assert snapshot.snapshot_hash == original_snapshot_hash
```

- [ ] 执行同一命令 GREEN；复审模板身份、跨域字段无损和无隐式业务计算；本地提交 `feat(fmea): add template-driven report view`。

## Task 4：三格式正式正文交付

**Files:** Modify `fmea_infrastructure/export_json.py`, `fmea_infrastructure/export_xlsx.py`, `fmea_infrastructure/export_docx.py`, `tests/integration/test_fmea_export_consistency.py`, `tests/unit/test_fmea_export_xlsx.py`, `tests/unit/test_fmea_export_docx.py`, `tests/unit/test_fmea_export_json.py`。

**Interfaces:** 消费 Task 3 的 `build_report_view`；保持现有 exporter `render` 和 JSON `iter_chunks` 合同、内容身份和旧快照支持。

- [ ] 扩充既有三格式一致性测试：JSON 正文完整；XLSX 主表有实际中文/长文本，证据在明细；DOCX 阅读正文不只是一张 ID 类型表；独立解码保留全部 canonical 内容。新可读表不能干扰现有类型表识别。
- [ ] 执行 `.venv/Scripts/python.exe -m pytest tests/integration/test_fmea_export_consistency.py tests/unit/test_fmea_export_json.py tests/unit/test_fmea_export_xlsx.py tests/unit/test_fmea_export_docx.py -q`，确认 RED。
- [ ] 使用统一 report view 渲染正文；评分关联按 row ID/version，不按数组位置；保留原 manifest、类型表、草稿标记及公式注入/XML 安全处理。断言示例复用现有独立解析器：

```python
assert _without_format_identity(_parse_xlsx(xlsx_bytes)) == _without_format_identity(_semantic_json(snapshot))
assert _without_format_identity(_parse_docx(docx_bytes)) == _without_format_identity(_semantic_json(snapshot))
```

- [ ] 同一命令 GREEN。生成一份小型长文本报告，按执行时可用的 documents/spreadsheets 技能做版式检查；没有渲染能力时明确列为未验证，不能称正文可读性验收完成。
- [ ] 复核内容完整与排版；本地提交 `feat(fmea): deliver readable body in office exports`。

## Task 5：完整样例、独立反例与交接

**Files:** Modify `examples/fmea/full-acceptance/governance_delivery_slice.py`, `scripts/verify_fmea_full_acceptance.py`, `tests/integration/test_fmea_full_acceptance.py`, `tests/integration/test_fmea_cross_domain_acceptance.py`, `tests/regression/test_fmea_delivery_security.py`, `examples/fmea/full-acceptance/README.md`, `docs/handoff/full-fmea-product.md`。

**Interfaces:** 复用 `run_full_acceptance(output_root=tmp_path)` 和 `verify_acceptance_directory(artifact_dir)`，不另建 runner，其中 `tmp_path` 为 pytest 临时目录。若验收包需要区分旧摘要与新正文，显式版本化包合同并保留旧验证分支；新包必须要求正文标记，删除标记应失败。

- [ ] 新增独立篡改反例：改故障正文、quote、评分关联、审核版本；将快照和导出文件一起改并重算自洽哈希；删除正文标记。verifier 必须依据批准原生记录拒绝，而不是复用生产投影或信任 manifest 的 P0 数字。
- [ ] 执行 `.venv/Scripts/python.exe -m pytest tests/integration/test_fmea_full_acceptance.py tests/integration/test_fmea_cross_domain_acceptance.py tests/regression/test_fmea_delivery_security.py -q`，确认 RED。
- [ ] 扩充现有 fuel-combustion 完整服务样例与 verifier；电气/软件只做结构迁移证明，不称为完整工程验证。保持三种证据 profile 的 provenance 无损，不连接新检索器。
- [ ] 同一命令 GREEN；对前四 Task 的定向测试集合合并去重后运行一次。未改前端不跑浏览器全套；未改分页/分块/大小合同不重复万行压测。
- [ ] 运行最终真实 runner 与独立 verifier：

```powershell
.venv/Scripts/python.exe scripts/run_fmea_full_acceptance.py
.venv/Scripts/python.exe scripts/verify_fmea_full_acceptance.py --latest
git diff --check
```

- [ ] 检查实际返回目录中的 Word/Excel/JSON。交接记录正文覆盖字段、包 ID、测试证据、平台跳过、旧快照兼容及仍待真实资料验证的边界；不能预填通过数。
- [ ] 做范围整体复审，关闭阻断项；仅提交本轮拥有的文件，提交信息 `test(fmea): verify publication body delivery end to end`。未授权不 push/PR。

## 并行安排与复核

Task 1 → Task 2 是版本与事务主链。Task 1 契约通过复审后，Task 3 可在独立文件内与 Task 2 并行；`composition.py` 由主代理串行整合。Task 4 等待 Task 2/3，Task 5 最后整合。避免多个代理同时写治理服务、SQLite 仓储或同一导出器。

每 Task 两级检查：先核规格/权限/兼容，再查代码/错误/必要反例；只复核该 Task 差异。阶段收尾再做一次整体正文绑定复核。文档中的接口为拟新增合同，实施前先读取两份设计和当前分支，不把注释示例当可执行实现。

## 自检与执行门禁

- 范围：正文、模板视图、三格式、完整样例，未扩大上游检索或领域算法。
- 覆盖：版本冻结在 Task 1/2；真实审核与证据在 Task 1/2；跨域模板在 Task 3；报告在 Task 4；独立证明在 Task 5。
- 兼容：旧快照不回填，新标记不可降级绕过；三格式共享同一保存内容。
- 依赖：现有 Python/SQLite/Office 库；没有新服务或付费调用。
- 设计及任务拆解已确认；从 Task 1 开始，延续用户指定的 Luna xhigh 分工偏好。仅在测试及独立复审通过后勾选完成项。
