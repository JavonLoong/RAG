# Phase 4 FMEA Migration and Delivery Closure — Task 1 Report

日期：2026-09-02
工作区：`C:\Users\35551\Desktop\RAG\.worktrees\interface-output-v1`
分支：`feat/interface-output-v1`
基线：`33c1af445c3c9b96000d424c9ba0f1bb6841e6b0`
范围：仅 Task 1；未实现 importer、persistence、exporter、route、CLI、Skill、browser、DomainPack demo 或 migration 010；未 push/PR。

## 结果

Status: DONE

实现提交：`8131ab4a0b169c46c7a5413581f0a23ae7dad78a`
提交消息：`feat(fmea): define migration and delivery contracts`

交付了：

- `TemplateDraft`、`SourceStructureItem`、`ProposedFieldMapping`；
- `TemplatePatchCandidate` 及 draft/patch status enums；
- `CompatibilityReport`、`MigrationStep`/`MigrationEdge`、`MigrationPlan`、`MigrationReport`；
- `ExportRun`、`ExportArtifactManifest`、`ExportFormat`；
- core FMEA package re-exports；
- 17 个 Task 1 focused contract tests。

## TDD RED 证据

先写测试，再运行 brief 指定命令：

```text
.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_template_migration_contracts.py -q
```

结果：退出码 2，collection 阶段失败：

```text
ModuleNotFoundError: No module named 'core_domain.fmea.template_migration'
1 error during collection
```

这是契约模块缺失导致的预期 RED，不是 fixture、SQL、导入数据或清理错误。

实现后的增量约束也遵循 RED → GREEN：

- 自定义结构 kind 测试先得到 `1 failed`，随后移除 domain-specific kind allowlist；
- identified fields 与 prefixed report hash 测试先得到 `2 failed`，随后加入兼容字段/前缀归一化；
- 重复 source labels/parser warnings 保留测试先得到 `1 failed`，随后改为保留型集合不去重。

## 文件与契约决策

实现文件：

- `core_domain/fmea/template_migration.py`
- `core_domain/fmea/__init__.py`
- `fmea_application/delivery_contracts.py`

测试文件：

- `tests/unit/test_fmea_template_migration_contracts.py`

关键决策：

1. 所有新对象使用 `@dataclass(frozen=True, slots=True)`；列表/映射会转为 tuple/`MappingProxyType`，嵌套结构不可变。
2. hash 校验复用既有 lowercase SHA-256 规则（兼容可选 `sha256:` 前缀）；报告 hash 使用既有 `governance.canonical_hash`，不创建第二套 JSON/hash 编码。
3. `TemplateDraft.status` 只能是 `draft`；来源文件名只接受 contained filename；来源结构 kind 仅做 bounded text 校验，以保留未来 Excel/Word/自定义结构，不把燃料/燃烧字段写进 generic core。
4. draft 保留 source filename/hash/type、结构、identified/proposed fields、unknown fields、ambiguous fields 与 parser warnings。保留型 source 集合按原顺序保存，重复内容不被静默丢弃；mapping source keys 仍必须唯一。
5. `TemplatePatchCandidate` 的 diff 是有上限、冻结、唯一 JSON-Pointer path 的 add/replace/remove 建议；`applied` 永远必须为 `False`，因此模型值不能成为 authority。
6. `MigrationPlan` 只能消费显式 `MigrationStep` edges；每条边有 source/target identity 与 adapter identity，版本边连续、同一 domain identity、最多 64 条，缺失路径 fail closed 并抛出 `migration path is not explicit`。
7. `CompatibilityReport`/`MigrationReport` 都是 immutable、bounded、UTC timestamped，并生成 deterministic canonical report hash；兼容性报告不允许“不可兼容但没有 blocking reason”。
8. `ExportRun` 与 `ExportArtifactManifest` 都绑定 revision ID 与 snapshot hash；published output 必须有 publication ID，draft preview 必须没有 publication ID。format 仅允许 JSON/XLSX/DOCX，media type 与 format 必须精确匹配。
9. artifact byte length 拒绝 bool/负数/超过 1 GiB；ID、filename、media type、hash、timestamp 均有长度/格式边界；filename 拒绝路径分隔符、父目录片段和保留路径名。

## 验证命令与实际结果

| 命令 | 实际结果 |
| --- | --- |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_template_migration_contracts.py -q` | `17 passed in 0.06s` |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_template_migration_contracts.py tests/unit/test_fmea_snapshot_contracts.py tests/unit/test_fmea_domain_pack.py -q` | `54 passed in 0.58s` |
| `.venv\Scripts\python.exe -m ruff check core_domain\fmea\template_migration.py core_domain\fmea\__init__.py fmea_application\delivery_contracts.py tests\unit\test_fmea_template_migration_contracts.py` | `All checks passed!` |
| `.venv\Scripts\python.exe -m ruff format --check core_domain\fmea\template_migration.py core_domain\fmea\__init__.py fmea_application\delivery_contracts.py tests\unit\test_fmea_template_migration_contracts.py` | `4 files already formatted` |
| `.venv\Scripts\python.exe -m compileall -q core_domain\fmea\template_migration.py core_domain\fmea\__init__.py fmea_application\delivery_contracts.py tests\unit\test_fmea_template_migration_contracts.py` | 退出码 0，无输出 |
| `git diff --cached --check` | 无 whitespace error；仅 Git 的 LF/CRLF warning |

未运行全量 pytest。一次 exploratory mypy 会沿既有 FMEA import chain 报仓库已有类型债务；它不是 brief 要求的 Task 1 gate，也没有用它作通过声明。

## Self-review

- staged/committed 文件严格为 brief 列出的 4 个实现/测试文件；未修改既有 canonical、snapshot、DomainPack、governance 或 migration SQL。
- `rg -i 'fuel|combustion'` 对两个新 production modules 无命中；fuel/combustion 只存在于 generic-path 测试的 migration identity fixture。
- 既有 snapshot 与 DomainPack compatibility matrix 通过，证明新 `core_domain.fmea` re-export 未破坏现有导入路径。
- 没有 importer、registry writer、migration executor、child-revision mutation、artifact publisher 或 route 行为；本任务只冻结后续实现消费的 DTO/contracts。
- 使用现有 `FmeaDomainError` 和 canonical hash/value patterns；没有网络、模型调用、数据库写入或外部副作用。

## Residual risks / handoff

1. Task 2/3 必须继续把 `TemplateDraft` 当作 import-only draft，把 `TemplatePatchCandidate.applied=False` 当作不可越过的 suggestion 边界；接受 patch/注册模板需由后续 human template-admin workflow 完成。
2. Task 3 必须消费 `MigrationPlan.steps` 的 exact ordered edges，并在 confirmation 中创建 child revision；本 Task 1 contract 不会也不能保证 repository 原子性或 source revision 不变，需要后续 service/persistence 测试证明。
3. `ExportArtifactManifest` 只能在单对象内验证 publication/preview 互斥和 format/media type；后续 export service 必须额外验证 manifest 与 `ExportRun` 的 run/revision/snapshot/publication identities 逐字段相等，并在 artifact bytes 写入后验证实际 hash/byte length。
4. 1 GiB 是本 contract 的制品上限，不等价于 10,000-row Office adapter 的内存保证；后续 acceptance 仍需验证分页/流式边界和 contained atomic publication。
