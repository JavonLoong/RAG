# RAG + GraphRAG 到 FMEA 的证据接口交接说明

## 1. 这条链路解决什么问题

本接口把普通 RAG 的原文片段、GraphRAG 的关系和社区摘要统一变成可追溯的 FMEA 证据快照。一次 `EvidenceRequest` 只发出一次 evidence-only `QueryService.query()`，得到 Citation 后由 `QueryServiceEvidenceProvider` 规范化为同一个不可变 `EvidencePack`。后续 FMEA 候选只引用包内 `evidence_id`，不直接依赖 Chroma、Neo4j、GraphStore 或某个特定 GraphRAG 项目。

这不是新的检索引擎。它是 M3/M4 检索结果与 FMEA 之间的接口层和证据责任边界。

## 2. 模块归属与交接责任

| 模块 | 负责 | 交给下一环节 | 不负责 |
| --- | --- | --- | --- |
| M3 资料库/RAG | 文档解析、切片、向量/关键词召回 | `TEXT` Citation：稳定 document/chunk/page/quote | FMEA 字段、审核和发布 |
| M4 GraphRAG | 实体关系、社区和图检索 | `GRAPH`/`COMMUNITY` Citation：关系、社区、来源和版本 | FMEA 评分、证据包持久化 |
| M5 查询输出接口（本工作） | evidence profile、请求校验、统一 Citation、warning/partial、向后兼容 | 一次 `QueryResponse`，含选定来源及真实降级状态 | 重做 M3/M4 算法、通用回答调优 |
| FMEA 证据适配（本工作） | Citation 允许列表、规范化、去重、ACL/版本/hash、`EvidenceSnapshot` | 一个 `EvidencePack`、来源计数、warning、incomplete | 自动批准工程结论 |
| FMEA 后续应用 | 候选、critic/repair、传播、S/O/D/RPN、人工审核、发布 | 可审核和可导出的 FMEA 成果 | 修改原始资料或图谱事实 |
| M6 | 流程编排、运行事件和总质量门 | 跨模块运行审计 | 改写本接口的领域规则 |

## 3. 公开调用方式

FMEA 侧只依赖结构化 Protocol：传入任何具有 `query(request) -> QueryResponse` 方法的对象即可。测试可传入记录请求的 fake；生产可传入真实 `QueryService`。两者都不需要继承生产类。

```python
request = EvidenceRequest(
    workspace_id="ws-1",
    analysis_id="analysis-1",
    query="燃料压力下降如何影响燃烧稳定性？",
    versions=version_set,
    acl_scope=("engineering",),
    evidence_profile=EvidenceSelectionProfile.COMBINED,
)
snapshot = provider.create_snapshot(request)
```

适配器内部构造一条 `mode=AUTO, evidence_only=true, include_context=true` 的 `QueryRequest`。旧的普通问答调用不传这些字段时，`graphrag.query.v1` 序列化和行为保持不变。

## 4. 各 profile 的请求与响应例子

下表省略固定的 workspace、版本和 ACL。响应中的 `refs` 表示 `EvidenceSnapshot.pack.refs[].source_type`；实际返回还包含 `source_counts`、`warnings` 和 `incomplete`。

| 用途 | 请求关键字段 | 响应例子 |
| --- | --- | --- |
| 普通 RAG only | `profile="rag_only"` | `refs=["rag_text"], warnings=[], incomplete=false` |
| GraphRAG local only | `profile="graphrag_local_only"` | `refs=["graphrag_relation"], warnings=[], incomplete=false` |
| GraphRAG global only | `profile="graphrag_global_only"` | `refs=["graphrag_community"], warnings=[], incomplete=false` |
| GraphRAG only | `profile="graphrag_only"` | `refs=["graphrag_relation","graphrag_community"], incomplete=false` |
| RAG + GraphRAG | `profile="combined"` | `refs=["rag_text","graphrag_relation","graphrag_community"], incomplete=false` |
| 自定义来源 | `profile="custom", evidence_types=["text","community"]` | `refs=["rag_text","graphrag_community"], incomplete=false` |
| combined 单路降级 | `profile="combined"` | `refs=["rag_text"], warnings=["GRAPH_RETRIEVAL_DEGRADED: ..."], incomplete=true` |

完整的查询响应仍是 `QueryResponse`，例如：

