# 通用结构化输出模板引擎设计

> 状态：用户已于 2026-08-24 确认，并授权在规格提交后直接生成实施计划和实施。
>
> 上游证据规格：`docs/superpowers/specs/2026-08-24-rag-graphrag-evidence-selection-design.md`
>
> 后续子项目：外部 LLM 与 FMEA 候选生成闭环；默认 `deepseek-v4-flash` 生成，`deepseek-v4-pro` critic/repair。

## 1. 目标

为面向任意领域的 RAG skill 提供可审计、可迁移、离线可重放的结构化输出模板引擎。模板作者用 JSON 或 YAML 描述标准 JSON Schema 2020-12 数据结构，并用独立 evidence binding manifest 描述字段级证据要求。系统把模板编译成不可变版本，校验任意模型候选 payload 及其 EvidencePack 引用，再将通用候选交给 FMEA、维修、科研等领域适配器。

本引擎属于 M5/接口输出层。它不修改 M3 普通 RAG、M4 GraphRAG，也不知道 FMEA 的 S/O/D、RPN、传播或审核规则。

## 2. 设计原则

1. 标准优先：业务数据使用 JSON Schema Draft 2020-12，不发明私有字段类型系统。
2. 证据规则分离：证据语义放在强制执行的 sidecar manifest，不依赖第三方 JSON Schema 实现理解自定义关键字。
3. 离线可重放：模板编译、注册、读取、示例生成和候选校验均不访问网络。
4. 不可变版本：同一 template ID/version 不能被不同内容覆盖。
5. 确定性：JSON/YAML 中语义相同的模板产生相同 canonical JSON 和 SHA-256 hash。
6. 失败关闭：模板 hash、workspace、ACL、EvidencePack 或禁用 Schema 特性不一致时不产生有效候选。
7. 领域解耦：FMEA 只是后续领域适配器之一，不能反向污染通用合同。
8. 模型不可信：模型输出只是候选；模板、证据和状态均由代码确定性校验。

## 3. 范围与归属

| 能力 | 归属 | 本阶段责任 |
| --- | --- | --- |
| 文档、向量、关键词检索 | M3 | `DEPEND`：只消费 TEXT Citation/EvidenceRef |
| 图关系、社区与 GraphRAG | M4 | `DEPEND`：只消费 GRAPH/COMMUNITY EvidenceRef |
| 通用模板合同、编译、注册、CLI | M5 | `OWN` |
| 候选 payload 与证据绑定校验 | M5 | `OWN` |
| EvidenceSnapshot/EvidencePack | M5/FMEA 交接 | `INTEGRATE`：只读消费现有稳定合同 |
| FMEA 字段映射、评分、传播、审核 | FMEA | `OUT`：进入后续子项目 |
| 外部模型生成、critic、repair | M5/FMEA 交接 | `OUT`：进入后续子项目 |

本阶段不实现 Excel/Word 样表导入、浏览器编辑器、通用问答生成、外部 LLM 调用、FMEA 评分/传播、人工审核、发布和结果导出。

## 4. 推荐架构

```text
JSON/YAML template source
        │
        ▼
safe loader ──> source limits
        │
        ▼
TemplateCompiler
  ├─ JSON Schema 2020-12 validation
  ├─ safe feature subset
  ├─ evidence binding validation
  └─ canonical JSON + SHA-256
        │
        ▼
CompiledTemplate
        │
        ▼
immutable TemplateRegistry

EvidenceSnapshot.pack + StructuredCandidate + CompiledTemplate
        │
        ▼
StructuredCandidateValidator
  ├─ template identity/hash
  ├─ payload schema
  ├─ target JSON Pointer
  ├─ binding coverage/state
  └─ EvidencePack membership
        │
        ▼
CandidateValidationReport
        │
        ├─ FMEA adapter (later)
        ├─ maintenance adapter (later)
        └─ research adapter (later)
```

### 4.1 代码边界

```text
core_domain/structured_output/
  contracts.py
  canonical.py
  policies.py

structured_output_application/
  ports.py
  compiler.py
  validators.py
  services.py

structured_output_infrastructure/
  file_registry.py
  source_loader.py
  jsonschema_adapter.py

scripts/
  output_template_skill.py

templates/
  examples/
  builtin/
```

`core_domain.structured_output` 不得导入 `fmea_application`、`fmea_infrastructure`、QueryService、Chroma、GraphStore 或外部 LLM 客户端。`structured_output_application` 只通过 Protocol 消费 registry 和 Schema validator。

