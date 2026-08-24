# 通用结构化输出模板引擎：作者指南与团队交接

## 1. 这次交付解决什么问题

这套能力把“模型应该输出什么字段、哪些字段必须有证据、候选是否可进入下游”从某个具体 FMEA 提示词中抽离，形成一个可审计、可版本化、可被 Codex Skill 或其他程序调用的通用接口。FMEA、设备维护、科研摘要只是三个已执行的例子；模板核心没有故障评分、传播、审核或某个模型厂商字段。

完整链路是：

```text
人工或 LLM 起草 JSON/YAML 模板
  -> 安全加载
  -> JSON Schema 2020-12 子集校验
  -> evidence binding 静态可达性校验
  -> canonical JSON + SHA-256
  -> 不可变 registry
  -> 模型候选 payload + 字段 claim
  -> EvidencePack 成员、来源、数量、状态校验
  -> 领域适配器（FMEA/维护/科研/未来领域）
```

它贴近开源生态的部分是标准 JSON Schema Draft 2020-12、RFC 6901 JSON Pointer、离线安全 YAML、Ports/Adapters 和内容寻址版本；本项目的组合创新是把这些标准与现有 RAG + GraphRAG `EvidencePack`、逐字段 claim 状态、不可覆盖版本和单 JSON Skill CLI 串成同一条可审计链路。

## 2. 所有权与交接边界

| 范围 | 责任模块 | 本引擎关系 | 不由本引擎负责 |
| --- | --- | --- | --- |
| M3 普通 RAG | 文档解析、切片、向量/关键词召回 | `DEPEND`：消费 `rag_text`/原文 EvidenceRef | OCR、索引、embedding、召回调优 |
| M4 GraphRAG | 实体关系、社区、图检索 | `DEPEND`：消费 `graphrag_relation`、`graphrag_community` EvidenceRef | 抽取、融合、社区算法、GraphStore |
| M5 接口输出 | 模板合同、编译、注册、CLI、候选校验 | `OWN`：本次 Plan A 的主体 | 通用回答生成和检索内部实现 |
| M5/FMEA 交接 | 只读消费稳定 `EvidencePack` | `INTEGRATE`：检查 pack ID、evidence ID、source type | 修改 Citation、EvidencePack 或上游资料事实 |
| FMEA 应用 | 字段映射、S/O/D、RPN、传播、审核、发布 | `OUT`：后续领域适配器消费通用候选 | 本模板核心不实现这些规则 |
| 外部 LLM | 候选生成、critic、一次 repair | `OUT`：Plan B 通过端口接入 | 本阶段不联网、不调用模型 |

现有 RAG/GraphRAG 到 EvidencePack 的上游说明见 `docs/handoff/rag-graphrag-fmea-evidence.md`。本文件从 EvidencePack 之后的通用结构化输出边界开始。

## 3. 模板源文件结构

根对象只能有三个字段：

```yaml
template:
  id: example-template
  version: 1.0.0
  title: 示例模板
  description: 说明模板用途、输入资料和输出边界
  domain_tags: [example]
  schema_dialect: https://json-schema.org/draft/2020-12/schema

output_schema:
  type: object
  additionalProperties: false
  required: [result]
  properties:
    result:
      type: string
      minLength: 1

evidence_bindings:
  - target: /result
    requirement: required
    min_refs: 1
    allowed_source_types: [rag_text, graphrag_relation, graphrag_community]
```

元数据限制：

- `id`：1–128 位小写 ASCII、数字、点、下划线或连字符；不能有路径分隔符或 `..`。
- `version`：严格 `MAJOR.MINOR.PATCH`，例如 `1.2.0`；不能写 `latest`。
- `title`：1–200 字符；`description`：0–2000 字符。
- `domain_tags`：最多 32 个、不重复，每项 1–64 字符。编译时排序，因此标签输入顺序不改变 hash。
- `schema_dialect`：必须精确为 Draft 2020-12 URI。

生产示例：

- `templates/examples/fuel-combustion-fmea.yaml`
- `templates/examples/maintenance-checklist.yaml`
- `templates/examples/research-summary.yaml`

第一份只是结构化候选示范，不包含 S/O/D、RPN、跨系统传播或自动批准。

## 4. 支持的 JSON Schema 子集

第一版采用“关闭式允许列表”：未列出的关键词一律拒绝，避免编译通过但样例生成器或候选校验器无法稳定解释。

