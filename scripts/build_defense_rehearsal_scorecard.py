from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = REPO_ROOT / "docs" / "challenge_cup" / "reproducibility"
OUTPUT_JSON = OUTPUT_DIR / "defense_rehearsal_scorecard.json"
OUTPUT_MD = OUTPUT_DIR / "defense_rehearsal_scorecard.md"

REPORT_TYPE = "challenge_cup_defense_rehearsal_scorecard"
STATUS = "ready_for_timed_rehearsal"
BOUNDARY = (
    "This scorecard proves rehearsal readiness and evidence anchors; it does not prove a live defense "
    "has already happened or guarantee an award."
)


EVIDENCE_FILES = [
    "docs/challenge_cup/00_项目一页纸.md",
    "docs/challenge_cup/03_实验评测报告.md",
    "docs/challenge_cup/04_系统演示脚本.md",
    "docs/challenge_cup/05_答辩问答手册.md",
    "docs/challenge_cup/07_评审主张证据矩阵.md",
    "docs/challenge_cup/08_特等奖评审自评表.md",
    "docs/challenge_cup/10_答辩攻防与彩排卡.md",
    "docs/challenge_cup/reproducibility/browser_demo_smoke_report.md",
    "docs/challenge_cup/reproducibility/application_validation_report.md",
    "docs/challenge_cup/reproducibility/readiness_gate_report.md",
    "evaluation/reports/challenge_cup_graphrag_context_demo.md",
    "evaluation/reports/challenge_cup_graphrag_same_question_report.md",
]


def build_payload() -> dict[str, Any]:
    killer_questions = [
        {
            "question": "这和普通 RAG 的本质差异是什么？",
            "answer_seconds": 30,
            "answer_frame": "先承认普通 RAG 是强基线，再说明本项目多了可审计关系证据和同题对照。",
            "evidence_anchors": [
                "docs/challenge_cup/03_实验评测报告.md",
                "docs/challenge_cup/07_评审主张证据矩阵.md",
                "evaluation/reports/challenge_cup_graphrag_same_question_report.md",
            ],
        },
        {
            "question": "GraphRAG 是否一定全面优于 keyword 或 hybrid？",
            "answer_seconds": 30,
            "answer_frame": "不做绝对化表述，只主张在需要关系解释和证据追踪的问题上有可展示优势。",
            "evidence_anchors": [
                "docs/challenge_cup/03_实验评测报告.md",
                "docs/challenge_cup/05_答辩问答手册.md",
                "evaluation/reports/challenge_cup_graphrag_context_demo.md",
            ],
        },
        {
            "question": "当前数据规模是否足以支撑真实生产级运维？",
            "answer_seconds": 30,
            "answer_frame": "把范围限定为教学科研验证集，强调已完成数据、索引、评测、演示闭环。",
            "evidence_anchors": [
                "docs/challenge_cup/reproducibility/dataset_manifest.md",
                "docs/challenge_cup/reproducibility/application_validation_report.md",
                "docs/challenge_cup/08_特等奖评审自评表.md",
            ],
        },
        {
            "question": "如果现场服务、浏览器或网络出问题怎么办？",
            "answer_seconds": 30,
            "answer_frame": "20 秒内切换到离线截图、smoke report 和固定演示脚本，避免现场阻塞。",
            "evidence_anchors": [
                "docs/challenge_cup/04_系统演示脚本.md",
                "docs/challenge_cup/reproducibility/browser_demo_smoke_report.md",
                "docs/challenge_cup/reproducibility/runbook.md",
            ],
        },
        {
            "question": "为什么这个项目具备冲击特等奖的完整度？",
            "answer_seconds": 30,
            "answer_frame": "用一页纸、证据矩阵和 readiness gate 串起创新性、工程性、可复现性与边界。",
            "evidence_anchors": [
                "docs/challenge_cup/00_项目一页纸.md",
                "docs/challenge_cup/reproducibility/readiness_gate_report.md",
                "docs/challenge_cup/10_答辩攻防与彩排卡.md",
            ],
        },
    ]
    unique_anchors = {
        anchor for question in killer_questions for anchor in question["evidence_anchors"]
    }
    return {
        "report_type": REPORT_TYPE,
        "status": STATUS,
        "boundary": BOUNDARY,
        "timing_targets": {
            "opening_seconds": 90,
            "demo_seconds": 180,
            "offline_fallback_seconds": 20,
            "killer_question_seconds": 30,
        },
        "opening_required_points": ["问题", "方法", "完成度", "边界"],
        "demo_timeline": [
            {
                "timebox": "0:00-0:30",
                "focus": "项目一页纸",
                "pass_condition": "问题、用户和交付物在半分钟内讲清。",
                "evidence_anchor": "docs/challenge_cup/00_项目一页纸.md",
            },
            {
                "timebox": "0:30-1:20",
                "focus": "浏览器检索演示",
                "pass_condition": "展示真实可运行页面和检索证据，不停留在口头描述。",
                "evidence_anchor": "docs/challenge_cup/reproducibility/browser_demo_smoke_report.md",
            },
            {
                "timebox": "1:20-2:10",
                "focus": "GraphRAG 关系证据",
                "pass_condition": "讲清文本证据与图谱证据如何共同支撑同一问题。",
                "evidence_anchor": "evaluation/reports/challenge_cup_graphrag_context_demo.md",
            },
            {
                "timebox": "2:10-2:40",
                "focus": "readiness gate",
                "pass_condition": "展示机器校验通过项，同时不把 readiness gate 说成获奖保证。",
                "evidence_anchor": "docs/challenge_cup/reproducibility/readiness_gate_report.md",
            },
            {
                "timebox": "2:40-3:00",
                "focus": "边界与下一步",
                "pass_condition": "明确当前验证边界和后续扩展，不夸大生产级覆盖。",
                "evidence_anchor": "docs/challenge_cup/08_特等奖评审自评表.md",
            },
        ],
        "killer_questions": killer_questions,
        "no_overclaim_boundaries": [
            "不说已经替代工程师",
            "不说 GraphRAG 对所有问题都更强",
            "不说当前数据覆盖真实生产全场景",
            "不把 readiness gate 说成获奖保证",
            "不伪造专家反馈或现场彩排记录",
        ],
        "minimum_evidence_anchor_count": len(unique_anchors),
        "evidence_files": EVIDENCE_FILES,
    }


