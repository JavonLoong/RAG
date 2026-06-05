# GraphRAG 补证整改计划

本计划把 GraphRAG 同题子集中的 partial/missing 结果转成下一轮可执行补证任务。它是整改入口，不是修复完成证明。

- Status: `ready_for_graph_iteration`
- Boundary: This plan turns partial/missing GraphRAG evidence into prioritized remediation work; it does not claim the gaps are already fixed.
- Total cases: 10
- Supported / partial / missing: 3 / 3 / 4
- Gaps marked fixed: `False`

## 不夸大规则

- 不把 partial/missing 改写成成功案例
- 不宣称 GraphRAG 已经全面优于 baseline
- 补证完成前保留原始 supported/partial/missing 统计

## 整改任务

| ID | Priority | Status | Action type | Missing keywords | Acceptance evidence |
| --- | --- | --- | --- | --- | --- |
| cc032 | P0 | missing | add_project_claim_graph_evidence | OCR、ChromaDB、知识图谱、人工评审、失败归因 | new_triples_or_summary_diff, source_page_or_doc_anchor, manual_review_note, rerun_report_json |
| cc033 | P1 | partial | add_global_community_summary | GraphRAG、跨文档、实体 | new_triples_or_summary_diff, source_page_or_doc_anchor, manual_review_note, rerun_report_json |
| cc034 | P1 | partial | expand_relation_synonyms | 三元组、evidence、实体、来源、臆测 | new_triples_or_summary_diff, source_page_or_doc_anchor, manual_review_note, rerun_report_json |
| cc035 | P0 | missing | add_domain_relation_seed | 27、26、1、0、人工评审、不能证明 | new_triples_or_summary_diff, source_page_or_doc_anchor, manual_review_note, rerun_report_json |
| cc043 | P0 | missing | add_global_community_summary | keyword、GraphRAG、术语、数字事实、跨实体、分类型 | new_triples_or_summary_diff, source_page_or_doc_anchor, manual_review_note, rerun_report_json |
| cc048 | P0 | missing | add_global_community_summary | global、跨文档、社区、全局归纳、故障模式、精确数字 | new_triples_or_summary_diff, source_page_or_doc_anchor, manual_review_note, rerun_report_json |
| cc056 | P1 | partial | expand_relation_synonyms | 关系类型、症状、处理措施、过滤 | new_triples_or_summary_diff, source_page_or_doc_anchor, manual_review_note, rerun_report_json |

## 执行动作

### cc032 本项目为什么不能只说自己是一个普通问答页面？

- 为 OCR、ChromaDB、知识图谱、人工评审、失败归因 建立项目主张到证据文件的图谱边。
- 把新增边绑定到 challenge_cup 文档、评测报告或命令记录，避免无来源项目自夸。
- 重新运行同题 GraphRAG 报告，确认项目定位类问题不再仅依赖文本 baseline。
- claim_fixed: `False`

### cc033 GraphRAG 在动力装备资料中适合解决哪一类普通 RAG 不稳定的问题？

- 围绕 GraphRAG、跨文档、实体 增加跨文档社区摘要或全局关系说明。
- 把摘要节点绑定到至少一个来源页、三元组或人工复核说明。
- 重新比较 global GraphRAG 与 keyword/hybrid，但保留不全面优于 baseline 的边界。
- claim_fixed: `False`

### cc034 为什么三元组必须绑定 evidence 才能用于可信问答？

- 为 三元组、evidence、实体、来源、臆测 增补同义词、实体别名和关系谓词映射。
- 检查现有 matched_graph_evidence 是否命中正确语义而非仅命中表面词。
- 复跑 answer benchmark，确认 partial 题的关键词覆盖率是否提升。
- claim_fixed: `False`

### cc035 当前知识图谱 POC 的人工评审结果能证明什么，不能证明什么？

- 把 27、26、1、0、人工评审、不能证明 作为下一轮关系抽取或人工补图谱的 seed terms。
- 为每个新增关系保存 subject、predicate、object、source_file、source_page 和 evidence_preview。
- 如果找不到可靠证据，继续保留 missing，不用弱证据硬补。
- claim_fixed: `False`

### cc043 如果 GraphRAG 没有在所有题上超过 keyword baseline，应该如何解释？

- 围绕 keyword、GraphRAG、术语、数字事实、跨实体、分类型 增加跨文档社区摘要或全局关系说明。
- 把摘要节点绑定到至少一个来源页、三元组或人工复核说明。
- 重新比较 global GraphRAG 与 keyword/hybrid，但保留不全面优于 baseline 的边界。
- claim_fixed: `False`

### cc048 GraphRAG global 更适合回答什么类型的问题？

- 围绕 global、跨文档、社区、全局归纳、故障模式、精确数字 增加跨文档社区摘要或全局关系说明。
- 把摘要节点绑定到至少一个来源页、三元组或人工复核说明。
- 重新比较 global GraphRAG 与 keyword/hybrid，但保留不全面优于 baseline 的边界。
- claim_fixed: `False`

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
