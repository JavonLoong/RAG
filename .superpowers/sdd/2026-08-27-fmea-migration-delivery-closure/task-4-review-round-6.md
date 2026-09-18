# Phase 4 Task 4 Round 6 独立终审报告

日期：2026-09-03
工作区：`C:\Users\35551\Desktop\RAG\.worktrees\interface-output-v1`
审查 HEAD：`ec23bb3419029029d1e5590328526ad883827f19`
重点范围：`5161d12e..ec23bb34`；Task4 回溯：`82ffa1f4..ec23bb34`

## 结论

**PASS**

在 full spec 所要求的 server-owned filesystem trust boundary 下，本轮没有发现 Critical 或仍阻断 Task4 的 Important。Round5 的 I7 completion-return 状态泄漏、caller-supplied exact snapshot 未先重建，以及 I8 POSIX lease parent/path TOCTOU 均已闭合。Windows 上两个真实 POSIX multiprocessing `flock` 测试和一个真实 symlink privilege 测试按设计跳过；它们列为单独的 Linux CI residual，不伪造为本机 PASS。

同一服务 effective UID 已经能够写入/替换受保护目录的恶意 OS 进程不纳入本模块威胁模型。这个边界合理：代码无法用普通 DAC、`O_NOFOLLOW` 或 dirfd 阻止同 UID 进程直接改写其可写对象；实现改为强制 root/workspace/`.locks` 为服务 UID 所有且 group/other 不可写，并把该前提写入 `artifact_store.py` 模块契约。它不构成当前声明模型内的开放 finding。

## 审查输入

已完整读取：

- Task4 总计划：`docs/superpowers/plans/2026-08-27-fmea-migration-delivery-closure.md`
- Task4 brief：`.superpowers/sdd/2026-08-27-fmea-migration-delivery-closure/task-4-brief.md`
- full spec：`docs/superpowers/specs/2026-08-27-full-fmea-modular-product-design.md`
- Round5 report：`.superpowers/sdd/2026-08-27-fmea-migration-delivery-closure/task-4-review-round-5.md`
- Round6 package：`.superpowers/sdd/2026-08-27-fmea-migration-delivery-closure/task-4-review-package-round-6.md`
- 历史 Round2/3/4 的 I6-I9 disposition，以及当前 `export_service.py`、`artifact_store.py`、`delivery_repository_sqlite.py`、delivery contracts/ports、narrative generator 和相关测试。

## Fresh verification

| 检查 | 命令/范围 | 结果 |
| --- | --- | --- |
| Task4 exact | `tests/unit/test_fmea_export_json.py tests/unit/test_fmea_export_narrative.py tests/unit/test_fmea_artifact_store.py tests/integration/test_fmea_export_runs.py tests/unit/test_fmea_snapshot_contracts.py` | **178 passed, 3 skipped**；181 collected，exit 0 |
| Task3/governance | `tests/integration/test_fmea_delivery_sqlite.py tests/regression/test_fmea_migration_rollback.py tests/integration/test_fmea_governance_sqlite.py` | **138 passed**，exit 0 |
| Round5 I7 probes | export-run malformed/exact/non-exact/committed/latest-reconciliation selection | **10 passed** |
| fake POSIX dirfd/flock probes | artifact-store `-k "posix and not process"` | **21 passed**；未把 fake 当作 kernel/process 证据 |
| Python Ruff | `ruff check` 覆盖 `82ffa1f4..HEAD` 的 9 个 Python 文件 | **All checks passed** |
| Ruff format | 同上 9 个文件 | **9 files already formatted** |
| diff check | `git diff --check 82ffa1f4..HEAD` | **通过** |
| inline completion probe | 首次 publish 与 latest reconciliation 的 committed non-exact completion return | 均 `SUCCEEDED`；latest 路径 exporter 不重渲染 |

审查前后 worktree 均无未提交产品/测试改动；未提交、未 push、未创建 PR。此报告路径由 `.superpowers/sdd/.gitignore` 忽略。

## Disposition

### Critical

无。

### Important

#### I6 cancellation / replay / terminal race — PASS

`fmea_application/delivery_contracts.py:36-42` 保留六种合法 run 状态及生命周期形状。`fmea_application/export_service.py:1150-1208,1299-1346` 使用公开的 cancellation transition，`start()` 能处理 `cancelling`/`cancelled` replay；repository 的 `request_export_cancellation()`、`complete_export_cancellation()` 和 `complete_export()` 使用事务并保持 terminal protection（`fmea_infrastructure/delivery_repository_sqlite.py:1658-1779,1889-2000`）。Task3/governance 的 138 项回归以及 Task4 exact 均通过；未发现正常应用路径依赖直接 SQL。

#### I7 completion exact/non-exact return — PASS

`_complete_export_run()` 已把 completion adapter 调用、结果重建、binding 校验和 completed-chain/store verification 放入同一 recovery boundary（`fmea_application/export_service.py:1259-1297`）。

- durable completion 已提交但 provider 返回被恶意 exact mutation 或 non-exact object：`_cooperative_state()` 重新读取 durable run，`SUCCEEDED` 只有在完整 delivery chain 和物理 artifact/latest 重新验证后才返回。
- durable completion 未提交或 completion result 无法重建：`_persist_failure()` 可靠写入 `FAILED`，不留下 `RUNNING`。
- 首次 publish 与已有 latest reconciliation 两条路径都经过该 boundary（`export_service.py:1446-1496,1509-1550`）。

