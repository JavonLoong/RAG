# RAG 成熟项目最佳实践接入

这份文档把成熟开源 RAG 项目的做法转成当前仓库可以直接使用的工程边界。这里借鉴的是架构、流程和质量门槛，不是把外部仓库源码整段复制进来。复用开源代码时必须保留对应许可证和署名。

## 参考项目

- RAGFlow：文档理解、chunk 可解释、引用溯源。
- Dify：应用、工作流、模型供应商、知识库边界。
- FastGPT / MaxKB：中文知识库产品流、可视化配置、企业问答。
- AnythingLLM / Open WebUI：低门槛本地部署、本地模型和知识库体验。
- Haystack：显式 pipeline 节点、转换器、retriever、ranker、generator。
- LlamaIndex：reader、node、metadata、query engine。
- LightRAG / Microsoft GraphRAG：轻量图检索、社区摘要、local/global search。
- RAGAS：faithfulness、answer relevancy、context recall 等评测思路。

参考链接：

- RAGFlow DeepDoc: https://github.com/infiniflow/ragflow/blob/main/deepdoc/README.md
- RAGFlow PDF parser selection: https://github.com/infiniflow/ragflow/blob/main/docs/guides/dataset/select_pdf_parser.md
- Docling: https://www.docling.ai/
- Docling GitHub: https://github.com/docling-project/docling
- Unstructured partitioning: https://docs.unstructured.io/open-source/core-functionality/partitioning

## 直接使用入口

在 Python 里查看当前仓库对成熟项目能力的接入状态：

```python
from rag_orchestrator import build_default_profile

profile = build_default_profile()
print(profile.to_markdown())
```

文档解析现在有一个统一入口，不需要再直接调用散落在 console demo 里的 parser/chunker：

```python
from pathlib import Path

from data_pipeline.document_intake import DocumentIntakeOptions, run_document_intake

path = Path("example.pdf")
result = run_document_intake(
    path.name,
    path.read_bytes(),
    options=DocumentIntakeOptions(parser_backend="docling"),
)

if result.status == "parsed":
    chunks = result.chunks
elif result.status == "needs_ocr":
    print(result.profile.recommended_next_step)
else:
    print(result.errors)
```

这个入口目前做的事情：

- 识别 PDF、DOCX、TXT、Markdown、CSV、TSV、JSON、JSONL、NDJSON、代码和日志文件。
- PDF 默认按 RAGFlow/DeepDoc、Docling 那类“版面 + 表格 + OCR 风险”路线处理；原生文本提不出来时返回 `needs_ocr`，不是直接炸掉。
- 支持 RAGFlow 式 parser/chunk 解耦：`parser_backend` 可以表达 `deepdoc`、`mineru`、`docling`、`native`，`chunking_method` 可以表达 `general`、`manual`、`paper`、`book`、`laws`、`presentation`、`one`。
- PDF 会生成视觉任务计划：`ocr`、`document_layout_recognition`、`table_structure_recognition`、`table_auto_rotation`。这些任务是队列/接口层；当前已接入完整 Docling runtime，RapidOCR 标准依赖也已补齐，但 DeepDoc/MinerU 还没有作为本地模型 runtime 接入。
- JSONL/NDJSON 按一行一条结构化记录处理，避免被当成普通文本。
- 返回 `profile`、`quality`、`warnings`、`errors`、`records`、`chunks`，前端/API 可以直接拿去做 chunk preview 和失败文件分流。
- 返回 `processing_plan`、`page_diagnostics`、`chunk_preview`，可以直接做解析预览、失败页定位、引用锚点展示。
- 每个 chunk 要求带 `source_file`、`record_id`、`page_nums`、`source_kind`、`char_count`、`estimated_tokens`，这是后续引用溯源和评测的底线。

当前本地已经接入并验证过的 Docling runtime 组合：

```powershell
.\.venv\Scripts\python.exe -m pip install docling opencv-python
```

`pyproject.toml` 的 `external-docs` extra 也已经记录这组依赖。当前环境安装完整 `docling` 时曾被正在运行的 OCR 服务锁住 `cv2.pyd`；已通过短暂停止并重启该服务解决，现在 `pip check` 为干净状态。

入库时直接指定 Docling backend：

```python
from chroma_rag_poc.pipeline import ingest_source_payloads

result = ingest_source_payloads(
    payloads=[("manual.md", Path("manual.md").read_bytes())],
    collection_name="docling_demo",
    parser_backend="docling",
)
```

