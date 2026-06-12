# Task for Codex

【首要任务：P0 级稳定性与安全修复】

请你专门处理以下几个针对 api_server 核心入口的 P0 级别问题：
1. 移除或隔离 pi.py 底部直接创建 pp = create_app() 的导入期副作用，防止多次重复挂载。
2. 修复找不到 FRONTEND_DIR 时直接导致程序抛出 StopIteration 奔溃的问题，改为优雅降级（在 / 路由下返回 404 即可）。
3. 限制高风险接口的安全边界（如 CORS 限制，或收紧本地数据处理的目录白名单）。

请直接在代码中修改并测试，完成后在当前目录输出一个 .success 文件或者打印完成日志。

---
*Note: This task was automatically dispatched by the Collaborative AI Brain.*
