# FMEA 风险闭环交接文档（Phase 1）

## 1. 本阶段交付了什么

本阶段把燃料系统、燃烧系统 FMEA 从“模型可以提出字段”推进到可审计的风险闭环：

1. RAG 或 GraphRAG 只负责形成不可变 `EvidencePack`。
2. 大模型根据受限证据和评分锚点提出 S/O/D 候选值，但不能计算并写入最终权威状态。
3. 确定性领域代码校验证据、DomainPack 和评分规则，再计算 RPN 与优先级。
4. 只有带 `risk_reviewer` 角色的人类可以确认或拒绝。
5. 行版本、EvidencePack、DomainPack、模板、规则或运行上下文变化后，已确认风险会转为 `invalidated`，不会静默保持“已确认”。
6. REST、CLI、离线验收包和独立校验器使用同一组版本化资源语义。

模型参与的是建议，不是审批。人工可以借助大模型解释冲突、起草范围或生成候选，但最终确认动作仍必须由人类身份通过接口提交。

## 2. RAG 与 GraphRAG 的统一方式

风险层不导入 Chroma、图数据库或具体检索实现。上游统一交付 `EvidencePack`，其中每条证据包含来源类型、定位信息、引用文本、内容哈希和 ACL。

离线验收覆盖以下模式：

| 验收模式 | 典型证据来源 |
| --- | --- |
| `rag_only` | 主文档与文本检索 |
| `graphrag_local` | 主文档与局部关系路径 |
| `graphrag_global` | 主文档与社区摘要 |
| `graphrag_only` | 局部关系与社区摘要 |
| `combined` | 文本、关系和社区联合证据 |
| `auto` | 上游自动选择后形成的固定证据包 |
| `custom` | 调用者预先声明的受限证据组合 |

模式只改变 EvidencePack 的来源集合，不改变 FMEA 服务、评分或人工确认逻辑。因此后续替换向量库、图数据库或 GraphRAG 实现时，不需要重写风险模块。

## 3. 默认运行时装配

API 和 CLI 会为每个工作区创建共享 SQLite 风险运行时，并自动注册仓库 `domain_packs/*/manifest.yaml` 以及对应 `scoring/*.yaml`。模型网关是惰性创建的：查看已有风险、人工确认和离线验收不需要 `DEEPSEEK_API_KEY`；只有真正生成建议时才访问外部模型。

通用 assistance 的 `reject`、`defer`、`request_evidence` 可由默认运行时记录。`adopt`、`partial_adopt`、`edit_and_adopt` 会在没有领域写入处理器时安全失败，因为不同领域的分析对象更新方式不同。接入新领域时应注册显式、幂等、可审计的 typed handler，不能让通用层猜测如何修改业务数据。

## 4. 本地配置

在启动 API 或 CLI 的同一个 PowerShell 进程中配置：

```powershell
$env:RAG_WORKSPACE_CONFIG = "C:\path\to\workspaces.json"
$env:FMEA_LOCAL_AUTH_ENABLED = "true"
$env:FMEA_REVIEW_TOKEN = "local-review-token-placeholder-0001"
$env:FMEA_REVIEW_ACTOR_ID = "reviewer-1"
$env:FMEA_REVIEW_WORKSPACE_ID = "ws-1"
```

示例工作区：

```json
{
  "allowed_root": "runtime",
  "workspaces": {
    "ws-1": {
      "chroma_persist_dir": "runtime/chroma",
      "chroma_collection": "workspace",
      "graph_db_path": "runtime/graph/graph.sqlite3",
      "fmea_db_path": "runtime/fmea/fmea.sqlite3",
      "fmea_template_registry_path": "runtime/fmea/templates",
      "supported_modes": ["vector", "local", "global", "hybrid"],
      "default_mode": "hybrid"
    }
  }
}
```

数据库、图存储和模板注册目录必须位于 `allowed_root` 内且互不重叠。FMEA 本地鉴权只接受 loopback 请求，不应把本地 token 接口直接暴露到不可信网络。

## 5. CLI 使用示例

查看风险：

```powershell
.venv\Scripts\python.exe scripts\fmea_skill.py risk show --row-id row-1
```

请求模型生成风险候选：

```powershell
.venv\Scripts\python.exe scripts\fmea_skill.py risk propose `
  --row-id row-1 --record-version 1 `
  --evidence-pack-id pack-1 `
  --domain-pack-id fuel-combustion --domain-pack-version 1.0.0 `
  --template-id fuel-combustion-fmea --template-version 1.0.0 `
  --rule-pack-id fuel-sod-rpn --rule-pack-version 1.0.0 `
  --idempotency-key 00000000-0000-4000-8000-000000000201
```

确认请求文件：

