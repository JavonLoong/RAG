"""
RAG 控制台统一入口 — 启动即用
- 自动启动 OCR Server (RapidOCR + Tesseract)
- 自动托管 index.html (HTTP 服务, 避免 file:// 限制)
- 自动打开浏览器
- 支持开机自启注册/取消
"""
import sys, os, io, json, time, threading, webbrowser, argparse, subprocess
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler
from socketserver import ThreadingMixIn

# Fix Windows encoding
for s in (sys.stdout, sys.stderr):
    if hasattr(s, 'reconfigure'):
        try: s.reconfigure(encoding='utf-8', errors='replace')
        except: pass

SCRIPT_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = SCRIPT_DIR  # index.html is here
OCR_SERVER = SCRIPT_DIR / "ocr_server.py"
WEB_PORT = 8766
OCR_PORT = 8765
STARTUP_NAME = "RAG_OCR_Console"


# ═══════════════════════════════════════════════
#  开机自启 — Windows 注册表
# ═══════════════════════════════════════════════

def _get_startup_cmd():
    """构造开机自启命令"""
    python = sys.executable
    script = str(Path(__file__).resolve())
    # 使用 pythonw.exe 静默启动（无窗口）
    pythonw = python.replace("python.exe", "pythonw.exe")
    if Path(pythonw).exists():
        return f'"{pythonw}" "{script}" --silent'
    return f'"{python}" "{script}" --silent'


def register_startup():
    """注册到 Windows 开机自启"""
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE
        )
        cmd = _get_startup_cmd()
        winreg.SetValueEx(key, STARTUP_NAME, 0, winreg.REG_SZ, cmd)
        winreg.CloseKey(key)
        print(f"✅ 已注册开机自启: {STARTUP_NAME}")
        print(f"   命令: {cmd}")
        return True
    except Exception as e:
        print(f"❌ 注册失败: {e}")
        return False


def unregister_startup():
    """取消开机自启"""
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE
        )
        try:
            winreg.DeleteValue(key, STARTUP_NAME)
            print(f"✅ 已取消开机自启: {STARTUP_NAME}")
        except FileNotFoundError:
            print(f"ℹ️ 未找到自启项: {STARTUP_NAME}")
        winreg.CloseKey(key)
        return True
    except Exception as e:
        print(f"❌ 取消失败: {e}")
        return False


def check_startup():
    """检查是否已注册开机自启"""
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_READ
        )
        try:
            val, _ = winreg.QueryValueEx(key, STARTUP_NAME)
            winreg.CloseKey(key)
            return val
        except FileNotFoundError:
            winreg.CloseKey(key)
            return None
    except:
        return None


# ═══════════════════════════════════════════════
#  OCR Server 子进程管理
# ═══════════════════════════════════════════════

_ocr_process = None

def _is_ocr_running():
    """检查 OCR Server 是否已在运行"""
    import urllib.request
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{OCR_PORT}/health", method="GET")
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = json.loads(resp.read())
            return data.get("status") == "ok"
    except:
        return False


def start_ocr_server(silent=False):
    """启动 OCR Server 子进程"""
    global _ocr_process

    if _is_ocr_running():
        if not silent:
            print(f"  ✅ OCR 服务器已在运行 (port {OCR_PORT})")
        return True

    if not OCR_SERVER.exists():
        if not silent:
            print(f"  ❌ 找不到 ocr_server.py: {OCR_SERVER}")
        return False

    python = sys.executable
    if not silent:
        print(f"  🚀 启动 OCR 服务器...")

    # 静默模式: CREATE_NO_WINDOW; 正常模式: 新窗口
    creation_flags = 0
    if sys.platform == "win32":
        if silent:
            creation_flags = subprocess.CREATE_NO_WINDOW
        else:
            creation_flags = subprocess.CREATE_NEW_CONSOLE

    _ocr_process = subprocess.Popen(
        [python, str(OCR_SERVER)],
        cwd=str(SCRIPT_DIR),
        stdout=subprocess.DEVNULL if silent else None,
        stderr=subprocess.DEVNULL if silent else None,
        creationflags=creation_flags,
    )

    # 等待就绪 (最多 30 秒)
    for i in range(30):
        time.sleep(1)
        if _is_ocr_running():
            if not silent:
                print(f"  ✅ OCR 服务器已就绪 ({i+1}s)")
            return True

    if not silent:
        print(f"  ⚠️ OCR 服务器启动超时，继续运行...")
    return False


