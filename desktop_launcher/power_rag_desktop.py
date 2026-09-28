"""PowerRAG Windows desktop launcher.

Starts the existing FastAPI/uvicorn console and opens the system browser.
This is not Electron; the browser remains the UI.
"""

from __future__ import annotations

import argparse
import os
import socket
import sys
import threading
import time
import traceback
import webbrowser
from pathlib import Path

PREFERRED_HOST = "127.0.0.1"
PREFERRED_PORT = 8000
WINDOW_TITLE = "动力装备知识库 RAG 控制台"
MISSING_DEPS_MESSAGE = (
    "缺少运行依赖，无法启动控制台。\n\n"
    "请先安装：pip install fastapi uvicorn chromadb sentence-transformers\n"
    "或使用仓库虚拟环境：\n"
    "  .venv\\Scripts\\python.exe desktop_launcher\\power_rag_desktop.py"
)


def contains_non_ascii_path(path: str | Path) -> bool:
    return any(ord(char) > 127 for char in str(path))


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def resource_root() -> Path:
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parents[1]


def repo_root() -> Path:
    if is_frozen():
        return resource_root()
    return Path(__file__).resolve().parents[1]


def setup_sys_path() -> None:
    """Match api_server/current_console/server.py: src first, then repo root."""
    root = repo_root()
    src_dir = root / "api_server" / "current_console" / "chroma_rag_poc" / "src"
    for path in (src_dir, root):
        text = str(path)
        if path.exists() and text not in sys.path:
            sys.path.insert(0, text)


def resolve_runtime_dir(root: Path) -> Path:
    explicit = os.environ.get("POWER_RAG_RUNTIME_DIR")
    if explicit:
        return Path(explicit)

    # Frozen bundles live under an ASCII _MEIPASS path. Always reuse the same
    # LOCALAPPDATA tree the current Windows server already uses.
    if is_frozen() or (os.name == "nt" and contains_non_ascii_path(root)):
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data and not contains_non_ascii_path(local_app_data):
            return Path(local_app_data) / "PowerRAG" / "current_console"

    return root / "storage_layer" / "runtime" / "current_console"


def ensure_runtime_dir_env(root: Path) -> Path:
    runtime_dir = resolve_runtime_dir(root)
    os.environ.setdefault("POWER_RAG_RUNTIME_DIR", str(runtime_dir))
    runtime_dir.mkdir(parents=True, exist_ok=True)
    (runtime_dir / "chroma").mkdir(parents=True, exist_ok=True)
    (runtime_dir / "uploads").mkdir(parents=True, exist_ok=True)
    (runtime_dir / "logs").mkdir(parents=True, exist_ok=True)
    return runtime_dir


def resolve_frontend_dir(root: Path) -> Path:
    candidates = (
        root / "frontend_app" / "current_console",
        Path(sys.executable).resolve().parent / "frontend_app" / "current_console",
        root / "api_server" / "current_console" / "frontend",
    )
    for path in candidates:
        if (path / "index.html").is_file():
            return path
    raise FileNotFoundError(
        "未找到控台前端 frontend_app/current_console/index.html。"
        "请确认仓库完整，或重新执行打包脚本收集前端资源。"
    )


def resolve_deliverables_dir(root: Path) -> Path:
    candidate = root / "docs" / "project_deliverables"
    if candidate.exists():
        return candidate
    return root / "__no_deliverables__"


