# -*- coding: utf-8 -*-
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
d = json.loads(Path("evaluation/reports/thermo_probe2_20260927.json").read_text(encoding="utf-8"))
print(f"{'backend':13} {'http':5} {'tatus':11} {'runtime':26} warnings")
for backend, entry in d["backends"].items():
    plan = entry.get("processing_plan") or {}
    runtime = plan.get("runtime") or {}
    label = f"{runtime.get('name')}/{runtime.get('status')}"
    warnings = entry.get("warnings") or []
    print(f"{backend:13} {entry.get('status'):5} {str(entry.get('intake_status')):11} {label:26} {warnings}")
print()
print("annotation endpoints:", d["annotation_surface"]["paths_mentioning_annotation"])
print("public-books endpoints:", d["annotation_surface"]["paths_mentioning_public_books"])
print("delivery endpoints:", len(d["annotation_surface"]["delivery_paths"]))
print("intake response keys:", d.get("intake_response_keys"))
