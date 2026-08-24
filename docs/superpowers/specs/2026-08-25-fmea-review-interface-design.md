# FMEA 复核接口设计

**日期：** 2026-08-25

**状态：** 已完成会话设计确认，待用户复审书面规格

**所属阶段：** FMEA 候选生成之后、风险评分与批准发布之前

**责任边界：** M5/FMEA 接口输出

## 1. 决策摘要

本设计采用以下方案：

1. 复用现有通用结构化模板引擎生成模型复核建议；
2. 使用独立 `ReviewService` 执行人工复核决定；
3. `ReviewSuggestion` 与 `ReviewDecision` 分离并不可变保存；
4. 模型只能建议，只有经过认证的 `human` reviewer 可以改变 FMEA 行的审核状态；
5. 模型建议作为异步长任务执行，人工决定同步、原子、可幂等提交；
6. SQLite 同一事务保存人工决定、更新后的行、递增版本和审计事件；
7. 普通 RAG、GraphRAG-only、RAG-only 和 combined 结果使用同一复核合同；
8. 本阶段不包含 S/O/D、RPN、revision 批准、发布、撤回、浏览器 UI 或办公文档导出。

该设计延续 `docs/superpowers/specs/2026-08-23-graphrag-fmea-system-design.md` 的三轴状态、人工最终裁决、乐观锁和审计原则，并接续 `docs/superpowers/specs/2026-08-24-structured-generation-deepseek-fmea-design.md` 产生的 `FmeaRow` suggestion。

旧计划 `docs/superpowers/plans/2026-08-23-fmea-review-interfaces.md` 同时混合了复核、评分、批准、发布、SSE、Skill 和全阶段验收，不能原样用于本次实现。后续实施计划只抽取本设计的复核切片；旧计划中的批准、发布和撤回任务仍然后置。

## 2. 目标与非目标

### 2.1 目标

首版复核接口必须做到：

- 读取 FMEA 行、人工可读身份、字段证据、检索来源和历史决定；
- 调用外部大模型生成有界、可验证的逐字段复核建议；
- 允许人工执行接受、修改后接受、驳回、请求补证和暂缓；
- 对人工修改实施明确字段白名单和证据约束；
- 防止模型、客户端自报角色或并发旧版本改变审核结果；
- 为重复请求、模型长任务、审计和故障恢复提供稳定合同；
- 将补证需求结构化回流给 RAG/GraphRAG 负责人，而不直接修改上游资料、索引或图谱；
- 让 REST、JSON CLI 和未来 Codex Skill 共享同一个应用服务语义。

### 2.2 非目标

本阶段明确不实现：

- S/O/D、RPN、风险矩阵或措施优先级；
- revision 批准、发布、撤回和发布清单；
- 传播边复核、跨系统路径编辑和公共原因裁决；
- 浏览器复核工作台；
- JSON 之外的 XLSX、Word 或 PDF 导出；
- 企业 OIDC/SSO、组织账号生命周期或企业权限平台；
- 通用 RAG/GraphRAG 检索算法、索引、建图、OCR 或资料治理；
- 允许模板运行任意代码、网络请求、工具调用或数据库语句；
- 自动安全放行、自动签字或用模型替代领域工程师。

## 3. 当前代码事实与兼容性约束

设计以当前仓库可验证事实为准：

- 公共 FMEA schema ID 是 `graphrag.fmea.v1`；复核资源通过 `resource_type` 和 `resource_version` 区分，不另造不兼容的顶层 schema ID。
- `FmeaRow.review_status` 已支持 `draft|suggested|in_review|accepted|rejected|superseded`。
- `FmeaRow.publication_status` 与审核状态独立；本阶段始终保持 `unpublished`。
- `FmeaRow.record_version` 已存在，可作为 HTTP `ETag/If-Match` 和应用层 `expected_record_version` 的来源。
- `FmeaRow` 当前存储 `item_id`、`function_id`，没有人类可读的 item/function 文本。
- 当前可直接编辑的专业内容字段是 `failure_mode`、`causes`、`mechanisms`、`effects`、`symptoms`、`controls`、`barriers` 和 `actions`。
- `field_evidence` 和 `field_support` 已提供字段级证据 ID 与支持状态；`claim_status` 当前是行级保守聚合，而不是逐字段字段。
- `FmeaRepository` 目前只有端口，没有 SQLite 实现；复核必须先补最小持久化基础，但不得使用或改造通用 GraphStore 数据库。
- 当前领域策略允许 `rejected -> draft`。本设计收紧为“同一 row revision 中 accepted/rejected 终态”，后续修改必须创建新 revision 并将旧行标记为 `superseded`。

### 3.1 人工可读身份补口

复核不能只向人展示哈希化 `item_id/function_id`。候选持久化时必须同时保存不可变 `ReviewSourceSnapshot`：

```json
{
  "row_id": "fmea-row-001",
  "source_record_version": 1,
  "candidate_id": "candidate-001",
  "item_label": "燃油过滤器",
  "function_label": "过滤燃油中的颗粒污染物",
  "template_id": "fuel-combustion-fmea-complete",
  "template_version": "1.0.0",
  "profile_id": "fuel-combustion-fmea-row",
  "profile_version": "1.0.0",
  "generation_run_id": "generation-run-001",
  "requested_evidence_profile": "auto",
  "resolved_evidence_profile": "combined",
  "evidence_types": ["text", "graph", "community"],
  "trace_id": "trace-001",
  "field_claim_statuses": [
    {"target_field": "failure_mode", "claim_status": "known"},
    {"target_field": "causes", "claim_status": "insufficient_evidence"}
  ],
  "source_hash": "sha256:..."
}
```

