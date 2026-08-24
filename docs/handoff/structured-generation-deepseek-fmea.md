# DeepSeek 结构化生成与 FMEA 候选交接说明

## 1. 这部分解决什么问题

这条链路把已经检索并固定下来的 `EvidencePack` 转换为可验证的结构化候选结果。它既可以输出任意已注册模板的通用结果，也可以把符合指定映射的候选转换为燃料系统、燃烧系统 FMEA 行建议。

边界非常明确：

- RAG、GraphRAG 或二者组合负责检索和构建 `EvidencePack`；本模块不重新检索。
- DeepSeek Flash 负责第一次结构化生成，DeepSeek Pro 负责证据批评和最多一次修复。
- JSON Schema、证据绑定和身份哈希由代码确定性校验，不把最终裁决交给模型。
- FMEA 输出始终是 `suggested + unpublished + persisted=false`，不评分、不发布、不替代人工批准。
- 命令行和服务层不接受模型、API 地址、思考模式或调用预算覆盖，避免调用方绕过已批准配置。

因此，同一套接口能接三种上游：

1. RAG-only：`EvidencePack.refs[].source_type` 只包含普通检索来源。
2. GraphRAG-only：只包含实体、关系、社区摘要等图检索来源。
3. RAG + GraphRAG：把两类引用放入同一个稳定、带哈希的 `EvidencePack`。

模型看到的只是统一后的证据包，不需要知道上游具体是哪一种检索实现。

## 2. 运行前准备

项目使用固定环境变量读取密钥：

```powershell
$env:DEEPSEEK_API_KEY = "你的测试密钥"
```

不要把密钥写入请求 JSON、模板、EvidencePack、日志或版本库。密钥轮换时只更新运行环境；代码和输入文件无需变化。

先注册模板。下面以燃料/燃烧系统完整 FMEA 模板为例：

```powershell
.venv\Scripts\python.exe scripts\output_template_skill.py register `
  templates\examples\fuel-combustion-fmea-full.yaml `
  --registry .local\template-registry
```

模板注册后是不可变版本。相同 `id@version` 内容不一致时会拒绝覆盖，应提升模板语义版本号。

## 3. 输入文件

### 请求文件

只允许两个字段，任何额外字段都会返回校验错误：

```json
{
  "run_id": "fuel-fmea-demo-001",
  "task": "根据证据提出燃料供给与燃烧稳定性相关的 FMEA 候选，不推测无证据内容。"
}
```

调用方不能在这里指定模型或注入 API 参数。

### EvidencePack

使用项目既有 `graphrag.fmea.v1` 证据包 JSON。关键约束包括：

- 每个引用有稳定 `evidence_id`、来源类型、定位信息和受限长度原文。
- 包内容与 `pack_hash` 必须一致；修改引用后必须重新构建包。
- 默认最多 20 个证据引用、每条引用最多 2000 字符、进入提示词的证据总量最多 24000 字符。
- ACL、资料版本、图谱版本和模板版本应在构建 EvidencePack 时固定。

### FMEA 分析和映射

`run-fmea` 还需要：

- `analysis.json`：分析范围、系统边界、燃料类型、工况、假设和版本集。
- `templates/fmea_profiles/fuel-combustion-fmea-full.json`：把通用模板 JSON Pointer 映射到 10 个非评分 FMEA 字段。

当前映射固定为：项目、功能、故障模式、原因、机理、影响、症状、控制、屏障和建议措施。严重度、发生度、探测度、RPN、传播边和审批工作流不在这条生成链路内。

## 4. 调用方式

### 通用模板输出

```powershell
.venv\Scripts\python.exe scripts\structured_generation_skill.py run `
  --template fuel-combustion-fmea-full@1.0.0 `
  --pack .local\inputs\evidence-pack.json `
  --registry .local\template-registry `
  --request .local\inputs\request.json `
  --pretty
```

### FMEA 候选输出

```powershell
.venv\Scripts\python.exe scripts\structured_generation_skill.py run-fmea `
  --template fuel-combustion-fmea-full@1.0.0 `
  --pack .local\inputs\evidence-pack.json `
  --analysis .local\inputs\analysis.json `
  --profile templates\fmea_profiles\fuel-combustion-fmea-full.json `
  --registry .local\template-registry `
  --request .local\inputs\request.json `
  --pretty
```

所有命令只向标准输出写一个 `rag.structured-generation.v1` JSON 对象。不会输出提示词、证据原文、API 密钥、模型原始响应、批评解释或异常堆栈。

### 最小连接测试

```powershell
.venv\Scripts\python.exe scripts\structured_generation_skill.py smoke --pretty
```

该命令真实调用一次 Flash 逻辑请求并严格解码固定 JSON。它用于确认账号、密钥、网络、模型名和 JSON 响应模式，不代表完整 FMEA 质量测试。

## 5. 输出和退出码

统一信封主要字段：

