# 四本书 KG construction 跑通记录

## 结论

这一步已经跑通一个本地知识图谱 construction POC：用 4 本 OCR 质量较稳定的燃气轮机资料，从 `pages.jsonl` 构建 chunk，按小 schema 抽取候选三元组，并给每条三元组绑定 evidence、页码和来源文件。

这不是完整 GraphRAG 问答系统，也不是 Neo4j / Microsoft GraphRAG 的完整索引；它证明的是“知识图谱构建前半段可以从现有 OCR 资料产出结构化候选关系”。

## 输入

- 01_燃气涡轮发动机燃烧_第3版：燃气涡轮发动机燃烧 第3版 (（英）A.H.勒菲沃（Arthur etc.) (z-library.sk, 1lib.sk, z-lib.sk).pdf，页数 442，OCR 字符 1078898
- 02_先进燃气轮机燃烧室：先进燃气轮机燃烧室=ADVANCED GAS TURBINE COMBUSTOR (金如山，索建秦著) (z-library.sk, 1lib.sk, z-lib.sk).pdf，页数 603，OCR 字符 1672703
- 03_燃气轮机原理结构与应用_上：燃气轮机原理、结构与应用 上 (沈阳黎明航空发动机（集团）有限责任公司编著) (z-library.sk, 1lib.sk, z-lib.sk).pdf，页数 485，OCR 字符 1393699
- 04_燃气轮机_南京燃气轮机研究所编：燃气轮机 (南京燃气轮机研究所编) (z-library.sk, 1lib.sk, z-lib.sk).pdf，页数 62，OCR 字符 223142

## 输出

- pages read：1592
- chunks built：4955
- triples emitted：240

关系分布：

- `HAS_PARAMETER`：85
- `HAS_PROBLEM`：51
- `HAS_COMPONENT`：24
- `HAS_SUBTYPE`：20
- `USES_FUEL`：19
- `IMPROVED_BY`：18
- `HAS_FUNCTION`：12
- `RELATED_TO`：11

## 可交付文件

- `schema.json`：实体类型和关系类型。
- `triples.json` / `triples.csv`：候选三元组和 evidence。
- `graph.json`：节点与边结构。
- `knowledge_graph.svg`：图谱图片。
- `kg_evidence_viewer.html`：三元组和 evidence 查看页面。

## 汇报口径

可以说：我用 4 本 OCR 质量比较稳定的燃气轮机资料跑通了本地 KG construction 工具链，已经能产出 schema、三元组、evidence、graph.json 和可视化图谱。现在这一步主要验证 construction 流程；三元组质量还需要人工审核，后续再接 Neo4j 或 GraphRAG 检索。