该快照只保存复核所需的结构化来源，不保存模型原始响应、完整 prompt、API Key 或 EvidencePack 之外的内容。`field_claim_statuses` 是候选中逐 claim 状态按专业字段做的保守聚合，用来补足当前 `FmeaRow` 只有行级 `claim_status` 的兼容缺口。后续复核上下文以来源快照为基线，按顺序折叠不可变人工决定，形成最新字段状态投影；它不伪装成当前核心 `FmeaRow` 已有字段。

旧行缺少来源快照时，读取接口返回 `reviewability=false` 和 `FMEA_REVIEW_SOURCE_MISSING`；可以驳回、暂缓或请求补证，但不能接受。

item/function 的身份变更不属于首版行内编辑。需要更改身份时，复核结果生成结构化 `identity_change_required` 问题，由后续 revision 流程创建新实体或新行。

## 4. 总体架构

```text
FmeaRow suggestion + EvidencePack + ReviewSourceSnapshot
                        |
                        v
                ReviewQueryService
                        |
             +----------+-----------+
             |                      |
             v                      v
    ReviewSuggestionService    ReviewDecisionService
             |                      |
    通用模板引擎 + 模型端口       人工权限/状态/证据校验
             |                      |
             v                      v
    immutable suggestion       atomic row decision
             |                      |
             +----------+-----------+
                        v
              SqliteFmeaRepository
        suggestion / decision / audit / row
                        |
             +----------+-----------+
             |                      |
             v                      v
        REST adapter            JSON CLI adapter
```

### 4.1 组件职责

| 组件 | 单一职责 | 明确不做 |
| --- | --- | --- |
| `ReviewQueryService` | 组装复核上下文和历史 | 不调用模型、不改变状态 |
| `ReviewSuggestionService` | 创建/执行模型建议任务并严格解码输出 | 不应用建议、不接受/驳回行 |
| `ReviewDecisionService` | 验证并原子执行人工决定 | 不做评分、批准或发布 |
| `ReviewTemplateAdapter` | 把行与证据投影为通用模板输入，把输出映射为建议 | 不直接读数据库或 HTTP |
| `SqliteFmeaRepository` | 迁移、事务、乐观锁、幂等和追加审计 | 不访问 GraphStore |
| REST/CLI adapter | 认证、输入输出映射和稳定错误合同 | 不复制领域规则 |

应用层可以使用一个 `ReviewService` facade 暴露上述三组能力，但内部必须保持查询、模型建议和人工决定边界，避免一个大函数同时处理模型、权限、数据库和 HTTP。

## 5. 核心数据合同

### 5.1 ActorContext

```python
@dataclass(frozen=True, slots=True)
class ActorContext:
    actor_id: str
    actor_type: ActorType
    roles: frozenset[str]
    workspace_id: str
```

`ActorContext` 只能由认证 provider 或内部模型服务身份构造。REST/CLI 请求正文不得提交或覆盖 `actor_id`、`actor_type`、`roles` 或 `workspace_id`。

首版权限：

| 操作 | analyst | reviewer | model service | publisher |
| --- | ---: | ---: | ---: | ---: |
| 读取复核上下文 | 是 | 是 | 受限内部读取 | 是 |
| 创建模型建议任务 | 是 | 是 | 否 | 是 |
| 保存模型建议 | 否 | 否 | 是 | 否 |
| 提交人工决定 | 否 | 是 | 否 | reviewer 角色存在时是 |
| 改变发布状态 | 否 | 否 | 否 | 本阶段不存在该接口 |

角色不能覆盖 actor 类型约束。`model` actor 即使错误地拥有 reviewer 角色，也不能提交人工决定。

### 5.2 ReviewAction

```text
accept | modify_and_accept | reject | request_evidence | defer
```

语义固定如下：

| action | 内容变化 | review_status | 额外要求 |
| --- | --- | --- | --- |
| `accept` | 无 | `accepted` | 人工 reviewer；来源快照可读 |
| `modify_and_accept` | 白名单字段原子替换 | `accepted` | 至少一条合法 edit；修改后证据校验通过 |
| `reject` | 无 | `rejected` | 必须提供理由 |
| `request_evidence` | 无 | `in_review` | 至少一条 `EvidenceRequestItem` |
| `defer` | 无 | `in_review` | 必须提供理由，不创建定时任务 |

接受表示“人工接受当前记录及其显式未知/冲突状态”，不等于所有字段已知，不等于风险可接受，更不等于已批准或发布。对 `unknown`、`insufficient_evidence` 或 `conflict` 的行进行接受时，必须在决定中明确列出 `unresolved_acknowledgements`。

`reason_code` 固定为：

```text
ACCEPT_AS_IS
FIELD_CORRECTION
UNSUPPORTED_CLAIM
CONFLICT_UNRESOLVED
EVIDENCE_REQUIRED
DEFERRED_FOR_EXPERT
HUMAN_OVERRIDE
OTHER
```

所有 action 都必须提供有界自然语言 `reason`；`reason_code=OTHER` 时 reason 不能只重复代码名称。

未解决项确认的结构为：

```json
{
  "target_field": "causes",
  "claim_status": "insufficient_evidence",
  "reason": "当前版本明确保留为证据不足，不把该原因当作已证实事实。"
}
```

每个仍为 `unknown|insufficient_evidence|conflict` 的字段在 accept/modify_and_accept 时必须恰有一条确认；不能用一条全局免责文字覆盖所有未解决字段。

### 5.3 FieldFinding

模型建议中的逐字段判断：

```json
{
  "target_field": "controls",
  "judgement": "insufficient_evidence",
  "recommended_claim_status": "insufficient_evidence",
  "evidence_ids": ["evidence-18"],
  "rationale": "现有证据只能证明压力监测存在，不能证明启动前人工检查已执行。"
}
```

`judgement` 固定为：

```text
supported | partially_supported | contradicted | insufficient_evidence | unknown | conflict | not_applicable
```

