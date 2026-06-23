# RAG 的前世今生、未来探索与新兴替代范式

这份文档整理我们刚才围绕 RAG、GraphRAG、Claude Code / Anthropic、agentic search、context engineering 以及清华燃气轮机知识库目标的讨论。核心结论是：传统 RAG 仍然重要，但它已经不是最顶尖知识系统的完整答案。面向高水平科研/工程知识库，应该从“做一个 RAG”升级为“做一个可审计、可评测、可溯源、可运维的领域知识智能体”。

## 1. 先明确：RAG 是什么

RAG，全称 Retrieval-Augmented Generation，通常翻译成“检索增强生成”。

传统 RAG 的基本流程是：

```text
原始文档
-> 文档解析
-> 文本切片 chunk
-> 向量化 embedding
-> 存入向量数据库
-> 用户提问
-> 问题向量化
-> 找最相似的 top-k 片段
-> 把片段塞给大模型
-> 大模型生成答案
```

它解决的问题是：大模型本身不一定知道你的私有资料，也不一定记得最新知识，所以要先从外部知识库中把相关内容找出来，再让模型基于这些内容回答。

传统 RAG 的优点很直接：

- 工程上容易实现。
- 对私有知识库很有用。
- 能给答案加引用和证据。
- 成本比把所有文档全塞进长上下文低。

但它也有明显问题：

- 文档切片会破坏上下文。
- top-k 召回容易漏掉真正相关片段。
- 向量相似不等于问题真正需要的证据。
- 对复杂多跳问题、因果链、系统关系理解较弱。
- 如果文档解析质量差，后面全都会错。

所以传统 RAG 是基础能力，不是终局。

## 2. RAG 的发展阶段

可以粗略分成几代。

### 第一代：Naive RAG

最基础的版本：

```text
chunk -> embedding -> vector search -> prompt
```

适合简单问答，比如：

```text
某个手册里某个参数是多少？
某个规程怎么写？
某份说明里有没有提到某个部件？
```

缺点是对复杂问题不稳。

### 第二代：Hybrid RAG

开始把向量检索和关键词检索结合起来：

```text
向量检索 + BM25/关键词检索 + RRF 融合 + rerank
```

这样可以缓解纯向量检索漏召的问题。比如“喘振”“NOx”“热障涂层”这类专业术语，关键词检索常常很重要。

### 第三代：GraphRAG

GraphRAG 不只是找文本片段，而是从文档中抽取：

```text
实体
关系
事件
主题
证据
来源
```

然后构建知识图谱。

例如：

```text
压气机 -> 可能发生 -> 喘振
喘振 -> 受影响于 -> 进口畸变
喘振 -> 可能导致 -> 振动升高
振动升高 -> 可能造成 -> 叶片损伤
```

GraphRAG 更适合回答：

- A 和 B 有什么关系？
- 某个故障链路是什么？
- 哪些因素共同导致某个现象？
- 一个系统级问题涉及哪些部件和工况？

### 第四代：Contextual Retrieval / Contextual RAG

Anthropic 提出的 Contextual Retrieval 不是放弃检索，而是改造传统 chunk 检索。

传统 chunk 的问题是：一个片段脱离原文后容易失去语境。

Contextual Retrieval 的做法是：给每个 chunk 补充上下文说明，再做 embedding / BM25 / rerank。

Anthropic 官方文章说，这种方式可以显著降低检索失败率：Contextual Embeddings + Contextual BM25 可减少 49% 的失败检索，加 rerank 后可减少 67%。

