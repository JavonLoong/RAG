# GraphRAG FMEA 系统设计规格

**状态：** 已确认设计，待实施计划

**日期：** 2026-08-23

**接口契约标识：** `graphrag.fmea.v1`

**首批领域：** 燃烧系统、燃料系统及二者之间的故障传播

**方法边界：** 基于 IEC 60812:2018 的项目化裁剪，不宣称认证、监管批准或安全放行

## 1. 目标

在现有 GraphRAG 项目上建立一个可审计、可导出、可调用的 FMEA 子系统，把资料库和图谱中的工程信息转换为：

- 两份相互独立但可关联的系统 FMEA：燃烧系统 FMEA、燃料系统 FMEA；
- 字段级可追溯的证据引用；
- 显式的未知、证据不足和多来源冲突；
- 可审核、可修改、可拒绝、可批准、可撤回的版本化成果；
- 燃料系统到燃烧系统以及反向影响的跨系统传播关系；
- 稳定的 REST、JSON CLI、Codex Skill 和浏览器工作台；
- 基于同一不可变快照生成的 JSON、XLSX 和 Word 输出。

系统自动化的目标是生成高质量 FMEA 候选并辅助人工裁决，不是替代工程师的最终 S/O/D 判断、安全放行和责任签字。

## 2. 设计原则

1. **FMEA 是独立领域，不是查询模式。** 不新增 `QueryMode.FMEA`，不把审核、评分和发布状态塞入 `graphrag.query.v1`。
2. **GraphRAG 只提供只读证据。** FMEA 通过 `EvidenceProvider` 适配查询、图谱和文档证据，不向通用 GraphStore 写入 FMEA 关系。
3. **主张与证据分离。** 模型建议不是证据；检索相似度也不是真实性评分。
4. **证据、审核和发布状态分离。** `known` 不代表已审核，`accepted` 不代表已发布，`published` 不代表已认证。
5. **未知优于编造。** 没有足够证据时输出 `unknown` 或 `insufficient_evidence`；冲突不得静默选边。
6. **人类是批准和发布的最终主体。** 模型身份在存储层没有批准和发布权限。
7. **版本组合可重放。** 数据、图谱、EvidencePack、模板、评分包、提示词、模型和输出 schema 都进入运行清单。
8. **规范语义核心稳定。** Excel 列名、浏览器布局和报告格式只是映射，不是事实模型。
9. **内核完整、产品分阶段。** 跨系统传播和模板扩展从首版进入数据内核；复杂图编辑器、任意插件和低代码画布后置。
10. **开源借鉴必须可追溯。** 在明确项目许可证和第三方许可证兼容性前，只借鉴思路，不直接复制代码。

## 3. 范围与非目标

### 3.1 首个完整闭环

- 创建本地项目并选择 workspace、资料版本、图谱版本、领域 Profile、模板和评分包；
- 定义分析范围、系统边界、设备构型、燃料类型和操作工况；
- 生成燃烧系统与燃料系统的结构、功能和 FMEA 候选；
- 为字段和传播边绑定 EvidencePack 中的稳定证据；
- 进行确定性校验、模型批判和一次有界修复；
- 在浏览器中逐字段审核、编辑、拒绝、确认和解决冲突；
- 审核跨系统传播边和公共原因；
- 由真实人工账号批准并发布不可变 revision；
- 从同一发布快照生成 JSON 和 XLSX，随后补充 Word；
- 通过 CLI 和 Codex Skill 重放生成、查询状态、比较版本和发起导出。

### 3.2 明确不做

- 不宣称 IEC、AIAG/VDA、监管或安全认证；
- 不自动签署最终安全结论；
- 不让 LLM 自动批准、发布、撤回或改变评分规则；
- 不让请求端传入任意数据库路径、模型地址或 API Key；
- 不在模板中执行任意 JavaScript、网络请求、循环或跨库查询；
- 不在首版提供用户上传并执行的服务端插件；
- 不把 20 条内部夹具宣传为工业金标或真实设备认证样本；
- 不把产品扩展成通用 QMS、工单或低代码平台。

