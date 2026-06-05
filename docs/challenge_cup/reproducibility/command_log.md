# 命令记录

生成时间：2026-06-05 21:06

## 2026-06-05 本轮验证记录

```text
python scripts/extend_challenge_cup_eval_questions.py
-> Wrote 60 questions to evaluation/system_eval_questions.jsonl

python scripts/build_challenge_cup_package.py
-> Wrote docs/challenge_cup with 60 evaluation questions
-> docs/challenge_cup/11_应用场景与专家验证.md
-> docs/challenge_cup/12_专家反馈采集与整改闭环.md
-> docs/challenge_cup/reproducibility/application_validation_report.md
-> docs/challenge_cup/reproducibility/expert_feedback_form.md
-> docs/challenge_cup/reproducibility/evaluation_coverage_profile.json

python scripts/run_day3_retrieval_baselines.py --dataset evaluation/system_eval_questions.jsonl --top-k 5
-> Corpus chunks: 6494
-> evaluation/reports/day3_retrieval_baseline_comparison_20260605_210540.md

python scripts/analyze_day4_failure_cases.py
-> evaluation/reports/day4_failure_analysis_20260605_210642.md
-> Analyzed cases: 40

python -m pytest tests/unit -q
-> 86 passed

python -m pytest api_server/current_console/chroma_rag_poc/tests -q
-> 21 passed

python scripts/run_challenge_cup_live_demo_smoke.py
-> docs/challenge_cup/reproducibility/live_demo_smoke_report.md
-> Status: pass (5/5 checks)

python -m unittest tests/unit/test_console_import_compat.py
-> OK

python -m unittest tests/unit/test_frontend_demo_mode_contract.py
-> OK

python -m unittest api_server/current_console/chroma_rag_poc/tests/test_pipeline.py -k test_frontend_libs_and_assets_are_served_from_root_paths
-> OK

python -m unittest api_server/current_console/chroma_rag_poc/tests/test_pipeline.py -k test_deliverable_assets_are_served_from_stable_root_path
-> OK

python scripts/build_graphrag_context_demo.py
-> evaluation/reports/challenge_cup_graphrag_context_demo.md
-> evaluation/reports/challenge_cup_graphrag_context_demo.json

python scripts/build_defense_rehearsal_scorecard.py
-> docs/challenge_cup/reproducibility/defense_rehearsal_scorecard.md
-> docs/challenge_cup/reproducibility/defense_rehearsal_scorecard.json

node scripts/run_challenge_cup_browser_demo_smoke.mjs
-> docs/challenge_cup/reproducibility/browser_demo_smoke_report.md
-> docs/challenge_cup/reproducibility/browser_demo_smoke_report.json
-> docs/challenge_cup/reproducibility/browser_screenshots/desktop_overview.png
-> docs/challenge_cup/reproducibility/browser_screenshots/desktop_search_results.png
-> docs/challenge_cup/reproducibility/browser_screenshots/desktop_kg_artifacts.png
-> docs/challenge_cup/reproducibility/browser_screenshots/mobile_overview.png
-> Status: pass (13/13 checks)

python scripts/check_challenge_cup_readiness.py
-> docs/challenge_cup/reproducibility/readiness_gate_report.md
-> Status: pass (22/22 gates)
```

推荐复现命令见 `runbook.md`。重新运行后，以新的终端输出和报告时间戳为准。