`rationale` 是不超过 500 字符的审阅摘要，不保存或要求模型思维链。

### 5.4 FieldReviewEdit

首版不开放 JSON Patch、JSON Merge Patch 或任意字段路径，只接受结构化替换：

```json
{
  "target_field": "controls",
  "operation": "replace",
  "value": ["启动前燃油压力检查"],
  "claim_status": "known",
  "support_status": "supported",
  "evidence_ids": ["evidence-18"],
  "reason": "根据当前 EvidencePack 中的维护规程补充。"
}
```

字段白名单：

```text
failure_mode
causes
mechanisms
effects
symptoms
controls
barriers
actions
```

类型要求：

- `failure_mode` 必须是非空字符串；
- 其余字段必须是去空白、保持顺序、去重后的字符串数组；
- `operation` 首版只能是 `replace`；
- evidence ID 必须存在于该行绑定的当前 EvidencePack；
- `claim_status=known` 时至少有一个 evidence ID，且 `support_status` 不能是 `contradicted` 或 `not_supported`；
- 字段级 `claim_status` 保存于来源快照和不可变决定记录，用于复核上下文；当前 `FmeaRow.claim_status` 根据折叠后的全部字段状态继续保存最保守的行级聚合；
- 未修改字段的 evidence/support 保持不变；被修改字段的 evidence/support 必须由命令完整提供，禁止隐式沿用可能已失真的旧证据。

行级 claim 聚合顺序与当前候选 adapter 保持一致：`conflict > insufficient_evidence > unknown > not_applicable > known`。数组元素先在字段内按同一顺序聚合，再跨字段聚合。字段支持状态沿用当前保守顺序：`not_supported > contradicted > partially_supported > supported`。服务端计算聚合结果，客户端和模型不能直接提交行级 `claim_status`。

禁止修改：

```text
row_id, analysis_id, evidence_pack_id, item_id, function_id,
risk_assessment, review_status, publication_status, record_version,
actor, audit, model, trace, propagation
```

### 5.5 EvidenceRequestItem

```json
{
  "target_field": "causes",
  "question": "查找喷油泵磨损导致供油压力下降的直接证据。",
  "preferred_source_types": ["maintenance_manual", "failure_report"],
  "priority": "high"
}
```

`priority` 为 `low|normal|high`。该对象是交给上游 M1-M4/M5 检索链路的机器可读请求；复核服务只保存并输出，不自动建库、建图或写上游数据。

### 5.6 ReviewSuggestion

```json
{
  "suggestion_id": "suggestion-001",
  "run_id": "review-run-001",
  "row_id": "fmea-row-001",
  "source_record_version": 7,
  "recommended_action": "modify_and_accept",
  "field_findings": [
    {
      "target_field": "controls",
      "judgement": "partially_supported",
      "recommended_claim_status": "known",
      "evidence_ids": ["evidence-18"],
      "rationale": "证据支持启动前压力检查，但当前字段未包含该控制。"
    }
  ],
  "proposed_edits": [
    {
      "target_field": "controls",
      "operation": "replace",
      "value": ["启动前燃油压力检查"],
      "claim_status": "known",
      "support_status": "supported",
      "evidence_ids": ["evidence-18"],
      "reason": "根据当前维护规程补充。"
    }
  ],
  "evidence_requests": [],
  "missing_evidence": [],
  "conflicts": [],
  "rationale": "建议摘要",
  "model_manifest": {
    "provider": "deepseek",
    "model": "deepseek-v4-pro",
    "template_id": "fmea-row-review",
    "template_version": "1.0.0",
    "prompt_hash": "sha256:..."
  },
  "actor_type": "model",
  "applied": false,
  "created_at": "2026-08-25T00:00:00Z"
}
```

建议不可更新、不可删除，也不能改变行。`applied=false` 是事实常量；人工决定只通过 `suggestion_id` 引用建议，不把建议改成已应用状态。

模型建议载荷也执行动作联动校验：`recommended_action=modify_and_accept` 必须至少有一条合法 `proposed_edits`；`request_evidence` 必须至少有一条 `evidence_requests`；`accept|reject|defer` 不允许携带会被误认为自动应用的 edit。联动失败时整个模型建议无效，不做宽松修补。

### 5.7 ReviewDecisionCommand

应用层命令：

```json
{
  "row_id": "fmea-row-001",
  "expected_record_version": 7,
  "idempotency_key": "f2308024-49d5-49ea-93ee-fcb95739d937",
  "action": "modify_and_accept",
  "suggestion_id": "suggestion-001",
  "reason_code": "FIELD_CORRECTION",
  "reason": "证据充分，但当前控制字段需要补充。",
  "edits": [
    {
      "target_field": "controls",
      "operation": "replace",
      "value": ["启动前燃油压力检查"],
      "claim_status": "known",
      "support_status": "supported",
      "evidence_ids": ["evidence-18"],
      "reason": "根据维护规程补充。"
    }
  ],
  "evidence_requests": [],
  "unresolved_acknowledgements": []
}
```

`ActorContext` 不属于客户端命令正文，由 adapter 单独注入。

### 5.8 ReviewDecisionResult

```json
{
  "decision_id": "decision-001",
  "row": {},
  "previous_record_version": 7,
  "record_version": 8,
  "review_status": "accepted",
  "publication_status": "unpublished",
  "audit_event_id": "audit-001",
  "suggestion_id": "suggestion-001",
  "evidence_requests": [],
  "persisted": true
}
```

## 6. 状态机与不变量

复核接口只允许：

```text
suggested -> accepted
suggested -> rejected
suggested -> in_review
in_review -> accepted
in_review -> rejected
in_review -> in_review   # 新的 request_evidence/defer 决定事件
```

规则：

