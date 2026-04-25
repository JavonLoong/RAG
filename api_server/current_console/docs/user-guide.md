# 使用说明

## 最短路径

1. 进入 `apps/jiwenlong-rag-console/`
2. 双击 `start_local.bat`
3. 浏览器打开 `http://localhost:8000`

## 页面使用顺序

1. 在“数据接入”页上传 `json/pdf/docx/txt/md/csv/tsv/log`
2. 点击“处理并入库”
3. 在“系统总览”查看统计信息
4. 在“语义检索”输入关键词验证效果
5. 在“性能基准”执行 benchmark

## 组会演示建议

推荐顺序：

1. 先展示总览页，说明当前知识库规模
2. 上传一批样例文件并点击入库
3. 展示 token、存储空间、集合数量变化
4. 输入一个设备故障词做检索
5. 最后跑一轮 benchmark 展示插入和检索速度

## 常见问题

### 双击后没启动

优先检查：

- 机器上是否有 Python 3.11
- 是否已经安装 `fastapi`、`uvicorn`、`chromadb`
- 浏览器里访问的是不是 `http://localhost:8000`

### 页面能打开但不能上传

通常是后端没起来，或者你打开的是脱离仓库的单独 `index.html` 副本。优先使用 `http://localhost:8000`。

### 想重置数据库

删除 `apps/jiwenlong-rag-console/data/chroma/` 里的本地内容后重新启动即可。
