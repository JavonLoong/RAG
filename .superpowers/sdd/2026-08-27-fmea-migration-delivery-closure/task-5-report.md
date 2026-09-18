# Phase4 Task5 Report

## RED

先创建三个测试文件，再执行：

```text
.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_export_xlsx.py tests/unit/test_fmea_export_docx.py tests/integration/test_fmea_export_consistency.py -q
```

结果为 collection failure：三个新测试文件分别因 `fmea_infrastructure.export_xlsx` / `fmea_infrastructure.export_docx` 尚不存在而报告 `ModuleNotFoundError`。这是预期的 RED。

## GREEN

新增 XLSX/DOCX presentation-only adapters 和对应 unit/integration tests。最终 Task5 exact：

```text
20 passed in 1.81s
```

Task4 JSON/snapshot regression：

```text
33 passed in 0.53s
```

## 设计

- 两个 adapter 接收严格类型 `NormalizedFmeaSnapshot`，复用已审查的 canonical JSON projection 和 snapshot hash 校验；不访问 repository/model/network/filesystem path，不重算 risk/propagation，不修改 authority 状态，`render` 只返回 bytes。
- XLSX 固定 `Manifest`、`FMEA`、`Risk`、`Propagation`、`Evidence`、`Decisions`、`Unresolved` 七个 sheet，带冻结表头、筛选、可读样式和最多 48 字符的 bounded column widths。
- Manifest 显式包含 export/snapshot schema、draft marker、snapshot/revision/publication/manifest identity、hash/count/version/audit 信息以及 format/media type。
- XLSX 所有数据 cell 均以 string cell 写入；字符串原值和类型通过隐藏 `__types__` 列保留，公式前缀不会生成 formula XML、external link、macro 或 DDE。
- DOCX 含 title、Manifest、六个数据 section 和 footer identity；使用内存 bytes 生成，包 XML/relationship 检查拒绝 external URI、宏、embedding、altChunk 和字段执行内容。
- draft preview 在两种 Office 格式及 JSON 对照语义中使用 exact `DRAFT PREVIEW — NOT PUBLISHED`；published 输出不写入该 marker。
- Office XML 不可表示控制字符、NaN/Inf、非法类型、超界 cell 文本和恶意 package 成员均 fail-closed；不做隐式清洗或语义改写。列宽仅采样前 32 行，关联采用一次遍历/预建列集合，保留 Task8 10k 行扩展空间。
- consistency integration parser 独立使用 openpyxl、python-docx 和 ZIP/XML 读取，未调用 adapter 的内部 projection；验证 JSON/XLSX/DOCX 的 identity、完整 rows、risk、propagation、evidence、decisions、unresolved、version manifest 语义一致，并覆盖空可选部分、Unicode、公式前缀、draft/published、重复 render 和 malformed/adversarial input。

## 调试与风险

初次 GREEN 暴露 DOCX 自校验器误把合法包内 `thumbnail.jpeg` 当作 XML 解析的问题；修复为仅解析 `.xml`/`.rels`，仍保留全部关系和 XML 安全检查。Office ZIP metadata 不要求 byte equality；重复 render 通过 semantic projection 验证确定性。由于用户限制，未修改 composition/API/CLI/frontend，adapter 注册由后续任务负责。

## 验证

- `ruff check`：通过。
- `ruff format --check`：5 files already formatted。
- `compileall`：通过。
- `git diff --check` 与 `git diff --cached --check`：通过。
- 提交前暂存文件精确为本 Task5 授权的 5 个文件；未 push/PR。

## Commit

`6c96f8bff07b79f5b19aeda2d1c2036f5b413c03` — `feat(fmea): export consistent xlsx and docx`

---

## Review Round 1 修复

### Reviewer probes RED

先新增首审复现测试，再运行 13 个定向 probes。结果为 `13 failed`：

- 三个 exporter 均不接受 per-call `draft_preview` keyword。
- hash-consistent `row_count` / `schema_version` mutation 未被三个 exporter 拒绝。
- `ExportService` 调用 fake exporter 时记录到 `draft_preview=None`，没有传 command bool。
- canonical JSON 不支持 preview envelope，真实 service 测试也无法创建带 direct-use preview default 的 JSON exporter。

共享 snapshot helper probe 单独运行时因 `revalidate_normalized_snapshot` 尚不存在而 collection error。失败原因均与 review I-1/I-2/I-3 对应，不是测试语法或 fixture 错误。

### GREEN 设计

