# 期末汇报 PPT 主视觉图片分镜说明

> 目标：生成一组可以直接放进 PPT 的 16:9 主视觉图片。  
> 原则：图片不是为了炫酷，而是帮助老师看懂项目为什么这样做、我们具体做了什么、做完后得到什么成果。  
> 使用方式：每一页以图片作为主体，PPT 中叠加标题、2-3 个关键词和少量数字。不要让 AI 在图片里生成大段中文，正文由 PPT 手动排版。

## 总体叙事

这套图不是按“技术名词”排列，而是按项目真实探索顺序排列：

```text
资料问题出现
→ 明确初心：从资料到可信答案
→ 早期可操作网页工作台
→ JSON / PDF / OCR 数据接入
→ OCR 多方案试错
→ 分块策略选择
→ 索引与 GraphRAG 入口
→ 检索方法比较
→ GraphRAG construction
→ RAG / GraphRAG 边界
→ 系统分层
→ 60 题评测
→ 失败归因
→ 最终可信问答闭环
```

重要提醒：

- 视觉图只负责“让人一眼理解”。真正的项目价值要靠旁边的标题、讲稿和证据数字讲清楚。
- 每页都要回答四件事：方法从哪里来、我们怎么做、为什么要优化、最后产出什么。
- 计算机系老师懂技术，不需要把 RAG 讲成科普玩具；但图要让复杂流程一眼可见。
- 图片里尽量少写中文。图中可以保留英文短标签，例如 `JSON`, `OCR`, `Chunk`, `Chroma`, `BM25`, `Graph`, `Evidence`, `Eval`。

---

## 01. 资料山：我们面对的不是一道问答题，而是一堆异构资料

### 这一页要讲明白什么

项目起点不是“问 GPT 一个问题”，而是老师给了一批动力装备资料：PDF、扫描版 PDF、问答 JSON、OCR 文本、教材和图表。真正难点是这些资料能不能被系统整理、检索、追溯。

### 项目证据

- `docs/project_deliverables/01_资料输入_14本PDF和问答JSON/资料输入说明_人话版.md`
- 当前资料类型：PDF 资料 14 本，扫描版 PDF 13 本，需要 OCR；可直接抽文本 PDF 1 本；问答 JSON 1 个。
- 资料领域包括燃气轮机、燃气-蒸汽联合循环、燃烧室、设备结构、故障诊断等动力装备内容。

### 方法来源

RAG 的基本前提是把外部知识转成可检索语料。对真实工程资料，第一步不是 embedding，也不是 LLM，而是资料可读性判断：

- 有文字层的 PDF 可以直接抽文本。
- 扫描版 PDF 本质是图片，必须 OCR。
- JSON 如果已经包含结构化标注、页码、bbox、transcription，会比原始 PDF 更适合作为第一批验证数据。

### 我们怎么做

先区分资料类型，再决定进入路径：

- JSON：优先作为结构化输入，用于早期 pipeline、chunk 和 Graph construction POC。
- 可抽文本 PDF：进入普通 RAG 文本抽取。
- 扫描 PDF：先进入 OCR 处理，再进入清洗、分块、索引。

### 优化与成果

成果不是“有很多资料”，而是我们把资料分成了不同处理通道，避免把扫描 PDF 当作普通文本直接喂给 RAG。这一点解决了很多普通 RAG demo 不面对的问题。

### 主视觉图片怎么画

画面是一个“资料山”：

- 左侧堆着 14 本 PDF、扫描页、问答 JSON、表格、图注、教材页。
- 每类资料上有小标签：`PDF`, `Scanned PDF`, `JSON`, `OCR image`, `Table`, `Figure`。
- 山脚下有一个小问题气泡，例如 `Why is combined cycle more efficient?`
- 右侧远处有一条还没完全建成的蓝色通道，通向 `Trusted QA System`。
- 风格：深灰黑板、白色粉笔轮廓、蓝色高亮通道。

### PPT 叠加文字

标题：`问题不是问答，而是资料太乱`  
副标题：`14 本 PDF、13 本扫描版、1 个问答 JSON：RAG 的第一关是资料能不能进入系统。`

### 生成图片提示词

```text
16:9 presentation hero image, dark gray chalkboard texture, educational explainer style. A mountain of heterogeneous engineering documents: PDF books, scanned image pages, JSON file cards, tables, figures, OCR text strips. Small labels in English only: PDF, Scanned PDF, JSON, OCR, Table, Figure. At the foot of the mountain, a small question bubble: "Why?". A faint blue path leads from the document mountain toward a distant trusted QA system silhouette. White chalk outlines, blue technical glow, clean composition, large empty top area for PPT title, no dense text, no people.
```

---

## 02. 初心：从混乱资料到带证据的可信答案

### 这一页要讲明白什么

