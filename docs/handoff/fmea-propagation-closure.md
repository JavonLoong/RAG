# FMEA propagation closure handoff

这是传播闭环的 Phase 2 acceptance/security gate。验收 runner 使用固定的
fuel/combustion DomainPack、propagation rule pack、topology snapshot 和
EvidencePack lineage fixture；模型部分是确定性的 offline fixture，不会调用
网络、付费模型或真实 DeepSeek。传播层只消费不可变 EvidencePack 及其 lineage，
不连接 retrieval backend、`retrieval_engine`、`kg_pipeline`、
`rag_orchestrator` 或 GraphRAG backend。

## 运行与验证

在 worktree 根目录使用项目环境：

```powershell
.venv\Scripts\python.exe scripts\run_fmea_propagation_acceptance.py
.venv\Scripts\python.exe scripts\verify_fmea_propagation_acceptance.py --latest
```

runner 先在目标 artifact 的同一父目录创建唯一临时目录，写入并完成全部
canonical/hash/语义检查，并调用独立 verifier 验证完整 artifact 后，才用原子
rename 发布。失败会清理临时目录，不创建半成品，也不修改已有目录。runner
不会在尚未完成 component-wise containment/reparse 检查前创建输出父目录。
verifier 不调用 runner 的验证函数，而是从每个
JSON 文件的 bytes 重新检查 UTF-8、重复 key、canonical JSON、文件集合、hash
manifest、topology/rule/graph identity、lineage、路径连续性、逐 edge evidence、
深度、cycle、risk、external、conflict、incomplete 和 actor policy。文件大小、
secret/private marker 和 raw-provider marker 保持 bytes-first 检查；本机路径则在
strict JSON parse 后递归检查 decoded string values，避免把 `\n` 等 JSON escape
误判成 Windows 路径。embedded path 可从字符串起点或任意非 path-body 字符后
开始；path-body 固定为 alphanumeric、underscore、dot、slash 和 backslash，
不维护 delimiter 枚举。HTTP/HTTPS URL span 内的 path-like 片段被排除，但同一
字符串在 URL span 外出现的本机路径仍会被拒绝。

topology identity 还绑定到仓库中固定 source-pinned 的
`domain_packs/fuel-combustion/topology/demo-1.0.0.json`：verifier 重新读取其
raw/canonical hash，并将规范化 snapshot 与 artifact 对比，因此不能通过同时
重写 artifact hash、graph hash 和 manifest 来制造自洽的伪 topology。

固定 artifact 集合及语义为：

| 文件 | 语义 |
| --- | --- |
| `topology.json` | topology snapshot、DomainPack/rule identity、七种证据 profile 和 immutable EvidencePack lineage |
| `proposal.json` | deterministic model proposal；endpoint/relation/evidence 均绑定公开 topology/rule/pack |
| `reviewed-graph.json` | review 后的 immutable graph revision；safe forward/reverse 可由 human reviewer confirm，其余保留 `in_review` |
| `paths.json` | 五类 path 的 edge 快照；每个 edge 必须有自己的 evidence IDs |
| `decisions.json` | 每个 case 一个决定；actor identity/type/role 固定绑定 authoritative human `propagation_reviewer` |
| `issues.json` | long/cyclic/high-risk/external/conflicting/incomplete/evidence-gap 问题 |
| `audit-summary.json` | 按顺序连接的 proposal/review 事件；review actor 必须匹配对应 decision actor，并校验 `previous_event_hash`、chain head 及 hash |
| `acceptance-summary.json` | manifest 与可重算计数；`invented_endpoint_count=0`、`model_confirmation_count=0` |

artifact schema 固定为
`graphrag.fmea.propagation.acceptance.v1`，case 集合恰为
`forward`、`reverse`、`cycle`、`conflict`、`long_path`。默认自动深度为 2；
long/cycle/high-risk/external/conflict/incomplete/evidence-gap 永远进入人工
review，不能被 model actor 确认。当前 fixture 中 forward/reverse 是两条可
确认的短路径，其余三类明确保留人工 review。

每个 evidence profile 都绑定完整 VersionSet（包括 data/graph/template/
scoring/prompt/model/input snapshot identity）以及 deterministic offline
model、network/paid-model 禁止项、token budget 和 edge/path/evidence caps。
`auto` 的 resolved profile 必须是 `combined`；`paid-live-model` 或
`pack-combined` 的 `profile_version=auto` 均不能通过 verifier。

