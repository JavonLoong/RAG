"""Focused tests for loopback-only local FMEA review authentication."""

from __future__ import annotations

import pytest

from core_domain.fmea.states import ActorType
from fmea_application.review_errors import ReviewError
from fmea_infrastructure.local_auth import LocalReviewAuthProvider


def test_local_auth_accepts_configured_token_only_from_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FMEA_LOCAL_AUTH_ENABLED", "true")
    monkeypatch.setenv("FMEA_REVIEW_TOKEN", "a" * 32)
    monkeypatch.setenv("FMEA_REVIEW_ACTOR_ID", "local-reviewer")
    monkeypatch.setenv("FMEA_REVIEW_WORKSPACE_ID", "ws-1")
    provider = LocalReviewAuthProvider.from_env()

    actor = provider.authenticate("a" * 32, "127.0.0.1")

    assert actor.actor_type is ActorType.HUMAN
    assert actor.roles == frozenset({"reviewer"})
    with pytest.raises(ReviewError) as captured:
        provider.authenticate("a" * 32, "192.0.2.10")
    assert captured.value.code == "FMEA_REVIEW_FORBIDDEN"


def test_local_auth_rejects_missing_short_or_wrong_token_without_echo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FMEA_LOCAL_AUTH_ENABLED", "true")
    monkeypatch.setenv("FMEA_REVIEW_TOKEN", "short")

    with pytest.raises(ReviewError) as captured:
        LocalReviewAuthProvider.from_env()

    assert captured.value.code == "FMEA_AUTH_CONFIGURATION_INVALID"
    assert "short" not in str(captured.value)