- 模型建议不触发状态转换；
- 所有由 `ReviewDecision` 触发的状态变化，包括 `in_review` 和 `rejected`，都要求 `ActorType.HUMAN` 且具备 reviewer 角色；现有只保护 `accepted` 的领域策略必须收紧，model/system 不能借 reject 或 request_evidence 改变状态；
- `draft` 不是模型候选复核入口；需先由候选持久化流程转成 `suggested`；
- `accepted` 和 `rejected` 对本复核接口是终态，不能通过该接口重开或编辑；
- 领域层仍保留 `accepted|rejected -> superseded`，仅供后续 revision 流程在创建新 revision/row 后使用；该流程后置，不在本接口内伪造；
- 实现时从现有领域策略删除 `rejected -> draft`，增加 `in_review -> in_review` 作为可审计的 request_evidence/defer 事件；其他 draft/revision 转换不暴露为复核接口 action；
- `publication_status` 在所有成功决定后仍为 `unpublished`；
- `record_version` 只有人工决定实际改变持久化状态时递增；
- 模型建议创建、建议失败和只读查询不递增 row 版本；
- 对同一 `in_review` 行重复提交不同的 request_evidence/defer 会追加新决定并递增版本，便于审计，而不是覆盖旧请求。

## 7. 模型建议设计

### 7.1 通用模板复用

注册版本化模板：

```text
template_id: fmea-row-review
template_version: 1.0.0
```

模板只描述模型输出字段和约束。模型 provider、base URL、API Key、超时、重试、预算和角色由服务端配置，不能由模板或请求决定。

模板允许模型生成的根字段仅为 `recommended_action`、`field_findings`、`proposed_edits`、`evidence_requests`、`missing_evidence`、`conflicts` 和有界 `rationale`。`suggestion_id`、`run_id`、`row_id`、`source_record_version`、`model_manifest`、`actor_type`、`applied` 和时间戳全部由服务端在严格解码后封装，模型不能提供或覆盖。

模型输入是有界 `ReviewModelInput`：

- 人工可读 item/function 标签；
- 当前八个专业字段；
- 当前字段级 claim/support/evidence 映射；
- 当前 EvidencePack 中被引用或策略允许补充查看的最小证据投影；
- 检索模式、模板版本和来源信任等级；
- 明确的审核政策和允许动作。

不得外发：

- workspace ACL 细节；
- 本地文件路径、URL、数据库路径；
- API Key、Authorization、Cookie；
- 未被批准发送的完整文档；
- 已有模型原始 reasoning；
- 客户端要求模型自行调用工具、联网或发布的指令。

### 7.2 运行语义

模型复核为异步任务：

```text
queued -> running -> succeeded
                  -> failed
```

首版只使用现有 `RunStatus` 的 `queued|running|succeeded|failed` 子集；不暴露取消接口，单次调用由服务端总时长上限终止。REST 只要求 202 + polling，不要求浏览器 SSE。运行记录持久化，因此服务重启后不会把已完成建议变成未知状态。worker 可使用现有结构化生成服务或进程内受控执行器，但 HTTP 路由不得直接执行长模型调用。

并发规则：

- 创建任务时记录 `source_record_version`；
- 模型完成时即使 row 已更新，建议仍可保存为历史，但标记 `stale=true`；
- stale 建议不能作为自动 patch 来源；人工若引用 stale suggestion，决定接口返回 `409 FMEA_REVIEW_SUGGESTION_STALE`；
- 相同 row version、模板、模型策略和规范化输入 hash 可以复用已有成功 suggestion，但每次仍重新验证权限和 EvidencePack 可用性。

### 7.3 模型失败

模型超时、限流、认证、非法 JSON 或语义验证失败时：

- run 进入 `failed`；
- 保存安全错误码和可重试标志；
- 不创建伪造建议；
- 不改变 FMEA 行；
- 不回显 provider 原始响应、prompt、quote、路径或密钥；
- 人工复核接口仍可继续使用。

## 8. REST 合同

### 8.1 路径与公共 envelope

路径前缀遵循总设计：

```text
/api/v1/fmea
```

成功响应：

```json
{
  "schema_version": "graphrag.fmea.v1",
  "resource_type": "review_context",
  "resource_version": "1.0.0",
  "request_id": "request-001",
  "trace_id": "trace-001",
  "data": {}
}
```

错误响应使用 `application/problem+json`：

```json
{
  "type": "https://errors.local/fmea/version-conflict",
  "title": "FMEA row version conflict",
  "status": 412,
  "code": "FMEA_VERSION_CONFLICT",
  "detail": "The row changed after the submitted review context was read.",
  "trace_id": "trace-001",
  "retryable": false,
  "errors": []
}
```

### 8.2 读取复核上下文

```http
GET /api/v1/fmea/rows/{row_id}/review-context
Authorization: Bearer <token>
```

响应同时返回 `ETag: "7"`：

```json
{
  "schema_version": "graphrag.fmea.v1",
  "resource_type": "review_context",
  "resource_version": "1.0.0",
  "request_id": "request-001",
  "trace_id": "trace-001",
  "data": {
    "row": {},
    "record_version": 7,
    "review_status": "suggested",
    "publication_status": "unpublished",
    "identity": {
      "item_id": "item-...",
      "item_label": "燃油过滤器",
      "function_id": "function-...",
      "function_label": "过滤颗粒污染物"
    },
    "reviewability": true,
    "field_reviews": [],
    "evidence": {
      "pack_id": "pack-001",
      "pack_hash": "sha256:...",
      "expires_at": null,
      "refs": [
        {
          "evidence_id": "evidence-18",
          "source_type": "rag_text",
          "source_trust": "reviewed",
          "is_primary": true,
          "locator": "manual:p42",
          "quote": "启动前应检查燃油供给压力。"
        }
      ]
    },
    "retrieval": {
      "requested_profile": "auto",
      "resolved_profile": "combined",
      "evidence_types": ["text", "graph", "community"],
      "trace_id": "retrieval-trace-001",
      "warnings": [],
      "incomplete": false
    },
    "latest_suggestion": null,
    "decision_history": []
  }
}
```

