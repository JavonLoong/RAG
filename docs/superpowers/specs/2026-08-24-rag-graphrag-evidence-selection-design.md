# RAG + GraphRAG 多来源证据选择与 FMEA 交接设计

> 状态：用户已于 2026-08-24 确认。本文是接口与责任边界规格，不是实施完成声明。
>
> 上位规格：`docs/superpowers/specs/2026-08-23-graphrag-fmea-system-design.md`

## 1. 目标

在不破坏现有 `graphrag.query.v1` 默认行为的前提下，为证据型调用增加以下可显式选择的检索组合：

- 普通 RAG only；
- GraphRAG local only；
- GraphRAG global only；
- GraphRAG only；
- 普通 RAG + GraphRAG combined；
- auto；
- 由调用方指定证据类型的 custom 组合。

FMEA 使用同一选择能力建立一次不可变 `EvidencePack`，但不拥有普通 RAG 索引、GraphRAG 图谱构建或通用检索算法。

## 2. 已确认的现有基础

当前 `QueryService` 已支持：

- `QueryMode.VECTOR`：文本/向量检索；
- `QueryMode.LOCAL`：文本检索、图关系检索和回答生成；
- `QueryMode.GLOBAL`：社区级 GraphRAG 检索；
- `QueryMode.HYBRID`：文本、图关系、社区和回答生成；
- `CitationType.TEXT`、`CitationType.GRAPH`、`CitationType.COMMUNITY` 的统一输出。

现有模式同时表达“检索哪些来源”和“怎样生成答案”。FMEA 只需要可审核证据，不应为了取得 Citation 再执行一次最终答案生成，也不应通过连续调用 `VECTOR + LOCAL + GLOBAL` 重复检索文本。

## 3. 功能归属

### 3.1 结论

多来源选择横跨通用查询接口和 FMEA 证据适配，不能整体算作 FMEA 功能。

| 能力 | 模块归属 | 本工作责任 | 不属于本工作 |
| --- | --- | --- | --- |
| 文档切片、向量索引、关键词/语义检索 | M3 资料库构建 | `DEPEND`：消费稳定 TEXT Citation | 重建索引、调 embedding、资料发布 |
| 实体关系、社区、图路径和 GraphRAG 检索 | M4 GraphRAG 构建 | `DEPEND`：消费稳定 GRAPH/COMMUNITY Citation | 实体抽取、图谱融合、社区算法、GraphStore 优化 |
| 查询请求、证据选择、统一 Citation 和降级错误 | M5 任务输出接口 | `OWN/INTEGRATE`：定义向后兼容合同和适配测试 | 替代 M3/M4 的检索内部实现 |
| Citation 到 EvidenceRef/EvidencePack | FMEA 证据闭环 | `OWN`：规范化、去重、ACL、版本、哈希和快照 | 修改原始资料或图谱事实 |
| FMEA 候选、未知/冲突、评分、审核和发布 | FMEA 领域与应用层 | `OWN` | 自动代替专家批准或安全责任签字 |
| 全流程调度、质量门和跨模块总验收 | M6 | `INTEGRATE`：提供稳定测试入口和 manifest | 维护全项目流水线 |

### 3.2 可计入 FMEA 的工作

- `EvidenceSelectionProfile` 在 FMEA 请求中的使用；
- Citation 到 EvidenceRef 的无损映射；
- 同一 workspace、ACL 和 VersionSet 下建立一个 EvidencePack；
- 证据缺失、来源降级、冲突和不完整快照的显式状态；
- 证据 ID 与 FMEA 字段、传播边的绑定；
- 审核、发布和审计边界。

### 3.3 不计入 FMEA 的工作

- Chroma 或其他向量库建库；
- 普通 RAG 召回、rerank 和 embedding 实现；
- GraphRAG 实体/关系/claim 抽取；
- Leiden 社区检测和社区报告生成；
- GraphStore 建库、图融合、别名治理和路径算法优化；
- 通用问答提示词与回答模型效果调优。