HTTP 接口也已经支持：

- `/api/process` JSON body: `{"parser_backend": "docling"}`
- `/api/ingest` form field: `parser_backend=docling`

`auto` backend 现在会把需要视觉/版面解析的格式自动送进 Docling：`PPTX`、`Spreadsheet` (`.xlsx`/`.xls`) 和 `Image` (`.png`/`.jpg`/`.jpeg`/`.tif`/`.tiff`/`.bmp`) 都已经进上传白名单和 document intake 路由。直接调用旧的文本 parser 读取这些二进制格式会被拒绝，避免把压缩包字节误当文本切 chunk。

当前 `/api/process` 和 `/api/ingest` 背后的 `ingest_source_payloads()` 已经切到 `run_document_intake()`。返回结果里的 `file_summaries` 会包含：

- `intake_status`
- `parser_route`
- `processing_plan`
- `page_diagnostics`
- `chunk_preview`
- `quality_gate_status`

扫描 PDF 会进入 `needs_ocr`，不会被伪装成普通解析异常。

检索底座现在也有 Haystack/LlamaIndex 风格的增强入口：

```python
from retrieval_engine import HybridRetriever
from model_adapters.reranker import CrossEncoderReranker

retriever = HybridRetriever(
    [dense_retriever, keyword_retriever, graph_retriever],
    fusion_mode="rrf",
    query_rewriter=my_query_rewriter,
    reranker=CrossEncoderReranker(),
    no_answer_min_score=0.12,
)

results = retriever.retrieve(
    "燃机叶片检查",
    top_k=5,
    filters={
        "operator": "AND",
        "conditions": [
            {"field": "meta.source_kind", "operator": "==", "value": "PDF"},
            {"field": "meta.year", "operator": ">=", "value": 2025},
        ],
    },
)

diagnostics = retriever.last_diagnostics
```

这个入口目前做的事情：

- `fusion_mode="rrf"`：按 LlamaIndex 的 reciprocal rank fusion 思路做多路结果融合，不再只靠不同检索器的原始分数硬加。
- `query_rewriter=...`：支持把原问题改写/扩展成多个查询，再统一进入 fusion。
- `filters={...}`：支持 Haystack 风格 metadata filter，能按 `meta.source_kind`、年份、来源等字段缩小检索范围。
- `reranker=...`：继续支持 CrossEncoder/LLM rerank，但失败会进入 `last_diagnostics.reranker_error`，不再静默吞掉。
- `no_answer_min_score` / `no_answer_min_results`：证据太弱时直接返回空结果，并在 `last_diagnostics.no_answer_reason` 里说明原因。

