"""Named quality target profiles for project-level RAG gates."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .harness import EvaluationThresholds


@dataclass(frozen=True, slots=True)
class QualityTargetProfile:
    """A measurable target profile for local RAG and GraphRAG evaluation."""

    name: str
    description: str
    thresholds: EvaluationThresholds
    benchmark_targets: dict[str, float | int]
    required_gates: tuple[str, ...]
    proof_requirements: tuple[str, ...]
    known_gaps: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "thresholds": {
                "min_keyword_recall_at_k": self.thresholds.min_keyword_recall_at_k,
                "min_answer_completeness": self.thresholds.min_answer_completeness,
                "max_missing_citation_rate": self.thresholds.max_missing_citation_rate,
                "max_medium_or_high_risk_rate": self.thresholds.max_medium_or_high_risk_rate,
                "max_no_result_rate": self.thresholds.max_no_result_rate,
            },
            "benchmark_targets": dict(self.benchmark_targets),
            "required_gates": list(self.required_gates),
            "proof_requirements": list(self.proof_requirements),
            "known_gaps": list(self.known_gaps),
        }


OPEN_SOURCE_90_PROFILE = QualityTargetProfile(
    name="open_source_90",
    description=(
        "A strict local gate intended to move PowerRAG toward the top tier of mature "
        "open-source RAG and GraphRAG projects without changing the existing architecture."
    ),
    thresholds=EvaluationThresholds(
        min_keyword_recall_at_k=0.90,
        min_answer_completeness=0.90,
        max_missing_citation_rate=0.0,
        max_medium_or_high_risk_rate=0.02,
        max_no_result_rate=0.02,
    ),
    benchmark_targets={
        "citation_coverage": 1.00,
        "source_page_accuracy": 0.95,
        "no_answer_precision": 0.90,
        "recall_at_10": 0.90,
        "reranked_top3_evidence_hit_rate": 0.85,
        "hallucination_rate_max": 0.02,
        "permission_leak_max": 0,
        "secret_leak_max": 0,
    },
    required_gates=(
        "npm run check",
        "GraphRAG graph quality gate",
        "GraphRAG promoted triage regression",
        "RAG evaluation harness with open_source_90 thresholds",
        "external benchmark or expert gold-set run",
    ),
    proof_requirements=(
        "Every final answer cites retrieved text or graph evidence.",
        "Global, local, graph, and text retrieval routes are visible in diagnostics.",
        "Full-contact or broad analytical questions must not be answered from top-k chunks only.",
        "No-answer behavior must trigger when evidence is missing or below threshold.",
        "Large graph rendering may be skipped, but backend graph data must remain queryable.",
    ),
    known_gaps=(
        "The profile is a gate target, not a claim of achieved 90% quality by itself.",
        "A real expert gold set is still required to prove corpus-specific recall and no-answer precision.",
        "External benchmark reports should be refreshed after any retriever or GraphRAG routing change.",
    ),
)


QUALITY_PROFILES = {
    OPEN_SOURCE_90_PROFILE.name: OPEN_SOURCE_90_PROFILE,
    "industry_90": OPEN_SOURCE_90_PROFILE,
}


def get_quality_profile(name: str = "open_source_90") -> QualityTargetProfile:
    key = name.strip().lower()
    try:
        return QUALITY_PROFILES[key]
    except KeyError as exc:
        available = ", ".join(sorted(QUALITY_PROFILES))
        raise ValueError(f"Unknown quality profile {name!r}. Available profiles: {available}") from exc


def render_quality_profile_markdown(profile: QualityTargetProfile = OPEN_SOURCE_90_PROFILE) -> str:
    thresholds = profile.thresholds
    lines = [
        "# Open Source 90 Quality Gate",
        "",
        f"- Profile: `{profile.name}`",
        f"- Description: {profile.description}",
        "- Status: target gate, not a proof of achieved quality until run against a real expert gold set.",
        "",
        "## Harness Thresholds",
        "",
        "| Metric | Rule |",
        "| --- | --- |",
        f"| keyword recall@k | >= {thresholds.min_keyword_recall_at_k:.2f} |",
        f"| answer completeness | >= {thresholds.min_answer_completeness:.2f} |",
        f"| missing citation rate | <= {thresholds.max_missing_citation_rate:.2f} |",
        f"| medium/high hallucination-risk rate | <= {thresholds.max_medium_or_high_risk_rate:.2f} |",
        f"| no-result rate | <= {thresholds.max_no_result_rate:.2f} |",
        "",
        "## Benchmark Targets",
        "",
        "| Target | Value |",
        "| --- | ---: |",
    ]
    for key, value in profile.benchmark_targets.items():
        lines.append(f"| {key} | {value} |")

    lines.extend(["", "## Required Gates", ""])
    lines.extend(f"- {gate}" for gate in profile.required_gates)
    lines.extend(["", "## Proof Requirements", ""])
    lines.extend(f"- {requirement}" for requirement in profile.proof_requirements)
    lines.extend(["", "## Known Gaps", ""])
    lines.extend(f"- {gap}" for gap in profile.known_gaps)
    return "\n".join(lines).rstrip() + "\n"
