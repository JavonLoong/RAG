# PowerRAG PRD 实现追溯矩阵

更新时间：2026-09-02  
需求基线：`PowerRAG_PRD_Official_Completed.docx`，可审计内容源为 `build/prd_official_authoring/prd_content_v2.py` 中的 PR-P0、PR-P1、TECH、NFR 与 AC 条目。  
状态口径：`已实现` 表示已有代码和自动化证据；`部分` 表示主能力存在但正式数据/专家验收或子要求未齐；`未通过验收` 表示现有真实产物明确低于 PRD 门槛。

## 产品需求

| ID | 状态 | 当前证据 | 尚需完成/验收 |
| --- | --- | --- | --- |
| PR-P0-01 | 已实现 | `ProjectWorkspaceRegistry` 为每个项目创建独立目录和 SQLite；对象带 `project_id`；隔离测试覆盖。 | 用正式局域网 OIDC 账户再做一次跨项目越权验收。 |
| PR-P0-02 | 已实现 | 正式界面任务中心覆盖资料、OCR 页重试、索引、图谱、FMEA、GraphRAG 同题集批量评测和反馈修复，支持状态筛选、取消、重试、指派和评论。 | 需用正式试点任务做并发与人工操作验收。 |
| PR-P0-03 | 已实现 | `DeliveryTask` 统一状态、阶段、进度、错误、重试属性；租约/心跳/取消测试覆盖。 | — |
| PR-P0-04 | 已实现 | multipart 主上传路径、60 MB 实传测试、Base64 兼容接口、异步处理。 | Electron 受限路径交接仍需单独安全验收。 |
| PR-P0-05 | 已实现 | 源资产保存 MIME、大小、SHA-256、页数、时间、项目；重复文件 409 预检且不产生幽灵记录。 | DOCX 页数仅能在具备可靠渲染器时登记。 |
| PR-P0-06 | 已实现 | 自动/native/OCR/外部 parser 路由与依赖状态存在；未安装 parser 返回明确状态。 | 在目标设备上安装后的 capability 健康检查。 |
| PR-P0-07 | 已实现 | OCR/解析证据支持 block type、table、image、caption、bbox、reading order；表格错位进入阻断审核。 | — |
| PR-P0-08 | 已实现 | 单页失败保留其他页；`retry-pages` 后台任务只重跑所选页并生成新版本；记录引擎、耗时、置信度、错误。 | — |
| PR-P0-09 | 已实现 | 正式界面原页/解析块对照、页码切换、编辑后生成新版本；原资产不覆盖。 | DOCX 原页预览依赖 Office/LibreOffice 渲染器。 |
| PR-P0-10 | 已实现 | 项目化资料台账支持状态、文件名、document_id、版本、问题代码与稳定分页。 | — |
| PR-P0-11 | 已实现 | 源证据/阻断问题/最新人工批准发布门禁；发布支持 actor、comment、idempotency、expected version 和 409。 | — |
| PR-P0-12 | 部分 | 索引快照记录资料版本、模型、维度、分块、配置 hash、构建时间；hashing 标记 test-only。 | 正式固定嵌入 Provider 尚未在目标设备完成验收。 |
| PR-P0-13 | 已实现 | 治理资料索引和正式界面支持 keyword/semantic/hybrid（RRF）。 | — |
| PR-P0-14 | 已实现 | 检索和 GraphRAG 引用可打开注册源页及块/表/图定位；失败返回 `citation_integrity_error` 409。 | DOCX 精确页定位受渲染器限制。 |
| PR-P0-15 | 已实现 | 项目级不可变 Schema 目录支持草稿、批准、内容哈希、审计、模板复制和备份恢复；图版本记录 Schema ID、版本、哈希及完整定义。 | 需由领域负责人批准正式燃机 Schema 版本。 |
| PR-P0-16 | 已实现 | rules 基线；small-model/LLM 强制注册 Provider；记录模型、prompt version/hash、温度、超时、重试、耗时和原始响应摘要 hash。 | 用真实受控模型 Provider 做一次验收。 |
| PR-P0-17 | 已实现 | 按关系、类型、型号、置信度、证据状态、问题代码筛选；正式界面逐语句审核。 | — |
| PR-P0-18 | 已实现 | 类型/端点/证据/冲突发布门禁；发布/回滚/重同步 GraphStore；记录活动图版本和边数一致性。 | — |
| PR-P0-19 | 已实现 | GraphRAG 返回路径、图/文本证据、图版本、路由和回退原因；正式界面可查询并打开引用。 | 正式 LLM 答案 Provider 尚未配置，当前可用确定性证据摘要。 |
| PR-P0-20 | 已实现 | `gas_turbine_minimum_v1` v1.1.0 含字段、关系、证据和评分政策；项目级模板目录支持草稿、批准、不可变版本、内容哈希、审计、模板复制、备份恢复与运行时血缘。 | — |
| PR-P0-21 | 已实现 | FMEA 七类专业字段分别保存 evidence_id 和明细。 | — |
| PR-P0-22 | 已实现 | 字段修改必须携带证据；无证据/拒绝字段阻断发布；逐字段审核 UI。 | — |
| PR-P0-23 | 已实现 | 人工批准后发布；JSON/CSV/DOCX 内容一致性验证；正式横向 DOCX 导出。 | DOCX 视觉渲染 QA 因当前设备无 Word/LibreOffice 尚未完成。 |
| PR-P0-24 | 已实现 | 写操作 actor 来自本地认证或 OIDC/JWT 上下文；前端 actor 只读。 | — |
| PR-P0-25 | 已实现 | 审核人和发布操作者分别记录；同人兼任显式写入审计。 | 多人 OIDC 场景需实测。 |
| PR-P0-26 | 已实现 | 项目审计记录对象、版本、动作、操作者、原因、摘要、关联 ID 和结果；不复制完整原文。 | 继续审计遗留非 delivery 写接口。 |
| PR-P0-27 | 已实现 | Delivery 错误统一包含 code/message/stage/retryable/details/correlation_id；前端显示可执行错误。 | — |
| PR-P0-28 | 已实现 | 反馈按来源/解析/资料/图谱/FMEA 根因路由；修复运行保存受影响对象、执行步骤和状态，并重新生成或重新验证下游。 | 真实试点反馈仍需由责任人完成一次闭环签字。 |
| PR-P0-29 | 已实现 | 验收工作台显示 12 个正式门禁、责任角色、所需文件和实时指标；支持包内证据上传、SHA-256、乐观并发、审计日志和正式验收包生成。 | 仍需对应角色提供真实金标准与签字。 |
| PR-P1-01 | 已实现 | 批量资料审核、批量任务重试、项目模板复制、任务指派/评论；批量审核不发布且不绕门禁。 | 批量图语句/FMEA 字段审核仍坚持逐项选择，不提供“一键全过”。 |
| PR-P1-02 | 部分 | 已内置燃气轮机和电动机两套项目级 Schema、FMEA 模板和不同的正式 DOCX 报告版式；均带不可变版本、批准状态和内容哈希。 | 电动机领域尚未建立独立金标准，不能宣称该领域已验收。 |
| PR-P1-03 | 已实现 | `current_console` 已拆为外部样式、应用编排、API client、状态管理、共享组件和九个业务页面注册模块（含验收工作台）；页面进入事件由页面模块处理。FastAPI 已实际挂载相对 URL 所需的 `/modules`、`/styles`、`/libs`、`/assets`、`/demo_data`，浏览器实测不再出现脚本/样式 404。 | — |

