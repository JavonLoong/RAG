# GraphRAG 补证整改计划

本报告记录 GraphRAG 同题子集 partial/missing 本地证据缺口的关闭状态；它证明固定证据覆盖已经补齐，但不证明在线 LLM answer win-rate 或外部专家验证。

- Status: `graph_evidence_gaps_closed_pending_external_validation`
- Boundary: This report closes local partial/missing GraphRAG evidence gaps with auditable supplement records; it does not claim online LLM answer win-rate, external validation, or that GraphRAG beats every baseline question.
- Total cases: 10
- Supported / partial / missing: 10 / 0 / 0
- P0 missing 已补证: `True`
- Gaps marked fixed: `True`
- All fixed GraphRAG evidence gaps closed: `True`

## 不夸大规则

- 不宣称在线 LLM answer win-rate
- 不宣称 GraphRAG 全面优于 baseline
- 不把本地证据覆盖等同于外部专家验证

## Closure evidence

- Closed case ids: cc056
- Manual supplement: `docs/challenge_cup/reproducibility/graphrag_manual_evidence_supplement.csv`
- Source graph report: `evaluation/reports/challenge_cup_graphrag_same_question_report.json`
- Source answer benchmark: `evaluation/reports/challenge_cup_graphrag_answer_benchmark.json`

## 整改任务

当前无 partial/missing remediation item；cc056 已通过 manual evidence supplement 关闭本地证据缺口。
## 复跑命令

- `python scripts/build_graphrag_challenge_report.py`
- `python scripts/build_graphrag_answer_benchmark.py`
- `python scripts/build_graphrag_gap_remediation_plan.py`
- `python scripts/check_challenge_cup_readiness.py`

## Boundary

This report closes local partial/missing GraphRAG evidence gaps with auditable supplement records; it does not claim online LLM answer win-rate, external validation, or that GraphRAG beats every baseline question.