def write_outputs(payload: dict[str, Any]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_markdown(OUTPUT_MD, payload)


def write_markdown(path: Path, payload: dict[str, Any]) -> None:
    timing = payload["timing_targets"]
    lines = [
        "# 答辩彩排计分卡",
        "",
        "本计分卡把现场答辩准备状态转成可复核的时间、证据和边界要求，用于正式答辩前的限时 rehearsal。",
        "",
        f"- Boundary: {payload['boundary']}",
        f"- Status: `{payload['status']}`",
        f"- 90秒开场：覆盖 {'、'.join(payload['opening_required_points'])}",
        f"- 三分钟演示节奏：{timing['demo_seconds']} 秒内完成 5 个固定节点",
        f"- 离线兜底：现场异常时 {timing['offline_fallback_seconds']} 秒内切换到离线证据；20 秒内切换必须完成",
        f"- 杀手问题：每题 {timing['killer_question_seconds']} 秒内回答；30 秒内回答必须落到证据锚点",
        "",
        "## 三分钟演示节奏",
        "",
        "| 时间 | 焦点 | 通过条件 | 证据锚点 |",
        "| --- | --- | --- | --- |",
    ]
    for item in payload["demo_timeline"]:
        lines.append(
            f"| {item['timebox']} | {item['focus']} | {item['pass_condition']} | `{item['evidence_anchor']}` |"
        )

    lines.extend(
        [
            "",
            "## 杀手问题",
            "",
            "| 问题 | 30 秒回答框架 | 证据锚点 |",
            "| --- | --- | --- |",
        ]
    )
    for question in payload["killer_questions"]:
        anchors = "<br>".join(f"`{anchor}`" for anchor in question["evidence_anchors"])
        lines.append(f"| {question['question']} | {question['answer_frame']} | {anchors} |")

    lines.extend(
        [
            "",
            "## 不可夸大边界",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in payload["no_overclaim_boundaries"])
    lines.extend(
        [
            "",
            "## 证据文件",
            "",
        ]
    )
    lines.extend(f"- `{item}`" for item in payload["evidence_files"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    payload = build_payload()
    write_outputs(payload)
    print(f"defense rehearsal scorecard: {OUTPUT_MD.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