`evidence` 是当前 actor 通过 workspace/ACL 检查后的复核投影，不是原始 `EvidencePack` 的无条件序列化。它保留人工核对所需的稳定 ID、来源类型、可信等级、定位和有界原文，但不返回 ACL、数据库路径、未授权文档元数据或模型输入中不需要的内容。

`retrieval.requested_profile` 和 `retrieval.resolved_profile` 使用现有证据选择合同：

```text
rag_only
graphrag_local_only
graphrag_global_only
graphrag_only
combined
custom
auto
```

复核接口不将这些 profile 重新简化成另一套互不兼容的 `mode` 枚举。非 `auto` 请求通常具有相同的 requested/resolved profile；`auto` 必须返回上游确定的最终 resolved profile，不能只返回 `auto`。`custom` 必须返回规范化、去重后的 `evidence_types`；其他 profile 也返回其确定性解析类型，调用者可据此显示 RAG-only、GraphRAG-only 或组合来源。

### 8.3 创建模型建议任务

```http
POST /api/v1/fmea/rows/{row_id}/review-suggestion-runs
Authorization: Bearer <token>
Idempotency-Key: <uuid>
If-Match: "7"
Content-Type: application/json
```

请求正文只允许：

```json
{
  "review_policy": "default",
  "focus_fields": ["failure_mode", "causes", "controls"]
}
```

`focus_fields` 为空表示复核全部八个专业字段。客户端不能指定 provider、model、URL、prompt、预算或 actor。

返回：

```http
202 Accepted
Location: /api/v1/fmea/review-suggestion-runs/review-run-001
```

```json
{
  "schema_version": "graphrag.fmea.v1",
  "resource_type": "review_suggestion_run",
  "resource_version": "1.0.0",
  "request_id": "request-001",
  "trace_id": "trace-001",
  "data": {
    "run_id": "review-run-001",
    "row_id": "fmea-row-001",
    "source_record_version": 7,
    "status": "queued",
    "status_url": "/api/v1/fmea/review-suggestion-runs/review-run-001"
  }
}
```

### 8.4 查询模型建议任务

```http
GET /api/v1/fmea/review-suggestion-runs/{run_id}
Authorization: Bearer <token>
```

成功完成时返回 `status=succeeded` 和完整 `suggestion`；运行中返回当前阶段和安全进度；失败返回稳定错误对象。任务查询不使用 `If-Match`。

### 8.5 提交人工决定

```http
POST /api/v1/fmea/rows/{row_id}/review-decisions
Authorization: Bearer <token>
Idempotency-Key: <uuid>
If-Match: "7"
Content-Type: application/json
```

HTTP adapter 将 `If-Match` 映射为应用命令的 `expected_record_version`，不要求客户端在正文重复提交版本。正文示例：

```json
{
  "action": "modify_and_accept",
  "suggestion_id": "suggestion-001",
  "reason_code": "FIELD_CORRECTION",
  "reason": "证据充分，但当前控制字段需要补充。",
  "edits": [
    {
      "target_field": "controls",
      "operation": "replace",
      "value": ["启动前燃油压力检查"],
      "claim_status": "known",
      "support_status": "supported",
      "evidence_ids": ["evidence-18"],
      "reason": "根据维护规程补充。"
    }
  ],
  "evidence_requests": [],
  "unresolved_acknowledgements": []
}
```

成功返回 `200 OK`、更新后的 `ETag: "8"` 和 `ReviewDecisionResult`。接口不会因为 `suggestion_id` 存在而自动应用 `proposed_edits`；人工必须把所接受的 edits 显式提交，避免模型输出在前端确认缺失时被静默执行。

### 8.6 读取建议和决定历史

```text
GET /api/v1/fmea/rows/{row_id}/review-suggestions
GET /api/v1/fmea/rows/{row_id}/review-decisions
```

两者均为分页只读接口，按服务端时间和稳定 ID 排序。历史对象不可修改或删除。

## 9. JSON CLI 合同

CLI 与 REST 共用 `ReviewService`，不得直接打开 SQLite：

```text
python scripts/fmea_skill.py review context --row-id <id>
python scripts/fmea_skill.py review suggest --row-id <id> --record-version 7 --idempotency-key <uuid>
python scripts/fmea_skill.py review suggestion-status --run-id <id>
python scripts/fmea_skill.py review decide --request-file <json>
python scripts/fmea_skill.py review decisions --row-id <id>
```

要求：

- stdout 恰好一个 JSON object；
- 成功和失败都使用 `graphrag.fmea.v1` envelope；CLI 失败把 REST `application/problem+json` 的 `code/detail/trace_id/retryable/errors` 映射到 envelope 的单个 `error` 对象，HTTP status 映射为稳定 exit code，不把两种传输格式误认为同一媒体类型；
- token 只从环境变量或受限输入读取，不出现在 argv、stdout、stderr 或审计；
- 写操作默认要求显式 `--confirm-human-review`；
- exit code 稳定区分输入错误、权限错误、并发冲突、上游模型故障和内部故障；
- CLI 不提供评分、批准、发布或撤回命令。

## 10. SQLite 持久化

### 10.1 数据库边界

FMEA 使用专用 SQLite 文件，例如：

```text
<workspace>/fmea/fmea.sqlite3
```

不得复用通用 GraphStore DB。初始化启用：

```text
PRAGMA foreign_keys = ON
PRAGMA journal_mode = WAL
PRAGMA busy_timeout = <bounded milliseconds>
```