```json
{
  "row_id": "row-1",
  "proposal_id": "proposal-1",
  "expected_assessment_version": 1,
  "idempotency_key": "00000000-0000-4000-8000-000000000202"
}
```

人工确认：

```powershell
.venv\Scripts\python.exe scripts\fmea_skill.py risk confirm `
  --request-file .local\risk-confirm.json `
  --confirm-human-risk-review
```

所有 CLI 命令只输出一个有界 JSON 对象，不接受 API Key、provider、endpoint、prompt 或模型覆盖参数。

## 6. REST 使用示例

查看：

```powershell
curl.exe http://127.0.0.1:8000/api/v1/fmea/rows/row-1/risk `
  -H "Authorization: Bearer local-review-token-placeholder-0001"
```

生成候选：

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/v1/fmea/rows/row-1/risk-proposal-runs `
  -H "Authorization: Bearer local-review-token-placeholder-0001" `
  -H 'If-Match: "1"' `
  -H "Idempotency-Key: 00000000-0000-4000-8000-000000000201" `
  -H "Content-Type: application/json" `
  -d '{"evidence_pack_id":"pack-1","domain_pack_id":"fuel-combustion","domain_pack_version":"1.0.0","template_id":"fuel-combustion-fmea","template_version":"1.0.0","rule_pack_id":"fuel-sod-rpn","rule_pack_version":"1.0.0"}'
```

确认：

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/v1/fmea/rows/row-1/risk-confirmations `
  -H "Authorization: Bearer local-review-token-placeholder-0001" `
  -H 'If-Match: "1"' `
  -H "Idempotency-Key: 00000000-0000-4000-8000-000000000202" `
  -H "Content-Type: application/json" `
  -d '{"proposal_id":"proposal-1"}'
```

写接口必须同时提供 `If-Match` 和 canonical UUID `Idempotency-Key`。POST 请求体上限为 256 KiB。

## 7. 离线验收与独立校验

运行一个模式：

```powershell
.venv\Scripts\python.exe scripts\run_fmea_risk_acceptance.py --retrieval-mode combined
.venv\Scripts\python.exe scripts\verify_fmea_risk_acceptance.py --latest
```

runner 先在目标目录内部创建临时目录，写入并哈希以下文件，全部完成后才原子改名：

- `analysis-scope-suggestion.json`
- `proposal.json`
- `confirmation.json`
- `invalidation.json`
- `audit-summary.json`
- `acceptance-summary.json`

verifier 仅使用 Python 标准库，重新验证 canonical JSON、文件集合、EvidencePack 哈希、建议目标与版本绑定、`applied=false`、S/O/D、RPN、未知/冲突阻断、人工确认、幂等回放、系统失效、事件哈希和秘密标记。任何缺失、额外、重复案例、非规范 JSON 或篡改都会失败关闭。

## 8. 可选真实 DeepSeek 测试

仅在离线门禁全部通过后配置：

```powershell
$env:DEEPSEEK_API_KEY = "在当前进程中设置真实密钥"
```

随后使用前面的 `risk propose` 命令。当前模型链路固定为 `deepseek-v4-flash` 生成、`deepseek-v4-pro` 批评，并在需要时最多进行一次 Pro 修复。密钥只能放在进程环境中，不能写入 workspace JSON、EvidencePack、模板、请求文件、日志、验收包或提交。

真实模型成功只证明外部调用和结构化解码可用，不代表评分正确，也不构成安全认证。

## 9. 接入新领域、新模板和人工工具

接入新领域时：

1. 新建 `domain_packs/<领域>/manifest.yaml`，使用新的不可变 `id + version + content_hash`。
2. 在 `scoring/` 下提供评分规则；修改锚点或策略必须升级版本，不能覆盖旧身份。
3. 注册对应结构化输出模板，保持模型只输出候选字段。
4. 如果要采纳 analysis assistance，提供 typed handler，把建议转换成领域命令，并实现幂等写入与版本检查。
5. 为新领域增加固定 EvidencePack、未知、冲突、确认和失效验收案例。
6. 复用现有 runner/verifier 合同，不把新检索后端导入 FMEA 内核。

新模板的主要难度不是 YAML 本身，而是字段语义、证据绑定、版本迁移、人工采纳处理器以及验证规则。模板映射可以由大模型或人工工具起草，但编译、注册和生效必须是确定性且可复核的操作。

## 10. 明确限制

- 固定夹具一致不等于工业认证。
- 示例 S=9、O=3、D=4、RPN=108 只用于软件验收。
- 项目不会自动批准风险，也不会替代 FMEA 主持人、领域专家或安全责任人。
- 现场工况、法规、组织评分表和失效后果必须由实际项目重新确认。
- 默认通用运行时不会猜测如何把 assistance 建议写入任意领域对象；需要显式 typed handler。