我们的初心不是做一个聊天框，而是让动力装备资料中的知识变成可追溯、可验证、可评测的答案。

### 具体例子

不要只写“证据、页码、来源”。要举一个鲜明问题：

> 问题：燃气-蒸汽联合循环为什么通常比单一燃气轮机循环效率更高？

正确答案不应该只说“效率更高”，而应该检索到：

- 联合循环利用燃气轮机排气余热。
- 余热产生蒸汽，驱动蒸汽轮机继续做功。
- 本质是能量梯级利用，提高总热效率。
- 答案旁边要能看到证据片段和来源页码。

这个例子来自 Day3 baseline 报告中的 `se001`，该题要求命中“联合循环、余热利用、蒸汽轮机或能量梯级利用”。

### 方法来源

RAG 和普通问答的差异在于：答案必须受检索上下文约束。我们之前的提交里也有类似方向：要求回答前必须有 retrieval context，避免模型脱离资料自由发挥。

### 我们怎么做

将答案拆成三层：

1. 用户问题。
2. 检索到的证据 chunk。
3. 带引用的答案。

在后续系统里，这些证据会来自 Chroma、BM25、GraphRAG evidence 或评测输出。

### 优化与成果

这页的成果要讲成：

> 我们追求的不是“模型能答”，而是“模型为什么这样答、证据在哪里、答错时能不能定位原因”。

### 主视觉图片怎么画

画面左右对照：

- 左边是混乱资料堆：PDF、扫描图、JSON。
- 中间有一束检索光，抽出 3 张证据卡片。
- 右边是清晰答案面板：上方是问题，下方是答案条，旁边连着三条证据引用线。
- 证据卡片上只放简短英文占位：`waste heat`, `steam turbine`, `source page`，中文由 PPT 叠加。

### PPT 叠加文字

标题：`初心：从资料到可信答案`  
核心例子：`联合循环效率为什么更高？→ 余热利用 + 蒸汽轮机 + 能量梯级利用`

### 生成图片提示词

```text
16:9 explainer illustration, chalkboard and clean technical style. Left: messy engineering documents and scanned pages. Center: a blue retrieval beam pulling out three evidence cards. Right: a clean answer panel with citation lines connected to evidence cards. Evidence cards have short English labels only: "waste heat", "steam turbine", "source page". The answer panel is bright and stable, representing trusted answer. Leave top-left space for Chinese PPT title. No dense paragraphs, no fake Chinese text.
```

---

## 03. 早期工作台：先做出能操作的入口，但还不是完整系统

### 这一页要讲明白什么

早期我们确实从页面和功能入口做起。这一页不应该占很重篇幅，但要说明：早期网页让项目能操作，但暴露出“功能堆叠不等于系统”的问题。

### 项目证据

Git 历史中早期前端不断加入：

- 文件上传、拖放区、collection 选择。
- 创建/追加数据库、导出 ChromaDB。
- RAG / GraphRAG 切换。
- OCR 控件、每个文件单独处理。
- LLM 配置粘贴、图谱可视化、benchmark tab。

代表提交包括：

- `c9a9616`：collection selection dialog and export panel。
- `4134cdc`：统一拖放区域 + 示例文件管理 + PDF 解析增强。
- `7b4cd08`：per-file OCR controls with 3-engine selector。
- `ee261c0` 到 `a2a6913`：RAG / GraphRAG workflow、benchmark tab、mockup。

### 方法来源

这类工作台本质上是“人机操作层”：让使用者能上传、入库、检索、查看结果。它很必要，但它只是入口，不是系统全部。

### 我们怎么做

早期网页解决了几个操作问题：

- 资料可以拖进去。
- 可以选择 collection。
- 可以导出备份。
- 可以切换标准 RAG / GraphRAG 模式。
- 可以触发 OCR 和查看图谱。

### 问题和矫正

问题：

- 页面功能越来越多，但系统边界变模糊。
- OCR、检索、图谱、LLM 配置混在一个大页面里，容易看起来复杂但难以证明可信。
- 早期还遇到 `file://` 协议、OCR server 状态、模型加载等运行问题。

矫正：

- 后来把能力拆到 `data_pipeline`、`retrieval_engine`、`kg_pipeline`、`rag_orchestrator`、`evaluation` 等模块。
- 页面回到“系统入口”的位置。

### 主视觉图片怎么画

画面是一张早期“未收束工作台”：

- 很多浮动面板：Upload、OCR、Collection、Graph、Search、Export、LLM Config。
- 这些面板之间有很多线，略显拥挤。
- 右下角有一个蓝色箭头指向“system layers”，暗示后来需要收束成架构。

### PPT 叠加文字

标题：`第一步：先做出能操作的入口`  
副标题：`网页让流程跑起来，但功能堆叠不能证明系统可信。`

### 生成图片提示词

