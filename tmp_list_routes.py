# -*- coding: utf-8 -*-
"""Extract live FastAPI routes from the current console app."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "api_server" / "current_console" / "chroma_rag_poc" / "src"
sys.path.insert(0, str(SRC))
sys.path.insert(0, str(ROOT))

from chroma_rag_poc.api import create_app  # noqa: E402

app = create_app(
    persist_dir=ROOT / "tmp_route_scan" / "chroma",
    upload_dir=ROOT / "tmp_route_scan" / "uploads",
    log_dir=ROOT / "tmp_route_scan" / "logs",
)

rows = []
for route in app.routes:
    methods = sorted(getattr(route, "methods", None) or [])
    methods = [m for m in methods if m not in {"HEAD", "OPTIONS"}]
    path = getattr(route, "path", None)
    name = getattr(route, "name", "")
    if not path or not methods:
        continue
    rows.append((",".join(methods), path, name))

rows.sort(key=lambda item: (item[1], item[0]))
out = ROOT / "_all_routes.txt"
out.write_text(
    f"count={len(rows)}\n" + "\n".join(f"{m}\t{p}\t{n}" for m, p, n in rows),
    encoding="utf-8",
)
print(out, len(rows))