## 5. 模板源格式

JSON 和 YAML 映射到同一个逻辑对象：

```yaml
template:
  id: fuel-combustion-fmea
  version: 1.0.0
  title: 燃料与燃烧系统 FMEA
  description: 以字段级证据生成燃料和燃烧系统 FMEA 候选
  domain_tags: [energy, fuel, combustion, fmea]
  schema_dialect: https://json-schema.org/draft/2020-12/schema

output_schema:
  type: object
  additionalProperties: false
  required: [item, failure_mode, effects]
  properties:
    item:
      type: string
      minLength: 1
    failure_mode:
      type: string
      minLength: 1
    effects:
      type: array
      minItems: 1
      items:
        type: string

evidence_bindings:
  - target: /item
    requirement: required
    min_refs: 1
  - target: /failure_mode
    requirement: required
    min_refs: 1
  - target: /effects/*
    requirement: required
    min_refs: 1
```

模板根对象只允许 `template`、`output_schema`、`evidence_bindings`。未知根字段在编译时拒绝，避免拼写错误被静默忽略。

### 5.1 模板元数据

- `id`：小写 ASCII、数字、点、下划线和连字符，长度 1-128，不能包含路径分隔符或 `..`。
- `version`：严格 SemVer `MAJOR.MINOR.PATCH`，不接受不确定别名如 `latest`。
- `title`：1-200 字符。
- `description`：0-2000 字符。
- `domain_tags`：去重后的 0-32 个字符串，每个 1-64 字符；排序进入 canonical form。
- `schema_dialect`：必须精确等于 `https://json-schema.org/draft/2020-12/schema`。

## 6. Evidence binding manifest

### 6.1 Binding 合同

```python
@dataclass(frozen=True, slots=True)
class EvidenceBinding:
    target: str
    requirement: Literal["required", "optional", "forbidden"]
    min_refs: int = 0
    max_refs: int | None = None
    allowed_source_types: tuple[str, ...] = ()
```

规则：

- `required` 必须 `min_refs >= 1`；
- `optional` 可为 0；
- `forbidden` 必须 `min_refs=0` 且 `max_refs=0`；
- `max_refs` 若存在则不小于 `min_refs`；
- source type 使用 EvidenceRef 的稳定 `source_type` 字符串，不导入上游 CitationType；
- 同一 target pattern 只能出现一次；
- pattern 必须能静态匹配 output schema 中至少一个字段位置。

### 6.2 受限 JSON Pointer pattern

- 普通对象字段：`/failure_mode`；
- 嵌套字段：`/risk/severity`；
- 数组直接元素：`/effects/*`；
- 数组元素字段：`/rows/*/failure_mode`；
- token 使用 RFC 6901 的 `~0`、`~1` 转义；
- `*` 只能占一个完整 segment；
- 禁止 `**`、过滤器、表达式、负索引和 URI fragment。

运行时 claim 必须使用不含 `*` 的精确 JSON Pointer，例如 `/effects/1`。校验器将精确 target 匹配到唯一 binding pattern；零匹配或多匹配都返回错误。

## 7. 通用候选合同

```python
class ClaimState(str, Enum):
    KNOWN = "known"
    UNKNOWN = "unknown"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    CONFLICT = "conflict"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True, slots=True)
class CandidateClaim:
    target: str
    state: ClaimState
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class StructuredCandidate:
    candidate_id: str
    payload: JsonValue
    claims: tuple[CandidateClaim, ...]


@dataclass(frozen=True, slots=True)
class StructuredCandidateBatch:
    template_id: str
    template_version: str
    template_hash: str
    evidence_pack_id: str
    candidates: tuple[StructuredCandidate, ...]
```

`JsonValue` 仅允许 JSON 的 null、boolean、integer/finite number、string、array 和 string-key object。禁止 NaN、Infinity、Python 对象和字节串。

### 7.1 Claim 状态规则

- `known`：必须满足 binding 的 min/max refs 和 source type；
- `unknown`：不得有 evidence ID；
- `insufficient_evidence`：可以无证据，也可保留不足以支持结论的证据，但不能被标成 valid-known；
- `conflict`：至少两个不同 evidence ID；
- `not_applicable`：不得带 evidence ID；
- 每个 payload 目标最多一个 claim；
- `required` binding 匹配到的每个实际 payload 节点都必须有 claim；
- `forbidden` binding 可以有 unknown/not_applicable claim，但不能引用证据；
- 所有 evidence ID 必须存在于同一个当前 EvidencePack。

