# evaluation

评测层。用于检索指标、答案指标、图谱指标、人工评估、消融实验和显著性检验。

## 当前评测集

- `system_eval_questions.jsonl`：60 题系统评测集，覆盖普通 RAG、OCR 风险、GraphRAG/知识图谱、结构化数据、挑战杯项目定位和评测方法。
- `scripts/run_system_evaluation.py`：可读取该 JSONL，并对系统输出计算 retrieval recall、answer evidence coverage、citation 缺失率和 hallucination risk 等指标。

每条记录包含：

- `question`
- `reference_answer`
- `expected_evidence_keywords`
- `task_type`
- `source_scope`
- `expected_modes`
- `grading_notes`

示例运行：

```powershell
python scripts/run_system_evaluation.py --dataset evaluation/system_eval_questions.jsonl --input path\to\rag_outputs.jsonl --run-name baseline
```
