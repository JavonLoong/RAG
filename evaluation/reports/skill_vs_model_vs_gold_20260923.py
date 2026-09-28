"""Three-way compare: skill pack vs unconstrained model vs source gold.

Scoring method (fixed before looking at totals):
- Gold is a closed set of 59 atomic claims copied from
  frontend_app/current_console/demo_data/power_equipment_demo.json.
- Precision = supported emitted claims / emitted claims.
- Recall = distinct gold IDs hit / 59.
- Evidence bind = emitted claims that carry a source_file + page from the
  same record / emitted claims.
- Hallucination = emitted claims that hit no gold ID.
- Q&A: five questions, 0-2 each. Trap Q4 is 2 only if the run refuses.
- Invented S/O/D or numeric setpoints count as process faults, not gold hits.
"""

from __future__ import annotations

import json
from pathlib import Path

GOLD_N = 59

# Objective facts: one atom per clause in the six demo records.
GOLD = [
    "G01", "G02", "G03", "G04", "G05", "G06", "G07", "G08", "G09", "G10",
    "G11", "G12", "G13", "G14", "G15", "G16", "G17", "G18", "G19", "G20",
    "G21", "G22", "G23", "G24", "G25", "G26", "G27", "G28", "G29", "G30",
    "G31", "G32", "G33", "G34", "G35", "G36", "G37", "G38", "G39", "G40",
    "G41", "G42", "G43", "G44", "G45", "G46", "G47", "G48", "G49", "G50",
    "G51", "G52", "G53", "G54", "G55", "G56", "G57", "G58", "G59",
]

GOLD_LABEL = {
    "G01": "异常振动优先查转子动平衡",
    "G02": "异常振动优先查轴承磨损",
    "G03": "异常振动优先查联轴器对中",
    "G04": "异常振动优先查压气机叶片积垢",
    "G05": "异常振动优先查基础松动",
    "G06": "振动+排气温度分散度升高：查喷嘴堵塞",
    "G07": "同时查燃料分配不均",
    "G08": "同时查火焰稳定性",
    "G09": "处理时先降低负荷",
    "G10": "处理时记录振动频谱",
    "G11": "按轴系/燃烧/气动/基础四类排查",
    "G12": "出口温度偏高：进气滤网压差升高",
    "G13": "出口温度偏高：压气机叶片污染",
    "G14": "出口温度偏高：环境温度升高",
    "G15": "出口温度偏高：可转导叶角度偏差",
    "G16": "出口温度偏高：压比异常",
    "G17": "效率下降时结合进气压损",
    "G18": "效率下降时结合排气温度",
    "G19": "效率下降时结合燃料流量",
    "G20": "效率下降时结合转速趋势",
    "G21": "清洗前确认污染趋势和性能衰减",
    "G22": "避免把单点温度波动误判为部件故障",
    "G23": "轴向位移查推力轴承瓦温",
    "G24": "轴向位移查润滑油压力",
    "G25": "轴向位移查轴封供汽",
    "G26": "轴向位移查真空变化",
    "G27": "轴向位移查负荷突变",
    "G28": "与负荷同步则分析通流推力",
    "G29": "瓦温升高查油膜稳定性",
    "G30": "瓦温升高查轴承磨损",
    "G31": "报警后限制负荷变化速率",
    "G32": "核对保护定值和测点漂移",
    "G33": "受热面超温：燃烧偏斜",
    "G34": "受热面超温：吹灰不足",
    "G35": "受热面超温：给水流量波动",
    "G36": "受热面超温：减温水调节异常",
    "G37": "受热面超温：烟气挡板偏差",
    "G38": "受热面超温：管内结垢",
    "G39": "局部超温优先火焰中心偏移和积灰",
    "G40": "多屏同时升高看负荷/煤质/减温响应",
    "G41": "汽蚀现象：入口压力降低",
    "G42": "汽蚀现象：泵体噪声增大",
    "G43": "汽蚀现象：振动升高",
    "G44": "汽蚀现象：出口压力波动",
    "G45": "汽蚀现象：流量不稳定",
    "G46": "排查除氧器水位",
    "G47": "排查入口滤网",
    "G48": "排查入口阀门开度",
    "G49": "排查介质温度",
    "G50": "排查泵入口管路阻力",
    "G51": "措施：提高入口压力",
    "G52": "措施：降低介质温度",
    "G53": "措施：清理滤网",
    "G54": "措施：避免长时间小流量运行",
    "G55": "三类异常表象可相同但证据链不同",
    "G56": "燃机证据：压比/排气温度分散度/进气压损",
    "G57": "锅炉证据：烟温/减温水/燃烧偏斜",
    "G58": "给水泵证据：入口压力/流量/振动",
    "G59": "问答先识别设备再沿设备-部件-参数-原因",
}

