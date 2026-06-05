from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = REPO_ROOT / "docs" / "challenge_cup" / "reproducibility"
OUTPUT_JSON = OUTPUT_DIR / "official_rubric_alignment.json"
OUTPUT_MD = OUTPUT_DIR / "official_rubric_alignment.md"

REPORT_TYPE = "challenge_cup_official_rubric_alignment"

OFFICIAL_SOURCES = [
    {
        "source_id": "tsinghua_44th_2026",
        "title": "清华大学第44届“挑战杯”学生课外学术科技作品竞赛颁奖仪式暨作品展开幕式举行",
        "url": "https://www.tsinghua.edu.cn/info/1177/125861.htm",
        "source_type": "tsinghua_news",
        "checked_at": "2026-06-06",
        "claims": [
            "2026年4月25日开展终审答辩",
            "主赛道共产生114项获奖作品，其中特等奖7项",
            "本届挑战杯共收到报名作品337件",
            "200余件学生科创作品参展",
        ],
    },
    {
        "source_id": "tsinghua_43rd_2025",
        "title": "清华大学第43届“挑战杯”学生课外学术科技作品竞赛颁奖仪式暨作品展开幕式",
        "url": "https://www.tsinghua.edu.cn/info/1176/118626.htm",
        "source_type": "tsinghua_news",
        "checked_at": "2026-06-06",
        "claims": [
            "2025年4月10日开展终审答辩",
            "主赛道特等奖6项",
            "清华挑战杯是学校历史最长、规模最大、水平最高的综合性学生课外学术科技作品竞赛",
            "鼓励立足重要领域的关键应用场景，做勇于创新、善于创新的清华青年",
        ],
    },
    {
        "source_id": "tsinghua_39th_2021",
        "title": "清华大学第39届“挑战杯”学生课外学术科技作品竞赛校级终审落幕",
        "url": "https://www.tsinghua.edu.cn/info/1175/82720.htm",
        "source_type": "tsinghua_news",
        "checked_at": "2026-06-06",
        "claims": [
            "评分维度包括学术/实用价值、创新性、作品完成度、现场答辩及墙报问辩表现",
            "每个分场至多推荐一项作品参加特等奖评比",
            "本届最终评选出特等奖6项",
        ],
    },
    {
        "source_id": "tsinghua_37th_2019",
        "title": "清华大学第37届“挑战杯”学生课外学术科技作品竞赛校级终审落幕",
        "url": "https://www.tsinghua.edu.cn/info/1181/35383.htm",
        "source_type": "tsinghua_news",
        "checked_at": "2026-06-06",
        "claims": [
            "强调遵守比赛规则、恪守学术规范和学术成果表述严谨性",
            "评委从学术价值或实用性、创新性、作品完成情况和现场答辩表现四个方面评分",
            "特等奖候选作品参与公开答辩并由评委综合评定",
        ],
    },
    {
        "source_id": "tsinghua_rules_pdf_2017",
        "title": "清华大学课外创新人才培养体系制度文件汇编",
        "url": "https://qiyuan.tsinghua.edu.cn/intro/2018/11024/%E6%94%AF%E6%92%91%E6%9D%90%E6%96%993-%E6%B8%85%E5%8D%8E%E5%A4%A7%E5%AD%A6%E8%AF%BE%E5%A4%96%E5%88%9B%E6%96%B0%E4%BA%BA%E6%89%8D%E5%9F%B9%E5%85%BB%E4%BD%93%E7%B3%BB%E5%88%B6%E5%BA%A6%E6%96%87%E4%BB%B6%E6%B1%87%E7%BC%96.pdf",
        "source_type": "tsinghua_rules_pdf",
        "checked_at": "2026-06-06",
        "claims": [
            "评审应考虑作品实用性、创新性和学术价值",
            "特等奖不超过6件，可空缺",
            "竞赛规程由清华相关部门和学生科协共同发布",
        ],
    },
]

