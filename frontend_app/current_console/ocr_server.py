"""
轻量级本地 OCR 服务器
使用 RapidOCR (PaddleOCR ONNX) 进行高精度中文 OCR
供前端 index.html 调用
"""
import sys
import os
import io
import json
import base64
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# ─── 配置 ───
PORT = 8765
HOST = "127.0.0.1"

# ─── 初始化 OCR 引擎 ───
print("正在加载 OCR 引擎 (RapidOCR)...")
try:
    from rapidocr_onnxruntime import RapidOCR
    ocr_engine = RapidOCR()
    OCR_ENGINE_NAME = "RapidOCR (PaddleOCR ONNX)"
    print(f"✅ {OCR_ENGINE_NAME} 加载成功")
except ImportError:
    print("⚠️  RapidOCR 未安装，尝试 EasyOCR...")
    try:
        import easyocr
        reader = easyocr.Reader(['ch_sim', 'en'], gpu=False)
        OCR_ENGINE_NAME = "EasyOCR"
        ocr_engine = None  # Use reader instead
        print(f"✅ {OCR_ENGINE_NAME} 加载成功")
    except ImportError:
        print("❌ 没有可用的 OCR 引擎！请安装: pip install rapidocr-onnxruntime")
        sys.exit(1)

# ─── PDF 处理 ───
try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False
    print("⚠️  PyMuPDF 未安装，不支持 PDF OCR。pip install pymupdf")

import numpy as np
from PIL import Image


def ocr_image(img_np):
    """对 numpy 数组图片进行 OCR，返回 (text, confidence, lines)"""
    if ocr_engine is not None:
        # RapidOCR
        result, elapse = ocr_engine(img_np)
        if result:
            texts = [item[1] for item in result]
            confs = [item[2] for item in result]
            return "\n".join(texts), sum(confs)/len(confs), len(texts)
        return "", 0, 0
    else:
        # EasyOCR fallback
        results = reader.readtext(img_np, detail=1)
        if results:
            texts = [r[1] for r in results]
            confs = [r[2] for r in results]
            return "\n".join(texts), sum(confs)/len(confs), len(texts)
        return "", 0, 0


def ocr_pdf_page(pdf_bytes, page_num, dpi=200):
    """OCR 单个 PDF 页面"""
    if not HAS_PYMUPDF:
        return {"error": "PyMuPDF not installed"}
    
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    if page_num < 1 or page_num > doc.page_count:
        doc.close()
        return {"error": f"Invalid page number: {page_num}, total: {doc.page_count}"}
    
    page = doc[page_num - 1]
    
    # Check for native text first
    native_text = page.get_text("text").strip()
    if len(native_text) > 50:
        doc.close()
        return {
            "text": native_text,
            "confidence": 1.0,
            "method": "native_text",
            "page": page_num,
            "total_pages": doc.page_count
        }
    
    # Render and OCR
    mat = fitz.Matrix(dpi/72, dpi/72)
    pix = page.get_pixmap(matrix=mat)
    img = Image.open(io.BytesIO(pix.tobytes("png")))
    img_np = np.array(img)
    
    text, conf, lines = ocr_image(img_np)
    
    total_pages = doc.page_count
    doc.close()
    
    return {
        "text": text,
        "confidence": conf,
        "lines": lines,
        "method": "ocr",
        "engine": OCR_ENGINE_NAME,
        "page": page_num,
        "total_pages": total_pages
    }


def ocr_pdf_all(pdf_bytes, dpi=200, max_pages=None):
    """OCR 整个 PDF"""
    if not HAS_PYMUPDF:
        return {"error": "PyMuPDF not installed"}
    
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    total = doc.page_count
    if max_pages:
        total = min(total, max_pages)
    
    results = []
    all_text = []
    
    for i in range(total):
        page = doc[i]
        native_text = page.get_text("text").strip()
        
        if len(native_text) > 50:
            results.append({
                "page": i+1, "method": "native", 
                "confidence": 1.0, "chars": len(native_text)
            })
            all_text.append(native_text)
            continue
        
        # OCR
        mat = fitz.Matrix(dpi/72, dpi/72)
        pix = page.get_pixmap(matrix=mat)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        img_np = np.array(img)
        
        text, conf, lines = ocr_image(img_np)
        results.append({
            "page": i+1, "method": "ocr",
            "confidence": conf, "chars": len(text)
        })
        all_text.append(text)
    
    doc.close()
    
    avg_conf = sum(r["confidence"] for r in results) / len(results) if results else 0
    
    return {
        "full_text": "\n\n".join(all_text),
        "pages": results,
        "total_pages": doc.page_count if hasattr(doc, 'page_count') else total,
        "processed_pages": total,
        "avg_confidence": avg_conf,
        "engine": OCR_ENGINE_NAME
    }


class OCRHandler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self._cors_headers()
        self.end_headers()
    
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._json_response({"status": "ok", "engine": OCR_ENGINE_NAME})
        elif parsed.path == "/":
            self._json_response({
                "service": "Local OCR Server",
                "engine": OCR_ENGINE_NAME,
                "endpoints": {
                    "GET /health": "Health check",
                    "POST /ocr/image": "OCR an image (multipart/form-data or base64 JSON)",
                    "POST /ocr/pdf": "OCR a PDF page (multipart/form-data)",
                    "POST /ocr/pdf/all": "OCR entire PDF"
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
            if parsed.path == "/ocr/image":
                result = self._handle_image_ocr(body)
            elif parsed.path == "/ocr/pdf":
                result = self._handle_pdf_page_ocr(body)
            elif parsed.path == "/ocr/pdf/all":
                result = self._handle_pdf_all_ocr(body)
            else:
                self.send_error(404)
                return
            
            result["elapsed_s"] = round(time.time() - t0, 2)
            self._json_response(result)
            
        except Exception as e:
            self._json_response({"error": str(e)}, status=500)
    
    def _handle_image_ocr(self, body):
        # Try JSON with base64
        try:
            data = json.loads(body)
            img_data = base64.b64decode(data["image"])
        except (json.JSONDecodeError, KeyError):
            img_data = body
        
        img = Image.open(io.BytesIO(img_data))
        img_np = np.array(img)
        text, conf, lines = ocr_image(img_np)
        
        return {
            "text": text,
            "confidence": conf,
            "lines": lines,
            "engine": OCR_ENGINE_NAME,
            "image_size": f"{img.width}x{img.height}"
        }
    
    def _handle_pdf_page_ocr(self, body):
        # Expect multipart or raw PDF with page param
        params = parse_qs(urlparse(self.path).query)
        page_num = int(params.get("page", ["1"])[0])
        dpi = int(params.get("dpi", ["200"])[0])
        return ocr_pdf_page(body, page_num, dpi)
    
    def _handle_pdf_all_ocr(self, body):
        params = parse_qs(urlparse(self.path).query)
        dpi = int(params.get("dpi", ["200"])[0])
        max_pages = params.get("max_pages", [None])[0]
        if max_pages:
            max_pages = int(max_pages)
        return ocr_pdf_all(body, dpi, max_pages)
    
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
        # Minimal logging
        if args and "POST" in str(args[0]):
            print(f"  [{time.strftime('%H:%M:%S')}] {args[0]}")


if __name__ == "__main__":
    print(f"\n🚀 OCR 服务器启动: http://{HOST}:{PORT}")
    print(f"   引擎: {OCR_ENGINE_NAME}")
    print(f"   Ctrl+C 停止\n")
    
    server = HTTPServer((HOST, PORT), OCRHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n⛔ 服务器已停止")
        server.server_close()