标准检索 API 现在也把这套协议暴露到产品层：`/api/search` 会通过 `HybridRetriever(fusion_mode="rrf")` 融合 Chroma vector 和 keyword 两路检索，并返回 `retrieval_diagnostics`，包含 `original_query`、`rewritten_queries`、`fusion_mode`、候选数、`reranker_error`、`no_answer_reason` 和 retriever 分布。控制台搜索结果顶部会渲染 `Retrieval Diagnostics` 卡片，所以用户不需要打开 raw JSON 就能看到这次检索是不是 hybrid/RRF、有没有 query rewrite、有没有 rerank 错误、为什么 no-answer。POST/GET 搜索还可以显式传 `query_rewrite=true` 打开模板 query expansion，传 `reranker=noop` 或 `reranker=cross_encoder` 打开可选 rerank 诊断；传 `graph_db_path=...` 时，还会把 `SQLiteGraphRetriever` 作为 graph 路径加入同一个 RRF adapter；POST 搜索还能传 `filters={...}` 做 Haystack 风格 metadata filter，传 `no_answer_min_score` 或 `no_answer_min_results` 阻断弱证据。自然语言里出现 markdown/pdf/txt/docx/csv/json 这类 source type、具体文件名或 20xx 年份提示时，会自动生成 `source_ext` / `source_file contains` filter；出现 author/作者、department/部门、product/产品 和 `2024-01-01 to 2024-12-31` 这类日期范围时，会自动生成 `meta.author`、`meta.department`、`meta.product`、`meta.source_date >=/<=` 业务 metadata filter；`retrieval_policies.json` 里的 `metadata_field_aliases` 可以把这些规范字段映射到真实语料字段，比如 `meta.source_date -> meta.document_date`、`meta.author -> meta.owner`，并在 `retrieval_diagnostics.auto_filters` 和 `effective_filters` 里显示映射结果。评测报告现在会输出 `retrieval_default_policy` / `Retrieval Default Policy`，把召回、引用、风险、no-result 指标翻译成 query rewrite、reranker、graph、no-answer gate 的默认策略建议；把建议写入 Chroma persist 目录下的 `retrieval_policies.json` 后，`/api/search` 会自动按 collection 应用 query rewrite、reranker、filters、metadata aliases 和 no-answer 默认值。`POST /api/retrieval/policies/roles/upsert` 可以在服务端 `role_registry` 里登记 reviewer/approver/admin/owner 角色和 collection assignment；`POST /api/retrieval/policies/directory/sync` 可以导入 SCIM 风格 users/groups、`role_group_mappings` 和 `recipient_defaults`，批量同步 `role_registry` 与 `notification_recipient_registry`；目录里 `active=false` 的用户会被标成停用并清空角色，不能再靠请求体伪造 approver/owner 通过审批；设置 `RAG_POLICY_OIDC_REQUIRED=1`、`RAG_POLICY_OIDC_ISSUER`、`RAG_POLICY_OIDC_AUDIENCE`、`RAG_POLICY_OIDC_JWKS_URL` 后，`/api/retrieval/policies/propose`、`/api/retrieval/policies/approve`、`/api/retrieval/policies/reject` 会要求 `Authorization: Bearer <OIDC JWT>`，用 PyJWT 通过 JWKS 校验签名、issuer、audience、exp，并用 token subject 覆盖请求体里的 reviewer/approver；`RAG_POLICY_OIDC_SUBJECT_CLAIM` 默认用 `email`，可以改成 `preferred_username` 或别的 claim。`POST /api/retrieval/policies/identity-provider/upsert` 也可以把同一套 OIDC 配置作为 `identity_provider.oidc` 写入 `retrieval_policies.json`：传 `provider="oidc"`、`enabled`、`issuer`、`audience`、`jwks_url`、`subject_claim`、`groups_claim` 和 `algorithms`；`GET /api/retrieval/policies/identity-provider` 可以读取当前配置；`client_secret` 这类请求字段会被忽略，不会落盘。控制台 `Retrieval Policy Review` 面板还提供 `Use Token` / `Clear Token`：把 reviewer 的 OIDC JWT 临时放进浏览器 `sessionStorage`，并对 `/api/retrieval/policies...` 请求自动附加 `Authorization: Bearer`，关闭标签页后清除。`POST /api/retrieval/policies/propose` 可以先创建 pending 策略草案但不生效；`POST /api/retrieval/policies/approve` 会优先使用 token subject 对应的 `role_registry` 服务端角色和 collection assignment，只有未启用 OIDC 的兼容路径才使用请求体角色，并会阻止同一个 reviewer 自己审批；`POST /api/retrieval/policies/reject` 可以拒绝不安全草案并写入 rejection audit；兼容路径 `POST /api/retrieval/policies/promote` 仍可直接把审核后的策略写入 `retrieval_policies.json`；`GET /api/retrieval/policies/history` 可以读取当前策略、pending proposals、audit 历史和最近两版 added/removed/changed diff；`POST /api/retrieval/policies/rollback` 可以把 collection 恢复到上一次审核过的策略，并继续追加 rollback audit entry；控制台搜索页已有 `Retrieval Policy Review` 面板支持 managed IdP config、tab-scoped token session、directory sync、role upsert、propose、approve、reject、promote、history/diff 和 rollback。当前剩余差距是真实 SSO 登录/callback/session exchange、租户管理、密钥轮换运维，以及真实语料字段覆盖率和阈值校准。

