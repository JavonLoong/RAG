# M2 解析与标注完成验收（2026-08-08）

- 仓库：`D:\虚拟C盘\RAG`
- 基线提交：`6603cf87c5944264907060f4dcec16d3e2445190`
- 实施模式：M2 能力补齐与回归验收
- 责任成员口径：纪文龙、丁河谷

## 结论

原先标记为“部分完成”的 M2 项目已经补齐为可执行、可审计、可复核的实现，并以代表性文件和故障注入测试验证。外部 OCR 与翻译引擎仍属于部署依赖，但其调用契约、超时、失败记录、重试和证据回流均已接入。

## 完成矩阵

| 验收项 | 状态 | 可执行证据 |
|---|---|---|
| 原生文字提取与 OCR | 完成 | 扫描 PDF/图片自动登记源文件、创建 OCR 作业、执行或阻塞、页级结果自动生成资料候选；作业可查询和重试 |
| 标题、段落、阅读顺序、表格、图片和图注 | 完成 | `TextBlock` 保存稳定 block/table/image/caption/bbox 定位；DOCX 按 XML 正文顺序恢复段落和表格；Docling Markdown 保留表格/图片/图注类型 |
| 语言、原文和对齐译文 | 完成 | 自动识别 `zh/en/mixed/unknown`；保存原文、哈希和修复审计；请求翻译时逐块保存 source/target/block_id 对齐记录 |
| 乱码、断句和基础结构修复 | 完成 | 支持现有多编码解码；保守修复英文断词、中英文软换行；原文不可丢失并可由审计元数据复核 |
| 缺页、低质量与表格错位 | 完成 | 缺页、空白页、低置信度、阅读顺序、OCR 超时/失败、表格列宽不一致均生成页/块/表级质量问题和证据 ID |
| 原页与结果对照复核 | 完成 | 原文件作为不可变 source asset 持久化；review-package 返回页图、可编辑候选、问题、任务和审核历史；另提供原页图片接口 |
| 确认、否定、修改和审核记录 | 完成 | review task 与 SQLite 审核记录联动；approve/reject/modify/rollback 均持久化，修改生成新资料版本 |
| 异常、超时和人工结果回流 | 完成 | 单页超时与失败不中断全批次；OCR 作业可重试；M2 修订经人工批准后重建索引、重建图候选，经图审核后重新生成 FMEA |

## 新增接口

| 接口 | 用途 |
|---|---|
| `POST /api/delivery/documents/intake` | 登记原始资产；按需请求翻译；扫描件自动建立/执行 OCR 作业 |
| `POST /api/delivery/documents/intake/ocr-result` | 接收块、表格、图片、图注、坐标及页级故障结果 |
| `GET /api/delivery/documents/ocr-jobs/{job_id}` | 查询 OCR 作业、尝试次数、页面结果和错误 |
| `POST /api/delivery/documents/ocr-jobs/{job_id}/run` | 初次执行或重试 OCR 作业 |
| `GET /api/delivery/documents/{version_id}/review-package?page=1` | 获取原页与解析结果对照复核包 |
| `GET /api/delivery/documents/source-assets/{asset_id}/pages/{page}` | 获取不可变原始文件的指定页图 |

## 部署配置

- OCR：应用可注入 `app.state.m2_ocr_provider`；独立部署可配置 `POWER_RAG_M2_OCR_COMMAND`。命令按 JSON 契约返回页文字、置信度、块、表格和布局信息。
- 翻译：应用可注入 `app.state.m2_translation_provider`；HTTP 部署可配置 `POWER_RAG_TRANSLATION_URL`，仅允许 `http/https`。
- 未配置外部引擎时不会伪造结果：OCR 作业进入 `blocked`，翻译请求生成失败候选和人工处理问题。

## 验证结果

```text
M2 + M2-M5 专项：54 passed in 6.24s
完整单元测试：262 passed in 54.67s
新增文件静态检查（E/F/I）：All checks passed
Python compileall：passed
```

新增代表性验收覆盖：原生 PDF、扫描 PDF、DOCX、图片、中英文、逐块翻译、结构定位、表格错位、原页对照、低置信度、缺页、OCR 单页超时、重试恢复、reject 审核，以及 M2→M3→M4→M5 回流。