## 4. 总体架构

```text
文档库 / Chroma / GraphStore / GraphRAG
                  │
                  │ read-only
                  ▼
          EvidenceProvider Adapter
                  │
                  ▼
       Immutable EvidencePack Snapshot
                  │
                  ▼
┌──────────────── FMEA Application ────────────────┐
│ Domain + Policies + Deterministic Validators     │
│ Candidate Pipeline + Review + Publication        │
│ Template/Profile/Scoring + Propagation            │
│ Audit + Export + Issue Feedback                    │
└──────────────────────┬────────────────────────────┘
                       │
             FMEA SQLite + migrations
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
      REST          JSON CLI       Browser UI
                        │
                        ▼
                    Codex Skill
```

### 4.1 推荐代码边界

沿用仓库已有 `core_domain` 结构，同时避免污染查询契约：

```text
core_domain/fmea/
  contracts.py
  entities.py
  value_objects.py
  states.py
  scoring.py
  propagation.py
  evidence.py
  policies.py

fmea_application/
  services.py
  commands.py
  queries.py
  validators.py
  candidate_pipeline.py
  review_service.py
  publication_service.py
  export_service.py

fmea_infrastructure/
  evidence_provider.py
  repository_sqlite.py
  migrations/
  llm_gateway.py
  exporters/
  templates/

api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/
  routes_fmea_v1.py

scripts/
  fmea_skill.py

frontend_app/current_console/
  fmea.html
  fmea/
```

`graphrag.fmea.v1` 是接口 schema 标识，不要求创建可能与外部库冲突的 Python 顶级 `graphrag` 包。

### 4.2 与现有代码的接缝

- `WorkspaceRegistry`：增加 FMEA DB、模板目录、夹具目录和允许的模型配置引用；所有路径由服务端解析并受 `allowed_root` 约束。
- `QueryService`：通过只读适配器提供批量证据快照，不被继承，也不加入 FMEA 状态。
- `engine_bridge.py`：继续负责连接现有检索器、GraphStore 和模型适配器。
- `GraphStore`：只读检索，不复用其 SQLite 文件和初始化逻辑。
- `OperationLogger`：记录运行 trace；FMEA 自建领域审计表，二者职责不同。
- `api.py`：只负责依赖组装和路由注册，不承载 FMEA 业务逻辑。
- `scripts/query_skill.py`：只复用 stdout 单 JSON、stderr 日志和稳定退出码约定；FMEA 使用独立 CLI。

## 5. 规范语义模型

### 5.1 分析上下文

`FmeaAnalysis` 至少包含：

- `analysis_id`、`project_id`、`analysis_type`；
- 生命周期阶段、范围、系统边界、排除项；
- 设备构型、控制软件版本、燃料类型；
- 操作模式：启动、点火、升负荷、稳态、低负荷、燃料切换、停机；
- 假设、限制、未分析部分；
- 系统版本、资料版本、图谱版本；
- Profile、模板、评分包和风险规则版本；
- 负责人、审核人、批准人和时间；
- 父 revision 和当前 revision。

### 5.2 核心实体

- `Item`：系统、子系统、组件和部件；
- `Function`：输入、输出、接口、性能要求、允许偏差和适用工况；
- `Interface`：跨边界变量、单位、方向和约束；
- `FailureMode`：功能或部件如何失效；
- `Deviation`：过高、过低、丢失、漂移、间歇、错误时序、泄漏、堵塞等偏差；
- `Cause`：触发或促成因素；
- `Mechanism`：物理、化学、软件或人因过程；
- `Effect`：局部、上一级、子系统、系统、运行、安全、环境、排放、资产和维护影响；
- `Symptom`：可观察信号，不与 effect 混用；
- `Control`：预防、检测、保护/响应和操作员处置；
- `Barrier`：屏障、安全功能、独立性和验证状态；
- `Action`：推荐措施、负责人、期限、完成证据和有效性验证；
- `RiskAssessment`：S/O/D、后果向量、决策优先级和四阶段风险；
- `EvidenceRef`：字段或关系的稳定证据；
- `PropagationEdge`：跨系统条件传播、公共原因或依赖；
- `ReviewDecision`：逐字段或逐关系的人工裁决；
- `PublicationManifest`：不可变发布清单；
- `IssueFeedback`：按根因回流上游 M1-M4，或留在 M5/M6 处理的结构化问题。

