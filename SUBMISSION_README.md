# PowerRAG 核心源码提交说明

这是项目的核心可运行源码包，不包含本地运行产物和大体积资料。

## 运行方式

```powershell
cd PowerRAG_core_submission
python -m venv .venv
.\.venv\Scripts\pip install -e .
npm install
npm run check
npm run desktop
```

启动后可打开 `http://127.0.0.1:8000` 使用 Web 控制台，也可以使用 Electron 桌面窗口。

## 包含内容

- FastAPI 后端入口：`api_server/current_console/`
- Web 控制台：`frontend_app/current_console/`
- Electron 桌面壳：`electron/`
- RAG/GraphRAG 核心模块：`rag_orchestrator/`、`retrieval_engine/`、`kg_pipeline/`、`storage_layer/`
- 文档解析、评测和运维脚本：`data_pipeline/`、`evaluation/`、`scripts/`
- 配置、测试、核心文档和项目说明。

## 未包含内容

为避免提交包过大，以下内容未打包：

- `.venv/`、`node_modules/`
- 本地模型权重：`models/`、`local_models/`
- 原始 PDF、OCR 中间产物、ChromaDB 向量库、运行日志、评测缓存
- `.git/`、外部开源仓库镜像、发布站点副本、历史大文件归档

这些内容不是源码本身。正式复现时，应先安装依赖，再上传资料或重新执行入库流程生成向量库和图谱索引。

## 提交建议

作业提交建议采用“两件套”：

1. 提交本压缩包作为核心源码。
2. 另附项目演示页面、技术路线图或网盘/GitHub 链接，用于查看大体积资料、截图、报告和演示视频。
