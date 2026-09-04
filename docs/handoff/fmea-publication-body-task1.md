# FMEA 正文发布：Task 1 交接

日期：2026-09-04。分支：`feat/interface-output-v1`。

## 结论

Task 1「正文投影与版本绑定契约」已完成并通过任务级审查及两轮定点复核。Task 2–5 未开始。当前真实发布仍沿用 Phase 4 的身份摘要；本次没有把 Word/Excel 正式正文报告描述为已接通。

实现提交：`75d1cb98`、`c4cdfc4b`、`7bd0c69b`。未推送、未创建 PR。

## 本次实际增加

- `fmea_application/publication_body.py`：行、评分、传播、证据、审核五部分的确定性公开投影；验证原生版本/哈希/证据引用；保留扩展字段类型和未知状态；输出深度不可变。
- `fmea_infrastructure/composition.py`：运行时独占正文入口，先验证既有 HMAC 来源证明，再从服务端配置的复核来源查询记录。基础来源或缺少配置时拒绝，不接受调用方提供的复核记录。
- `fmea_application/ports.py`：可选的 `GovernancePublicationReviewQueryPort`，为 Task 2 的真实 SQLite 适配保留接口；不改外部请求或 EvidencePack 合同。
- `fmea_application/snapshot_contracts.py`：识别 `graphrag.fmea.body.v1` 标记并校验五部分结构与引用；旧无标记快照保持兼容；顶层维持 10,000 项预算，嵌套维持 500 项限制。

支持入口为 `source.build_publication_body(revision, inputs)`，不是独立可由客户端传入审核结论的函数。内部 `_project_publication_body` 只是纯投影，不提供权限。

证据先验证原生身份，再公开为安全定位。`page:N#span:N` 转为 page/span 对象；canonical JSON locator 经成员安全检查后公开。不使用包装或改名方式绕过 URL/私有路径限制。同一证据可出现在多个包中，但相同 ID 的冲突内容、同包重复仍拒绝。

每行要求一个精确版本对应的已接受人工决定。传播边必须已接受，但发布前正常的 UNPUBLISHED 状态不会被错误改为 PUBLISHED。评分确认人的内部 actor ID 不进入公开评分正文，内部审计仍保留。

## 验证与复审

主代理在最终代码提交 `7bd0c69b` 上运行：

```powershell
.venv/Scripts/python.exe -m pytest tests/unit/test_fmea_publication_body.py tests/unit/test_fmea_snapshot_contracts.py tests/unit/test_fmea_governance_source.py -q
```

结果：**100 passed in 0.79s**。范围 Ruff：All checks passed；`git diff d1040fcf..HEAD --check` 通过。

实现遵循测试先失败再修复：初版缺少正文模块/标记校验产生 RED；round 1 的缺口复现为 16 failed、79 passed，修复后 96 passed；round 2 的两项回归复现为 2 failed、38 passed，修复后快照 40 passed。它们是不同阶段证据，不与最终 100 项相加。

独立 Luna xhigh 复审及原实现者修复，关闭：

1. 调用方可伪造复核记录；
2. 已确认图中仍含未接受边；
3. 正文标记/五部分完整性校验不足；
4. 重复或非接受的复核决定；
5. 评分确认人内部 ID 进入公开正文；
6. 修复后误拒绝跨包共享同一引用；
7. 修复后错误限制顶层容量为 500。

最终 round 2 结论：**PASS / CLOSED，无新增 Critical/Important**。这是对已有发现和修复差异的复核，不是整条产品链路的新一轮验收。早期审查的测试耦合/异常捕获建议不属于新增功能；不得据此声称全仓静态类型检查通过。探索性 mypy 曾在依赖树中报错，本轮不把它作为通过门禁。

## 实施中调整

1. 运行时入口代替计划初稿中的独立函数：既有 HMAC 验证器是运行时私有闭包，应用层不能凭 proof 的外观判断可信。代价是小范围内部入口/配置适配。
2. 将最小复核查询端口提前到 Task 1：否则调用方传入的记录不受来源证明保护。真实 SQLite 解析仍由 Task 2 完成。代价是内部 port 与测试夹具的调整，不涉及迁移或外部 API。

## Task 2 起点

按 [实施计划](../superpowers/plans/2026-09-04-fmea-publication-body.md) 接入真实发布：

- 从 `review_decisions` 与绑定的 `audit_events` 解析人工决定、角色、时间和结果行哈希；不能由 accepted 状态推造历史。
- 配置 `publication_reviews` provider；在治理服务中调用新的运行时正文入口，保存标记及完整正文。
- 发布事务内重查可变源版本/内容，防止读取与提交间的变化；不得只验证自洽的导出哈希链。
- 保留旧发布、幂等回放、撤销/替代语义和失败回滚。

本次未运行新的真实资料/DeepSeek 测试、三格式正文渲染、浏览器或万行 Office 压测；这些不能用 Task 1 的单元测试替代。