支持：

```text
$schema, $id, $defs, 本地 $ref
type, properties, required, additionalProperties, items
minItems, maxItems, uniqueItems
minLength, maxLength, pattern
minimum, maximum, exclusiveMinimum, exclusiveMaximum, multipleOf
enum, const
title, description, default, examples
readOnly, writeOnly, deprecated, $comment
```

明确不支持：

```text
远程/file/相对文件 $ref
$dynamicRef, $dynamicAnchor
allOf, anyOf, oneOf, not
if, then, else
contains, dependentSchemas, patternProperties
unevaluatedProperties, unevaluatedItems
contentEncoding, contentMediaType, format
```

本地引用只允许 `#/$defs/<name>`，并拒绝自引用或 A→B→A 循环。模板解析期间不访问网络，也不执行 YAML 自定义对象。

注意：`pattern`、数值组合等复杂约束可以用于候选校验；如果系统无法在固定资源限制内自动合成一个满足约束的中性样例，`example` 会返回 `TEMPLATE_EXAMPLE_UNSUPPORTED`，不会伪造一个“看起来像成功”的样例。

## 5. Evidence binding 规则

每条 binding 把一个字段位置或数组字段模式绑定到证据要求：

- `/failure_mode`：对象字段。
- `/risk/severity`：嵌套字段。
- `/effects/*`：数组每个实际元素。
- `/rows/*/result`：数组对象中的字段。
- `~0` 表示 `~`，`~1` 表示 `/`。
- `*` 只能占一个完整 segment；禁止 `**`、过滤表达式、负索引和 URI fragment。

`requirement`：

- `required`：实际 payload 中每个匹配节点都必须有 claim，且 `min_refs >= 1`。
- `optional`：字段可以没有 claim；一旦有 claim，仍检查 EvidencePack、来源和状态。
- `forbidden`：必须 `min_refs=0`、`max_refs=0`，只允许 `unknown` 或 `not_applicable` 且不得引用证据。

`allowed_source_types` 留空表示不限制；正式例子允许：

| 上游选择 | EvidenceRef `source_type` |
| --- | --- |
| RAG-only | `rag_text` |
| GraphRAG local | `graphrag_relation` |
| GraphRAG global | `graphrag_community` |
| combined | 上述三类可组合 |
| 本地人工/测试资料 | `primary_document` |

模板不负责选择检索 profile。上游先按 `rag_only`、`graphrag_only`、global 或 combined 建立同一个不可变 EvidencePack；模板只检查候选引用的 source type 是否获准。

## 6. 候选合同与五种 claim 状态

候选批次示例：

```json
{
  "template_id": "example-template",
  "template_version": "1.0.0",
  "template_hash": "64位小写SHA-256",
  "evidence_pack_id": "pack-1",
  "candidates": [
    {
      "candidate_id": "candidate-1",
      "payload": {"result": "检查通过"},
      "claims": [
        {"target": "/result", "state": "known", "evidence_ids": ["ev-1"]}
      ]
    }
  ]
}
```

状态语义：

- `known`：证据数量必须满足 binding 的 min/max，来源必须获准。
- `unknown`：明确未知，不能带 evidence ID。
- `insufficient_evidence`：可以没有引用，也可以保留不足以支持 known 的引用；仍检查来源和最大数量。
- `conflict`：至少引用两个不同 evidence ID，用于保留多来源冲突。
- `not_applicable`：字段不适用，不能带 evidence ID。

通用校验只证明“引用存在、数量正确、来源获准、状态一致”，不证明 quote 在工程语义上一定支持字段。语义支持应由 Plan B critic、FMEA 规则校验和人工审核共同完成。

## 7. CLI 用法

以下命令都只向 stdout 写一个 `rag.structured-output.v1` JSON 对象；`--pretty` 可放在子命令参数中。命令不访问网络或调用模型。

