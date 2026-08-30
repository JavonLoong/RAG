# Phase 3 FMEA Governance Closure — Task 2 Report

日期：2026-08-31
基线：`64d023f1`（Task 1 accepted）
范围：仅实现 Task 2，未进入 Task 3+，未 push/PR。

## 结果

Status: DONE

本地 commits：`0573812b`（implementation/tests）、`8d6fb19a` 与 `783c80ac`（本报告及格式修复）。

以下“Fix round 1”记录覆盖独立复审 round 1 的 NEEDS_FIXES；以其最新结果为准。

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

## Fix round 1 — independent review response

日期：2026-08-31

### 结果

Status: DONE

实现 commit：`16bd811a`；本报告单独作为 documentation commit 保存。

本轮只处理 Task 2，没有进入 Task 3+，没有 push/PR，也没有创建子智能体。

### RED

先新增最小反向测试，再改生产代码。首轮 focused 命令：

```text
.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_revision_assembler.py tests/unit/test_fmea_publication_readiness.py tests/unit/test_fmea_governance_assistance.py tests/unit/test_fmea_governance_source.py -q
```

结果：`15 failed, 15 passed`。失败分别复现了 mapping/coerce 输入、弱类型 policy、缺失 graph 无条件 blocker、零/伪 identity、foreign parent、phantom evidence、空 acknowledgement wildcard、model forged mapping/private path、以及 callback source seam。

### GREEN 与设计裁定

- `GovernanceDomainPolicy` 是 frozen typed policy；required risk/propagation/template/scoring/propagation-rule/evidence 与 acknowledgement 开关独立表达，所有 bool 使用 exact `bool` 检查，unknown mapping field 拒绝，`"false"` 不会被转换为 true。缺失 graph 不由 assembler 添加 blocker，只由 policy 的 `required_propagation` 决定；retrieval profile 只进入 provenance。
- `ResolvedArtifactIdentity` 与 `GovernanceArtifactSet` 强制 server registry verified、非零 hash、manifest id/version/hash 绑定。`RegistryGovernanceArtifactProvider` 逐一调用现有 DomainPack/template/scoring/propagation registries，交叉验证返回对象身份和 canonical content hash；graph 的实际 rule pack 必须匹配 domain pack 与 resolved propagation rule。
- `GovernanceInputs` 现在只接收 typed `FmeaAnalysis`、`DomainPackManifest`、resolved identities、typed rows/risk/graph/evidence/acknowledgements；删除 `Mapping`/`coerce`、caller `analysis_hash`、deterministic placeholder。analysis hash 始终从 authoritative analysis canonical helper 计算。`RevisionAssemblyRequest` 增加 `parent_revision_hash` precondition，parent id/hash/workspace/analysis 全绑定。
- assembler 对 row field claims、risk dimensions、graph edges 和 paths 逐引用调用既有 evidence validators，并检查 pack self-hash/lineage/workspace/ACL/timestamps/expiry；phantom ref 和失效 pack 都生成 blocking issue。acknowledgement 只接受 exact typed `HumanAcknowledgementReference`（HUMAN、decision/scope/issue/revision/version/evidence 全匹配）；没有在 `FmeaRevision` 重复添加字段，沿用既有 `ReadinessIssue.acknowledgement_decision_id` 对 canonical revision hash 的覆盖。
- assistance 只接受 typed `PublicationReadinessReport`；发送 generator 前构造不含 workspace/analysis/private path/URI/raw provider output 的 bounded allowlisted `ReadinessChecklistProjection`。generator mapping 采用 exact schema、严格 bool、长度上限和 identifier 校验；任何 ready/blocker/revision identity 改写拒绝，generator unavailable 回退 offline，`AssistanceSuggestion.applied` 始终 false。
- `RepositoryGovernanceSource`/`ServerGovernanceSourceAdapter` 由 `GovernanceRepositoryProviders` 的 typed analysis/review/risk/propagation/evidence/artifact/run/ack query ports 组成。`load_inputs` 只接收 analysis/workspace scope，实体与 identity 全部 server lookup；移除 `WorkspaceGovernanceSource` arbitrary callable seam，不增加 SQLite migration/repository 或 governance mutation。

### 测试与工具结果

最终指定 focused、计划 compatibility、Task 1 governance/review 最小兼容组合：`159 passed`。

```text
.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_revision_assembler.py tests/unit/test_fmea_publication_readiness.py tests/unit/test_fmea_governance_assistance.py tests/unit/test_fmea_governance_source.py tests/unit/test_fmea_risk_service.py tests/unit/test_fmea_propagation_review.py tests/unit/test_fmea_review_service.py tests/unit/test_fmea_governance_contracts.py tests/unit/test_fmea_review_composition.py tests/unit/test_fmea_review_contracts.py tests/unit/test_fmea_propagation_graph.py tests/unit/test_fmea_risk_repository_contract.py -q
```

结果：`159 passed in 0.86s`。

```text
.venv\Scripts\ruff.exe check <Task 2 changed production/test files>
.venv\Scripts\ruff.exe format --check <Task 2 changed production/test files>
.venv\Scripts\python.exe -m compileall -q fmea_application fmea_infrastructure tests
git diff --check
```

结果：ruff check passed；除保持仓库既有格式的 `governance_contracts.py` 外，其余 10 个改动文件 format check passed；compileall passed；diff check passed。未运行全量 pytest。`governance_contracts.py` 只保留 parent hash 的 8 行必要契约变更。

### Fix round 1 文件与迁移

生产/port/composition：

- `fmea_application/revision_assembler.py`
- `fmea_application/governance_assistance_service.py`
- `fmea_application/governance_contracts.py`（仅 parent hash precondition）
- `fmea_application/ports.py`
- `fmea_infrastructure/governance_assistance_generator.py`
- `fmea_infrastructure/composition.py`

测试/fixtures：

- `tests/unit/test_fmea_revision_assembler.py`
- `tests/unit/test_fmea_publication_readiness.py`
- `tests/unit/test_fmea_governance_assistance.py`
- `tests/unit/test_fmea_governance_source.py`
- `tests/fmea_governance_fixtures.py`（typed fixture migration）

### Concerns / Task 3/4 handoff

1. Task 3 需要为 `GovernanceRepositoryProviders` 提供现有 review/risk/propagation/analysis/evidence/decision repositories 的 typed query wrappers；不能恢复 callback/mapping loader，也不能让 transport/client 提供治理实体或 identities。
2. Task 3 继续从 persistence 读取真实 `revision_record_version`，并保持 Task 1 `PreparedApprovalSubmission`/`PreparedPublication` 的 version evidence；不得把 submission/publication version 写入 `FmeaRevision` content hash。
3. Task 4 可消费 `PublicationReadinessReport` 和 immutable assistance suggestion，但不得让模型、ack reference 或 UI 改写 deterministic blockers、revision identity、ack lineage 或 legacy `PublicationStatus`。