Round6 新增 exact tests 及 Round5 I7 定向选择共 10 项通过；额外 inline probe 也分别覆盖了 committed non-exact first-publish 和 committed non-exact latest-reconciliation。

#### I7 caller-supplied exact snapshot / DTO and error boundary — PASS

`_rebuild_snapshot()` 在任何 workspace comparison、projection 或 snapshot-hash 使用前，逐字段复制 exact `NormalizedFmeaSnapshot` 为 plain bounded JSON-compatible values（`fmea_application/export_service.py:245-273`）；`suggest_narrative()` 入口立即使用它，失败固定为 `FMEA_EXPORT_NARRATIVE_REQUEST_INVALID`（`export_service.py:1555-1580`）。nested row、workspace、snapshot hash 的 `eq/str/hash/len` adversarial cases 均固定错误且不泄漏。

同一原则也覆盖 provider result：`_boundary_call()`、`_narrative_boundary_call()` 和 `_rebuild_run/_rebuild_manifest/_rebuild_artifact` 不信任 adapter 的异常字段或 exact frozen DTO 的后续可变字段（`export_service.py:129-184,341-411`）。path-free `VerifiedExportArtifact` 的完整 workspace/run/artifact/filename/manifest/payload binding 在 `_verify_store()` 中重新验证（`export_service.py:1063-1074`）。

#### I8 POSIX lease trust model and parent replacement — PASS（同 UID compromise out of scope）

`WorkspaceArtifactStore` 初始化和 lease acquisition 对 root、workspace、`.locks` 逐层做 `O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC` dirfd traversal，并验证受信目录的 service effective UID ownership 与 `st_mode & 0o022 == 0`（`fmea_infrastructure/artifact_store.py:322-324,1023-1100`）。

Lease 使用已验证 `.locks` descriptor 上的 `os.open(lease_name, ..., dir_fd=locks_descriptor)`，不是可被替换祖先影响的绝对 pathname（`artifact_store.py:1144-1195,1220-1276`）。每次打开、加锁、写诊断后都以 `fstat(fd)` 与同一 locks dirfd 下的 `stat(..., follow_symlinks=False)` 比较 regular-file identity；所有 lease/locks descriptors 在异常、竞争返回、fault 和 release 路径关闭。POSIX release 只 `flock(LOCK_UN)` 后 close，不 unlink/rename lease（`artifact_store.py:1291-1302`）。

fake parent replacement、symlink/reparse、foreign owner、group/other writable、descriptor leak 和 lease mutation probes 通过；真实 parent replacement race 不再能把 lease 导向新 `.locks` 或 outside 目录。根/工作区/`.locks` 的非服务 UID 或 group/other 写权限被固定拒绝。

#### I8 persistent flock crash recovery / compatibility — PASS（Linux kernel evidence residual）

Lease 是 persistent regular file；旧的 directory reservation 不作为 POSIX lease，orphan `.artifact-tmp-*` 不参与 reservation，也不会阻塞 retry。flock contention 有 monotonic deadline 和 bounded polling；没有 `fcntl.flock` 时固定返回 retryable `FMEA_ARTIFACT_BUSY`，不回退到不安全的 pathname lock。已有 final/latest 时能重放；fault 后 lease fd close，下一次同内容 publish 可继续收敛。

对应 fake dirfd/flock 选择 21 项通过，Task4 exact 也通过。

#### I9 narrative bounded projection / evidence closure — PASS

`_build_bounded_context()` 先尝试保留一个完整 row，再按既定顺序加入完整 evidence/unresolved/remaining rows；每个候选都以完整 canonical JSON 同时检查 Unicode 字符数与 UTF-8 bytes，未切片 JSON 或多字节文本。unresolved 只有在其 evidence refs 已入选时才加入（`fmea_infrastructure/export_narrative_generator.py:596-661`）。现有 I9 large multibyte、tiny-budget quota、omitted evidence reference 和 narrative no-mutation tests 均通过，未见回退。

#### M-R4-1 same-workspace cross-actor run/key conflict — PASS

同 workspace 不同 actor 复用相同 run/key 的路径现在识别为非 retryable `FMEA_EXPORT_IDEMPOTENCY_CONFLICT`；对应 integration regression 在 Task4 exact 中通过，未见跨 workspace 读取或权限绕过。

### Minor

无开放 Minor。Round4 的 M-R4-1 已在本轮复核中关闭；Linux-only test execution 作为 residual validation 单列，不升级为 finding。

## Linux CI residual validation

当前主机为 Windows，因此 exact suite 中以下两个真实 POSIX multiprocessing tests 按 `skipif(os.name == "nt")` 跳过：

- `test_posix_process_lease_is_bounded_busy_then_recovers_after_close`
- `test_posix_process_exit_releases_lease_to_waiting_competitor`

另有一个真实 symlink 创建测试因 Windows privilege 被跳过；Windows synthetic reparse、dirfd/fake-flock 和 parent-replacement probes 已执行，但不能替代 Linux kernel/process 证据。Linux CI 应运行同一 Task4 exact suite，使上述两个真实 `fcntl.flock` tests 实际执行，并保留对正常 close、abrupt process exit、bounded busy、same-content convergence、different-content conflict、old-directory compatibility 和 orphan-temp nonblocking 的真实验证。当前没有把这些 Windows skips 宣称为 PASS，也没有因此提出代码变更。