通用引擎只验证证据存在、数量、来源类型和状态一致性，不判断 quote 是否真的语义支持字段；语义支持由后续领域 validator/critic 和人工审核负责。

## 8. 编译与规范化

`TemplateCompiler.compile(source) -> CompiledTemplate` 执行：

1. 载入并检查源大小和 JSON 类型；
2. 校验模板元数据；
3. 校验 JSON Schema meta-schema；
4. 扫描禁用关键字与引用；
5. 计算字段数、深度和静态数组结构限制；
6. 校验 binding pattern 与 schema 可达性；
7. 生成 canonical object；
8. 计算 SHA-256 template hash；
9. 返回冻结的 `CompiledTemplate`。

Canonical form：

- 对象 key 排序；
- domain tags 和 allowed source types 去重排序；
- bindings 按 target 排序；
- tuple/array 保持有业务意义的顺序；
- JSON 使用 UTF-8、无多余空白、禁止 NaN；
- YAML 注释、anchor 名称和源文件格式不进入 hash。

语义相同的 JSON/YAML 与不同 key 顺序必须产生同一 hash；binding 规则或约束发生变化必须改变 hash。

## 9. 安全 Schema 子集

第一版支持普通对象、数组、字符串、boolean、null、integer/number、`enum`、`const`、数值/长度边界、`required`、`additionalProperties`、`$defs` 和包内 `$ref`。

第一版禁止：

- HTTP/HTTPS/file/绝对 URI `$ref`；
- `$dynamicRef`、`$dynamicAnchor`；
- 直接或间接递归 `$ref`；
- `contentEncoding`、`contentMediaType` 等隐式内容处理；
- 任何脚本、表达式或 Python callback；
- 无上界的模板复杂度。

默认限制：

```text
max_source_bytes = 1_048_576
max_schema_depth = 16
max_properties = 500
max_bindings = 500
max_candidates = 100
max_claims_per_candidate = 1000
max_array_items = 1000
max_string_length = 65536
```

限制由代码常量和构造参数提供；正式 registry 使用默认或更严格值，不允许模板源自行放宽。

YAML 使用安全加载器，预先限制文件大小并拒绝 alias/anchor。禁止 YAML 自定义标签和对象构造。

## 10. 不可变 Registry

```text
template_registry/
  <template_id>/
    <version>/
      source.yaml | source.json
      compiled.json
      manifest.json
```

- Registry 根目录由服务端配置并解析到允许根目录内；
- 模板 ID/version 只作为已验证的单目录名；
- 写入使用临时目录、flush、原子 rename；
- 同 id/version/hash 重复注册返回原对象且不重写；
- 同 id/version 不同 hash 返回 `TEMPLATE_VERSION_CONFLICT`；
- 读取时重新计算 compiled hash，并与 manifest 比较；
- 本阶段不提供覆盖、删除或在线迁移命令。

`TemplateRegistry` 是应用 Protocol，文件 registry 只是第一版实现；未来可替换数据库而不改变编译器和候选校验器。

## 11. 应用服务与 CLI

```python
class StructuredOutputService:
    def validate_source(self, path: Path) -> TemplateValidationReport: ...
    def compile_source(self, path: Path) -> CompiledTemplate: ...
    def register_source(self, path: Path) -> CompiledTemplate: ...
    def get_template(self, template_id: str, version: str) -> CompiledTemplate: ...
    def make_example(self, template_id: str, version: str) -> StructuredCandidateBatch: ...
    def validate_candidates(
        self,
        batch: StructuredCandidateBatch,
        evidence_pack: EvidencePack,
    ) -> CandidateValidationReport: ...
```

CLI：

```text
python scripts/output_template_skill.py validate <source>
python scripts/output_template_skill.py compile <source> --out <compiled.json>
python scripts/output_template_skill.py register <source> --registry <root>
python scripts/output_template_skill.py show <template_id>@<version> --registry <root>
python scripts/output_template_skill.py example <template_id>@<version> --registry <root>
python scripts/output_template_skill.py validate-candidate <batch.json> --pack <pack.json> --registry <root>
```

CLI stdout 只输出一个 JSON 对象；日志写 stderr；成功退出 0，模板/候选校验失败退出 2，依赖或 registry 错误退出 3，未处理内部错误退出 1。任何命令都不访问网络或调用模型。

`example` 根据 Schema 生成确定性最小骨架和 unknown claims，不生成领域事实，不保证作为完整业务实例发布。

## 12. 错误合同