补充：检索策略提案现在已经支持 `assigned_to` / `due_at`，会把待审任务写入本地 assignment notification outbox；`GET /api/retrieval/policies/notifications?recipient=...&status=pending` 可以按接收人读取 pending 通知，控制台 `Retrieval Policy Review` 面板也能 Load Notifications 并把 `proposal_id` 带回 approve/reject 流程。`POST /api/retrieval/policies/notifications/dispatch` 支持 `delivery_mode="outbox_file"`，会把 pending 通知投递到 persist 目录下受路径保护的 JSONL outbox，并把通知状态改成 `delivered`、追加 `dispatch_notification` audit；也支持 `delivery_mode="webhook"` + `webhook_url`，向 HTTPS 外部 webhook 发送真实 POST，本地测试只允许 `http://127.0.0.1` / `localhost` 这类 loopback URL；`webhook_template="lark_text"` 会生成 Lark/飞书文本机器人风格 payload，`webhook_template="dingtalk_text"` / `webhook_template="wecom_text"` 会生成钉钉/企微文本机器人风格 payload；`webhook_template="pagerduty_event_v2"` 会生成 PagerDuty Events API v2 trigger payload，并用 `webhook_routing_key_env` 指定服务端环境变量里的 routing key；`webhook_template="opsgenie_alert"` 会生成 Opsgenie alert payload，可以用 `webhook_auth_header_name="Authorization"`、`webhook_auth_scheme="GenieKey"`、`webhook_auth_token_env` 从环境变量拼认证头；`webhook_signing_secret_env` 会从服务端环境变量读取密钥并发送 `hmac-sha256` 签名头，密钥不会写入 `retrieval_policies.json` 或 API 响应；也支持 `delivery_mode="smtp"` + `smtp_host` / `smtp_port` / `smtp_from` / `smtp_to` / `smtp_subject` / `smtp_use_tls` / `smtp_username_env` / `smtp_password_env` 直发邮件，SMTP 用户名和密码只从服务端环境变量读取，不会写入 `retrieval_policies.json` 或 API 响应；webhook 或 SMTP 失败不会再让整条审批通知流直接中断，返回体和 audit 会区分 `attempted_count`、`dispatched_count`、`failed_count`，通知会标成 `failed`，delivery 里保留 failed delivery 的 status/error/response 供重试和审计；控制台也有 Delivery mode、Webhook URL、Webhook template、Signing secret env、Webhook routing key env、Webhook auth header/token env/scheme、SMTP host/port/from/to/subject/TLS/env 和 Dispatch Notifications 按钮。这里还没接的是企业 IdP、企业通讯录收件人解析、产品级账号配置和真实值班升级流，不是本地通知队列、webhook、SMTP 或 PagerDuty/Opsgenie 模板边界。

`POST /api/retrieval/policies/notification-recipients/upsert` 可以把 `policy-approver` 这类本地主体登记到 `notification_recipient_registry`，保存 email、webhook_url、webhook_template、webhook_signing_secret_env、webhook_routing_key_env、webhook_auth_header_name、webhook_auth_token_env、webhook_auth_scheme 和 preferred_delivery_mode；`GET /api/retrieval/policies/notification-recipients` 可以读取注册表；dispatch 时如果没有显式传 `smtp_to`、`webhook_url`、事故平台模板或认证 env 字段，会按通知 recipient 从注册表自动解析，并在 delivery/audit 里写入 `recipient_source="notification_recipient_registry"`。`/api/retrieval/policies/directory/sync` 则把企业目录导出的 users/groups 一次性灌进这两个注册表：group 通过 `role_group_mappings` 映射到 reviewer/approver/admin/owner 与 assigned_collections，email/webhook 默认值通过 `recipient_defaults` 继承，停用账号用 `active=false` 保留审计但失效。OIDC/JWKS enforcement、managed IdP config、PKCE login URL、hosted callback、HttpOnly session、server-side refresh_token session refresh、AESGCM 加密落盘和 tab-scoped `sessionStorage` token bridge 补的是资源服务器验 token、配置落盘、浏览器登录跳转和控制台请求授权头的边界，不是完整企业 IAM 产品；剩下的是租户级 IdP 管理、session 管理和密钥轮换运维。

OIDC 登录链路现在也补了一层可直接接企业 IdP 的 PKCE 桥接：`POST /api/retrieval/policies/identity-provider/upsert` 除了 `jwks_url`，还可以保存 `authorization_endpoint`、`token_endpoint`、`client_id`、`client_secret_env`、`redirect_uri` 和 `scopes`；`client_secret_env` 只保存环境变量名，真实 client secret 仍从服务端环境变量读取，不会写入 `retrieval_policies.json`。`POST /api/retrieval/policies/identity-provider/login-url` 会生成带 `state`、`nonce`、`code_challenge`、`code_challenge_method=S256` 的授权 URL，把 `state`、`nonce`、`code_verifier` 和 redirect_uri 写进 `retrieval_policy_oidc_states.json`，并下发 `HttpOnly` / `SameSite=Lax` 的 `rag_policy_oidc_state` cookie。用户完成 IdP 登录后，`GET /api/retrieval/policies/identity-provider/callback?code=...&state=...` 会校验 `rag_policy_oidc_state`，消费服务端保存的 `state/code_verifier`，换取 token，验证 `id_token` 或 `access_token`，把 IdP 返回的 `refresh_token` 只存进服务端 `retrieval_policy_sessions.json`，再创建 HttpOnly policy session。如果设置 `RAG_POLICY_SESSION_SECRET_KEYS=activeKid:base64urlKey,oldKid:base64urlKey`，refresh token 会以 `refresh_token_encrypted` 结构用 AESGCM 加密落盘；第一个 key 负责新写入，后面的 old key 只负责解旧 session，用来做基础 key rotation。控制台仍保留手工粘 code 的兼容路径：`POST /api/retrieval/policies/identity-provider/token` 会用 `code`、`code_verifier` 和 `redirect_uri` 换取 token，再把 token 放进 `Use Token` 的 `sessionStorage` 临时登录态。这里已经不是手工粘 JWT 的唯一方式，但仍不是完整托管 SSO 产品：还缺租户级 IdP/session 管理和密钥轮换运维。