## 技术要求

| ID | 状态 | 当前证据 | 尚需完成/验收 |
| --- | --- | --- | --- |
| TECH-01 | 已实现 | Project、SourceAsset、DocumentVersion、EvidenceLocator、IndexSnapshot、GraphVersion、FMEATask 均有持久化对象。 | — |
| TECH-02 | 已实现 | SourceAsset、DocumentVersion、EvidenceLocator、IndexSnapshot、GraphVersion、FMEATask 均携带 `project_id`、来源版本、`created_at`、`created_by`、内容 SHA-256 与配置 SHA-256；旧库自动补列且保留迁移标记；FMEA 与图来源一致性有门禁。 | — |
| TECH-03 | 已实现 | 每项目目录含 source_assets、governance、retrieval/chroma、graph、exports、logs、manifests。 | — |
| TECH-04 | 已实现 | 资料/图发布同步投影；失败投影状态为 failed；可重建、回滚、重同步并核对数量。 | — |
| TECH-05 | 已实现 | 解析、OCR 页重试、索引、图谱抽取、证据约束社区摘要、GraphRAG 同题集批量评测、FMEA 和反馈修复均使用后台任务，具备租约、心跳、取消、幂等、失败状态和重试分发。 | 需在正式资料上做并发、进程中断和恢复验收。 |
| TECH-06 | 已实现 | `/api/delivery` 有项目、台账、审核队列、FMEA、审计、健康、血缘相关接口；列表稳定排序/游标。 | — |
| TECH-07 | 已实现 | 20 MB 以上走 multipart/受限路径；全部小型 delivery 写接口统一支持 `Idempotency-Key` 请求指纹、并发占位、响应重放和异请求 409，大文件任务继续使用显式幂等键与 SHA-256 去重；内容更新/发布支持 expected version。 | — |
| TECH-08 | 已实现 | 解析/OCR/翻译/嵌入/图谱/答案 Provider 注册、health、capability、model/version、timeout、cost/data policy。 | 真实 Provider 配置尚未全部到位。 |
| TECH-09 | 已实现 | 外部 Provider 原文外发前执行项目数据策略和调用审计；涉密默认本地。 | — |
| TECH-10 | 已实现 | 单机本地身份与局域网 OIDC/JWT；delivery 独立中间件和 project 授权。 | 真实 IdP 联调待环境。 |
| TECH-11 | 已实现 | 预览/导出/恢复均限制到登记资产或项目根；ZIP 路径穿越测试；密钥不从前端复制。 | — |
| TECH-12 | 已实现 | 每个 `/api/delivery` 请求返回 correlation、`X-Response-Time-Ms`/`Server-Timing` 并写项目级去敏 JSONL；任务返回 duration，保存 stage、对象、版本、provider、retry 和 error；后台异常堆栈单独落盘，10 MB 轮转并保留 5 份。 | 需在正式运行周期核对容量与保留策略是否合适。 |
| TECH-13 | 已实现 | 健康包含治理库、检索/图投影、Providers、磁盘、最近失败任务。 | — |
| TECH-14 | 已实现 | 备份包含项目全目录、治理库、Provider/Schema 清单和去密钥控制面快照；任务、指派、评论、审计、投影状态可映射恢复，SHA-256 校验与路径安全测试通过。 | 需在正式试点项目上做一次恢复演练。 |
| TECH-15 | 部分 | 已有性能测量接口与小规模自动化；投影查询均为本地。 | 尚未在约定 Windows 参考设备、14 本正式库上形成 P95 验收报告。 |
| TECH-16 | 已实现 | 60 MB multipart 实传、202 异步、无 Base64、无请求超时测试通过。 | 浏览器人工观察“不卡死”仍需正式界面验收记录。 |
| TECH-17 | 已实现 | GraphSchema 和 FMEATemplate 目录使用不可变版本、状态与内容哈希；历史批准版本不可覆盖，项目模板复制生成目标项目独立目录。 | — |
| TECH-18 | 已实现 | 验收工作台把输入、上传证据、审计和输出限制在受控根目录；拒绝路径逃逸，manifest 递归记录相对路径、大小和 SHA-256。 | — |

