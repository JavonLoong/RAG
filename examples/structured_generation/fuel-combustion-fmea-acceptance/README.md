# 燃料与燃烧系统 FMEA：DeepSeek 一键验收包

这个目录用于真实验证项目的“统一证据包 → DeepSeek 结构化生成 → FMEA 候选 → 离线安全验收”链路。样例资料全部是合成数据，只验证接口和约束，不代表任何真实装置的安全结论。

## 这次验收覆盖什么

`evidence-pack.json` 同时包含四类来源：原始资料 `primary_document`、普通 RAG 文本 `rag_text`、GraphRAG 关系路径 `graphrag_relation` 和 GraphRAG 社区摘要 `graphrag_community`。它验证普通 RAG 与 GraphRAG 可以汇入同一个稳定 `EvidencePack`，生成层不依赖上游具体数据库或检索框架。

生成任务使用 `fuel-combustion-fmea-full@1.0.0` 通用模板和对应 FMEA 映射，要求模型给出以下 10 个非评分字段：

1. 项目；
2. 功能；
3. 故障模式；
4. 原因；
5. 机理；
6. 影响；
7. 症状；
8. 当前控制；
9. 屏障；
10. 建议措施。

严重度、发生度、探测度、RPN、传播边、审核结论和发布动作不属于这条自动生成链路。模型结果必须保持“建议、未发布、待人工复核”，也不能写入业务存储。

## 一键运行

在仓库根目录打开 PowerShell，先把自己的测试密钥放入当前进程，再运行脚本：

```powershell
$env:DEEPSEEK_API_KEY = "你的 DeepSeek API 密钥"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
  examples\structured_generation\fuel-combustion-fmea-acceptance\run-acceptance.ps1
```

脚本会按顺序完成：

1. 在本地不可变 registry 中注册模板；
2. 发起一次最小 DeepSeek Flash 连接测试；
3. 用 Flash 生成候选、用 Pro 独立批评，并在需要时最多用 Pro 修复一次；
4. 将通用候选适配成未持久化的 FMEA 行建议；
5. 在内存中用本地验收器检查真实模板哈希、完整候选契约、FMEA 领域规则、证据绑定、隐私和人工审核边界；
6. 只有验收通过后，才把完整结果写成 `run-fmea.json`；未通过的模型结果不会保存为该文件。

成功时标准输出只有一个安全摘要，例如：

```json
{"schema_version":"rag.structured-generation.acceptance.v1","status":"passed","summary":{"status":"needs_review","candidate_count":1,"row_count":1,"trace_count":2,"evidence_link_count":10},"error":null}
```

默认产物写入 `.local/structured-generation-acceptance/<时间戳>/`：

- `template-register.json`：模板注册结果；
- `smoke.json`：最小真实 API 连通结果；
- `run-fmea.json`：验收通过后才落盘的完整结构化生成和 FMEA 建议；
- `acceptance-summary.json`：不含证据原文和模型解释的验收摘要。

可以显式指定本地输出和 registry 目录：

```powershell
examples\structured_generation\fuel-combustion-fmea-acceptance\run-acceptance.ps1 `
  -OutputDirectory .local\my-acceptance `
  -RegistryDirectory .local\my-template-registry
```

## 离线验收器检查项

`scripts/verify_structured_generation_acceptance.py` 不调用网络，可单独验证已经生成的结果：

```powershell
.venv\Scripts\python.exe scripts\verify_structured_generation_acceptance.py `
  --output .local\my-acceptance\run-fmea.json `
  --pack examples\structured_generation\fuel-combustion-fmea-acceptance\evidence-pack.json `
  --analysis examples\structured_generation\fuel-combustion-fmea-acceptance\analysis.json `
  --request examples\structured_generation\fuel-combustion-fmea-acceptance\request.json
```

验收器会拒绝：

- 不匹配的运行编号、模板或证据包；
- 缺少 Flash 生成或 Pro 批评轨迹；
- FMEA 字段不完整、引用了包外证据或完全没有证据绑定；
- 已持久化、已确认、已发布的模型结果；
- S/O/D、RPN、传播关系或审批字段；
- 请求私有标记、证据私有标记、长证据原文、提示词或原始推理泄漏。

## 退出码和边界

- `0`：全部验收通过；
- `2`：输入或离线验收失败；
- `3`：密钥、模板、环境或 FMEA 映射配置失败；
- `4`：生成成功但需要人工复核，这是 `run-fmea` 的正常中间状态；一键脚本会继续做离线验收；
- `5`：模型调用、生成、批评或修复失败。

不要把 API 密钥、真实工厂资料或未脱敏记录提交到版本库。这个包只证明接口链路能生成有证据绑定、可审计、待人工复核的候选；工程师仍需确认系统边界、故障语义、证据充分性和后续风险评分。
