"""Contract tests for the single-JSON FMEA review CLI."""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from scripts import fmea_skill


def test_cli_parser_has_only_review_commands() -> None:
    assert frozenset(
        {"context", "suggest", "suggestion-status", "decide", "decisions"}
    ) == fmea_skill.FMEA_REVIEW_COMMANDS
    parser = fmea_skill.build_parser()
    parsed = parser.parse_args(["review", "context", "--row-id", "row-1"])
    assert (parsed.command, parsed.review_command) == ("review", "context")
    assert parser.allow_abbrev is False
    with pytest.raises(fmea_skill.CliUsageError):
        fmea_skill.parse_cli_args(["review", "publish", "--row-id", "row-1"])


def test_cli_runtime_builder_has_no_user_supplied_connection_arguments() -> None:
    assert tuple(inspect.signature(fmea_skill.build_cli_runtime).parameters) == ()


def test_cli_source_has_no_direct_sqlite_or_http_route_dependencies() -> None:
    source = Path(fmea_skill.__file__).read_text(encoding="utf-8")
    assert "sqlite3" not in source
    assert "SqliteFmeaRepository" not in source
    assert "routes_fmea_review_v1" not in source


@pytest.mark.parametrize(
    ("payload", "expected_detail"),
    [
        ({"extra": True}, "invalid review request file"),
        ({"row_id": "row-1"}, "invalid review request file"),
    ],
)
def test_decision_request_requires_exact_top_level_keys(
    tmp_path: Path,
    payload: dict[str, object],
    expected_detail: str,
) -> None:
    request = tmp_path / "decision.json"
    request.write_text(fmea_skill.json.dumps(payload), encoding="utf-8")

    with pytest.raises(fmea_skill.CliUsageError, match=expected_detail):
        fmea_skill.load_decision_request(request)


def test_decision_request_rejects_symlink(tmp_path: Path) -> None:
    target = tmp_path / "real.json"
    target.write_text("{}", encoding="utf-8")
    link = tmp_path / "decision.json"
    try:
        link.symlink_to(target)
    except OSError as exc:
        if getattr(exc, "winerror", None) == 1314:
            pytest.skip("the Windows test account cannot create symlinks")
        raise

    with pytest.raises(fmea_skill.CliUsageError, match="invalid review request file"):
        fmea_skill.load_decision_request(link)


@pytest.mark.parametrize(
    "case",
    ["invalid_utf8", "oversized"],
)
def test_decision_request_is_utf8_and_size_bounded(tmp_path: Path, case: str) -> None:
    request = tmp_path / "decision.json"
    raw = b"\xff" if case == "invalid_utf8" else b"x" * (fmea_skill.DECISION_REQUEST_MAX_BYTES + 1)
    request.write_bytes(raw)

    with pytest.raises(fmea_skill.CliUsageError, match="invalid review request file"):
        fmea_skill.load_decision_request(request)
