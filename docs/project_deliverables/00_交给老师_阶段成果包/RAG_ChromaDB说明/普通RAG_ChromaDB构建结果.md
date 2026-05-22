# 普通 RAG 数据库构建结果

这一步解决的是：把老师给的资料真正放进一个可以查询的数据库，而不是只停留在“下载了文件”。

## 放进去了什么

- 13 本 OCR 后的扫描 PDF。
- 1 本可直接抽文本 PDF。
- 之前已有的问答 JSON。

## 产出是什么

产出是一个 ChromaDB 向量数据库：

`storage_layer/runtime/ocr_enriched_rag_chroma/`

它包含 9080 个 chunk：

- OCR 文本：8468 个 chunk。
- 直接抽文本 PDF：132 个 chunk。
- 问答 JSON：480 个 chunk。

## 现在证明了什么

已经证明：资料可以被整理、切片、向量化、入库，并且数据库重启后仍能读取和检索。

## 还没证明什么

还没证明最终检索质量已经很好。现在用的是本地 hashing embedding，适合证明流程跑通；后续要换更好的 embedding 模型，再做质量评估。