def pick_listen_port(host: str, preferred: int) -> int:
    def can_bind(port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((host, port))
            except OSError:
                return False
        return True

    if can_bind(preferred):
        return preferred
    for port in range(preferred + 1, preferred + 21):
        if can_bind(port):
            return port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def import_create_app():
    try:
        from chroma_rag_poc.api import create_app
    except ImportError as exc:
        if is_frozen():
            raise RuntimeError(
                f"打包后的程序缺少依赖模块：{exc}\n请重新运行 desktop_launcher/build_windows_exe.ps1。"
            ) from exc
        raise RuntimeError(MISSING_DEPS_MESSAGE + f"\n\n原始错误：{exc}") from exc
    return create_app


def configure_stdio() -> None:
    if sys.stdout is None:
        return
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def wait_for_server(server, worker: threading.Thread, timeout: float = 60.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if getattr(server, "started", False):
            return
        if not worker.is_alive():
            raise RuntimeError("控制台服务线程在启动完成前退出。")
        time.sleep(0.1)
    if not getattr(server, "started", False):
        raise RuntimeError("控制台服务启动超时。")


def stop_server(server, worker: threading.Thread, timeout: float = 12.0) -> None:
    server.should_exit = True
    force_exit = getattr(server, "force_exit", None)
    if force_exit is not None:
        server.force_exit = True
    worker.join(timeout=timeout)


def show_error(message: str) -> None:
    print(message, file=sys.stderr)
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(WINDOW_TITLE, message)
        root.destroy()
    except Exception:
        pass


def run_status_window(url: str, runtime_dir: Path, on_close) -> None:
    try:
        import tkinter as tk
        from tkinter import ttk
    except Exception:
        print(f"{WINDOW_TITLE} 已启动：{url}")
        print("关闭此窗口或按 Ctrl+C 将停止服务。")
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass
        on_close()
        return

    root = tk.Tk()
    root.title(WINDOW_TITLE)
    root.geometry("560x260")
    root.minsize(480, 220)

    frame = ttk.Frame(root, padding=16)
    frame.pack(fill="both", expand=True)

    ttk.Label(frame, text=WINDOW_TITLE, font=("Microsoft YaHei UI", 12, "bold")).pack(anchor="w")
    ttk.Label(frame, text="界面在系统默认浏览器中打开，本窗口仅用于保持服务运行。").pack(
        anchor="w", pady=(8, 12)
    )
    ttk.Label(frame, text=f"控台地址：{url}").pack(anchor="w")
    ttk.Label(frame, text=f"数据目录：{runtime_dir}").pack(anchor="w", pady=(4, 12))
    ttk.Label(frame, text="关闭本窗口将停止本地服务。向量库仍保存在上述数据目录。").pack(anchor="w")

    buttons = ttk.Frame(frame)
    buttons.pack(anchor="w", pady=(16, 0))
    ttk.Button(buttons, text="重新打开浏览器", command=lambda: webbrowser.open(url)).pack(
        side="left"
    )
    ttk.Button(buttons, text="停止服务", command=root.destroy).pack(side="left", padx=(8, 0))

    def handle_close() -> None:
        on_close()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", handle_close)
    root.mainloop()
    on_close()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=WINDOW_TITLE)
    parser.add_argument("--host", default=PREFERRED_HOST, help="监听地址，默认 127.0.0.1")
    parser.add_argument(
        "--port",
        type=int,
        default=PREFERRED_PORT,
        help="首选端口，被占用时自动寻找下一个空闲端口",
    )
    parser.add_argument("--no-browser", action="store_true", help="启动服务但不打开浏览器")
    parser.add_argument(
        "--no-window",
        action="store_true",
        help="不显示状态窗口（前台运行，Ctrl+C 停止）",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    configure_stdio()
    args = parse_args(argv)
    setup_sys_path()
    root = repo_root()
    runtime_dir = ensure_runtime_dir_env(root)

    try:
        frontend_dir = resolve_frontend_dir(root)
    except FileNotFoundError as exc:
        show_error(str(exc))
        return 1

    try:
        create_app = import_create_app()
    except RuntimeError as exc:
        show_error(str(exc))
        return 1

    host = args.host
    port = pick_listen_port(host, args.port)
    origin = f"http://{host}:{port}"
    persist_dir = runtime_dir / "chroma"
    upload_dir = runtime_dir / "uploads"
    log_dir = runtime_dir / "logs"

    try:
        app = create_app(
            persist_dir=persist_dir,
            upload_dir=upload_dir,
            log_dir=log_dir,
            frontend_dir=frontend_dir,
            deliverables_dir=resolve_deliverables_dir(root),
            cors_origins=(
                origin,
                f"http://localhost:{port}",
                "http://127.0.0.1:8000",
                "http://localhost:8000",
            ),
        )
    except Exception as exc:
        show_error(f"创建控制台应用失败：{exc}\n\n{traceback.format_exc()}")
        return 1

    try:
        import uvicorn
    except ImportError as exc:
        show_error(MISSING_DEPS_MESSAGE + f"\n\n原始错误：{exc}")
        return 1

    config = uvicorn.Config(app, host=host, port=port, log_level="info", access_log=False)
    server = uvicorn.Server(config)
    server.install_signal_handlers = lambda: None

    worker = threading.Thread(target=server.run, name="power-rag-uvicorn", daemon=True)
    closed = threading.Event()

    def shutdown() -> None:
        if closed.is_set():
            return
        closed.set()
        stop_server(server, worker)

    try:
        worker.start()
        wait_for_server(server, worker)
    except Exception as exc:
        shutdown()
        show_error(f"启动控制台服务失败：{exc}")
        return 1

    for line in (
        "=" * 60,
        WINDOW_TITLE,
        f"前端: {origin}",
        f"API 文档: {origin}/docs",
        f"向量库目录: {persist_dir}",
        f"上传目录: {upload_dir}",
        f"日志目录: {log_dir}",
        "=" * 60,
    ):
        print(line, flush=True)

    if not args.no_browser:
        webbrowser.open(origin)

    try:
        if args.no_window:
            worker.join()
        else:
            run_status_window(origin, runtime_dir, shutdown)
    except KeyboardInterrupt:
        pass
    finally:
        shutdown()
    return 0


setup_sys_path()


if __name__ == "__main__":
    raise SystemExit(main())