迁移必须按版本顺序、在事务内执行；不得通过删除数据库或重建全表解决正常升级。

### 10.2 最小表

| 表 | 关键字段 | 可变性 |
| --- | --- | --- |
| `fmea_rows` | row JSON、三轴状态、record_version、hash | 乐观锁更新 |
| `evidence_packs` | pack JSON、hash、版本、过期时间 | 不可变 |
| `review_source_snapshots` | labels、candidate/template/profile/run、source_hash | 不可变 |
| `review_suggestion_runs` | row/version、status、request_hash、安全错误 | 状态机更新 |
| `review_suggestions` | 完整 suggestion、input/output hash、model manifest | 只追加 |
| `review_decisions` | actor、action、reason、edits、请求补证、版本 | 只追加 |
| `audit_events` | before/after hash、actor、command、trace | 只追加 |
| `idempotency_records` | actor、method/path/command、key hash、payload hash、response | 原子保留/完成 |

建议任务与人工决定使用不同表，避免把模型预测和人工标注混成一个可覆盖对象。

### 10.3 人工决定事务

```text
BEGIN IMMEDIATE
  1. 验证 actor/workspace/role
  2. 按 actor/command/path/key 读取幂等记录并比较 canonical payload hash
     - 已完成且 payload 相同：返回原状态码、响应和资源 ID，不重新执行当前版本检查
     - key 相同但 payload 不同：回滚并返回 409
     - 无记录：原子 reserve，继续处理新请求
  3. 读取 row 并验证 publication_status=unpublished
  4. 比较 expected_record_version
  5. 验证 action、suggestion、字段、值、证据和状态转换
  6. 构造新 immutable FmeaRow，重新执行 validate_row_evidence
  7. 插入 ReviewDecision
  8. 条件更新 row WHERE record_version = expected
  9. 插入 AuditEvent
  10. 完成 idempotency response
COMMIT
```

任一步骤失败均回滚。`review_decisions`、`audit_events` 或行更新不能单独成功。

## 11. 乐观锁与幂等

### 11.1 乐观锁

- GET context 返回 `ETag`；
- 创建模型建议任务和提交人工决定必须携带 `If-Match`；
- 缺少 `If-Match` 返回 `428 FMEA_PRECONDITION_REQUIRED`；
- 版本不匹配返回 `412 FMEA_VERSION_CONFLICT`；
- stale 请求不得保存 decision、audit 或部分行更新；
- 建议任务可以在完成时成为 stale 历史，但不能改变行。

### 11.2 幂等

幂等作用域：

```text
workspace + actor_id + command/method + canonical path + idempotency_key
```

规则：

- 相同作用域、相同规范化 payload hash：返回第一次完成的状态码、响应体和资源 ID；
- 相同 key、不同 payload：`409 FMEA_IDEMPOTENCY_CONFLICT`；
- authentication、actor、workspace、command/path 和 payload hash 检查不能因 replay 被绕过；命中已完成且完全相同的请求后允许直接返回原响应，因为首次成功已经递增 row 版本；只有新 reserve 的请求执行当前 `If-Match` 和状态检查；
- 存储原始 key 的安全 hash，不在日志和审计中保存明文；
- 人工决定的幂等保留与数据库更新在同一事务；
- 模型建议 run 的幂等保留与 run 创建在同一事务。

## 12. 审计

每个模型建议 run 创建/完成/失败，以及每个人工决定，都追加不可变 `AuditEvent`。人工决定事件至少包含：

```text
event_id
occurred_at_server
workspace_id
actor_id / actor_type / roles
command / action / reason_code / reason
analysis_id / row_id / suggestion_id / decision_id
expected_record_version / applied_record_version
before_hash / after_hash
changed_fields
evidence_ids / evidence_request_targets
idempotency_key_hash / canonical_payload_hash
schema/template/profile/model/version manifest
request_id / trace_id / retrieval_trace_id
```

审计约束：

- 时间使用服务器 UTC；
- before/after hash 使用规范化 JSON；
- 不存 API Key、Authorization、Cookie、私有路径、完整 prompt 或模型思维链；
- 决定理由可以保存，但有明确长度上限并经过控制字符校验；
- 审计查询与写入分离，普通 reviewer 不能删除或修改历史；
- 撤销错误决定不删除旧事件，而是在未来 revision 流程追加 supersede 关系。

## 13. 本机认证

首版提供 loopback-only local auth provider：

```env
FMEA_LOCAL_AUTH_ENABLED=true
FMEA_REVIEW_ACTOR_ID=local-reviewer
FMEA_REVIEW_TOKEN=<用户自行设置的高熵随机值>
```

要求：

- 仓库不提交默认 token；
- token 使用恒定时间比较；
- 默认只允许 `127.0.0.1`/`::1`；
- 非回环监听时 local auth 必须失败关闭，除非显式配置受信认证 provider；
- 日志只记录 actor ID 和 token 指纹，不记录 token；
- 本地账号固定为 `human`，角色由服务端配置；
- 外部模型 API 使用独立内部 `model` actor，不复用人的 token。

## 14. 错误合同