### 5.3 三条状态轴

声明状态：

```text
known | unknown | insufficient_evidence | conflict | not_applicable
```

审核状态：

```text
draft | suggested | in_review | accepted | rejected | superseded
```

发布状态：

```text
unpublished | published | withdrawn
```

三个状态必须独立存储。`not_applicable` 不能映射为 `unknown`；`published` 也不能显示为 `certified`。

## 6. 证据闭环

### 6.1 EvidencePack

每次生成前先产生不可变 EvidencePack，至少包含：

- workspace/租户和 ACL 范围；
- `document_id`、资料版本和内容 hash；
- 文件、页码、chunk、span、表格单元格或图谱 triple locator；
- 原文 quote、规范化 quote 和 evidence hash；
- 检索运行 ID、检索模式、来源类型和来源可信等级；
- 是否为原始资料、人工整理、图谱关系或 LLM 社区摘要；
- 创建时间、过期状态和 EvidencePack hash。

FMEA 主张只能引用当前 EvidencePack 内的 ID。

### 6.2 证据支持状态

```text
supported | partially_supported | contradicted | not_supported
```

服务端必须确定性验证：

- Evidence ID 存在并属于当前 workspace；
- 文档、版本、hash 和 ACL 一致；
- quote 与 span 或单元格内容匹配；
- 证据支持的是当前字段或传播关系，而非仅仅语义相似；
- 所有冲突来源均被保留；
- 缺证据的字段不能成为 `known`。

模型输出和检索分数不得直接改变证据支持状态。

### 6.3 审计与原始轨迹

- 普通领域审计保存 actor、命令、前后 revision、理由、版本和 hash；
- 普通运行日志只保存 ID、hash、阶段、耗时、token、重试、缓存和 fallback；
- 原始 prompt、证据全文和模型原始响应进入加密、受限且有保留期限的 trace vault；
- 发布清单保存审计事件链和内容 hash，撤回通过新事件表达，不覆盖旧记录。

### 6.4 问题回流

FMEA 输出阶段发现的问题必须先记录为 `IssueFeedback`，再按根因路由，不能直接修改上游资料或图谱：

- M1 资料获取：来源、权限、密级、版本或资料缺失；
- M2 解析与标注：OCR、阅读顺序、表格、页码或证据定位错误；
- M3 资料库构建：切片、索引、资料版本、发布或撤回不一致；
- M4 GraphRAG：实体、关系、别名、图谱版本、路径或检索错误；
- M5 任务输出接口：FMEA schema、模板、评分、审核、导出或接口合同问题；
- M6 流程编排与质检：运行恢复、质量门、回归、重复执行或跨模块兼容问题。

每条问题保存发现位置、受影响字段/传播边、证据、根因候选、严重度、复现输入、目标模块、状态和回流后的重验 run。LLM 可以建议分类和修复说明，但只有人工或确定性规则可以确认根因和关闭问题。

## 7. 风险与评分

### 7.1 评分包版本化

每个 S/O/D 规则包保存：

- 规则包 ID、版本和适用分析类型；
- 1-10 的锚点定义和方向；
- O 的观察窗口、暴露单位和分母；
- D 的检测位置、覆盖率和允许检测时限；
- 每项评分的证据或专家判断理由；
- 评分区间和不确定性；
- RPN 公式版本、风险矩阵版本和决策优先级规则版本。

### 7.2 风险表达