## REST、CLI 与人工复审

REST adapter 对应：

```text
POST /api/v1/fmea/analyses/{analysis_id}/propagation-runs
GET  /api/v1/fmea/propagation-runs/{run_id}
GET  /api/v1/fmea/propagation-graphs/{graph_revision_id}
GET  /api/v1/fmea/propagation-graphs/{graph_revision_id}/paths
POST /api/v1/fmea/propagation-graphs/{graph_revision_id}/reviews
```

CLI 对应 `propagation start`、`status`、`show`、`paths`、`review`。两者都只是
application service adapter：使用 workspace actor、Idempotency-Key、版本/游标
约束和安全错误 envelope；`review` 需要显式 human confirmation、human actor
和 `propagation_reviewer` role。CLI 的 failed run 使用非零退出码，REST/CLI
不会接受客户端 topology/domain/rule resource override，也不直读 SQLite。

人工复审者必须逐 edge 检查 endpoint、interface variable、unit、direction、
operating mode、timing、barrier、风险等级和对应 EvidencePack 引用；逐 path
确认连续性与 cycle/depth；对冲突、外部依赖、证据不足和未处理项记录理由与
acknowledgement。人工确认只创建新的 graph revision，并与 audit/outbox
transactional commit；不能把 model suggestion 当成 authority，也不能因
summary 计数而跳过原始 artifact 检查。

## 七种证据输入

验收覆盖 `rag_only`、`graphrag_local_only`、`graphrag_global_only`、
`graphrag_only`、`combined`、`auto -> combined`、`custom`。profile 只记录
requested/resolved profile、证据类型、EvidencePack ID/hash 和 incomplete
状态。新增 retrieval 能力时，上游团队应先产生新的 immutable EvidencePack
及可验证 lineage；传播团队只接收该 pack，不在传播代码中重新 query 或拼接
检索结果。

## 扩展 DomainPack、模板、拓扑和 rule pack

新增 DomainPack 时，为新的 `(pack_id, version)` 提供 manifest、模板 identity、
propagation rule identity 和内容 hash，并让 composition/runtime 以 server-owned
配置绑定它。新增模板必须使用新的 immutable identity/version，不能覆盖同一
identity 的既有 bytes。新增 topology 时提供 canonical snapshot、稳定 identity、
source hash pin、所有 endpoint/interface 和 topology hash；新增 rule pack 时
声明 analysis types、relation/interface/unit/direction、timing、mandatory
review conditions、风险升级和 `max_automatic_depth=2`，并通过 registry 的
公开 loader/identity 检查。随后为新的 fixture case 添加独立 evidence、path
continuity、human decision、audit 和 tamper regression；不要修改既有 case 的
含义来“通过” gate。

## 交接边界与辅助工具

上游 RAG/GraphRAG 团队负责 EvidencePack、ACL、source type、版本和 lineage；
DomainPack/rule/topology 团队负责 immutable resource identity 与 source pins；
传播 application 团队负责 candidate、path、review、idempotency 和 atomic
audit/outbox；REST/CLI 团队负责 transport parity、auth、错误映射和分页。此
acceptance gate 只消费这些公开/application/composition interfaces，不改写上述
业务规则或 backend。

脚本、静态检查器和大模型可以辅助生成 fixture、列出路径、发现缺失证据、审阅
差异和提出风险分类；它们不能替代 human `propagation_reviewer` 的 authority，
不能写入 confirmed graph，也不能绕过 EvidencePack、lineage、版本或 audit。

Windows 上 symlink/reparse 创建可能因开发者模式、管理员权限或策略而失败；
测试会对该平台动作做精确 skip，不声称特权 symlink 已验证。无特权的
component-wise 路径检查仍会验证：普通目录可接受、普通文件组件和 link/reparse
组件均拒绝；其中 Windows `FILE_ATTRIBUTE_REPARSE_POINT` 分支通过确定性 seam
常驻验证。artifact 中还会拒绝精确 POSIX root、任意 POSIX absolute、Windows
drive absolute、UNC 和 root-relative path；普通 prose 中不构成本机绝对路径
token 的斜杠及 multiline 文本不受影响。whole-value `/ foo/bar` 和精确单反斜杠
root 仍按本机绝对/root-relative 路径拒绝。生产部署仍应在具备相应 Windows
policy 的环境补跑真实 reparse 覆盖。
