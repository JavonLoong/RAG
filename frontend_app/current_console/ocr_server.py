"""
高性能并发 OCR 服务器 v3 — 一键全量并发
流程: 上传 PDF → 服务器自动分页并发 OCR → 前端轮询进度 → 返回合并文本

接口:
  POST /ocr/pdf/start   上传 PDF，立即开始后台并发处理，返回 {session_id, total_pages}
  GET  /ocr/pdf/progress?session=xxx  轮询进度 {done, total, pct, results?, complete}
  GET  /health           健康检查
"""
import sys, os, io, json, time, uuid, threading

# Fix Windows GBK console encoding crash with Unicode characters
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try: sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except: pass
if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
    try: sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except: pass

from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from urllib.parse import urlparse, parse_qs
from concurrent.futures import ThreadPoolExecutor, as_completed

PORT = 8765
HOST = "127.0.0.1"
CPU_COUNT = os.cpu_count() or 4
MAX_OCR_WORKERS = max(2, min(CPU_COUNT // 2, 12))

# ─── OCR 引擎 ───
print(f"CPU: {CPU_COUNT} 核, OCR 线程: {MAX_OCR_WORKERS}")
print("加载 RapidOCR...")
try:
    from rapidocr_onnxruntime import RapidOCR
    OCR_ENGINE_NAME = "RapidOCR (PaddleOCR ONNX)"
    RapidOCR()  # test
    print(f"[OK] {OCR_ENGINE_NAME}")
except ImportError:
    print("[ERROR] pip install rapidocr-onnxruntime"); sys.exit(1)

try:
    import fitz
except ImportError:
    print("[ERROR] pip install pymupdf"); sys.exit(1)

import numpy as np
from PIL import Image

_tls = threading.local()
def get_engine():
    if not hasattr(_tls, 'e'): _tls.e = RapidOCR()
    return _tls.e

pool = ThreadPoolExecutor(max_workers=MAX_OCR_WORKERS, thread_name_prefix="ocr")

# ─── Session 管理 ───
sessions = {}  # id → { pages_done, total, results[], complete, text, ... }
sess_lock = threading.Lock()

def _ocr_one_page(pdf_bytes, page_num, dpi=200):
    """OCR 单页（线程内运行）"""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = doc[page_num - 1]
    
    # 先检查原生文本
    native = page.get_text("text").strip()
    if len(native) > 50:
        doc.close()
        return {"page": page_num, "text": native, "confidence": 1.0,
                "lines": native.count('\n')+1, "method": "native", "engine": "native"}
    
    # 渲染 + OCR
    mat = fitz.Matrix(dpi/72, dpi/72)
    pix = page.get_pixmap(matrix=mat)
    img_np = np.array(Image.open(io.BytesIO(pix.tobytes("png"))))
    doc.close()
    
    engine = get_engine()
    result, _ = engine(img_np)
    if result:
        texts = [r[1] for r in result]
        confs = [r[2] for r in result]
        return {"page": page_num, "text": "\n".join(texts),
                "confidence": sum(confs)/len(confs), "lines": len(texts),
                "method": "ocr", "engine": OCR_ENGINE_NAME}
    return {"page": page_num, "text": "", "confidence": 0, "lines": 0,
            "method": "ocr", "engine": OCR_ENGINE_NAME}


def start_ocr_session(pdf_bytes, dpi=200):
    """上传 PDF，立刻后台启动全量并发 OCR"""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    total = doc.page_count
    doc.close()
    
    sid = uuid.uuid4().hex[:12]
    session = {
        "total": total, "done": 0, "results": [None]*total,
        "complete": False, "error": None, "started": time.time(),
        "engine": OCR_ENGINE_NAME, "concurrency": MAX_OCR_WORKERS
    }
    with sess_lock:
        sessions[sid] = session
    
    # 启动后台处理
    def _run():
        t0 = time.time()
        all_pages = list(range(1, total + 1))
        
        # 提交所有页面到线程池
        futures = {}
        for p in all_pages:
            f = pool.submit(_ocr_one_page, pdf_bytes, p, dpi)
            futures[f] = p
        
        # 每完成一页就更新进度
        for f in as_completed(futures):
            p = futures[f]
            try:
                r = f.result()
            except Exception as e:
                r = {"page": p, "text": "", "confidence": 0, "error": str(e)}
            
            with sess_lock:
                session["results"][p-1] = r
                session["done"] += 1
                
                if session["done"] >= total:
                    # 全部完成 — 按页码顺序合并文本
                    all_texts = []
                    for res in session["results"]:
                        if res and res.get("text"):
                            all_texts.append(res["text"])
                    session["full_text"] = "\n\n".join(all_texts)
                    session["complete"] = True
                    session["elapsed_s"] = round(time.time() - t0, 1)
                    
                    avg_conf = 0
                    valid = [r for r in session["results"] if r and r.get("confidence")]
                    if valid:
                        avg_conf = sum(r["confidence"] for r in valid) / len(valid)
                    session["avg_confidence"] = round(avg_conf, 3)
                    
                    print(f"  [DONE] session={sid[:8]}, {total} 页, "
                          f"耗时 {session['elapsed_s']}s, 置信度 {avg_conf:.1%}")
    
    threading.Thread(target=_run, daemon=True).start()
    
    print(f"  [START] session={sid[:8]}, {total} 页, {MAX_OCR_WORKERS} 线程并发")
    return {"session_id": sid, "total_pages": total, "concurrency": MAX_OCR_WORKERS}


def get_progress(sid):
    """获取 OCR 进度"""
    with sess_lock:
        s = sessions.get(sid)
    if not s:
        return {"error": "Session not found"}
    
    result = {
        "done": s["done"], "total": s["total"],
        "pct": round(s["done"] / s["total"] * 100) if s["total"] else 0,
        "complete": s["complete"],
        "engine": s["engine"], "concurrency": s["concurrency"]
    }
    
    # 返回最近完成的页面文本片段（用于前端实时预览）
    if not s["complete"] and s["done"] > 0:
        # 找到最近完成的页面
        for r in reversed(s["results"]):
            if r and r.get("text"):
                text = r["text"].strip()
                # 取最后一行非空文本作为预览，限制长度
                lines = [l for l in text.split("\n") if l.strip()]
                if lines:
                    result["latest_text"] = lines[-1][:150]
                    result["latest_page"] = r.get("page", 0)
                break
    
    if s["complete"]:
        result["full_text"] = s["full_text"]
        result["elapsed_s"] = s.get("elapsed_s", 0)
        result["avg_confidence"] = s.get("avg_confidence", 0)
        
        # 每页的详细结果（不含全文本，太大）
        result["pages"] = []
        for r in s["results"]:
            if r:
                result["pages"].append({
                    "page": r.get("page"), "confidence": r.get("confidence", 0),
                    "chars": len(r.get("text", "")), "lines": r.get("lines", 0),
                    "method": r.get("method", ""), "engine": r.get("engine", "")
                })
        
        # 完成后清理 session（保留 2 分钟供重新获取）
        threading.Timer(120, lambda: sessions.pop(sid, None)).start()
    
    return result


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

class OCRHandler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200); self._cors(); self.end_headers()
    
    def do_GET(self):
        path = urlparse(self.path).path
        params = parse_qs(urlparse(self.path).query)
        
        if path == "/health":
            self._json({"status": "ok", "engine": OCR_ENGINE_NAME,
                        "concurrency": MAX_OCR_WORKERS, "cpu_cores": CPU_COUNT,
                        "active_sessions": len(sessions)})
        elif path == "/ocr/pdf/progress":
            sid = params.get("session", [""])[0]
            self._json(get_progress(sid))
        else:
            self._json({"service": "OCR Server v3", "engine": OCR_ENGINE_NAME,
                        "concurrency": MAX_OCR_WORKERS})
    
    def do_POST(self):
        path = urlparse(self.path).path
        body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
        
        try:
            if path == "/ocr/pdf/start":
                self._json(start_ocr_session(body))
            elif path == "/ocr/pdf":
                # 保留单页接口兼容性
                params = parse_qs(urlparse(self.path).query)
                p = int(params.get("page", ["1"])[0])
                r = _ocr_one_page(body, p)
                self._json(r)
            else:
                self.send_error(404)
        except Exception as e:
            import traceback; traceback.print_exc()
            self._json({"error": str(e)}, 500)
    
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
    
    def _json(self, data, status=200):
        self.send_response(status); self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        b = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_header("Content-Length", len(b)); self.end_headers()
        self.wfile.write(b)
    
    def log_message(self, fmt, *a):
        if a and "POST" in str(a[0]):
            print(f"  [{time.strftime('%H:%M:%S')}] {a[0]}")

if __name__ == "__main__":
    print(f"\n>>> OCR Server v3: http://{HOST}:{PORT}")
    print(f"    Engine: {OCR_ENGINE_NAME}")
    print(f"    Workers: {MAX_OCR_WORKERS} threads / {CPU_COUNT} cores")
    print(f"    Usage: POST /ocr/pdf/start (upload PDF)")
    print(f"           GET  /ocr/pdf/progress?session=xxx (poll progress)\n")
    
    server = ThreadingHTTPServer((HOST, PORT), OCRHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[STOP]"); pool.shutdown(wait=False); server.server_close()
