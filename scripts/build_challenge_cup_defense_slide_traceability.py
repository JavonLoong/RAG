from __future__ import annotations

import json
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from build_challenge_cup_claim_integrity_report import build_payload as build_claim_integrity_payload
from build_challenge_cup_judge_objection_matrix import build_payload as build_judge_objection_payload


REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_MD_RELATIVE = "docs/challenge_cup/reproducibility/defense_slide_traceability.md"
OUTPUT_JSON_RELATIVE = "docs/challenge_cup/reproducibility/defense_slide_traceability.json"
OUTPUT_MD = REPO_ROOT / OUTPUT_MD_RELATIVE
OUTPUT_JSON = REPO_ROOT / OUTPUT_JSON_RELATIVE
DEFENSE_DECK_PPTX_RELATIVE = "docs/challenge_cup/defense_deck/challenge_cup_defense_deck.pptx"
DEFENSE_DECK_NOTES_RELATIVE = "docs/challenge_cup/defense_deck/challenge_cup_defense_speaker_notes.md"
DEFENSE_DECK_PPTX = REPO_ROOT / DEFENSE_DECK_PPTX_RELATIVE
DEFENSE_DECK_NOTES = REPO_ROOT / DEFENSE_DECK_NOTES_RELATIVE
STATUS = "defense_slide_traceability_ready_no_rehearsal_or_award_claim"
FAIL_STATUS = "defense_slide_traceability_gap"
BOUNDARY = (
    "This report maps the defense deck slide-by-slide to local evidence, judge-objection answers, "
    "and evidence-bound claims. It does not guarantee an award, does not claim expert approval, "
    "does not claim timed rehearsal completion, and does not satisfy goal completion without real "
    "expert feedback and real timed rehearsal evidence."
)
REQUIRED_SLIDE_INDEXES = set(range(1, 11))
ALLOWED_RUBRIC_DIMENSIONS = {
    "academic_or_practical_value",
    "innovation",
    "completion",
    "defense_performance",
    "academic_norms_and_rigor",
}


