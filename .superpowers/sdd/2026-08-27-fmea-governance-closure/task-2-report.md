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

## Fix round 2 — re-review OPEN/NEW response

日期：2026-08-31

### 结果

Status: DONE

实现 commit：`a05cf595`；本轮仍只处理 Task 2，没有进入 Task 3+，没有 push/PR，也没有创建子智能体。

### RED

先新增最小反向测试并运行 Task 2 focused 组。首轮结果为 `7 failed, 32 passed`，失败复现公开 `registry_verified=True`、artifact declaration subset、公开 acknowledgement reference、model acknowledgement replacement/duplicate、缺少 scoped analysis record、以及缺少 retrieval provenance port。随后补充的 `required=false` declared-template 漏洞测试先以 `True` 失败，确认 readiness 会漏掉 declared artifact；source 错 hash fixture 先被修正为真正篡改持久化 record 后再验证。

### GREEN 与设计裁定

- artifact identity 不再暴露 caller-settable `registry_verified`。`RegistryArtifactRecord` 是 typed registry 数据，`RegistryGovernanceArtifactProvider` 重新核对 registry 返回对象的 id/version 与现有 canonical/source content hash，再由模块内部 capability 签发 attestation；`ResolvedArtifactIdentity`、`GovernanceArtifactSet`、`GovernanceInputs` 和 readiness context 都重新验证 attestation。declared template/scoring identity 使用 exact set，propagation rule 也必须与 graph 实际 rule pack id/version 精确绑定；缺失、额外、全零、错 registry hash 或非零伪 identity 均 fail closed。
- legacy `FmeaAnalysis` 不再作为 scope proof。`ResolvedAnalysisRecord` 携带 workspace、typed analysis、record version、canonical/source hash 和 resolver attestation；analysis query port/source/assembler/readiness 精确绑定这些字段。普通 caller 只构造 `FmeaAnalysis + workspace_id` 或伪 hash 不能进入 governance inputs。
- acknowledgement query port 改为返回 typed `GovernanceAcknowledgementRecord`，source 逐条验证 accepted status、decision hash/version、HUMAN actor、workspace/analysis、issue identity、revision/version/evidence binding，再内部签发 `HumanAcknowledgementReference`。公开 reference 无 resolver proof 不能构造；provider omission、foreign scope、错 status/hash/version 都不能清 blocker。`ReadinessIssue.acknowledgement_decision_id` 仍是唯一 revision 侧字段，未重复加入 revision contract。
- model checklist 的 authority fields（code、severity、source、evidence、acknowledgement）与安全 projection 做 canonical exact comparison；删改、替换或重复 item 拒绝，canonical reorder 可接受。ready、blockers、revision identity 仍不可改，unavailable generator 继续 offline fallback，suggestion 永远 `applied=False`。
- 新增 typed `RetrievalProvenanceQueryPort`。source 不再默认 combined/空值，而是 server lookup bounded `GovernanceRetrievalProvenance`，严格检查 scope、allowed profile、identifier、warning 安全字符和大小；`rag_only`/`graphrag_only`/hybrid provenance 原样进入 revision canonical hash，仍不决定 propagation 是否 required。
- `RepositoryGovernanceSource` 的 test 使用完整有效 providers 后再调用 `load_inputs` 验证 client rows/evidence/identity override 被签名边界拒绝；risk、graph、evidence、analysis、acknowledgement、provenance mixed scope 和 active-run provider 均有实际 source 负测。没有恢复 callback/mapping runtime seam，也没有新增 SQLite migration/repository 或 governance mutation。

### 字段/port 迁移与兼容影响

- `GovernanceRepositoryProviders` 新增必填 `retrieval: RetrievalProvenanceQueryPort`；analysis provider 必须返回 `ResolvedAnalysisRecord`，ack provider 必须返回 `GovernanceAcknowledgementRecord`，artifact provider 必须返回 registry-attested `GovernanceArtifactSet`。
- `GovernanceInputs.analysis` 从裸 `FmeaAnalysis` 迁移为 `ResolvedAnalysisRecord`，并新增必填 `retrieval_provenance`；旧的 caller profile 默认值、裸 analysis hash、公开 verified bool 和公开 ack reference 构造路径均按设计拒绝。
- `PublicationReadinessContext` 新增 server-resolved analysis/artifact authority binding；required=false 只控制 readiness 是否要求该 artifact，不能使 revision 漏掉 DomainPack 已声明的 artifact。
- 这些是 fail-closed 的 application/port contract 变更；Task 3 需要用现有 repositories/query adapters 生成上述 typed records，不应通过 transport/client 传入实体或 identity。