- `severity_by_consequence_class`：安全、环境、排放、可用性、资产、维护；
- `decision_severity`：用于规则引擎的决策严重度；
- `RPN = S × O × D`：派生排序指标；
- `decision_priority`：综合后果向量、不确定性、工况和硬升级规则；
- `inherent_risk`、`current_risk`、`target_residual_risk`、`verified_residual_risk`。

unknown、conflict 或缺失评分不能转换为 0，也不能生成有效 RPN。措施完成但缺少有效性证据时，不得自动生成 verified residual risk。

## 8. 燃料系统与燃烧系统传播

传播关系必须是一等对象：

```text
source failure
  -> interface variable change
  -> operating mode / threshold / delay
  -> target failure or effect
  -> hazard or system consequence
  -> detection / protection / response
```

`PropagationEdge` 至少保存：

- source 和 target 实体 ID；
- relation type：传播、公共原因、依赖、反馈；
- 接口变量、单位、方向、阈值和范围；
- 工况、延迟、响应时间和故障容忍时间；
- 屏障和保护；
- 证据、声明状态、审核状态和不确定性；
- 最大路径长度、循环、未处理、外部和终止标记。

首批接口变量覆盖燃料压力、质量流量、温度、燃料组分、Wobbe 指数、液体夹带、颗粒污染、阀位与反馈、燃料分级、净化/放空、仪表空气、电源、控制网络、火焰信号、动态压力和排气温度分布。

默认自动传播搜索最多两跳；超过两跳必须标记为推断且待人工确认。高风险、无证据或存在循环的传播边不能自动接受。

## 9. LLM 介入架构

### 9.1 有界候选流水线

```text
确定性范围/权限/版本/预算检查
    -> EvidencePack 快照
    -> 批量结构化候选生成
    -> schema/证据/关系/评分确定性校验
    -> 高风险或冲突记录的独立批判
    -> 最多一次有界修复
    -> candidate / unknown / conflict / needs_review
    -> 人工审核
```

避免为每个字段启动独立智能体。模型工具统一为只读、有限输入、有限候选、有限调用和有限传播深度。

### 9.2 模型可做与不可做

模型可以：

- 建议系统结构、功能、故障模式、原因、机理、影响、控制和措施；
- 建议字段与证据的对应关系；
- 识别缺失、冲突和潜在传播链；
- 提供 S/O/D 候选和理由；
- 生成审核摘要、差异说明、模板映射和问题回流建议。

模型不得：

- 访问不在 EvidencePack 中的路径、URL 或租户；
- 选择自身权限、模型供应商、工具或重试策略；
- 把资料中的指令当作系统指令；
- 静默解决冲突或把未知改为 known；
- 修改已发布模板和评分锚点；
- 执行 approve、publish、withdraw 或责任签字。

### 9.3 外部模型 API

- 按数据分类决定是否允许外发；
- 默认只发送完成任务所需的最小证据片段；
- 使用服务端 egress allowlist、脱敏和 DLP；
- API Key 仅来自服务端 Secret 配置；
- 记录 provider、地区、retention、training opt-out 和删除策略；
- 模型路由由确定性策略决定，高敏感数据使用本地或批准端点；
- 高严重度、冲突或长传播链使用更强且尽量独立的批判模型；
- 批判模型不可用时只能降级为 `needs_review`，不能自动放行。

### 9.4 成本、重试、缓存和幂等

每个 run 设置最大候选数、输入/输出 token、调用次数、总时长、修复轮数和传播边数。仅对 timeout、429、5xx 和网络错误重试。

幂等和缓存键至少包含：

```text
workspace/ACL + task + input_snapshot_hash + EvidencePack_hash
+ data_version + graph_version + template_version + scoring_version
+ stage + model/provider + prompt_hash + tool_schema_hash
```

缓存只复用 suggestion；每次命中后仍重新执行证据、权限、版本和状态校验。

## 10. 模板与新模板接入

### 10.1 四层版本结构

