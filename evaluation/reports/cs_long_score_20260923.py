"""Score long-doc exam: hit / cite / refuse only. Pin is not scored."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

GOLD = json.loads(Path(__file__).with_name("cs_long_gold_20260923.json").read_text(encoding="utf-8"))
ANS_PATH = Path(__file__).with_name("cs_long_answers_20260923.json")

ALTS = {
    "Guided Setup": ("Guided Setup", "设置向导"),
    "Verify Level": ("Verify Level", "验证液位"),
    "不是同一": ("不是同一", "不是同一种", "不是一类", "不同类", "不是同一个项目", "不是同一项目", "两类不同"),
    "CGT25-D-002": ("CGT25-D-002", "DU80L1"),
}


def wilson(success: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    if n <= 0:
        return None
    p = success / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z / denom) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (round(max(0.0, center - half), 3), round(min(1.0, center + half), 3))


def has_key(blob: str, key: str) -> bool:
    for alt in ALTS.get(key, (key,)):
        if alt in blob:
            return True
    if key == "2016" and re.search(r"2016[-./年]?\s*11[-./月]?\s*10", blob):
        return True
    return key in blob


def score_arm(items: dict) -> dict:
    hit = cite = refuse_ok = 0
    by_q = {}
    for q in GOLD["questions"]:
        qid = q["id"]
        row = items[qid]
        blob = row["answer"] + " " + row["source"]
        if q["in_corpus"]:
            keys = q["hit_keys"]
            is_hit = all(has_key(blob, k) for k in keys)
            sources = q["source"] if isinstance(q["source"], list) else [q["source"]]
            is_cite = all(Path(s).name in row["source"] or Path(s).stem in row["source"] for s in sources)
            if qid == "Q6":
                is_cite = ("yandun_july2020" in row["source"] or "2020" in row["source"]) and (
                    "yandun_unit2" in row["source"] or "trip" in row["source"] or "unit2" in row["source"]
                )
            if qid == "Q8":
                is_cite = "hp_turbine" in row["source"] or "coating" in row["source"] or "X25" in blob
            hit += int(is_hit)
            cite += int(is_cite)
            by_q[qid] = {"hit": is_hit, "cite": is_cite, "refuse": None}
        else:
            denied = any(w in row["answer"] for w in ("未记载", "没有", "未写", "未给出", "不在本包"))
            invented = bool(re.search(r"\d+(?:\.\d+)?\s*GW", row["answer"])) if qid == "Q9" else False
            if qid == "Q10":
                invented = invented or ("727" in row["answer"] and "有" in row["answer"] and "没有" not in row["answer"] and "未" not in row["answer"])
            ok = denied and not invented
            refuse_ok += int(ok)
            by_q[qid] = {"hit": None, "cite": None, "refuse": ok}
    return {
        "hit": hit,
        "cite": cite,
        "refuse": refuse_ok,
        "in_corpus_n": 8,
        "ood_n": 2,
        "hit_rate": hit / 8,
        "cite_rate": cite / 8,
        "refuse_rate": refuse_ok / 2,
        "primary": hit + refuse_ok,
        "primary_max": 10,
        "hit_ci95": wilson(hit, 8),
        "cite_ci95": wilson(cite, 8),
        "refuse_ci95": wilson(refuse_ok, 2),
        "by_q": by_q,
    }


def main() -> None:
    ans = json.loads(ANS_PATH.read_text(encoding="utf-8"))
    report = {name: score_arm(payload["items"]) for name, payload in ans.items()}
    out = Path(__file__).with_name("cs_long_scores_computed_20260923.json")
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    printable = {k: {kk: vv for kk, vv in v.items() if kk != "by_q"} for k, v in report.items()}
    print(json.dumps(printable, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
