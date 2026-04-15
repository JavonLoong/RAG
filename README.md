# RAG Industrial Console

这是一个可直接部署到 GitHub Pages 的静态网站版本，用来展示动力装备知识库 RAG 控制台。

## 在线地址

启用 GitHub Pages 后，项目站点地址通常会是：

- `https://javonloong.github.io/RAG/`

## 特性

- 纯白背景 + Klein Blue 点缀的工业级 Bento 控制台
- 系统总览 / 数据接入 / 语义检索 / 系统结构 / 性能基准 五个页面
- GitHub Pages 静态模式下可直接运行
- 如果将来接入真实后端接口，也可以继续复用这套前端结构

## 文件说明

- `index.html`：页面结构
- `styles.css`：视觉样式
- `app.js`：前端交互与静态演示逻辑

## 启用 GitHub Pages

1. 进入仓库 `Settings`
2. 打开 `Pages`
3. Source 选择 `Deploy from a branch`
4. Branch 选择 `main` / `/ (root)`
5. 保存后等待几分钟

如果之后你希望把“真实上传 / 真检索 / 真 benchmark”也接上，需要把 FastAPI 后端单独部署到云服务器，再把前端接口地址指过去。
