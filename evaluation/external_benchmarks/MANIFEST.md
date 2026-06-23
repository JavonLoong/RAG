# RAG / GraphRAG 外部评测资产清单

更新时间：2026-06-20

这个目录只放“拿来评测用”的外部资产：题目、语料、标准答案、证据标注、评测脚本。原始开源仓库完整副本放在 `external_repos/`。

## 已下载资产

| 名称 | 本地路径 | 来源 | 已包含内容 | 主要用途 |
| --- | --- | --- | --- | --- |
| CRUD-RAG | `evaluation/external_benchmarks/CRUD_RAG__benchmark` | https://github.com/IAAR-Shanghai/CRUD_RAG | 中文 RAG 题目、答案/参考结果、任务拆分、RAGQuestEval 题集 | 中文知识库问答、摘要、续写、幻觉修改、单文档/多文档问答 |
| GraphRAG-Bench | `evaluation/external_benchmarks/GraphRAG-Bench__GraphRAG-Bench` | https://github.com/GraphRAG-Bench/GraphRAG-Benchmark 和 https://huggingface.co/datasets/GraphRAG-Bench/GraphRAG-Bench | medical/novel 语料、问题集、GraphRAG 生成与检索评测脚本 | GraphRAG 与普通 RAG 在事实检索、复杂推理、上下文总结、生成上的对比 |
| Microsoft GraphRAG benchmarking datasets | `evaluation/external_benchmarks/microsoft__graphrag-benchmarking-datasets` | https://github.com/microsoft/graphrag-benchmarking-datasets | HotPotQA、Kevin Scott podcast、MSFT 财报电话会问题 CSV 和已解压文本语料 | GraphRAG 端到端构图、跨文档检索、多文档总结 |
| RAGBench | `evaluation/external_benchmarks/galileo-ai__ragbench` | https://huggingface.co/datasets/galileo-ai/ragbench | emanual、techqa、expertqa、hotpotqa 的 validation/test Parquet | 通用 RAG 回答质量、上下文相关性、证据支持度评测 |
| Legal RAG Bench | `evaluation/external_benchmarks/isaacus__legal-rag-bench` | https://huggingface.co/datasets/isaacus/legal-rag-bench | `corpus.jsonl`、`qa.jsonl` | 法律/长文本场景的检索问答评测，可作为高严肃领域样例 |
| Rageval | `external_repos/rageval` | https://github.com/gomate-community/rageval | 评测框架、指标实现、ASQA/HOTPotQA/ALCE/WebGLM 等 benchmark 脚本和样例结果 | 补齐 Answer Correctness、Groundedness、Citation、Context Recall、Hit Rate、MRR、NDCG 等指标 |
| Awesome RAG Evaluation | `external_repos/awesome-rag-evaluation` | https://github.com/yhpeter/awesome-rag-evaluation | RAG 评测论文、框架、数据集索引 | 后续继续补基准时的索引 |
| Awesome GraphRAG | `external_repos/Awesome-GraphRAG` | https://github.com/DEEP-PolyU/Awesome-GraphRAG | GraphRAG 论文、项目、benchmark 索引 | 后续继续补 GraphRAG 方向基准时的索引 |

## 当前可直接使用的文件

### CRUD-RAG

- `crud_data/1doc_QA.json`
- `crud_data/2docs_QA.json`
- `crud_data/3docs_QA.json`
- `crud_data/continuing_writing.json`
- `crud_data/event_summary.json`
- `crud_data/hallu_modified.json`
- `crud_data/merged.json`
- `split_merged.json`
- `quest_eval/*.json`

### GraphRAG-Bench

- `Datasets/Corpus/medical.json`
- `Datasets/Corpus/novel.json`
- `Datasets/Questions/medical_questions.json`
- `Datasets/Questions/novel_questions.json`
- `Evaluation/generation_eval.py`
- `Evaluation/retrieval_eval.py`
- `Evaluation/metrics/*.py`

### Microsoft GraphRAG Benchmarking

- `HotPotQA Filtered Questions.csv`
- `Kevin Scott Questions.csv`
- `MSFT Single Transcript Questions.csv`
- `MSFT Multi Transcript Questions.csv`
- `HotPotQA_Filtered_Input_Text/input/*.txt`
- `Kevin_Scott_Podcast_Transcripts_Input_Text/input/*.txt`
- `MSFT_Input_Text/txt/*.txt`

### RAGBench

- `emanual/{validation,test}-*.parquet`
- `techqa/{validation,test}-*.parquet`
- `expertqa/{validation,test}-*.parquet`
- `hotpotqa/{validation,test}-*.parquet`
- `emanual/{validation,test}-*.jsonl`
- `techqa/{validation,test}-*.jsonl`
- `expertqa/{validation,test}-*.jsonl`
- `hotpotqa/{validation,test}-*.jsonl`

注意：原始 Parquet 已保留，并已转出同名 JSONL。当前 `.venv` 已安装 `pyarrow==24.0.0` 用于读取 Parquet；重建环境时需要补这个依赖。

### Legal RAG Bench

- `corpus.jsonl`
- `qa.jsonl`

## 完整性统计

| 资产 | 语料 | 题目/样例 | 答案/证据/标注情况 |
| --- | ---: | ---: | --- |
| CRUD-RAG | 原仓库含 `80000_docs` 新闻检索库；统一目录含任务内文本 | 1doc QA 3199、2docs QA 3199、3docs QA 3199、续写 10728、摘要 10728、幻觉修改 5130 | 有 `answers`、`summary`、`realContinuation`、`quest_eval` 参考题集；适合中文 RAG 端到端评测 |
| CRUD-RAG split | 同上 | event_summary 2000、continuing_writing 1999、hallu_modified 1268、1doc 800、2docs 797、3docs 797 | 论文实验拆分，可作为正式回归集 |
| GraphRAG-Bench | medical 1 个长语料、novel 20 个长语料 | medical 2062、novel 2010 | 每题有 `answer`、`evidence`，部分有 `evidence_relations` / `evidence_triple` |
| Microsoft GraphRAG benchmarking | HotPotQA 5491 txt、Kevin Scott 1669 txt、MSFT 41 txt | HotPotQA 5491、Kevin Scott 125、MSFT single 21、MSFT multi 20 | CSV 主要是开放问题，没有传统标准答案；更适合 GraphRAG 构图、跨文档检索和 LLM-as-judge |
| RAGBench | 每条样例自带 documents | 2102 条 JSONL | 有 response、句子支持信息、adherence/relevance/utilization/completeness 等标注分数 |
| Legal RAG Bench | 4876 条法律语料 | 100 条 QA | 有 `answer` 和 `relevant_passage_id`，适合严肃领域检索准确性评测 |
| Rageval | benchmark 脚本和样例输出 | ASQA/ALCE/HOTPotQA/WebGLM 等脚本 | 重点是指标实现：Answer F1/EM/Rouge、Citation Precision/Recall、Context Recall、Hit Rate、MRR、NDCG 等 |

## 后续接入顺序

1. 先把 JSON/JSONL/CSV 资产转成本地统一格式：`case_id`、`question`、`answer`、`corpus_ids`、`evidence`、`task_type`、`source_benchmark`。
2. 先跑 Legal RAG Bench、GraphRAG-Bench、Microsoft CSV，因为这些最容易映射到当前本地 harness。
3. 再跑 CRUD-RAG，因为中文任务更全，但字段结构要单独适配。
4. 最后把 RAGBench 的标注分数接入本地指标，作为回答支持度和上下文相关性的专项评测。
