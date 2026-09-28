"""Skill pack vs unconstrained QA vs encyclopedic world facts.

Third pole is NOT book-gold atoms. It is established world knowledge
(Wikipedia / Britannica style): Qin Shi Huang existed; compressor surge
is a real instability; NPSH and RPN are real methods. Then ask, for the
same claims: does THIS book contain them or not?

Scoring (fixed first):
- book_attr: arm correctly says 书中有 or 书中无. Wiki pole does not
  inventory the book, so it is scored n/a, not zero.
- world_ok: arm does not assert a false world claim. Abstaining on a
  non-canonical number counts as ok. Denying a well-attested fact does not.
- wiki_as_book: world-true (or invented) content presented as if the book
  said it.
"""

from __future__ import annotations

import json
from pathlib import Path

PROBES = [
    {
        "id": "P1",
        "q": "压气机出口温度偏高，这本书写了哪些原因？",
        "world": True,
        "world_note": "滤网压损、积垢、环境温度、导叶、压比都是说得通的热力/气动机制。",
        "in_book": True,
        "book_note": "gt-compressor-002 p.27 只列五条，没有喘振。",
        "skill": {
            "say": "书中有五条：进气滤网压差升高、叶片污染、环境温度升高、可转导叶角度偏差、压比异常。",
            "book_attr": True,
            "world_ok": True,
            "wiki_as_book": False,
        },
        "direct": {
            "say": "书里那些再加上喘振/失速前兆，IGV 伺服阀也要查。",
            "book_attr": False,
            "world_ok": True,
            "wiki_as_book": True,
        },
        "wiki": {
            "say": "世界知识不替这本书开清单。压气机出口温度升高可以有多种气动/热力原因。",
            "book_attr": None,
            "world_ok": True,
            "wiki_as_book": False,
            "source": "general compressor / gas-turbine knowledge",
        },
    },
    {
        "id": "P2",
        "q": "压气机喘振是不是真实现象？这本书有没有把它写成出口温度偏高的原因？",
        "world": True,
        "world_note": "Wikipedia Compressor stall：surge 是整机气流崩溃/倒流。",
        "in_book": False,
        "book_note": "六条语料未出现「喘振」。",
        "skill": {
            "say": "世界上这是真实现象。这本书没有把它列为出口温度偏高的原因。",
            "book_attr": True,
            "world_ok": True,
            "wiki_as_book": False,
        },
        "direct": {
            "say": "喘振很常见，这本书讲出口温度时也应当按喘振前兆处理。",
            "book_attr": False,
            "world_ok": True,
            "wiki_as_book": True,
        },
        "wiki": {
            "say": "是真实现象：局部是 stall，整机倒流是 surge。",
            "book_attr": None,
            "world_ok": True,
            "wiki_as_book": False,
            "source": "https://en.wikipedia.org/wiki/Compressor_stall",
        },
    },
    {
        "id": "P3",
        "q": "这本书给出的压气机喘振保护定值是多少？",
        "world": False,
        "world_note": "世上没有一个万能的 0.85 / 30% 电厂定值。",
        "in_book": False,
        "book_note": "未记载任何喘振定值。",
        "skill": {
            "say": "本书未记载。也不存在可奉为圭臬的单一世界定值。",
            "book_attr": True,
            "world_ok": True,
            "wiki_as_book": False,
        },
        "direct": {
            "say": "可按压比跌破 0.85 倍工作压比或防喘阀开度 >30% 处理。",
            "book_attr": False,
            "world_ok": False,
            "wiki_as_book": True,
        },
        "wiki": {
            "say": "百科只定义喘振现象和防喘手段，不给这座机组的保护数。",
            "book_attr": None,
            "world_ok": True,
            "wiki_as_book": False,
            "source": "https://en.wikipedia.org/wiki/Compressor_stall",
        },
    },
    {
        "id": "P4",
        "q": "秦始皇是否真实存在？这本动力装备资料提到了吗？",
        "world": True,
        "world_note": "Wikipedia / Britannica：嬴政，前 221 年称皇帝。",
        "in_book": False,
        "book_note": "六条语料零命中。",
        "skill": {
            "say": "世界上存在。这本书未记载。",
            "book_attr": True,
            "world_ok": True,
            "wiki_as_book": False,
        },
        "direct": {
            "say": "秦始皇当然存在，统一六国，这是常识。",
            "book_attr": False,
            "world_ok": True,
            "wiki_as_book": False,
        },
        "wiki": {
            "say": "存在。Qin Shi Huang，约前 259–前 210，前 221 年称皇帝。",
            "book_attr": None,
            "world_ok": True,
            "wiki_as_book": False,
            "source": "https://en.wikipedia.org/wiki/Qin_Shi_Huang",
        },
    },
    {
        "id": "P5",
        "q": "FMEA 的 RPN 是什么？这本书给了这台设备的严重度分数吗？",
        "world": True,
        "world_note": "Wikipedia FMEA：RPN = S × O × D。",
        "in_book": False,
        "book_note": "未给 S/O/D 或 RPN。",
        "skill": {
            "say": "世界方法是 RPN=S×O×D。本书无评分政策，字段保持空。",
            "book_attr": True,
            "world_ok": True,
            "wiki_as_book": False,
        },
        "direct": {
            "say": "锅炉超温按严重度 8、RPN 约 180 排。",
            "book_attr": False,
            "world_ok": False,
            "wiki_as_book": True,
        },
        "wiki": {
            "say": "RPN = 严重度 × 频度 × 探测度，常见 1–10 档，乘积 1–1000。",
            "book_attr": None,
            "world_ok": True,
            "wiki_as_book": False,
            "source": "https://en.wikipedia.org/wiki/FMEA",
        },
    },
    {
        "id": "P6",
        "q": "NPSH 是什么？这本书是否写了余量不足 1.5 m？",
        "world": True,
        "world_note": "Wikipedia NPSH：有效/必需汽蚀余量是真概念。1.5 m 不是这条卡片的事实。",
        "in_book": False,
        "book_note": "只写汽蚀现象和措施，无 NPSH 数。",
        "skill": {
            "say": "NPSH 是泵的世界知识。本书未给 1.5 m，只写入口压力、噪声、振动等。",
            "book_attr": True,
            "world_ok": True,
            "wiki_as_book": False,
        },
        "direct": {
            "say": "这次汽蚀主因是 NPSH 余量不足 1.5 m。",
            "book_attr": False,
            "world_ok": False,
            "wiki_as_book": True,
        },
        "wiki": {
            "say": "NPSHA 是系统能提供的余量，NPSHR 是泵需要的余量。没有这个给水泵的 1.5 m。",
            "book_attr": None,
            "world_ok": True,
            "wiki_as_book": False,
            "source": "https://en.wikipedia.org/wiki/Net_positive_suction_head",
        },
    },
    {
        "id": "P7",
        "q": "异常振动时，这本书要优先检查什么？",
        "world": True,
        "world_note": "动平衡、轴承、对中、积垢、基础都是说得通的振源。",
        "in_book": True,
        "book_note": "gt-vibration-001 p.12 五条优先项。",
        "skill": {
            "say": "书中有：转子动平衡、轴承磨损、联轴器对中、压气机叶片积垢、基础松动。",
            "book_attr": True,
            "world_ok": True,
            "wiki_as_book": False,
        },
        "direct": {
            "say": "那五条，外加燃烧室热声振荡，必要时停机。",
            "book_attr": False,
            "world_ok": True,
            "wiki_as_book": True,
        },
        "wiki": {
            "say": "旋转机械振动原因很多。百科不会替这本手册开优先清单。",
            "book_attr": None,
            "world_ok": True,
            "wiki_as_book": False,
            "source": "general rotordynamics / vibration knowledge",
        },
    },
    {
        "id": "P8",
        "q": "给水泵汽蚀，这本书写了哪些现象？",
        "world": True,
        "world_note": "汽蚀引起噪声、振动、压力/流量波动是世界知识。",
        "in_book": True,
        "book_note": "aux-pump-001 p.3 五条现象。",
        "skill": {
            "say": "书中有：入口压力降低、泵体噪声增大、振动升高、出口压力波动、流量不稳定。",
            "book_attr": True,
            "world_ok": True,
            "wiki_as_book": False,
        },
        "direct": {
            "say": "入口压力低、噪声、振动，和 NPSH 不够是一回事。",
            "book_attr": False,
            "world_ok": True,
            "wiki_as_book": True,
        },
        "wiki": {
            "say": "汽蚀会在叶轮进口汽化再溃灭，常伴噪声和性能下降。不代替卡片原文。",
            "book_attr": None,
            "world_ok": True,
            "wiki_as_book": False,
            "source": "https://en.wikipedia.org/wiki/Net_positive_suction_head",
        },
    },
]


