from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "build_challenge_cup_poster_render_smoke.py"


def load_poster_smoke_module():
    spec = importlib.util.spec_from_file_location("build_challenge_cup_poster_render_smoke", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_builds_poster_render_smoke_report_with_print_contract_and_link_checks(tmp_path: Path) -> None:
    module = load_poster_smoke_module()
    module.configure_paths(tmp_path)
    poster = tmp_path / "docs" / "challenge_cup" / "poster" / "challenge_cup_a0_poster.html"
    target = tmp_path / "docs" / "challenge_cup" / "reproducibility" / "readiness_gate_report.md"
    target.parent.mkdir(parents=True)
    target.write_text("readiness", encoding="utf-8")
    poster.parent.mkdir(parents=True)
    poster.write_text(
        """<!doctype html>
<html lang="zh-CN">
<head>
  <title>知燃知维 Challenge Cup A0 Poster</title>
  <style>@page { size: A0 landscape; margin: 0; } .poster { width: 1189mm; height: 841mm; }</style>
</head>
<body>
  <article class="poster" aria-label="知燃知维 A0 展板">
    <h1>知燃知维 GraphRAG</h1>
    <p>GraphRAG GT-07 readiness gate browser smoke no award guarantee real expert feedback real timed rehearsal</p>
    <a href="../reproducibility/readiness_gate_report.md">Readiness</a>
  </article>
</body>
</html>
""",
        encoding="utf-8",
    )

    payload = module.write_outputs()

    assert payload["report_type"] == "challenge_cup_poster_render_smoke"
    assert payload["status"] == "pass"
    assert payload["poster_path"] == "docs/challenge_cup/poster/challenge_cup_a0_poster.html"
    assert payload["render_contract"]["page_size"] == "A0 landscape"
    assert payload["render_contract"]["poster_dimensions_mm"] == {"width": 1189, "height": 841}
    assert payload["render_contract"]["print_css_detected"] is True
    assert payload["required_term_checks"]["missing"] == []
    assert payload["link_checks"]["missing_targets"] == []
    assert payload["boundary_checks"]["no_award_guarantee"] is True
    assert payload["boundary_checks"]["external_hard_evidence_pending"] is True

    output_json = (
        tmp_path / "docs" / "challenge_cup" / "reproducibility" / "poster_render_smoke_report.json"
    )
    output_md = tmp_path / "docs" / "challenge_cup" / "reproducibility" / "poster_render_smoke_report.md"
    assert json.loads(output_json.read_text(encoding="utf-8")) == payload
    markdown = output_md.read_text(encoding="utf-8")
    assert "Poster Render Smoke" in markdown
    assert "A0 landscape" in markdown
    assert "readiness_gate_report.md" in markdown