```text
16:9 presentation illustration, dark chalkboard background with floating UI panels. Panels labeled in English: Upload, OCR, Collection, Search, Graph, Export, LLM Config. The panels are connected with many thin lines, showing an early crowded workbench prototype. On the right, a clean blue arrow points toward abstract stacked system layers. Educational, polished, not messy beyond readability, no Chinese text, no real app screenshot.
```

---

## 04. 数据入口：为什么 JSON 和 PDF 要分开处理

### 这一页要讲明白什么

JSON 和 PDF 不是同一种输入。JSON 是已有结构化标注，适合做第一版可控 pipeline；PDF 是原始资料，里面又分为可抽文本 PDF 和扫描 PDF。真实 RAG 项目不能把所有资料“一锅端”。

### 项目证据

`组会展示要点.md` 中写明：

- 输入来源：Label Studio 导出的 OCR / bbox / transcription JSON。
- 流程：`JSON -> OCR 文本块 -> chunk -> schema -> 候选三元组 -> evidence -> 人工判断 -> 导出评审结果`。
- 当时结果：OCR 文本块 246 个，chunk 14 个，schema 10 类实体、15 类关系，候选三元组 27 条，人工评审 26 条正确、1 条待讨论。

`资料输入说明_人话版.md` 中写明：

- 14 本 PDF。
- 13 本扫描版 PDF 需要 OCR。
- 1 本可直接抽文本 PDF。
- 1 个问答 JSON 可作为已有结构化文本进入普通 RAG。

### 方法来源

Label Studio JSON 的价值在于它已经包含：

- 页面信息。
- bbox 坐标。
- transcription 文本。
- label 类型，例如 `Para`, `Title`, `Table`, `Figure`, `Formula`。

这使得系统可以按结构处理资料，而不是只拿一坨纯文本。

### JSON 本身的问题

JSON 并不天然完美：

- Label Studio 导出可能是累计快照，多次导入会重复。
- label 可能不规范，例如页码、目录碎片、图注被当正文。
- Table、Figure、Formula 需要人工复核。
- OCR 错字、乱码、两栏串行不能直接入库。

这些规则在 `configs/public_books_text_filter_rules.yaml` 中有体现。

### 我们怎么做

我们把数据入口分成三条：

1. Label Studio JSON：作为结构化文本入口，先跑通 pipeline 和 Graph construction。
2. 可抽文本 PDF：直接解析文本，保留页码与段落。
3. 扫描 PDF：先 OCR，再清洗和分块。

### 优化与成果

成果是系统没有把资料当成同质文本处理，而是为不同资料建立不同入口。这样后续 chunk、metadata、evidence 才可靠。

### 主视觉图片怎么画

画面是一台“数据分流机”：

- 左边三种输入：`Label Studio JSON`, `Text PDF`, `Scanned PDF`。
- JSON 进入结构化通道，显示 bbox、label、page。
- Text PDF 进入 direct text extraction。
- Scanned PDF 进入 OCR 通道。
- 三条通道最后汇成 `Clean text blocks + metadata`。

### PPT 叠加文字

标题：`资料先进入系统，RAG 才有基础`  
关键句：`JSON 有结构，PDF 有文字层差异，扫描 PDF 必须 OCR。`

### 生成图片提示词

```text
16:9 technical explainer image, dark chalkboard style. A data routing machine with three inputs on the left: Label Studio JSON, Text PDF, Scanned PDF. JSON path shows bbox boxes, labels, page numbers; Text PDF path shows extracted text lines; Scanned PDF path goes through an OCR scanner. All paths merge into clean text blocks with metadata tags. Blue and green highlights, white chalk arrows, no Chinese text, leave title space.
```

---

## 05. OCR 试错：真实扫描资料倒逼我们换方案

### 这一页要讲明白什么

OCR 是数据入口的一部分，但因为扫描 PDF 占多数，所以值得单独成一张主图。这里要强调：我们不是为了做 OCR 而做 OCR，而是因为 13 本扫描 PDF 不先 OCR 就无法进入 RAG。

### 项目证据

Git 历史显示做过多轮 OCR 方案：

- `852331f`：Tesseract.js 浏览器端 OCR。
- `e3e4b60`：RapidOCR + 本地 OCR server。
- `a9c63c8`、`e87cf58`：PaddleOCR.js 浏览器端方案。
- `91dc928`：移除 Tesseract.js，记录其中文效果很差。
- `d19385c`：加入百度云 OCR 作为高准确率方案。
- `76de3d2`、`d19a4d2`：OCR 并发、重试、worker 数量优化。

### 方法来源

OCR 方法可以分成三类：

1. 浏览器端 OCR：部署简单，但模型加载、性能和中文准确率受限。
2. 本地 OCR server：可控，适合批量扫描件，但要解决启动、环境和并发。
3. 云 OCR：准确率高，但依赖网络、API 和成本。