## 4. 方案选择

### 4.1 未采用：不断增加 QueryMode

直接增加 `rag_only`、`graphrag_only`、`local_graph_only` 等 QueryMode 虽然直观，但会把证据来源、检索策略和回答策略继续绑定，模式数量随新来源增长。

### 4.2 未采用：只增加单一 retrieval_profile

单一 profile 能覆盖当前需求，但以后加入表格、图像、实时遥测或仿真证据时仍要继续增加枚举值，难以表达自定义组合。

### 4.3 采用：证据类型选择器 + 稳定预设

底层使用已有 `CitationType` 作为来源选择单位，上层提供稳定 profile。profile 只是常见组合的别名；custom 才允许传入具体类型。

此设计有三个好处：

1. 普通用户只选 profile，不必理解底层类型；
2. 高级调用方可以组合来源；
3. 将来新增证据类型时不必成倍增加 QueryMode。

## 5. 查询合同

### 5.1 新增枚举

```python
class EvidenceSelectionProfile(str, Enum):
    AUTO = "auto"
    RAG_ONLY = "rag_only"
    GRAPHRAG_LOCAL_ONLY = "graphrag_local_only"
    GRAPHRAG_GLOBAL_ONLY = "graphrag_global_only"
    GRAPHRAG_ONLY = "graphrag_only"
    COMBINED = "combined"
    CUSTOM = "custom"
```

### 5.2 QueryRequest 向后兼容扩展

```python
class QueryRequest(_ContractModel):
    query: str
    workspace_id: str
    mode: QueryMode = QueryMode.AUTO
    top_k: int = 5
    include_context: bool = False
    include_debug: bool = False
    evidence_only: bool = False
    evidence_profile: EvidenceSelectionProfile = EvidenceSelectionProfile.AUTO
    evidence_types: tuple[CitationType, ...] = ()
```

兼容规则：

- 老调用方不传新字段时，行为与当前 `graphrag.query.v1` 完全一致；
- `evidence_only=False` 时必须使用 `evidence_profile=auto` 且 `evidence_types=()`；
- 非 `auto` profile 仅用于 `evidence_only=True`；
- `custom` 必须提供至少一个 `evidence_types`；
- 非 `custom` 不得同时提供 `evidence_types`；
- `evidence_types` 不允许重复；
- `evidence_only=True` 时 `mode` 必须为 `AUTO`，避免来源 profile 与旧 mode 同时控制执行路径。

### 5.3 Profile 到来源的唯一映射

| Profile | Citation 类型 | 执行组件 |
| --- | --- | --- |
| `rag_only` | `TEXT` | text retriever |
| `graphrag_local_only` | `GRAPH` | graph retriever |
| `graphrag_global_only` | `COMMUNITY` | global searcher，使用 context-only |
| `graphrag_only` | `GRAPH + COMMUNITY` | graph retriever + global searcher |
| `combined` | `TEXT + GRAPH + COMMUNITY` | text retriever + graph retriever + global searcher |
| `custom` | 调用方提供 | 仅执行对应组件 |
| `auto` | 工作区可用来源 | 在证据调用中选择所有已配置来源，并记录缺失来源 warning |

`graphrag_only` 不得执行普通 RAG text retriever；`rag_only` 不得访问 GraphStore 或 global searcher。该隔离必须由 recording dependency 测试证明，不能只检查最终输出。

### 5.4 evidence_only 响应语义

继续返回现有 `QueryResponse`：

- `answer.text=""`；
- `answer.finish_reason="stop"`；
- `citations` 返回规范化证据；
- `context` 在 `include_context=True` 时返回；
- `retrieval.text_hits/graph_hits/community_hits` 保持真实计数；
- `warnings` 记录指定来源的缺失或执行失败；
- 不执行最终回答 LLM；
- global searcher 为生成已有社区级结果所需的内部调用不算“最终回答 LLM”，可以执行。
- `ModeDecision.requested/used` 均为 `AUTO`，reason 明确记录 evidence profile；证据调用不经过旧 answer router，也不借用工作区默认 answer mode 决定来源。