## 非功能要求

| ID | 状态 | 当前证据 | 尚需完成/验收 |
| --- | --- | --- | --- |
| NFR-01 | 已实现 | 资料/图谱/FMEA 发布均有证据、阻断问题和版本一致性门禁；源资产、配置、Schema、模板、索引和图版本均保存哈希与血缘。 | 完整可复现结论仍以正式验收包为准。 |
| NFR-02 | 已实现 | 默认本地项目目录；密钥来自后端配置；外部 Provider 受数据策略和调用审计约束；日志去敏，文件范围受登记资产/项目根限制。 | 局域网部署仍需真实 OIDC 与传输配置验收。 |
| NFR-03 | 已实现 | 写接口幂等、expected version、后台任务租约/心跳/取消/重试、部分页恢复、不可变发布/回滚和备份恢复均有自动化覆盖。 | 正式进程中断与恢复演练待签字。 |
| NFR-04 | 部分 | 长任务均异步，60 MB multipart 实传已通过；检索、图路径和预览有测量接口。 | TECH-15 参考设备 P95 与 TECH-16 浏览器观察尚未签字。 |
| NFR-05 | 已实现 | 解析/OCR/翻译/嵌入/图谱/答案 Provider 注册，Schema、模板、投影接口化；燃气轮机和电动机目录验证核心治理逻辑可复用。 | 新领域必须单独建立金标准。 |
| NFR-06 | 已实现 | 请求/任务 correlation_id、阶段耗时、Provider、重试、错误、投影状态、轮转日志和健康接口存在；前端拆为页面/API/状态/组件模块并有合同测试。 | 正式运行周期需核对日志容量策略。 |
| NFR-07 | 部分 | 状态具有文字标签，正式页面与 FastAPI 静态路径合同通过；Electron 与本地 Web 均为主路径。 | 完整键盘可访问性与依赖缺失提示仍需人工无障碍验收。 |

