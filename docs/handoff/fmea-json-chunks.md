# JSON 可选分块导出接口

2026-09-04：经用户批准，给 `CanonicalJsonExporter` 增加可选接口，不修改公共 exporter protocol、REST、ExportService、存储或其他格式导出器。

```python
exporter = CanonicalJsonExporter()
for chunk in exporter.iter_chunks(snapshot, chunk_size=65_536):
    output.write(chunk)
```

## 兼容与调用约定

- `render(snapshot, *, draft_preview=None) -> bytes` 保留，旧调用方无需修改。
- `iter_chunks(snapshot, *, draft_preview=None, chunk_size=65_536)` 返回字节迭代器。`chunk_size` 必须为正整数，不接受布尔值；错误码为 `FMEA_EXPORT_CHUNK_SIZE_INVALID`。
- 同一快照和预览选项下，拼接所有块与 `render()` 的字节完全一致，包括排序、数值、中文、尾部换行和 SHA-256。
- 每块非空，长度不超过 `chunk_size`。块可能切开 UTF-8 多字节字符；应直接写 bytes、拼接后解码，或者使用增量 UTF-8 解码器，不能逐块独立 `.decode()`。
- 快照校验在首次消费迭代器时、输出首块之前执行。错误沿用安全的导出错误格式。
- 消费者必须读完迭代器，才能将制品视为完成。目标文件、异常清理、取消和原子发布仍由调用方负责；本接口不替代制品存储服务。

## 实现与内存边界

沿用现有快照重验和语义投影；按顶层字段排序，对顶层数组逐条记录调用原来的规范 JSON 编码器，再以有界缓冲区输出。它不先调用 `render()` 生成完整 export bytes，也不更换数值/字符串编码规则。

这里的“分块”仅指导出字节的逐段序列化与输出。快照、完整投影以及哈希重验仍驻留内存，单条记录或非数组字段也会编码为完整片段；不能宣称端到端恒定内存。现有 ExportService 仍调用 `render()`，XLSX/DOCX 仍物化完整 Office 文件。

## 验证

新增测试先得到 12 个缺失接口失败，再通过。旧 JSON golden SHA-256 保持不变。

限定矩阵：JSON/XLSX/DOCX 单元测试、跨格式一致性、真实 10,000 行导出性能测试，共 **101 passed in 13.70s**。万行 JSON 测试已删除本地“先 render 再切块”辅助函数，改为直接写入新接口产出的块。

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_export_json.py tests/unit/test_fmea_export_xlsx.py tests/unit/test_fmea_export_docx.py tests/integration/test_fmea_export_consistency.py tests/performance/test_fmea_10000_row_export.py -q
```

本接口完成不等于 Task 8 全产品验收完成；传播、治理、模板迁移等完整验收串联仍按总计划继续。

限定独立复审通过，无阻塞问题。另行验证了现有 ExportService 的真实 JSON 预览/制品清单调用（1 passed）；未要求旧调用方采用迭代接口。