### 我们怎么做

我们没有只押一个方案，而是通过真实资料试错：

- 先试浏览器端。
- 发现中文扫描件质量和兼容性问题后，引入本地 OCR。
- 对更复杂资料保留云 OCR 兜底。
- 加入 OCR server 状态提示、一键启动、自动重试、实时预览、文本导出。

### 优化与成果

成果不是“选了最强 OCR”，而是形成了一个多级 OCR 认知：

- 扫描件必须先识别。
- OCR 结果要能预览和导出。
- 低质量页要审计和复核。
- OCR 只是进入 RAG 的前置数据治理，不是项目终点。

### 主视觉图片怎么画

画面是四条 OCR 赛道：

- `Tesseract` 路线输出乱码和红色警告。
- `PaddleOCR` 路线输出部分文字，但有模型加载/浏览器限制符号。
- `RapidOCR local` 路线连接到本地服务器。
- `Cloud OCR` 路线输出最清晰文字，但旁边有 API/cloud 标记。
- 最后四条路都汇到 `Verified OCR Text`，其中主通道是本地/云端组合。

### PPT 叠加文字

标题：`OCR 弯路：真实资料没有那么干净`  
副标题：`13 本扫描 PDF 先变成可用文本，RAG 才能继续。`

### 生成图片提示词

```text
16:9 chalkboard explainer image showing four OCR routes from scanned PDF pages to text. Routes labeled in English: Tesseract, PaddleOCR, RapidOCR local, Cloud OCR. Tesseract route has red warning symbols and noisy text strips; PaddleOCR has partial text and browser model icon; RapidOCR has a local server icon; Cloud OCR has the cleanest text output with a cloud API icon. All routes converge into verified OCR text. High contrast, educational, no Chinese text, no logos.
```

---

## 06. 分块策略：不是随便按页切，而是把资料切成证据单元

### 这一页要讲明白什么

RAG 不能把一本书整本塞给模型。分块的目标是让每个 chunk 既足够小，可以被检索；又足够完整，可以作为答案证据。

### 项目证据

早期 legacy 脚本和当前 `chunking.py` 都显示了具体分块策略：

- Label Studio JSON 中先提取 block。
- block 按 `page_num`, `y`, `order` 排序。
- `Title` 标签触发新 chunk。
- 文本超过长度限制会切分。
- 保留 overlap，防止上下文断裂。
- metadata 保留 source_file、record_id、filename、doc_id、page_nums、chunk_index、char_count、estimated_tokens、labels。

当前 `chunking.py` 的合并策略：

- Title 触发。
- 多级断点：段落、换行、句号、叹号、问号、分号、逗号、空格。
- 默认 `chunk_size=500`，`overlap=50`。评测报告中 Day3 使用 `chunk size / overlap = 900 / 120`。

### 分块方法比较

| 方法 | 好处 | 问题 |
| --- | --- | --- |
| 按页切 | 页码清晰，方便引用 | 一页可能太长或混合多个主题 |
| 按固定字数切 | 实现简单，长度稳定 | 容易从句子中间切断 |
| 按段落切 | 语义自然 | 段落长短差异大，检索粒度不稳定 |
| 按标题 + 多级断点 + overlap | 保留结构、长度可控、上下文连续 | 实现复杂，需要 metadata 和清洗支持 |

### 我们怎么做

我们的选择不是单纯按页，也不是单纯按字数，而是：

> 标题触发 + 多级语义断点 + overlap + 页码 metadata。

这样每个 chunk 能带着来源页码进入检索系统。

### 优化与成果

成果是 chunk 不再只是“小纸片”，而是有结构的证据单元：

- 有正文。
- 有来源。
- 有页码。
- 有标签分布。
- 有估计 token。

### 主视觉图片怎么画

画面像你截图里的“分片方式”，但更贴近项目：

- 左边一页动力装备教材，页面上有 Title、Para、Table、Figure 区域。
- 右边展示四种切法的小对比：
  1. by page：一整页大块。
  2. fixed length：机械等长切。
  3. paragraph：按自然段。
  4. our choice：Title + breakpoints + overlap，带 page/source 标签。
- 最后一种用蓝色高亮。

### PPT 叠加文字

标题：`分块：把资料切成证据单元`  
副标题：`Title 触发 + 多级断点 + overlap + 页码 metadata`

### 生成图片提示词

```text
16:9 educational chalkboard illustration about document chunking. Left: one engineering textbook page with visual regions labeled Title, Para, Table, Figure. Right: four chunking strategies shown as paper slices: by page, fixed length, paragraph, and highlighted "Title + breakpoints + overlap". The highlighted chunks carry small tags: page, source, labels. Use simple English labels only. White chalk, blue highlight, clean layout, no dense text.
```

---