```text
Canonical Semantic Core
  -> Domain Profile
  -> Scoring / Risk Rule Pack
  -> View and Export Mapping
```

- 核心实体和状态语义固定；
- 领域扩展使用命名空间，例如 `gas_turbine.fuel.wobbe_index`；
- 模板、评分包、风险矩阵、提示词和导出映射独立版本化；
- 发布后的模板不可原地修改，只能产生新版本；
- 已发布 FMEA 永久绑定原模板和评分版本。

模板生命周期：

```text
draft -> validating -> published -> deprecated
```

### 10.2 浏览器模板工具

首版提供配置表单和预览，不做任意拖拽低代码画布。允许配置：

- 字段标签、顺序、分组、类型、必填、枚举和静态提示；
- 已注册评分包的选择；
- 有限的校验、警告和条件显示；
- 语义字段到 Excel/Word/API 的映射；
- 自定义命名空间字段。

禁止任意 JavaScript、网络请求、任意公式、循环、跨表查询以及由模板决定权限或审批。

### 10.3 Excel 模板导入与 LLM 助手

Excel 导入保存原始文件 hash、工作表、行列、单元格地址和合并单元格关系。未知列保留原文，歧义表头进入人工映射；导入结果只能成为模板草案。

LLM 可以建议字段映射、扩展字段和模板 patch，但每个 patch 必须记录输入版本、模型、提示词、diff 以及人工接受或拒绝结果。

### 10.4 新模板难度分级

| 变更 | 工具完成度 | 是否写代码 |
| --- | --- | --- |
| 标签、顺序、必填、导出列 | 浏览器直接配置 | 否 |
| 普通扩展字段、枚举、提示 | JSON Schema 表单 | 否 |
| 有限条件与校验 | 受限 DSL | 通常否 |
| 新 Excel 表头映射 | 导入助手 + 人工确认 | 否 |
| 新评分算法或审批语义 | 服务端扩展 | 是 |
| 第三方领域插件 | 白名单、版本锁定、权限声明、隔离执行 | 是，后置 |

## 11. 审核、账号与发布

### 11.1 角色

- `analyst`：生成、编辑、绑定证据和提交审核；
- `reviewer`：接受、拒绝、修改和解决冲突；
- `publisher`：批准发布或撤回；
- `template_admin`：管理模板草案和发布；
- `admin`：本地管理员，可拥有全部角色。

actor 类型严格区分 `human`、`model` 和 `system`。批准和发布要求 `human` actor。

### 11.2 本地测试账号

首版提供仅适用于本机回环地址的 local auth provider：

- 一个全角色管理员账号供用户自测；
- 密码由环境变量或初始化命令设置，不提交默认明文密码；
- 非回环监听时必须显式关闭 local dev auth 或配置受信认证；
- 认证层保留 OIDC/反向代理适配接口，但首版不要求部署企业 IdP。

### 11.3 并发与状态机

- revision 和 row 使用递增 `record_version`；
- HTTP 使用 `ETag/If-Match`，冲突返回 409 或 412；
- 不允许静默覆盖；
- unresolved 项可以由人带理由接受，但必须在发布清单中显式列出；
- published revision 不可修改；修改时从它创建新 revision；
- withdrawal 产生新审计事件，不删除旧发布版本。

### 11.4 发布清单

`PublicationManifest` 至少包含：

- project、analysis、revision 和 parent revision；
- schema、Profile、模板和评分版本；
- 数据、图谱、EvidencePack 和输入快照 hash；
- 内容 hash、传播关系 hash、审核记录和未解决项；
- 批准者、发布者、时间和撤回关系；
- “非认证、非安全批准、需专业人员负责”的免责声明。

## 12. REST、长任务和错误合同

### 12.1 资源

```text
/api/v1/fmea/projects
/api/v1/fmea/analyses
/api/v1/fmea/revisions
/api/v1/fmea/rows
/api/v1/fmea/evidence-packs
/api/v1/fmea/propagation-edges
/api/v1/fmea/templates
/api/v1/fmea/template-versions
/api/v1/fmea/runs
/api/v1/fmea/exports
/api/v1/fmea/audit-events
/api/v1/fmea/issues
```