### 测试与工具结果

最终指定 combined focused/compatibility matrix：`179 passed in 0.78s`。

运行的 pytest matrix 为：

`tests/unit/test_fmea_revision_assembler.py`、`test_fmea_publication_readiness.py`、`test_fmea_governance_assistance.py`、`test_fmea_governance_source.py`、`test_fmea_risk_service.py`、`test_fmea_propagation_review.py`、`test_fmea_review_service.py`、`test_fmea_governance_contracts.py`、`test_fmea_review_composition.py`、`test_fmea_review_contracts.py`、`test_fmea_propagation_graph.py`、`test_fmea_risk_repository_contract.py`。

结果：`179 passed`；scoped `ruff check` passed；Task 2 改动文件 `ruff format --check`（10 files，未机械重排既有 `governance_contracts.py`）passed；`python -m compileall -q fmea_application fmea_infrastructure tests` passed；`git diff --check` passed。未运行全量 pytest。

### Concerns / Task 3/4 handoff

1. Task 3 必须让现有 analysis/review/risk/propagation/evidence/decision/run/retrieval repositories 通过 typed query wrappers 提供 resolver-attested records；不能直接构造或重新暴露旧裸对象、mapping/callback loader，也不能让 transport/client 选择 artifact/provenance/graph identity。
2. Task 3 继续使用真实 `revision_record_version` 作为 persistence precondition evidence；不得用 submission/publication version 替代，也不得把它加入 `FmeaRevision` content hash。当前 round 2 没有改 Task 1 prepared contracts 或 legacy `PublicationStatus`。
3. Task 4 可消费 `PublicationReadinessReport` 与 immutable assistance suggestion；模型/ack/UI 不能改 deterministic readiness、authority fields、ack lineage 或 revision identity。Task 2 无未解决 blocker。

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

## Fix round 3 — authority-proof and payload-safety re-review response

日期：2026-08-31

### 结果

Status: DONE_WITH_CONCERNS

实现 commit：`324dfc8e`。本轮报告随后单独提交；未 push/PR，未创建子智能体，未进入 Task 3+。

本轮只处理 authority proof、artifact/source authenticity、parent scope、propagation declaration、assistance payload safety 和 test-count truthfulness。

### RED

先添加最小反向测试，再改生产代码。首轮 fix round 3 RED：

```text
.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_revision_assembler.py::test_revision_assembler_requires_a_runtime_bound_verifier tests/unit/test_fmea_revision_assembler.py::test_legacy_module_level_resolver_issuance_helpers_are_not_importable tests/unit/test_fmea_revision_assembler.py::test_governance_inputs_rejects_missing_declared_propagation_identity_even_when_optional tests/unit/test_fmea_governance_assistance.py::test_suggestion_payload_does_not_echo_unsafe_report_identifiers -q
```

结果：`4 failed in 0.19s`。失败复现了裸 assembler 接受未验证 inputs、旧 module-level resolver helper 仍存在、声明的 propagation identity 可省略、以及 assistance payload 回显不安全 identifier；失败原因是缺实现而非测试环境故障。

随后补充的反向测试也先失败：typed registry ports 没有 source-byte 能力；registry 返回与 typed template 不一致的 source bytes 时原实现 false-green；foreign parent 可以在 source 签名前进入 inputs；registry source 被篡改后 getter 仍会返回 bytes。

### GREEN 与设计裁定