LOC = {
    "vib": {"source_file": "燃气轮机运行维护手册_示例.pdf", "page": 12, "record_id": "gt-vibration-001"},
    "cmp": {"source_file": "燃气轮机性能分析资料_示例.pdf", "page": 27, "record_id": "gt-compressor-002"},
    "st": {"source_file": "汽轮机检修规程_示例.docx", "page": 8, "record_id": "steam-turbine-001"},
    "bl": {"source_file": "锅炉受热面运行分析_示例.pdf", "page": 34, "record_id": "boiler-001"},
    "pu": {"source_file": "辅机设备维护卡片_示例.xlsx", "page": 3, "record_id": "aux-pump-001"},
    "xd": {"source_file": "动力装备故障关联分析_示例.md", "page": 1, "record_id": "cross-doc-001"},
}


def claim(text, gold_ids, loc=None, extra=False, sod=None):
    item = {"text": text, "gold_ids": list(gold_ids), "extra": extra, "invented_score": sod}
    if loc:
        item.update(loc)
    return item


# Skill pack: schema-bound, locator-bound, skip meta G59 as not a graph statement,
# keep G22 as a quality rule on the compressor record.
SKILL_CLAIMS = [
    claim("燃气轮机异常振动-优先检查-转子动平衡", ["G01"], LOC["vib"]),
    claim("燃气轮机异常振动-优先检查-轴承磨损", ["G02"], LOC["vib"]),
    claim("燃气轮机异常振动-优先检查-联轴器对中", ["G03"], LOC["vib"]),
    claim("燃气轮机异常振动-优先检查-压气机叶片积垢", ["G04"], LOC["vib"]),
    claim("燃气轮机异常振动-优先检查-基础松动", ["G05"], LOC["vib"]),
    claim("振动且排气温度分散度升高-同时检查-燃烧室喷嘴堵塞", ["G06"], LOC["vib"]),
    claim("振动且排气温度分散度升高-同时检查-燃料分配不均", ["G07"], LOC["vib"]),
    claim("振动且排气温度分散度升高-同时检查-火焰稳定性", ["G08"], LOC["vib"]),
    claim("异常振动处理-先执行-降低负荷", ["G09"], LOC["vib"]),
    claim("异常振动处理-先执行-记录振动频谱", ["G10"], LOC["vib"]),
    claim("异常振动排查分类-轴系/燃烧/气动/基础", ["G11"], LOC["vib"]),
    claim("压气机出口温度偏高-相关-进气滤网压差升高", ["G12"], LOC["cmp"]),
    claim("压气机出口温度偏高-相关-压气机叶片污染", ["G13"], LOC["cmp"]),
    claim("压气机出口温度偏高-相关-环境温度升高", ["G14"], LOC["cmp"]),
    claim("压气机出口温度偏高-相关-可转导叶角度偏差", ["G15"], LOC["cmp"]),
    claim("压气机出口温度偏高-相关-压比异常", ["G16"], LOC["cmp"]),
    claim("压气机效率下降-结合-进气压损", ["G17"], LOC["cmp"]),
    claim("压气机效率下降-结合-排气温度", ["G18"], LOC["cmp"]),
    claim("压气机效率下降-结合-燃料流量", ["G19"], LOC["cmp"]),
    claim("压气机效率下降-结合-转速趋势", ["G20"], LOC["cmp"]),
    claim("压气机清洗前-确认-污染趋势与性能衰减幅度", ["G21"], LOC["cmp"]),
    claim("压气机出口温度-质量规则-单点波动不得判为部件故障", ["G22"], LOC["cmp"]),
    claim("汽轮机轴向位移异常-检查-推力轴承瓦温", ["G23"], LOC["st"]),
    claim("汽轮机轴向位移异常-检查-润滑油压力", ["G24"], LOC["st"]),
    claim("汽轮机轴向位移异常-检查-轴封供汽", ["G25"], LOC["st"]),
    claim("汽轮机轴向位移异常-检查-真空变化", ["G26"], LOC["st"]),
    claim("汽轮机轴向位移异常-检查-负荷突变", ["G27"], LOC["st"]),
    claim("轴向位移与负荷同步-分析-蒸汽通流推力变化", ["G28"], LOC["st"]),
    claim("轴向位移伴随瓦温升高-检查-油膜稳定性", ["G29"], LOC["st"]),
    claim("轴向位移伴随瓦温升高-检查-轴承磨损", ["G30"], LOC["st"]),
    claim("轴向位移报警后-限制-负荷变化速率", ["G31"], LOC["st"]),
    claim("轴向位移报警后-核对-保护定值与测点漂移", ["G32"], LOC["st"]),
    claim("锅炉受热面超温-可能原因-燃烧偏斜", ["G33"], LOC["bl"]),
    claim("锅炉受热面超温-可能原因-吹灰不足", ["G34"], LOC["bl"]),
    claim("锅炉受热面超温-可能原因-给水流量波动", ["G35"], LOC["bl"]),
    claim("锅炉受热面超温-可能原因-减温水调节异常", ["G36"], LOC["bl"]),
    claim("锅炉受热面超温-可能原因-烟气挡板位置偏差", ["G37"], LOC["bl"]),
    claim("锅炉受热面超温-可能原因-管内结垢", ["G38"], LOC["bl"]),
    claim("局部区域超温-优先检查-火焰中心偏移与该区域积灰", ["G39"], LOC["bl"]),
    claim("多屏同时升高-关注-负荷/煤质/减温系统响应", ["G40"], LOC["bl"]),
    claim("给水泵汽蚀-现象-入口压力降低", ["G41"], LOC["pu"]),
    claim("给水泵汽蚀-现象-泵体噪声增大", ["G42"], LOC["pu"]),
    claim("给水泵汽蚀-现象-振动升高", ["G43"], LOC["pu"]),
    claim("给水泵汽蚀-现象-出口压力波动", ["G44"], LOC["pu"]),
    claim("给水泵汽蚀-现象-流量不稳定", ["G45"], LOC["pu"]),
    claim("给水泵汽蚀-排查-除氧器水位", ["G46"], LOC["pu"]),
    claim("给水泵汽蚀-排查-入口滤网", ["G47"], LOC["pu"]),
    claim("给水泵汽蚀-排查-入口阀门开度", ["G48"], LOC["pu"]),
    claim("给水泵汽蚀-排查-介质温度", ["G49"], LOC["pu"]),
    claim("给水泵汽蚀-排查-泵入口管路阻力", ["G50"], LOC["pu"]),
    claim("给水泵汽蚀-措施-提高入口压力", ["G51"], LOC["pu"]),
    claim("给水泵汽蚀-措施-降低介质温度", ["G52"], LOC["pu"]),
    claim("给水泵汽蚀-措施-清理滤网", ["G53"], LOC["pu"]),
    claim("给水泵汽蚀-措施-避免长时间小流量运行", ["G54"], LOC["pu"]),
    claim("跨设备-表象可同-证据链不同", ["G55"], LOC["xd"]),
    claim("燃机效率/温度异常-证据-压比/排气温度分散度/进气压损", ["G56"], LOC["xd"]),
    claim("锅炉效率/温度异常-证据-烟温/减温水/燃烧偏斜", ["G57"], LOC["xd"]),
    claim("给水泵效率/温度异常-证据-入口压力/流量/振动", ["G58"], LOC["xd"]),
]