## 07. 索引入口：chunk 如何进入 Chroma、关键词索引和 GraphRAG

### 这一页要讲明白什么

从这一页开始进入 GraphRAG 相关主线。chunk 不是终点，它会进入不同索引结构：

- 向量索引：解决语义相似。
- 关键词索引：解决强术语精确命中。
- 图谱结构：解决实体关系和跨文档解释。

### 项目证据

代码中存在：

- `embeddings.py`：默认 BGE-m3，支持 sentence-transformer；没有本地模型时降级 hashing。
- `retrieval.py`：HybridRetriever，语义检索 + BM25 + RRF。
- `storage_layer/graph_store.py`：图存储。
- `kg_pipeline`：GraphRAG construction。
- `evaluation`：检索评测。

### 向量是什么，和普通数学向量有什么区别

这里要给计算机系老师讲清楚：

- 普通数学向量可以理解成明确坐标，例如 `(x, y, z)`。
- embedding 向量也是坐标，但每一维不是“温度”“压力”这种可直接命名的字段。
- 它是模型学出来的语义空间坐标，维度共同表达文本含义。
- BGE-m3 这类 embedding 会把“燃气轮机压气机作用”和相关段落映射到相近位置。
- ChromaDB 存的是这些向量、原文 chunk 和 metadata，通过 cosine 相似度等方式找近邻。

注意：不要说“每一维分别代表某个具体概念”。更准确说法是“每一维是分布式语义特征，单维通常不可解释，整体距离才有意义”。

### 为什么还要关键词索引

动力装备资料有很多强术语、型号、部件名、报告词。例如：

- `QC185`
- `燃烧室`
- `压气机`
- `M701F`
- `联合循环`

这些词有时 BM25 / keyword 比向量更稳。因此我们不能只做 dense retrieval。

### 我们怎么做

把 chunk 同时送入：

- ChromaDB：保存 embedding、document、metadata。
- BM25：jieba 分词后构建关键词索引。
- Graph construction：抽实体、关系、evidence，为 GraphRAG 做准备。

### 优化与成果

这页要强调：

> 我们开始从“存资料”变成“能按不同问题类型找资料”。这也是普通 RAG 和面向动力装备资料的特异化 RAG 的区别。

### 主视觉图片怎么画

画面从左到右：

- 左边是带 metadata 的 chunk 卡片。
- 中间分三路：
  1. 蓝色向量空间云：点和坐标轴，标 `Embedding / Chroma`。
  2. 黄色关键词书架：标 `BM25 / Keyword`。
  3. 绿色图谱种子：实体节点和证据边，标 `Graph seeds`。
- 三路最后汇入一个 `Retrieval Router`。

### PPT 叠加文字

标题：`索引：让证据能被找回来`  
副标题：`向量负责语义，关键词负责术语，图谱负责关系。`

### 生成图片提示词

```text
16:9 chalkboard technical illustration. Left: chunk cards with metadata tags page/source/title. The chunks split into three paths: a blue vector space cloud labeled Embedding / Chroma, a yellow keyword index shelf labeled BM25 / Keyword, and a green graph seed network labeled Graph seeds / Evidence. The three paths converge into a retrieval router. Educational, clean, high contrast, minimal English labels only, no Chinese text.
```

---

## 08. 检索竞争：keyword / dense / hybrid 不是凭感觉选

### 这一页要讲明白什么

行业里常见检索方法包括关键词检索、向量检索和混合检索。我们没有直接假设“复杂方法一定更好”，而是用同一套 60 题评测集比较。

### 项目证据

Day3 baseline：

| 方法 | Question recall@K | Avg keyword coverage | Strong | Weak | Missed |
| --- | ---: | ---: | ---: | ---: | ---: |
| keyword | 0.833 | 0.563 | 25 | 25 | 10 |
| dense_hashing | 0.583 | 0.300 | 12 | 23 | 25 |
| hybrid_rrf | 0.817 | 0.520 | 24 | 25 | 11 |

### 方法来源

- keyword：稀疏检索，适合显式术语。
- dense：语义向量检索，适合同义表达和语义相似。
- hybrid：常见工业做法，把多路召回融合，例如 RRF。

代码中的 `HybridRetriever` 使用：

- Chroma 语义检索。
- BM25 关键词检索。
- RRF 融合排序。

### 我们怎么做

用 60 题评测集跑三种 baseline，比较 recall 和 coverage。

关键结论：

- keyword 在当前资料中表现最好。
- hybrid 接近 keyword，但没有稳定超过。
- dense_hashing 只是离线可复现的语义式 baseline，不代表最终 embedding 上限。

### 优化与成果

成果不是“我们有三种检索”，而是得到一个判断：

> 动力装备资料强术语明显，不能盲目相信 dense；后续需要 query routing、reranker 和更正式的 embedding。

