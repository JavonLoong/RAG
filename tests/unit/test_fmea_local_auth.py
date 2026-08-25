"""Focused tests for loopback-only local FMEA review authentication."""

from __future__ import annotations

import pytest

from core_domain.fmea.states import ActorType
from fmea_application.review_errors import ReviewError
from fmea_infrastructure.local_auth import LocalReviewAuthProvider

_UNICODE_TOKEN = "é" * 32


def _set_valid_auth_environment(monkeypatch: pytest.MonkeyPatch, *, enabled: str = "true") -> None:
    monkeypatch.setenv("FMEA_LOCAL_AUTH_ENABLED", enabled)
    monkeypatch.setenv("FMEA_REVIEW_TOKEN", _UNICODE_TOKEN)
    monkeypatch.setenv("FMEA_REVIEW_ACTOR_ID", "local-reviewer")
    monkeypatch.setenv("FMEA_REVIEW_WORKSPACE_ID", "ws-1")


@pytest.mark.parametrize(
    ("enabled", "remote_host", "candidate", "expected_code"),
    [
        ("true", "::1", _UNICODE_TOKEN, None),
        ("true", "::ffff:127.0.0.1", _UNICODE_TOKEN, None),
        ("true", "127.0.0.1", "wrong-token", "FMEA_AUTH_REQUIRED"),
        ("true", "127.0.0.1", "\ud800" * 32, "FMEA_AUTH_REQUIRED"),
        ("true", "192.0.2.10", _UNICODE_TOKEN, "FMEA_REVIEW_FORBIDDEN"),
        ("false", "127.0.0.1", _UNICODE_TOKEN, "FMEA_AUTH_REQUIRED"),
    ],
)
def test_local_auth_security_matrix(
    monkeypatch: pytest.MonkeyPatch,
    enabled: str,
    remote_host: str,
    candidate: str,
    expected_code: str | None,
) -> None:
    _set_valid_auth_environment(monkeypatch, enabled=enabled)
    provider = LocalReviewAuthProvider.from_env()

    if expected_code is None:
        actor = provider.authenticate(candidate, remote_host)
        assert actor.actor_type is ActorType.HUMAN
        assert actor.roles == frozenset({"reviewer"})
        return

    with pytest.raises(ReviewError) as captured:
        provider.authenticate(candidate, remote_host)
    assert captured.value.code == expected_code
    assert candidate not in str(captured.value)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("FMEA_REVIEW_TOKEN", "short"),
        ("FMEA_REVIEW_TOKEN", None),
        ("FMEA_REVIEW_ACTOR_ID", "bad id"),
        ("FMEA_REVIEW_ACTOR_ID", "../actor"),
        ("FMEA_REVIEW_WORKSPACE_ID", ""),
        ("FMEA_REVIEW_WORKSPACE_ID", "x" * 129),
    ],
)
def test_local_auth_rejects_invalid_configuration_without_echo(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: str | None,
) -> None:
    _set_valid_auth_environment(monkeypatch)
    if value is None:
        monkeypatch.delenv(field)
    else:
        monkeypatch.setenv(field, value)

    with pytest.raises(ReviewError) as captured:
        LocalReviewAuthProvider.from_env()

    assert captured.value.code == "FMEA_AUTH_CONFIGURATION_INVALID"
    if value:
        assert value not in str(captured.value)
