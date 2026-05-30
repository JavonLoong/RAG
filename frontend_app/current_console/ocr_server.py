"""
高性能并发 OCR 服务器 v5 — 多引擎 + 高并发
流程: 上传 PDF → 服务器自动分页并发 OCR → 前端轮询进度 → 返回合并文本

引擎:
  - rapidocr (默认) — RapidOCR (PaddleOCR ONNX), 高精度中文
  - tesseract         — Tesseract OCR (chi_sim+eng), 需本机安装

接口:
  POST /ocr/pdf/start?engine=rapidocr   上传 PDF，立即开始后台并发处理
  POST /ocr/pdf/start?engine=tesseract   使用 Tesseract 引擎
  GET  /ocr/pdf/progress?session=xxx     轮询进度
  GET  /health                           健康检查 (返回可用引擎列表)
"""
import sys, os, io, json, time, uuid, threading, subprocess, csv, tempfile
from pathlib import Path

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
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed

PORT = 8765
HOST = "127.0.0.1"
CPU_COUNT = os.cpu_count() or 4
# 默认: CPU核数的一半, 上限12; 可通过环境变量 OCR_WORKERS 覆盖
_env_workers = os.environ.get("OCR_WORKERS")
MAX_OCR_WORKERS = int(_env_workers) if _env_workers else max(2, min(CPU_COUNT // 2, 12))

# ─── Tesseract paths ───
TESSERACT_EXE = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
TESSDATA_DIR = Path(r"C:\Users\15410\tessdata-local")
TESSERACT_AVAILABLE = TESSERACT_EXE.exists() and TESSDATA_DIR.exists()

# ─── OCR 引擎 ───
print(f"CPU: {CPU_COUNT} 核, OCR 线程: {MAX_OCR_WORKERS}")
print("加载 OCR 引擎...")

# RapidOCR
RAPID_AVAILABLE = False
try:
    from rapidocr_onnxruntime import RapidOCR
    RapidOCR()  # test
    RAPID_AVAILABLE = True
    print(f"[OK] RapidOCR (PaddleOCR ONNX)")
except ImportError:
    print("[SKIP] RapidOCR 未安装 (pip install rapidocr-onnxruntime)")
except Exception as e:
    print(f"[SKIP] RapidOCR 初始化失败: {e}")

# Tesseract
if TESSERACT_AVAILABLE:
    print(f"[OK] Tesseract OCR (exe: {TESSERACT_EXE})")
else:
    print(f"[SKIP] Tesseract 未找到 (路径: {TESSERACT_EXE})")

if not RAPID_AVAILABLE and not TESSERACT_AVAILABLE:
    print("[ERROR] 至少需要一个 OCR 引擎！")
    sys.exit(1)

try:
    import fitz
except ImportError:
    print("[ERROR] pip install pymupdf"); sys.exit(1)

import numpy as np
from PIL import Image

_tls = threading.local()

# 限制 ONNX Runtime 每个实例的线程数, 避免 N×M 线程过度竞争
# 总线程 ≈ MAX_OCR_WORKERS × _ONNX_THREADS ≈ 12×2 = 24 (恰好用满 CPU)
_ONNX_THREADS = max(1, CPU_COUNT // MAX_OCR_WORKERS)

def get_rapid_engine():
    if not hasattr(_tls, 'rapid'):
        _tls.rapid = RapidOCR(
            # Det/Cls/Rec 每个子模型的 ONNX 内部并行线程数
            det_intra_op_num_threads=_ONNX_THREADS,
            det_inter_op_num_threads=1,
            cls_intra_op_num_threads=_ONNX_THREADS,
            cls_inter_op_num_threads=1,
            rec_intra_op_num_threads=_ONNX_THREADS,
            rec_inter_op_num_threads=1,
        )
    return _tls.rapid

pool = ThreadPoolExecutor(max_workers=MAX_OCR_WORKERS, thread_name_prefix="ocr")
_pool_type = "Thread"

# ─── Session 管理 ───
sessions = {}  # id → { pages_done, total, results[], complete, text, ... }
sess_lock = threading.Lock()


def _ocr_one_page_rapid(pdf_bytes, page_num, dpi=200):
    """RapidOCR 单页 (子进程安全)"""
    t0 = time.time()
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = doc[page_num - 1]

    # 先检查原生文本
    native = page.get_text("text").strip()
    if len(native) > 50:
        doc.close()
        return {"page": page_num, "text": native, "confidence": 1.0,
                "lines": native.count('\n')+1, "method": "native", "engine": "native",
                "time_ms": round((time.time()-t0)*1000)}

    # 渲染 + OCR
    mat = fitz.Matrix(dpi/72, dpi/72)
    pix = page.get_pixmap(matrix=mat)
    img_np = np.array(Image.open(io.BytesIO(pix.tobytes("png"))))
    doc.close()

    # 子进程中用 thread-local 引擎实例
    engine = get_rapid_engine()
    result, _ = engine(img_np)
    elapsed = round((time.time()-t0)*1000)
    if result:
        texts = [r[1] for r in result]
        confs = [r[2] for r in result]
        return {"page": page_num, "text": "\n".join(texts),
                "confidence": sum(confs)/len(confs), "lines": len(texts),
                "method": "ocr", "engine": "RapidOCR", "time_ms": elapsed}
    return {"page": page_num, "text": "", "confidence": 0, "lines": 0,
            "method": "ocr", "engine": "RapidOCR", "time_ms": elapsed}


def _ocr_one_page_tesseract(pdf_bytes, page_num, dpi=200, lang="chi_sim+eng", psm=6):
    """Tesseract OCR 单页"""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = doc[page_num - 1]

    # 先检查原生文本
    native = page.get_text("text").strip()
    if len(native) > 50:
        doc.close()
        return {"page": page_num, "text": native, "confidence": 1.0,
                "lines": native.count('\n')+1, "method": "native", "engine": "native"}

    # 渲染
    mat = fitz.Matrix(dpi/72, dpi/72)
    pix = page.get_pixmap(matrix=mat)
    doc.close()

    with tempfile.TemporaryDirectory(prefix="ocr_tess_") as tmp:
        img_path = Path(tmp) / "page.png"
        out_base = Path(tmp) / "out"
        pix.save(img_path)
        cmd = [
            str(TESSERACT_EXE), str(img_path), str(out_base),
            "--tessdata-dir", str(TESSDATA_DIR),
            "-l", lang, "--psm", str(psm),
            "-c", "tessedit_create_tsv=1",
        ]
        cp = subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", check=False)
        if cp.returncode != 0:
            return {"page": page_num, "text": "", "confidence": 0, "lines": 0,
                    "method": "ocr", "engine": "Tesseract",
                    "error": cp.stderr.strip()[:200]}

        tsv_path = out_base.with_suffix(".tsv")
        rows = []
        with tsv_path.open("r", encoding="utf-8", errors="replace", newline="") as f:
            rows = list(csv.DictReader(f, delimiter="\t"))

    # Parse TSV → text lines
    grouped = {}
    for row in rows:
        text = (row.get("text") or "").strip()
        if not text or row.get("level") != "5":
            continue
        key = (row.get("block_num", ""), row.get("par_num", ""), row.get("line_num", ""))
        grouped.setdefault(key, []).append(row)

    lines, all_confs = [], []
    for key in sorted(grouped.keys()):
        words = grouped[key]
        tokens = []
        for w in words:
            tokens.append((w.get("text") or "").strip())
            try:
                c = float(w.get("conf", 0))
                if c >= 0: all_confs.append(c / 100)
            except: pass
        line = ""
        for t in tokens:
            if line and line[-1:].isascii() and line[-1:].isalnum() and t[:1].isascii() and t[:1].isalnum():
                line += " "
            line += t
        if line.strip():
            lines.append(line.strip())

    text = "\n".join(lines)
    avg_conf = sum(all_confs) / len(all_confs) if all_confs else 0.0
    return {"page": page_num, "text": text,
            "confidence": avg_conf, "lines": len(lines),
            "method": "ocr", "engine": "Tesseract"}


def _ocr_one_page(pdf_bytes, page_num, dpi=200, engine_name="rapidocr"):
    """统一入口: 根据引擎名路由"""
    if engine_name == "tesseract":
        return _ocr_one_page_tesseract(pdf_bytes, page_num, dpi)
    else:
        return _ocr_one_page_rapid(pdf_bytes, page_num, dpi)


def start_ocr_session(pdf_bytes, dpi=200, engine_name="rapidocr"):
    """上传 PDF，立刻后台启动全量并发 OCR"""
    # Validate engine availability
    if engine_name == "rapidocr" and not RAPID_AVAILABLE:
        return {"error": "RapidOCR 引擎不可用，请安装 rapidocr-onnxruntime"}
    if engine_name == "tesseract" and not TESSERACT_AVAILABLE:
        return {"error": "Tesseract 引擎不可用，请安装 Tesseract OCR"}

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    total = doc.page_count
    doc.close()

    engine_label = "RapidOCR" if engine_name == "rapidocr" else "Tesseract"

    sid = uuid.uuid4().hex[:12]
    session = {
        "total": total, "done": 0, "results": [None]*total,
        "complete": False, "error": None, "started": time.time(),
        "engine": engine_label, "concurrency": MAX_OCR_WORKERS
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
            f = pool.submit(_ocr_one_page, pdf_bytes, p, dpi, engine_name)
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
                          f"引擎={engine_label}, "
                          f"耗时 {session['elapsed_s']}s, 置信度 {avg_conf:.1%}")

    threading.Thread(target=_run, daemon=True).start()

    print(f"  [START] session={sid[:8]}, {total} 页, 引擎={engine_label}, {MAX_OCR_WORKERS} 线程并发")
    return {"session_id": sid, "total_pages": total, "concurrency": MAX_OCR_WORKERS,
            "engine": engine_label}


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
            engines = []
            if RAPID_AVAILABLE: engines.append("rapidocr")
            if TESSERACT_AVAILABLE: engines.append("tesseract")
            self._json({
                "status": "ok",
                "engine": "RapidOCR" if RAPID_AVAILABLE else "Tesseract",
                "engines": engines,
                "rapidocr": RAPID_AVAILABLE,
                "tesseract": TESSERACT_AVAILABLE,
                "concurrency": MAX_OCR_WORKERS,
                "cpu_cores": CPU_COUNT,
                "active_sessions": len(sessions)
            })
        elif path == "/ocr/pdf/progress":
            sid = params.get("session", [""])[0]
            self._json(get_progress(sid))
        elif path == "/debug":
            debug_sessions = {}
            for k, v in sessions.items():
                debug_sessions[k] = {
                    "done": v.get("done"),
                    "total": v.get("total"),
                    "complete": v.get("complete"),
                    "results_len": len(v.get("results", [])),
                    "error": v.get("error")
                }
            self._json(debug_sessions)
        else:
            self._json({"service": "OCR Server v5", "engines": {
                "rapidocr": RAPID_AVAILABLE,
                "tesseract": TESSERACT_AVAILABLE
            }, "concurrency": MAX_OCR_WORKERS, "pool_type": _pool_type})

    def do_POST(self):
        path = urlparse(self.path).path
        params = parse_qs(urlparse(self.path).query)
        body = self.rfile.read(int(self.headers.get('Content-Length', 0)))

        try:
            if path == "/ocr/pdf/start":
                engine_name = params.get("engine", ["rapidocr"])[0]
                self._json(start_ocr_session(body, engine_name=engine_name))
            elif path == "/ocr/pdf":
                # Single-page compatibility
                p = int(params.get("page", ["1"])[0])
                engine_name = params.get("engine", ["rapidocr"])[0]
                r = _ocr_one_page(body, p, engine_name=engine_name)
                self._json(r)
            elif path == "/proxy":
                # CORS proxy for Baidu Cloud OCR API
                target_url = params.get("url", [""])[0]
                if not target_url:
                    self._json({"error": "missing url param"}, 400)
                    return
                import urllib.request as _ur
                content_type = self.headers.get('Content-Type', 'application/x-www-form-urlencoded')
                req = _ur.Request(target_url, data=body if body else None,
                                  headers={"Content-Type": content_type},
                                  method="POST" if body else "GET")
                with _ur.urlopen(req, timeout=30) as resp:
                    resp_body = resp.read()
                self.send_response(200); self._cors()
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", len(resp_body)); self.end_headers()
                self.wfile.write(resp_body)
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
    engines_str = []
    if RAPID_AVAILABLE: engines_str.append("RapidOCR ✅")
    if TESSERACT_AVAILABLE: engines_str.append("Tesseract ✅")
    print(f"\n>>> OCR Server v5: http://{HOST}:{PORT}")
    print(f"    可用引擎: {', '.join(engines_str)}")
    print(f"    Workers: {MAX_OCR_WORKERS} {_pool_type.lower()}s / {CPU_COUNT} cores")
    if _env_workers:
        print(f"    (OCR_WORKERS 环境变量覆盖: {_env_workers})")
    print(f"    Usage: POST /ocr/pdf/start?engine=rapidocr  (默认)")
    print(f"           POST /ocr/pdf/start?engine=tesseract")
    print(f"           GET  /ocr/pdf/progress?session=xxx\n")

    server = ThreadingHTTPServer((HOST, PORT), OCRHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[STOP]"); pool.shutdown(wait=False); server.server_close()
