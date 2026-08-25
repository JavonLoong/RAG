"""Fail-closed loopback authentication for the local FMEA review surface."""

from __future__ import annotations

import hmac
import ipaddress
import os
import re
from dataclasses import dataclass, field
from hashlib import sha256

from core_domain.fmea.states import ActorType
from fmea_application.review_contracts import ActorContext
from fmea_application.review_errors import ReviewError

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_LOOPBACK_V4 = ipaddress.IPv4Address("127.0.0.1")
_LOOPBACK_V6 = ipaddress.IPv6Address("::1")


def _configuration_error() -> ReviewError:
    return ReviewError(
        "FMEA_AUTH_CONFIGURATION_INVALID",
        "local review authentication configuration is invalid",
    )


def _valid_id(value: str | None) -> bool:
    return value is not None and _SAFE_ID.fullmatch(value) is not None


def _is_loopback_host(remote_host: str | None) -> bool:
    if not isinstance(remote_host, str) or not remote_host.strip():
        return False
    try:
        address = ipaddress.ip_address(remote_host.strip())
    except ValueError:
        return False
    if address in (_LOOPBACK_V4, _LOOPBACK_V6):
        return True
    return isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped == _LOOPBACK_V4


@dataclass(frozen=True, slots=True)
class LocalReviewAuthProvider:
    """Map one environment-owned bearer token to one server-owned human actor."""

    _enabled: bool
    _token: str | None = field(repr=False)
    _actor_id: str | None
    _workspace_id: str | None

    @classmethod
    def from_env(cls) -> LocalReviewAuthProvider:
        if os.environ.get("FMEA_LOCAL_AUTH_ENABLED") != "true":
            return cls(False, None, None, None)

        token = os.environ.get("FMEA_REVIEW_TOKEN")
        actor_id = os.environ.get("FMEA_REVIEW_ACTOR_ID")
        workspace_id = os.environ.get("FMEA_REVIEW_WORKSPACE_ID")
        if token is None:
            raise _configuration_error()
        try:
            token.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise _configuration_error() from exc
        if not 32 <= len(token) <= 512 or not _valid_id(actor_id) or not _valid_id(workspace_id):
            raise _configuration_error()
        return cls(True, token, actor_id, workspace_id)

    @property
    def token_fingerprint(self) -> str | None:
        """Return the short, non-secret correlation value for operator logs."""

        if self._token is None:
            return None
        return sha256(self._token.encode("utf-8")).hexdigest()[:12]

    def authenticate(self, bearer_token: str | None, remote_host: str | None) -> ActorContext:
        if not self._enabled:
            raise ReviewError("FMEA_AUTH_REQUIRED", "review authentication is required")
        if not _is_loopback_host(remote_host):
            raise ReviewError("FMEA_REVIEW_FORBIDDEN", "review authentication is restricted to loopback")

        expected_token = b""
        if self._token is not None:
            expected_token = self._token.encode("utf-8")
        candidate_token = b""
        if isinstance(bearer_token, str):
            try:
                candidate_token = bearer_token.encode("utf-8")
            except UnicodeEncodeError:
                candidate_token = b""
        if self._token is None or not hmac.compare_digest(candidate_token, expected_token):
            raise ReviewError("FMEA_AUTH_REQUIRED", "review authentication is required")
        if self._actor_id is None or self._workspace_id is None:
            raise _configuration_error()
        return ActorContext(
            actor_id=self._actor_id,
            actor_type=ActorType.HUMAN,
            roles=frozenset({"reviewer"}),
            workspace_id=self._workspace_id,
        )


__all__ = ["LocalReviewAuthProvider"]
