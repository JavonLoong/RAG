from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = REPO_ROOT / "docs" / "challenge_cup" / "reproducibility"
OUTPUT_JSON = OUTPUT_DIR / "defense_rehearsal_result_packet.json"
OUTPUT_MD = OUTPUT_DIR / "defense_rehearsal_result_packet.md"

REPORT_TYPE = "challenge_cup_defense_rehearsal_result_packet"
STATUS = "ready_to_record_actual_rehearsal"
BOUNDARY = (
    "This packet prepares actual timed rehearsal recording; it does not claim a timed rehearsal has "
    "already been completed."
)
TIMING_TARGETS = {
    "opening_seconds": 90,
    "demo_seconds": 180,
    "offline_fallback_seconds": 20,
    "killer_question_seconds": 30,
}
PASS_FAIL_RULES = {
    "opening_actual_seconds_max": 90,
    "demo_actual_seconds_max": 180,
    "offline_fallback_actual_seconds_max": 20,
    "each_killer_question_actual_seconds_max": 30,
    "required_killer_question_count": 5,
}
ARCHIVE_EVIDENCE_TYPES = ["计时截图", "彩排录屏", "观察员签字或备注", "问题遗漏清单"]
EVIDENCE_FILES = [
    "docs/challenge_cup/04_系统演示脚本.md",
    "docs/challenge_cup/05_答辩问答手册.md",
    "docs/challenge_cup/08_特等奖评审自评表.md",
    "docs/challenge_cup/10_答辩攻防与彩排卡.md",
    "docs/challenge_cup/reproducibility/defense_rehearsal_scorecard.md",
    "docs/challenge_cup/reproducibility/readiness_gate_report.md",
]


def result_template() -> dict[str, Any]:
    return {
        "rehearsal_date": None,
        "recorder": None,
        "observer": None,
        "opening_actual_seconds": None,
        "demo_actual_seconds": None,
        "offline_fallback_actual_seconds": None,
        "killer_question_results": [
            {
                "question_index": 1,
                "question": "这和普通 RAG 的本质差异是什么？",
                "actual_seconds": None,
                "missed_evidence_anchor": None,
                "needs_revision": None,
            },
            {
                "question_index": 2,
                "question": "GraphRAG 是否一定全面优于 keyword 或 hybrid？",
                "actual_seconds": None,
                "missed_evidence_anchor": None,
                "needs_revision": None,
            },
            {
                "question_index": 3,
                "question": "当前数据规模是否足以支撑真实生产级运维？",
                "actual_seconds": None,
                "missed_evidence_anchor": None,
                "needs_revision": None,
            },
            {
                "question_index": 4,
                "question": "如果现场服务、浏览器或网络出问题怎么办？",
                "actual_seconds": None,
                "missed_evidence_anchor": None,
                "needs_revision": None,
            },
            {
                "question_index": 5,
                "question": "为什么这个项目具备冲击特等奖的完整度？",
                "actual_seconds": None,
                "missed_evidence_anchor": None,
                "needs_revision": None,
            },
        ],
        "archive_evidence_paths": [],
        "issue_list": [],
        "overall_result": "not_recorded",
    }


def build_payload() -> dict[str, Any]:
    return {
        "report_type": REPORT_TYPE,
        "status": STATUS,
        "actual_rehearsal_completed": False,
        "boundary": BOUNDARY,
        "timing_targets": TIMING_TARGETS,
        "pass_fail_rules": PASS_FAIL_RULES,
        "required_archive_evidence_types": ARCHIVE_EVIDENCE_TYPES,
        "result_template": result_template(),
        "post_recording_actions": [
            "填写所有 actual_seconds 字段并归档计时截图或录屏。",
            "把每个超时项和遗漏证据锚点写入 issue_list。",
            "更新 overall_result 为 pass 或 needs_revision。",
            "重新运行 scripts/check_challenge_cup_readiness.py。",
        ],
        "evidence_files": EVIDENCE_FILES,
    }


def write_outputs(payload: dict[str, Any]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown(OUTPUT_MD, payload)


def write_markdown(path: Path, payload: dict[str, Any]) -> None:
    template = payload["result_template"]
    lines = [
        "# 答辩计时彩排结果归档包",
        "",
        "本包用于记录一次真实计时彩排的用时、遗漏点和归档证据。当前状态是尚未记录真实计时彩排；不伪造现场彩排记录。",
        "",
        f"- Boundary: {payload['boundary']}",
        f"- Status: `{payload['status']}`",
        f"- actual_rehearsal_completed: `{payload['actual_rehearsal_completed']}`",
        "",
        "## 通过阈值",
        "",
        f"- 90 秒开场：opening_actual_seconds <= {payload['pass_fail_rules']['opening_actual_seconds_max']}",
        f"- 三分钟演示：demo_actual_seconds <= {payload['pass_fail_rules']['demo_actual_seconds_max']}",
        f"- 离线兜底切换：offline_fallback_actual_seconds <= {payload['pass_fail_rules']['offline_fallback_actual_seconds_max']}",
        f"- 杀手问题：每题 actual_seconds <= {payload['pass_fail_rules']['each_killer_question_actual_seconds_max']}",
        "",
        "## 待填写字段",
        "",
        "- rehearsal_date",
        "- recorder",
        "- observer",
        "- opening_actual_seconds",
        "- demo_actual_seconds",
        "- offline_fallback_actual_seconds",
        "- killer_question_results",
        "- archive_evidence_paths",
        "- issue_list",
        "- overall_result",
        "",
        "## killer_question_results 模板",
        "",
        "| # | Question | actual_seconds | missed_evidence_anchor | needs_revision |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in template["killer_question_results"]:
        lines.append(
            f"| {item['question_index']} | {item['question']} | {item['actual_seconds']} | {item['missed_evidence_anchor']} | {item['needs_revision']} |"
        )
    lines.extend(
        [
            "",
            "## 归档证据类型",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in payload["required_archive_evidence_types"])
    lines.extend(["", "## 后续动作", ""])
    lines.extend(f"- {item}" for item in payload["post_recording_actions"])
    lines.extend(["", "## 证据文件", ""])
    lines.extend(f"- `{item}`" for item in payload["evidence_files"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    payload = build_payload()
    write_outputs(payload)
    print(f"defense rehearsal result packet: {OUTPUT_MD.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