| HTTP | code | 条件 |
| ---: | --- | --- |
| 400 | `FMEA_REVIEW_REQUEST_INVALID` | JSON 或 header 形状错误 |
| 401 | `FMEA_AUTH_REQUIRED` | token 缺失或无效 |
| 403 | `FMEA_REVIEW_FORBIDDEN` | actor/role/workspace 不允许 |
| 404 | `FMEA_ROW_NOT_FOUND` | row 不存在或对 actor 不可见 |
| 404 | `FMEA_REVIEW_SUGGESTION_NOT_FOUND` | suggestion/run 不存在或不可见 |
| 409 | `FMEA_IDEMPOTENCY_CONFLICT` | key 相同但请求不同 |
| 409 | `FMEA_REVIEW_TERMINAL` | 当前 revision 已 accepted/rejected/superseded |
| 409 | `FMEA_REVIEW_SUGGESTION_STALE` | 引用建议的 source version 过期 |
| 412 | `FMEA_VERSION_CONFLICT` | `If-Match` 过期 |
| 422 | `FMEA_REVIEW_ACTION_INVALID` | action 与 edits/request 不匹配 |
| 422 | `FMEA_REVIEW_FIELD_INVALID` | 字段、operation 或 value 不合法 |
| 422 | `FMEA_EVIDENCE_INVALID` | evidence 不在当前 pack 或与 known 冲突 |
| 422 | `FMEA_UNRESOLVED_ACK_REQUIRED` | 接受未知/冲突时未确认 |
| 428 | `FMEA_PRECONDITION_REQUIRED` | 缺 `If-Match` 或 Idempotency-Key |
| 429 | `FMEA_REVIEW_RATE_LIMITED` | 模型建议速率/预算受限 |
| 502 | `FMEA_MODEL_SUGGESTION_INVALID` | 模型输出无法严格解码或验证 |
| 503 | `FMEA_MODEL_SUGGESTION_UNAVAILABLE` | provider/网络/限流在有界重试后失败 |
| 503 | `FMEA_REVIEW_STORAGE_UNAVAILABLE` | SQLite 忙或存储故障 |

模型任务已经成功入队后，轮询一个 `failed` run 仍返回 `200`，失败原因放在 run 的安全 `error` 对象中并使用上表稳定 code；`502/503` HTTP 状态只用于任务无法创建、同步 adapter 边界失败或状态资源自身不可用，避免把“成功读取到失败任务”误报为 HTTP 传输失败。

错误 `detail` 不包含 traceback、SQL、数据库路径、prompt、证据 quote、模型原始错误或 secret。

## 15. RAG/GraphRAG 适配与交接

复核服务消费现有不可变 `EvidencePack`，不再次调用 QueryService。来源模式由 EvidencePack 的 profile/trace 决定：

| profile | 复核行为 |
| --- | --- |
| `rag_only` | 只展示/发送 `rag_text` 证据；不得静默使用图证据 |
| `graphrag_local_only` | 只展示局部关系证据 |
| `graphrag_global_only` | 只展示社区/全局证据 |
| `graphrag_only` | 使用允许的 graph/community 证据，不加入文本 fallback |
| `combined` | 同时展示文本、关系和社区证据，并保留来源类型 |
| `custom` | 严格按 `evidence_types`；不自动补来源 |
| `auto` | 展示上游最终解析 profile 和降级 warning，不在复核层重新路由 |

多来源冲突不能由模型静默解决。模型可以输出 `conflicts` 和建议，但只有人工决定可以接受当前冲突表达、请求补证或驳回。

交接合同：

```text
上游 RAG/GraphRAG
  输出：FmeaRow + EvidencePack + ReviewSourceSnapshot + trace

本复核接口
  输出：ReviewSuggestion + ReviewDecision + EvidenceRequestItem + AuditEvent

后续评分/批准/发布
  输入：accepted FmeaRow revision + review history
```

`EvidenceRequestItem` 的目标模块由后续编排映射为 M1/M2/M3/M4/M5 问题；本服务不直接修复上游。

## 16. 安全与隐私

必须覆盖：

- prompt injection 不能改变模型工具、角色、provider、审核或发布权限；
- 模型输出中的未知字段、状态、ID、actor、SQL、URL 或 tool request 必须严格拒绝；
- EvidencePack 之外的 evidence ID 必须失败关闭；
- 外部模型只收到最小证据投影；
- HTTP/CLI/log/audit 不泄漏 token、API Key、路径、原始 provider error 或 EvidencePack 私有元数据；
- rationale/reason/label/value 具备长度、Unicode 控制字符和 JSON 深度上限；
- 单次 run 的证据数量、字符数、输出 token、HTTP attempts、总时长和并发量有硬上限；
- SQLite 路径由 workspace registry 决定，客户端不能提交；
- 所有 SQL 参数化，迁移文件固定且不由模板生成。

## 17. 测试策略

### 17.1 领域与合同单元测试

- 五种 action 的输入不变量和状态映射；
- 字段白名单、类型、replace-only 和禁止字段；
- known/evidence/support 组合规则；
- 行级 claim status 保守聚合；
- accepted/rejected 当前 revision 终态；
- model actor 无法提交人工决定；
- publication 始终保持 unpublished；
- source snapshot 缺失时不能 accept；
- unresolved acknowledgement 要求；
- 严格 JSON decode 拒绝模型额外字段和越权字段。

### 17.2 SQLite 集成测试

- 从空库按顺序迁移且不触碰 GraphStore；
- foreign keys、WAL 和 busy timeout 生效；
- decision + row + version + audit 原子成功/回滚；
- stale version 零写入；
- 相同幂等请求单创建，key 冲突返回 409；
- suggestion/decision/audit 不可更新和删除；
- 服务重启后 run 状态、suggestion 和 history 可恢复；
- 并发两个 reviewer 只有一个成功写入。

### 17.3 模型建议测试

- fake model valid suggestion；
- malformed JSON、额外字段、pack 外 evidence、超长 rationale；
- provider timeout/401/429/5xx 和有界重试；
- row 更新后完成的 suggestion 标记 stale；
- 模型建议成功或失败均不改变 row；
- RAG-only、GraphRAG-only、combined 使用同一模板和服务；
- 自动测试不调用真实付费 API；
- 单独 live DeepSeek 命令使用用户环境变量并输出安全摘要。

### 17.4 REST/CLI 契约测试