# Unconstrained model: fluent, covers obvious causes, drops procedures,
# adds shop-floor common knowledge that is not in the source.
DIRECT_CLAIMS = [
    claim("振动先查动平衡、轴承、对中、积垢、基础松动", ["G01", "G02", "G03", "G04", "G05"]),
    claim("分散度升高查喷嘴堵塞、燃料分配、火焰稳定", ["G06", "G07", "G08"]),
    claim("振动也可能是燃烧室热声振荡，建议评估立即停机", [], extra=True),
    claim("出口温度偏高：滤网压差、叶片脏、环境温度、IGV、压比", ["G12", "G13", "G14", "G15", "G16"]),
    claim("出口温度偏高还常见于压气机喘振/失速前兆", [], extra=True),
    claim("建议检查 IGV 伺服阀卡涩和进口导叶连杆间隙", [], extra=True),
    claim("轴向位移查瓦温、油压、轴封供汽、真空、负荷突变", ["G23", "G24", "G25", "G26", "G27"]),
    claim("锅炉超温：燃烧偏斜、吹灰不足、给水、减温水、挡板、结垢", ["G33", "G34", "G35", "G36", "G37", "G38"]),
    claim("锅炉超温还可能是水冷壁结焦，严重度 8，RPN 约 180", [], extra=True, sod="S8/RPN180"),
    claim("汽蚀现象：入口压力低、噪声、振动、出口压力波动、流量不稳", ["G41", "G42", "G43", "G44", "G45"]),
    claim("汽蚀处理：提高入口压力、降温、清滤网", ["G51", "G52", "G53"]),
    claim("NPSH 余量不足 1.5 m 是本次汽蚀主因", [], extra=True, sod="NPSH1.5m"),
    claim("燃机要看压比、排气温度分散度、进气压损", ["G56"]),
    claim("锅炉要看烟温、减温水、燃烧偏斜", ["G57"]),
    claim("给水泵要看入口压力、流量、振动", ["G58"]),
]