参考：Anthropic, [Contextual Retrieval](https://www.anthropic.com/engineering/contextual-retrieval)

### 第五代：Agentic Retrieval / Context Engineering

这就是我们重点讨论的方向。

它不是简单：

```text
用户问题 -> 检索器给 top-k -> 模型回答
```

而是：

```text
用户目标
-> 模型判断需要查什么
-> 读取文档地图/项目地图
-> 调用 grep / glob / read / fetch 等工具
-> 逐步打开资料
-> 不够再继续查
-> 组织证据
-> 回答并验证
```

Anthropic 在 context engineering 文章里提到，Claude Code 使用混合模式：`CLAUDE.md` 这类文件会先进入上下文，而 `glob/grep` 等工具允许它按需即时检索文件，从而绕开 stale indexing 和复杂语法树的问题。

参考：Anthropic, [Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)

这说明顶尖系统不再只靠传统 RAG，而是把 RAG 变成“上下文工程”的一部分。

## 3. Claude Code / Anthropic 和传统 RAG 的关键差别

Claude Code 这种系统的核心不是“外面接一个向量数据库”。

它更像：

```text
强模型
+ 长上下文
+ 工具调用
+ 文件搜索
+ 项目记忆
+ 动态上下文管理
+ 多步验证
```

普通 RAG 是被动的：

```text
检索器先找片段
模型只能看检索器给它的东西
```

Claude Code / agentic search 是主动的：

```text
模型自己判断要查哪里
自己决定打开哪些文件
自己决定是否继续搜索
自己运行命令或测试验证
```

所以不是“没有检索增强”，而是“不再是传统 RAG 形态的检索增强”。

更准确的名字是：

```text
Context Engineering
Agentic Retrieval
Tool-Augmented Generation
```

## 4. Agentic Search 里的“文档地图”到底是什么

视频里提到的做法可以理解为：

```text
不给模型一个预先建好的向量库
而是给模型一份资料地图
让模型自己决定看哪些资料
```

资料地图大概长这样：

```text
文件 A：讲压气机喘振机理、进口畸变、失速边界和保护策略。
文件 B：讲燃烧振荡、贫预混燃烧、NOx 排放控制。
文件 C：讲透平叶片冷却、热障涂层、热疲劳和蠕变。
文件 D：讲燃气轮机启停规程、保护逻辑和常见故障处置。
```

模型拿到问题后，先看这个地图，再决定：

```text
我要打开哪个文件？
我要搜哪些关键词？
我要不要继续查别的文件？
```

这不是传统 RAG，而是“面向 agent 的语义导航层”。

但这个方法有一个非常大的工程问题：每份资料的说明到底写多长？

如果太短：

```text
文件 A：讲燃气轮机。
```

基本没用。

如果太长：

```text
文件 A：几千字摘要。
```

又会占用上下文，变成另一个大型摘要库。

所以更合理的方式不是只做一个文件说明，而是做多层地图：

```text
文件级说明：100-300 中文字
章节级说明：50-150 中文字
社区摘要：200-500 中文字
原文 chunk：按证据需要读取
```

但这些数字不是死规则，必须通过评测调。

一个长但主题单一的文件，文件级说明可以短。

一个短但主题复杂的事故报告，说明反而要更细。

## 5. GraphRAG 社区摘要和文档地图的关系

我们刚才讨论过一个关键点：GraphRAG 的社区摘要本身也可以承担“地图”的作用。

社区摘要通常来自：

```text
实体
关系
事件
主题
证据片段
来源文档
```

它可以告诉模型：

```text
这一片知识在讲什么？
涉及哪些部件？
涉及哪些故障？
相关证据来自哪些文档？
```

所以它不是单纯的知识图谱说明，也可以反向成为 agent 找资料的导航入口。

区别在于：

```text
文档地图：
以文件/章节为中心。
告诉你资料在哪里，讲什么。

GraphRAG 社区摘要：
以实体/关系/主题社区为中心。
告诉你这一团知识讲什么，相关证据来自哪里。
```

最好的设计不是二选一，而是融合：

```text
文档目录 = 文件级资料地图
章节摘要 = 章节级资料地图
社区摘要 = 主题级知识地图
chunk 检索 = 原文证据定位
```

最终流程应该是：

```text
用户问题
-> 看文档地图和社区摘要判断方向
-> 查 GraphRAG 社区和实体关系
-> 回到原文 chunk 找证据
-> rerank / no-answer gate
-> 带引用回答
```

## 6. “开源头部”不等于“行业顶尖”

这个判断很重要。

我们之前对标的很多是开源 RAG 项目，比如 RAGFlow、Dify、Haystack、LlamaIndex、LightRAG、RAGAS 等。

这些项目很有价值，因为：

- 能看源码。
- 能复用工程模式。
- 能落地到本地系统。
- 能验证功能边界。

但开源头部不一定等于行业真正顶尖。

真正的行业顶尖还包括很多闭源系统：

- Claude / Claude Code
- ChatGPT / Deep Research
- Perplexity
- Glean
- NotebookLM
- Cursor
- 企业级知识管理和搜索系统

这些系统很多已经不再只是“RAG 产品”，而是：

```text
context engineering system
agentic knowledge system
enterprise search assistant
tool-using knowledge agent
```

所以我们不能只问：

```text
我们有没有 RAG？
```

而要问：

```text
我们的知识系统能不能像顶尖 agent 一样主动找资料、组织证据、引用原文、解释关系、拒答不确定问题？
```

## 7. 对清华燃气轮机知识库的目标定位

如果这个系统是给清华大学能源与动力工程相关团队、燃气轮机所做的，那么目标不能只是“能问答”。

更合理的定位是：

```text
燃气轮机领域知识智能体
```

它应该具备：

- 高质量文档解析：PDF、扫描件、图表、表格、标准、手册、论文。
- 专业术语识别：压气机、燃烧室、透平、控制系统、热障涂层、喘振、NOx、贫预混等。
- Hybrid Retrieval：向量 + BM25 + rerank。
- Contextual Retrieval：给 chunk 加上下文再检索。
- GraphRAG：抽实体、关系、故障链路和系统结构。
- 社区摘要：作为主题级知识地图。
- 文档地图：作为文件/章节级资料导航。
- 原文引用：答案必须能回到页码、章节、chunk 或原始证据。
- no-answer gate：证据不足时不硬答。
- 评测集：用真实燃气轮机问题验证召回、引用、正确性、拒答能力。
- 权限治理：不同资料、不同用户、不同操作要可控。
- 审计与运维：关键检索策略、审批、session、密钥等可追踪。

## 8. 什么才算“顶尖”

顶尖不是页面看起来漂亮，也不是简单接了一个大模型。

对这个项目来说，顶尖应该至少满足：

### 8.1 答案有证据

每个关键结论都能追溯到：

```text
文档名
章节
页码
chunk
原文片段
```

### 8.2 能处理复杂关系

例如：

```text
进口畸变为什么会影响喘振裕度？
燃烧振荡和燃烧室结构、燃料控制有什么关系？
透平叶片热疲劳和冷却结构、材料、工况之间有什么因果链？
```

这些不是简单 top-k 能稳定解决的。

### 8.3 能拒答

如果证据不足，系统应该说：

```text
当前资料中没有足够证据支持结论。
```

而不是编一个看起来专业的答案。

### 8.4 能评测

必须有问题集和指标：

- recall@k
- citation coverage
- answer faithfulness
- no-answer precision
- latency
- cost
- graph evidence coverage

### 8.5 能维护

资料更新后，文档地图、社区摘要、图谱、索引都要能更新。

不能靠一次性 demo。

## 9. 我们应该采用的最终架构

推荐路线：

```text
资料接入层
  -> PDF/Word/表格/图片/扫描件解析
  -> OCR 和版面结构识别

文档地图层
  -> 文件级说明
  -> 章节级说明
  -> 资料适用问题类型

检索层
  -> BM25
  -> 向量检索
  -> Contextual Retrieval
  -> rerank

图谱层
  -> 实体抽取
  -> 关系抽取
  -> 社区发现
  -> 社区摘要
  -> source evidence

Agent 层
  -> 先读地图
  -> 决定查什么
  -> 调用检索/图谱/原文工具
  -> 多步补证据
  -> 生成答案

治理层
  -> 权限
  -> 审计
  -> 策略审批
  -> 密钥/会话运维

评测层
  -> 真实问题集
  -> 回归测试
  -> smoke gate
  -> 质量报告
```

## 10. 最重要的结论

第一，传统 RAG 没死，但它已经不是顶尖系统的全部。

第二，GraphRAG 不是只做关系图，它的社区摘要可以成为 agent 的主题级导航层。

第三，agentic search 不是魔法，它的“文档说明”长度、质量、更新同步都是工程难点。

第四，Anthropic / Claude Code 代表的方向不是普通 RAG，而是 context engineering + tool use + agentic retrieval。

第五，对清华燃气轮机知识库来说，目标不应该是“做一个 RAG”，而应该是：

```text
做一个燃气轮机领域知识智能体。
```

它要能：

```text
读资料
找证据
理解关系
引用原文
拒绝瞎答
支持专家评测
支持长期维护
```

这才是更接近行业顶尖的目标。

## 参考资料

- Anthropic: [Contextual Retrieval](https://www.anthropic.com/engineering/contextual-retrieval)
- Anthropic: [Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- Anthropic: [Model Context Protocol](https://www.anthropic.com/news/model-context-protocol)
- Anthropic Docs: [Claude Code overview](https://docs.anthropic.com/en/docs/agents-and-tools/claude-code/overview)
- Anthropic Docs: [Claude Code memory](https://docs.anthropic.com/en/docs/claude-code/memory)