SLIDE_PLAN: list[dict[str, Any]] = [
    {
        "slide_index": 1,
        "title": "知燃知维：面向动力装备运维知识的可信 GraphRAG 系统",
        "rubric_dimensions": ["completion", "defense_performance", "academic_norms_and_rigor"],
        "evidence_files": [
            "docs/challenge_cup/00_项目一页纸.md",
            "docs/challenge_cup/package_manifest.json",
            "docs/challenge_cup/reproducibility/evaluation_coverage_profile.json",
            "docs/challenge_cup/reproducibility/claim_integrity_report.md",
        ],
        "judge_objection_ids": [
            "OJ-07-expert-validation",
            "OJ-08-special-prize-claim",
            "OJ-10-project-closure",
        ],
        "claim_ids": ["package_review_ready", "evaluation_transparency", "external_hard_evidence_not_closed"],
        "notes_anchor_terms": ["知燃知维", "GraphRAG", "GT-07", "诚信边界"],
        "boundary": "Opening may frame completion readiness, but it must not imply expert endorsement or award certainty.",
    },
    {
        "slide_index": 2,
        "title": "动力装备资料难点不在问答，而在证据链能否被追溯",
        "rubric_dimensions": ["academic_or_practical_value", "innovation", "academic_norms_and_rigor"],
        "evidence_files": [
            "docs/challenge_cup/02_技术白皮书.md",
            "docs/challenge_cup/07_评审主张证据矩阵.md",
            "docs/challenge_cup/05_答辩问答手册.md",
        ],
        "judge_objection_ids": [
            "OJ-01-normal-rag",
            "OJ-03-engineer-replacement",
            "OJ-04-production-data",
        ],
        "claim_ids": [
            "graphrag_innovation_bounded",
            "human_decision_boundary",
            "application_value_bounded",
        ],
        "notes_anchor_terms": ["evidence-bound", "OCR", "GraphRAG", "工程师"],
        "boundary": "Problem framing must stay at evidence assistance and must not claim engineer replacement.",
    },
    {
        "slide_index": 3,
        "title": "工程闭环覆盖资料导入、检索增强、图谱证据和评测门禁",
        "rubric_dimensions": ["innovation", "completion"],
        "evidence_files": [
            "docs/challenge_cup/02_技术白皮书.md",
            "evaluation/system_eval_questions.jsonl",
            "evaluation/reports/challenge_cup_graphrag_context_demo.md",
            "docs/challenge_cup/package_manifest.json",
        ],
        "judge_objection_ids": [
            "OJ-01-normal-rag",
            "OJ-06-cherry-picked-evaluation",
            "OJ-10-project-closure",
        ],
        "claim_ids": ["graphrag_innovation_bounded", "evaluation_transparency", "package_review_ready"],
        "notes_anchor_terms": ["OCR", "RAG", "KG", "Gate"],
        "boundary": "Architecture proves an implemented workflow, not production deployment certification.",
    },
    {
        "slide_index": 4,
        "title": "60 题评测集把“能演示”压实为“能复核”",
        "rubric_dimensions": ["innovation", "completion", "academic_norms_and_rigor"],
        "evidence_files": [
            "evaluation/system_eval_questions.jsonl",
            "docs/challenge_cup/03_实验评测报告.md",
            "evaluation/reports/challenge_cup_graphrag_answer_benchmark.md",
            "docs/challenge_cup/reproducibility/evaluation_coverage_profile.json",
        ],
        "judge_objection_ids": [
            "OJ-02-graphrag-baseline",
            "OJ-06-cherry-picked-evaluation",
        ],
        "claim_ids": ["evaluation_transparency", "graphrag_innovation_bounded"],
        "notes_anchor_terms": ["60", "11", "17", "supported=10"],
        "boundary": "Evaluation coverage is local reproducibility evidence, not an online LLM win-rate claim.",
    },
    {
        "slide_index": 5,
        "title": "固定应用场景：GT-07 燃气轮机异常振动诊断流程",
        "rubric_dimensions": ["academic_or_practical_value", "defense_performance"],
        "evidence_files": [
            "docs/challenge_cup/11_应用场景与专家验证.md",
            "docs/challenge_cup/reproducibility/application_value_quantification.md",
            "docs/challenge_cup/reproducibility/browser_demo_smoke_report.json",
            "docs/challenge_cup/reproducibility/numeric_traceability_report.md",
        ],
        "judge_objection_ids": [
            "OJ-03-engineer-replacement",
            "OJ-04-production-data",
            "OJ-05-live-demo-failure",
        ],
        "claim_ids": ["application_value_bounded", "human_decision_boundary", "defense_demo_fallback_ready"],
        "notes_anchor_terms": ["GT-07", "异常振动", "5", "41.80", "人工确认"],
        "boundary": "The GT-07 workflow is a fixed local scenario, not production validation or final maintenance authority.",
    },
    {
        "slide_index": 6,
        "title": "GraphRAG 价值不靠泛化承诺，而靠关系证据可视化",
        "rubric_dimensions": ["innovation", "academic_norms_and_rigor"],
        "evidence_files": [
            "docs/challenge_cup/02_技术白皮书.md",
            "evaluation/reports/challenge_cup_graphrag_same_question_report.md",
            "evaluation/reports/challenge_cup_graphrag_gap_remediation_plan.md",
            "docs/challenge_cup/reproducibility/graphrag_manual_evidence_supplement.csv",
        ],
        "judge_objection_ids": [
            "OJ-01-normal-rag",
            "OJ-02-graphrag-baseline",
            "OJ-06-cherry-picked-evaluation",
        ],
        "claim_ids": ["graphrag_innovation_bounded", "evaluation_transparency"],
        "notes_anchor_terms": ["GraphRAG", "关系证据", "P0 missing", "baseline"],
        "boundary": "GraphRAG is claimed as relationship-evidence organization, not universal baseline superiority.",
    },
    {
        "slide_index": 7,
        "title": "结项提交不是散文件：已形成归档包、哈希和机器门禁",
        "rubric_dimensions": ["completion", "defense_performance", "academic_norms_and_rigor"],
        "evidence_files": [
            "docs/challenge_cup/package_manifest.json",
            "docs/challenge_cup/reproducibility/evidence_hashes.json",
            "docs/challenge_cup/reproducibility/challenge_cup_submission_archive_manifest.json",
            "docs/challenge_cup/reproducibility/readiness_gate_report.md",
        ],
        "judge_objection_ids": [
            "OJ-05-live-demo-failure",
            "OJ-09-ip-and-compliance",
            "OJ-10-project-closure",
        ],
        "claim_ids": ["package_review_ready", "defense_demo_fallback_ready"],
        "notes_anchor_terms": ["SHA256", "README", "readiness gate", "manifest"],
        "boundary": "Archive counts and byte sizes must be read from manifest as source of truth; gate status is not an award guarantee.",
    },
    {
        "slide_index": 8,
        "title": "特等奖争取点：创新性、完成度、可复现和边界严谨同时成立",
        "rubric_dimensions": [
            "academic_or_practical_value",
            "innovation",
            "completion",
            "defense_performance",
            "academic_norms_and_rigor",
        ],
        "evidence_files": [
            "docs/challenge_cup/08_特等奖评审自评表.md",
            "docs/challenge_cup/reproducibility/official_rubric_alignment.md",
            "docs/challenge_cup/reproducibility/special_prize_readiness_dashboard.md",
            "docs/challenge_cup/reproducibility/rubric_defense_coverage.md",
        ],
        "judge_objection_ids": [
            "OJ-01-normal-rag",
            "OJ-02-graphrag-baseline",
            "OJ-08-special-prize-claim",
        ],
        "claim_ids": [
            "special_prize_competition_argument",
            "graphrag_innovation_bounded",
            "package_review_ready",
            "evaluation_transparency",
        ],
        "notes_anchor_terms": ["创新性", "完成度", "可复现", "获奖保证"],
        "boundary": "Special-prize positioning is an evidence-backed competition argument, not a result prediction.",
    },
    {
        "slide_index": 9,
        "title": "专家反馈与彩排是最后硬证据：已准备采集，不伪造结果",
        "rubric_dimensions": ["defense_performance", "academic_norms_and_rigor"],
        "evidence_files": [
            "docs/challenge_cup/reproducibility/expert_feedback_request_packet.md",
            "docs/challenge_cup/reproducibility/hard_evidence_ledger.md",
            "docs/challenge_cup/reproducibility/timed_rehearsal_schedule_ledger.md",
            "docs/challenge_cup/reproducibility/defense_rehearsal_result_packet.md",
        ],
        "judge_objection_ids": [
            "OJ-07-expert-validation",
            "OJ-08-special-prize-claim",
            "OJ-10-project-closure",
        ],
        "claim_ids": ["external_hard_evidence_not_closed", "special_prize_competition_argument"],
        "notes_anchor_terms": ["ready-to-send", "ready-to-record", "专家反馈", "真实彩排"],
        "boundary": "Prepared packets are not real expert approval and are not completed timed rehearsal evidence.",
    },
    {
        "slide_index": 10,
        "title": "90 秒讲清项目，3 分钟证明它能被复核",
        "rubric_dimensions": ["completion", "defense_performance", "academic_norms_and_rigor"],
        "evidence_files": [
            "docs/challenge_cup/defense_deck/challenge_cup_defense_speaker_notes.md",
            "docs/challenge_cup/reproducibility/readiness_gate_report.md",
            "docs/challenge_cup/reproducibility/final_acceptance_audit.md",
            "docs/challenge_cup/reproducibility/claim_integrity_report.md",
        ],
        "judge_objection_ids": [
            "OJ-05-live-demo-failure",
            "OJ-07-expert-validation",
            "OJ-08-special-prize-claim",
            "OJ-10-project-closure",
        ],
        "claim_ids": [
            "package_review_ready",
            "defense_demo_fallback_ready",
            "external_hard_evidence_not_closed",
            "special_prize_competition_argument",
        ],
        "notes_anchor_terms": ["90s", "180s", "20s", "30s", "0"],
        "boundary": "Closing may claim package review readiness only; final goal completion still needs real hard evidence.",
    },
]