```json
{
  "status": "partial",
  "answer": {"text": "", "finish_reason": "stop"},
  "citations": [{"id": "T1", "type": "text", "quote": "低燃料压力可能导致火焰不稳定"}],
  "warnings": [{"code": "GRAPH_RETRIEVAL_DEGRADED", "message": "Graph sources are unavailable."}]
}
```

该结果会形成一个仍可审计的文本证据包，但 `snapshot.incomplete=true`。下游可以生成“待补证/未知”候选，不能把它当成完整证据事实。

## 5. Citation 到 EvidenceRef 的允许列表

| Citation 类型 | `EvidenceRef.source_type` | 稳定身份/定位允许进入的字段 | 明确排除 |
| --- | --- | --- | --- |
| `TEXT` | `rag_text` | document_id、document_version、file、page、chunk_id、quote | score、rank、任意 metadata、prompt |
| `GRAPH` | `graphrag_relation` | subject、predicate、object、edge ID、source document、graph version、quote | 检索分数、未允许的图属性 |
| `COMMUNITY` | `graphrag_community` | community ID、title、graph version、quote | 原始模型 prompt、任意社区 metadata |

证据身份由来源类型、文档/图版本、稳定 locator 和规范化 quote 共同决定，不能只按文字去重。缺少上游 document ID 时使用带命名空间的技术 ID，例如 `text:<workspace>:<citation>`，不得伪装成原始文档编号。

## 6. warning、incomplete 与禁止静默回退

- 显式 `rag_only` 失败时不改用 GraphRAG；显式 `graphrag_only` 失败时不改用普通 RAG。
- `combined` 某一路失败时保留其他 Citation，同时返回稳定 warning，并设置 `incomplete=true`。
- 指定来源零命中、Citation 结构非法、证据身份冲突或元数据冲突都必须显式记录。
- warning 属于运行审计，不写进 `EvidenceRef`，也不把回答文本冒充原始证据。
- 空证据包可以存在，用于表达 unknown/insufficient evidence；不能据此生成 `known` 字段。

## 7. 如何替换 fake 或真实检索实现

最小 fake 只需记录请求并返回合同对象：

```python
class FakeQueryService:
    def __init__(self, response):
        self.response = response
        self.requests = []

    def query(self, request):
        self.requests.append(request)
        return self.response
```

生产实现同样只需满足这个结构。向量库可从 Chroma 换为其他后端，图后端可换成 Neo4j、NetworkX、Microsoft GraphRAG、LightRAG 或自研实现；只要保持 `QueryRequest/QueryResponse/Citation` 合同、workspace/ACL/版本语义和 warning 规则，FMEA 领域对象无需修改。

可运行交接证据位于 `tests/integration/test_fmea_evidence_handoff.py`：它覆盖 7 种选择、一次查询、单一快照、候选证据引用和架构依赖方向。

## 8. 新 FMEA 模板怎样接入

模板位于 `EvidenceSnapshot` 之后：

```text
QueryService -> EvidenceSnapshot -> TemplateAdapter -> 候选 schema -> 校验/critic -> 人工审核
```

新增模板只需声明字段定义、必填项、字段到证据 ID 的绑定规则、评分规则和导出映射。它不应改变 evidence profile、重新调用检索器或把模板私有字段塞进 Citation。这样可以由人工工具辅助建立模板，也可以由大模型生成“模板草案”，但模板版本、确定性校验和发布仍须由工具/人工确认。

推荐扩展流程：导入样表或 JSON Schema → 工具生成字段映射草案 → 人工确认字段/评分语义 → 分配 `template_version` → 用固定 EvidenceSnapshot 做回归测试。新模板的主要难度在领域字段和审核规则，不在 RAG/GraphRAG 重接。

## 9. 明确非目标

本交接不实现：索引构建、OCR/切片、图谱抽取/融合/社区检测、GraphStore 优化、通用答案生成、UI、导出器，以及具体 FMEA 模板的编写。它也不允许模型替代工程师签字或用检索分数代替 S/O/D/RPN 判断。

## 10. 后续依赖工作

下一阶段按依赖顺序接入：

1. 外部大模型 gateway、简单账号/API 配置和可替换供应商；
2. FMEA 候选 schema、生成器、独立 critic 与一次有界 repair；
3. 燃料系统/燃烧系统的传播分析器与两跳安全策略；
4. 人工审核、修改、否定、确认和发布状态机；
5. SQLite 仓储、模板注册/迁移工具与审计日志；
6. Word/Excel/JSON 等导出器和 M6 流程事件。

这些后续模块消费 `EvidenceSnapshot`，不得反向侵入 M3/M4 检索内部。
