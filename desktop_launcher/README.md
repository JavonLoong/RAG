# PowerRAG Windows 桌面启动器

这是把现有 FastAPI 控台打成 Windows 可执行文件的打包目录。**不是 Electron**。界面仍然是系统默认浏览器里的 `frontend_app/current_console` 工作台。

## 客户怎么用

1. 打开 `desktop_launcher/dist/PowerRAG/PowerRAG.exe`（onedir 目录，不要只拷贝单独一个 exe）。
2. 若要打成压缩包再交给客户：`powershell -NoProfile -ExecutionPolicy Bypass -File desktop_launcher/pack_customer_bundle.ps1`，得到 `desktop_launcher/dist/PowerRAG-customer-windows.zip`。`dist/` 不进 git，必须随安装包另发。
3. 双击后会在本机启动控制台服务，并打开浏览器。
4. 默认地址是 `http://127.0.0.1:8000`。若 8000 已被占用，启动器会改用下一个空闲端口，并以状态窗口里的地址为准。
5. 关闭状态窗口即停止服务。向量库、上传文件、日志仍使用服务器已有的运行目录：`%LOCALAPPDATA%\PowerRAG\current_console\`（`chroma` / `uploads` / `logs`）。不会另建第二套数据库。

源码方式（未打包时）也可以直接启动：

```powershell
python desktop_launcher/power_rag_desktop.py
```

指定端口、不弹浏览器（避免和已有 8000 服务抢端口）：

```powershell
python desktop_launcher/power_rag_desktop.py --port 8010 --no-browser --no-window
```

从源码运行时如果缺少 `fastapi` / `uvicorn` 等依赖，启动器会弹出中文错误，提示先安装依赖或改用仓库 `.venv`。

## 怎么重新打包

在仓库根目录执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File desktop_launcher/build_windows_exe.ps1
```

或双击 `desktop_launcher/build_windows_exe.bat`。

精确等价命令：

```powershell
python -m PyInstaller --noconfirm --clean --workpath "$env:TEMP\power_rag_pyinstaller" --distpath "desktop_launcher\dist" "desktop_launcher\power_rag_desktop.spec"
```

产物：`desktop_launcher/dist/PowerRAG/PowerRAG.exe`（onedir，需连同旁边的 `_internal` 一起拷贝）。构建缓存放到 `%TEMP%\power_rag_pyinstaller`，避开仓库路径里的中文目录。

打包需要本机已能运行控台依赖（至少 `fastapi`、`uvicorn`）；脚本会在当前 Python 里按需安装 `pyinstaller`。完整二进制会连带 `torch` 等库，体积可能超过 1.5 GB，一次完整打包大约 15–20 分钟。

已知打包注意：

- `chromadb 0.5.3` 在 `numpy 2.x` 下顶层 `import chromadb` 会因 `np.float_` 失败，`collect_all('chromadb')` 可能告警。spec 会按包目录补收 `chromadb`。
- `collect_all` 还会带上一些可选/测试模块（如 `torch.distributed._shard.checkpoint.*`、`networkx` 测试、`tbb12.dll`），缺了一般不阻断打包。
- 不要用仓库里的 Electron 或 `npm run desktop`。

## 说明

- 启动器只负责拉起现有 `create_app`，不改控台 UI。
- 前端由 FastAPI 原样挂载，不复制第二套业务前端树；PyInstaller 仅在打包时收集 `frontend_app/current_console` 和 `configs/fmea` 等静态资源。
- 仓库里的 `electron/` 与 `npm run desktop` **不要使用**。
