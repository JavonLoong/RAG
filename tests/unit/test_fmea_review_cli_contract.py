"""Contract tests for the single-JSON FMEA review CLI."""

from __future__ import annotations

import builtins
import importlib.util
import os
import sys
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


@pytest.mark.parametrize(
    "raw",
    [
        '{"row_id":"row-1","expected_record_version":1,"idempotency_key":"00000000-0000-4000-8000-000000000011","action":"accept","suggestion_id":null,"reason_code":"ACCEPT_AS_IS","reason":"ok","edits":[],"evidence_requests":[],"unresolved_acknowledgements":[],"edits":[]}',
        '{"row_id":"row-1","expected_record_version":1,"idempotency_key":"00000000-0000-4000-8000-000000000011","action":"accept","suggestion_id":null,"reason_code":"ACCEPT_AS_IS","reason":"ok","edits":[{"target_field":"controls","operation":"replace","value":[],"claim_status":"unknown","support_status":"not_supported","evidence_ids":[],"reason":"x","reason":"duplicate"}],"evidence_requests":[],"unresolved_acknowledgements":[]}',
        '{"row_id":"row-1","expected_record_version":NaN,"idempotency_key":"00000000-0000-4000-8000-000000000011","action":"accept","suggestion_id":null,"reason_code":"ACCEPT_AS_IS","reason":"ok","edits":[],"evidence_requests":[],"unresolved_acknowledgements":[]}',
    ],
    ids=["duplicate-top-level", "duplicate-nested", "non-standard-constant"],
)
def test_decision_request_rejects_duplicate_keys_and_non_standard_constants(
    tmp_path: Path, raw: str
) -> None:
    request = tmp_path / "decision.json"
    request.write_text(raw, encoding="utf-8")
    with pytest.raises(fmea_skill.CliUsageError, match="invalid review request file") as exc_info:
        fmea_skill.load_decision_request(request)
    assert "row-1" not in str(exc_info.value)
    assert "NaN" not in str(exc_info.value)


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
    ["invalid_utf8", "oversized", "deeply_nested", "nonfile", "identity_mismatch"],
)
def test_decision_request_adversarial_matrix(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    case: str,
) -> None:
    request = tmp_path / "decision.json"
    read_sizes: list[int] = []
    if case == "invalid_utf8":
        request.write_bytes(b"\xff")
    elif case == "oversized":
        request.write_bytes(b"0" * (256 * 1024 + 1))
        original_read = os.read

        def bounded_read(file_descriptor: int, size: int) -> bytes:
            read_sizes.append(size)
            return original_read(file_descriptor, size)

        monkeypatch.setattr(fmea_skill.os, "read", bounded_read)
    elif case == "deeply_nested":
        request.write_bytes((b"[" * 3000) + b"0" + (b"]" * 3000))
    elif case == "nonfile":
        request.mkdir()
    else:
        request.write_text(
            fmea_skill.json.dumps(
                {
                    "row_id": "row-1",
                    "expected_record_version": 1,
                    "idempotency_key": "00000000-0000-4000-8000-000000000011",
                    "action": "accept",
                    "suggestion_id": None,
                    "reason_code": "ACCEPT_AS_IS",
                    "reason": "Human reviewer accepts the supported row.",
                    "edits": [],
                    "evidence_requests": [],
                    "unresolved_acknowledgements": [],
                }
            ),
            encoding="utf-8",
        )
        identities = iter((True, False))
        monkeypatch.setattr(fmea_skill, "_same_file_identity", lambda _left, _right: next(identities))

    with pytest.raises(fmea_skill.CliUsageError, match="invalid review request file") as exc_info:
        fmea_skill.load_decision_request(request)
    assert str(request) not in str(exc_info.value)
    if case == "oversized":
        assert read_sizes
        assert sum(read_sizes) <= 256 * 1024 + 1
        assert max(read_sizes) <= 256 * 1024 + 1


def test_project_import_failure_after_module_import_is_sanitized(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = Path(fmea_skill.__file__)
    spec = importlib.util.spec_from_file_location("isolated_fmea_skill", source)
    assert spec is not None and spec.loader is not None
    isolated = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, isolated.__name__, isolated)
    original_import = builtins.__import__

    def blocked_project_import(name: str, *args: object, **kwargs: object):
        if name.startswith(("chroma_rag_poc", "core_domain", "fmea_application", "fmea_infrastructure")):
            raise ImportError("PRIVATE_PROJECT_PATH")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked_project_import)
    spec.loader.exec_module(isolated)

    def fail_project_import(name: str):
        if name.startswith(("chroma_rag_poc", "core_domain", "fmea_application", "fmea_infrastructure")):
            raise ImportError("PRIVATE_PROJECT_PATH")
        return original_import(name)

    monkeypatch.setattr(isolated, "import_module", fail_project_import)

    exit_code = isolated.main(["review", "context", "--row-id", "row-1"])
    captured = capsys.readouterr()

    assert exit_code == 10
    assert captured.err == ""
    assert captured.out.count("\n") == 1
    assert "PRIVATE_PROJECT_PATH" not in captured.out
    assert "traceback" not in captured.out.lower()