控制台现在还可以把已验证的 OIDC token 升级为服务端 session：`POST /api/retrieval/policies/identity-provider/session` 接收 `Authorization: Bearer <OIDC JWT>`，后端先按 JWKS 校验 token，再写入 `retrieval_policy_sessions.json` 并下发 `HttpOnly` / `SameSite=Lax` 的 policy session cookie；之后 `/api/retrieval/policies/propose`、`approve`、`reject` 即使没有显式 Authorization header，也会从 cookie 解析 reviewer/approver 身份。`POST /api/retrieval/policies/identity-provider/session/refresh` 会用 session 里服务端保存的 `refresh_token` 调 IdP 的 refresh grant，重新验证返回的 `id_token` 或 `access_token`，如果 IdP 轮换了 refresh_token 就覆盖旧值，并续期 HttpOnly cookie。租户管理员可以先在 `role_registry` 里给 OIDC subject 登记 `admin` 或 `owner`，再用 `GET /api/retrieval/policies/identity-provider/sessions` 查看脱敏后的活跃 session 列表；响应只返回 subject、groups、过期时间、是否有 refresh token、secret_storage 等元数据，不返回 refresh token 或 AESGCM ciphertext。控制台的 Retrieval Policy Review 面板现在有 `OIDC session inventory` 表格，展示 subject、groups、`secret_storage`、`has_refresh_token` 和过期时间，管理员可以点 Select 把 session id 填进撤销输入框；`Session admin audit` 会显示最近一次 `identity_provider_session_key_rotate` 或 `identity_provider_session_revoke` 动作。`GET /api/retrieval/policies/identity-provider/sessions/key-status` 是只读密钥运维体检：返回 `active_key_id`、`key_source`、`stale_encrypted_session_count`、`plain_refresh_session_count`、`rotation_due` 和 `rotation_due_reasons`，不会返回 key material、refresh token 或 ciphertext；设置 `RAG_POLICY_SESSION_KEY_MAX_AGE_SECONDS` 后，可以把上次 `identity_provider_session_key_rotate` audit 距今时间纳入 rotation due 判断。控制台里对应的是 Key Status。`POST /api/retrieval/policies/identity-provider/sessions/rotate-key` 会用 `RAG_POLICY_SESSION_SECRET_KEYS` 的第一个 active key 重加密已有 `refresh_token_encrypted`，同时仍可用后面的 old key 解旧 session，并向 `retrieval_policies.json` 追加 `identity_provider_session_key_rotate` audit entry；审计只记录 admin、role_source、active_key_id、rotated_count、session id 等元数据，不写 refresh token 或 ciphertext。`DELETE /api/retrieval/policies/identity-provider/sessions/{session_id}` 可以立即撤销某个服务端 session，并追加 `identity_provider_session_revoke` audit entry；控制台里对应的是 Load Sessions、Revoke Session 和 Rotate Keys。`POST /api/retrieval/policies/identity-provider/logout` 会删除当前服务端 session 并清掉 cookie。剩下没补的是更完整的 SSO 管理页和密钥轮换 runbook。

GraphRAG 底座现在加了 LightRAG 风格的查询模式入口：

```python
from rag_orchestrator import LightRagQueryEngine

engine = LightRagQueryEngine(
    text_retriever=hybrid_text_retriever,
    graph_retriever=sqlite_graph_retriever,
    global_searcher=global_search_orchestrator,
)

result = engine.query("燃机叶片维护风险有哪些关联主题？", mode="mix", top_k=8)
print(result.context)
print(result.diagnostics.to_dict())
```

这个入口目前做的事情：

