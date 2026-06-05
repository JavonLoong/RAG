from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = REPO_ROOT / "docs" / "challenge_cup" / "reproducibility"
OUTPUT_JSON = OUTPUT_DIR / "expert_feedback_request_packet.json"
OUTPUT_MD = OUTPUT_DIR / "expert_feedback_request_packet.md"

REPORT_TYPE = "challenge_cup_expert_feedback_request_packet"
STATUS = "ready_to_send"
BOUNDARY = (
    "This packet proves review outreach readiness; it does not claim expert approval, signed feedback, "
    "or production validation."
)

REVIEW_DIMENSIONS = [
    "实用性",
    "创新性",
    "工程完成度",
    "评测可信度",
    "答辩清晰度",
    "边界严谨性",
]
ARCHIVE_EVIDENCE_TYPES = ["签字页", "邮件回复", "会议纪要", "聊天记录截图"]
EVIDENCE_FILES = [
    "docs/challenge_cup/00_项目一页纸.md",
    "docs/challenge_cup/03_实验评测报告.md",
    "docs/challenge_cup/04_系统演示脚本.md",
    "docs/challenge_cup/07_评审主张证据矩阵.md",
    "docs/challenge_cup/08_特等奖评审自评表.md",
    "docs/challenge_cup/10_答辩攻防与彩排卡.md",
    "docs/challenge_cup/11_应用场景与专家验证.md",
    "docs/challenge_cup/12_专家反馈采集与整改闭环.md",
    "docs/challenge_cup/reproducibility/application_validation_report.md",
    "docs/challenge_cup/reproducibility/browser_demo_smoke_report.md",
    "docs/challenge_cup/reproducibility/defense_rehearsal_scorecard.md",
    "docs/challenge_cup/reproducibility/expert_feedback_form.md",
    "docs/challenge_cup/reproducibility/readiness_gate_report.md",
]


def build_payload() -> dict[str, Any]:
    attachments = [
        "docs/challenge_cup/00_项目一页纸.md",
        "docs/challenge_cup/11_应用场景与专家验证.md",
        "docs/challenge_cup/reproducibility/application_validation_report.md",
        "docs/challenge_cup/reproducibility/expert_feedback_form.md",
        "docs/challenge_cup/reproducibility/readiness_gate_report.md",
    ]
    return {
        "report_type": REPORT_TYPE,
        "status": STATUS,
        "no_external_feedback_claimed": True,
        "boundary": BOUNDARY,
        "recipient_roles": [
            "指导教师或课程负责老师",
            "动力装备、运维、能源系统相关方向专家",
            "实验室同学、课程助教或具备工程背景的复核者",
        ],
        "review_dimensions": REVIEW_DIMENSIONS,
        "required_archive_evidence_types": ARCHIVE_EVIDENCE_TYPES,
        "review_questions": [
            "固定燃气轮机异常振动场景是否能支撑项目实用性？",
            "证据链是否覆盖现象、原因、检查项、处理措施和复机结果？",
            "GraphRAG 与普通 RAG 的差异是否讲清楚？",
            "当前评测设计是否足以支撑结项答辩？",
            "失败案例和边界说明是否足够诚实？",
            "现场三分钟演示是否能让非项目成员快速理解？",
            "哪些数据、实验或工程细节最需要补充？",
            "若面向挑战杯终审，最可能被追问的问题是什么？",
        ],
        "sendable_message": {
            "subject": "请协助复核“知燃知维”挑战杯结项材料与固定应用场景",
            "body": "\n".join(
                [
                    "老师/同学您好，",
                    "",
                    "我们正在整理“知燃知维：面向动力装备运维知识的可信 GraphRAG 系统”的结项与挑战杯材料。"
                    "想请您按附件中的一页纸、固定应用场景和反馈表，帮忙做一次外部视角复核。",
                    "",
                    "重点希望您指出：实用性是否成立、证据链是否可信、评测是否足够支撑结项、"
                    "答辩口径是否清楚、边界是否严谨，以及哪些材料还需要补充。",
                    "",
                    "当前材料仍处于待真实反馈归档状态；我们不会把本次邀请表述为外部背书。"
                    "如果您愿意反馈，可直接在表格中填写，或用邮件/会议纪要/聊天记录形式回复。",
                    "",
                    "感谢！",
                ]
            ),
            "attachments": attachments,
        },
        "archive_rule": {
            "status_before_receipt": "待真实反馈归档",
            "allowed_evidence_types": ARCHIVE_EVIDENCE_TYPES,
            "required_post_receipt_action": "将原件或摘要归档后，更新专家反馈闭环并重新运行 readiness gate。",
            "integrity_boundary": "不宣称已获得专家认可；不把内部自评写成外部背书。",
        },
        "minimum_evidence_file_count": len(EVIDENCE_FILES),
        "evidence_files": EVIDENCE_FILES,
    }


def write_outputs(payload: dict[str, Any]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown(OUTPUT_MD, payload)


def write_markdown(path: Path, payload: dict[str, Any]) -> None:
    message = payload["sendable_message"]
    lines = [
        "# 专家反馈外发包",
        "",
        "本包用于把“待真实反馈归档”推进到可执行的外发状态。它证明材料已准备好发送给老师、专家或具备工程背景的复核者，但不宣称已获得专家认可。",
        "",
        f"- Boundary: {payload['boundary']}",
        f"- Status: `{payload['status']}`",
        "- 当前反馈状态：待真实反馈归档",
        "- 诚信边界：不宣称已获得专家认可，不把内部自评写成外部背书。",
        "",
        "## 建议邮件主题",
        "",
        message["subject"],
        "",
        "## 建议正文",
        "",
        "```text",
        message["body"],
        "```",
        "",
        "## 复核维度",
        "",
    ]
    lines.extend(f"- {item}" for item in payload["review_dimensions"])
    lines.extend(["", "## 复核问题", ""])
    lines.extend(f"- {item}" for item in payload["review_questions"])
    lines.extend(["", "## 建议附件", ""])
    lines.extend(f"- `{item}`" for item in message["attachments"])
    lines.extend(["", "## 归档要求", ""])
    lines.extend(f"- {item}" for item in payload["required_archive_evidence_types"])
    lines.extend(
        [
            "",
            "收到真实反馈后，应将原件或摘要归档，更新 `docs/challenge_cup/12_专家反馈采集与整改闭环.md`，并重新运行 readiness gate。",
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
    print(f"expert feedback request packet: {OUTPUT_MD.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
