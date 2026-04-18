# Repository Layout

## Top-level layout

```text
.
├─ apps/
│  └─ jiwenlong-rag-console/
├─ src/
│  └─ power_rag_pipeline/
├─ tests/
├─ docs/
│  └─ diagrams/
├─ archive/
│  └─ legacy-code/
├─ pyproject.toml
├─ Dockerfile
├─ Makefile
└─ .gitlab-ci.yml
```

## What each area is for

### `apps/`

放当前真正要继续推进的应用。

当前只有一个主应用：

- `jiwenlong-rag-console`

### `src/`

放根仓仍然保留的 Python 原型包。

当前包名：

- `power_rag_pipeline`

### `tests/`

放根仓原型包的测试。

### `docs/`

放文档和结构图。逻辑结构图已经从根目录移到：

- `docs/diagrams/logic-structure.html`

### `archive/`

放历史内容，避免继续污染根目录视图。

当前包括：

- `legacy-code/plant-graph-rag`
- `legacy-code/guo-demo`

## Notes

- 根仓不再使用旧的 `02_代码` 作为顶层目录
- 文档、容器、CI、测试配置都已同步到新结构