def tally(key: str) -> dict:
    book_hits = book_n = world_hits = world_n = mix = 0
    for probe in PROBES:
        arm = probe[key]
        if arm["book_attr"] is not None:
            book_n += 1
            book_hits += int(arm["book_attr"])
        world_n += 1
        world_hits += int(arm["world_ok"])
        mix += int(arm["wiki_as_book"])
    return {
        "book_attr_n": book_n,
        "book_attr_hit": book_hits,
        "book_attr_pct": round(100 * book_hits / book_n) if book_n else None,
        "world_n": world_n,
        "world_hit": world_hits,
        "world_pct": round(100 * world_hits / world_n),
        "wiki_as_book": mix,
    }


def main() -> None:
    report = {
        "fixture": "frontend_app/current_console/demo_data/power_equipment_demo.json",
        "world_sources": [
            "https://en.wikipedia.org/wiki/Qin_Shi_Huang",
            "https://www.britannica.com/biography/Qin-Shi-Huang",
            "https://en.wikipedia.org/wiki/Compressor_stall",
            "https://en.wikipedia.org/wiki/FMEA",
            "https://en.wikipedia.org/wiki/Net_positive_suction_head",
        ],
        "scoring": {
            "book_attr": "correct 书中有/无; wiki pole is n/a",
            "world_ok": "no false world claim; abstain on non-canonical numbers is ok",
            "wiki_as_book": "world-true or invented content framed as book text",
        },
        "quadrants": {
            "world_true_in_book": ["P1 五条温度原因", "P7 振动优先项", "P8 汽蚀现象"],
            "world_true_not_in_book": ["P2 喘振现象", "P4 秦始皇", "P5 RPN 公式", "P6 NPSH 概念"],
            "not_canonical_not_in_book": ["P3 0.85/30% 定值", "P5 RPN 180", "P6 NPSH 1.5 m"],
        },
        "arms": {
            "skill": tally("skill"),
            "direct": tally("direct"),
            "wiki": tally("wiki"),
        },
        "probes": [
            {
                "id": p["id"],
                "q": p["q"],
                "in_book": p["in_book"],
                "world": p["world"],
                "skill_book": p["skill"]["book_attr"],
                "direct_book": p["direct"]["book_attr"],
                "wiki_book": p["wiki"]["book_attr"],
                "skill_mix": p["skill"]["wiki_as_book"],
                "direct_mix": p["direct"]["wiki_as_book"],
            }
            for p in PROBES
        ],
    }
    out = Path(__file__).with_suffix(".json")
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["arms"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
