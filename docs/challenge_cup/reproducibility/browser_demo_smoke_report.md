# Browser Demo Smoke Report

- Status: `pass`
- Passed: 12/12
- URL: http://127.0.0.1:8000
- Query: 燃气轮机异常振动诊断流程
- Playwright: C:\Users\15410\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules\.pnpm\playwright@1.60.0\node_modules\playwright

| Check | Result | Detail |
| --- | --- | --- |
| health endpoint | pass | GET /api/health -> ok |
| libs route | pass | GET /libs/d3.min.js -> 200 |
| assets route | pass | GET /assets/hero-gas-turbine-rag.webp -> 200 |
| deliverables route | pass | GET /deliverables/06_四本书KG工具跑通演示/knowledge_graph.svg -> 200 |
| page identity | pass | title=动力装备知识库控制台 |
| desktop not blank | pass | desktop overview contains app content |
| desktop console health | pass | 0 warning/error console events |
| search interaction | pass | 集合 gas_turbine_ocr_demo_snapshot · 延迟 43.50 ms · 结果 5 · 后端 public-demo |
| KG SVG render | pass | 1500x980 |
| KG artifact links | pass | knowledge_graph.svg:200, kg_evidence_viewer.html:200, triples.csv:200, run_report.md:200 |
| mobile not blank | pass | mobile overview contains app content |
| mobile console health | pass | 0 warning/error console events |

## Evidence

- Desktop overview screenshot: `docs/challenge_cup/reproducibility/browser_screenshots/desktop_overview.png`
- Desktop search screenshot: `docs/challenge_cup/reproducibility/browser_screenshots/desktop_search_results.png`
- Desktop KG artifacts screenshot: `docs/challenge_cup/reproducibility/browser_screenshots/desktop_kg_artifacts.png`
- Mobile overview screenshot: `docs/challenge_cup/reproducibility/browser_screenshots/mobile_overview.png`

## Static Route Checks

| Route | Result | Detail |
| --- | --- | --- |
| libs route | pass | GET /libs/d3.min.js -> 200 |
| assets route | pass | GET /assets/hero-gas-turbine-rag.webp -> 200 |
| deliverables route | pass | GET /deliverables/06_四本书KG工具跑通演示/knowledge_graph.svg -> 200 |

## Search Result Preview

```text
燃气轮机运行维护手册_doc101.json
JSON
score 80.8%
distance 0.1916
chunk 76
80.8%

关键监测参数阈值包括：排气温度散布度不大于 25°C，轴承振动不大于 25.4 mm/s，滑油金属颗粒不大于 5 ppm，压气机效率衰减不大于 3%。这些指标可作为运行异常和早期故障诊断线索。

record demo-maint-thresholds-076
tokens 94
pages 5.7
展开全文
燃气轮机可靠性维护理论及应用.txt
文本
score 80.5%
distance 0.1952
chunk 130
80.5%

燃气轮机结构强度故障是指发生在燃气轮机机械结构和部件中的形变或机械损伤，会引起机组不正常振动并影响正常运行；由于机组尺寸大、转速高，这些机械故障可能导致破坏性机械损伤、停机甚至机组报废。

record demo-structure-fault-130
tokens 112
pages 第6章
展开全文
燃气轮机设备故障样例文本.md
文本
score 80.0%
distance 0.1999
chunk 21
80.0%

GT-07 燃气轮机升负荷至 75% 后，压气机出口温度从 430°C 升至 485°C，振动传感器 VIB-CMP-01 的读数升至 7.2 mm/s，DCS 触发“压气机出口温度偏高”报警。运行员记录：燃烧室火焰稳定，未见明显燃烧波动。

record demo-gt07-fault-021
tokens 112
pages POC-1
展开全文
燃气轮机设备故障样例文本.md
文本
score 79.8%
distance 0.2017
chunk 22
79.8%

停机检查发现，进气滤网压差偏高，滤网局部堵塞；压气机前三级叶片表面积灰明显。检修人员清理进气滤网，安排压气机叶片离线清洗，并复位温度传感器 TT-COMP-02。复机后，压气机出口温度回落至 438°C，振动值降至 3.1 mm/s。

record demo-gt07-repair-022
tokens 118
pages POC-2
展开全文
燃气轮机设备故障样例文本.md
文本
score 79.7%
distance 0.2035
chunk 23
79.7%

压气机出口温度偏高的常见原因包括进气阻力增大、压气机叶片污染和温度传感器漂移。建议检查进气滤网压差，清理或更换滤网，清洗压气机叶片，并对温度传感器进行校验。若振动值持续偏高，应进一步检查轴承状态和联轴器对中情况。

record demo-gt07-manual-023
tokens 115
pages POC-3
展开全文
```