认证属于平台能力，使用 `/api/v1/auth`，不嵌入 FMEA 资源命名空间。

### 12.2 命令

```text
POST /analyses/{id}/runs
POST /runs/{id}/cancel
POST /rows/{id}/review-decisions
POST /revisions/{id}/approve
POST /revisions/{id}/publish
POST /revisions/{id}/withdraw
POST /revisions/{id}/exports
POST /template-versions/{id}/validate
POST /template-versions/{id}/publish
```

### 12.3 写入和任务合同

- 写请求支持 `Idempotency-Key`；
- 修改可变资源要求 `If-Match`；
- 长任务返回 HTTP 202、`run_id`、`Location`、状态 URL、事件 URL 和取消 URL；
- run 状态为 `queued/running/cancelling/cancelled/succeeded/failed`；
- 取消是协作式取消，断开 SSE 不取消任务；
- SSE 事件有单调 ID、心跳、当前快照和 `Last-Event-ID` 重连；
- 表格使用 cursor 分页、稳定排序和服务端过滤；
- 所有成功输出带 `schema_version/request_id/trace_id`。

### 12.4 错误格式

采用 `application/problem+json`：

```json
{
  "type": "https://errors.example/fmea/version-conflict",
  "title": "Revision conflict",
  "status": 412,
  "code": "FMEA_VERSION_CONFLICT",
  "detail": "The revision changed after it was loaded.",
  "trace_id": "...",
  "retryable": false,
  "errors": [{"pointer": "/record_version", "code": "STALE_VERSION"}]
}
```

不得返回 Python 异常栈、本地文件路径、日志路径、密钥或模型原始错误正文。

## 13. CLI 与 Codex Skill

### 13.1 CLI

`scripts/fmea_skill.py` 提供稳定机器调用：

```text
project create/show
analysis configure
validate
generate
status
cancel
rows list/show/diff
evidence show
review submit
publish
export
template import/validate
```

- stdout 只输出一个 JSON 文档；
- 日志写 stderr；
- 固定退出码区分输入、权限、冲突、运行失败和部分成功；
- CLI 与 HTTP 共享 application service、权限、状态机和审计；
- CLI 不直接访问 SQLite。

### 13.2 Codex Skill

Skill 负责编排项目配置、生成、状态查询、证据缺口说明、审核准备和导出请求。默认只读；任何人工写操作必须显式提交 actor 上下文。

Skill 不绕过权限、不读取数据库、不携带 API Key、不自动发布，也不把评测通过解释为工程结论正确。

## 14. 浏览器工作台

保持现有 `index.html` 不动，新增独立薄壳和原生 ES Modules：

```text
frontend_app/current_console/fmea.html
frontend_app/current_console/fmea/
  bootstrap.js
  config.js
  state/store.js
  api/client.js
  api/runs.js
  api/sse.js
  domain/fmea.js
  views/project-list.js
  views/configuration.js
  views/workbench.js
  views/evidence-panel.js
  views/propagation.js
  views/review.js
  views/publication.js
  views/template-editor.js
  schemas/
  fixtures/
  fmea.css
```

UI 规则：

- 主表只显示关键字段，完整内容放在右侧字段检查器；
- 固定 row ID、失效模式和风险状态；
- 支持列预设、宽度、换行、密度、水平滚动和键盘导航；
- 每个字段显示已支持、部分支持、冲突、缺失、过期、人工填写或模型建议；
- 证据侧栏显示来源、版本、页码/chunk/单元格、quote 和高亮；
- 明确区分模型建议和工程师确认值，支持逐字段接受、拒绝、编辑和 diff；
- 批量接受前显示影响行数、证据覆盖率、冲突和高风险项；
- 支持未保存修改、自动保存失败、并发冲突和旧版本恢复；
- 颜色不是唯一状态表达方式；
- GitHub Pages 或 `file:` 演示模式明确标记只读并禁用批准、发布和真实持久化。

