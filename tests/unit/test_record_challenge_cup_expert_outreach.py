from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "record_challenge_cup_expert_outreach.py"


def load_outreach_module():
    spec = importlib.util.spec_from_file_location("record_challenge_cup_expert_outreach", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def outreach_args(source: Path, *extra: str) -> list[str]:
    return [
        "--id",
        "advisor-a-20260606",
        "--source",
        str(source),
        "--recipient-alias",
        "advisor-a",
        "--recipient-role",
        "advisor",
        "--channel",
        "email",
        "--sent-date",
        "2026-06-06",
        "--status",
        "sent",
        "--requested-review-dimension",
        "practicality",
        "--requested-review-dimension",
        "innovation",
        "--requested-review-dimension",
        "boundary rigor",
        "--requested-attachment",
        "docs/challenge_cup/00_项目一页纸.md",
        "--requested-attachment",
        "docs/challenge_cup/reproducibility/expert_feedback_form.md",
        "--followup-due-date",
        "2026-06-09",
        *extra,
    ]


def test_refuses_to_write_without_real_outreach_confirmation(tmp_path: Path) -> None:
    module = load_outreach_module()
    module.configure_paths(tmp_path)
    source = tmp_path / "incoming" / "sent_email.txt"
    source.parent.mkdir(parents=True)
    source.write_text("sent email receipt", encoding="utf-8")

    exit_code = module.main(outreach_args(source))

    assert exit_code == 2
    assert not (tmp_path / "docs").exists()


def test_records_confirmed_expert_outreach_and_refreshes_ledger(tmp_path: Path) -> None:
    module = load_outreach_module()
    module.configure_paths(tmp_path)
    source = tmp_path / "incoming" / "sent_email.txt"
    source.parent.mkdir(parents=True)
    source.write_text("real sent email receipt", encoding="utf-8")

    exit_code = module.main(outreach_args(source, "--confirm-real-outreach"))

    assert exit_code == 0
    outreach_dir = tmp_path / "docs" / "challenge_cup" / "reproducibility" / "expert_feedback_outreach"
    copied_source = outreach_dir / "advisor-a-20260606.txt"
    metadata_path = outreach_dir / "advisor-a-20260606.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert copied_source.read_text(encoding="utf-8") == "real sent email receipt"
    assert metadata == {
        "outreach_type": "expert_feedback_request",
        "recipient_alias": "advisor-a",
        "recipient_role": "advisor",
        "channel": "email",
        "sent_date": "2026-06-06",
        "status": "sent",
        "request_source_path": (
            "docs/challenge_cup/reproducibility/expert_feedback_outreach/advisor-a-20260606.txt"
        ),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "requested_review_dimensions": ["practicality", "innovation", "boundary rigor"],
        "requested_attachment_paths": [
            "docs/challenge_cup/00_项目一页纸.md",
            "docs/challenge_cup/reproducibility/expert_feedback_form.md",
        ],
        "followup_due_date": "2026-06-09",
        "notes": [],
        "no_external_feedback_claimed": True,
        "does_not_satisfy_hard_evidence": True,
    }
    ledger = json.loads(
        (tmp_path / "docs" / "challenge_cup" / "reproducibility" / "expert_feedback_outreach_ledger.json").read_text(
            encoding="utf-8"
        )
    )
    assert ledger["report_type"] == "challenge_cup_expert_feedback_outreach_ledger"
    assert ledger["status"] == "outreach_recorded_awaiting_response"
    assert ledger["no_external_feedback_claimed"] is True
    assert ledger["does_not_satisfy_goal_completion"] is True
    assert ledger["outreach_record_count"] == 2
    assert metadata["request_source_path"] in ledger["outreach_files"]


def test_rejects_empty_outreach_source_file(tmp_path: Path) -> None:
    module = load_outreach_module()
    module.configure_paths(tmp_path)
    source = tmp_path / "incoming" / "sent_email.txt"
    source.parent.mkdir(parents=True)
    source.write_text("", encoding="utf-8")

    exit_code = module.main(outreach_args(source, "--confirm-real-outreach"))

    assert exit_code == 2
    assert not (tmp_path / "docs").exists()


def test_rejects_json_outreach_source_file(tmp_path: Path) -> None:
    module = load_outreach_module()
    module.configure_paths(tmp_path)
    source = tmp_path / "incoming" / "sent_email.json"
    source.parent.mkdir(parents=True)
    source.write_text('{"sent": true}', encoding="utf-8")

    exit_code = module.main(outreach_args(source, "--confirm-real-outreach"))

    assert exit_code == 2
    assert not (tmp_path / "docs").exists()


def test_rejects_future_sent_date(tmp_path: Path) -> None:
    module = load_outreach_module()
    module.configure_paths(tmp_path)
    source = tmp_path / "incoming" / "sent_email.txt"
    source.parent.mkdir(parents=True)
    source.write_text("sent email receipt", encoding="utf-8")
    args = outreach_args(source, "--confirm-real-outreach")
    sent_index = args.index("--sent-date")
    args[sent_index + 1] = "2999-01-01"

    exit_code = module.main(args)

    assert exit_code == 2
    assert not (tmp_path / "docs").exists()


def test_rejects_under_scoped_review_request(tmp_path: Path) -> None:
    module = load_outreach_module()
    module.configure_paths(tmp_path)
    source = tmp_path / "incoming" / "sent_email.txt"
    source.parent.mkdir(parents=True)
    source.write_text("sent email receipt", encoding="utf-8")
    args = outreach_args(source, "--confirm-real-outreach")
    first_dimension = args.index("--requested-review-dimension")
    truncated_args = args[: first_dimension + 2] + [
        "--requested-attachment",
        "docs/challenge_cup/00_项目一页纸.md",
        "--confirm-real-outreach",
    ]

    exit_code = module.main(truncated_args)

    assert exit_code == 2
    assert not (tmp_path / "docs").exists()
