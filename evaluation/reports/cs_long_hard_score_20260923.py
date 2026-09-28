"""Score hard synthesis exam. Pin is not scored."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

GOLD = json.loads(Path(__file__).with_name("cs_long_hard_gold_20260923.json").read_text(encoding="utf-8"))
ANS_PATH = Path(__file__).with_name("cs_long_hard_answers_20260923.json")

ALTS = {
    "不一致": ("不一致", "不符", "不同", "矛盾", "两处", "打架", "不是同一个"),
    "未返回": ("未返回", "没有返回", "未送回", "没有被送回", "计划随"),
    "不是": ("不是", "并非", "不同口径", "不是同一"),
    "存疑": ("存疑", "真实性", "不可信", "高度相似"),
    "不是同一": (
        "不是同一",
        "不是同一个项目",
        "不是同一条",
        "不能当成同一",
        "不能视为同一",
        "不同项目",
        "不同故障链",
        "独立",
    ),
    "振动疲劳": ("振动疲劳", "振动疲劳失效"),
    "氧化铝": ("氧化铝", "Al2O3", "夹杂"),
    "锥齿轮": ("锥齿轮", "从动锥齿轮"),
    "下部传动箱": ("下部传动箱", "下传动箱", "北极"),
}


def wilson(success: int, n: int, z: float = 1.96):
    if n <= 0:
        return None
    p = success / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z / denom) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (round(max(0.0, center - half), 3), round(min(1.0, center + half), 3))


def has_key(blob: str, key: str) -> bool:
    return any(alt in blob for alt in ALTS.get(key, (key,)))


def score_arm(items: dict) -> dict:
    hit = cite = refuse_ok = 0
    by_q = {}
    for q in GOLD["questions"]:
        qid = q["id"]
        row = items[qid]
        blob = row["answer"] + " " + row["source"]
        if q["in_corpus"]:
            is_hit = all(has_key(blob, k) for k in q["hit_keys"])
            needed = [Path(s).name for s in q["source"]]
            is_cite = all(name in row["source"] or Path(name).stem in row["source"] for name in needed)
            hit += int(is_hit)
            cite += int(is_cite)
            by_q[qid] = {"hit": is_hit, "cite": is_cite, "refuse": None}
        else:
            denied = any(w in row["answer"] for w in ("未记载", "没有", "未写", "未给出"))
            invented = bool(re.search(r"\d+(?:\.\d+)?\s*GW", row["answer"])) if qid == "H11" else False
            if qid == "H12":
                invented = invented or ("727" in row["answer"] and "没有" not in row["answer"] and "未" not in row["answer"])
            ok = denied and not invented
            refuse_ok += int(ok)
            by_q[qid] = {"hit": None, "cite": None, "refuse": ok}
    return {
        "hit": hit,
        "cite": cite,
        "refuse": refuse_ok,
        "in_corpus_n": 10,
        "ood_n": 2,
        "primary": hit + refuse_ok,
        "primary_max": 12,
        "hit_rate": hit / 10,
        "cite_rate": cite / 10,
        "refuse_rate": refuse_ok / 2,
        "hit_ci95": wilson(hit, 10),
        "cite_ci95": wilson(cite, 10),
        "by_q": by_q,
    }


def main() -> None:
    ans = json.loads(ANS_PATH.read_text(encoding="utf-8"))
    report = {name: score_arm(payload["items"]) for name, payload in ans.items()}
    Path(__file__).with_name("cs_long_hard_scores_20260923.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk != "by_q"} for k, v in report.items()}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