```powershell
& '.venv\Scripts\python.exe' scripts/output_template_skill.py validate templates/examples/fuel-combustion-fmea.yaml

& '.venv\Scripts\python.exe' scripts/output_template_skill.py compile templates/examples/fuel-combustion-fmea.yaml --out compiled.json

& '.venv\Scripts\python.exe' scripts/output_template_skill.py register templates/examples/fuel-combustion-fmea.yaml --registry .local/template-registry

& '.venv\Scripts\python.exe' scripts/output_template_skill.py show fuel-combustion-fmea@1.0.0 --registry .local/template-registry

& '.venv\Scripts\python.exe' scripts/output_template_skill.py example fuel-combustion-fmea@1.0.0 --registry .local/template-registry --pretty

& '.venv\Scripts\python.exe' scripts/output_template_skill.py validate-candidate candidate-batch.json --pack evidence-pack.json --registry .local/template-registry
```

退出码：

- `0`：成功。
- `2`：参数、模板或候选校验失败，不应通过重试掩盖。
- `3`：输出路径、registry、版本或完整性依赖失败，自动化可按基础设施故障处理。
- `1`：未分类内部错误；公共响应不含堆栈或原始异常。

`example` 的 `result` 外层固定带 `example_only: true`。样例使用固定 ID、不含 evidence ID、不含时间/随机数/领域事实，不能当成已审核业务成果。

## 8. 版本、hash 与不可变 registry

编译身份由以下逻辑内容决定：排序后的元数据、output schema、排序后的 binding。源文件路径、JSON/YAML 后缀和 YAML 注释不进入 hash，因此语义相同的 JSON/YAML 得到相同 canonical JSON 和 SHA-256。

registry 布局：

```text
<root>/<template_id>/<version>/
  source.yaml | source.yml | source.json
  compiled.json
  manifest.json
```

- 同一 ID/version/hash 重复注册是幂等操作，不改 mtime。
- 同一 ID/version 出现不同 hash 返回 `TEMPLATE_VERSION_CONFLICT`，不能覆盖。
- 写入先在同级临时目录完成并 fsync，最后原子重命名。
- 读取重新计算 hash，并核对 manifest、目录身份和 canonical form。
- 本阶段没有 delete、overwrite 或在线迁移命令。

修改任何 schema、binding、版本或元数据内容后，应明确提升 SemVer，再 validate/compile/register。不要直接编辑 registry 文件。

## 9. 人工与 LLM 怎样共同制作新模板

推荐门控：

1. 人工提供样表、字段定义、必填项、证据规则和示例输入。
2. 人工或 LLM 只在工作目录起草 JSON/YAML，不写 registry。
3. 运行 `validate`，修复未知关键词、不可达 binding、循环引用和限制错误。
4. 运行 `compile`，由负责人查看 canonical 结构与 hash。
5. 用中性 `example` 和至少一份真实但非认证测试 EvidencePack 验证候选。
6. 人工确认 ID、SemVer、字段语义和来源允许列表。
7. 只有获得工具写权限的人工流程执行 `register`。

LLM 可以帮助识别表头、建议 JSON 类型、起草 description、生成测试候选和解释错误；LLM 不能自行放宽限制、覆盖版本、把 unknown 改成 known、签署 S/O/D 或发布 FMEA。

## 10. 新 Excel/Word 模板怎样迁移

未来 importer 不是第二套模板引擎，只是把办公文档确定性转换为同一个三段式源合同：

```text
Excel/Word
  -> 人工选择表头/重复行/必填项/证据列
  -> importer 生成 template + output_schema + evidence_bindings
  -> 人工预览 diff
  -> 现有 validate/compile/register 门
```

复杂度估计：

| 新模板类型 | 难度 | 主要工作 |
| --- | --- | --- |
| 与现有例子相似的 JSON/YAML | 低 | 改字段、required、binding、版本；CLI 可完成 |
| 新领域的嵌套表/数组 | 中 | 明确重复行和 wildcard target，补候选测试 |
| Excel 固定表头导入器 | 中 | 人工字段映射 UI/CLI、类型推断、预览与回写，不改核心 |
| Word 非规则表格/段落 | 中高 | 布局解析和人工框选；输出仍走同一合同 |
| 需要 oneOf/条件 schema/远程 ref | 高 | 先设计新引擎版本、样例策略和迁移规则；不能静默放开 |

人工工具应提供字段映射、类型下拉框、required 开关、binding 规则、source type 多选和生成前预览。这样新模板主要是“配置与审核”，而不是为每个行业重写 Python。

## 11. Plan B 怎样接入 DeepSeek 而不污染核心

Plan B 在 application 外新增模型端口和 FMEA 适配器：