- 删除 `fmea_application.revision_assembler` 中 module-level resolver capability、signer/issuance helper 和 per-record proof constructors。`ResolvedArtifactIdentity`/`ResolvedAnalysisRecord` 是严格 typed records，authority 不由公开 `registry_verified` bool、格式合法 hash 或 caller-settable proof 表示。`HumanAcknowledgementReference` 的普通 constructor 永远拒绝；reference 只由 source 从实际查询的 `GovernanceAcknowledgementRecord` 内部解析。
- `RepositoryGovernanceSource` 在实例闭包内持有随机 HMAC secret 与 issuance nonce，只生成 opaque digest/signature proof，不暴露 module-level signer、可导入 token 或公开 production issuance API。签名覆盖完整 canonical `GovernanceInputs` body：workspace/analysis、scoped analysis record version/canonical/source hash、domain/template/scoring/propagation exact identities、rows/risk/graph/evidence packs、unresolved issues、实际 HUMAN acknowledgement decision fields、active runs、retrieval provenance 与 parent revision。验证使用 `hmac.compare_digest`；替换 inputs、artifact、analysis、ack 或 active-run state 均不能通过。
- `build_workspace_governance_runtime` 创建同一个 source，并把 source-bound verifier 接入该 runtime 的 assembler/readiness policy；裸 `RevisionAssembler` 没有 verifier 时拒绝 production inputs。transport/source boundary 仍只接受 `analysis_id`/`workspace_id`，不能传 rows、evidence、identities、ack 或治理 inputs；fixtures 通过 typed providers + runtime source 获取 attested inputs，不调用 production issuance helper。
- `GovernanceDomainPolicy` 继续 exact-typed bool/unknown-field rejection，并独立表达 required risk、propagation、template、scoring rule、propagation rule、evidence。assembler 对缺失 graph 不无条件添加 blocker；graph 存在时只记录非法/失效问题，缺失 required artifact/graph 由 readiness policy 决定。propagation declaration 在 `GovernanceArtifactSet` 和 `GovernanceInputs` 两侧均做 bidirectional exact equality，None、omission、extra identity 都 fail closed。
- registry provider 现在要求 typed registry `get_source_bytes(id, version)` port，并对 raw source 重新解析/编译后 exact compare typed registry record 的 id/version/content。具体 file registries 的 source getter 也会重新验证已存 manifest/self-hash；template manifest 增加独立 `source_hash`，不再只依赖 compiled `template_hash`。domain pack declared artifact set 与 resolved identities exact，graph rule pair 必须与 resolved propagation rule exact 绑定。
- source adapter 对 query 返回的 `ResolvedAnalysisRecord` 做 workspace/analysis/version/hash 验证；parent provider 返回值在签名前做 typed scope 校验，assembler 仍要求 request 的 parent id/hash 精确匹配。retrieval 使用 typed `RetrievalProvenanceQueryPort` 的 server lookup，保留 `rag_only`/`graphrag_only`/`hybrid` provenance，不与 propagation requirement 耦合。
- assistance generator 只收到 bounded sanitized projection；source/evidence/blocker identifiers 经过 allowlist 或稳定 redaction，private Windows/POSIX path、URI、secret-like content 不进入 generator 或最终 suggestion payload。Mapping 输出继续 exact-schema、strict bool、bounded-size、authority-field exact comparison；ack 删除/替换失败，canonical reorder 允许，unavailable generator offline fallback，`AssistanceSuggestion.applied` 恒为 `False`。

### 字段/port 迁移与兼容影响

- `DomainPackRegistry`、`ScoringRuleRegistry`、`PropagationRuleRegistry` 增加 typed `get_source_bytes(id, version)` port；具体 file registries 提供 bounded integrity-checked implementation。`FileTemplateRegistry` manifest 增加 `source_hash`，旧 manifest 缺少该字段会 fail closed，需要后续显式 re-register/migration；本轮不实现 migration，避免进入 Task 3+。
- `GovernanceRepositoryProviders` 保持按 concern 分解的 typed query ports，并新增可选 typed parent revision provider；没有恢复万能 `Callable[[], Mapping]` seam。analysis query 必须返回 `ResolvedAnalysisRecord`，ack query 必须返回持久化 `GovernanceAcknowledgementRecord`，retrieval query 必须返回 scoped `GovernanceRetrievalProvenance`。
- `GovernanceInputs` 增加 source-owned opaque attestation precondition；`RevisionAssembler`/readiness runtime 使用 source-bound verifier。`FmeaRevision` 未重复添加 acknowledgement 字段，仍只通过 `ReadinessIssue.acknowledgement_decision_id` 覆盖 canonical revision hash；Task 1 `revision_record_version` persistence evidence 仍不进入 revision content hash。
- 仅修改 Task 2 所需的 registry source verification seam、application ports/composition、Task 2 implementation/tests/fixtures；未写 SQLite migration/repository、governance service、REST/CLI/export/UI，未改变 legacy row/edge `PublicationStatus`。

### 测试与工具结果