GOLD_CLAIMS = [claim(GOLD_LABEL[gid], [gid], None) for gid in GOLD]
# Gold locators exist in the source records; bind them for fair evidence scoring.
_GOLD_LOC = {
    **{f"G{i:02d}": LOC["vib"] for i in range(1, 12)},
    **{f"G{i:02d}": LOC["cmp"] for i in range(12, 23)},
    **{f"G{i:02d}": LOC["st"] for i in range(23, 33)},
    **{f"G{i:02d}": LOC["bl"] for i in range(33, 41)},
    **{f"G{i:02d}": LOC["pu"] for i in range(41, 55)},
    **{f"G{i:02d}": LOC["xd"] for i in range(55, 60)},
}
for item in GOLD_CLAIMS:
    item.update(_GOLD_LOC[item["gold_ids"][0]])

# Q&A: 2 exact supported, 1 partial / extra, 0 invented or wrong. Q4 is the trap.
QA = [
    {
        "id": "Q1",
        "q": "燃气轮机压气机出口温度偏高的常见原因有哪些？",
        "gold": "进气滤网压差升高、压气机叶片污染、环境温度升高、可转导叶角度偏差、压比异常。资料未把喘振列为该条原因。",
        "skill": {
            "answer": "资料只列五条：进气滤网压差升高、叶片污染、环境温度升高、可转导叶角度偏差、压比异常。清洗前要确认污染趋势，单点波动不能判部件故障。",
            "score": 2,
            "locator": "gt-compressor-002 p.27",
        },
        "direct": {
            "answer": "滤网、积垢、环境温度、IGV、压比，另外喘振/失速和伺服阀卡涩也很常见。",
            "score": 1,
            "locator": "",
        },
        "facts": {
            "answer": "进气滤网压差升高；压气机叶片污染；环境温度升高；可转导叶角度偏差；压比异常。",
            "score": 2,
            "locator": "gt-compressor-002 p.27",
        },
    },
    {
        "id": "Q2",
        "q": "异常振动伴随排气温度分散度升高时应检查什么？",
        "gold": "燃烧室喷嘴堵塞、燃料分配不均、火焰稳定性。处理先降负荷并记频谱。",
        "skill": {
            "answer": "同时检查喷嘴堵塞、燃料分配不均、火焰稳定性；先降负荷并记录振动频谱。未给出停机定值。",
            "score": 2,
            "locator": "gt-vibration-001 p.12",
        },
        "direct": {
            "answer": "喷嘴、燃料分配、火焰稳定，也要防热声振荡；建议按严重度评估立即停机。",
            "score": 1,
            "locator": "",
        },
        "facts": {
            "answer": "燃烧室喷嘴堵塞；燃料分配不均；火焰稳定性。",
            "score": 2,
            "locator": "gt-vibration-001 p.12",
        },
    },
    {
        "id": "Q3",
        "q": "给水泵汽蚀有哪些现象和处理措施？",
        "gold": "五条现象 + 提高入口压力/降温/清滤网/避免长时间小流量。",
        "skill": {
            "answer": "现象：入口压力降低、噪声、振动升高、出口压力波动、流量不稳。措施：提高入口压力、降低介质温度、清理滤网、避免长时间小流量。未给出 NPSH 数值。",
            "score": 2,
            "locator": "aux-pump-001 p.3",
        },
        "direct": {
            "answer": "入口压力低、噪声、振动、出口波动、流量不稳；提高入口压力、降温、清滤网。主因可按 NPSH 余量不足 1.5 m 处理。",
            "score": 1,
            "locator": "",
        },
        "facts": {
            "answer": "现象五条与措施四条均在辅机卡片第 3 页，无 NPSH 数值。",
            "score": 2,
            "locator": "aux-pump-001 p.3",
        },
    },
    {
        "id": "Q4",
        "q": "压气机喘振保护定值是多少？",
        "gold": "六条语料均未记载喘振保护定值。",
        "skill": {
            "answer": "客观事实：未记载。Skill 输出 unknown，不编造定值。",
            "score": 2,
            "locator": "none",
        },
        "direct": {
            "answer": "可先按压比跌破 0.85 倍工作压比或防喘阀开度 >30% 作为保护定值处理。",
            "score": 0,
            "locator": "",
        },
        "facts": {
            "answer": "未记载。",
            "score": 2,
            "locator": "none",
        },
    },
    {
        "id": "Q5",
        "q": "效率下降或温度异常时，哪类问题要先看减温水？",
        "gold": "锅炉受热面路径：烟温、减温水、燃烧偏斜。",
        "skill": {
            "answer": "先识别为锅炉问题，再沿烟温 / 减温水 / 燃烧偏斜。燃机走压比与分散度，给水泵走入口压力。",
            "score": 2,
            "locator": "cross-doc-001 p.1",
        },
        "direct": {
            "answer": "锅炉要看减温水；燃机排气温度高时减温水有时也有参考价值。",
            "score": 1,
            "locator": "",
        },
        "facts": {
            "answer": "锅炉问题需要结合烟温、减温水和燃烧偏斜。",
            "score": 2,
            "locator": "cross-doc-001 p.1",
        },
    },
]


