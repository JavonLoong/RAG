# Current Console 模块边界

- `console-app.js`：兼容既有控制台的应用编排与领域页面控制器。
- `delivery-api.js`：`/api/delivery` API client 与项目头注入。
- `delivery-state.js`：可信交付页状态模型。
- `delivery-components.js`：状态标记与列表行共享组件。
- `pages/`：各独立页面的注册模块；页面切换通过 `powerrag:page-enter` 事件解耦。其中 `acceptance-page.js` 提供 PRD 验收工作队列、证据上传、模板编辑、SHA-256 乐观锁与验收包生成界面。
- `../styles/console.css`：控制台样式，已从 HTML 单文件迁出。

所有脚本和样式均由相对路径加载；`libs/` 仍作为 Electron/本地服务离线依赖源。
