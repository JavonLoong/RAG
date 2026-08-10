# 百度云 OCR 与本地 OCR 优化流程

## 目标

这套流程不把“百度结果不同”直接解释成“百度一定更准”。只有人工逐字核对的金标文本，才能计算本地和云端各自的字符错误率（CER）。没有金标时，只报告差异并送人工复核。

## 数据安全门禁

- 每个样本必须填写 `external_allowed`。
- 只有严格等于 `true` 的页面才会上传百度云。
- M1 清单中标记 `internal`、`external_allowed=false` 的资料不能直接用于云端测试。
- 百度 API Key、Secret Key 和 access token 只通过环境变量进入进程，不写入仓库、日志和报告。
- 建议先使用团队自行制作或明确获得外发许可的 20—50 页小样本。

## 分层抽样

至少分别选择以下页面，不能只看平均值：

| 类别 | 建议关注指标 |
|---|---|
| 正文 | CER、断句、数字和英文缩写 |
| 低清扫描 | CER、空白行、漏行 |
| 双栏 | 阅读顺序、跨栏串行 |
| 表格 | 行列对应、合并单元格 |
| 公式/符号 | 数字、上下标、拉丁字符 |
| 图注/页眉页脚 | 错归正文、重复文字 |

## 准备清单

复制 `configs/ocr/benchmark_manifest.json.example` 为 `configs/ocr/benchmark_manifest.json`，再为每个样本填写：

- `source_path`：图片或 PDF；
- `page`：PDF 页码，图片固定为 1；
- `local_result_path`：已有本地 OCR 的 JSON 或 JSONL；
- `gold_text`：人工逐字核对结果；
- `category`：正文、表格、公式或双栏等；
- `external_allowed`：资料负责人确认是否允许上传云端。

## 本地预检

不调用百度，只验证清单、源文件、本地 OCR 和金标：

```powershell
.\.venv\Scripts\python.exe scripts\run_ocr_benchmark.py `
  --manifest configs\ocr\benchmark_manifest.json `
  --output-dir build\ocr_benchmark\local_only
```

## 百度云对比

先在百度文字识别控制台创建应用并取得 API Key 和 Secret Key，然后只在当前终端设置环境变量：

```powershell
$env:BAIDU_OCR_API_KEY = "<API Key>"
$env:BAIDU_OCR_SECRET_KEY = "<Secret Key>"
$env:BAIDU_OCR_MODEL = "general"

.\.venv\Scripts\python.exe scripts\run_ocr_benchmark.py `
  --manifest configs\ocr\benchmark_manifest.json `
  --output-dir build\ocr_benchmark\baidu_vs_local `
  --include-cloud
```

`general` 是含位置的通用识别接口，适合比较文字和坐标。还可以在小样本上分别测试 `general_basic`、`accurate_basic` 和 `accurate`，但每次调用都要计入配额。

如果已确认账号的实际单价，可额外传入：

```powershell
--price-per-cloud-call 0.005
```

这个参数只用于估算，不代表账号真实账单。

## 输出

- `ocr_benchmark.json`：逐页原始结果、指标、SHA-256 和策略决定；
- `ocr_benchmark.md`：适合汇报的汇总、差异明细和优化建议。

重点指标：

- `local_cer`：本地结果相对人工金标的字符错误率；
- `cloud_cer`：百度结果相对人工金标的字符错误率；
- `pair_disagreement_rate`：两套 OCR 互相有多大差异，不能替代准确率；
- `numeric_token_overlap`：数字保留一致程度；
- `latin_token_overlap`：英文缩写和变量保留一致程度。

## 如何把结果用于“微调”

云端 OCR 通常不能直接拿项目数据去微调本地引擎。正确做法是先把错误分成几类，再分别处理：

1. 图像质量问题：调整渲染倍率、去噪、倾斜矫正和对比度。
2. 双栏顺序问题：保留坐标，先做版面分栏，再按栏排序。
3. 专业词错字：建立经过人工审核的燃机术语词典，做受控后处理。
4. 表格问题：转用表格/办公文档识别，正文 OCR 不承担表格结构恢复。
5. 本地模型问题：积累人工金标后，再评估 PaddleOCR 微调或 PP-OCR 模型升级。
6. 路由问题：本地高置信度页面留在本地；低置信度、复杂版面且允许外发的页面才调用百度。

任何自动纠错都必须保留原始文字、纠正后的文字、页码和审核记录，不能覆盖原文。
