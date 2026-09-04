# ruff: noqa: RUF001
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_ROOT = REPO_ROOT / "frontend_app" / "current_console" / "fmea"
CORE_FILES = (
    REPO_ROOT / "frontend_app" / "current_console" / "fmea.html",
    FRONTEND_ROOT / "styles.css",
    FRONTEND_ROOT / "api-client.js",
    FRONTEND_ROOT / "store.js",
    FRONTEND_ROOT / "app.js",
    FRONTEND_ROOT / "views" / "analysis.js",
    FRONTEND_ROOT / "views" / "evidence.js",
    FRONTEND_ROOT / "views" / "review.js",
)


def test_core_shell_exists_with_labeled_setup_and_accessible_navigation() -> None:
    missing = [str(path.relative_to(REPO_ROOT)) for path in CORE_FILES if not path.is_file()]
    assert not missing, f"core workbench files are missing: {missing}"

    html = CORE_FILES[0].read_text(encoding="utf-8")
    for label in (
        "访问令牌（仅当前页面内存）",
        "分析 ID",
        "行 ID",
        "修订 ID",
        "载入工作台",
        "证据",
        "字段复核",
    ):
        assert label in html
    assert '<main id="workbench-main" tabindex="-1">' in html
    assert 'aria-label="FMEA 工作台导航"' in html
    assert 'aria-live="polite"' in html


def test_core_modules_expose_the_named_client_store_and_view_interfaces() -> None:
    source = "\n".join(path.read_text(encoding="utf-8") for path in CORE_FILES if path.is_file())

    for public_name in (
        "export class FmeaClient",
        "export class WorkbenchStore",
        "export function renderAnalysisView",
        "export function renderEvidenceView",
        "export function renderReviewView",
    ):
        assert public_name in source


def test_core_source_does_not_persist_login_or_add_backend_authority() -> None:
    source = "\n".join(path.read_text(encoding="utf-8") for path in CORE_FILES if path.is_file())

    assert "localStorage" not in source
    assert "sessionStorage" not in source
    assert "sqlite" not in source.lower()
    assert "chroma" not in source.lower()