#### 用户要求的完整 matrix（fix round 3 最终 fresh 成功运行）

命令：

```text
.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_revision_assembler.py tests/unit/test_fmea_publication_readiness.py tests/unit/test_fmea_governance_assistance.py tests/unit/test_fmea_governance_source.py tests/unit/test_fmea_risk_service.py tests/unit/test_fmea_propagation_review.py tests/unit/test_fmea_review_service.py tests/unit/test_fmea_governance_contracts.py tests/unit/test_fmea_review_composition.py tests/unit/test_fmea_review_contracts.py tests/unit/test_fmea_propagation_graph.py tests/unit/test_fmea_risk_repository_contract.py -q
```

fresh stdout：

```text
........................................................................ [ 37%]
........................................................................ [ 75%]
..............................................                           [100%]
190 passed in 0.73s
```

`179 passed` 是上一轮报告中的历史结果，当前 checkout fresh 重跑不可复现；re-review 提到的 `158` 也不是本轮最终 matrix 的 fresh 结果。round 3 新增/纳入的 reverse tests 以及 parent/registry checks 使当前完整 matrix 的唯一 fresh 记录为 `190 passed`，因此不再使用 `179`。

额外 registry/source compatibility：

```text
.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_domain_pack_registry.py tests/unit/test_fmea_propagation_rule_registry.py tests/unit/test_structured_output_file_registry.py -q
......................................................ssssss............ [ 92%]
......                                                                   [100%]
72 passed, 6 skipped in 1.23s
```

TDD 后的 Task 2 focused：`78 passed in 0.31s`；后续 parent/source integrity 反向测试通过，最终 matrix 上述 `190 passed` 已包含这些测试。

静态/编译/差异检查：

```text
.venv\Scripts\ruff.exe check <16 个 Task 2 改动代码/测试文件>
All checks passed!

.venv\Scripts\ruff.exe format --check <16 个 Task 2 改动代码/测试文件>
16 files already formatted

.venv\Scripts\python.exe -m compileall -q fmea_application fmea_infrastructure structured_output_infrastructure tests
passed

git diff --check
passed（仅 Git 的 LF/CRLF warning，无 diff whitespace error）
```

未运行全量 pytest，符合用户的范围要求。

### Concerns / Task 3/4 handoff

1. `FileTemplateRegistry` 的 source authenticity 需要独立 `source_hash`，所以旧 manifest 会 fail closed；后续如需保留旧 registry data，必须由明确的 migration/re-registration 任务处理，不能在 transport 或 readiness 中放宽兼容路径。本轮已用 compatibility tests 覆盖新布局与篡改拒绝。
2. Task 3 必须通过 runtime-bound `RepositoryGovernanceSource` 提供真实 typed providers：analysis scope attestation、registry source bytes/typed records、rows/risk/graph/evidence query、实际 ack decision records、active-run query、retrieval provenance 和 parent query；不得构造 signer/verifier、伪造 attestation 或从 transport 传入治理 state。
3. Task 3 继续从 persistence 读取真实 `revision_record_version` 作为 prepared approval/publication precondition；不得用 submission/publication record version 替代，也不得把它加入 `FmeaRevision` content hash。Task 4 只能消费 deterministic readiness report 与 immutable assistance suggestion。

Task 3 handoff：组合现有 review/risk/propagation/evidence/decision/run/retrieval repositories 为本报告列出的 typed query providers，并让 runtime source 负责签发一次完整-input attestation；不恢复 callback/mapping seam，不实现 transport。

Task 4 handoff：在 deterministic readiness 已完成且 blocker/ack identity 已验证后接入 governance lifecycle；保持模型 offline fallback、`applied=False`、ack exact binding 与 legacy `PublicationStatus` 不变。

## Fix round 4 — runtime authority and registry TOCTOU closure

日期：2026-08-31

### 结果

Status: DONE_WITH_CONCERNS

基线：`217cfea0`。本轮只处理 round 3 reviewer 账本中的 runtime authority API、完整 provenance attestation body 与 registry 单次受保护读取；未进入 Task 3+，未实现 persistence/service/transport/export/UI，未 push/PR，未创建子智能体。

### RED

中断前已先写最小反向测试并确认缺实现导致失败。authority/provenance/TOCTOU 首轮 RED 命令：

