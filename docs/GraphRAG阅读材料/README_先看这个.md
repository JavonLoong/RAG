# GraphRAG 阅读材料说明

建议不要从头硬啃，按下面顺序看。

## 1. Microsoft GraphRAG 论文

文件：`01_Microsoft_GraphRAG_From_Local_to_Global.pdf`

先看：摘要、Introduction、方法图、实验结论。

重点问题：GraphRAG 为什么适合跨文档、全局总结类问题。

## 2. GraphRAG Survey

文件：`02_GraphRAG_Survey_Retrieval_Augmented_Generation_with_Graphs.pdf`

先看：整体框架图、GraphRAG 模块划分、挑战与未来方向。

重点问题：论文里通常怎么拆 GraphRAG 系统模块。

## 3. Neo4j GraphRAG 文档

文件：`03_Neo4j_GraphRAG_Python_Documentation.html`

重点问题：如果要落到图数据库，文本、实体、关系、embedding 怎么进入 Neo4j。

## 4. LlamaIndex Property Graph Index 文档

文件：`04_LlamaIndex_Property_Graph_Index_Documentation.html`

重点问题：如果不先做重型图数据库，怎么在 Python RAG 工程里快速接入知识图谱。

## 读完要能回答的 5 个问题

1. 普通 RAG 和 GraphRAG 的差别是什么？
2. 为什么要先 construction，再做问答？
3. schema 和关系粒度为什么重要？
4. Neo4j 和 LlamaIndex 的路线差别是什么？
5. 我们项目下一步应该先做 OCR、embedding，还是 KG 抽取？
