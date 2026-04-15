# RAG Industrial Console

这是一个可直接部署到 GitHub Pages 的静态网站版本，用来展示并运行动力装备知识库 RAG 控制台。

## 在线地址

启用 GitHub Pages 后，项目站点地址通常会是：

- `https://javonloong.github.io/RAG/`

## 特性

- 纯白背景 + Klein Blue 点缀的工业级 Bento 控制台
- 系统总览 / 数据接入 / 语义检索 / 系统结构 / 性能基准 五个页面
- GitHub Pages 静态模式下可直接运行
- 用户拖入的文件只在浏览器本地解析、分块、检索，不会写入你的 GitHub 仓库
- 如果将来接入真实后端接口，也可以继续复用这套前端结构

## 文件说明

- `index.html`：页面结构
- `styles.css`：视觉样式
- `app.js`：前端交互与浏览器本地分析逻辑

## 启用 GitHub Pages

1. 进入仓库 `Settings`
2. 打开 `Pages`
3. Source 选择 `Deploy from a branch`
4. Branch 选择 `main` / `/ (root)`
5. 保存后等待几分钟

## 数据安全说明

- 拖入网站的文件只在访问者自己的浏览器里处理
- 不会写回 GitHub 仓库
- 不会在你的项目目录里自动生成新文件
- 关闭页面后，本次会话内的数据索引也会一起消失

如果之后你希望把“多人共享同一知识库 / 长期保存索引 / 远程协作检索”也接上，再单独部署后端即可。
