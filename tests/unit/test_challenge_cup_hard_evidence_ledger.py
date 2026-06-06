from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "build_challenge_cup_hard_evidence_ledger.py"


def load_ledger_module():
    spec = importlib.util.spec_from_file_location("build_challenge_cup_hard_evidence_ledger", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def configure_module_paths(module, repo_root: Path) -> None:
    module.REPO_ROOT = repo_root
    module.OUTPUT_DIR = repo_root / "docs" / "challenge_cup" / "reproducibility"
    module.OUTPUT_JSON = module.OUTPUT_DIR / "hard_evidence_ledger.json"
    module.OUTPUT_MD = module.OUTPUT_DIR / "hard_evidence_ledger.md"
    module.INTAKE_ROOT = module.OUTPUT_DIR / "hard_evidence"
    module.EXPERT_DIR = module.INTAKE_ROOT / "expert_feedback"
    module.REHEARSAL_DIR = module.INTAKE_ROOT / "timed_rehearsal"
    module.ROOT_README = module.INTAKE_ROOT / "README.md"
    module.EXPERT_README = module.EXPERT_DIR / "README.md"
    module.REHEARSAL_README = module.REHEARSAL_DIR / "README.md"


def test_hard_evidence_ledger_readme_commands_require_real_dates(tmp_path: Path) -> None:
    module = load_ledger_module()
    configure_module_paths(module, tmp_path)

    payload = module.write_outputs()

    assert payload["report_type"] == "challenge_cup_hard_evidence_ledger"
    assert payload["status"] == "awaiting_real_external_feedback_and_timed_rehearsal"
    assert payload["completion_claim_allowed"] is False
    assert payload["required_before_goal_completion"] == ["expert_feedback", "timed_rehearsal"]

    output_json = tmp_path / "docs" / "challenge_cup" / "reproducibility" / "hard_evidence_ledger.json"
    output_md = tmp_path / "docs" / "challenge_cup" / "reproducibility" / "hard_evidence_ledger.md"
    root_readme = tmp_path / "docs" / "challenge_cup" / "reproducibility" / "hard_evidence" / "README.md"
    expert_readme = root_readme.parent / "expert_feedback" / "README.md"
    rehearsal_readme = root_readme.parent / "timed_rehearsal" / "README.md"

    assert json.loads(output_json.read_text(encoding="utf-8")) == payload
    assert output_md.exists()
    assert root_readme.exists()
    command_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [expert_readme, rehearsal_readme]
    )
    assert "2026-06-06" not in command_text
    assert "20260606" not in command_text
    for placeholder in [
        "<real-feedback-id>",
        "<real-feedback-file>",
        "<real-reviewer-identity>",
        "<real-reviewer-role-or-org>",
        "<real-review-date-yyyy-mm-dd>",
        "<real-rehearsal-id>",
        "<real-timer-or-observer-file>",
        "<real-rehearsal-date-yyyy-mm-dd>",
        "<actual-opening-seconds>",
        "<q5-seconds>",
    ]:
        assert placeholder in command_text
