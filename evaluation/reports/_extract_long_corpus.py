"""Extract selected Label Studio documents into page-ordered text files."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

SRC = Path(r"C:\Users\15410\AppData\Local\PowerRAG\current_console\uploads\project-1-at-2026-05-21-06-17-203caed5.json")
OUT = Path(__file__).resolve().parents[1] / "fixtures" / "cs_long_20260923"

KEEP = {
    "EAB-BOP-X-2754-IS-001_Ya_Suo_Ji_Hua_You_Qiao_Shuo_Ming_Shu_BOP-X-2754ABC_.pdf": "oil_skid_manual.txt",
    "CGT25-DARan_Qu_Ya_Suo_Ji_Zu_Zong_Jie_Bao_Gao_lastsss.pdf": "cgt25_da_summary.txt",
    "2025-09-18_Xia_Bu_Chuan_Dong_Xiang_Gu_Zhang_Yuan_Yin_Fen_Xi_Bao_Gao_-v5.pdf": "gearbox_failure_20250918.txt",
    "2020Nian_7Yue_Yan_Dun_Xian_Chang_Gong_Zuo_Zong_Jie_.pdf": "yandun_july2020_summary.txt",
    "Yan_Dun_Ya_Qi_Zhan_Guo_Chan_2Ya_Suo_Ji_Zu_Ting_Ji_Fen_Xi_Bao_Gao_.pdf": "yandun_unit2_trip.txt",
    "Gao_Ya_Wo_Lun_Dong_Xie_Tu_Ceng_Lie_Wen_Fen_Xi_Bao_Gao_20240315Di_Shi_Gao_.pdf": "hp_turbine_coating_crack.txt",
    "2024.05.13_Wu_Zhou_Chuan_Dong_Xiang_Zhui_Chi_Lun_Duan_Lie_Shi_Xiao_Fen_Xi_-Zhong_Ban_.pdf": "wuzhou_bevel_gear_20240513.txt",
    "322097Dong_Li_Wo_Lun_Gu_Zhang_Gui_Ling_Bao_Gao_.pdf": "power_turbine_zeroing_322097.txt",
}


def blocks(task: dict) -> list[tuple[float, float, str]]:
    by_id: dict[str, dict] = {}
    for ann in task.get("annotations") or []:
        for res in ann.get("result") or []:
            rid = res.get("id") or f"{res.get('from_name')}-{id(res)}"
            rec = by_id.setdefault(rid, {"y": 0.0, "x": 0.0, "text": ""})
            val = res.get("value") or {}
            if "y" in val:
                rec["y"] = float(val.get("y") or 0)
                rec["x"] = float(val.get("x") or 0)
            text = val.get("text")
            if isinstance(text, list):
                rec["text"] = "\n".join(str(x).strip() for x in text if str(x).strip())
            elif isinstance(text, str) and text.strip():
                rec["text"] = text.strip()
    return [(r["y"], r["x"], r["text"]) for r in by_id.values() if r["text"]]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    tasks = json.loads(SRC.read_text(encoding="utf-8"))
    pages: dict[str, dict[int, list[str]]] = defaultdict(lambda: defaultdict(list))
    for task in tasks:
        name = (task.get("data") or {}).get("filename")
        if name not in KEEP:
            continue
        page = int((task.get("data") or {}).get("page_num") or 0)
        ordered = sorted(blocks(task), key=lambda t: (t[0], t[1]))
        pages[name][page].extend(t[2] for t in ordered)

    manifest = []
    for src_name, out_name in KEEP.items():
        page_map = pages.get(src_name) or {}
        lines = [f"# SOURCE {src_name}", f"# PAGES {len(page_map)}", ""]
        chars = 0
        for page in sorted(page_map):
            body = "\n".join(page_map[page])
            chars += len(body)
            lines.append(f"===== PAGE {page} =====")
            lines.append(body)
            lines.append("")
        dest = OUT / out_name
        dest.write_text("\n".join(lines), encoding="utf-8")
        manifest.append({"source": src_name, "file": out_name, "pages": len(page_map), "chars": chars})
        print(f"{out_name}\tpages={len(page_map)}\tchars={chars}")
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
