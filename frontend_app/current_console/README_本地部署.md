# 动力装备知识库控制台 - 本地部署说明

## 快速启动

**双击 `start.bat` 即可**（自动启动本地服务器并打开浏览器）

## 文件结构

```
current_console/
├── index.html       ← 主页面
├── start.bat        ← 一键启动脚本
├── libs/            ← 依赖库（离线可用）
│   ├── d3.min.js
│   ├── iconify-icon.min.js
│   ├── jszip.min.js
│   ├── mammoth.browser.min.js
│   ├── marked.min.js
│   ├── papaparse.min.js
│   ├── pdf.min.js
│   ├── pdf.worker.min.js
│   ├── purify.min.js
│   ├── sql-wasm.js
│   └── sql-wasm.wasm
└── README_本地部署.md  ← 本文件
```

## 注意事项

1. **不要直接双击 index.html 打开** — 浏览器的 `file://` 协议会导致部分功能不可用（如 WASM 向量库导出）
2. **请使用 start.bat 启动** — 它会启动一个本地 HTTP 服务器（优先 Python，没有则用 PowerShell）
3. **离线环境完全可用** — 所有依赖库已下载到 `libs/` 文件夹，无需联网
4. **服务地址** — 默认 http://localhost:8080
