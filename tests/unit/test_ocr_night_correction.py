from __future__ import annotations

from scripts.ocr_night_correction import choose_best_candidate, page_flags, text_quality_score


def test_page_flags_marks_low_confidence_and_empty_pages() -> None:
    low = {"avg_confidence": 0.2, "char_count": 120, "text": "燃气轮机文本"}
    empty = {"avg_confidence": 0.0, "char_count": 0, "text": ""}

    assert "平均置信度偏低" in page_flags(low)
    assert "无文字" in page_flags(empty)


def test_text_quality_score_rewards_confidence_and_readable_text() -> None:
    poor = {"avg_confidence": 0.2, "text": "abc 123 !!!", "char_count": 11, "line_count": 1}
    better = {"avg_confidence": 0.8, "text": "燃气轮机燃烧室的压力损失较高。", "char_count": 17, "line_count": 1}

    assert text_quality_score(better) > text_quality_score(poor)


def test_choose_best_candidate_keeps_original_when_candidate_loses_text() -> None:
    original = {"avg_confidence": 0.55, "text": "燃气轮机燃烧室压力损失。" * 20, "char_count": 260, "line_count": 20}
    candidate = {"avg_confidence": 0.9, "text": "压力损失。", "char_count": 5, "line_count": 1}

    accepted, _reason, chosen, _score = choose_best_candidate(original, [candidate])

    assert accepted is False
    assert chosen["text"] == original["text"]


def test_choose_best_candidate_accepts_clear_improvement() -> None:
    original = {"avg_confidence": 0.2, "text": "燃 气 轮 机", "char_count": 7, "line_count": 1}
    candidate = {"avg_confidence": 0.75, "text": "燃气轮机燃烧室压力损失。", "char_count": 13, "line_count": 1}

    accepted, _reason, chosen, _score = choose_best_candidate(original, [candidate])

    assert accepted is True
    assert chosen["text"] == candidate["text"]
