from __future__ import annotations

import importlib.util
import hashlib
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
RUBRIC_SCRIPT = REPO_ROOT / "scripts" / "build_challenge_cup_official_rubric_alignment.py"
RECHECK_SCRIPT = REPO_ROOT / "scripts" / "build_challenge_cup_official_source_recheck_pack.py"


def load_module(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def test_official_source_recheck_pack_builds_final_submission_work_order(tmp_path: Path) -> None:
    rubric_module = load_module(RUBRIC_SCRIPT, "build_challenge_cup_official_rubric_alignment_for_recheck_test")
    rubric_module.REPO_ROOT = tmp_path
    rubric_module.OUTPUT_DIR = tmp_path / "docs" / "challenge_cup" / "reproducibility"
    rubric_module.OUTPUT_JSON = rubric_module.OUTPUT_DIR / "official_rubric_alignment.json"
    rubric_module.OUTPUT_MD = rubric_module.OUTPUT_DIR / "official_rubric_alignment.md"
    rubric_payload = rubric_module.write_outputs()

    recheck_module = load_module(RECHECK_SCRIPT, "build_challenge_cup_official_source_recheck_pack")
    recheck_module.REPO_ROOT = tmp_path
    recheck_module.OUTPUT_DIR = rubric_module.OUTPUT_DIR
    recheck_module.OFFICIAL_RUBRIC_JSON = rubric_module.OUTPUT_JSON
    recheck_module.OUTPUT_JSON = recheck_module.OUTPUT_DIR / "official_source_recheck_pack.json"
    recheck_module.OUTPUT_MD = recheck_module.OUTPUT_DIR / "official_source_recheck_pack.md"

    payload = recheck_module.write_outputs()

    assert payload["report_type"] == "challenge_cup_official_source_recheck_pack"
    assert payload["status"] == "ready_for_final_submission_source_recheck"
    assert payload["generated_from"] == "docs/challenge_cup/reproducibility/official_rubric_alignment.json"
    assert payload["source_lock_current_as_of"] == "2026-06-07"
    assert payload["latest_public_result_source_id"] == "tsinghua_44th_2026"
    assert payload["requires_manual_recheck_before_final_submission"] is True
    assert payload["completion_claim_allowed"] is False
    assert payload["no_award_guarantee"] is True
    assert payload["does_not_satisfy_goal_completion"] is True

    source_ids = {item["source_id"] for item in payload["source_recheck_items"]}
    assert source_ids == {source["source_id"] for source in rubric_payload["official_sources"]}
    assert {"tsinghua_44th_2026", "tsinghua_ee_44th_2026", "tsinghua_auto_44th_2026"} <= source_ids
    assert all(item["url"].startswith("https://") for item in payload["source_recheck_items"])
    assert all("tsinghua.edu.cn" in item["url"] for item in payload["source_recheck_items"])
    assert all(item["required_action"] == "open_official_url_and_compare_anchor_terms" for item in payload["source_recheck_items"])
    assert all(item["manual_recheck_required"] is True for item in payload["source_recheck_items"])
    assert any(
        item["source_id"] == "tsinghua_44th_2026" and item["anchor_terms"]
        for item in payload["source_recheck_items"]
    )
    for item in payload["source_recheck_items"]:
        snapshot_path = tmp_path / item["snapshot_path"]
        assert item["snapshot_path"].startswith("docs/challenge_cup/reproducibility/official_source_snapshots/")
        assert snapshot_path.exists()
        assert item["snapshot_sha256"] == sha256_file(snapshot_path)
        snapshot = snapshot_path.read_text(encoding="utf-8")
        assert item["source_id"] in snapshot
        assert item["url"] in snapshot
        for term in item["anchor_terms"]:
            assert term in snapshot

    final_check_ids = {item["check_id"] for item in payload["final_submission_checks"]}
    assert final_check_ids == {
        "official_url_access",
        "latest_public_result_not_superseded",
        "rubric_dimension_recheck",
        "department_benchmark_recheck",
        "boundary_recheck",
    }
    assert payload["integrity_rules"] == {
        "manual_web_recheck_required": True,
        "no_award_guarantee": True,
        "no_fake_external_validation": True,
        "does_not_satisfy_goal_completion": True,
    }

    output = json.loads(recheck_module.OUTPUT_JSON.read_text(encoding="utf-8"))
    assert output == payload
    markdown = recheck_module.OUTPUT_MD.read_text(encoding="utf-8")
    for term in [
        "Official Source Recheck Pack",
        "manual_web_recheck_required",
        "tsinghua_44th_2026",
        "latest_public_result_not_superseded",
        "new Tsinghua Challenge Cup official notice or result page",
        "official_source_snapshots",
        "snapshot_sha256",
        "no award guarantee",
        "does not satisfy goal completion",
        "python scripts/check_challenge_cup_readiness.py",
    ]:
        assert term in markdown
