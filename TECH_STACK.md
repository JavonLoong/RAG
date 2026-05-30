# RAG 项目完整技术栈清单 (Tech Stack)

这是一份本地 RAG 项目的完整技术栈清单。根据项目代码库（包括 `pyproject.toml`、前端源码以及后端的集成情况），整个系统构建在现代化、轻量级的架构之上。

## 1. 🎨 前端架构 (Frontend)
本项目前端采用了**零构建、零依赖**的原生架构，主打轻量、极速启动和本地浏览器直接渲染。
* **核心骨架**：原生 HTML5 + Vanilla JavaScript + CSS3（无 React/Vue，通过 `index.html` 单文件控制）。
* **UI 风格组件库**：玻璃拟物化设计 (Glassmorphism)，配合手写的动态微动画。
* **本地文件解析**：
  * **PDF.js** (Mozilla)：用于浏览器端纯本地加载和渲染 PDF，生成 Canvas 交给 OCR 引擎。
  * **PapaParse**：用于快速解析和表格化显示 CSV/TSV 等结构化数据。
  * **marked.js**：用于 Markdown 格式的实时渲染。
* **前端自带算法**：
  * **OnnxRuntime-Web (WASM)**：支持在浏览器本地纯前端运行模型。
  * **PaddleOCR.js**：基于 WebAssembly 运行的前端备用 OCR 引擎 (PP-OCRv5)。

---

## 2. 🧠 OCR 文档解析引擎 (Document Understanding)
系统采用“多级回退、多引擎并存”的设计来应对不同类型的复杂扫描件。
* **主力高精度引擎 (本地)**：**RapidOCR (ONNX Runtime)**
  * **并发架构**：通过 `ThreadPoolExecutor` 自行实现并发路由，利用 CPU 多线程能力（最高 12 个 Worker 并发处理），实现极速本地解析。
* **备用本地引擎**：**Tesseract-OCR** (主要用于对比测试和纯英文字段补全)。
* **前端 Web 引擎**：**PaddleOCR WASM版** (当本地 Python 服务器未开启时使用的兜底方案)。
* **商用云端 API**：**百度云 OCR (accurate_basic)**，仅在排版极其复杂时调用的高精度外部兜底。
* **原生文本提取**：**PyPDF (`pypdf`)** 与 **python-docx**（用于提取非扫描版的原生文字流）。

---

## 3. 💾 向量检索与混合数据库 (Vector & Storage Layer)
* **向量数据库**：**ChromaDB** (`chromadb>=0.5.23`)
  * 以本地 SQLite 的形式运行，不需要额外部署中间件。
* **文本嵌入模型 (Embeddings)**：**Sentence-Transformers** + **PyTorch** (`torch`)，支持加载各类开源大模型如 BGE-m3 等用于语义向量化。
* **全文稀疏检索 (Lexical Search)**：**BM25** (`rank-bm25`) + **结巴分词** (`jieba`)，用于实现混合检索 (Hybrid Search) 中的精确关键词匹配。

---

## 4. 🕸️ 知识图谱 (Knowledge Graph / GraphRAG)
引入了图模型来强化实体之间的逻辑推理能力。
* **图结构构建与运算**：**NetworkX** (`networkx>=3.0`)
* **图社区发现聚类**：**Louvain 算法** (`python-louvain`)，用于在 GraphRAG 模式下进行层次化的信息摘要和聚类。

---

## 5. ⚙️ 后端服务与核心框架 (Backend & Orchestration)
* **API 与服务路由**：**FastAPI** + **Uvicorn**（用于主控节点和高性能 API 分发），结合自带的 `http.server` 充当极简前端托管容器。
* **数据序列化**：**Orjson**（极速 JSON 解析）、**Pydantic**（数据验证和 Schema 定义）。
* **并行与异步控制**：Python 原生 `asyncio` 和 `threading` 多线程模型。
* **大模型交互 (LLM Integration)**：利用 `requests` / `transformers` 对接本地 Ollama 或云端 API 模型进行 QA 生成。

---

## 6. 🛠️ 项目管理与工程化 (DevOps & Tooling)
* **包管理器与构建系统**：**uv** (取代 pip，极速包管理) + **Hatchling** (符合 PEP 621 标准的现代构建后端)。
* **代码规范与 Linting**：**Ruff** (极速代码检查和格式化)。
* **静态类型检查**：**Mypy**。
* **自动化测试**：**Pytest** + **pytest-cov** (测试覆盖率分析)。
* **持续集成与文档**：**GitLab CI** + **MkDocs** (使用 Material 主题用于开发文档的生成)。
