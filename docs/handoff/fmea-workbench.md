# FMEA 本地工作台

工作台是现有 FMEA REST 接口的薄客户端，不包含第二套评分、传播、审批或检索引擎。Task 7 已完成实现、定向验证与复审，详见 [验证记录](phase4-task7-workbench-verification.md)；本说明不是 Phase 4 全产品验收结论。

## 本地打开

使用项目现有工作区配置和本地鉴权。启动 API 的进程需要配置 `RAG_WORKSPACE_CONFIG`、`FMEA_LOCAL_AUTH_ENABLED=true`、`FMEA_REVIEW_TOKEN`、`FMEA_REVIEW_ACTOR_ID` 和 `FMEA_REVIEW_WORKSPACE_ID`；配置结构见 [本地配置](fmea-risk-closure.md)。真实令牌不得提交进仓库。

在仓库根目录运行：

```powershell
$env:PYTHONPATH = "api_server/current_console/chroma_rag_poc/src"
.venv\Scripts\python.exe -m uvicorn chroma_rag_poc.api:create_app --factory --host 127.0.0.1 --port 8000
```

浏览器访问 `http://127.0.0.1:8000/static/fmea.html`。输入已存在的分析 ID、行 ID、修订 ID 及本地访问令牌。工作区与人工身份由服务端鉴权决定，页面不允许自行声明审批身份。

令牌只在当前页面内存中使用，不从 URL 读取、不保存在浏览器存储；重新载入页面后需要重新连接。不要把本地鉴权接口直接暴露到公网。

## 操作边界

- 分析与证据：查询已有行上下文、字段状态、原文引用、定位符及 RAG/GraphRAG 来源信息；不会重新检索或创建知识库。
- 字段复核：查看不可变模型建议与人工记录；明确确认后提交接受、修改后接受、拒绝、补证或暂缓。复杂字段按接口合同输入 JSON，不会自动把建议转换为结论。
- 风险、传播、批准发布：页面展示服务端结果并提交显式命令；不自行计算 RPN、推断传播边或判定发布就绪。
- 模板与迁移：Office 文件先成为草稿，模型补丁不自动注册；接受模板变更与确认迁移仍是独立人工操作。
- 成果导出：区分草稿预览与已发布成果；运行状态、快照身份和制品摘要由服务端提供。

现有 REST 接口没有分析/行/模板发现列表，因此资源 ID 仍需从已有任务、CLI 输出或团队交接获取。模板、DomainPack、迁移适配器和模型供应商的服务端配置不属于此页面职责。

## 并发与重试

修改请求使用已读取的资源版本与唯一幂等键。发生版本冲突后刷新资源，用户核对最新内容并再次明确确认；不会自动重提权威操作。

“停止等待”只中止当前 HTTP 等待，不表示后端任务已取消。网络超时或中断后，写入结果可能未知；“重试原请求”保留原始内容与幂等键，并要求再次确认。不要把未知结果当成执行失败后另起一次同类操作。

服务端标记为可重试的错误（例如 503）同样保留原请求。写入进行中或存在未决写入时，不允许切换连接、断开连接或生成新幂等键绕过重试；关闭页面时会提示，但浏览器不能保证阻止用户最终离开。令牌和重试请求不落盘，离开页面后需通过服务端查询核实状态。

如果已收到写入成功回执、只是随后的状态读取失败，页面会明确保留成功回执，并提供“仅重试读取状态”；此操作只发 GET，不再次提交写入。

## 开发验证

```powershell
node --test tests/frontend/test-fmea-client.mjs tests/frontend/test-fmea-store.mjs tests/frontend/test-fmea-review-view.mjs tests/frontend/test-fmea-authority-views.mjs tests/frontend/test-fmea-delivery-views.mjs
.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_frontend_contract.py tests/browser/test_fmea_workbench.py -q
```

浏览器测试需要开发依赖及 Chromium：`.venv\Scripts\python.exe -m playwright install chromium`。默认测试使用离线夹具，不触发付费模型调用。

附加 Node 行为测试本次使用 Node 24.16.0；工作台本身是浏览器原生模块，没有前端构建步骤。浏览器测试依赖由 Python Playwright 提供。