- `mode="naive"`：只走普通文本/向量/关键词检索，等价于 LightRAG 的非图检索路径。
- `mode="local"`：只走实体邻域图检索，用 `SQLiteGraphRetriever` 查低层实体和关系细节。
- `mode="global"`：只走社区摘要/全局搜索，用 `GlobalSearchOrchestrator` 查高层主题。
- `mode="hybrid"`：合并 local + global，适合既要实体关系又要主题背景的问题。
- `mode="mix"`：默认推荐，合并 naive + local + global，也就是文本证据、图证据、社区证据一起进上下文。
- `LightRagDiagnostics` 会记录每条路径返回多少证据、最终融合多少条、global 是否失败。

GraphRAG 现在也有质量门，图谱没过关不能默认拿去回答：

```python
from rag_orchestrator import GraphQualityThresholds, evaluate_graph_quality

report = evaluate_graph_quality(
    graph_store,
    thresholds=GraphQualityThresholds(
        min_evidence_coverage=1.0,
        min_edge_confidence=0.7,
        max_isolated_node_rate=0.0,
        min_community_assignment_coverage=1.0,
        min_community_summary_coverage=1.0,
        min_summary_evidence_coverage=1.0,
    ),
)

if report.gate_status != "pass":
    print(report.to_dict())
```

这个门槛会检查：每条边是否有 evidence、低置信度边比例、孤立节点比例、节点是否进入社区、社区是否有摘要、社区摘要是否绑定 evidence/triple id，以及多句社区摘要是否有逐句 `sentence_evidence` 和原文 `source_evidence` 绑定。它抄的是 Microsoft GraphRAG/LightRAG 里“图谱不是能查就能用，必须先有结构质量和证据绑定”的工程边界。

`/api/query` 已经默认接入这个门槛：只要请求带 `graph_db_path`，并且实际路由走 `local`、`global` 或 `aggregation`，后端会先跑 `evaluate_graph_quality(graph_store)`。失败时直接返回 `422`，`detail.graph_quality` 会告诉你哪些指标没过；成功时响应里会带 `graph_quality`。如果只是调试坏图谱，可以临时传 `allow_unsafe_graph=true`，生产请求不要开。

控制台回答面板现在会渲染 `Graph Quality Gate`：成功回答显示 pass/fail、核心覆盖率指标和 bypass 状态；质量门阻断时会展示失败指标、缺 evidence 的边、低置信度边、孤立节点、缺摘要社区、缺 evidence 的社区摘要、逐句证据绑定不足的摘要和缺少原文 source span 的摘要。这样抄的是 RAGFlow / GraphRAG 产品里“答案旁边必须能看见证据健康度”的可解释边界。

回答面板的 Evidence 区域也会显示 `graph_community_source` 引用：GraphRAG global/community 摘要里的 `source_evidence` 会作为可见证据片段出现在答案后面，用户能从答案回到社区、三元组和原文 evidence。

GraphRAG 现在也有历史 triage 和 reviewer dashboard：`/api/query` 走图谱路径时会把通过或失败的 graph quality 状态、路由、citation 数量和 `source_evidence` 数量写入 `rag_orchestrator/triage.py` 管理的 JSONL；`/api/graphrag/triage` 可以按 `graph_quality_status`、`review_status`、`route_strategy` 过滤历史记录，`/api/graphrag/triage/{triage_id}/review` 可以写入 `accepted` / `rejected` 和 review note，`/api/graphrag/triage/export` 可以导出筛选后的 JSONL，`/api/graphrag/triage/analytics` 可以汇总图质量状态、review 状态、路由策略、失败指标、source evidence coverage、`failure_trend` 和 `route_drilldown`，`/api/graphrag/triage/{triage_id}/promote` 可以把坏样本追加到运行时 `evaluation/graphrag_triage_regression.jsonl`。控制台的 `GraphRAG Triage History` 面板会展示这些记录，并支持 graph quality / review status / route strategy 过滤、快速 review、导出和一键 promote；其中 `kgTriageAnalytics` 会直接渲染 source evidence coverage、`promoted_case_count`、failure trend、route-level drilldown、路由分布和失败指标分布。`scripts/run_graphrag_triage_regression.py --persist-dir <chroma_dir> --collection <collection>` 已经接入 GitLab `rag-smoke-job`，没有 promoted case 时允许空集通过，有 promoted case 时会用 `LocalChromaRegressionRag` 查询本地 Chroma 并作为真实回归 gate。现在还缺的是 reviewer assignment、重复失败告警、以及真实 LLM profile 下的 GraphRAG 回归重跑。