def repo_path(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def is_safe_repo_path(relative: str) -> bool:
    posix = PurePosixPath(relative)
    return (
        bool(relative)
        and not relative.startswith(("http://", "https://"))
        and not posix.is_absolute()
        and ".." not in posix.parts
        and "\\" not in relative
        and relative.startswith(("docs/", "evaluation/"))
    )


def existing_repo_file(relative: str) -> bool:
    path = REPO_ROOT / relative
    return path.exists() and path.stat().st_size > 0


def unique_paths(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        relative = str(value).strip()
        if relative and relative not in seen:
            seen.add(relative)
            unique.append(relative)
    return unique


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", "", text).lower()


def extract_pptx_slide_texts(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as archive:
        slide_names = sorted(
            (name for name in archive.namelist() if name.startswith("ppt/slides/slide") and name.endswith(".xml")),
            key=lambda name: int(re.search(r"slide(\d+)\.xml$", name).group(1)),
        )
        texts: list[str] = []
        for name in slide_names:
            root = ET.fromstring(archive.read(name))
            texts.append("\n".join(node.text or "" for node in root.iter() if node.tag.endswith("}t")))
    return texts


def anchor_present(anchor: str, slide_text: str, notes_text: str) -> bool:
    normalized_anchor = normalize_text(anchor)
    return normalized_anchor in normalize_text(slide_text) or normalized_anchor in normalize_text(notes_text)


def build_payload() -> dict[str, Any]:
    objection_payload = build_judge_objection_payload()
    claim_payload = build_claim_integrity_payload()
    objection_ids = {
        str(item.get("objection_id", ""))
        for item in objection_payload.get("objections", [])
        if isinstance(item, dict)
    }
    claim_ids = {
        str(item.get("claim_id", ""))
        for item in claim_payload.get("claims", [])
        if isinstance(item, dict)
    }

    gaps: list[str] = []
    if not DEFENSE_DECK_PPTX.exists():
        gaps.append(f"defense deck missing: {DEFENSE_DECK_PPTX_RELATIVE}")
        slide_texts: list[str] = []
    else:
        try:
            slide_texts = extract_pptx_slide_texts(DEFENSE_DECK_PPTX)
        except (OSError, zipfile.BadZipFile, ET.ParseError, AttributeError) as exc:
            gaps.append(f"defense deck unreadable: {exc}")
            slide_texts = []
    notes_text = DEFENSE_DECK_NOTES.read_text(encoding="utf-8") if DEFENSE_DECK_NOTES.exists() else ""
    if not notes_text.strip():
        gaps.append(f"speaker notes missing or empty: {DEFENSE_DECK_NOTES_RELATIVE}")

    report_outputs = {OUTPUT_MD_RELATIVE, OUTPUT_JSON_RELATIVE}
    slides: list[dict[str, Any]] = []
    for plan in SLIDE_PLAN:
        index = int(plan["slide_index"])
        slide_text = slide_texts[index - 1] if index <= len(slide_texts) else ""
        row_gaps: list[str] = []
        if not slide_text.strip():
            row_gaps.append(f"slide {index}: pptx text missing")
        if normalize_text(str(plan["title"])) not in normalize_text(slide_text):
            row_gaps.append(f"slide {index}: title not found in pptx text")

        rubric_dimensions = [str(value) for value in plan["rubric_dimensions"]]
        missing_dimensions = sorted(set(rubric_dimensions) - ALLOWED_RUBRIC_DIMENSIONS)
        if missing_dimensions:
            row_gaps.append(f"slide {index}: unknown rubric dimensions {missing_dimensions}")

        evidence_files = unique_paths([str(path) for path in plan["evidence_files"]])
        if len(evidence_files) < 2:
            row_gaps.append(f"slide {index}: fewer than 2 evidence files")
        for relative in evidence_files:
            if not is_safe_repo_path(relative):
                row_gaps.append(f"slide {index}: unsafe evidence path {relative}")
            elif relative in report_outputs:
                row_gaps.append(f"slide {index}: self-references defense slide traceability output: {relative}")
            elif not existing_repo_file(relative):
                row_gaps.append(f"slide {index}: evidence file missing or empty {relative}")

        missing_objections = sorted(item for item in plan["judge_objection_ids"] if item not in objection_ids)
        if missing_objections:
            row_gaps.append(f"slide {index}: missing judge_objection_ids {missing_objections}")
        missing_claims = sorted(item for item in plan["claim_ids"] if item not in claim_ids)
        if missing_claims:
            row_gaps.append(f"slide {index}: missing claim_ids {missing_claims}")

        missing_anchors = [
            str(anchor)
            for anchor in plan["notes_anchor_terms"]
            if not anchor_present(str(anchor), slide_text, notes_text)
        ]
        if missing_anchors:
            row_gaps.append(f"slide {index}: missing anchor terms {missing_anchors}")
        if not str(plan["boundary"]).strip():
            row_gaps.append(f"slide {index}: boundary missing")

        gaps.extend(row_gaps)
        slides.append(
            {
                "slide_index": index,
                "title": str(plan["title"]),
                "coverage_status": "covered" if not row_gaps else "gap",
                "rubric_dimensions": rubric_dimensions,
                "evidence_files": evidence_files,
                "judge_objection_ids": [str(item) for item in plan["judge_objection_ids"]],
                "claim_ids": [str(item) for item in plan["claim_ids"]],
                "notes_anchor_terms": [str(item) for item in plan["notes_anchor_terms"]],
                "boundary": str(plan["boundary"]),
            }
        )

    actual_slide_indexes = {item["slide_index"] for item in slides}
    if len(slide_texts) != len(REQUIRED_SLIDE_INDEXES):
        gaps.append(f"pptx slide count={len(slide_texts)}, expected={len(REQUIRED_SLIDE_INDEXES)}")
    missing_slide_indexes = sorted(REQUIRED_SLIDE_INDEXES - actual_slide_indexes)
    if missing_slide_indexes:
        gaps.append(f"missing slide indexes: {missing_slide_indexes}")

    covered_slide_count = sum(1 for item in slides if item["coverage_status"] == "covered")
    coverage_complete = covered_slide_count == len(REQUIRED_SLIDE_INDEXES) and not gaps
    return {
        "report_type": "challenge_cup_defense_slide_traceability",
        "checked_at": "2026-06-06",
        "status": STATUS if coverage_complete else FAIL_STATUS,
        "completion_claim_allowed": False,
        "does_not_satisfy_goal_completion": True,
        "award_guarantee_claimed": False,
        "expert_approval_claimed": False,
        "timed_rehearsal_completion_claimed": False,
        "coverage_complete": coverage_complete,
        "slide_count": len(slide_texts),
        "covered_slide_count": covered_slide_count,
        "slides": slides,
        "gaps": gaps,
        "source_assets": {
            "defense_deck": DEFENSE_DECK_PPTX_RELATIVE,
            "speaker_notes": DEFENSE_DECK_NOTES_RELATIVE,
            "archive_source_of_truth": "docs/challenge_cup/reproducibility/challenge_cup_submission_archive_manifest.json",
        },
        "boundary": BOUNDARY,
        "verification_commands": [
            "python scripts/build_challenge_cup_defense_slide_traceability.py",
            "python scripts/build_challenge_cup_package.py",
            "python scripts/check_challenge_cup_readiness.py",
        ],
        "output_files": [OUTPUT_MD_RELATIVE, OUTPUT_JSON_RELATIVE],
    }


def build_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Defense Slide Traceability",
        "",
        f"- status: `{payload['status']}`",
        f"- coverage_complete: `{payload['coverage_complete']}`",
        f"- covered slides: {payload['covered_slide_count']}/{len(REQUIRED_SLIDE_INDEXES)}",
        "- boundary: no award guarantee; no fake expert approval; no timed rehearsal completion claim",
        "- archive numbers: use submission archive manifest as the source of truth",
        "",
        "## Slide Coverage",
        "",
        "| Slide | Status | Title | Rubric Dimensions | Judge Objections | Claim IDs | Evidence | Boundary |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in payload["slides"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    f"slide {item['slide_index']}",
                    str(item["coverage_status"]),
                    str(item["title"]),
                    "<br>".join(f"`{value}`" for value in item["rubric_dimensions"]),
                    "<br>".join(f"`{value}`" for value in item["judge_objection_ids"]),
                    "<br>".join(f"`{value}`" for value in item["claim_ids"]),
                    "<br>".join(f"`{value}`" for value in item["evidence_files"]),
                    str(item["boundary"]),
                ]
            )
            + " |"
        )

    lines.extend(["", "## Source Assets", ""])
    for label, relative in payload["source_assets"].items():
        lines.append(f"- {label}: `{relative}`")
    lines.extend(["", "## Gaps", ""])
    if payload["gaps"]:
        lines.extend(f"- {gap}" for gap in payload["gaps"])
    else:
        lines.append("- none")
    lines.extend(["", "## Boundary", "", str(payload["boundary"])])
    return "\n".join(lines).rstrip() + "\n"


def write_outputs() -> dict[str, Any]:
    payload = build_payload()
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    OUTPUT_MD.write_text(build_markdown(payload), encoding="utf-8")
    return payload


def main() -> int:
    payload = write_outputs()
    print(f"defense slide traceability: {repo_path(OUTPUT_MD)}")
    print(f"Status: {payload['status']}")
    return 0 if payload["status"] == STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
