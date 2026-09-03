from __future__ import annotations

from pathlib import Path

import yaml

SKILL_PATH = Path(__file__).parents[2] / "skills" / "graphrag-fmea" / "SKILL.md"
_CONFIRMATION_FLAGS = (
    "--confirm-template-change",
    "--confirm-migration",
    "--confirm-publication",
    "--confirm-human-assistance-decision",
)


def test_fmea_skill_has_trigger_only_frontmatter_and_supported_cli_recipe() -> None:
    text = SKILL_PATH.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    _, raw_frontmatter, body = text.split("---", 2)
    frontmatter = yaml.safe_load(raw_frontmatter)
    assert set(frontmatter) == {"name", "description"}
    assert "scripts/fmea_skill.py" in body
    assert "read-only by default" in body
    assert all(flag in body for flag in _CONFIRMATION_FLAGS)
    assert "repository" not in text.lower()
    assert "sqlite" not in text.lower()


def test_fmea_skill_does_not_offer_client_owned_paths_or_model_authority() -> None:
    text = SKILL_PATH.read_text(encoding="utf-8").lower()
    for forbidden in ("--provider", "--model", "--artifact-root", "--filename", "--adapter"):
        assert forbidden not in text