传播首版提供关系表、证据审核、前向影响和后向贡献者只读图；自由拖拽图编辑器后置。

## 15. 导出一致性与安全

JSON 是规范输出，XLSX 和 Word 是同一 normalized DTO 的展示适配器。导出只能读取不可变发布快照或显式标记的 draft preview，不能读取浏览器当前可变状态。

每份产物携带：

- project、analysis、revision；
- schema、Profile、模板和评分版本；
- snapshot hash、数据和图谱版本；
- 审核人、发布人和时间；
- 证据 manifest、未解决项和免责声明。

安全要求：

- Excel 文本以 `= + - @` 开头时安全转义；
- 禁止宏和外部链接；
- Word 使用纯文本或安全 XML，不拼接用户 HTML；
- 文件名、下载路径和 Content-Disposition 由服务端生成；
- 下载检查项目权限，并使用短期授权；
- 大导出通过 run 和临时产物存储执行；
- golden fixture 比较 JSON/XLSX/Word 的 row ID、字段、评分、证据数、状态、revision 和 snapshot hash。

首个发布闭环先完成 JSON 和 XLSX；Word 在 normalized DTO 和一致性测试完成后接入。

## 16. 评测与发布门槛

### 16.1 20 条内部非认证夹具

- 燃烧系统 10 条；
- 燃料系统 10 条；
- 至少 2 条跨系统传播链，并覆盖公共原因、循环或未处理传播；
- 覆盖完整行、层级边界、原因/机理/效果/症状分离、unknown、证据不足、冲突、版本失配、RPN 碰撞、措施前后风险、导出往返、模板扩展和 LLM 权限边界。

每条保存 fixture ID、版本、预期不变量、证据来源、编写者、评审者、争议、许可证和变更历史。早期允许一名用户自测，但不得声明已完成双领域专家认证。

### 16.2 安全和故障回归

在 20 条领域夹具外至少增加：

- 5 条直接 prompt injection；
- 5 条文档内间接 injection；
- 4 条证据缺失或 OCR 损坏；
- 4 条多来源冲突；
- 4 条版本不匹配；
- 4 条 429、timeout、5xx 或 malformed JSON；
- 4 条重复请求、缓存命中、fallback 和重连场景。

### 16.3 P0 硬零指标

以下数量必须为 0：

- 接受不存在或越权的 Evidence ID；
- quote/span/hash 不匹配仍被接受；
- 无证据字段成为 known；
- 冲突被静默解决；
- 模型触发 approved、published 或 withdrawn；
- 重试产生重复状态迁移；
- prompt injection 导致越权读取、外发或写入；
- 关键审计轨迹缺失；
- JSON/XLSX/Word 指向不同 revision 或 snapshot hash。

### 16.4 初始内容指标

- 状态感知字段 F1 ≥ 0.85；
- 证据支持 precision ≥ 0.95；
- 非 unknown 字段证据覆盖率 ≥ 0.90；
- unknown/conflict 召回率 ≥ 0.90；
- 传播边 precision ≥ 0.90；
- 高风险记录无证据传播边为 0；
- RPN 算术正确率 100%。

指标只用于内部回归，不能证明工业有效性。S/O/D 还需检查理由、评分版本、区间和单调性，不能只判断是否等于某个专家数字。

## 17. 实施阶段和质量门

### 阶段 A：领域内核

实现规范实体、关系、状态轴、风险阶段、传播边和版本组合。通过纯领域单元测试后才能进入存储。

### 阶段 B：独立存储与审计

实现 FMEA SQLite、schema version、事务迁移、外键、唯一约束、乐观锁、备份和迁移失败保护。不得复用 `GraphStore.initialize(reset=True)`。

### 阶段 C：证据闭环

实现 EvidenceProvider、EvidencePack、hash/span/ACL 校验和冲突保留。通过 P0 证据硬零测试后才能接模型。

