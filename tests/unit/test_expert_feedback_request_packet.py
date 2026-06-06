from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
PACKET_JSON = REPO_ROOT / "docs" / "challenge_cup" / "reproducibility" / "expert_feedback_request_packet.json"
PACKET_MD = REPO_ROOT / "docs" / "challenge_cup" / "reproducibility" / "expert_feedback_request_packet.md"
BOUNDARY = (
    "This packet proves review outreach readiness; it does not claim expert approval, signed feedback, "
    "or production validation."
)


def test_build_expert_feedback_request_packet_outputs_sendable_integrity_pack() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/build_expert_feedback_request_packet.py"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    assert "expert feedback request packet" in result.stdout
    payload = json.loads(PACKET_JSON.read_text(encoding="utf-8"))
    assert payload["report_type"] == "challenge_cup_expert_feedback_request_packet"
    assert payload["status"] == "ready_to_send"
    assert payload["no_external_feedback_claimed"] is True
    assert payload["boundary"] == BOUNDARY
    assert len(payload["recipient_roles"]) >= 3
    assert payload["review_dimensions"] == [
        "实用性",
        "创新性",
        "工程完成度",
        "评测可信度",
        "答辩清晰度",
        "边界严谨性",
    ]
    assert payload["required_archive_evidence_types"] == ["签字页", "邮件回复", "会议纪要", "聊天记录截图"]
    assert len(payload["review_questions"]) >= 8
    assert payload["minimum_evidence_file_count"] >= 10
    assert "docs/challenge_cup/reproducibility/expert_feedback_form.md" in payload["evidence_files"]
    assert "docs/challenge_cup/reproducibility/defense_rehearsal_scorecard.md" in payload["evidence_files"]
    assert "docs/challenge_cup/reproducibility/readiness_gate_report.md" in payload["evidence_files"]
    intake = payload["post_receipt_hard_evidence_intake"]
    assert "source_sha256" in intake["required_metadata_fields"]
    assert "feedback_source_path" in intake["required_metadata_fields"]
    assert any("source_sha256" in item for item in intake["source_integrity_guardrails"])
    assert any("must not be a JSON metadata file" in item for item in intake["source_integrity_guardrails"])
    assert any("preflight_challenge_cup_hard_evidence.py expert_feedback" in item for item in intake["recording_commands"])
    assert any("record_challenge_cup_hard_evidence.py expert_feedback" in item for item in intake["recording_commands"])
    assert any("--confirm-real-feedback" in item for item in intake["recording_commands"])
    assert "已经获得专家认可" not in payload["sendable_message"]["body"]
    assert "通过专家验证" not in payload["sendable_message"]["body"]

    markdown = PACKET_MD.read_text(encoding="utf-8")
    assert "专家反馈外发包" in markdown
    assert "待真实反馈归档" in markdown
    assert "不宣称已获得专家认可" in markdown
    assert "建议邮件主题" in markdown
    assert "post-receipt hard evidence intake" in markdown
    assert "source_sha256" in markdown
    assert "must not be a JSON metadata file" in markdown
    assert "record_challenge_cup_hard_evidence.py expert_feedback" in markdown
    for term in ["签字页", "邮件回复", "会议纪要", "聊天记录截图"]:
        assert term in markdown
    assert BOUNDARY in markdown
