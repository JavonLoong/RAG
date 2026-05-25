"""
高性能并发 OCR 服务器 v2
使用 RapidOCR (PaddleOCR ONNX) + 多线程并发处理

核心优化: PDF 上传一次缓存，后续请求只发 session ID
- POST /ocr/pdf/upload → 缓存 PDF，返回 session_id + total_pages
- POST /ocr/pdf/batch?session=xxx&pages=1,2,3 → 并发 OCR（不再重传 PDF）
- 自动清理超过 10 分钟的 session
"""
import sys
import os
import io
import json
import base64
import time
import uuid
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from urllib.parse import urlparse, parse_qs
from concurrent.futures import ThreadPoolExecutor, as_completed

# ─── 配置 ───
PORT = 8765
HOST = "127.0.0.1"
CPU_COUNT = os.cpu_count() or 4
MAX_OCR_WORKERS = max(2, min(CPU_COUNT // 2, 12))
SESSION_TIMEOUT = 600  # 10 minutes

# ─── 初始化 OCR 引擎 ───
print(f"系统 CPU 核心数: {CPU_COUNT}")
print(f"OCR 并发线程数: {MAX_OCR_WORKERS}")
print("正在加载 OCR 引擎 (RapidOCR)...")

OCR_ENGINE_CLASS = None
OCR_ENGINE_NAME = None

try:
    from rapidocr_onnxruntime import RapidOCR
    OCR_ENGINE_CLASS = RapidOCR
    OCR_ENGINE_NAME = "RapidOCR (PaddleOCR ONNX)"
    test_engine = RapidOCR()
    print(f"✅ {OCR_ENGINE_NAME} 加载成功")
except ImportError:
    print("❌ RapidOCR 未安装！pip install rapidocr-onnxruntime")
    sys.exit(1)

# ─── Thread-local OCR 实例 ───
_thread_local = threading.local()

def get_ocr_engine():
    if not hasattr(_thread_local, 'ocr_engine'):
        _thread_local.ocr_engine = OCR_ENGINE_CLASS()
    return _thread_local.ocr_engine

# ─── OCR 线程池 ───
ocr_pool = ThreadPoolExecutor(max_workers=MAX_OCR_WORKERS, thread_name_prefix="ocr")

# ─── PDF 处理 ───
try:
    import fitz  # PyMuPDF
except ImportError:
    print("❌ PyMuPDF 未安装！pip install pymupdf")
    sys.exit(1)

import numpy as np
from PIL import Image

# ─── PDF Session 缓存 ───
_pdf_sessions = {}  # session_id → { "bytes": bytes, "pages": int, "created": float }
_session_lock = threading.Lock()

def _cleanup_sessions():
    """清理过期 session"""
    now = time.time()
    with _session_lock:
        expired = [sid for sid, s in _pdf_sessions.items() if now - s["created"] > SESSION_TIMEOUT]
        for sid in expired:
            del _pdf_sessions[sid]
            print(f"  [SESSION] 清理过期 session: {sid[:8]}...")

def create_pdf_session(pdf_bytes):
    """缓存 PDF 并返回 session info"""
    _cleanup_sessions()
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    total = doc.page_count
    doc.close()
    
    sid = uuid.uuid4().hex[:16]
    with _session_lock:
        _pdf_sessions[sid] = {
            "bytes": pdf_bytes,
            "pages": total,
            "created": time.time()
        }
    print(f"  [SESSION] 创建 session {sid[:8]}..., {total} 页, {len(pdf_bytes)/1024/1024:.1f}MB")
    return {"session_id": sid, "total_pages": total, "size_mb": round(len(pdf_bytes)/1024/1024, 1)}

def get_session_pdf(session_id):
    """获取缓存的 PDF bytes"""
    with _session_lock:
        s = _pdf_sessions.get(session_id)
        if s:
            s["created"] = time.time()  # Refresh timeout
            return s["bytes"]
    return None


def ocr_image(img_np):
    """对 numpy 数组图片进行 OCR"""
    engine = get_ocr_engine()
    result, elapse = engine(img_np)
    if result:
        texts = [item[1] for item in result]
        confs = [item[2] for item in result]
        return "\n".join(texts), sum(confs)/len(confs), len(texts)
    return "", 0, 0


def _render_and_ocr_page(pdf_bytes, page_num, dpi=200):
    """渲染并 OCR 单个 PDF 页面（线程安全）"""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    if page_num < 1 or page_num > doc.page_count:
        doc.close()
        return {"page": page_num, "error": f"Invalid page: {page_num}"}
    
    page = doc[page_num - 1]
    total_pages = doc.page_count
    
    # Check native text first
    native_text = page.get_text("text").strip()
    if len(native_text) > 50:
        doc.close()
        return {
            "text": native_text, "confidence": 1.0,
            "lines": native_text.count('\n') + 1,
            "method": "native_text", "page": page_num,
            "total_pages": total_pages, "engine": "native"
        }
    
    # Render and OCR
    mat = fitz.Matrix(dpi/72, dpi/72)
    pix = page.get_pixmap(matrix=mat)
    img = Image.open(io.BytesIO(pix.tobytes("png")))
    img_np = np.array(img)
    doc.close()
    
    text, conf, lines = ocr_image(img_np)
    return {
        "text": text, "confidence": conf, "lines": lines,
        "method": "ocr", "engine": OCR_ENGINE_NAME,
        "page": page_num, "total_pages": total_pages
    }


def ocr_pdf_batch(pdf_bytes, pages, dpi=200):
    """并发 OCR 多个 PDF 页面"""
    t0 = time.time()
    results = {}
    
    futures = {}
    for page_num in pages:
        future = ocr_pool.submit(_render_and_ocr_page, pdf_bytes, page_num, dpi)
        futures[future] = page_num
    
    for future in as_completed(futures):
        page_num = futures[future]
        try:
            results[page_num] = future.result()
        except Exception as e:
            results[page_num] = {"page": page_num, "error": str(e)}
    
    sorted_results = [results[p] for p in sorted(results.keys())]
    elapsed = time.time() - t0
    pages_done = len([r for r in sorted_results if "error" not in r])
    avg_conf = 0
    if pages_done:
        avg_conf = sum(r.get("confidence", 0) for r in sorted_results if "error" not in r) / pages_done
    
    return {
        "results": sorted_results,
        "batch_size": len(pages),
        "pages_done": pages_done,
        "avg_confidence": round(avg_conf, 3),
        "elapsed_s": round(elapsed, 2),
        "concurrency": MAX_OCR_WORKERS,
        "engine": OCR_ENGINE_NAME
    }


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class OCRHandler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self._cors_headers()
        self.end_headers()
    
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._json_response({
                "status": "ok",
                "engine": OCR_ENGINE_NAME,
                "concurrency": MAX_OCR_WORKERS,
                "cpu_cores": CPU_COUNT,
                "active_sessions": len(_pdf_sessions)
            })
        elif parsed.path == "/":
            self._json_response({
                "service": "Local OCR Server v2 (Session-based)",
                "engine": OCR_ENGINE_NAME,
                "concurrency": MAX_OCR_WORKERS,
                "endpoints": {
                    "POST /ocr/pdf/upload": "Upload PDF once, get session_id",
                    "POST /ocr/pdf/batch?session=xxx&pages=1,2,3": "OCR pages (no re-upload)",
                    "POST /ocr/pdf?page=N": "OCR single page (sends PDF in body)",
                }
            })
        else:
            self.send_error(404)
    
    def do_POST(self):
        parsed = urlparse(self.path)
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)
        
        t0 = time.time()
        
        try:
            if parsed.path == "/ocr/pdf/upload":
                result = create_pdf_session(body)
            elif parsed.path == "/ocr/pdf/batch":
                result = self._handle_session_batch(body)
            elif parsed.path == "/ocr/pdf":
                result = self._handle_pdf_page_ocr(body)
            elif parsed.path == "/ocr/pdf/all":
                result = self._handle_pdf_all_ocr(body)
            elif parsed.path == "/ocr/image":
                result = self._handle_image_ocr(body)
            else:
                self.send_error(404)
                return
            
            if "elapsed_s" not in result:
                result["elapsed_s"] = round(time.time() - t0, 2)
            self._json_response(result)
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            self._json_response({"error": str(e)}, status=500)
    
    def _handle_session_batch(self, body):
        """批量 OCR — 使用缓存的 PDF session"""
        params = parse_qs(urlparse(self.path).query)
        session_id = params.get("session", [""])[0]
        pages_str = params.get("pages", [""])[0]
        dpi = int(params.get("dpi", ["200"])[0])
        
        if not session_id:
            return {"error": "Missing 'session' parameter"}
        if not pages_str:
            return {"error": "Missing 'pages' parameter"}
        
        pdf_bytes = get_session_pdf(session_id)
        if not pdf_bytes:
            return {"error": f"Session '{session_id[:8]}...' expired or not found"}
        
        pages = [int(p.strip()) for p in pages_str.split(",") if p.strip()]
        print(f"  [BATCH] session={session_id[:8]}..., {len(pages)} pages, workers={MAX_OCR_WORKERS}")
        return ocr_pdf_batch(pdf_bytes, pages, dpi)
    
    def _handle_pdf_page_ocr(self, body):
        params = parse_qs(urlparse(self.path).query)
        page_num = int(params.get("page", ["1"])[0])
        dpi = int(params.get("dpi", ["200"])[0])
        return _render_and_ocr_page(body, page_num, dpi)
    
    def _handle_pdf_all_ocr(self, body):
        params = parse_qs(urlparse(self.path).query)
        dpi = int(params.get("dpi", ["200"])[0])
        doc = fitz.open(stream=body, filetype="pdf")
        total = doc.page_count
        doc.close()
        pages = list(range(1, total + 1))
        return ocr_pdf_batch(body, pages, dpi)
    
    def _handle_image_ocr(self, body):
        try:
            data = json.loads(body)
            img_data = base64.b64decode(data["image"])
        except (json.JSONDecodeError, KeyError):
            img_data = body
        
        img = Image.open(io.BytesIO(img_data))
        img_np = np.array(img)
        text, conf, lines = ocr_image(img_np)
        return {"text": text, "confidence": conf, "lines": lines, "engine": OCR_ENGINE_NAME}
    
    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
    
    def _json_response(self, data, status=200):
        self.send_response(status)
        self._cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)
    
    def log_message(self, format, *args):
        if args and "POST" in str(args[0]):
            print(f"  [{time.strftime('%H:%M:%S')}] {args[0]}")


if __name__ == "__main__":
    print(f"\n🚀 OCR 服务器 v2 启动: http://{HOST}:{PORT}")
    print(f"   引擎: {OCR_ENGINE_NAME}")
    print(f"   并发线程: {MAX_OCR_WORKERS} (CPU: {CPU_COUNT} 核)")
    print(f"   Session 超时: {SESSION_TIMEOUT}s")
    print(f"   Ctrl+C 停止\n")
    
    server = ThreadingHTTPServer((HOST, PORT), OCRHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n⛔ 服务器已停止")
        ocr_pool.shutdown(wait=False)
        server.server_close()