### 阶段 D：候选生成

实现确定性预算、结构化生成、校验、独立批判、一次修复、缓存、重试和显式 fallback。

### 阶段 E：审核与发布

实现本地账号、角色权限、人工审核、不可变 revision、审计和发布清单。模型身份的非法状态迁移必须由存储层拒绝。

### 阶段 F：接口输出

实现 REST、SSE、JSON CLI 和 Codex Skill，完成 OpenAPI/JSON Schema 契约、幂等、ETag 和重连测试。

### 阶段 G：浏览器工作台

实现 FMEA 独立页面、字段证据侧栏、传播审核、并发冲突和发布检查。

### 阶段 H：导出与模板工具

先完成 JSON/XLSX，再接 Word；同时实现声明式模板配置、预览和 Excel 模板导入。任意插件继续后置。

### 阶段 I：回归和发布准备

完成领域夹具、安全/故障回归、端到端主链、许可证和第三方来源清单。

## 18. 开源参考与项目创新

借鉴边界：

- Microsoft GraphRAG：本地、全局和图证据检索边界；
- KUREAS：FMEA、系统结构和报告工作台的轻量交互；
- OSATE2/EMV2：前向影响、后向贡献者、传播终止和循环表达；
- NASA fmdtools：故障传播、状态和场景化验证；
- IBM AssetOpsBench：保存最终结果和中间轨迹的评测思想；
- JSON Schema 2020-12：声明式模板校验。

在直接复用任何源码前，必须增加根级项目许可证决策、`THIRD_PARTY_NOTICES.md`、开源来源矩阵和逐文件许可证检查。GPL 等不兼容实现只做行为参考。

可作为本项目真实创新并通过实验验证的内容：

1. **Evidence-closed FMEA：** 每个字段、传播边和评分理由均可被服务器验证；缺证据自动降级。
2. **反事实证据回归：** 删除、替换或冲突化证据，验证输出是否降为 unknown/conflict。
3. **风险自适应计算预算：** 仅对高严重度、低证据覆盖、冲突或长传播链升级模型和批判成本。
4. **可重放 suggestion ledger：** 固化输入、EvidencePack、版本、模型、提示词、tool schema 和规范化结果，支持模型版本 diff。
5. **状态安全性指标：** 把无越权状态迁移、无重复写入、无证据不发布作为核心质量指标。

strict tool calling、Evidence ID、GraphRAG + KG、generate + critic、RPN 自动计算、OpenAI-compatible API、多智能体角色和普通缓存/日志不单独宣称为创新。

## 19. 最终验收主链

同一份输入快照依次完成：

1. 项目配置和版本锁定；
2. EvidencePack 生成；
3. 燃料/燃烧 FMEA 候选及传播边生成；
4. SSE 断线和重连；
5. 人工字段及传播审核；
6. 并发修改冲突处理；
7. 人工批准和发布；
8. JSON/XLSX 导出；
9. Skill/CLI 重放和版本 diff。

验收时 JSON 和 XLSX 必须引用同一个 `revision_id` 和 `snapshot_hash`，没有静默冲突、越权访问、重复状态迁移或无证据已知字段。Word 接入后必须通过相同一致性门槛。

## 20. 参考资料

- [IEC 60812:2018](https://webstore.iec.ch/en/publication/26359)
- [Microsoft GraphRAG](https://github.com/microsoft/graphrag)
- [KUREAS](https://github.com/curtlsmith/KUREAS)
- [OSATE2](https://github.com/osate/osate2)
- [NASA fmdtools](https://github.com/nasa/fmdtools)
- [IBM AssetOpsBench](https://github.com/IBM/AssetOpsBench)
- [JSON Schema 2020-12](https://json-schema.org/draft/2020-12)
- [RFC 9457: Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457.html)
- [OWASP LLM Prompt Injection](https://genai.owasp.org/llmrisk/llm01-prompt-injection/)
