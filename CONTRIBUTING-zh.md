# 贡献说明

这个仓库现在是一个工作区，不再是单一模板项目。

## 改动前先判断归属

请先确认你的改动应该放在哪一层：

- `apps/jiwenlong-rag-console/`
- `src/power_rag_pipeline/`
- `docs/`
- `archive/` 仅用于归档和保留历史材料

## 本地环境

```bash
uv sync
uv run pre-commit install
```

## 常用命令

```bash
make check
make test
make docs-test
```

## 约定

- 面向演示和继续开发的功能，优先进入 `apps/`
- 根仓 `src/` 只保留原型代码或可复用的轻量逻辑
- `archive/` 默认只读参考，不继续堆新功能
- 改目录结构时，必须同步更新 `README.md` 和 `docs/repository-layout.md`
- 改可运行应用时，至少验证一次 `http://localhost:8000/api/health`