```text
.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_revision_assembler.py::test_revision_assembler_constructor_has_no_retrieval_dependency tests/unit/test_fmea_revision_assembler.py::test_revision_assembler_rejects_callable_authority_injection tests/unit/test_fmea_publication_readiness.py::test_bare_readiness_policy_fails_closed_without_runtime_authority tests/unit/test_fmea_publication_readiness.py::test_readiness_policy_rejects_callable_authority_injection tests/unit/test_fmea_governance_source.py::test_source_exposes_no_issuer_or_verifier_instance_seam tests/unit/test_fmea_governance_source.py::test_cross_runtime_attestation_cannot_be_reused tests/unit/test_fmea_governance_source.py::test_source_attestation_binds_every_retrieval_provenance_field tests/unit/test_structured_output_file_registry.py::test_get_source_bytes_reads_source_once_and_returns_verified_bytes tests/unit/test_structured_output_file_registry.py::test_get_source_bytes_does_not_reread_after_source_swap tests/unit/test_fmea_domain_pack_registry.py::test_registry_get_source_bytes_reads_source_once_and_returns_verified_bytes tests/unit/test_fmea_domain_pack_registry.py::test_registry_get_source_bytes_does_not_reread_after_source_swap -q
```

fresh-at-RED stdout：`17 failed in 0.58s`。失败分别证明 public verifier constructor 仍可注入、裸 readiness 可 ready、source 暴露 verifier/issuer seam、cross-runtime/provenance 篡改未被同一 authority 拒绝，以及 template/generic registry getter 对 source 做二次读取并可返回 swap 后 bytes。

registry adapter 的独立 RED：

```text
.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_governance_source.py::test_registry_adapter_uses_one_verified_source_load_without_get_fallback -q
```

结果：`1 failed in 0.15s`，原 provider 先调用 `get()`，随后再次读取 source。

template protected-reader 探针 RED：

```text
.venv\Scripts\python.exe -m pytest tests/unit/test_structured_output_file_registry.py::test_get_source_bytes_reads_source_once_and_returns_verified_bytes tests/unit/test_structured_output_file_registry.py::test_get_source_bytes_does_not_reread_after_source_swap -q
```

结果：`2 failed in 0.18s`，原 getter 没有复用单次受保护 source 读取。

### GREEN 与设计裁定

- `RevisionAssembler()` 与 `PublicationReadinessPolicy()` 的公共 constructor 不再接受 verifier/callable authority。裸实例保留类型/API 存在，但 assembler 直接 fail closed，readiness 只返回 `UNVERIFIED_GOVERNANCE_INPUTS`，不能让伪 identity ready。
- `RepositoryGovernanceSource` 的公共行为只有 `load_inputs(analysis_id, workspace_id)`；裸 source fail closed，实例不保存或暴露 issuer、signer、verifier callback。`build_workspace_governance_runtime` 在函数局部创建随机 HMAC secret、nonce、opaque proof class 及 sign/verify closure，并用同一 closure 绑定 runtime source、assembler、readiness policy。签名验证使用 `hmac.compare_digest`；cross-runtime proof 和 `dataclasses.replace` 后的输入均失败。
- attestation canonical body 现在显式覆盖 `GovernanceRetrievalProvenance` 的 workspace、analysis、requested/resolved profile、evidence types、source counts 与 warnings。任一字段替换都会改变 digest 并被拒绝。合法 provenance 仍进入 canonical revision；retrieval profile 不参与 propagation-required policy 判定。
- `FileTemplateRegistry` 用 `_verified_entry()` 在同一次受保护读取中取得 compiled/manifest/source，校验 path containment、parent lstat、打开后 fstat/lstat identity、文件类型、size、manifest/source hash 与重新 compile 的 typed template；`get()`/`get_source_bytes()` 分别返回同一 verified loader 的 model/同一 source bytes，不在验证后第二读。
- domain/scoring/propagation generic file registry 用 `_verified_stored_model()` 一次读取 source/body/manifest，校验 typed model、canonical body 与 raw source hash后返回 `(model, same_source_bytes)`；`get()` 与 `get_source_bytes()` 复用该 loader。source 在首次读取后被替换时只返回已验证旧 bytes 或 fail closed，semantic-equivalent raw source 也不能绕过 manifest `source_hash`。
- `RegistryGovernanceArtifactProvider` 只消费 registry 的 integrity-checked source getter，再解析并精确核对 id/version/content/source hash 与 DomainPack declarations；不恢复 `get()` 后二次读的 TOCTOU 路径。

