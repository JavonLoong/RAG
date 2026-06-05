# GraphRAG 补证整改计划

本计划把 GraphRAG 同题子集中的 partial/missing 结果转成下一轮可执行补证任务。它是整改入口，不是修复完成证明。

- Status: `ready_for_graph_iteration`
- Boundary: This plan turns partial/missing GraphRAG evidence into prioritized remediation work; it does not claim the gaps are already fixed.
- Total cases: 10
- Supported / partial / missing: 9 / 1 / 0
- P0 missing 已补证: `True`
- Gaps marked fixed: `False`

## 不夸大规则

- 不把 partial/missing 改写成成功案例
- 不宣称 GraphRAG 已经全面优于 baseline
- 补证完成前保留原始 supported/partial/missing 统计

## 整改任务

| ID | Priority | Status | Action type | Missing keywords | Acceptance evidence |
| --- | --- | --- | --- | --- | --- |
| cc056 | P1 | partial | expand_relation_synonyms | 关系类型、症状、处理措施、过滤 | new_triples_or_summary_diff, source_page_or_doc_anchor, manual_review_note, rerun_report_json |

## 执行动作

### cc056 为什么知识图谱关系类型不能全部写成 related_to？

- 为 关系类型、症状、处理措施、过滤 增补同义词、实体别名和关系谓词映射。
- 检查现有 matched_graph_evidence 是否命中正确语义而非仅命中表面词。
- 复跑 answer benchmark，确认 partial 题的关键词覆盖率是否提升。
- claim_fixed: `False`

## 复跑命令

- `python scripts/build_graphrag_challenge_report.py`
- `python scripts/build_graphrag_answer_benchmark.py`
- `python scripts/build_graphrag_gap_remediation_plan.py`
- `python scripts/check_challenge_cup_readiness.py`

## Boundary

This plan turns partial/missing GraphRAG evidence into prioritized remediation work; it does not claim the gaps are already fixed.