### 主视觉图片怎么画

画三条检索赛道：

- `Keyword` 黄色选手略领先。
- `Hybrid RRF` 蓝色选手接近。
- `Dense hashing` 灰色选手落后。
- 终点不是“第一名”，而是 `Recall / Coverage` 仪表。

### PPT 叠加文字

标题：`评测告诉我们：不是越复杂越好`  
关键数字：`keyword recall@K 0.833 | hybrid_rrf 0.817 | dense_hashing 0.583`

### 生成图片提示词

```text
16:9 presentation illustration, chalkboard race track metaphor. Three retrieval lanes labeled Keyword, Hybrid RRF, Dense hashing. Keyword runner slightly ahead, Hybrid close behind, Dense behind. Finish line is an evaluation dashboard labeled Recall / Coverage. Add small bar chart shapes but no dense numbers. Blue, yellow, gray accents, clean educational style, no Chinese text.
```

---

## 09. GraphRAG construction：图不是装饰，而是 evidence 关系网

### 这一页要讲明白什么

GraphRAG 的核心不是“画一个漂亮图”，而是把文本中的实体、关系和证据绑定起来，让跨文档解释有结构。

### 项目证据

组会展示清单中已经有最小 Graph construction POC：

- 输入：Label Studio OCR / bbox / transcription JSON。
- OCR 文本块：246 个。
- chunk：14 个。
- schema：10 类实体，15 类关系。
- 候选三元组：27 条。
- schema 校验通过：27 条。
- 人工评审：26 条正确，1 条待讨论，0 条错误。

### 方法来源

GraphRAG construction 通常包括：

1. 文本块输入。
2. 实体抽取。
3. 关系抽取。
4. schema 校验。
5. evidence 绑定。
6. 图存储和图检索。

### 我们怎么做

我们先用 Label Studio JSON 跑通最小闭环：

```text
JSON → OCR 文本块 → chunk → schema → 候选三元组 → evidence → 人工评审 → 导出结果
```

这比直接宣称“GraphRAG 完成”更稳，因为它先证明 construction 链路能走通。

### 优化与成果

成果是：

- 图谱不是凭空生成，而是受 schema 约束。
- 每条关系都要绑定 evidence。
- 结果可以人工判断和导出。

边界：

- 这证明了构建链路。
- 还不能夸大成完整在线 GraphRAG 问答全面超过普通 RAG。

### 主视觉图片怎么画

画一个图谱流水线：

- 左边是 chunk 卡片。
- 中间抽出实体节点：Equipment、Component、Fault、Method、Metric。
- 节点之间形成关系边。
- 每条边挂着 evidence 小卡片和 page 标签。
- 右边是人工评审面板：Correct / Discuss / Wrong。

### PPT 叠加文字

标题：`GraphRAG：把证据组织成关系网`  
关键数字：`246 blocks → 14 chunks → 27 triples → 26 correct`

### 生成图片提示词

```text
16:9 chalkboard technical illustration of GraphRAG construction. Left: chunk cards. Center: entity nodes and relation edges forming a knowledge graph, with small evidence cards attached to edges and page tags. Right: a manual review panel with three simple buttons labeled Correct, Discuss, Wrong. Use English labels only: Chunk, Entity, Relation, Evidence, Schema, Review. Blue and green highlights, clean, no dense text.
```

---

## 10. RAG 和 GraphRAG 的边界：不同问题需要不同结构

### 这一页要讲明白什么

这页要防止老师追问：“GraphRAG 到底是不是比 RAG 强？”我们应该主动讲边界。

### 方法来源

普通 RAG 适合：

- 单文档事实。
- 明确术语。
- 直接证据。

GraphRAG 更适合：

- 跨文档综合。
- 实体关系解释。
- 全局摘要。
- 因果链、故障链、部件关系。

### 我们怎么做

从 60 题中筛出 GraphRAG 同题子集：

- GraphRAG 子集题数：10。
- context 题：8。
- global 题：4。
- 当前文本 baseline 最优覆盖率均值：0.633333。
- 优先补 GraphRAG 实测案例：6。

### 优化与成果

成果是我们没有把 GraphRAG 当成口号，而是把它变成可评测的问题子集。

### 主视觉图片怎么画

左右对比：

- 左边：普通 RAG，问题箭头直接指向几个 chunk，再到答案。
- 右边：GraphRAG，问题先进入实体关系网，再通过 evidence 和 community summary 输出答案。
- 中间有一个问题分类器：Fact / Entity relation / Global summary。

### PPT 叠加文字

标题：`不是所有问题都需要 GraphRAG`  
副标题：`事实题走 RAG，关系题和全局题进入 GraphRAG 子集。`

### 生成图片提示词