### 字段/port 兼容影响

- `GovernanceInputs.attestation_body` 增加完整 typed retrieval provenance；`FmeaRevision`、Task 1 `revision_record_version` evidence、legacy row/edge `PublicationStatus` 均未改变。
- `GovernanceRuntime` 仍是 Task 3/4 唯一应消费的组合结果。Task 3 只应提供真实 typed repository/query/registry providers 并持有 runtime 服务；不得裸构造 assembler/policy/source，不得向 transport 暴露 factory 内 sign/verify closure 或 attestation。
- registry manifest/source integrity 继续 fail closed。旧 template manifest 缺 `source_hash` 时仍需未来明确 re-registration/migration；本轮没有添加兼容放宽或 migration。

### 最终 fresh 验证

Task 2 focused + risk/propagation/review + Task 1 governance/review composition compatibility exact matrix：

```text
.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_revision_assembler.py tests/unit/test_fmea_publication_readiness.py tests/unit/test_fmea_governance_assistance.py tests/unit/test_fmea_governance_source.py tests/unit/test_fmea_risk_service.py tests/unit/test_fmea_propagation_review.py tests/unit/test_fmea_review_service.py tests/unit/test_fmea_governance_contracts.py tests/unit/test_fmea_review_composition.py tests/unit/test_fmea_review_contracts.py tests/unit/test_fmea_propagation_graph.py tests/unit/test_fmea_risk_repository_contract.py -q
........................................................................ [ 35%]
........................................................................ [ 71%]
.........................................................                [100%]
201 passed in 0.92s
```

registry/source compatibility：

```text
.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_domain_pack_registry.py tests/unit/test_fmea_propagation_rule_registry.py tests/unit/test_structured_output_file_registry.py -q
..........................................................ssssss........ [ 85%]
............                                                             [100%]
78 passed, 6 skipped in 1.50s
```

focused authority/provenance/TOCTOU（上述 RED 同一 11 个 node ids）：`17 passed in 0.30s`。focused source/registry combined：`113 passed, 6 skipped in 1.92s`。

静态、格式、编译与差异检查：

```text
.venv\Scripts\ruff.exe check <本轮 10 个受控 Python 文件>
All checks passed!

.venv\Scripts\ruff.exe format --check <本轮 10 个受控 Python 文件>
10 files already formatted

.venv\Scripts\python.exe -m compileall -q fmea_application fmea_infrastructure structured_output_infrastructure tests/fmea_governance_fixtures.py tests/unit/test_fmea_revision_assembler.py tests/unit/test_fmea_publication_readiness.py tests/unit/test_fmea_governance_source.py tests/unit/test_fmea_domain_pack_registry.py tests/unit/test_structured_output_file_registry.py
exit 0

git diff --check
exit 0（只有 Git 的 LF/CRLF warning，无 whitespace error）
```

未运行全量 pytest。

### Concerns / Task 3/4 handoff

1. 旧 `FileTemplateRegistry` manifest 没有独立 `source_hash` 时按设计 fail closed；后续需要可信 re-registration/migration，而不是在 Task 3 transport 或 readiness 中降级校验。
2. Task 3 composition 必须只分发 factory 返回的 `GovernanceRuntime`，并由 server-owned typed providers 提供 analysis/artifact/row/risk/graph/evidence/ack/run/retrieval/parent state；不得把 factory-local authority 变成可注入 callback 或 transport API。
3. Task 4 只能消费 runtime-bound deterministic readiness 和 immutable assistance suggestion；不得让模型或客户端改变 blockers、ack、revision identity、propagation requirement 或 Task 1 persistence preconditions。

## Fix round 5 — public governance APIs fail closed

日期：2026-08-31

结果：DONE_WITH_CONCERNS

基线：`5cf8cf57818a964a42c364ba0128f1aa91198978`。本轮只修复 scoped re-review 的最后一项 Important authority bypass；未进入 Task 3+，未修改 registry、provenance HMAC 或 TOCTOU 路径，未 push/PR，未创建子智能体。

### 根因