- `schema_version`：固定为 `rag.structured-generation.v1`。
- `status`：`succeeded`、`needs_review` 或 `failed`。
- `result.batch`：通用候选、逐字段 claim 状态和证据 ID。
- `result.critic`：批评结论及结构化支持分类，不含模型解释原文。
- `result.traces`：模型、阶段、提示/响应哈希、尝试次数和 token 计数。
- `result.fmea`：仅 `run-fmea` 存在，明确 `persisted=false`。

退出码：

| 退出码 | 含义 |
|---:|---|
| 0 | 结构化生成成功 |
| 1 | 未分类内部错误，输出已脱敏 |
| 2 | 请求、输入 JSON 或边界校验失败 |
| 3 | 模板注册表、FMEA profile 或密钥配置失败 |
| 4 | 得到候选，但必须人工复核 |
| 5 | 模型调用或模型输出失败 |

FMEA 行即使随成功响应返回，也只是候选。`review_status=suggested`、`publication_status=unpublished` 和 `persisted=false` 是交接给后续人工/模型辅助审核接口的硬边界。

## 6. 模型编排和失败策略

一次完整运行最多三个逻辑调用：

1. Flash 生成候选，禁用 thinking。
2. Pro 高推理批评每个候选与证据的对应关系。
3. 仅在必要时由 Pro 高推理修复一次；修复后不再次批评，结果降级为 `needs_review`。

总 HTTP 尝试最多 6 次，单次超时 30 秒，总运行时限 90 秒；响应最多 128000 字符，单次输出预算最多 8000 token。429、连接超时和部分 5xx 可在共享预算内重试，其余错误直接失败。

代码校验优先于模型判断：模板身份、模板哈希、EvidencePack 身份、JSON Schema、claim 指针、证据 ID、来源类型和数量均由确定性逻辑检查。模型批评不能把确定性失败改成通过。

## 7. 新模板如何接入

通用模板只需编写 YAML/JSON 模板并注册，不需要改生成管线。模板应包含：

- 稳定的 `id` 和语义版本号；
- Draft 2020-12 输出 schema；
- 每个可陈述字段的 evidence binding；
- 允许的证据来源类型及最小/最大引用数量。

人工可以使用 `output_template_skill.py validate/register/show/example` 完成校验、注册和检查。普通领域模板通常只增加模板文件；只有要转换成某个专业领域对象时，才需要额外的 profile 和纯适配器。

新增 FMEA 模板的难度取决于字段是否仍是当前 10 字段：

- 字段相同：复制 profile，修改模板身份和 JSON Pointer，经测试后即可接入。
- 字段语义不同：需要新的显式 profile 版本和适配测试，不能让模型自行猜字段映射。
- 要加入 S/O/D、RPN、审批或发布：应交给评分、审核和发布模块，不应塞进本生成接口。

接第二家模型供应商时，只实现 `StructuredModelGateway` 端口并通过相同契约测试；服务层、模板、EvidencePack、FMEA 适配器和 CLI 信封无需重写。生产环境是否允许切换供应商应由部署配置和审批控制，而不是增加任意 CLI 参数。

## 8. 测试

默认测试不会产生 API 费用：

```powershell
.venv\Scripts\python.exe -m pytest -s -q
```

只跑本模块：

```powershell
.venv\Scripts\python.exe -m pytest `
  tests\unit\test_structured_generation_contracts.py `
  tests\unit\test_structured_generation_json_codec.py `
  tests\unit\test_structured_generation_prompts.py `
  tests\unit\test_structured_generation_pipeline.py `
  tests\unit\test_deepseek_structured_gateway.py `
  tests\integration\test_structured_generation_cross_domain.py `
  tests\integration\test_structured_generation_skill_cli.py `
  tests\integration\test_structured_generation_live_smoke.py -q
```

只有明确要求并已配置测试账号时才运行真实付费测试：

```powershell
.venv\Scripts\python.exe -m pytest `
  tests\integration\test_structured_generation_live_smoke.py `
  -m live_deepseek -q
```

模拟冒烟测试仍会验证一次 Flash 调用、禁用 thinking 和严格 JSON 解码，但不访问网络。

## 9. 常见问题

- 退出 3 且 `MODEL_CONFIGURATION_INVALID`：检查当前进程是否配置 `DEEPSEEK_API_KEY`。
- `TEMPLATE_NOT_FOUND`：先注册准确的 `id@version`，并确认运行时使用同一个 registry 目录。
- 输入退出 2：检查请求是否只有 `run_id/task`、EvidencePack 哈希是否匹配、JSON 是否 UTF-8 且未超过大小限制。
- 输出为 `needs_review`：查看结构化 issue code、指针和证据 ID；不要根据模型自然语言猜测原因。
- FMEA 没有行：先检查通用 batch 是否生成，再检查 profile 身份、10 字段路径和候选是否有重复/缺失字段。
- 想直接写数据库或自动发布：当前接口故意不提供该能力，应把候选交给独立审核、版本和发布链路。