```text
16:9 educational split-screen illustration. Left side: Standard RAG path, question to retrieved chunks to answer. Right side: GraphRAG path, question to entity-relation graph, evidence cards, community summary, answer. In the middle, a router with simple labels: Fact, Relation, Global. Dark chalkboard style, white arrows, blue for RAG, green for GraphRAG, no Chinese text.
```

---

## 11. 系统分层：从一个页面拆成工程架构

### 这一页要讲明白什么

我们不是把所有能力堆在一个网页里，而是逐渐拆成工程模块。页面是入口，系统能力在后面。

### 项目证据

当前 README 目录结构：

- `data_pipeline`
- `kg_pipeline`
- `retrieval_engine`
- `rag_orchestrator`
- `model_adapters`
- `storage_layer`
- `evaluation`
- `api_server`
- `frontend_app`

### 方法来源

系统分层的意义：

- 数据层负责资料进入。
- 检索层负责证据召回。
- 图谱层负责实体关系。
- 编排层负责答案生成和引用。
- 评测层负责比较效果。
- 前端只是操作入口。

### 我们怎么做

把早期页面里的功能拆到模块：

```text
frontend_app → 操作入口
api_server → 服务接口
data_pipeline → 解析、清洗、分块
retrieval_engine → keyword / dense / hybrid
kg_pipeline → schema / triples / graph
rag_orchestrator → 问答编排
evaluation → 评测闭环
storage_layer → Chroma / graph / runtime
```

### 优化与成果

成果是项目从“可操作页面”升级成“可维护系统”。这也是和普通课程 demo 的重要区别。

### 主视觉图片怎么画

画成分层剖面图：

- 最上层：Frontend console。
- API 层。
- 数据管线层。
- 检索层。
- 图谱层。
- 评测层。
- 存储层。

每层用不同颜色，但整体克制。

### PPT 叠加文字

标题：`从页面堆功能，到系统分层`  
副标题：`页面是入口，可信问答能力在后端链路。`

### 生成图片提示词

```text
16:9 polished system architecture illustration, chalkboard style. Show a cluttered UI panel on the left being transformed into clean stacked layers on the right. Layers labeled in English: Frontend, API, Data Pipeline, Retrieval, Graph, Orchestrator, Evaluation, Storage. White chalk lines, blue and green accents, professional, minimal text.
```

---

## 12. 60 题评测：让项目从“能跑”变成“可比较”

### 这一页要讲明白什么

评测不是最后打分，而是系统迭代的方向盘。

### 项目证据

`evaluation/system_eval_questions.jsonl`：60 题。  
Day3 baseline 报告有三种方法对比。  
报告中保存了：

- question recall@K。
- keyword recall@K。
- avg keyword coverage。
- strong / weak / missed / zero-hit。

### 方法来源

信息检索系统必须用同一批问题比较不同检索策略，否则只看几个成功 demo 没意义。

### 我们怎么做

把问题分为：

- standard_rag_fact。
- standard_rag_process。
- kg_graph_rag。
- answer_quality。

每个问题有期望命中的关键词或证据。

### 优化与成果

成果：

- 能比较 keyword / dense / hybrid。
- 能挑出成功、部分命中、失败案例。
- 能为 GraphRAG 子集提供依据。

### 主视觉图片怎么画

画一个评测仪表台：

- 左边 60 张问题卡进入机器。
- 中间三种方法跑过同一批问题。
- 右边输出 recall、coverage、strong/weak/missed 的仪表。

### PPT 叠加文字

标题：`60 题评测集：让结果可比较`  
副标题：`同题比较 keyword / dense / hybrid，而不是只展示成功案例。`

### 生成图片提示词

```text
16:9 evaluation dashboard illustration, dark chalkboard background. A deck of 60 question cards flows into an evaluation machine. Three method paths labeled Keyword, Dense, Hybrid pass through the same machine. Output dashboard shows simple gauges labeled Recall, Coverage, Strong, Weak, Missed. Clean educational style, blue/yellow/green accents, no Chinese text.
```

---

## 13. 失败归因：失败不是结束，而是下一轮优化路线图

### 这一页要讲明白什么

一个成熟项目不应该只展示成功案例。失败案例能说明系统下一步怎么改。

### 项目证据

Day3 报告中列出失败：

- `se013`：Reranker 在 RAG 流程中的作用是什么？覆盖率 0。
- `se015`：检索结果没有覆盖关键证据会有什么风险？覆盖率 0。
- `se024`：知识图谱 POC 人工评审结果是多少？覆盖率 0。

Day4 failure analysis 中出现了失败类型：

- hybrid_dilution。
- partial_ranking_gap。
- evaluation_concept_gap。

### 方法来源

检索系统优化不能只看总分，需要把失败分成可行动类别：

- 是召回没进来？
- 是进来了但排序靠后？
- 是关键词和 dense 融合后被稀释？
- 是评测概念本身没有覆盖？

