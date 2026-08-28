# 燃料与燃烧 FMEA 风险验收夹具

该目录提供不依赖外部模型、数据库或检索后端的固定输入。七种检索模式都转换成同一个不可变 EvidencePack 合同，FMEA 风险层不会导入或判断具体 RAG/GraphRAG 后端。

夹具描述的示例链路是：燃料过滤器堵塞导致下游压力降低，继而造成偏稀燃烧和火焰稳定性下降。示例仅用于软件合同、证据绑定和风险工作流验收，不是工业安全认证，也不能替代专业工程师的系统边界确认、评分依据审查或现场验证。

运行：

```powershell
.venv\Scripts\python.exe scripts\run_fmea_risk_acceptance.py --retrieval-mode combined
.venv\Scripts\python.exe scripts\verify_fmea_risk_acceptance.py --latest
```
