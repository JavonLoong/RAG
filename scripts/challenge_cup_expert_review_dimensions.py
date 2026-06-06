from __future__ import annotations

from typing import Any


REQUIRED_EXPERT_REVIEW_DIMENSION_GROUPS: dict[str, tuple[str, ...]] = {
    "practical_value": (
        "practicality",
        "practical",
        "usefulness",
        "useful",
        "utility",
        "application_value",
        "application",
        "value",
        "实用",
        "应用",
        "价值",
        "落地",
        "场景",
    ),
    "innovation": (
        "innovation",
        "innovative",
        "novelty",
        "originality",
        "创新",
        "新颖",
        "突破",
    ),
    "boundary_rigor": (
        "boundary_rigor",
        "boundary",
        "risk",
        "safety",
        "rigor",
        "integrity",
        "credibility",
        "trustworthiness",
        "边界",
        "风险",
        "严谨",
        "可信",
        "评测",
        "合规",
        "安全",
        "诚信",
        "不伪造",
    ),
}


def normalize_review_dimension(value: str) -> str:
    return value.strip().casefold().replace("-", "_").replace(" ", "_")


def covered_required_review_dimension_groups(review_dimensions: Any) -> set[str]:
    if not isinstance(review_dimensions, list):
        return set()

    covered: set[str] = set()
    for item in review_dimensions:
        if not isinstance(item, str):
            continue
        normalized = normalize_review_dimension(item)
        if not normalized:
            continue
        for group, aliases in REQUIRED_EXPERT_REVIEW_DIMENSION_GROUPS.items():
            if any(normalize_review_dimension(alias) in normalized for alias in aliases):
                covered.add(group)
    return covered


def missing_required_review_dimension_groups(review_dimensions: Any) -> list[str]:
    covered = covered_required_review_dimension_groups(review_dimensions)
    return [group for group in REQUIRED_EXPERT_REVIEW_DIMENSION_GROUPS if group not in covered]