本次不增加新的 response schema 字段，避免旧严格客户端因额外字段拒绝 `graphrag.query.v1`。证据 profile 由请求、运行审计和 FMEA manifest 保存。

## 6. 执行和降级规则

### 6.1 显式选择不做静默跨源回退

- `rag_only` 失败：返回文本来源 warning/partial，不自动调用 GraphRAG；
- `graphrag_only` 失败：返回图来源 warning/partial，不自动调用普通 RAG；
- `combined`：任一路失败时保留其他来源并返回 partial；
- `auto`：可使用工作区已有来源，但必须在 warning 和运行审计中记录实际缺失项。

### 6.2 没有证据不是成功事实

零 Citation 可以形成不完整 EvidencePack，以便 FMEA 显式输出 `unknown` 或 `insufficient_evidence`；不得因为某一路返回空结果而生成 `known` 字段。

### 6.3 错误边界

- workspace、ACL、路径越界和版本错误：在检索前失败关闭；
- 单个检索组件故障：partial + warning；
- 所有指定组件不可初始化：返回可识别依赖错误，不调用候选生成模型；
- Citation 结构非法、缺少稳定定位且无法构造回退定位：拒绝该 Citation 并记录 warning；
- 不允许把回答文本本身作为原始证据引用。

## 7. FMEA EvidenceProvider 适配

### 7.1 请求

FMEA `EvidenceRequest` 增加：

```python
evidence_profile: EvidenceSelectionProfile
evidence_types: tuple[CitationType, ...] = ()
```

默认 profile 为 `combined`，因为项目目标明确是普通 RAG + GraphRAG；测试或用户可显式选择其他 profile。

EvidenceProvider 返回轻量包装对象，而不是丢弃查询运行信息：

```python
@dataclass(frozen=True, slots=True)
class EvidenceSnapshot:
    pack: EvidencePack
    profile: EvidenceSelectionProfile
    source_counts: tuple[tuple[CitationType, int], ...]
    warnings: tuple[str, ...]
    incomplete: bool
```

`EvidencePack` 只保存工程证据；profile、命中计数和降级 warning 由 `EvidenceSnapshot` 交给 run audit/suggestion ledger。后续候选流水线使用 `snapshot.pack`，不得把 warning 文本混入 EvidenceRef。

### 7.2 单次查询

`QueryServiceEvidenceProvider.create_snapshot()` 对一个 EvidenceRequest 只构造一个 `QueryRequest`，并返回 `EvidenceSnapshot`：

```python
QueryRequest(
    query=request.query,
    workspace_id=request.workspace_id,
    mode=QueryMode.AUTO,
    top_k=request.max_hits,
    include_context=True,
    include_debug=False,
    evidence_only=True,
    evidence_profile=request.evidence_profile,
    evidence_types=request.evidence_types,
)
```

不得再通过 `VECTOR + LOCAL + GLOBAL` 三次调用拼接同一快照。

### 7.3 Citation 到 EvidenceRef

| Citation | EvidenceRef.source_type | 必须保留 |
| --- | --- | --- |
| `TEXT` | `rag_text` | document_id、file、page、chunk_id、quote |
| `GRAPH` | `graphrag_relation` | triple、edge/triple ID、source document、quote、graph version |
| `COMMUNITY` | `graphrag_community` | community ID、title、quote、community metadata、graph version |

检索 score、rank 和未经过允许列表筛选的原始 metadata 是查询运行信息，不是工程证据真值，不写入 `EvidenceRef`。它们保存在 run audit/suggestion ledger。GRAPH 只将 subject、predicate、object、edge/triple ID 纳入稳定 locator；COMMUNITY 只将 community ID 和 title 纳入稳定 locator。这样无需扩大当前 EvidenceRef schema，也避免上游任意 metadata 进入 FMEA 数据库。

如果上游没有 document_id，使用带命名空间的稳定回退 ID：

