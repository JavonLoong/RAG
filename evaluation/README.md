# evaluation

评测层。用于检索指标、答案指标、图谱指标、人工评估、消融实验和显著性检验。

## 当前评测集

- `system_eval_questions.jsonl`：60 题系统评测集，覆盖普通 RAG、OCR 风险、GraphRAG/知识图谱、结构化数据和评测方法。
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

## GraphRAG triage 回归集

`/api/graphrag/triage/{triage_id}/promote` 会把人工判定的问题追加到运行时
`evaluation/graphrag_triage_regression.jsonl`。本地或 CI 可以用下面的命令做 promoted case gate：

```powershell
python scripts/run_graphrag_triage_regression.py --dataset outputs\smoke_chroma\evaluation\graphrag_triage_regression.jsonl --report-dir evaluation\reports --persist-dir outputs\smoke_chroma --collection rag_smoke --backend hashing --allow-empty
```

没有 promoted case 时该命令返回 `triage_regression=pass case_count=0`；有 case 时会通过 `LocalChromaRegressionRag` 查询指定 `--persist-dir` 里的本地 Chroma collection，再用 `RAGEvaluationHarness` 计算 keyword recall、answer completeness、citation 缺失率、no-result rate 和 hallucination risk。

库内直接调用：

```python
from evaluation import EvaluationThresholds, LocalChromaRegressionRag, RAGEvaluationCase, RAGEvaluationHarness

cases = [
    RAGEvaluationCase(
        id="smoke-001",
        question="检索结果是否覆盖关键证据？",
        reference_answer="答案应说明检索上下文必须覆盖关键证据。",
        expected_evidence_keywords=["检索上下文", "关键证据"],
        task_type="evaluation_method",
        source_scope="evaluation_framework",
        grading_notes="用于本地 smoke gate。",
    )
]

harness = RAGEvaluationHarness(
    rag_system=LocalChromaRegressionRag(
        persist_dir="outputs/smoke_chroma",
        collection_name="rag_smoke",
        backend="hashing",
    ),
    thresholds=EvaluationThresholds(min_keyword_recall_at_k=0.7),
)
report = harness.run(cases, run_name="smoke")
report.save("evaluation/reports")
```
