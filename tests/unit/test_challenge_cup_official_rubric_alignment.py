from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "build_challenge_cup_official_rubric_alignment.py"


def load_official_rubric_module():
    spec = importlib.util.spec_from_file_location("build_challenge_cup_official_rubric_alignment", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_official_rubric_alignment_locks_latest_public_source_facts(tmp_path: Path) -> None:
    module = load_official_rubric_module()
    module.REPO_ROOT = tmp_path
    module.OUTPUT_DIR = tmp_path / "docs" / "challenge_cup" / "reproducibility"
    module.OUTPUT_JSON = module.OUTPUT_DIR / "official_rubric_alignment.json"
    module.OUTPUT_MD = module.OUTPUT_DIR / "official_rubric_alignment.md"

    payload = module.write_outputs()

    source_lock = payload["official_source_lock"]
    latest = source_lock["latest_public_result"]
    assert source_lock["current_as_of"] == "2026-06-07"
    assert latest["source_id"] == "tsinghua_44th_2026"
    assert latest["source_url"] == "https://www.tsinghua.edu.cn/info/1177/125861.htm"
    assert latest["published_date"] == "2026-04-29"
    assert latest["final_defense_date"] == "2026-04-25"
    assert latest["award_ceremony_date"] == "2026-04-26"
    assert latest["registration_count"] == 337
    assert latest["school_finalist_counts"] == {"undergraduate": 173, "graduate": 9}
    assert latest["main_track_award_counts"] == {
        "total": 114,
        "special_prize": 7,
        "first_prize": 11,
        "second_prize": 32,
        "third_prize": 64,
    }
    assert latest["exhibition_work_count_min"] == 200
    assert set(source_lock["rubric_dimension_lock"]["source_ids"]) >= {
        "tsinghua_37th_2019",
        "tsinghua_39th_2021",
    }
    assert source_lock["rubric_dimension_lock"]["required_dimensions"] == [
        "academic_or_practical_value",
        "innovation",
        "completion",
        "defense_performance",
    ]
    assert source_lock["recency_policy"]["must_recheck_before_final_submission"] is True
    assert source_lock["recency_policy"]["no_award_guarantee"] is True

    source_ids = {source["source_id"] for source in payload["official_sources"]}
    assert {"tsinghua_ee_44th_2026", "tsinghua_auto_44th_2026"}.issubset(source_ids)
    assert payload["official_source_count"] == len(payload["official_sources"]) >= 7

    benchmarks = payload["special_prize_competition_benchmarks"]
    assert benchmarks["current_as_of"] == "2026-06-07"
    assert benchmarks["no_award_guarantee"] is True
    assert benchmarks["benchmark_source_ids"] == [
        "tsinghua_44th_2026",
        "tsinghua_ee_44th_2026",
        "tsinghua_auto_44th_2026",
    ]
    department_ids = {item["source_id"] for item in benchmarks["department_benchmarks"]}
    assert department_ids == {"tsinghua_ee_44th_2026", "tsinghua_auto_44th_2026"}
    electronic_engineering = next(
        item for item in benchmarks["department_benchmarks"] if item["source_id"] == "tsinghua_ee_44th_2026"
    )
    assert electronic_engineering["reported_awards"] == {
        "special_prize": 1,
        "first_prize": 1,
        "second_prize": 2,
    }
    automation = next(
        item for item in benchmarks["department_benchmarks"] if item["source_id"] == "tsinghua_auto_44th_2026"
    )
    assert automation["reported_awards"] == {"second_prize": 4, "third_prize": 2}

    output = json.loads(module.OUTPUT_JSON.read_text(encoding="utf-8"))
    assert output["official_source_lock"] == source_lock
    markdown = module.OUTPUT_MD.read_text(encoding="utf-8")
    for term in [
        "Official Source Lock",
        "44th Department Benchmarks",
        "tsinghua_ee_44th_2026",
        "tsinghua_auto_44th_2026",
        "department_total_score_first",
        "department_total_score_fifth",
        "2026-04-25",
        "2026-04-29",
        "337",
        "173",
        "9",
        "114",
        "7",
    ]:
        assert term in markdown
