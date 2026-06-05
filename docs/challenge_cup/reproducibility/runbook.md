# 可复现运行手册

## 运行测试

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit -q
.\.venv\Scripts\python.exe -m pytest api_server/current_console/chroma_rag_poc/tests -q
```

## 扩展评测集

```powershell
.\.venv\Scripts\python.exe scripts/extend_challenge_cup_eval_questions.py
```

## 运行现场演示烟测

```powershell
.\.venv\Scripts\python.exe scripts/run_challenge_cup_live_demo_smoke.py
node scripts/run_challenge_cup_browser_demo_smoke.mjs
```

## 重新生成 Day3 baseline

```powershell
.\.venv\Scripts\python.exe scripts/run_day3_retrieval_baselines.py --dataset evaluation/system_eval_questions.jsonl --top-k 5
```

## 重新生成 Day4 失败分析

```powershell
.\.venv\Scripts\python.exe scripts/analyze_day4_failure_cases.py
```

## 重新生成挑战杯成果包

```powershell
.\.venv\Scripts\python.exe scripts/build_challenge_cup_package.py
```

## 刷新终审答辩 PPT

```powershell
.\.venv\Scripts\python.exe scripts/build_challenge_cup_defense_deck.py --force
```

## 刷新官方评审口径对齐表

```powershell
.\.venv\Scripts\python.exe scripts/build_challenge_cup_official_rubric_alignment.py
```

## 刷新硬证据台账

```powershell
.\.venv\Scripts\python.exe scripts/build_challenge_cup_hard_evidence_ledger.py
```

## 运行结项 readiness gate

```powershell
.\.venv\Scripts\python.exe scripts/check_challenge_cup_readiness.py
```
