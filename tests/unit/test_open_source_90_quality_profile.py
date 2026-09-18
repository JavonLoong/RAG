from __future__ import annotations

import pytest

from evaluation import OPEN_SOURCE_90_PROFILE, get_quality_profile, render_quality_profile_markdown


def test_open_source_90_profile_sets_strict_rag_thresholds() -> None:
    profile = get_quality_profile("open_source_90")

    assert profile is OPEN_SOURCE_90_PROFILE
    assert profile.thresholds.min_keyword_recall_at_k == 0.90
    assert profile.thresholds.min_answer_completeness == 0.90
    assert profile.thresholds.max_missing_citation_rate == 0.0
    assert profile.thresholds.max_medium_or_high_risk_rate == 0.02
    assert profile.thresholds.max_no_result_rate == 0.02


def test_open_source_90_profile_tracks_external_quality_targets() -> None:
    targets = OPEN_SOURCE_90_PROFILE.benchmark_targets

    assert targets["citation_coverage"] == 1.00
    assert targets["source_page_accuracy"] == 0.95
    assert targets["no_answer_precision"] == 0.90
    assert targets["recall_at_10"] == 0.90
    assert targets["reranked_top3_evidence_hit_rate"] == 0.85
    assert targets["hallucination_rate_max"] == 0.02
    assert targets["permission_leak_max"] == 0
    assert targets["secret_leak_max"] == 0


def test_open_source_90_markdown_report_is_explicit_about_proof_gap() -> None:
    markdown = render_quality_profile_markdown()

    assert "# Open Source 90 Quality Gate" in markdown
    assert "keyword recall@k | >= 0.90" in markdown
    assert "missing citation rate | <= 0.00" in markdown
    assert "recall_at_10 | 0.9" in markdown
    assert "not a proof of achieved quality" in markdown
    assert "expert gold set" in markdown


def test_unknown_quality_profile_raises_clear_error() -> None:
    with pytest.raises(ValueError, match="Unknown quality profile"):
        get_quality_profile("not-real")