- `text:<workspace_id>:<citation_id>`；
- `graph:<graph_version>:<citation_id>`；
- `community:<graph_version>:<citation_id>`。

回退 ID 表示技术来源对象，不得伪装成原始文档 ID。UI 和导出必须显示 source_type。

### 7.4 去重与身份

不能只按 quote 去重。证据身份至少包含：

```text
source_type
+ document_id
+ locator
+ normalized_quote
+ graph/document version
```

相同文字出现在不同页、不同版本或不同来源类型时保留为不同 EvidenceRef。完全相同身份的重复 Citation 合并；score、rank 和原始 metadata 仅在 run audit 中按命中次序保存。稳定 locator 所需的允许列表字段发生冲突时保留两条证据并标记冲突，不静默覆盖。

### 7.5 快照

所有来源必须进入同一个：

- `workspace_id`；
- ACL scope；
- `VersionSet.data_version`；
- `VersionSet.graph_version`；
- input snapshot hash；
- EvidencePack hash。

普通 RAG 和 GraphRAG 结果不得各自建立一个可被独立替换的 pack 后再由模型临时混合。

## 8. 是否已有同链路开源实现

### 8.1 核实结论

截至本规格编写时，根据下列官方资料，没有找到一个开源项目同时实现完整链路：

```text
普通 RAG + GraphRAG 可选取证
→ 字段级 EvidencePack
→ FMEA S/O/D/RPN
→ 故障传播
→ unknown/conflict
→ 人工审核
→ 版本一致发布
```

这是基于公开官方能力的比较结论，不代表不存在未公开或未检索到的实现。

### 8.2 可复用部分

| 开源项目 | 可复用能力 | 缺失的本项目链路 |
| --- | --- | --- |
| Microsoft GraphRAG | TextUnit、Entity、Relationship、Claim、Community 及 text-unit 来源 | 没有 FMEA 字段级 EvidencePack、S/O/D、人工审核/发布状态 |
| Neo4j GraphRAG | Vector/Hybrid/Cypher retriever 和向量命中后的图遍历 | 没有 FMEA 状态机、证据快照和安全发布门 |
| Graphiti | episode provenance、自定义边、双时态和增量失效 | 没有 FMEA 评分、两跳审核和发布责任链 |
| NASA fmdtools | 模型驱动故障注入、传播、场景历史和 FMEA-style 仿真分析 | 不是文档 RAG/GraphRAG，不提供字段级原文证据和审核发布流程 |

### 8.3 项目可声明的独特性

不把“使用 RAG + GraphRAG”单独宣称为创新。可声明的是：

1. 对普通文本、图关系和社区证据进行显式、可复现的来源选择；
2. 将多来源 Citation 固化到同一不可变 EvidencePack；
3. 把证据身份、字段状态、风险、传播、人工审核和发布版本串成一个责任闭环；
4. 明确允许模型介入候选和人工工具，但禁止模型越过 accepted/published 边界。

官方参考：

- Microsoft GraphRAG outputs：https://microsoft.github.io/graphrag/index/outputs/
- Microsoft GraphRAG dataflow：https://microsoft.github.io/graphrag/index/default_dataflow/
- Neo4j GraphRAG retrievers：https://neo4j.com/docs/neo4j-graphrag-python/current/user_guide_rag.html
- Graphiti overview：https://help.getzep.com/graphiti/getting-started/overview
- NASA fmdtools simulation：https://nasa.github.io/fmdtools/docs-source/fmdtools.sim.html
- NASA fmdtools analysis：https://nasa.github.io/fmdtools/docs-source/fmdtools.analyze.html

## 9. 与他人工作的交接设计

### 9.1 上游交给本工作的最小合同

M3/M4 只需交付 `QueryService` 可调用的 retriever/searcher，并输出现有 Citation 合同：

- TEXT：稳定 document/chunk/page/quote；
- GRAPH：稳定 triple/edge ID、source document 和 quote；
- COMMUNITY：稳定 community ID、summary/quote 和 graph version；
- 统一 workspace 能力声明和明确 warning/error。