```text
EvidencePack + CompiledTemplate
  -> generator adapter（默认配置标签 deepseek-v4-flash）
  -> StructuredCandidateBatch
  -> 本次确定性 validator
  -> critic adapter（默认配置标签 deepseek-v4-pro）
  -> 最多一次有界 repair
  -> 再次确定性 validator
  -> FMEA 字段映射、规则、人工审核
```

模型只产生现有候选合同，不得修改 TemplateCompiler、registry 或 ClaimState。模型 API 名、base URL、Key、预算和超时放在 adapter/config；模板源不能携带密钥或自行选择高权限模型。即使外部 API 不可用，Plan A 的 validate/compile/register/show/example 和离线候选校验仍可运行。

## 12. 常见错误与处理

| 错误码 | 含义 | 处理 |
| --- | --- | --- |
| `TEMPLATE_SOURCE_INVALID` | 文件、UTF-8、JSON/YAML 或根对象无效 | 修复源文件；不要使用 alias/anchor/自定义标签 |
| `TEMPLATE_LIMIT_EXCEEDED` | 文件、深度、字段、binding、候选或字符串/数组超限 | 缩小模板/批次；模板不能放宽服务端限制 |
| `TEMPLATE_ROOT_INVALID` | 根字段缺失或多出拼写错误字段 | 只保留三段根合同 |
| `TEMPLATE_METADATA_INVALID` | ID、SemVer、标题、标签或 dialect 无效 | 按第 3 节修复 |
| `TEMPLATE_SCHEMA_INVALID` | 不符合 Draft 2020-12 | 修复 JSON Schema |
| `TEMPLATE_SCHEMA_UNSUPPORTED` | 使用了第一版禁止关键词或远程 ref | 改写为允许子集，或提出新版本设计 |
| `TEMPLATE_SCHEMA_REF_INVALID/CYCLE` | 本地 ref 不存在或成环 | 修复 `$defs` 图 |
| `TEMPLATE_BINDING_INVALID` | min/max/requirement/source type/重复 target 无效 | 修复 binding 合同 |
| `TEMPLATE_BINDING_TARGET_INVALID` | target 模式无法静态到达 schema | 修正 JSON Pointer 与数组 wildcard |
| `TEMPLATE_VERSION_CONFLICT` | 同 ID/version 已有不同 hash | 提升 SemVer，禁止覆盖 |
| `TEMPLATE_HASH_MISMATCH` | registry 或候选绑定了错误内容 | 停止使用并核对 artifact/manifest |
| `CANDIDATE_SCHEMA_INVALID` | payload 不符合 schema | 修复候选字段/类型 |
| `CANDIDATE_TARGET_INVALID` | claim target 在 payload 不存在 | 使用实际精确 pointer |
| `CANDIDATE_BINDING_AMBIGUOUS` | claim 匹配零个或多个 binding | 消除重叠或补 binding |
| `CANDIDATE_EVIDENCE_MISSING` | required claim 缺失或 evidence ID 不在当前 pack | 补 claim/引用，或标记 unknown/insufficient |
| `CANDIDATE_EVIDENCE_SOURCE_FORBIDDEN` | 引用来源不在允许列表 | 改 EvidencePack profile 或模板版本，不伪造来源 |
| `CANDIDATE_CLAIM_STATE_INVALID` | state 与证据数量/forbidden 规则冲突 | 按第 6 节修复 |

## 13. 交给下一位开发者的文件入口

- 领域合同与策略：`core_domain/structured_output/`
- 编译、服务、候选校验：`structured_output_application/`
- 安全加载、Schema、文件 registry：`structured_output_infrastructure/`
- Skill CLI：`scripts/output_template_skill.py`
- 正式示例：`templates/examples/`
- 单元/集成验收：`tests/unit/test_structured_output_*.py`、`tests/unit/test_structured_candidate_validator.py`、`tests/integration/test_output_template_skill_cli.py`、`tests/integration/test_structured_output_cross_domain.py`
- 设计与实施计划：`docs/superpowers/specs/2026-08-24-generic-structured-output-template-engine-design.md`、`docs/superpowers/plans/2026-08-24-generic-structured-output-template-engine.md`

Plan A 到此交付的是通用、离线、可审计的接口输出核心。外部模型生成、FMEA 字段映射/评分/传播、Excel/Word importer、人工工作台、发布和导出仍是后续明确项目，不应被描述为已经完成。