`/api/query` 现在也会返回 `lightrag_diagnostics`，并把同一份 `LightRagDiagnostics` 写进 triage 记录。它会列出当前问题、LightRAG 模式、route strategy、naive text / local graph / global community 三路 evidence 数量、最终 citation 数量、active paths 和 source type 分布。控制台回答面板会渲染 `LightRAG Diagnostics` 区块，不用打开 raw JSON 也能看到三路检索贡献。这个做法抄的是 LightRAG / GraphRAG 项目里“混合检索必须解释每一路贡献”的工程边界；目前还没做的是把这份诊断升级成可点击的 route-level drilldown。

评测现在有一个 RAGAS/DeepEval 风格的本地 harness，可以直接对一个 RAG 对象跑问题集和质量门槛：

```python
from evaluation import EvaluationThresholds, RAGEvaluationCase, RAGEvaluationHarness

cases = [
    RAGEvaluationCase(
        id="q1",
        question="燃机叶片维护风险有哪些证据？",
        reference_answer="答案必须引用叶片维护风险相关证据。",
        expected_evidence_keywords=["叶片", "维护", "风险"],
        task_type="ordinary_rag",
        source_scope="manuals",
        grading_notes="必须命中证据关键词并带引用。",
    )
]

harness = RAGEvaluationHarness(
    rag_system=my_rag_system,
    thresholds=EvaluationThresholds(
        min_keyword_recall_at_k=0.7,
        min_answer_completeness=0.7,
        max_missing_citation_rate=0.2,
        max_medium_or_high_risk_rate=0.4,
    ),
)
report = harness.run(cases, run_name="smoke")
paths = report.save("evaluation/reports")
print(report.gate_status, paths)
```

这个入口目前做的事情：

- 自动调用 `answer`、`query`、`search` 或 callable RAG 对象，不强迫改现有框架。
- 复用 `scripts/run_system_evaluation.py` 的 evidence keyword recall、answer coverage、citation missing rate 和 hallucination risk 指标。
- 输出 `evaluation_gate`：阈值、失败指标、失败案例数量和 `pass`/`fail`。
- 同时保存机器可读 JSON 和读者可读 Markdown，方便后续接 CI、控制台或人工复盘。

当前 profile 覆盖六个方面：

1. `document_parsing_product`
2. `engineering_boundary`
3. `retrieval_quality`
4. `graphrag`
5. `evaluation`
6. `operating_steps`

## 六块能力怎么抄

