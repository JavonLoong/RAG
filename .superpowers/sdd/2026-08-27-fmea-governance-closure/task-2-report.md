# Phase 3 FMEA Governance Closure — Task 2 Report

日期：2026-08-30  
基线：`64d023f1`（Task 1 accepted）  
范围：仅实现 Task 2，未进入 Task 3+，未 push/PR。

## 结果

Status: DONE

Task 2 已提供：

- server-owned `GovernanceInputs`、canonical `RevisionAssembler`；
- immutable `PublicationReadinessContext`、deterministic `PublicationReadinessPolicy`、`PublicationReadinessReport`；
- offline/provider-neutral `GovernanceAssistanceService` 与 immutable `AssistanceSuggestion(applied=False)` checklist；
- `GovernanceSourcePort` 与 `GovernanceAssistanceGenerator`；
- 不接 SQLite、不改变 governance state 的 composition runtime/source scope seam。

## TDD 记录

### RED

先添加计划列出的三组 focused tests，并加入 scope、客户端 resource override、active run、stale child、critical issue、human actor 等负向覆盖。

命令：

```text
.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_revision_assembler.py tests/unit/test_fmea_publication_readiness.py tests/unit/test_fmea_governance_assistance.py -q
```

结果：`14 failed`。失败原因为三个 Task 2 production modules 尚不存在（`ModuleNotFoundError`），不是既有 Task 1 contract failure。

### GREEN

最小实现后修正了一个真实问题：revision ID 初版吸收了输入 rows 的原始顺序，导致相同集合的 hash 不一致；改为只基于 canonical sorted outputs 计算。

随后补齐了：

- scope 校验与未知输入字段拒绝；
- EvidencePack lineage/self-hash 校验；
- accepted row、confirmed risk、confirmed propagation、required evidence、identity hash、active mutation run blockers；
- acknowledgement reference 仅保留 source 已有引用；
- model checklist 对 `ready`、`blocking_codes`、revision identity 做不可变 authority binding。

## 验证

所有指定测试组均通过：

| 验证组 | 结果 |
| --- | --- |
| Task 2 focused（assembler/readiness/assistance） | `14 passed` |
| 计划 compatibility（risk/propagation/review） | `42 passed` |
| Task 1 governance contracts + review composition 最小兼容组 | `44 passed` |
| ruff scoped check | passed |
| `python -m compileall -q fmea_application fmea_infrastructure tests\unit` | passed |
| `git diff --check` | passed |

未运行全量 `pytest`，符合 Task 2 范围要求。

## 设计与安全约束核对

- `RevisionAssembler` canonical-sort rows、risks、evidence packs、identities、provenance 与 issues；相同输入不依赖 clock 的 revision hash。
- revision content hash 不包含 `revision_record_version`，也没有用 submission/publication version 替代 Task 1 的 persistence precondition evidence；Task 1 `PreparedApprovalSubmission`/`PreparedPublication` 未被复制或弱化。
- `GovernanceSourcePort.load_inputs` 只接收 server-owned `analysis_id`/`workspace_id`；composition adapter 拒绝返回不同 scope，并拒绝未知的客户端 resource override 字段。
- readiness 是 deterministic-first：active mutation runs、未接受 rows、缺失/失效 evidence、未确认 risk/propagation、stale child/analysis、缺失/未解析 identity、未确认 critical issue 均不能被 model checklist 清除。
- assistance 默认 offline；未新增厂商或 DeepSeek 耦合。模型只产生 `APPROVAL_READINESS_CHECKLIST`，`applied` 永远为 `False`。
- 新增实现不硬编码燃烧/燃料领域；legacy `PublicationStatus` 与既有 Task 1 contracts 未改动。

## 文件

实现/port/composition：

- `fmea_application/revision_assembler.py`
- `fmea_application/governance_assistance_service.py`
- `fmea_application/ports.py`
- `fmea_infrastructure/governance_assistance_generator.py`
- `fmea_infrastructure/composition.py`

测试：

- `tests/unit/test_fmea_revision_assembler.py`
- `tests/unit/test_fmea_publication_readiness.py`
- `tests/unit/test_fmea_governance_assistance.py`

## Concerns / handoff

1. Task 2 只提供 `WorkspaceGovernanceSource` callback seam；没有实现 repository/SQLite loader、governance mutation service、REST/CLI/export/UI。这些留给 Task 3/4。
2. `DomainPackManifest` 当前只携带 nested template/rule 的 id/version。若 source 没有传真实 `version_identities` hash，assembler 会使用 deterministic placeholder 同时产生 identity-hash blocker；Task 3 的 authoritative source 必须提供真实 identity evidence，不能把 placeholder 当作 ready。
3. 后续 approval/publication preparation 必须继续从 persistence 读取并传递真实 `revision_record_version`，不可用 submission/publication record version 替换。

Task 3 handoff：实现 server-owned `GovernanceSourcePort` 的 authoritative query/persistence 接入，并消费本报告中的 readiness blockers；保留客户端不能选择 DomainPack/template/rule/evidence/graph identity 的边界。  
Task 4 handoff：在 readiness 已确定后接 publication/export/UI；model checklist 仍只能作为 immutable explanation，不能改变 deterministic readiness 或 legacy publication status。