- `ETag/If-Match`、`Idempotency-Key`、Location 和状态码；
- 401/403/404/409/412/422/428/429/502/503 problem detail；
- REST 与 CLI 对相同服务结果输出等价资源字段；
- CLI stdout 单 JSON，stderr 无敏感信息；
- request body 伪造 actor/role/model/status 被拒绝；
- 没有评分、批准、发布或撤回路由/命令。

### 17.5 安全回归

- 模型请求“接受/发布该行”不会产生人工决定；
- evidence quote 中的指令不会改变系统 prompt 或工具范围；
- token/API Key/private marker 在输出、日志、审计和 fixture 中计数为零；
- 目录遍历、SQLite path 注入、SQL 注入和超深 JSON 被拒绝；
- local auth 在非 loopback 监听时失败关闭。

## 18. 验收标准

实现完成必须同时满足：

1. reviewer 可读取包含人类可读 item/function、字段证据、来源 profile 和历史的 review context；
2. 模型建议接口返回持久化 async run，完成后产生不可变 suggestion；
3. 模型建议无论成功、失败或 stale 都不能改变 FMEA 行；
4. human reviewer 可执行五种 action，且状态、证据和字段规则符合本设计；
5. modify_and_accept 在一个事务内保存决定、行、版本和审计；
6. stale `If-Match`、幂等冲突和越权请求零写入；
7. accepted/rejected 行不能在原 revision 内编辑或重开；
8. 所有结果保持 `publication_status=unpublished`，且没有 S/O/D/RPN/批准/发布接口；
9. `rag_only`、`graphrag_only` 和 `combined` fixture 均通过同一复核链路；
10. 补证请求可作为稳定 JSON 交给上游，复核服务不修改资料库或图谱；
11. REST 和 CLI 均使用 `graphrag.fmea.v1` envelope 和同一 `ReviewService`；
12. 自动测试离线通过，显式 live DeepSeek 复核测试只在用户配置 Key 时运行；
13. 安全扫描确认 token、API Key、private marker、路径和原始 provider error 不泄漏；
14. 全仓已知 GraphRAG global-search 基线失败单独报告，不归因于本复核切片。

## 19. 预计实现边界

后续实施计划可以创建或修改：

```text
fmea_application/review_contracts.py
fmea_application/review_service.py
fmea_application/review_template_adapter.py
fmea_application/ports.py
fmea_application/service_factory.py
fmea_application/structured_candidate_adapter.py
fmea_infrastructure/repository_sqlite.py
fmea_infrastructure/local_auth.py
fmea_infrastructure/migrations/*.sql
api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/fmea_review_contracts.py
api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/routes_fmea_review_v1.py
api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/api.py
scripts/fmea_skill.py
templates/examples/fmea-row-review.yaml
tests/unit/test_fmea_review_*.py
tests/integration/test_fmea_review_*.py
tests/regression/test_fmea_review_security.py
```

若 `SqliteFmeaRepository` 尚不存在，先实现 review 所需的最小 analysis/evidence/row/source snapshot 基础，再实现建议与决定。不得为追求一次完成而顺带加入 publication、评分、传播、浏览器 UI 或导出。

## 20. 开源对照与项目独特性

### 20.1 可借鉴部分

- Argilla 将模型 suggestion 与人工 response 分离；本设计采用相同责任分离，防止模型预测覆盖人工标注。
- LangGraph human-in-the-loop 使用 approve/edit/reject、持久化暂停和恢复；本设计采用 durable run、显式人工决定和重放语义，但不依赖 LangGraph runtime。
- OpenLineage 使用结构化追加事件表达运行事实；本设计使用不可变 AuditEvent 保存 actor、版本、hash 和 trace。

### 20.2 本项目增加的 FMEA 特性

- 将普通 RAG、GraphRAG-only 和组合检索统一到 EvidencePack/profile，不在复核层重新路由；
- 每个专业字段绑定 pack 内 evidence ID 和支持状态；
- 模型建议、人工决定、声明状态、审核状态、发布状态严格分离；
- `request_evidence` 直接产生可回流 M1-M5 的结构化请求；
- 接受未知/冲突不等于消除未知/冲突，必须显式 acknowledgement；
- 对 row 使用乐观锁，对命令使用幂等，对审计使用 before/after hash；
- item/function 哈希身份与人工可读来源快照分离，避免为界面便利破坏稳定 ID；
- 模板引擎可迁移到其他领域，但 FMEA 字段白名单、证据规则和状态机保留在领域 adapter/service，不污染通用引擎。

## 21. 迁移与后续

本设计不改变现有 `graphrag.fmea.v1` schema ID，也不修改通用结构化模板根合同。新增 review resource 使用自身 `resource_type/resource_version`，因此普通查询和既有生成 CLI 不需要迁移。

后续阶段可以在 accepted FMEA row revision 之上分别增加：

1. 版本化 S/O/D 和确定性 RPN；
2. 传播边与公共原因复核；
3. revision 批准、发布和撤回；
4. 浏览器复核工作台；
5. JSON/XLSX/Word 同快照导出；
6. 企业认证 provider。

这些后续能力必须消费本设计的稳定决定和审计记录，不得让评分或发布接口绕过人工复核服务。

## 22. 官方参考

- Argilla Records/Suggestions：https://docs.argilla.io/latest/reference/argilla/records/suggestions/
- Argilla Record workflow：https://docs.argilla.io/latest/how_to_guides/record/
- LangChain Human-in-the-loop：https://docs.langchain.com/oss/python/langchain/human-in-the-loop
- LangGraph Interrupts：https://docs.langchain.com/oss/python/langgraph/interrupts
- LangGraph Persistence：https://docs.langchain.com/oss/python/langgraph/persistence
- OpenLineage Object Model：https://openlineage.io/docs/spec/object-model/
- OpenLineage Schemas：https://openlineage.io/docs/spec/schemas/