| 方面 | 主要借鉴 | 本地落点 | 现在状态 |
| --- | --- | --- | --- |
| 文档解析产品 | RAGFlow、Docling、Unstructured、LlamaIndex、Haystack | `data_pipeline/document_intake.py`、`pipeline.py`、`parsing.py`、OCR scripts、`data_pipeline/ocr_processing_stages` | 已有统一 intake、OCR 分流、页面诊断和 chunk preview；重视觉模型运行时还未内置 |
| 工程边界 | Dify、FastGPT、MaxKB、AnythingLLM | `server.py`、`api.py`、两个 `pyproject.toml`、前端控制台 | 可运行，但依赖、包边界和前端拆分需要收敛 |
| 检索质量 | Haystack、LlamaIndex、RAGFlow | `retrieval_engine/*`、`model_adapters/reranker.py`、`/api/search`、`/api/retrieval/policies/roles/upsert`、`/api/retrieval/policies/directory/sync`、`/api/retrieval/policies/identity-provider/upsert`、`/api/retrieval/policies/identity-provider`、`/api/retrieval/policies/propose`、`/api/retrieval/policies/approve`、`/api/retrieval/policies/reject`、`/api/retrieval/policies/promote`、`/api/retrieval/policies/history`、`/api/retrieval/policies/rollback`、`frontend_app/current_console/index.html`、`evaluation/harness.py` | `/api/search` 已接入 `HybridRetriever(fusion_mode="rrf")`，融合 Chroma vector + keyword，支持 `graph_db_path`、`query_rewrite=true`、`reranker=noop/cross_encoder`、POST `filters={...}`、source type/filename/year/author/department/product/date-range 自然语言 auto filter、`metadata_field_aliases` 字段别名映射和 no-answer 阈值，并返回 `retrieval_diagnostics`；评测报告已有 `retrieval_default_policy` / `Retrieval Default Policy`，`retrieval_policies.json` 已能应用 collection-level 默认策略，role_registry/directory sync/managed IdP config/OIDC JWKS bearer enforcement/propose/approve/reject/promote/history/rollback API 都有 audit entry、pending proposal、服务端角色门或 diff 输出，控制台 `Retrieval Policy Review` 面板支持 managed IdP config、Use Token sessionStorage 自动 Authorization、SCIM directory sync、role upsert、propose、approve、reject、promote、history/diff 和 rollback；还缺真实 SSO 登录/callback/session exchange、租户管理、真实语料字段覆盖率和阈值校准 |
| GraphRAG | LightRAG、Microsoft GraphRAG | `kg_pipeline/*`、`storage_layer/graph_store.py`、`rag_orchestrator/graph_quality.py`、`rag_orchestrator/triage.py`、`global_search.py`、`/api/query`、`/api/graphrag/triage`、`/api/graphrag/triage/export`、`/api/graphrag/triage/analytics`、`frontend_app/current_console/index.html` | local/global 主体、API 预回答图质量门、CI smoke、回答面板 Graph Quality Gate、摘要逐句 `source_evidence` 原文绑定、`graph_community_source` 引用 UI、`lightrag_diagnostics`、历史 triage/review/filter/export/analytics/promote、`failure_trend`、`route_drilldown`、`kgTriageAnalytics` reviewer dashboard 和 promoted regression gate 已有；还缺 reviewer assignment、重复失败告警和真实 LLM profile 回归重跑 |
| 评测 | RAGAS、Haystack eval、DeepEval | `evaluation/harness.py`、`evaluation/*`、`scripts/run_system_evaluation.py` | 有 60 题评测集、`RAGEvaluationHarness`、`LocalChromaRegressionRag` 和 quality gates；tiny smoke 与 GraphRAG promoted regression gate 已进 CI，还缺完整 60 题 CI/控制台强制执行 |
| 运行步骤 | AnythingLLM、Open WebUI、Dify | `start_local.bat`、`Dockerfile`、README、`.gitlab-ci.yml` | 有启动入口、CI `rag-smoke-job` 和 ingest-search-evaluation-graph-quality-`/api/query` fake-LLM global answer smoke；还缺真实 LLM profile |

## 不建议直接复制的东西

- 不要把 Dify、FastGPT、Open WebUI 的源码整段复制进本仓库后改名。它们的许可证或品牌条款可能限制商用、SaaS 或去标识。
- 不要直接把大型项目的前端框架搬进来。当前仓库的主要问题是边界混乱，先收敛主线再换框架。
- 不要先堆 GraphRAG 新功能。检索质量、引用、评测不过关时，GraphRAG 只会放大噪声。

## 推荐落地顺序

1. 先统一工程边界：一个包入口、一个依赖入口、一个运行入口。
2. 再补文档解析产品化：扫描件 OCR、表格/公式风险、chunk preview、页码引用。
3. 然后补检索质量：RRF fusion、query rewrite、rerank 错误显性化、metadata filter。
4. 再把 GraphRAG 质量门槛接进 API、CI 和控制台：社区摘要引用、isolated node、edge confidence、summary coverage。
5. 最后把 60 题评测和 `/api/query` GraphRAG global answer smoke 接到 CI；本地 fake-LLM smoke 已经能跑。

## 当前最小命令

启动当前控制台：

```powershell
cd D:\虚拟C盘\RAG\api_server\current_console
python server.py
```

运行一键 ingest-search-evaluation-graph-quality-`/api/query` smoke：

```powershell
cd D:\虚拟C盘\RAG
.\.venv\Scripts\python.exe scripts/run_rag_smoke_evaluation.py --persist-dir outputs/smoke_chroma --report-dir evaluation/reports --collection rag_smoke
```

命令成功时会输出 `gate_status=pass graphrag_query=pass graphrag_global=pass`。这里的 `graphrag_global` 使用本地 fake LLM 验证 `/api/query mode=global` 的 GraphRAG 生成链路，不依赖外部 API key。

GitLab CI 里 `rag-smoke-job` 会在 Docker build 后、deploy 前运行同一条 smoke，并用 `grep` 强制检查 `gate_status=pass`、`graphrag_query=pass`、`graphrag_global=pass`。

运行生产 profile 测试：

```powershell
cd D:\虚拟C盘\RAG
.\.venv\Scripts\python.exe -m pytest tests/unit/test_production_profile.py -q
```

运行现有单元测试：

```powershell
cd D:\虚拟C盘\RAG
.\.venv\Scripts\python.exe -m pytest tests/unit -q
```