DIMENSIONS = {
    "academic_or_practical_value": {
        "label": "学术/实用价值",
        "official_source_ids": ["tsinghua_39th_2021", "tsinghua_37th_2019", "tsinghua_rules_pdf_2017"],
        "project_argument": "面向动力装备运维资料知识化，用固定 GT-07 场景证明证据链整理价值。",
        "evidence_files": [
            "docs/challenge_cup/00_项目一页纸.md",
            "docs/challenge_cup/03_实验评测报告.md",
            "docs/challenge_cup/11_应用场景与专家验证.md",
            "docs/challenge_cup/reproducibility/application_validation_report.md",
            "docs/challenge_cup/reproducibility/browser_demo_smoke_report.json",
        ],
    },
    "innovation": {
        "label": "创新性",
        "official_source_ids": ["tsinghua_39th_2021", "tsinghua_37th_2019", "tsinghua_rules_pdf_2017"],
        "project_argument": "不是普通 RAG 页面，而是 evidence-bound GraphRAG、人工补证和失败归因闭环。",
        "evidence_files": [
            "docs/challenge_cup/02_技术白皮书.md",
            "docs/challenge_cup/07_评审主张证据矩阵.md",
            "evaluation/reports/challenge_cup_graphrag_same_question_report.md",
            "evaluation/reports/challenge_cup_graphrag_context_demo.md",
            "evaluation/reports/challenge_cup_graphrag_answer_benchmark.md",
        ],
    },
    "completion": {
        "label": "作品完成度",
        "official_source_ids": ["tsinghua_39th_2021", "tsinghua_37th_2019"],
        "project_argument": "已形成项目书、实验评测、浏览器演示、答辩材料、归档包和机器门禁。",
        "evidence_files": [
            "docs/challenge_cup/package_manifest.json",
            "docs/challenge_cup/reproducibility/readiness_gate_report.md",
            "docs/challenge_cup/reproducibility/challenge_cup_submission_package.zip",
            "docs/challenge_cup/reproducibility/challenge_cup_submission_archive_manifest.json",
            "docs/challenge_cup/reproducibility/runbook.md",
        ],
    },
    "defense_performance": {
        "label": "现场答辩",
        "official_source_ids": ["tsinghua_39th_2021", "tsinghua_37th_2019"],
        "project_argument": "用 10 页终审 deck、讲稿、彩排计分卡和硬证据台账支撑现场表达。",
        "evidence_files": [
            "docs/challenge_cup/defense_deck/challenge_cup_defense_deck.pptx",
            "docs/challenge_cup/defense_deck/challenge_cup_defense_speaker_notes.md",
            "docs/challenge_cup/reproducibility/defense_rehearsal_scorecard.md",
            "docs/challenge_cup/reproducibility/defense_rehearsal_result_packet.md",
            "docs/challenge_cup/reproducibility/hard_evidence_ledger.md",
        ],
    },
    "academic_norms_and_rigor": {
        "label": "学术规范与严谨表述",
        "official_source_ids": ["tsinghua_37th_2019"],
        "project_argument": "所有高水平主张绑定证据和边界，不把 readiness gate、内部自评或准备包说成获奖保证/外部背书。",
        "evidence_files": [
            "docs/challenge_cup/05_答辩问答手册.md",
            "docs/challenge_cup/08_特等奖评审自评表.md",
            "docs/challenge_cup/reproducibility/expert_feedback_request_packet.md",
            "docs/challenge_cup/reproducibility/hard_evidence_ledger.json",
        ],
    },
}


def build_payload() -> dict[str, Any]:
    return {
        "report_type": REPORT_TYPE,
        "checked_at": "2026-06-06",
        "official_source_count": len(OFFICIAL_SOURCES),
        "official_sources": OFFICIAL_SOURCES,
        "dimensions": DIMENSIONS,
        "special_prize_policy": {
            "max_special_prize_count": 7,
            "may_be_vacant": True,
            "source_ids": [
                "tsinghua_44th_2026",
                "tsinghua_rules_pdf_2017",
                "tsinghua_39th_2021",
                "tsinghua_43rd_2025",
            ],
            "latest_public_result_source_id": "tsinghua_44th_2026",
            "historical_rule_note": "2017制度文件写有特等奖不超过6件、可空缺；2026年第44届公开报道显示主赛道实际特等奖7项，材料以最新公开结果为准并保留历史口径说明。",
            "project_boundary": "本项目只能证明材料与答辩准备对齐官方口径；不承诺获奖结果。",
        },
        "integrity_rules": {
            "no_award_guarantee": True,
            "no_fake_external_validation": True,
            "source_backed_claims_only": True,
            "must_disclose_unfinished_external_feedback_and_rehearsal": True,
        },
        "rerun_commands": [
            "python scripts/build_challenge_cup_official_rubric_alignment.py",
            "python scripts/build_challenge_cup_package.py",
            "python scripts/check_challenge_cup_readiness.py",
        ],
    }


def write_markdown(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# 官方评审口径对齐表",
        "",
        "本表把清华“挑战杯”公开报道和制度文件中的评审口径转化为本项目的可核验证据路线。它不承诺获奖，只用于倒逼材料、演示和边界表达贴近官方尺度。",
        "",
        f"- report_type: `{payload['report_type']}`",
        f"- checked_at: `{payload['checked_at']}`",
        f"- official_source_count: `{payload['official_source_count']}`",
        "- 第44届（2026）主赛道公开结果：特等奖7项；历史制度口径可能变化；本项目不承诺获奖。",
        "",
        "## 官方来源",
        "",
    ]
    for source in payload["official_sources"]:
        lines.extend(
            [
                f"### {source['source_id']}",
                f"- Title: {source['title']}",
                f"- URL: {source['url']}",
                f"- Checked at: {source['checked_at']}",
            ]
        )
        lines.extend(f"- Claim: {claim}" for claim in source["claims"])
        lines.append("")

    lines.extend(["## 维度对齐", "", "| 官方维度 | 项目主张 | 证据文件 |", "| --- | --- | --- |"])
    for item in payload["dimensions"].values():
        evidence = "<br>".join(f"`{path}`" for path in item["evidence_files"])
        lines.append(f"| {item['label']} | {item['project_argument']} | {evidence} |")
    lines.extend(
        [
            "",
            "## 诚信边界",
            "",
            "- 不承诺获奖，不把 readiness gate 说成获奖保证。",
            "- 不伪造外部验证，不把内部自评写成专家背书。",
            "- 未归档真实专家反馈和真实计时彩排前，必须在答辩中主动说明。",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def write_outputs(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or build_payload()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown(OUTPUT_MD, payload)
    return payload


def main() -> int:
    payload = write_outputs()
    print(f"official rubric alignment: {OUTPUT_MD.relative_to(REPO_ROOT)}")
    print(f"official sources: {payload['official_source_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