- `SnapshotExporter.render` 统一为 `render(snapshot, *, draft_preview: bool | None = None) -> bytes`；`ExportService.start` 每次显式传入 `command.draft_preview`。三个生产 exporter 与两个 fake/Blocking exporter 使用同一签名，不注册 preview/published 双实例，也不使用可变全局状态。
- direct-use constructor default 保留；service keyword 对本次调用具有最终决定权。真实 `ExportService` 测试使用一个 constructor default 为 preview 的 JSON exporter，连续验证 published command 仍输出 published、preview command 输出 preview。
- JSON/XLSX/DOCX envelope 统一增加 `snapshot_schema_version`、`draft_preview`、`draft_marker`、`source_publication_id`、`format`、`media_type`。preview 的 `publication_id=None`，来源 publication 只写入 `source_publication_id`；published 则保留 authoritative `publication_id` 且 `source_publication_id=None`。
- application-owned `revalidate_normalized_snapshot` 只复制 exact plain JSON builtins，重建新的 `NormalizedFmeaSnapshot`，重放 schema、identity、collection、row count、hash、timestamp 和 export-safety 构造不变量。三个 exporter 在 projection 前调用；`ExportService` 的 snapshot load 与 narrative 边界也复用它，旧的 service 私有 snapshot copy/rebuild 实现已删除。
- helper 对 hash-consistent row-count/schema 绕过以及带恶意 `__eq__`/`__str__`/`__hash__`/`__len__` 的 nested value 固定 fail-closed，不回显输入且不保留 backend cause。
- consistency parser 继续独立使用 JSON/openpyxl/python-docx，新增 preview/source publication/schema/format/media type 比较；published JSON 和 XLSX/DOCX 全部 ZIP XML 均 raw-scan 确认不存在 marker。DOCX footer 显式包含 revision/snapshot/publication/source-publication/hash identity。
- Office formula-string、external relationship/macro/altChunk、非法 XML 控制字符与 bounded-width/线性遍历逻辑未放宽。

### 最终验证

- Task5 exact：`24 passed in 1.93s`。
- JSON/snapshot 控制端：`40 passed in 0.54s`。
- 完整 export-runs（含 provider/cancellation/idempotency/recovery）：`79 passed in 22.05s`。
- `ruff check`：`All checks passed!`。
- `ruff format --check`：`12 files already formatted`。
- `compileall`、`git diff --check`、`git diff --cached --check`：通过。
- 提交内容精确为 12 个授权文件；未修改 composition/store/repository/migrations/API/CLI/frontend，未 push/PR。

### Review Fix Commit

`884ec9b815870fa71dc61649c897213788560a8f` — `fix(fmea): unify preview export contracts`

---

## Review Round 2 修复

### Reviewer probes RED

新增共享 revalidation probe、8 类嵌套业务字段 × JSON/XLSX/DOCX × published/preview 的 48 个跨格式 probes，以及全 ZIP 成员/entity-aware Office marker probe。生产代码未修改时定向运行结果为：

```text
49 failed, 1 passed in 3.14s
```

共享 helper 和全部 48 个 exporter 组合均以 `DID NOT RAISE` 失败，证明 hash-consistent snapshot 中的保留 sentinel 会被当作业务数据渲染。全包 Office probe 已通过，证明新测试 helper 能遍历每个 ZIP member，并在 XML entity decode 后识别 marker。

### GREEN 设计

- application-owned `revalidate_normalized_snapshot` 在复制任何 exact plain string 时递归拒绝保留 presentation sentinel `DRAFT PREVIEW — NOT PUBLISHED`；检查覆盖顶层字符串、嵌套 tuple/list/dict value 及字符串 mapping key。
- snapshot 在检查前后均不做 sanitize、escape 或 mutation；带 sentinel 的合法 hash-consistent snapshot 固定 fail-closed。
- 三个 exporter 继续在 projection/render 前调用同一 revalidation helper，并把 helper failure 映射到各自稳定公开错误：`FMEA_EXPORT_JSON_INVALID`、`FMEA_EXPORT_XLSX_INVALID`、`FMEA_EXPORT_DOCX_INVALID`。错误不回显 marker、相邻业务秘密或内部 cause。
- marker 常量由 application contract 单点定义，JSON envelope 和 DOCX presentation 复用；XLSX 通过共享 projection 获取同一值。
- consistency package helper 遍历 XLSX/DOCX 的每个 ZIP member；对 XML/relationships 同时执行安全 XML parse、entity decode 和 visible-text 拼接。它继续拒绝 external relationship、外部 URI、macro/executable/embedding/altChunk/field parts 与不安全 member path。
- 正常 published Office artifacts 的全包 marker 命中为 0；preview 只允许生成位置命中：XLSX `xl/worksheets/sheet1.xml` 1 次，DOCX `word/document.xml` 2 次。

### Round 2 验证

- RED probes 修复后：`50 passed in 0.79s`。
- review 指定六文件 bounded matrix：`193 passed in 24.39s`（先前 143 + 新增 50）。
- `ruff check`：`All checks passed!`。
- `ruff format --check`：`6 files already formatted`。
- `git diff --check`：通过。
- Review Round 2 commit：`0d02b541d349e3cc01b8ea0b891d14c3d88eec46` — `fix(fmea): reserve preview marker semantics`。