```python
@dataclass(frozen=True, slots=True)
class ValidationIssue:
    code: str
    message: str
    pointer: str
    candidate_id: str | None = None
    target: str | None = None
    binding: str | None = None
```

模板编译失败立即返回有序 issues；候选校验尽量收集完整 issues。以下错误失败关闭，不返回 valid candidate：

```text
TEMPLATE_SOURCE_INVALID
TEMPLATE_SCHEMA_UNSUPPORTED
TEMPLATE_REMOTE_REF_FORBIDDEN
TEMPLATE_RECURSION_FORBIDDEN
TEMPLATE_LIMIT_EXCEEDED
TEMPLATE_BINDING_INVALID
TEMPLATE_BINDING_TARGET_INVALID
TEMPLATE_VERSION_CONFLICT
TEMPLATE_HASH_MISMATCH
TEMPLATE_NOT_FOUND
CANDIDATE_SCHEMA_INVALID
CANDIDATE_TARGET_INVALID
CANDIDATE_BINDING_AMBIGUOUS
CANDIDATE_EVIDENCE_MISSING
CANDIDATE_EVIDENCE_SOURCE_FORBIDDEN
CANDIDATE_CLAIM_STATE_INVALID
EVIDENCE_PACK_MISMATCH
```

Issue 排序固定为 candidate input order、target、code，保证重复运行输出一致。

## 13. 测试策略

### 13.1 通用性 fixture

必须包含三个不共享业务字段的模板：

1. 燃料/燃烧 FMEA；
2. 设备维修检查清单；
3. 科研文献结构化摘要。

### 13.2 编译和确定性

- JSON/YAML 等价源 hash 相同；
- key 顺序和 YAML 注释不影响 hash；
- binding、schema 或版本变化改变 hash；
- 本地 `$defs/$ref` 正常；远程、递归和 dynamic ref 拒绝；
- 限制、未知根字段、非法 SemVer 和路径字符拒绝。

### 13.3 Binding 与候选

- 普通字段、嵌套字段、数组 `*`；
- 零匹配、重复 pattern 和运行时歧义；
- known/unknown/insufficient/conflict/not_applicable；
- min/max refs 和 source type；
- 不存在、重复或其他 pack 的 evidence ID；
- required 节点缺 claim；
- 非 JSON 数值和超限 payload。

### 13.4 Registry 与 CLI

- 同版本同 hash 幂等；
- 同版本不同 hash 拒绝；
- 原子写入失败不留下半注册目录；
- manifest/compiled 篡改被读取校验发现；
- path traversal 拒绝；
- 每个命令 stdout 单 JSON、退出码稳定；
- registry 重启后读取结果一致。

### 13.5 回归

现有 query/FMEA 证据交接测试必须保持通过。通用包导入不得导入 FMEA、QueryService、Chroma、GraphStore 或模型适配器。

## 14. 验收标准

- 任意受支持领域 JSON/YAML 模板可以离线编译并不可变注册；
- 编译结果和 hash 可跨进程重放；
- 任意 JSON payload 可按模板验证；
- 字段级 claim 可按 EvidencePack、source type 和状态验证；
- 三个跨领域 fixture 通过同一 API 和 CLI；
- 恶意/超限模板、路径和候选失败关闭；
- CLI 可直接被后续 Codex/RAG skill 调用；
- 不存在外部模型、检索后端或 FMEA 领域依赖；
- 原有接口/FMEA scoped regression 保持绿色；
- 全仓既有 GraphRAG global-search 基线失败不得被误算为本阶段回归。

## 15. 后续衔接

Plan B 在不修改本引擎合同的前提下增加：

```text
EvidenceSnapshot + CompiledTemplate
  -> deepseek-v4-flash structured generation
  -> StructuredCandidateBatch
  -> generic deterministic validation
  -> deepseek-v4-pro critic
  -> at most one deepseek-v4-pro repair
  -> generic validation again
  -> FMEA adapter
  -> FmeaRow candidates
```

后续 Excel/Word importer、浏览器编辑器和其他领域适配器只产生同一模板源合同，不进入 compiler/registry 内核。

## 16. 官方标准依据

- JSON Schema Draft 2020-12：https://json-schema.org/draft/2020-12
- JSON Schema annotations：https://json-schema.org/understanding-json-schema/reference/annotations
- JSON Schema dialect/vocabulary guidance：https://json-schema.org/understanding-json-schema/reference/schema
- DeepSeek API model list：https://api-docs.deepseek.com/api/list-models/
- DeepSeek thinking mode：https://api-docs.deepseek.com/guides/thinking_mode/