### 我们怎么做

把失败案例转成下一步任务：

- hybrid_dilution → query routing / 权重调整。
- partial_ranking_gap → reranker。
- evaluation_concept_gap → 扩展评测集和标准答案。
- GraphRAG 子集低覆盖 → local/global GraphRAG 实测。

### 优化与成果

成果是失败变成路线图，而不是扣分项。

### 主视觉图片怎么画

画一个失败案例分诊台：

- 左边失败问题卡。
- 中间贴标签：Dilution、Ranking gap、Concept gap。
- 右边变成优化任务卡：Reranker、Source scope、Query router、GraphRAG subset。

### PPT 叠加文字

标题：`失败归因：把问题变成路线图`  
副标题：`失败案例告诉我们下一步该改哪里。`

### 生成图片提示词

```text
16:9 chalkboard illustration of failure analysis as triage. Left: failed question cards with red warning icons. Middle: tags labeled Dilution, Ranking gap, Concept gap. Right: optimization task cards labeled Reranker, Source scope, Query router, GraphRAG subset. Arrows show failed cases becoming action items. Professional educational style, no Chinese text.
```

---

## 14. 最终收束：面向动力装备资料的可信 RAG / GraphRAG 闭环

### 这一页要讲明白什么

最终成果不是“一个网页”，也不是“一个模型”，而是一条闭环：

```text
资料进入 → 清洗分块 → 索引检索 → 图谱解释 → 答案引用 → 评测反馈 → 下一轮优化
```

### 项目证据

当前项目已有：

- 数据入口和 OCR 材料。
- Chroma / BM25 / hybrid 检索。
- Graph construction POC。
- evaluation 评测报告。
- GitHub Pages HTML PPT 和评测驾驶舱。
- GitLab 工程运行线和启动脚本。

### 方法来源

真实 RAG 系统不是一次性生成，而是持续闭环：

- 数据质量影响检索。
- 检索质量影响答案。
- 答案质量需要评测。
- 评测结果反过来改 chunk、embedding、keyword、reranker、GraphRAG。

### 我们怎么做

把前面 13 页收束成一个系统：

- 对动力装备资料做专门入口。
- 对强术语做 keyword / BM25。
- 对语义相似做 embedding / Chroma。
- 对实体关系做 GraphRAG construction。
- 对效果做 60 题评测和失败归因。
- 对展示做 HTML PPT 和评测页面。

### 优化与成果

最终要讲：

> 我们不是把开源 RAG 拼起来，而是围绕动力装备资料的特点，把资料接入、OCR、分块、检索、GraphRAG、评测和展示组合成一个领域化可信问答系统。

### 主视觉图片怎么画

画一个闭环系统：

- 左侧：动力装备资料。
- 下方：数据处理和 chunk。
- 中间：Chroma / BM25 / Graph。
- 右侧：答案面板 + citation。
- 上方：evaluation feedback loop 回到数据和检索。
- 整个闭环中间写 `Trusted Power Equipment QA` 英文占位。

### PPT 叠加文字

标题：`最终成果：可信问答闭环`  
副标题：`资料、证据、图谱、评测和优化形成一个可复现系统。`

### 生成图片提示词

```text
16:9 final hero illustration, dark chalkboard texture with polished technical glow. A closed-loop system for Power Equipment RAG / GraphRAG. Left: engineering documents. Bottom: data cleaning and chunking. Center: Chroma vector index, BM25 keyword index, knowledge graph. Right: trusted answer panel with citation links. Top: evaluation feedback loop returning to retrieval and data processing. Main English label: Trusted Power Equipment QA. Blue, green, yellow accents, cinematic, clean, no Chinese text, large empty area for PPT title.
```

---

## 生成图片时的统一风格约束

为了让 14 张图像是一套，而不是 14 张散图，所有图片统一使用：

- 画幅：16:9，建议 1920x1080 或更高。
- 背景：深灰黑板质感，微弱粉笔纹理。
- 主色：白色线稿 + 蓝色主线 + 绿色 GraphRAG + 黄色评测/关键词 + 红色风险。
- 文字：图片中只放英文短标签，不放大段中文。
- PPT 叠加中文：标题、关键数字、讲稿提示都在 PPT 里做。
- 风格：科普视频截图感，但更干净、更工程化。
- 避免：卡通人物、过多图标、复杂小字、真实品牌 logo、伪中文。

## 放进 PPT 时的排版建议

每页固定三层：

1. 主视觉图片铺满 16:9。
2. 左上角或上方叠加标题。
3. 底部放一句“讲述判断”，不要超过 24 个字。

示例：

```text
标题：问题不是问答，而是资料太乱
底部判断：先把资料变成可检索证据，RAG 才有意义。
```

不要把所有方法细节都写在图片上。方法细节放讲稿或备注。

