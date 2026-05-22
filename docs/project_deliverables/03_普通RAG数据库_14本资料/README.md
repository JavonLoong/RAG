# 普通 RAG 数据库：14 本资料

这个目录对应老师说的 ChromaDB 产出。

## 它是什么

把以下内容合到一起，做成一个可检索数据库：

- 13 本扫描 PDF 的 OCR 文本。
- 1 本可直接抽文本 PDF。
- 已有问答 JSON。

## 当前结果

- 数据库：`gas_turbine_ocr_enriched_rag`
- 总 chunk：9080
- OCR chunk：8468
- 直接抽文本 PDF chunk：132
- 问答 JSON chunk：480

## 实际数据库位置

`storage_layer/runtime/ocr_enriched_rag_chroma/`

注意：数据库本体保留英文路径，是为了避免 Windows 中文路径导致 ChromaDB 索引损坏。这里是给人看的说明入口。

本目录里的 `ChromaDB数据库本体_真实文件夹_约195MB` 可以直接点进去看真实数据库文件。

## 这里的文件

- `数据库构建摘要_程序原始版.json`：程序输出的原始统计。
