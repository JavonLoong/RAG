from __future__ import annotations

import json
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_MD_RELATIVE = "docs/challenge_cup/reproducibility/runtime_reproducibility_snapshot.md"
OUTPUT_JSON_RELATIVE = "docs/challenge_cup/reproducibility/runtime_reproducibility_snapshot.json"
OUTPUT_MD = REPO_ROOT / OUTPUT_MD_RELATIVE
OUTPUT_JSON = REPO_ROOT / OUTPUT_JSON_RELATIVE
BROWSER_SMOKE_JSON_RELATIVE = "docs/challenge_cup/reproducibility/browser_demo_smoke_report.json"
BROWSER_SMOKE_JSON = REPO_ROOT / BROWSER_SMOKE_JSON_RELATIVE

REPORT_TYPE = "challenge_cup_runtime_reproducibility_snapshot"
STATUS = "runtime_snapshot_ready_no_environment_portability_claim"
RUNTIME_SCOPE = "local challenge-cup package reproduction environment"
BOUNDARY = (
    "This snapshot records the local runtime used to reproduce the challenge-cup package; it is not a "
    "production deployment certification, does not guarantee a special-prize result, and does not replace "
    "real expert feedback or real timed rehearsal evidence."
)


def repo_path(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def run_command(command: list[str], timeout: int = 10) -> str:
    try:
        result = subprocess.run(
            command,
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"unavailable: {exc}"
    output = (result.stdout or result.stderr).strip()
    if result.returncode != 0:
        return f"unavailable: exit {result.returncode}; {output}".strip()
    return output or "available"


def project_python_path() -> Path:
    return REPO_ROOT / ".venv" / "Scripts" / "python.exe"


def browser_smoke_json_path() -> Path:
    return REPO_ROOT / BROWSER_SMOKE_JSON_RELATIVE


def read_browser_smoke() -> dict[str, Any]:
    path = browser_smoke_json_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def collect_browser_automation() -> dict[str, Any]:
    browser = read_browser_smoke().get("browser", {})
    if not isinstance(browser, dict):
        browser = {}
    return {
        "source_report": BROWSER_SMOKE_JSON_RELATIVE,
        "playwright_source": str(browser.get("playwright_source") or "unavailable"),
        "frontend_url": str(browser.get("frontend_url") or "unavailable"),
        "browser_smoke_status": str(read_browser_smoke().get("status") or "unavailable"),
    }


def build_payload() -> dict[str, Any]:
    project_python = project_python_path()
    node_version = run_command(["node", "--version"])
    return {
        "report_type": REPORT_TYPE,
        "status": STATUS,
        "completion_claim_allowed": False,
        "does_not_satisfy_goal_completion": True,
        "external_validation_claimed": False,
        "runtime_scope": RUNTIME_SCOPE,
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "python": {
            "current_executable": sys.executable,
            "current_version": platform.python_version(),
            "project_python": ".venv/Scripts/python.exe",
            "project_venv_present": project_python.exists(),
            "pytest_probe": run_command([str(project_python if project_python.exists() else sys.executable), "-m", "pytest", "--version"]),
        },
        "node": {
            "node_available": not node_version.startswith("unavailable:"),
            "node_version": node_version,
            "package_json_present": (REPO_ROOT / "package.json").exists(),
            "package_lock_present": (REPO_ROOT / "package-lock.json").exists(),
            "node_modules_present": (REPO_ROOT / "node_modules").exists(),
        },
        "browser_automation": collect_browser_automation(),
        "repository_controls": {
            "package_manifest": "docs/challenge_cup/package_manifest.json",
            "evidence_hashes": "docs/challenge_cup/reproducibility/evidence_hashes.json",
            "submission_archive_manifest": (
                "docs/challenge_cup/reproducibility/challenge_cup_submission_archive_manifest.json"
            ),
            "submission_verifier": "docs/challenge_cup/reproducibility/verify_submission_package.py",
        },
        "verification_commands": [
            ".\\.venv\\Scripts\\python.exe docs/challenge_cup/reproducibility/verify_submission_package.py --root .",
            ".\\.venv\\Scripts\\python.exe scripts/check_challenge_cup_readiness.py",
            ".\\.venv\\Scripts\\python.exe -m pytest tests/unit -q",
        ],
        "boundary": BOUNDARY,
        "output_files": [OUTPUT_MD_RELATIVE, OUTPUT_JSON_RELATIVE],
    }


def write_markdown(payload: dict[str, Any]) -> None:
    lines = [
        "# Runtime Reproducibility Snapshot",
        "",
        f"- report_type: `{payload['report_type']}`",
        f"- status: `{payload['status']}`",
        f"- runtime_scope: {payload['runtime_scope']}",
        f"- completion_claim_allowed: `{payload['completion_claim_allowed']}`",
        f"- does_not_satisfy_goal_completion: `{payload['does_not_satisfy_goal_completion']}`",
        f"- external_validation_claimed: `{payload['external_validation_claimed']}`",
        "",
        "## Python Runtime",
        "",
        f"- current executable: `{payload['python']['current_executable']}`",
        f"- current version: `{payload['python']['current_version']}`",
        f"- project python: `{payload['python']['project_python']}`",
        f"- project venv present: `{payload['python']['project_venv_present']}`",
        f"- pytest probe: `{payload['python']['pytest_probe']}`",
        "",
        "## Node And Browser Automation",
        "",
        f"- node version: `{payload['node']['node_version']}`",
        f"- package.json present: `{payload['node']['package_json_present']}`",
        f"- package-lock.json present: `{payload['node']['package_lock_present']}`",
        f"- node_modules present: `{payload['node']['node_modules_present']}`",
        f"- Playwright source: `{payload['browser_automation']['playwright_source']}`",
        f"- frontend URL: `{payload['browser_automation']['frontend_url']}`",
        "",
        "## Repository Controls",
        "",
    ]
    lines.extend(f"- `{value}`" for value in payload["repository_controls"].values())
    lines.extend(["", "## Verification Commands", ""])
    lines.extend(f"- `{command}`" for command in payload["verification_commands"])
    lines.extend(["", "## Boundary", "", payload["boundary"]])
    write_text(OUTPUT_MD, "\n".join(lines))


def write_outputs() -> dict[str, Any]:
    payload = build_payload()
    write_text(OUTPUT_JSON, json.dumps(payload, ensure_ascii=False, indent=2))
    write_markdown(payload)
    return payload


def main() -> int:
    payload = write_outputs()
    print(f"runtime reproducibility snapshot: {repo_path(OUTPUT_MD)}")
    print(f"Status: {payload['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
