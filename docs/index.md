# Power Equipment RAG Workspace

这份文档对应仓库根目录的工作区结构，而不是单一模板包。

## 现在的仓库定位

仓库被整理成三层：

1. `apps/`：真正可运行、可演示的应用
2. `src/`：保留在根仓的原型代码
3. `archive/`：历史实验与旧材料

## 推荐入口

日常开发、组会演示、界面联调都优先使用：

- `apps/jiwenlong-rag-console/`

它包含：

- FastAPI 后端
- 极简前端控制台
- Chroma 入库与检索
- benchmark 与统计接口

## 根仓原型包

`src/power_rag_pipeline/` 保留了一条更轻量的原型实现，用于记录早期的：

- Label Studio JSON 解析
- 文本清洗
- 分块
- 向量化
- 混合检索

它不是当前主应用入口，但仍然适合作为思路参考和最小实验基线。

## 归档区

`archive/legacy-code/` 中存放：

- `plant-graph-rag/`：历史 gitlink / 子仓快照
- `guo-demo/`：早期个人实验页面与脚本

这些内容默认不作为当前主线维护目标。