round 4 的 `RevisionAssembler` 与 `PublicationReadinessPolicy` 仍在公开 base 的 `__slots__` 中保存可写的 `_runtime_marker`。公共 `assemble()`/`evaluate()` 只检查 marker 是否为 `None`，因此普通调用者可直接写入任意 `object()`，绕过 runtime HMAC：裸 assembler 可产生 revision，裸 policy 可返回 `ready=True`。`PublicationReadinessPolicy` 还保留了可从 base 实例直接调用的 `_evaluate_authoritative` 方法。

### RED

先添加真实行为/API 测试：尝试给裸 assembler/policy 写入任意 `_runtime_marker`，再实际调用 `assemble()`/`evaluate()`；同时断言 base 实例没有 direct authoritative entrypoint。

命令：

```text
.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_revision_assembler.py::test_caller_writable_runtime_marker_cannot_authorize_bare_assembler tests/unit/test_fmea_publication_readiness.py::test_caller_writable_runtime_marker_cannot_authorize_bare_readiness_policy tests/unit/test_fmea_publication_readiness.py::test_public_readiness_policy_has_no_direct_authoritative_entrypoint -q
```

真实失败：

```text
FFF                                                                      [100%]
3 failed in 0.17s
```

其中 assembler marker 测试 `DID NOT RAISE`，policy marker 测试观察到 `ready=True`，base API 测试观察到 `_evaluate_authoritative` 仍存在；失败来自目标行为缺失，不是测试环境错误。

### GREEN 设计

- `RevisionAssembler.__slots__` 只保留 `_clock`，`PublicationReadinessPolicy.__slots__` 只保留 `_domain_policy`；两个公开 base 的公共入口都不能由 caller-writable marker/flag/callable/secret 参数授权。assembler 对合法输入无条件抛出 `trusted governance runtime authority is required`；policy 只返回包含 `UNVERIFIED_GOVERNANCE_INPUTS` 的不可 ready 报告。
- 原 deterministic assembly/readiness 逻辑移入模块私有 core function；factory-local runtime subclass 先用 closure-private HMAC 验证同一 runtime 的 attested `GovernanceInputs`，再调用 core。删除 runtime marker 与 base `_evaluate_authoritative`，没有暴露 signer/verifier/issuer 构造参数、属性或 source method。
- 新测试继续实际调用 production object；若尝试设置 `_runtime_marker` 在新 slots 下失败，也继续验证该裸入口不能 assemble/ready。round 4 已通过的 cross-runtime、tampered-input、provenance binding、registry TOCTOU 行为未改动。

### Fresh 验证

authority-bypass nodes：

```text
...                                                                      [100%]
3 passed in 0.06s
```

Task 2 exact matrix（沿用 round 4 的 12 个测试文件）：

```text
........................................................................ [ 35%]
........................................................................ [ 70%]
............................................................             [100%]
204 passed in 0.79s
```

本轮改动文件静态/编译/差异检查：

```text
.venv\Scripts\ruff.exe check fmea_application\revision_assembler.py fmea_infrastructure\composition.py tests\unit\test_fmea_revision_assembler.py tests\unit\test_fmea_publication_readiness.py
All checks passed!

.venv\Scripts\ruff.exe format --check fmea_application\revision_assembler.py fmea_infrastructure\composition.py tests\unit\test_fmea_revision_assembler.py tests\unit\test_fmea_publication_readiness.py
4 files already formatted

.venv\Scripts\python.exe -m compileall -q fmea_application fmea_infrastructure tests\fmea_governance_fixtures.py tests\unit\test_fmea_revision_assembler.py tests\unit\test_fmea_publication_readiness.py
exit 0

git diff --check
exit 0（仅 Git 的 LF/CRLF warning，无 whitespace error）
```

未运行全量 pytest。registry/source compatibility 未重跑：本轮未触及 registry 路径，round 4 的 `78 passed, 6 skipped` 证据仍对应未修改的 registry/source 代码。

### 兼容影响与 concern

1. 公开 base assembler 仍保留类型/API 入口，但现在只能 fail closed；只有 factory 返回的 runtime-local assembler/policy 可执行 authoritative assembly/readiness。Task 3/4 必须继续消费 factory runtime，不得直接构造 base 或恢复 marker/callback seam。
2. round 4 已记录的旧 `FileTemplateRegistry` manifest 缺独立 `source_hash` 时 fail closed、需可信 re-registration/migration 的 concern unchanged；本轮没有放宽它，也没有引入新的 registry compatibility 风险。