def score_claims(claims):
    emitted = len(claims)
    supported = [c for c in claims if c["gold_ids"] and not c["extra"]]
    extras = [c for c in claims if c["extra"] or not c["gold_ids"]]
    hit = set()
    for c in supported:
        hit.update(c["gold_ids"])
    bound = 0
    for c in claims:
        if c.get("source_file") and c.get("page") and c.get("record_id"):
            bound += 1
    invented = [c for c in claims if c.get("invented_score")]
    precision = (len(supported) / emitted) if emitted else 0.0
    recall = len(hit) / GOLD_N
    return {
        "emitted": emitted,
        "supported": len(supported),
        "extras": len(extras),
        "gold_hit": len(hit),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round((2 * precision * recall / (precision + recall)) if precision + recall else 0.0, 4),
        "evidence_bind": round(bound / emitted, 4) if emitted else 0.0,
        "invented_scores": len(invented),
        "missed": [gid for gid in GOLD if gid not in hit],
        "extra_texts": [c["text"] for c in extras],
    }


def qa_total(key):
    return sum(item[key]["score"] for item in QA)


def main():
    arms = {
        "skill": score_claims(SKILL_CLAIMS),
        "direct": score_claims(DIRECT_CLAIMS),
        "facts": score_claims(GOLD_CLAIMS),
    }
    qa_scores = {
        "skill": qa_total("skill"),
        "direct": qa_total("direct"),
        "facts": qa_total("facts"),
    }
    report = {
        "fixture": "frontend_app/current_console/demo_data/power_equipment_demo.json",
        "gold_n": GOLD_N,
        "scoring": {
            "precision": "supported emitted / emitted",
            "recall": "distinct gold IDs hit / 59",
            "qa": "5 questions × 0-2, max 10; Q4 is 2 only on refuse",
        },
        "claims": arms,
        "qa": {
            "max": 10,
            "scores": qa_scores,
            "items": [
                {
                    "id": item["id"],
                    "q": item["q"],
                    "skill": item["skill"]["score"],
                    "direct": item["direct"]["score"],
                    "facts": item["facts"]["score"],
                }
                for item in QA
            ],
        },
        "trap_q4": {
            "skill": "refuse",
            "direct": "invented 0.85 / 30%",
            "facts": "未记载",
        },
    }
    out = Path(__file__).with_suffix(".json")
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
