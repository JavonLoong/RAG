# api_server

服务接口层。当前主控制台已经迁移到 `current_console/`，继续承担上传、处理、检索、问答和日志接口。

- `current_console/server.py`：当前 FastAPI 启动入口。
- `current_console/chroma_rag_poc/src/chroma_rag_poc/`：当前核心后端包。