上游不需要导入 `core_domain.fmea`，也不需要计算 FMEA 状态。

### 9.2 本工作交给下游的最小合同

向 FMEA 候选流水线、UI、导出和 M6 交付：

- `EvidenceSelectionProfile` 和请求校验规则；
- 一个包含不可变 EvidencePack、profile、source counts、warnings 和 incomplete 的 EvidenceSnapshot；
- 每条 EvidenceRef 的 source_type、locator、版本和 hash；
- 实际命中的来源计数；
- 降级 warning 和不完整快照标识；
- recording dependency 合同测试；
- deterministic fixtures：RAG-only、GraphRAG-only、combined、单路失败和零证据。

### 9.3 可替换性

任何同事可以替换：

- Chroma 为其他向量库；
- 当前 GraphStore 为 Neo4j/NetworkX/其他图后端；
- 当前 GraphRAG 实现为 Microsoft GraphRAG、LightRAG 或自研实现；
- 外部模型供应商。

替换方只需通过 Citation 合同测试和 workspace/version/ACL 约束，不得修改 FMEA 领域对象。

### 9.4 冲突和变更管理

- Citation 字段变更先走查询接口版本和合同测试；
- EvidenceRef/FMEA 字段变更走 FMEA schema 版本；
- GraphStore 内部变更不得直接修改 FMEA 数据库；
- 新增证据类型先扩展 CitationType 和映射测试，再由 profile 选择；
- 已发布 EvidencePack 不迁移覆盖，只创建新 pack/revision；
- 交接文档必须列出接口版本、fixture 版本、已知 warning 和未支持来源。

## 10. 验收标准

### 10.1 查询合同

- 老 QueryRequest 回归结果不变；
- 每个 profile 只调用指定组件；
- custom 组合严格按 evidence_types 调用；
- evidence-only 不调用最终回答 LLM；
- explicit profile 不做静默跨源回退；
- Citation 类型、来源和命中计数正确；
- 非法 profile/type/mode 组合在检索前被拒绝。

### 10.2 FMEA 适配

- 一个 EvidenceRequest 只调用 QueryService 一次；
- RAG-only pack 只含 `rag_text`；
- GraphRAG-only pack 只含 `graphrag_relation/graphrag_community`；
- combined pack 同时包含三类来源；
- 相同文字、不同来源/定位/版本不被错误合并；
- 完全重复 Citation 规范合并；
- 空证据不会产生 known FMEA 字段；
- workspace、ACL、data/graph version 和 pack hash 可重放；
- 单路失败保留其他来源并返回可审计 warning。

### 10.3 交接

- M3/M4 fake/recording 实现不依赖 FMEA 包即可通过查询合同测试；
- FMEA fake QueryService 不依赖具体向量库或图数据库即可建立 EvidenceSnapshot；
- 交接 fixture 可由另一名开发者独立运行；
- 文档明确区分已实现、依赖、降级和未支持项。

## 11. 非目标

本规格不实现：

- 新的向量数据库或图数据库；
- 普通 RAG 或 GraphRAG 效果调参；
- 文档解析、OCR、图谱构建或社区检测；
- FMEA 候选生成模型；
- REST/UI/导出页面；
- 企业认证、DLP 或全链路调度；
- 用 RAG/GraphRAG 检索分数代替 FMEA S/O/D 或工程判断。

## 12. 后续实施顺序

1. 查询合同：profile、custom types、evidence-only 和 recording tests；
2. QueryService：独立来源执行计划、无最终回答生成和降级语义；
3. Task 4.1：PropagationEdge 自动接受策略加固；
4. Task 5：FmeaService、EvidenceRequest、EvidenceSnapshot 与持久化候选边界；
5. FMEA EvidenceProvider：单次查询、规范映射、身份去重和 EvidencePack；
6. 交接 fixtures、合同测试和中文说明；
7. 再进入候选生成、两跳传播、UI、模板和导出阶段。