# ═══════════════════════════════════════════════
#  Web 文件服务器 (托管 index.html)
# ═══════════════════════════════════════════════

class QuietHandler(SimpleHTTPRequestHandler):
    """静默 HTTP 文件服务器"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(FRONTEND_DIR), **kwargs)

    def log_message(self, format, *args):
        pass  # 静默, 不打印请求日志

    def end_headers(self):
        # 添加 CORS 和缓存头
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def start_web_server(silent=False):
    """启动前端文件服务器"""
    try:
        server = ThreadedHTTPServer(("127.0.0.1", WEB_PORT), QuietHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        if not silent:
            print(f"  ✅ 前端服务器已启动: http://127.0.0.1:{WEB_PORT}")
        return server
    except OSError as e:
        if "10048" in str(e) or "Address already in use" in str(e):
            if not silent:
                print(f"  ✅ 前端服务器已在运行 (port {WEB_PORT})")
            return None
        raise


# ═══════════════════════════════════════════════
#  主入口
# ═══════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="RAG 控制台一键启动")
    parser.add_argument("--silent", action="store_true", help="静默模式 (无窗口, 用于开机自启)")
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    parser.add_argument("--register", action="store_true", help="注册开机自启")
    parser.add_argument("--unregister", action="store_true", help="取消开机自启")
    parser.add_argument("--status", action="store_true", help="检查状态")
    args = parser.parse_args()

    # 注册/取消开机自启
    if args.register:
        register_startup()
        return
    if args.unregister:
        unregister_startup()
        return
    if args.status:
        startup = check_startup()
        ocr = _is_ocr_running()
        print(f"开机自启: {'✅ ' + startup if startup else '❌ 未注册'}")
        print(f"OCR服务器: {'✅ 运行中' if ocr else '❌ 未运行'}")
        print(f"前端地址: http://127.0.0.1:{WEB_PORT}")
        return

    if not args.silent:
        print()
        print("  ╔══════════════════════════════════════╗")
        print("  ║  RAG 知识库控制台 — 自动启动          ║")
        print("  ╚══════════════════════════════════════╝")
        print()

    # 1. 启动 OCR Server
    if not args.silent:
        print("[1/3] OCR 服务器")
    start_ocr_server(silent=args.silent)

    # 2. 启动 Web Server
    if not args.silent:
        print("[2/3] 前端服务器")
    web_server = start_web_server(silent=args.silent)

    # 3. 打开浏览器
    if not args.no_browser and not args.silent:
        print("[3/3] 打开浏览器")
        url = f"http://127.0.0.1:{WEB_PORT}/index.html"
        webbrowser.open(url)
        print(f"  ✅ 已打开: {url}")

    if not args.silent:
        startup = check_startup()
        print()
        print("  ════════════════════════════════════════")
        print(f"  前端:       http://127.0.0.1:{WEB_PORT}")
        print(f"  OCR服务器:  http://127.0.0.1:{OCR_PORT}")
        print(f"  开机自启:   {'✅ 已注册' if startup else '❌ 未注册 (运行 --register 注册)'}")
        print("  ════════════════════════════════════════")
        print()
        print("  按 Ctrl+C 退出...")
        print()

    # 保持运行
    try:
        while True:
            time.sleep(60)
            # 定期检查 OCR Server 是否还活着, 挂了就重启
            if not _is_ocr_running():
                if not args.silent:
                    print("  ⚠️ OCR 服务器掉线, 正在重启...")
                start_ocr_server(silent=args.silent)
    except KeyboardInterrupt:
        if not args.silent:
            print("\n  [停止] 正在关闭...")
        if _ocr_process and _ocr_process.poll() is None:
            _ocr_process.terminate()
        if web_server:
            web_server.shutdown()


if __name__ == "__main__":
    main()
