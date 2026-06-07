from __future__ import annotations

import json
import re
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIR = REPO_ROOT / "docs" / "challenge_cup"
REPRO_DIR = PACKAGE_DIR / "reproducibility"
POSTER_BOARD_HTML = PACKAGE_DIR / "poster" / "challenge_cup_a0_poster.html"
OUTPUT_JSON = REPRO_DIR / "poster_render_smoke_report.json"
OUTPUT_MD = REPRO_DIR / "poster_render_smoke_report.md"

REPORT_TYPE = "challenge_cup_poster_render_smoke"
REQUIRED_TERMS = ["A0", "GraphRAG", "GT-07", "readiness gate", "browser smoke"]
NO_AWARD_BOUNDARY_TERMS = ["no award guarantee", "不承诺获奖", "特等奖保证"]
EXTERNAL_EVIDENCE_PENDING_TERMS = [
    ("real expert feedback", "真实专家反馈"),
    ("real timed rehearsal", "真实计时彩排"),
]


class LocalReferenceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for name, value in attrs:
            if name.lower() == "href" and value:
                self.hrefs.append(unescape(value))


def configure_paths(repo_root: Path) -> None:
    global REPO_ROOT, PACKAGE_DIR, REPRO_DIR, POSTER_BOARD_HTML, OUTPUT_JSON, OUTPUT_MD

    REPO_ROOT = repo_root
    PACKAGE_DIR = REPO_ROOT / "docs" / "challenge_cup"
    REPRO_DIR = PACKAGE_DIR / "reproducibility"
    POSTER_BOARD_HTML = PACKAGE_DIR / "poster" / "challenge_cup_a0_poster.html"
    OUTPUT_JSON = REPRO_DIR / "poster_render_smoke_report.json"
    OUTPUT_MD = REPRO_DIR / "poster_render_smoke_report.md"


def repo_path(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def local_references(html: str) -> list[str]:
    parser = LocalReferenceParser()
    parser.feed(html)
    references = list(parser.hrefs)
    references.extend(re.findall(r"docs/challenge_cup/[^\s<>'\")]+", html))
    cleaned = [item.rstrip(".,;:") for item in references]
    return sorted(set(item for item in cleaned if item))


def local_reference_target(reference: str) -> Path | None:
    parsed = urlparse(reference)
    if parsed.scheme or reference.startswith("#"):
        return None
    if reference.startswith("docs/challenge_cup/"):
        return REPO_ROOT / reference
    return (POSTER_BOARD_HTML.parent / reference).resolve()


def link_checks(html: str) -> dict[str, Any]:
    checked: list[dict[str, Any]] = []
    missing: list[str] = []
    for reference in local_references(html):
        target = local_reference_target(reference)
        if target is None:
            continue
        exists = target.exists()
        target_path = repo_path(target) if target.is_relative_to(REPO_ROOT) else str(target)
        checked.append({"reference": reference, "target_path": target_path, "exists": exists})
        if not exists:
            missing.append(reference)
    return {"checked": checked, "missing_targets": sorted(missing)}


def poster_dimensions_mm(html: str) -> dict[str, int | None]:
    width_match = re.search(r"\bwidth\s*:\s*(\d+)mm", html)
    height_match = re.search(r"\b(?:height|min-height)\s*:\s*(\d+)mm", html)
    return {
        "width": int(width_match.group(1)) if width_match else None,
        "height": int(height_match.group(1)) if height_match else None,
    }


def render_contract(html: str) -> dict[str, Any]:
    print_css_detected = bool(re.search(r"@page\s*\{[^}]*size\s*:\s*A0\s+landscape", html, flags=re.I | re.S))
    return {
        "page_size": "A0 landscape" if print_css_detected else "unknown",
        "poster_dimensions_mm": poster_dimensions_mm(html),
        "print_css_detected": print_css_detected,
        "smoke_type": "static_html_print_contract",
    }


def required_term_checks(html: str) -> dict[str, Any]:
    present = [term for term in REQUIRED_TERMS if term in html]
    missing = [term for term in REQUIRED_TERMS if term not in html]
    return {"required": REQUIRED_TERMS, "present": present, "missing": missing}


def any_term_present(html: str, terms: list[str]) -> bool:
    return any(term in html for term in terms)


def external_evidence_pending(html: str) -> bool:
    return all(any(term in html for term in alternatives) for alternatives in EXTERNAL_EVIDENCE_PENDING_TERMS)


def boundary_checks(html: str) -> dict[str, bool]:
    return {
        "no_award_guarantee": any_term_present(html, NO_AWARD_BOUNDARY_TERMS),
        "external_hard_evidence_pending": external_evidence_pending(html),
    }


def build_payload() -> dict[str, Any]:
    html = POSTER_BOARD_HTML.read_text(encoding="utf-8")
    contract = render_contract(html)
    terms = required_term_checks(html)
    links = link_checks(html)
    boundaries = boundary_checks(html)
    dimensions = contract["poster_dimensions_mm"]
    status = (
        "pass"
        if POSTER_BOARD_HTML.exists()
        and contract["print_css_detected"]
        and dimensions == {"width": 1189, "height": 841}
        and not terms["missing"]
        and not links["missing_targets"]
        and all(boundaries.values())
        else "fail"
    )
    return {
        "report_type": REPORT_TYPE,
        "status": status,
        "poster_path": repo_path(POSTER_BOARD_HTML),
        "render_contract": contract,
        "required_term_checks": terms,
        "link_checks": links,
        "boundary_checks": boundaries,
        "does_not_claim_award_or_external_hard_evidence": True,
    }


def write_markdown(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# Poster Render Smoke",
        "",
        f"- report_type: `{payload['report_type']}`",
        f"- status: `{payload['status']}`",
        f"- poster_path: `{payload['poster_path']}`",
        f"- page_size: `{payload['render_contract']['page_size']}`",
        f"- dimensions_mm: `{payload['render_contract']['poster_dimensions_mm']}`",
        f"- print_css_detected: `{payload['render_contract']['print_css_detected']}`",
        "- boundary: this checks poster print/render readiness only; no award guarantee is claimed, real expert feedback is still required, and real timed rehearsal evidence is still required.",
        "",
        "## Required Terms",
        "",
    ]
    lines.extend(f"- {term}" for term in payload["required_term_checks"]["present"])
    if payload["required_term_checks"]["missing"]:
        lines.extend(f"- missing: {term}" for term in payload["required_term_checks"]["missing"])
    lines.extend(["", "## Local Target Checks", ""])
    for item in payload["link_checks"]["checked"]:
        state = "pass" if item["exists"] else "missing"
        lines.append(f"- {state}: `{item['reference']}` -> `{item['target_path']}`")
    lines.extend(["", "## Boundary Checks", ""])
    for key, value in payload["boundary_checks"].items():
        lines.append(f"- {key}: `{value}`")
    write_text(path, "\n".join(lines))


def write_outputs(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or build_payload()
    write_text(OUTPUT_JSON, json.dumps(payload, ensure_ascii=False, indent=2))
    write_markdown(OUTPUT_MD, payload)
    return payload


def main() -> int:
    payload = write_outputs()
    print(f"poster render smoke: {repo_path(OUTPUT_MD)}")
    print(f"Status: {payload['status']}")
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
