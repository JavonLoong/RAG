# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(r"D:\虚拟C盘\PowerRAG-latest")
SRC = ROOT / "api_server" / "current_console" / "chroma_rag_poc" / "src"
sys.path.insert(0, str(SRC))
sys.path.insert(0, str(ROOT))

from chroma_rag_poc.api import create_app

app = create_app(
    persist_dir=ROOT / "tmp_route_scan" / "chroma",
    upload_dir=ROOT / "tmp_route_scan" / "uploads",
    log_dir=ROOT / "tmp_route_scan" / "logs",
)
schema = app.openapi()
out = ROOT / "_openapi_current.json"
out.write_text(json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8")
print(out, "paths", len(schema.get("paths", {})), "schemas", len(schema.get("components", {}).get("schemas", {})))