## 验收要求

| ID | 当前判定 | 权威现状 |
| --- | --- | --- |
| AC-M2-01 | 未通过验收 | 正式验收器读取既有真实 OCR 报告：13 本、5483 页中 5481 页有文本/结构；其余 2 页已根据初始 OCR、高分辨率重识别和夜间 5 组候选记录形成页面级阻断，覆盖核算为 100%。当前仍缺 clear、low_quality、table、dual_column、image 五类逐页人工签字，因此不能通过。验收器已拒绝仅填写页数或分类名的伪证据。 |
| AC-M2-02 | 未通过验收 | 现有报告主要是完整性、置信度和风险；缺少按 PRD 分层抽样的人工金标准 CER/关键字段正确率正式签字包。 |
| AC-M3-01 | 未通过验收 | 既有 10 问报告只有“6 个能检索到证据、4 个结果弱”，没有专家相关块标注、Recall@5/MRR/引用可解析率，不能据此宣称达到 80%。 |
| AC-M3-02 | 部分 | 代码覆盖无答案停止、版本限定、回滚与冲突/回退机制；缺真实专家问题集签字。 |
| AC-M4-01 | 未通过验收 | 现有人工 POC 只有 27 条候选（26 correct、1 discuss），低于不少于 100 条金标准关系，且没有召回率分母。 |
| AC-M4-02 | 部分 | 发布图证据绑定率/Schema/端点逃逸门禁和 RAG/GraphRAG 同题比较代码已实现；缺 100 条真实集结果。 |
| AC-M5-01 | 未通过验收 | 字段证据门禁已实现，但缺领域专家对真实 FMEA 的接受/轻改/重大修改/拒绝统计。 |
| AC-M5-02 | 已实现（代码） | JSON/CSV/DOCX 一致性和血缘测试通过，未批准评分政策时 S/O/D/RPN 为空；仍待真实任务签字。 |
| AC-E2E-01 | 部分 | 正式界面已覆盖创建、接入、问题处理、资料/图/FMEA 发布、导出、反馈回流；新增“验收工作台”显示责任人、上传包内证据、保存双人签字文件并实时重算门禁。仍需知识工程师和领域审核人实际走一遍并签字。 |
| AC-E2E-02 | 部分 | 正式界面已有索引重建、图重同步、资料回滚、项目恢复；验收工作台可用 SHA-256 乐观锁保存九类输入、一键生成递归证据哈希清单和开放工作队列，但当前仍缺试点角色真实恢复演练签字。 |

## 自动化证据

- 主交付测试：`tests/unit/test_delivery_product_control.py`、`tests/unit/test_delivery_api.py`。
- M2：`tests/unit/test_m2_completion.py`。
- M4/GraphRAG：`tests/unit/test_graphrag_completion_acceptance.py`、`tests/unit/test_governed_delivery_workflow.py`。
- M5：`tests/unit/test_m5_completion.py`。
- 正式前端脚本：`frontend_app/current_console/index.html` 与 `frontend_app/current_console/modules/`，由 Node 语法检查覆盖。
- 真实历史材料：`docs/project_deliverables/02_OCR结果_13本扫描PDF/OCR交付前验收报告.md`、`docs/project_deliverables/04_检索测试结果_10个问题/检索测试报告_10个问题.md`、`docs/project_deliverables/05_知识图谱POC_三元组和人工判断/人工判断小结.md`。
- 当前机器生成验收包：`build/prd_acceptance_current/acceptance.md`、`acceptance.json`、`work_items.json` 和 `manifest.json`；结论为 `not_accepted`。`work_items.json` 已把 12 个未关闭项映射到责任角色和应交证据。所有人工/实测门禁均要求具名时间、验收包内证据引用和 SHA-256 清单，未把布尔声明、分类名称或缺少金标准的项目算作通过。

本矩阵不把“代码可运行”冒充“真实数据与专家验收已通过”。只有“尚需完成/验收”列全部清零，且验收包由指定角色签字，才可以把整份 PRD 标为完成。
