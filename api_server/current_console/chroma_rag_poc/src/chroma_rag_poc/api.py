from __future__ import annotations

import io
import base64
import hashlib
import os
import re
import secrets
import shutil
import sys
import tempfile
import time
import zipfile
from collections import Counter
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request as UrlRequest, urlopen

import jwt
import orjson
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .benchmark import run_synthetic_benchmark
from .embeddings import DEFAULT_SENTENCE_TRANSFORMER_MODEL
from .observability import OperationLogger
from .parsing import get_source_kind, is_supported_source, supported_source_extensions
from .pipeline import (
    DEFAULT_PERSIST_DIR,
    DEFAULT_UPLOAD_DIR,
    RETRIEVAL_POLICY_FILENAME,
    _close_client,
    _create_client,
    approve_collection_retrieval_policy_proposal,
    build_empty_hybrid_retrieval_diagnostics,
    dispatch_retrieval_policy_notifications,
    get_all_stats,
    get_collection_retrieval_policy_history,
    get_collection_stats,
    get_retrieval_policy_identity_provider_config,
    ingest_source_payloads,
    list_retrieval_policy_notification_recipients,
    list_retrieval_policy_notifications,
    propose_collection_retrieval_policy,
    promote_collection_retrieval_policy,
    query_collection,
    reject_collection_retrieval_policy_proposal,
    rollback_collection_retrieval_policy,
    sync_retrieval_policy_identity_directory,
    upsert_retrieval_policy_identity_provider_config,
    upsert_retrieval_policy_notification_recipient,
    upsert_retrieval_policy_role,
)
from .public_books_json import ingest_latest_snapshot_to_chroma, write_ingest_summary

REPO_ROOT = Path(__file__).resolve().parents[5]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from model_adapters.llm import OpenAICompatibleLLMClient
from rag_orchestrator.advanced_query import ADVANCED_QUERY_ROUTES, AdvancedQueryExecutor
from rag_orchestrator.graphrag_qa import GraphRagQAOrchestrator
from rag_orchestrator.graph_quality import evaluate_graph_quality
from rag_orchestrator.lightrag import LightRagDiagnostics
from rag_orchestrator.global_search import GlobalSearchOrchestrator
from rag_orchestrator.query_understanding import QueryRouteName, SemanticQueryAnalyzer
from rag_orchestrator.router import (
    AdaptiveQueryRouter,
    QueryRoute,
    RoutingDecision,
)
from rag_orchestrator.triage import GraphRagTriageStore
from retrieval_engine.graph import SQLiteGraphRetriever
from storage_layer.graph_store import GraphStore

PACKAGE_FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"
RETRIEVAL_POLICY_SESSION_COOKIE = "rag_policy_session"
RETRIEVAL_POLICY_SESSION_FILENAME = "retrieval_policy_sessions.json"
RETRIEVAL_POLICY_OIDC_STATE_COOKIE = "rag_policy_oidc_state"
RETRIEVAL_POLICY_OIDC_STATE_FILENAME = "retrieval_policy_oidc_states.json"


def _env_truthy(name: str) -> bool:
    return os.getenv(name, "").strip().casefold() in {"1", "true", "yes", "on"}


def _persisted_retrieval_policy_oidc_config(persist_dir: Path) -> dict[str, Any]:
    identity_provider = get_retrieval_policy_identity_provider_config(persist_dir).get("identity_provider", {})
    if not isinstance(identity_provider, dict):
        return {}
    nested = identity_provider.get("oidc")
    if isinstance(nested, dict):
        return nested
    return identity_provider


def _retrieval_policy_oidc_config(persist_dir: Path) -> dict[str, Any]:
    required_env = os.getenv("RAG_POLICY_OIDC_REQUIRED", "").strip()
    if required_env:
        if not _env_truthy("RAG_POLICY_OIDC_REQUIRED"):
            return {}
        return {
            "enabled": True,
            "issuer": os.getenv("RAG_POLICY_OIDC_ISSUER", "").strip(),
            "audience": os.getenv("RAG_POLICY_OIDC_AUDIENCE", "").strip(),
            "jwks_url": os.getenv("RAG_POLICY_OIDC_JWKS_URL", "").strip(),
            "subject_claim": os.getenv("RAG_POLICY_OIDC_SUBJECT_CLAIM", "email").strip() or "email",
            "groups_claim": os.getenv("RAG_POLICY_OIDC_GROUPS_CLAIM", "groups").strip() or "groups",
            "algorithms": [
                item.strip()
                for item in os.getenv("RAG_POLICY_OIDC_ALGORITHMS", "RS256").split(",")
                if item.strip()
            ] or ["RS256"],
        }
    persisted = _persisted_retrieval_policy_oidc_config(persist_dir)
    if not isinstance(persisted, dict) or persisted.get("enabled") is not True:
        return {}
    return {
        "enabled": True,
        "issuer": str(persisted.get("issuer") or "").strip(),
        "audience": str(persisted.get("audience") or "").strip(),
        "jwks_url": str(persisted.get("jwks_url") or "").strip(),
        "subject_claim": str(persisted.get("subject_claim") or "email").strip() or "email",
        "groups_claim": str(persisted.get("groups_claim") or "groups").strip() or "groups",
        "algorithms": [
            str(item or "").strip()
            for item in persisted.get("algorithms", ["RS256"])
            if str(item or "").strip()
        ] or ["RS256"],
    }


def _decode_retrieval_policy_oidc_token(token: str, oidc_config: dict[str, Any]) -> dict[str, Any]:
    issuer = str(oidc_config.get("issuer") or "").strip()
    audience = str(oidc_config.get("audience") or "").strip()
    jwks_url = str(oidc_config.get("jwks_url") or "").strip()
    if not issuer or not audience or not jwks_url:
        raise HTTPException(status_code=500, detail="OIDC policy auth requires issuer, audience, and JWKS URL")

    algorithms = [
        str(item or "").strip()
        for item in oidc_config.get("algorithms", ["RS256"])
        if str(item or "").strip()
    ] or ["RS256"]
    try:
        signing_key = jwt.PyJWKClient(jwks_url).get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=algorithms,
            audience=audience,
            issuer=issuer,
        )
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"OIDC bearer token validation failed: {exc}") from exc

    subject_claim = str(oidc_config.get("subject_claim") or "email").strip() or "email"
    subject = (
        claims.get(subject_claim)
        or claims.get("preferred_username")
        or claims.get("email")
        or claims.get("sub")
    )
    if not str(subject or "").strip():
        raise HTTPException(status_code=401, detail="OIDC bearer token does not contain a usable subject")
    groups_claim = str(oidc_config.get("groups_claim") or "groups").strip() or "groups"
    groups = claims.get(groups_claim)
    if not isinstance(groups, list):
        groups = []
    return {
        "subject": str(subject).strip(),
        "groups": [str(group).strip() for group in groups if str(group).strip()],
        "identity_source": "oidc",
    }


def _retrieval_policy_session_path(persist_dir: Path) -> Path:
    return Path(persist_dir) / RETRIEVAL_POLICY_SESSION_FILENAME


def _read_retrieval_policy_sessions(persist_dir: Path) -> dict[str, Any]:
    session_path = _retrieval_policy_session_path(persist_dir)
    try:
        payload = orjson.loads(session_path.read_bytes()) if session_path.exists() else {}
    except (OSError, orjson.JSONDecodeError):
        payload = {}
    return payload if isinstance(payload, dict) else {}


def _write_retrieval_policy_sessions(persist_dir: Path, sessions: dict[str, Any]) -> None:
    session_path = _retrieval_policy_session_path(persist_dir)
    session_path.parent.mkdir(parents=True, exist_ok=True)
    session_path.write_bytes(orjson.dumps(sessions, option=orjson.OPT_INDENT_2))


def _append_retrieval_policy_audit_entry(persist_dir: Path, entry: dict[str, Any]) -> dict[str, Any]:
    policy_path = Path(persist_dir) / RETRIEVAL_POLICY_FILENAME
    try:
        payload = orjson.loads(policy_path.read_bytes()) if policy_path.exists() else {}
    except (OSError, orjson.JSONDecodeError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    audit = payload.get("audit") if isinstance(payload.get("audit"), list) else []
    allowed_keys = {
        "action",
        "admin",
        "admin_role",
        "role_source",
        "active_key_id",
        "rotated_count",
        "skipped_count",
        "expired_pruned_count",
        "session_count",
        "rotated_session_ids",
        "revoked_session_id",
        "revoked",
    }
    audit_entry: dict[str, Any] = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }
    for key in allowed_keys:
        if key not in entry:
            continue
        value = entry[key]
        if isinstance(value, str):
            audit_entry[key] = value.strip()
        elif isinstance(value, bool):
            audit_entry[key] = value
        elif isinstance(value, int):
            audit_entry[key] = value
        elif isinstance(value, list):
            audit_entry[key] = [str(item).strip() for item in value if str(item).strip()]
    audit.append(audit_entry)
    payload["audit"] = audit
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path.write_bytes(orjson.dumps(payload, option=orjson.OPT_INDENT_2))
    return audit_entry


def _decode_base64url_secret(value: str) -> bytes:
    raw = str(value or "").strip()
    if not raw:
        raise HTTPException(status_code=500, detail="OIDC session encryption key is empty")
    padded = raw + "=" * (-len(raw) % 4)
    try:
        return base64.urlsafe_b64decode(padded.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise HTTPException(status_code=500, detail="OIDC session encryption key must be base64url encoded") from exc


def _retrieval_policy_session_secret_keys() -> list[tuple[str, bytes]]:
    raw_keyring = str(os.getenv("RAG_POLICY_SESSION_SECRET_KEYS") or "").strip()
    legacy_key = str(os.getenv("RAG_POLICY_SESSION_SECRET_KEY") or "").strip()
    if not raw_keyring and legacy_key:
        raw_keyring = f"default:{legacy_key}"
    if not raw_keyring:
        return []
    keys: list[tuple[str, bytes]] = []
    for index, entry in enumerate(raw_keyring.split(",")):
        item = entry.strip()
        if not item:
            continue
        if ":" in item:
            kid, encoded_key = item.split(":", 1)
            kid = kid.strip() or f"key-{index + 1}"
        else:
            kid = f"key-{index + 1}"
            encoded_key = item
        key = _decode_base64url_secret(encoded_key)
        if len(key) not in {16, 24, 32}:
            raise HTTPException(status_code=500, detail="OIDC session encryption keys must decode to 16, 24, or 32 bytes")
        keys.append((kid, key))
    if not keys:
        raise HTTPException(status_code=500, detail="OIDC session encryption keyring is empty")
    return keys


def _encrypt_retrieval_policy_session_secret(secret: str) -> dict[str, Any] | None:
    value = str(secret or "").strip()
    if not value:
        return None
    keys = _retrieval_policy_session_secret_keys()
    if not keys:
        return None
    kid, key = keys[0]
    nonce = secrets.token_bytes(12)
    ciphertext = AESGCM(key).encrypt(nonce, value.encode("utf-8"), b"retrieval-policy-session-refresh-token")
    return {
        "alg": "AESGCM",
        "kid": kid,
        "nonce": _base64url_no_padding(nonce),
        "ciphertext": _base64url_no_padding(ciphertext),
    }


def _decrypt_retrieval_policy_session_secret(record: dict[str, Any]) -> str:
    encrypted = record.get("refresh_token_encrypted")
    if not isinstance(encrypted, dict):
        return str(record.get("refresh_token") or "").strip()
    kid = str(encrypted.get("kid") or "").strip()
    nonce = _decode_base64url_secret(str(encrypted.get("nonce") or ""))
    ciphertext = _decode_base64url_secret(str(encrypted.get("ciphertext") or ""))
    keyring = _retrieval_policy_session_secret_keys()
    ordered_keys = [
        (candidate_kid, key)
        for candidate_kid, key in keyring
        if not kid or candidate_kid == kid
    ] or keyring
    for _candidate_kid, key in ordered_keys:
        try:
            plaintext = AESGCM(key).decrypt(nonce, ciphertext, b"retrieval-policy-session-refresh-token")
            return plaintext.decode("utf-8").strip()
        except Exception:
            continue
    raise HTTPException(status_code=401, detail="OIDC policy session refresh_token cannot be decrypted")


def _apply_oidc_token_payload_to_session_record(record: dict[str, Any], token_payload: dict[str, Any] | None) -> None:
    if not isinstance(token_payload, dict):
        return
    refresh_token = str(token_payload.get("refresh_token") or "").strip()
    if refresh_token:
        encrypted_refresh_token = _encrypt_retrieval_policy_session_secret(refresh_token)
        if encrypted_refresh_token:
            record["refresh_token_encrypted"] = encrypted_refresh_token
            record.pop("refresh_token", None)
        else:
            record["refresh_token"] = refresh_token
            record.pop("refresh_token_encrypted", None)
    token_type = str(token_payload.get("token_type") or "").strip()
    if token_type:
        record["token_type"] = token_type
    try:
        expires_in = int(token_payload.get("expires_in") or 0)
    except (TypeError, ValueError):
        expires_in = 0
    if expires_in > 0:
        record["token_expires_at"] = int(time.time()) + expires_in


def _create_retrieval_policy_session(
    persist_dir: Path,
    identity: dict[str, Any],
    token_payload: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    ttl_seconds = max(60, int(os.getenv("RAG_POLICY_SESSION_TTL_SECONDS", "28800")))
    now = int(time.time())
    session_id = secrets.token_urlsafe(32)
    record = {
        "subject": str(identity.get("subject") or "").strip(),
        "groups": list(identity.get("groups") or []),
        "identity_source": "oidc_session",
        "created_at": now,
        "expires_at": now + ttl_seconds,
    }
    if not record["subject"]:
        raise HTTPException(status_code=401, detail="OIDC token does not contain a usable subject")
    _apply_oidc_token_payload_to_session_record(record, token_payload)
    sessions = _read_retrieval_policy_sessions(persist_dir)
    sessions[session_id] = record
    _write_retrieval_policy_sessions(persist_dir, sessions)
    return session_id, record


def _refresh_retrieval_policy_session_record(
    persist_dir: Path,
    session_id: str,
    identity: dict[str, Any],
    token_payload: dict[str, Any],
) -> dict[str, Any]:
    session_key = str(session_id or "").strip()
    if not session_key:
        raise HTTPException(status_code=401, detail="OIDC policy session cookie is required")
    sessions = _read_retrieval_policy_sessions(persist_dir)
    record = sessions.get(session_key)
    if not isinstance(record, dict):
        raise HTTPException(status_code=401, detail="OIDC policy session is invalid or expired")
    existing_subject = str(record.get("subject") or "").strip()
    subject = str(identity.get("subject") or "").strip()
    if not existing_subject or not subject or existing_subject != subject:
        raise HTTPException(status_code=401, detail="OIDC refreshed token subject does not match the policy session")
    ttl_seconds = max(60, int(os.getenv("RAG_POLICY_SESSION_TTL_SECONDS", "28800")))
    now = int(time.time())
    record["subject"] = subject
    record["groups"] = list(identity.get("groups") or [])
    record["identity_source"] = "oidc_session"
    record["refreshed_at"] = now
    record["expires_at"] = now + ttl_seconds
    _apply_oidc_token_payload_to_session_record(record, token_payload)
    sessions[session_key] = record
    _write_retrieval_policy_sessions(persist_dir, sessions)
    return record


def _resolve_retrieval_policy_session_identity(persist_dir: Path, session_id: str) -> dict[str, Any]:
    session_key = str(session_id or "").strip()
    if not session_key:
        raise HTTPException(status_code=401, detail="OIDC bearer token or policy session cookie is required")
    sessions = _read_retrieval_policy_sessions(persist_dir)
    record = sessions.get(session_key)
    if not isinstance(record, dict):
        raise HTTPException(status_code=401, detail="OIDC policy session is invalid or expired")
    if int(record.get("expires_at") or 0) <= int(time.time()):
        sessions.pop(session_key, None)
        _write_retrieval_policy_sessions(persist_dir, sessions)
        raise HTTPException(status_code=401, detail="OIDC policy session is invalid or expired")
    subject = str(record.get("subject") or "").strip()
    if not subject:
        raise HTTPException(status_code=401, detail="OIDC policy session is invalid or expired")
    groups = record.get("groups") if isinstance(record.get("groups"), list) else []
    return {
        "subject": subject,
        "groups": [str(group).strip() for group in groups if str(group).strip()],
        "identity_source": "oidc_session",
    }


def _delete_retrieval_policy_session(persist_dir: Path, session_id: str) -> None:
    session_key = str(session_id or "").strip()
    if not session_key:
        return
    sessions = _read_retrieval_policy_sessions(persist_dir)
    if session_key in sessions:
        sessions.pop(session_key, None)
        _write_retrieval_policy_sessions(persist_dir, sessions)


def _resolve_retrieval_policy_session_admin_identity(request: Request, persist_dir: Path) -> dict[str, Any]:
    identity = _resolve_retrieval_policy_oidc_identity(request, persist_dir)
    subject = str(identity.get("subject") or "").strip()
    if not subject:
        raise HTTPException(status_code=401, detail="OIDC administrator identity is required")
    policy_path = Path(persist_dir) / RETRIEVAL_POLICY_FILENAME
    try:
        payload = orjson.loads(policy_path.read_bytes()) if policy_path.exists() else {}
    except (OSError, orjson.JSONDecodeError):
        payload = {}
    role_registry = payload.get("role_registry") if isinstance(payload, dict) and isinstance(payload.get("role_registry"), dict) else {}
    role_entry = role_registry.get(subject)
    if not isinstance(role_entry, dict) or role_entry.get("active") is False:
        raise HTTPException(status_code=403, detail="retrieval policy session administration requires an active admin or owner role")
    roles = {
        str(role or "").strip().casefold()
        for role in role_entry.get("roles", [])
        if str(role or "").strip()
    }
    if not roles.intersection({"admin", "owner"}):
        raise HTTPException(status_code=403, detail="retrieval policy session administration requires an active admin or owner role")
    return {
        **identity,
        "admin_role": "owner" if "owner" in roles else "admin",
        "role_source": "role_registry",
    }


def _sanitize_retrieval_policy_session_record(session_id: str, record: dict[str, Any]) -> dict[str, Any]:
    encrypted_refresh = record.get("refresh_token_encrypted") if isinstance(record.get("refresh_token_encrypted"), dict) else None
    has_plain_refresh = bool(str(record.get("refresh_token") or "").strip())
    has_encrypted_refresh = encrypted_refresh is not None
    groups = record.get("groups") if isinstance(record.get("groups"), list) else []
    return {
        "session_id": str(session_id),
        "subject": str(record.get("subject") or "").strip(),
        "groups": [str(group).strip() for group in groups if str(group).strip()],
        "identity_source": str(record.get("identity_source") or "").strip(),
        "created_at": int(record.get("created_at") or 0),
        "refreshed_at": int(record.get("refreshed_at") or 0) or None,
        "expires_at": int(record.get("expires_at") or 0),
        "token_expires_at": int(record.get("token_expires_at") or 0) or None,
        "token_type": str(record.get("token_type") or "").strip(),
        "has_refresh_token": has_plain_refresh or has_encrypted_refresh,
        "secret_storage": "encrypted" if has_encrypted_refresh else ("plain" if has_plain_refresh else "none"),
    }


def _list_retrieval_policy_session_records(persist_dir: Path) -> tuple[list[dict[str, Any]], int]:
    now = int(time.time())
    sessions = _read_retrieval_policy_sessions(persist_dir)
    active_sessions: dict[str, Any] = {}
    expired_count = 0
    for session_id, record in sessions.items():
        if not isinstance(record, dict):
            expired_count += 1
            continue
        if int(record.get("expires_at") or 0) <= now:
            expired_count += 1
            continue
        active_sessions[str(session_id)] = record
    if expired_count:
        _write_retrieval_policy_sessions(persist_dir, active_sessions)
    sanitized = [
        _sanitize_retrieval_policy_session_record(session_id, record)
        for session_id, record in active_sessions.items()
        if isinstance(record, dict)
    ]
    sanitized.sort(key=lambda item: (int(item.get("created_at") or 0), str(item.get("session_id") or "")), reverse=True)
    return sanitized, expired_count


def _rotate_retrieval_policy_session_refresh_token_keys(persist_dir: Path) -> dict[str, Any]:
    keyring = _retrieval_policy_session_secret_keys()
    if not keyring:
        raise HTTPException(status_code=400, detail="RAG_POLICY_SESSION_SECRET_KEYS is required for OIDC session key rotation")
    active_key_id = keyring[0][0]
    now = int(time.time())
    sessions = _read_retrieval_policy_sessions(persist_dir)
    updated_sessions: dict[str, Any] = {}
    rotated_session_ids: list[str] = []
    expired_pruned_count = 0
    skipped_count = 0
    for session_id, record in sessions.items():
        if not isinstance(record, dict):
            expired_pruned_count += 1
            continue
        if int(record.get("expires_at") or 0) <= now:
            expired_pruned_count += 1
            continue
        encrypted = record.get("refresh_token_encrypted") if isinstance(record.get("refresh_token_encrypted"), dict) else None
        has_plain_refresh = bool(str(record.get("refresh_token") or "").strip())
        if not has_plain_refresh and not encrypted:
            skipped_count += 1
            updated_sessions[str(session_id)] = record
            continue
        if encrypted and str(encrypted.get("kid") or "").strip() == active_key_id and not has_plain_refresh:
            skipped_count += 1
            updated_sessions[str(session_id)] = record
            continue
        refresh_token = _decrypt_retrieval_policy_session_secret(record)
        encrypted_refresh_token = _encrypt_retrieval_policy_session_secret(refresh_token)
        if not encrypted_refresh_token:
            raise HTTPException(status_code=400, detail="RAG_POLICY_SESSION_SECRET_KEYS is required for OIDC session key rotation")
        record["refresh_token_encrypted"] = encrypted_refresh_token
        record.pop("refresh_token", None)
        updated_sessions[str(session_id)] = record
        rotated_session_ids.append(str(session_id))
    if rotated_session_ids or expired_pruned_count:
        _write_retrieval_policy_sessions(persist_dir, updated_sessions)
    return {
        "active_key_id": active_key_id,
        "rotated_count": len(rotated_session_ids),
        "rotated_session_ids": rotated_session_ids,
        "skipped_count": skipped_count,
        "expired_pruned_count": expired_pruned_count,
        "session_count": len(updated_sessions),
    }


def _retrieval_policy_session_key_source() -> str:
    if str(os.getenv("RAG_POLICY_SESSION_SECRET_KEYS") or "").strip():
        return "RAG_POLICY_SESSION_SECRET_KEYS"
    if str(os.getenv("RAG_POLICY_SESSION_SECRET_KEY") or "").strip():
        return "RAG_POLICY_SESSION_SECRET_KEY"
    return "none"


def _latest_retrieval_policy_session_key_rotation_audit(persist_dir: Path) -> dict[str, Any] | None:
    policy_path = Path(persist_dir) / RETRIEVAL_POLICY_FILENAME
    try:
        payload = orjson.loads(policy_path.read_bytes()) if policy_path.exists() else {}
    except (OSError, orjson.JSONDecodeError):
        payload = {}
    audit = payload.get("audit") if isinstance(payload, dict) and isinstance(payload.get("audit"), list) else []
    for item in reversed(audit):
        if not isinstance(item, dict) or item.get("action") != "identity_provider_session_key_rotate":
            continue
        return {
            "timestamp": str(item.get("timestamp") or "").strip(),
            "admin": str(item.get("admin") or "").strip(),
            "active_key_id": str(item.get("active_key_id") or "").strip(),
            "rotated_count": int(item.get("rotated_count") or 0),
        }
    return None


def _retrieval_policy_session_key_rotation_age_seconds(rotation: dict[str, Any] | None) -> int | None:
    timestamp = str((rotation or {}).get("timestamp") or "").strip()
    if not timestamp:
        return None
    try:
        rotated_at = datetime.fromisoformat(timestamp)
    except ValueError:
        return None
    return max(0, int((datetime.now() - rotated_at).total_seconds()))


def _summarize_retrieval_policy_session_key_status(persist_dir: Path) -> dict[str, Any]:
    keyring = _retrieval_policy_session_secret_keys()
    key_ids = [kid for kid, _key in keyring]
    active_key_id = key_ids[0] if key_ids else ""
    known_key_ids = set(key_ids)
    now = int(time.time())
    sessions = _read_retrieval_policy_sessions(persist_dir)
    active_sessions: dict[str, Any] = {}
    expired_pruned_count = 0
    active_encrypted_session_count = 0
    stale_encrypted_session_count = 0
    unknown_key_session_count = 0
    plain_refresh_session_count = 0
    missing_refresh_session_count = 0

    for session_id, record in sessions.items():
        if not isinstance(record, dict):
            expired_pruned_count += 1
            continue
        if int(record.get("expires_at") or 0) <= now:
            expired_pruned_count += 1
            continue
        active_sessions[str(session_id)] = record
        encrypted = record.get("refresh_token_encrypted") if isinstance(record.get("refresh_token_encrypted"), dict) else None
        has_plain_refresh = bool(str(record.get("refresh_token") or "").strip())
        if encrypted:
            kid = str(encrypted.get("kid") or "").strip()
            if kid == active_key_id and active_key_id:
                active_encrypted_session_count += 1
            else:
                stale_encrypted_session_count += 1
                if kid and kid not in known_key_ids:
                    unknown_key_session_count += 1
        elif has_plain_refresh:
            plain_refresh_session_count += 1
        else:
            missing_refresh_session_count += 1

    if expired_pruned_count:
        _write_retrieval_policy_sessions(persist_dir, active_sessions)

    last_rotation = _latest_retrieval_policy_session_key_rotation_audit(persist_dir)
    rotation_age_seconds = _retrieval_policy_session_key_rotation_age_seconds(last_rotation)
    try:
        max_age_seconds = int(os.getenv("RAG_POLICY_SESSION_KEY_MAX_AGE_SECONDS", "0") or 0)
    except ValueError:
        max_age_seconds = 0
    rotation_due_reasons: list[str] = []
    if max_age_seconds > 0 and (rotation_age_seconds is None or rotation_age_seconds > max_age_seconds):
        rotation_due_reasons.append("last_rotation_exceeded_max_age")
    if stale_encrypted_session_count or plain_refresh_session_count:
        rotation_due_reasons.append("stale_or_plain_sessions")
    if not keyring:
        rotation_due_reasons.append("keyring_missing")

    return {
        "key_source": _retrieval_policy_session_key_source(),
        "active_key_id": active_key_id,
        "key_count": len(key_ids),
        "old_key_count": max(0, len(key_ids) - 1),
        "key_ids": key_ids,
        "session_count": len(active_sessions),
        "encrypted_session_count": active_encrypted_session_count + stale_encrypted_session_count,
        "active_encrypted_session_count": active_encrypted_session_count,
        "stale_encrypted_session_count": stale_encrypted_session_count,
        "unknown_key_session_count": unknown_key_session_count,
        "plain_refresh_session_count": plain_refresh_session_count,
        "missing_refresh_session_count": missing_refresh_session_count,
        "expired_pruned_count": expired_pruned_count,
        "last_rotation": last_rotation,
        "rotation_age_seconds": rotation_age_seconds,
        "rotation_max_age_seconds": max_age_seconds,
        "rotation_due": bool(rotation_due_reasons),
        "rotation_due_reasons": rotation_due_reasons,
    }


def _retrieval_policy_oidc_state_path(persist_dir: Path) -> Path:
    return Path(persist_dir) / RETRIEVAL_POLICY_OIDC_STATE_FILENAME


def _read_retrieval_policy_oidc_states(persist_dir: Path) -> dict[str, Any]:
    state_path = _retrieval_policy_oidc_state_path(persist_dir)
    try:
        payload = orjson.loads(state_path.read_bytes()) if state_path.exists() else {}
    except (OSError, orjson.JSONDecodeError):
        payload = {}
    return payload if isinstance(payload, dict) else {}


def _write_retrieval_policy_oidc_states(persist_dir: Path, states: dict[str, Any]) -> None:
    state_path = _retrieval_policy_oidc_state_path(persist_dir)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_bytes(orjson.dumps(states, option=orjson.OPT_INDENT_2))


def _store_retrieval_policy_oidc_state(
    persist_dir: Path,
    *,
    state: str,
    nonce: str,
    code_verifier: str,
    redirect_uri: str,
) -> dict[str, Any]:
    ttl_seconds = max(60, int(os.getenv("RAG_POLICY_OIDC_STATE_TTL_SECONDS", "600")))
    now = int(time.time())
    record = {
        "state": state,
        "nonce": nonce,
        "code_verifier": code_verifier,
        "redirect_uri": redirect_uri,
        "created_at": now,
        "expires_at": now + ttl_seconds,
    }
    states = {
        key: value
        for key, value in _read_retrieval_policy_oidc_states(persist_dir).items()
        if isinstance(value, dict) and int(value.get("expires_at") or 0) > now
    }
    states[state] = record
    _write_retrieval_policy_oidc_states(persist_dir, states)
    return record


def _consume_retrieval_policy_oidc_state(persist_dir: Path, state: str) -> dict[str, Any]:
    state_key = str(state or "").strip()
    if not state_key:
        raise HTTPException(status_code=400, detail="OIDC callback state is required")
    states = _read_retrieval_policy_oidc_states(persist_dir)
    record = states.pop(state_key, None)
    _write_retrieval_policy_oidc_states(persist_dir, states)
    if not isinstance(record, dict):
        raise HTTPException(status_code=400, detail="OIDC callback state is invalid or expired")
    if int(record.get("expires_at") or 0) <= int(time.time()):
        raise HTTPException(status_code=400, detail="OIDC callback state is invalid or expired")
    return record


def _resolve_retrieval_policy_oidc_identity(request: Request, persist_dir: Path) -> dict[str, Any]:
    oidc_config = _retrieval_policy_oidc_config(persist_dir)
    if not oidc_config:
        return {}

    authorization = str(request.headers.get("authorization") or "").strip()
    if authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        if not token:
            raise HTTPException(status_code=401, detail="OIDC bearer token is required")
        return _decode_retrieval_policy_oidc_token(token, oidc_config)

    session_id = str(request.cookies.get(RETRIEVAL_POLICY_SESSION_COOKIE) or "").strip()
    if session_id:
        return _resolve_retrieval_policy_session_identity(persist_dir, session_id)

    raise HTTPException(status_code=401, detail="OIDC bearer token or policy session cookie is required")


def _base64url_no_padding(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _new_pkce_verifier() -> str:
    return _base64url_no_padding(secrets.token_bytes(48))


def _pkce_challenge(verifier: str) -> str:
    return _base64url_no_padding(hashlib.sha256(verifier.encode("ascii")).digest())


def _retrieval_policy_oidc_login_config(persist_dir: Path) -> dict[str, Any]:
    config = _persisted_retrieval_policy_oidc_config(persist_dir)
    if not isinstance(config, dict) or config.get("enabled") is not True:
        raise HTTPException(status_code=400, detail="managed OIDC identity provider is not enabled")
    if not str(config.get("authorization_endpoint") or "").strip():
        raise HTTPException(status_code=400, detail="OIDC authorization_endpoint is not configured")
    if not str(config.get("token_endpoint") or "").strip():
        raise HTTPException(status_code=400, detail="OIDC token_endpoint is not configured")
    if not str(config.get("client_id") or "").strip():
        raise HTTPException(status_code=400, detail="OIDC client_id is not configured")
    return config


def _resolve_oidc_redirect_uri(config: dict[str, Any], requested_redirect_uri: str = "") -> str:
    configured_redirect_uri = str(config.get("redirect_uri") or "").strip()
    redirect_uri = str(requested_redirect_uri or "").strip() or configured_redirect_uri
    if not redirect_uri:
        raise HTTPException(status_code=400, detail="OIDC redirect_uri is required")
    if configured_redirect_uri and redirect_uri != configured_redirect_uri:
        raise HTTPException(status_code=400, detail="OIDC redirect_uri does not match the configured redirect_uri")
    parsed = urlparse(redirect_uri)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=400, detail="OIDC redirect_uri must be an absolute http or https URL")
    return redirect_uri


def _request_oidc_token(config: dict[str, Any], form_data: dict[str, str]) -> dict[str, Any]:
    token_endpoint = str(config.get("token_endpoint") or "").strip()
    client_id = str(config.get("client_id") or "").strip()
    if not token_endpoint or not client_id:
        raise HTTPException(status_code=400, detail="OIDC token_endpoint and client_id are required")
    request_form_data = {
        key: str(value or "").strip()
        for key, value in form_data.items()
        if str(value or "").strip()
    }
    request_form_data["client_id"] = client_id
    client_secret_env = str(config.get("client_secret_env") or "").strip()
    if client_secret_env:
        client_secret = os.getenv(client_secret_env, "").strip()
        if client_secret:
            request_form_data["client_secret"] = client_secret
    encoded = urlencode(request_form_data).encode("utf-8")
    request = UrlRequest(
        token_endpoint,
        data=encoded,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=15) as response:
            body = response.read()
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise HTTPException(status_code=502, detail=f"OIDC token endpoint returned {exc.code}: {detail}") from exc
    except URLError as exc:
        raise HTTPException(status_code=502, detail=f"OIDC token endpoint request failed: {exc}") from exc
    try:
        payload = orjson.loads(body)
    except orjson.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail="OIDC token endpoint did not return JSON") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=502, detail="OIDC token endpoint returned an invalid payload")
    return payload


def _exchange_oidc_authorization_code(config: dict[str, Any], *, code: str, code_verifier: str, redirect_uri: str) -> dict[str, Any]:
    form_data = {
        "grant_type": "authorization_code",
        "code": str(code or "").strip(),
        "redirect_uri": redirect_uri,
        "code_verifier": str(code_verifier or "").strip(),
    }
    if not form_data["code"]:
        raise HTTPException(status_code=400, detail="OIDC authorization code is required")
    if not form_data["code_verifier"]:
        raise HTTPException(status_code=400, detail="OIDC code_verifier is required")
    return _request_oidc_token(config, form_data)


def _exchange_oidc_refresh_token(config: dict[str, Any], *, refresh_token: str) -> dict[str, Any]:
    token = str(refresh_token or "").strip()
    if not token:
        raise HTTPException(status_code=400, detail="OIDC policy session does not have a refresh_token")
    return _request_oidc_token(
        config,
        {
            "grant_type": "refresh_token",
            "refresh_token": token,
        },
    )
CONSOLE_FRONTEND_DIR = Path(__file__).resolve().parents[3] / "frontend"
REPO_FRONTEND_DIR = REPO_ROOT / "frontend_app" / "current_console"
FRONTEND_DIR_CANDIDATES = (REPO_FRONTEND_DIR, CONSOLE_FRONTEND_DIR, PACKAGE_FRONTEND_DIR)
PUBLIC_BOOKS_JSON_ROOT = REPO_ROOT / "data_pipeline"
DEFAULT_DELIVERABLES_DIR = REPO_ROOT / "docs" / "project_deliverables"
DEFAULT_CORS_ORIGINS = (
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
)
SUPPORTED_EXTENSIONS_LABEL = ", ".join(supported_source_extensions())
UPLOAD_MANIFEST_NAME = ".upload-manifest.json"
WINDOWS_INVALID_UPLOAD_CHARS = set('<>:"/\\|?*')
DEFAULT_LOG_DIR = DEFAULT_UPLOAD_DIR.parent / "logs"
LOG_FILENAME_PATTERN = re.compile(r"^[0-9A-Za-z._-]+\.log$")


def _resolve_frontend_dir(candidates: tuple[Path, ...] = FRONTEND_DIR_CANDIDATES) -> Path | None:
    try:
        for path in candidates:
            if path.exists():
                return path
    except (StopIteration, OSError):
        pass
    return None


def _configured_cors_origins() -> list[str]:
    raw_origins = os.getenv("POWER_RAG_CORS_ORIGINS", "")
    if not raw_origins.strip():
        return list(DEFAULT_CORS_ORIGINS)

    origins: list[str] = []
    for raw_origin in raw_origins.split(","):
        origin = raw_origin.strip().rstrip("/")
        parsed = urlparse(origin)
        if parsed.scheme in {"http", "https"} and parsed.netloc and origin != "*":
            origins.append(origin)
    return origins or list(DEFAULT_CORS_ORIGINS)


def _safe_upload_name(raw_name: str) -> str:
    clean = normalize_upload_name(raw_name)
    return clean[:220] if len(clean) > 220 else clean


def _sanitize_upload_part(part: str) -> str:
    cleaned = "".join(
        "_" if char in WINDOWS_INVALID_UPLOAD_CHARS or ord(char) < 32 else char
        for char in str(part)
    )
    cleaned = cleaned.strip().strip(".")
    return cleaned or "item"


def normalize_upload_name(raw_name: str) -> str:
    raw = str(raw_name or "").replace("\x00", "")
    parts = [
        _sanitize_upload_part(part.strip())
        for part in Path(raw).parts
        if part not in {"", ".", ".."}
    ]
    if not parts:
        return f"upload-{int(time.time())}.bin"
    return "__".join(parts)


def _manifest_path(upload_dir: Path) -> Path:
    return Path(upload_dir) / UPLOAD_MANIFEST_NAME


def _read_upload_manifest(upload_dir: Path) -> dict[str, dict]:
    manifest_path = _manifest_path(upload_dir)
    if not manifest_path.exists():
        return {}
    try:
        payload = orjson.loads(manifest_path.read_bytes())
    except Exception:
        return {}

    if isinstance(payload, dict):
        files = payload.get("files", payload)
        if isinstance(files, dict):
            return {
                str(filename): entry
                for filename, entry in files.items()
                if isinstance(filename, str) and isinstance(entry, dict)
            }
    return {}


def _write_upload_manifest(upload_dir: Path, entries: dict[str, dict]) -> None:
    manifest_path = _manifest_path(upload_dir)
    manifest_path.write_bytes(
        orjson.dumps(
            {"files": entries},
            option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS,
        )
    )


def _supported_upload_paths(upload_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in Path(upload_dir).iterdir()
        if path.is_file() and path.name != UPLOAD_MANIFEST_NAME and is_supported_source(path.name)
    )


def _guess_display_name(filename: str) -> str:
    return filename.replace("__", "/")


def _collect_upload_entries(upload_dir: Path) -> list[dict]:
    upload_dir = Path(upload_dir)
    manifest = _read_upload_manifest(upload_dir)
    synced: dict[str, dict] = {}

    for file_path in _supported_upload_paths(upload_dir):
        stat = file_path.stat()
        existing = manifest.get(file_path.name, {})
        status = str(existing.get("status") or "uploaded")
        if status not in {"uploaded", "processed"}:
            status = "uploaded"

        entry = {
            "filename": file_path.name,
            "display_name": str(existing.get("display_name") or _guess_display_name(file_path.name)),
            "size_kb": round(stat.st_size / 1024, 1),
            "modified": stat.st_mtime,
            "uploaded_at": float(existing.get("uploaded_at") or stat.st_mtime),
            "processed_at": existing.get("processed_at"),
            "status": status,
            "source_kind": str(existing.get("source_kind") or get_source_kind(file_path.name)),
            "last_collection": existing.get("last_collection"),
            "last_records": int(existing.get("last_records") or 0),
            "last_chunks": int(existing.get("last_chunks") or 0),
            "last_error": existing.get("last_error"),
            "last_log_file": existing.get("last_log_file"),
        }
        synced[file_path.name] = entry

    _write_upload_manifest(upload_dir, synced)

    return sorted(
        synced.values(),
        key=lambda item: (
            0 if item.get("status") != "processed" else 1,
            str(item.get("display_name") or item.get("filename") or "").lower(),
        ),
    )


def _update_upload_entry(upload_dir: Path, filename: str, **updates) -> dict:
    upload_dir = Path(upload_dir)
    manifest = _read_upload_manifest(upload_dir)
    current = dict(manifest.get(filename, {}))
    current.update({key: value for key, value in updates.items() if value is not None})
    manifest[filename] = current
    _write_upload_manifest(upload_dir, manifest)
    return current


def _remove_upload_entries(upload_dir: Path, filenames: list[str]) -> None:
    upload_dir = Path(upload_dir)
    manifest = _read_upload_manifest(upload_dir)
    for filename in filenames:
        manifest.pop(filename, None)
    _write_upload_manifest(upload_dir, manifest)


def _mark_process_result(
    upload_dir: Path,
    result: dict,
    collection_name: str,
    log_file: str | None = None,
) -> None:
    upload_dir = Path(upload_dir)
    manifest = _read_upload_manifest(upload_dir)
    now = time.time()

    for item in result.get("file_summaries", []):
        filename = str(item.get("source_file") or "").strip()
        if not filename:
            continue
        current = dict(manifest.get(filename, {}))
        current["status"] = "processed" if item.get("status") == "ok" else "uploaded"
        current["processed_at"] = now if item.get("status") == "ok" else current.get("processed_at")
        current["last_collection"] = collection_name
        current["last_records"] = int(item.get("records_extracted") or 0)
        current["last_chunks"] = int(result.get("chunks_written") or 0) if item.get("status") == "ok" else 0
        current["last_error"] = None if item.get("status") == "ok" else item.get("error")
        current["last_log_file"] = log_file or current.get("last_log_file")
        manifest[filename] = current

    _write_upload_manifest(upload_dir, manifest)


def _operation_log_payload(logger: OperationLogger) -> dict[str, str]:
    return {"log_file": logger.file_name}


def _graph_triage_store(request: Request) -> GraphRagTriageStore:
    return GraphRagTriageStore(Path(request.app.state.persist_dir) / "graphrag_triage.jsonl")


def _source_evidence_count(citations: list[dict] | None) -> int:
    if not citations:
        return 0
    return sum(1 for item in citations if item.get("source_type") == "graph_community_source")


def _build_lightrag_diagnostics(
    *,
    question: str,
    route: dict,
    top_k: int,
    citations: list[dict] | None,
    global_error: str | None = None,
) -> dict:
    source_counts: dict[str, int] = {}
    for item in citations or []:
        source_type = str(item.get("source_type") or "unknown")
        source_counts[source_type] = source_counts.get(source_type, 0) + 1

    naive_count = source_counts.get("text", 0)
    local_count = source_counts.get("graph", 0)
    global_count = source_counts.get("graph_community_source", 0)
    active_paths = tuple(
        path
        for path, count in (
            ("naive", naive_count),
            ("local", local_count),
            ("global", global_count),
        )
        if count > 0
    )
    diagnostics = LightRagDiagnostics(
        question=question,
        mode=_derive_lightrag_mode(active_paths, str(route.get("strategy") or "")),
        top_k=top_k,
        route_strategy=str(route.get("strategy") or ""),
        naive_count=naive_count,
        local_count=local_count,
        global_count=global_count,
        final_count=len(citations or []),
        fusion_mode="graph_rag_route",
        active_paths=active_paths,
        source_type_counts=source_counts,
        global_error=global_error,
    )
    return diagnostics.to_dict()


def _citation_preview(text: object, *, limit: int = 220) -> str:
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: max(0, limit - 1)].rstrip() + "..."


def _build_text_citations_from_results(results: list[dict], *, source_type: str = "text") -> list[dict]:
    citations: list[dict] = []
    for index, item in enumerate(results, start=1):
        metadata = dict(item.get("metadata") or {}) if isinstance(item, dict) else {}
        text = str(item.get("text") or item.get("document") or "") if isinstance(item, dict) else ""
        source = (
            item.get("source")
            or metadata.get("source_file")
            or metadata.get("source")
            or metadata.get("filename")
            or metadata.get("file")
            if isinstance(item, dict)
            else None
        )
        citations.append(
            {
                "id": f"T{index}",
                "source_type": source_type,
                "rank": index,
                "text": text,
                "source": source,
                "score": item.get("score") if isinstance(item, dict) else None,
                "metadata": metadata,
                "raw_id": item.get("id") if isinstance(item, dict) else None,
            }
        )
    return citations


def _build_text_retrieval_fallback_response(
    *,
    question: str,
    text_retriever: "_QueryCollectionTextRetriever",
    top_k: int,
    reason: str,
) -> dict[str, Any]:
    retrieval_error = None
    try:
        results = text_retriever.retrieve(question, top_k=top_k)
    except Exception as exc:
        results = []
        retrieval_error = str(exc)

    citations = _build_text_citations_from_results(list(results or []), source_type="text")
    lines = [
        f"Result: {reason}",
        "",
    ]
    if citations:
        lines.append(f"Text retrieval result: found {len(citations)} evidence item(s).")
        lines.append("")
        lines.append("Key evidence:")
        for citation in citations[: min(5, len(citations))]:
            source = citation.get("source") or "unknown source"
            lines.append(f"- [{citation['id']}] {source}: {_citation_preview(citation.get('text'))}")
    else:
        lines.append("Text retrieval result: no usable evidence was returned for this input.")
        lines.append("Conclusion: there is not enough source evidence to answer reliably from the current collection.")
    if retrieval_error:
        lines.extend(["", f"Text retrieval warning: {retrieval_error}"])

    context = "\n\n".join(
        [
            "## Text retrieval evidence",
            "\n\n".join(
                f"[{item['id']}] {item.get('source') or 'unknown source'}\n{item.get('text') or ''}"
                for item in citations
            )
            or "No text retrieval evidence returned.",
        ]
    )
    return {
        "question": question,
        "answer": "\n".join(lines),
        "context": context,
        "citations": citations,
        "evidence": citations,
        "context_only": False,
        "prompt": None,
        "text_fallback": True,
        "text_fallback_reason": reason,
    }


def _build_graph_quality_fallback_response(
    *,
    question: str,
    text_retriever: "_QueryCollectionTextRetriever",
    top_k: int,
    graph_quality: dict | None,
    gate_message: str,
) -> dict[str, Any]:
    retrieval_error = None
    try:
        results = text_retriever.retrieve(question, top_k=top_k)
    except Exception as exc:
        results = []
        retrieval_error = str(exc)

    citations = _build_text_citations_from_results(list(results or []), source_type="text")
    failures = [
        str(item.get("metric") or "")
        for item in ((graph_quality or {}).get("quality_gate") or {}).get("failures", [])
        if str(item.get("metric") or "").strip()
    ]
    lines = [
        "Result: the graph was not used for this answer because its evidence quality check failed. I switched to text retrieval so the response still gives a concrete result.",
        "",
    ]
    if citations:
        lines.append(f"Text retrieval result: found {len(citations)} evidence item(s).")
        lines.append("")
        lines.append("Key evidence:")
        for citation in citations[: min(5, len(citations))]:
            source = citation.get("source") or "unknown source"
            lines.append(f"- [{citation['id']}] {source}: {_citation_preview(citation.get('text'))}")
    else:
        lines.append("Text retrieval result: no usable text evidence was returned for this question.")
        lines.append("Conclusion: there is not enough source evidence to answer the question reliably from the current collection.")
    if failures:
        lines.extend(["", f"Graph check summary: blocked because {', '.join(failures[:5])}."])
    if retrieval_error:
        lines.extend(["", f"Text retrieval warning: {retrieval_error}"])

    context_parts = [
        "## Text retrieval evidence",
        "\n\n".join(
            f"[{item['id']}] {item.get('source') or 'unknown source'}\n{item.get('text') or ''}"
            for item in citations
        )
        or "No text retrieval evidence returned.",
        "## Graph quality gate",
        gate_message,
    ]
    return {
        "question": question,
        "answer": "\n".join(lines),
        "context": "\n\n".join(context_parts),
        "citations": citations,
        "evidence": citations,
        "context_only": False,
        "prompt": None,
        "graph_quality_blocked": True,
        "graph_quality_blocked_reason": gate_message,
    }


def _build_resilient_query_failure_response(
    *,
    question: str,
    persist_dir: Path,
    collection_name: str | None,
    top_k: int,
    error: Exception,
) -> dict[str, Any]:
    citations: list[dict] = []
    retrieval_error: str | None = None
    if collection_name:
        try:
            fallback_retriever = _QueryCollectionTextRetriever(
                persist_dir=persist_dir,
                collection_name=collection_name,
            )
            results = fallback_retriever.retrieve(question, top_k=max(1, min(top_k, 8)))
            citations = _build_text_citations_from_results(list(results or []), source_type="text_resilient_fallback")
        except Exception as exc:  # noqa: BLE001
            retrieval_error = str(exc)

    lines = [
        "Result: primary query execution failed, so the system returned a resilient fallback instead of freezing.",
        f"- Failed path error: {type(error).__name__}: {error}",
        f"- Collection: {collection_name or 'not resolved'}",
        "",
    ]
    if citations:
        lines.append(f"Fallback text retrieval found {len(citations)} evidence item(s):")
        for citation in citations[:5]:
            lines.append(
                "- [{id}] {source}: {text}".format(
                    id=citation["id"],
                    source=citation.get("source") or "unknown source",
                    text=_citation_preview(citation.get("text")),
                )
            )
        lines.extend(
            [
                "",
                "Conclusion: the answer above is the closest available evidence-backed response from text retrieval. The original route should be inspected, but the query did not hard-fail.",
            ]
        )
    else:
        lines.extend(
            [
                "Fallback text retrieval did not return usable evidence.",
                "Conclusion: there is not enough source evidence to answer reliably from the current collection, but the query completed with a diagnostic answer.",
            ]
        )
    if retrieval_error:
        lines.extend(["", f"Fallback retrieval warning: {retrieval_error}"])

    context = "\n\n".join(
        [
            "## Resilient query fallback",
            f"Primary error: {type(error).__name__}: {error}",
            "## Fallback text retrieval evidence",
            "\n\n".join(
                f"[{item['id']}] {item.get('source') or 'unknown source'}\n{item.get('text') or ''}"
                for item in citations
            )
            or "No fallback text retrieval evidence returned.",
        ]
    )
    return {
        "question": question,
        "answer": "\n".join(lines),
        "context": context,
        "citations": citations,
        "evidence": citations,
        "context_only": False,
        "prompt": None,
        "resilient_fallback": True,
        "query_error": {
            "type": type(error).__name__,
            "message": str(error),
        },
        "fallback_retrieval_error": retrieval_error,
    }


_UNIVERSAL_ASSURANCE_SCAN_LIMIT = 5000
_UNIVERSAL_ASSURANCE_MAX_CITATIONS = 12
_LOW_QUALITY_ANSWER_MARKERS = (
    "no text retrieval evidence returned",
    "no graph retrieval evidence returned",
    "no usable evidence",
    "no usable text evidence",
    "not enough source evidence",
    "insufficient evidence",
    "无法获取任何聊天记录",
    "没有提供任何文本检索证据",
    "没有提供任何图检索证据",
    "证据不足",
)
_UNIVERSAL_CHINESE_QUERY_STOP_TERMS = (
    "聊天记录",
    "有没有",
    "是否有",
    "里面",
    "这里",
    "这个",
    "那个",
    "相关",
    "信息",
    "内容",
    "问题",
    "帮我",
    "请问",
    "分析",
    "一下",
    "哪些",
    "什么",
)


def _assess_unified_query_answer_quality(response: dict[str, Any], question: str) -> dict[str, Any]:
    answer = str(response.get("answer") or "").strip()
    citations = response.get("citations") or []
    context = str(response.get("context") or "")
    has_citations = bool(citations)
    if response.get("context_only"):
        return {"status": "ok", "reason": "context_only_response", "citation_count": len(citations)}
    if response.get("coverage_report") and response.get("advanced_mode") == QueryRouteName.COMPREHENSIVE_ANALYSIS.value:
        return {"status": "ok", "reason": "deterministic_comprehensive_response", "citation_count": len(citations)}
    if response.get("graph_quality_blocked"):
        return {"status": "ok", "reason": "graph_quality_blocked_fallback_response", "citation_count": len(citations)}
    if response.get("resilient_fallback") and answer:
        return {"status": "ok", "reason": "resilient_fallback_response", "citation_count": len(citations)}

    folded_answer = answer.casefold()
    folded_context = context.casefold()
    low_quality_markers = [
        marker
        for marker in _LOW_QUALITY_ANSWER_MARKERS
        if marker.casefold() in folded_answer or marker.casefold() in folded_context
    ]
    reasons: list[str] = []
    if not answer:
        reasons.append("empty_answer")
    if not has_citations:
        reasons.append("no_citations")
    if low_quality_markers:
        reasons.append("low_quality_marker:" + ",".join(low_quality_markers[:3]))
    if not has_citations and len(answer) < 80:
        reasons.append("short_uncited_answer")
    source_types = {str(item.get("source_type") or "") for item in citations if isinstance(item, dict)}
    has_graph_citations = any("graph" in source_type for source_type in source_types)
    if has_citations and not has_graph_citations and not _citations_cover_universal_query_terms(citations, question):
        reasons.append("no_query_term_overlap")

    if reasons and (not has_citations or "empty_answer" in reasons or "no_query_term_overlap" in reasons):
        return {
            "status": "needs_fallback",
            "reason": "; ".join(reasons),
            "citation_count": len(citations),
        }
    return {"status": "ok", "reason": "primary_answer_has_traceable_evidence", "citation_count": len(citations)}


def _universal_query_terms(question: str) -> list[str]:
    terms = _extract_generic_query_terms(question)
    raw_question = str(question or "")
    for sequence in re.findall(r"[\u4e00-\u9fff]{2,}", raw_question):
        reduced = sequence
        for stop_term in _UNIVERSAL_CHINESE_QUERY_STOP_TERMS:
            reduced = reduced.replace(stop_term, " ")
        for piece in re.findall(r"[\u4e00-\u9fff]{2,}", reduced):
            if piece not in terms:
                terms.append(piece)
            if len(piece) > 4:
                for index in range(0, len(piece) - 1):
                    bigram = piece[index : index + 2]
                    if bigram not in terms and bigram not in _UNIVERSAL_CHINESE_QUERY_STOP_TERMS:
                        terms.append(bigram)
    text = _compact_query_text(question)
    for term in (*_PRIVATE_CONTACT_AFFECTION_TERMS, *_PRIVATE_CONTACT_EVENT_TERMS):
        if term in text and term not in terms:
            terms.append(term)
    return terms[:24]


def _citations_cover_universal_query_terms(citations: list[dict], question: str) -> bool:
    terms = _universal_query_terms(question)
    if not terms:
        return True
    haystack = "\n".join(str(item.get("text") or "") for item in citations[:20]).casefold()
    if not haystack.strip():
        return False
    return any(str(term or "").casefold() in haystack for term in terms)


def _universal_line_score(line: str, terms: list[str]) -> int:
    folded = str(line or "").casefold()
    score = 0
    for term in terms:
        normalized = str(term or "").casefold().strip()
        if normalized and normalized in folded:
            score += 10 + min(len(normalized), 8)
    return score


def _scan_universal_keyword_evidence(
    *,
    text_retriever: "_QueryCollectionTextRetriever",
    question: str,
    existing_count: int,
) -> list[dict[str, Any]]:
    terms = _universal_query_terms(question)
    if not terms:
        return []
    try:
        items = text_retriever.scan_all(limit=_UNIVERSAL_ASSURANCE_SCAN_LIMIT)
    except Exception:
        return []

    scored_rows: list[tuple[int, int, dict[str, Any]]] = []
    for raw_index, item in enumerate(items, start=1):
        metadata = dict(item.get("metadata") or {}) if isinstance(item, dict) else {}
        text = str(item.get("text") or "")
        source = (
            item.get("source")
            or metadata.get("source_file")
            or metadata.get("source")
            or metadata.get("filename")
            or metadata.get("file")
        )
        chunk_id = str(item.get("id") or metadata.get("chunk_id") or raw_index)
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines and text.strip():
            lines = [text.strip()]
        for line_index, line in enumerate(lines[:80], start=1):
            score = _universal_line_score(line, terms)
            if score <= 0:
                continue
            scored_rows.append(
                (
                    score,
                    -raw_index,
                    {
                        "text": line,
                        "source": source,
                        "score": float(score),
                        "metadata": {
                            **metadata,
                            "chunk_id": chunk_id,
                            "line_index": line_index,
                            "hit_terms": [term for term in terms if str(term).casefold() in line.casefold()],
                            "retrieval_path": "universal_keyword_scan",
                        },
                        "raw_id": f"{chunk_id}#line-{line_index}",
                    },
                )
            )
    scored_rows.sort(key=lambda row: (-row[0], row[1]))
    citations: list[dict[str, Any]] = []
    seen_texts: set[str] = set()
    for _score, _order, row in scored_rows:
        text = str(row.get("text") or "").strip()
        if not text or text in seen_texts:
            continue
        seen_texts.add(text)
        rank = existing_count + len(citations) + 1
        citations.append(
            {
                "id": f"T{rank}",
                "source_type": "text_universal_keyword_scan",
                "rank": rank,
                "text": text,
                "source": row.get("source"),
                "score": row.get("score"),
                "metadata": row.get("metadata") or {},
                "raw_id": row.get("raw_id"),
            }
        )
        if len(citations) >= _UNIVERSAL_ASSURANCE_MAX_CITATIONS:
            break
    return citations


def _collect_universal_fallback_citations(
    *,
    text_retriever: "_QueryCollectionTextRetriever",
    question: str,
    top_k: int,
) -> list[dict[str, Any]]:
    citations: list[dict[str, Any]] = []
    citations.extend(
        _scan_universal_keyword_evidence(
            text_retriever=text_retriever,
            question=question,
            existing_count=0,
        )
    )
    try:
        vector_results = text_retriever.retrieve(question, top_k=max(1, min(max(top_k, 8), 20)))
        vector_citations = _build_text_citations_from_results(list(vector_results or []), source_type="text_universal_vector")
    except Exception:
        vector_citations = []

    seen_texts = {str(item.get("text") or "").strip() for item in citations if str(item.get("text") or "").strip()}
    for item in vector_citations:
        text = str(item.get("text") or "").strip()
        if text and text not in seen_texts:
            seen_texts.add(text)
            citations.append(item)
        if len(citations) >= _UNIVERSAL_ASSURANCE_MAX_CITATIONS:
            break

    for index, item in enumerate(citations[:_UNIVERSAL_ASSURANCE_MAX_CITATIONS], start=1):
        item["id"] = f"T{index}"
        item["rank"] = index
    return citations[:_UNIVERSAL_ASSURANCE_MAX_CITATIONS]


def _build_universal_query_fallback_response(
    *,
    question: str,
    text_retriever: "_QueryCollectionTextRetriever",
    collection_name: str,
    top_k: int,
    primary_response: dict[str, Any],
    quality: dict[str, Any],
) -> dict[str, Any]:
    citations = _collect_universal_fallback_citations(
        text_retriever=text_retriever,
        question=question,
        top_k=top_k,
    )
    lines = [
        "Result: the primary RAG route did not produce an evidence-backed answer, so I used the universal fallback path.",
        f"- Primary quality issue: {quality.get('reason') or 'unknown'}",
        f"- Collection: {collection_name}",
        "",
    ]
    if citations:
        lines.append("Closest evidence-backed answer:")
        for citation in citations[:6]:
            lines.append(
                "- [{id}] {source}: {text}".format(
                    id=citation["id"],
                    source=citation.get("source") or "unknown source",
                    text=_citation_preview(citation.get("text")),
                )
            )
        lines.extend(
            [
                "",
                "Conclusion: this is the closest supported answer from the current collection. If these evidence items do not answer the question, the correct response is that the collection lacks enough source evidence.",
            ]
        )
    else:
        lines.extend(
            [
                "No vector or keyword evidence matched this question.",
                "Conclusion: the current collection does not contain enough source evidence to answer this question reliably.",
            ]
        )

    context = "\n\n".join(
        [
            "## Universal answer fallback",
            f"Primary quality issue: {quality.get('reason') or 'unknown'}",
            "## Fallback evidence",
            "\n\n".join(
                f"[{item['id']}] {item.get('source') or 'unknown source'}\n{item.get('text') or ''}"
                for item in citations
            )
            or "No fallback evidence returned.",
            "## Primary answer preview",
            _citation_preview(primary_response.get("answer"), limit=800),
        ]
    )
    return {
        "question": question,
        "answer": "\n".join(lines),
        "context": context,
        "citations": citations,
        "evidence": citations,
        "context_only": False,
        "prompt": None,
        "universal_answer_fallback": True,
        "answer_quality": {
            **quality,
            "status": "fallback",
            "fallback_citation_count": len(citations),
        },
        "primary_answer_preview": _citation_preview(primary_response.get("answer"), limit=800),
    }


def _ensure_unified_query_answer_contract(
    response: dict[str, Any],
    *,
    question: str,
    text_retriever: "_QueryCollectionTextRetriever",
    collection_name: str,
    top_k: int,
) -> dict[str, Any]:
    quality = _assess_unified_query_answer_quality(response, question)
    if quality["status"] == "ok":
        response["answer_quality"] = quality
        return response
    return _build_universal_query_fallback_response(
        question=question,
        text_retriever=text_retriever,
        collection_name=collection_name,
        top_k=top_k,
        primary_response=response,
        quality=quality,
    )


def _should_block_graph_quality(graph_quality_report: Any) -> bool:
    if graph_quality_report.gate_status == "pass":
        return False
    failures = {
        str(item.get("metric") or "")
        for item in graph_quality_report.gate_failures
        if str(item.get("metric") or "").strip()
    }
    if not failures:
        return False
    if failures != {"isolated_node_rate"}:
        return True

    metrics = graph_quality_report.metrics
    return not (
        float(metrics.get("evidence_coverage") or 0.0) >= 1.0
        and float(metrics.get("low_confidence_edge_rate") or 0.0) <= 0.0
        and float(metrics.get("community_assignment_coverage") or 0.0) >= 1.0
        and float(metrics.get("community_summary_coverage") or 0.0) >= 1.0
        and float(metrics.get("summary_evidence_coverage") or 0.0) >= 1.0
        and float(metrics.get("summary_sentence_evidence_coverage") or 0.0) >= 1.0
        and float(metrics.get("summary_sentence_source_coverage") or 0.0) >= 1.0
    )


def _mark_graph_quality_non_blocking(graph_quality: dict[str, Any]) -> dict[str, Any]:
    quality_gate = graph_quality.setdefault("quality_gate", {})
    quality_gate["status"] = "warn"
    quality_gate["blocking"] = False
    quality_gate["message"] = (
        "Only isolated nodes failed the graph quality gate; evidence, confidence, "
        "community assignment, and community summary citations are valid, so GraphRAG "
        "can still use the connected graph and global summaries."
    )
    return graph_quality


def _derive_lightrag_mode(active_paths: tuple[str, ...], route_strategy: str) -> str:
    path_set = set(active_paths)
    if path_set == {"naive"} or route_strategy == RoutingDecision.VECTOR_ONLY:
        return "naive"
    if path_set == {"local"}:
        return "local"
    if path_set == {"global"}:
        return "global"
    if path_set == {"local", "global"}:
        return "hybrid"
    return "mix"


def _write_graph_triage_record(
    request: Request,
    *,
    question: str,
    graph_db_path: Path | None,
    route: dict,
    graph_quality: dict | None,
    citations: list[dict] | None,
    answer: str | None,
    log_file: str,
    lightrag_diagnostics: dict | None = None,
) -> dict:
    quality_gate = (graph_quality or {}).get("quality_gate") or {}
    record = _graph_triage_store(request).append(
        {
            "question": question,
            "graph_db_path": str(graph_db_path) if graph_db_path else None,
            "route": route,
            "graph_quality_status": quality_gate.get("status"),
            "graph_quality": graph_quality,
            "citation_count": len(citations or []),
            "source_evidence_count": _source_evidence_count(citations),
            "lightrag_diagnostics": lightrag_diagnostics,
            "answer_preview": str(answer or "")[:500],
            "log_file": log_file,
        }
    )
    return record


def _validate_top_k(top_k: int, *, max_top_k: int = 20) -> int:
    value = int(top_k)
    if value < 1 or value > max_top_k:
        raise HTTPException(status_code=400, detail=f"top_k ?1 ?{max_top_k} ")
    return value


def _list_operation_logs(log_dir: Path, limit: int = 50) -> list[dict]:
    log_dir = Path(log_dir)
    if not log_dir.exists():
        return []

    items: list[dict] = []
    for path in sorted(log_dir.glob("*.log"), key=lambda item: item.stat().st_mtime, reverse=True):
        stat = path.stat()
        items.append(
            {
                "filename": path.name,
                "size_kb": round(stat.st_size / 1024, 1),
                "modified": stat.st_mtime,
            }
        )
        if len(items) >= limit:
            break
    return items


def _parse_operation_log_payload(line: str) -> dict[str, Any] | None:
    json_start = str(line or "").find("{")
    if json_start < 0:
        return None
    try:
        payload = orjson.loads(line[json_start:].encode("utf-8"))
    except orjson.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _stage_label_from_event(event: str) -> str:
    label = str(event or "").strip()
    for suffix in ("_start", "_ok", "_error"):
        if label.endswith(suffix):
            label = label[: -len(suffix)]
            break
    return label or "operation"


def _operation_log_progress(log_path: Path, *, recent_limit: int = 40) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    with Path(log_path).open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            payload = _parse_operation_log_payload(line)
            if payload is not None:
                events.append(payload)

    if not events:
        return {
            "log_file": Path(log_path).name,
            "status": "unknown",
            "percent": 0,
            "event_count": 0,
            "current_stage": "waiting",
            "recent_events": [],
        }

    last = events[-1]
    status = "running"
    for item in reversed(events):
        event = str(item.get("event") or "")
        if event == "operation_end":
            status = str(item.get("status") or "ok").strip() or "ok"
            break
        if str(item.get("level") or "").upper() == "ERROR" or event.endswith("_error"):
            status = "error"
            break

    if status in {"ok", "success", "completed"}:
        percent = 100
    elif status == "error":
        percent = 100
    else:
        completed_stage_count = len({
            _stage_label_from_event(str(item.get("event") or ""))
            for item in events
            if str(item.get("event") or "").endswith("_ok")
        })
        started_stage_count = len({
            _stage_label_from_event(str(item.get("event") or ""))
            for item in events
            if str(item.get("event") or "").endswith("_start")
        })
        percent = min(92, 4 + completed_stage_count * 12 + max(0, started_stage_count - completed_stage_count) * 4)

    for item in reversed(events):
        try:
            done = float(item.get("done"))
            total = float(item.get("total"))
        except (TypeError, ValueError):
            continue
        if total > 0 and status == "running":
            percent = max(percent, min(95, round(done / total * 100)))
            break

    started_ts = str(events[0].get("ts") or "")
    updated_ts = str(last.get("ts") or "")
    elapsed_s = last.get("elapsed_s")
    if not isinstance(elapsed_s, (int, float)):
        try:
            started = datetime.fromisoformat(started_ts.replace("Z", "+00:00"))
            updated = datetime.fromisoformat(updated_ts.replace("Z", "+00:00"))
            elapsed_s = round((updated - started).total_seconds(), 3)
        except (TypeError, ValueError):
            elapsed_s = None

    recent = events[-max(1, min(int(recent_limit), 200)) :]
    return {
        "log_file": Path(log_path).name,
        "status": status,
        "percent": int(max(0, min(100, percent))),
        "event_count": len(events),
        "started_at": started_ts,
        "updated_at": updated_ts,
        "elapsed_s": elapsed_s,
        "current_stage": _stage_label_from_event(str(last.get("event") or "")),
        "last_event": str(last.get("event") or ""),
        "last_level": str(last.get("level") or ""),
        "recent_events": recent,
    }


def _resolve_log_path(log_dir: Path, filename: str) -> Path:
    clean_name = str(filename or "").strip()
    if not LOG_FILENAME_PATTERN.fullmatch(clean_name):
        raise HTTPException(status_code=400, detail="")
    log_root = Path(log_dir).resolve()
    log_path = (log_root / clean_name).resolve()
    try:
        log_path.relative_to(log_root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="") from exc
    if not log_path.exists() or not log_path.is_file():
        raise HTTPException(status_code=404, detail="log file not found")
    return log_path


def _enforce_log_same_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    host = request.headers.get("host")
    if not origin or not host:
        return
    if urlparse(origin).netloc != host:
        raise HTTPException(status_code=403, detail="logs are restricted to same-origin access")


def _resolve_upload_path(upload_dir: Path, filename: str) -> tuple[str, Path]:
    stored_name = str(filename or "").strip()
    if (
        not stored_name
        or stored_name == UPLOAD_MANIFEST_NAME
        or _safe_upload_name(stored_name) != stored_name
    ):
        raise HTTPException(status_code=400, detail="")

    upload_root = Path(upload_dir).resolve()
    file_path = (upload_root / stored_name).resolve()
    try:
        file_path.relative_to(upload_root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="") from exc
    return stored_name, file_path


def _resolve_public_books_input_dir(request: Request, raw_input_dir: str) -> Path:
    requested = Path(str(raw_input_dir or "").strip()).expanduser()
    input_dir = requested.resolve() if requested.is_absolute() else (REPO_ROOT / requested).resolve()
    allowed_roots = (
        PUBLIC_BOOKS_JSON_ROOT.resolve(),
        Path(request.app.state.upload_dir).resolve(),
    )
    if not any(input_dir.is_relative_to(root) for root in allowed_roots):
        raise HTTPException(status_code=400, detail="input_dir is not allowed")
    if not input_dir.exists() or not input_dir.is_dir():
        raise HTTPException(status_code=400, detail=f"JSON input_dir does not exist: {input_dir}")
    return input_dir


def _purge_vectors_by_source_files(persist_dir: Path, filenames: list[str]) -> dict:
    requested = [str(name).strip() for name in filenames if str(name).strip()]
    if not requested:
        return {"chunks_deleted": 0, "collections": {}}

    client = _create_client(persist_dir)
    deleted_total = 0
    deleted_by_collection: dict[str, int] = {}

    try:
        for coll in client.list_collections():
            collection = client.get_collection(name=coll.name)
            collection_deleted = 0
            for filename in requested:
                try:
                    payload = collection.get(where={"source_file": filename})
                except Exception:
                    payload = {"ids": []}
                ids = payload.get("ids") or []
                if ids:
                    collection.delete(ids=ids)
                    collection_deleted += len(ids)
            if collection_deleted:
                deleted_by_collection[coll.name] = collection_deleted
                deleted_total += collection_deleted
    finally:
        _close_client(client)

    return {"chunks_deleted": deleted_total, "collections": deleted_by_collection}


class _QueryCollectionTextRetriever:
    def __init__(self, *, persist_dir: Path, collection_name: str) -> None:
        self.persist_dir = persist_dir
        self.collection_name = collection_name

    def retrieve(self, query: str, top_k: int = 5) -> list[dict]:
        result = query_collection(
            query_text=query,
            persist_dir=self.persist_dir,
            collection_name=self.collection_name,
            top_k=top_k,
        )
        return list(result.get("results") or [])

    def scan_all(self, limit: int | None = 1000) -> list[dict]:
        client = _create_client(self.persist_dir)
        try:
            collection = client.get_collection(name=self.collection_name)
            count = collection.count()
            if count <= 0:
                return []
            if limit is None or int(limit) <= 0:
                resolved_limit = count
            else:
                resolved_limit = min(count, max(1, int(limit)))
            result = collection.get(
                include=["documents", "metadatas"],
                limit=resolved_limit,
            )
            ids = result.get("ids") or []
            documents = result.get("documents") or []
            metadatas = result.get("metadatas") or []
            items: list[dict] = []
            for index, document in enumerate(documents):
                metadata = metadatas[index] if index < len(metadatas) and isinstance(metadatas[index], dict) else {}
                source = (
                    metadata.get("source_file")
                    or metadata.get("source")
                    or metadata.get("filename")
                    or metadata.get("file")
                )
                items.append(
                    {
                        "id": ids[index] if index < len(ids) else None,
                        "text": document,
                        "source": source,
                        "score": 1.0,
                        "metadata": metadata,
                    }
                )
            return items
        finally:
            _close_client(client)


class _EmptyRetriever:
    def retrieve(self, query: str, top_k: int = 5) -> list[dict]:
        return []


class _ConfiguredLLMClient:
    def __init__(self, client, *, temperature: float, max_tokens: int) -> None:
        self.client = client
        self.temperature = temperature
        self.max_tokens = max_tokens

    def generate(self, prompt: str, **kwargs) -> str:
        kwargs.setdefault("temperature", self.temperature)
        kwargs.setdefault("max_tokens", self.max_tokens)
        return self.client.generate(prompt, **kwargs)

    def complete(self, prompt: str, **kwargs) -> str:
        return self.generate(prompt, **kwargs)

    def invoke(self, prompt: str, **kwargs) -> str:
        return self.generate(prompt, **kwargs)


class _RecordingQueryRouter:
    def __init__(
        self,
        delegate,
        *,
        default_strategy: str,
        reason: str,
        default_task_route: QueryRouteName | None = None,
    ) -> None:
        self.delegate = delegate
        self.last_route = QueryRoute(strategy=default_strategy, reason=reason, task_route=default_task_route)

    def route_query(self, question: str) -> QueryRoute:
        self.last_route = self.delegate.route_query(question)
        return self.last_route


class _StaticQueryRouter:
    def __init__(self, strategy: str, reason: str, task_route: QueryRouteName | None = None) -> None:
        self.route = QueryRoute(strategy=strategy, reason=reason, task_route=task_route)

    def route_query(self, question: str) -> QueryRoute:
        return self.route


def _mode_to_route(mode: str) -> QueryRoute:
    normalized = (mode or "auto").strip().lower()
    if normalized == "vector":
        return QueryRoute(RoutingDecision.VECTOR_ONLY, "Mode override: vector", QueryRouteName.LOCAL_RAG)
    if normalized == "global":
        return QueryRoute(RoutingDecision.GLOBAL_SEARCH, "Mode override: global", QueryRouteName.GLOBAL_SUMMARY)
    if normalized == "aggregation":
        return QueryRoute(
            RoutingDecision.GLOBAL_SEARCH,
            "Mode override: aggregation uses global context plus text evidence",
            QueryRouteName.COMPREHENSIVE_ANALYSIS,
        )
    return QueryRoute(RoutingDecision.LOCAL_SEARCH, "Mode override: local", QueryRouteName.GRAPH_PATH)


@dataclass(frozen=True, slots=True)
class AnalysisProfile:
    profile_id: str
    analysis_type: str
    partition_keys: tuple[str, ...]
    label_keys: tuple[str, ...]
    evidence_id_keys: tuple[str, ...]
    date_keys: tuple[str, ...]
    source_keys: tuple[str, ...]


GENERIC_PARTITION_PROFILE = AnalysisProfile(
    profile_id="generic_partition_evidence",
    analysis_type="generic_partition_evidence_sweep",
    partition_keys=(
        "partition_id",
        "document_id",
        "case_id",
        "project_id",
        "equipment_id",
        "equipment",
        "source_txt",
        "source_html",
        "source_file",
        "filename",
        "record_id",
    ),
    label_keys=("title", "heading", "section", "name", "filename", "source_file", "document_id"),
    evidence_id_keys=("message_id", "msg_id", "chunk_id", "record_id", "chroma_id"),
    date_keys=("date", "send_date", "source_date", "created_at", "first_date", "last_date", "time"),
    source_keys=("source_file", "filename", "source", "source_txt", "source_html"),
)

_GENERIC_COMPREHENSIVE_SCOPE_MARKERS = (
    "full corpus",
    "full-corpus",
    "all documents",
    "all docs",
    "all files",
    "every document",
    "entire corpus",
    "whole corpus",
    "\u5168\u91cf",
    "\u6240\u6709\u6587\u6863",
    "\u6240\u6709\u8d44\u6599",
    "\u5168\u90e8\u8d44\u6599",
    "\u6bcf\u4e2a\u6587\u6863",
    "\u9010\u4e2a",
)
_GENERIC_ANALYSIS_MARKERS = (
    "analysis",
    "analyze",
    "scan",
    "sweep",
    "evidence",
    "map-reduce",
    "map reduce",
    "\u5206\u6790",
    "\u626b\u63cf",
    "\u8bc1\u636e",
    "\u7edf\u8ba1",
    "\u6c47\u603b",
)
_GENERIC_STOP_TERMS = {
    "run",
    "full",
    "corpus",
    "evidence",
    "analysis",
    "analyze",
    "scan",
    "sweep",
    "across",
    "all",
    "documents",
    "document",
    "docs",
    "files",
    "file",
    "for",
    "the",
    "and",
    "with",
    "from",
    "only",
    "use",
    "top",
    "chunks",
    "chunk",
    "not",
    "do",
    "does",
    "please",
    "find",
    "show",
    "list",
    "each",
    "every",
}

def _compact_query_text(question: str) -> str:
    return re.sub(r"\s+", "", str(question or "").casefold())


def _is_generic_comprehensive_analysis_question(question: str) -> bool:
    text = str(question or "").strip().casefold()
    if not text:
        return False
    return (
        any(marker.casefold() in text for marker in _GENERIC_COMPREHENSIVE_SCOPE_MARKERS)
        and any(marker.casefold() in text for marker in _GENERIC_ANALYSIS_MARKERS)
    )


def _extract_generic_query_terms(question: str) -> list[str]:
    raw_terms = re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}|[\u4e00-\u9fff]{2,}", str(question or ""))
    terms: list[str] = []
    seen: set[str] = set()
    for term in raw_terms:
        normalized = term.casefold().strip("-_")
        if not normalized or normalized in _GENERIC_STOP_TERMS or normalized.isdigit():
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        terms.append(normalized)
    return terms[:24]


def _metadata_text(metadata: dict[str, Any], keys: tuple[str, ...] | list[str], *, default: str = "") -> str:
    for key in keys:
        value = metadata.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return default


def _extract_line_date(line: str, metadata: dict[str, Any]) -> str:
    existing = _metadata_text(metadata, GENERIC_PARTITION_PROFILE.date_keys)
    if existing:
        return existing
    match = re.search(r"(\d{4}[-/年]\d{1,2}[-/月]\d{1,2}(?:日)?(?:\s+\[\d{1,2}:\d{2}(?::\d{2})?\])?)", str(line or ""))
    return match.group(1) if match else ""


def _extract_line_sender(line: str, metadata: dict[str, Any]) -> str:
    existing = _metadata_text(metadata, ("sender", "from", "speaker", "contact_name", "name"))
    if existing:
        return existing
    cleaned = str(line or "").strip()
    cleaned = re.sub(r"^\d{4}[-/年]\d{1,2}[-/月]\d{1,2}(?:日)?\s*(?:\[\d{1,2}:\d{2}(?::\d{2})?\])?\s*", "", cleaned)
    match = re.match(r"([^:：]{1,40})[:：]", cleaned)
    return match.group(1).strip() if match else ""


def _choose_profile_partition_key(items: list[dict[str, Any]], profile: AnalysisProfile) -> str:
    metadata_rows = [
        dict(item.get("metadata") or {})
        for item in items
        if isinstance(item, dict) and isinstance(item.get("metadata"), dict)
    ]
    for key in profile.partition_keys:
        values = {str(meta.get(key) or "").strip() for meta in metadata_rows if str(meta.get(key) or "").strip()}
        if len(values) >= 2:
            return key
    for key in profile.partition_keys:
        if any(str(meta.get(key) or "").strip() for meta in metadata_rows):
            return key
    return "chunk_id"


def _profile_partition_id(metadata: dict[str, Any], partition_key: str, fallback: str) -> str:
    value = str(metadata.get(partition_key) or "").strip()
    if value:
        return value
    for key in ("source_file", "filename", "record_id", "chroma_id"):
        value = str(metadata.get(key) or "").strip()
        if value:
            return value
    return fallback


def _profile_partition_label(metadata: dict[str, Any], profile: AnalysisProfile, partition_id: str) -> str:
    for key in profile.label_keys:
        value = str(metadata.get(key) or "").strip()
        if value:
            return value
    return partition_id


def _generic_line_matches(line: str, terms: list[str]) -> tuple[bool, list[str]]:
    if not terms:
        return False, []
    folded = str(line or "").casefold()
    hits = [term for term in terms if term in folded]
    return bool(hits), hits


def _extract_generic_partition_evidence(
    *,
    text: str,
    metadata: dict[str, Any],
    chunk_id: str,
    partition_id: str,
    terms: list[str],
) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    if not lines and str(text or "").strip():
        lines = [str(text).strip()]
    for line_index, line in enumerate(lines, start=1):
        matched, hit_terms = _generic_line_matches(line, terms)
        if not matched:
            continue
        message_id = _metadata_text(metadata, GENERIC_PARTITION_PROFILE.evidence_id_keys, default=f"{chunk_id}#line-{line_index}")
        evidence.append(
            {
                "partition_id": partition_id,
                "date": _metadata_text(metadata, GENERIC_PARTITION_PROFILE.date_keys) or _extract_line_date(line, metadata),
                "sender": _extract_line_sender(line, metadata),
                "chunk_id": str(metadata.get("chunk_id") or chunk_id or ""),
                "message_id": message_id,
                "line_index": line_index,
                "hit_terms": hit_terms,
                "text": line,
                "source": _metadata_text(metadata, GENERIC_PARTITION_PROFILE.source_keys),
            }
        )
    return evidence


def _format_generic_partition_analysis_answer(report: dict[str, Any]) -> str:
    coverage = report["coverage_report"]
    profile = report["analysis_profile"]
    candidates = report["candidates"]
    lines = [
        "Result:",
        (
            f"- Found {coverage['candidate_partition_count']} partition(s) with traceable original-text evidence "
            f"after scanning {coverage['scanned_chunks']} chunk(s) across {coverage['partitions_analyzed']} partition(s)."
        ),
        "- This result is based on a full partition scan, not only top-k chunks.",
        f"- Partition key used: {profile['partition_key']}.",
        "",
        "Matched evidence:",
    ]
    if not candidates:
        lines.append("- No partition has traceable original-text evidence for the requested terms.")
    for index, candidate in enumerate(candidates[:30], start=1):
        lines.extend(
            [
                f"{index}. {candidate['partition_label'] or candidate['partition_id']}",
                f"   - partition_id: {candidate['partition_id']}",
                f"   - evidence_count: {candidate['evidence_count']}",
            ]
        )
        for row in candidate.get("evidence", [])[:5]:
            lines.append(
                "   - {date} | message_id={message_id} | chunk_id={chunk_id}: {text} [{citation}]".format(
                    date=row.get("date") or "unknown date",
                    message_id=row.get("message_id") or "-",
                    chunk_id=row.get("chunk_id") or "-",
                    text=row.get("text") or "",
                    citation=row.get("citation_id") or "",
                )
            )
        if candidate.get("evidence_truncated"):
            lines.append(f"   - Evidence is truncated in the answer; structured payload keeps the count: {candidate['evidence_count']}.")
    lines.extend(
        [
            "",
            "Why other partitions are not counted:",
            "- partitions without matching original-text evidence are not counted.",
            "- structured coverage details remain available in coverage_report and partition_analysis.",
        ]
    )
    return "\n".join(lines)


def _run_generic_partition_comprehensive_analysis(
    *,
    text_retriever: _QueryCollectionTextRetriever,
    collection_name: str,
    question: str,
) -> dict[str, Any]:
    all_items = text_retriever.scan_all(limit=0)
    profile = GENERIC_PARTITION_PROFILE
    partition_key = _choose_profile_partition_key(all_items, profile)
    terms = _extract_generic_query_terms(question)
    partitions: dict[str, dict[str, Any]] = {}
    evidence_rows: list[dict[str, Any]] = []

    for raw_index, item in enumerate(all_items, start=1):
        metadata = dict(item.get("metadata") or {}) if isinstance(item, dict) else {}
        chunk_id = str(item.get("id") or metadata.get("chunk_id") or raw_index)
        partition_id = _profile_partition_id(metadata, partition_key, fallback=chunk_id)
        partition = partitions.setdefault(
            partition_id,
            {
                "partition_id": partition_id,
                "partition_label": _profile_partition_label(metadata, profile, partition_id),
                "chunk_count": 0,
                "evidence": [],
            },
        )
        partition["chunk_count"] += 1
        evidence = _extract_generic_partition_evidence(
            text=str(item.get("text") or ""),
            metadata=metadata,
            chunk_id=chunk_id,
            partition_id=partition_id,
            terms=terms,
        )
        partition["evidence"].extend(evidence)

    citation_rank = 1
    candidates: list[dict[str, Any]] = []
    for partition in partitions.values():
        evidence = partition["evidence"]
        if not evidence:
            continue
        deduped: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()
        for row in evidence:
            key = (str(row.get("partition_id") or ""), str(row.get("message_id") or ""), str(row.get("text") or ""))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(row)
        deduped.sort(key=lambda row: (-len(row.get("hit_terms") or []), str(row.get("date") or ""), int(row.get("line_index") or 0)))
        normalized: list[dict[str, Any]] = []
        for row in deduped:
            citation_id = f"T{citation_rank}"
            citation_rank += 1
            row = {**row, "citation_id": citation_id}
            normalized.append(row)
            evidence_rows.append(row)
        candidates.append(
            {
                "partition_id": partition["partition_id"],
                "partition_label": partition["partition_label"],
                "chunk_count": partition["chunk_count"],
                "evidence_count": len(normalized),
                "evidence": normalized,
                "evidence_truncated": len(normalized) > 5,
            }
        )

    candidates.sort(key=lambda item: (-item["evidence_count"], item["partition_label"]))
    coverage = {
        "analysis_type": profile.analysis_type,
        "collection": collection_name,
        "top_k_used": False,
        "scanned_chunks": len(all_items),
        "partition_key": partition_key,
        "partitions_analyzed": len(partitions),
        "candidate_partition_count": len(candidates),
        "partitions_without_evidence_count": max(0, len(partitions) - len(candidates)),
    }
    profile_payload = {
        "profile_id": profile.profile_id,
        "analysis_type": profile.analysis_type,
        "partition_key": partition_key,
        "query_terms": terms,
        "evidence_id_keys": list(profile.evidence_id_keys),
        "date_keys": list(profile.date_keys),
        "source_keys": list(profile.source_keys),
    }
    citations = [
        {
            "id": row["citation_id"],
            "source_type": "text_full_partition_scan",
            "rank": index,
            "text": row["text"],
            "source": row.get("source"),
            "metadata": {
                "partition_id": row.get("partition_id"),
                "date": row.get("date"),
                "sender": row.get("sender"),
                "chunk_id": row.get("chunk_id"),
                "message_id": row.get("message_id"),
                "hit_terms": row.get("hit_terms") or [],
                "retrieval_path": "generic_full_partition_scan",
            },
            "raw_id": row.get("message_id") or row.get("chunk_id"),
        }
        for index, row in enumerate(evidence_rows, start=1)
    ]
    report = {
        "question": question,
        "collection": collection_name,
        "analysis_profile": profile_payload,
        "coverage_report": coverage,
        "candidates": candidates,
    }
    context = "\n\n".join(
        [
            "## Generic full-partition scan coverage",
            orjson.dumps(coverage, option=orjson.OPT_INDENT_2).decode("utf-8"),
            "## Candidate partitions",
            orjson.dumps(candidates, option=orjson.OPT_INDENT_2).decode("utf-8"),
        ]
    )
    return {
        "question": question,
        "answer": _format_generic_partition_analysis_answer(report),
        "context": context,
        "citations": citations,
        "evidence": citations,
        "context_only": False,
        "prompt": None,
        "task_spec": {
            "original_question": question,
            "rewritten_question": question,
            "intent": "comprehensive",
            "route": QueryRouteName.COMPREHENSIVE_ANALYSIS.value,
            "objects": ["partitions"],
            "evidence_requirements": {
                "must_cite": True,
                "require_source_span": True,
                "no_evidence_policy": "return_insufficient_evidence",
                "coverage_report": True,
                "min_sources": 1,
            },
            "output_contract": {
                "format": "partition_evidence_ledger",
                "include_citations": True,
                "include_uncertainty": True,
            },
            "requires_planning": True,
            "route_reason": "deterministic generic full-partition analysis",
        },
        "advanced_mode": QueryRouteName.COMPREHENSIVE_ANALYSIS.value,
        "steps": [
            {"index": 1, "type": "resolve_analysis_profile", "evidence_count": 1},
            {"index": 2, "type": "scan_all_chunks", "evidence_count": len(all_items)},
            {"index": 3, "type": "partition_by_metadata", "evidence_count": len(partitions)},
            {"index": 4, "type": "build_evidence_ledger", "evidence_count": len(citations)},
        ],
        "coverage_report": coverage,
        "comparison_table": [],
        "analysis_profile": profile_payload,
        "partition_analysis": report,
    }


_PRIVATE_CONTACT_AFFECTION_TERMS = (
    "宝宝",
    "宝贝",
    "亲爱的",
    "想你",
    "喜欢你",
    "喜欢",
    "爱你",
    "抱抱",
    "亲亲",
    "晚安",
    "撒娇",
    "陪陪",
    "想要你陪",
    "约见面",
    "亲密",
    "暧昧",
    "好感",
)

_PRIVATE_CONTACT_EVENT_TERMS = (
    "安慰",
    "争执",
    "吵架",
    "难过",
    "喜欢",
    "想你",
    "陪",
    "见面",
    "约",
    "好感",
    "暧昧",
    "情绪",
    "租房",
    "房子",
    "房屋",
    "房租",
    "出租",
    "租金",
    "中介",
)

_PRIVATE_CONTACT_RENTAL_TERMS = (
    "租房",
    "房子",
    "房屋",
    "房租",
    "出租",
    "租金",
    "房东",
    "房源",
    "公寓",
    "看房",
    "合租",
    "整租",
    "押金",
)

_PRIVATE_CONTACT_EXCLUDED_TYPES = {
    "group",
    "group_chat",
    "chatroom",
    "room",
    "public",
    "official",
    "system",
    "filehelper",
    "file_helper",
}


def _is_private_contact_full_scan_question(question: str) -> bool:
    text = _compact_query_text(question)
    raw = str(question or "").casefold()
    return (
        "contact_full_scan" in raw
        or ("好感" in text and ("谁" in text or "哪些人" in text or "联系人" in text or "和我" in text))
        or ("暧昧" in text and ("线索" in text or "情绪" in text or "值得注意" in text or "有没有" in text))
        or ("情绪" in text and ("暧昧" in text or "线索" in text or "值得注意" in text))
        or ("私聊" in text and "联系人" in text and ("暧昧" in text or "关系" in text or "分析" in text))
        or ("全量" in text and ("暧昧" in text or "女生" in text) and ("联系人" in text or "私聊" in text))
    )


def _is_private_contact_question(question: str) -> bool:
    text = _compact_query_text(question)
    if _is_private_contact_full_scan_question(question):
        return True
    markers = ("谁", "哪些人", "哪个人", "联系人", "和我", "我和", "对方")
    term_hit = any(term in text for term in _PRIVATE_CONTACT_EVENT_TERMS)
    return term_hit and (any(marker in text for marker in markers) or "有关的人" in text or "相关的人" in text)


def _is_self_identity_question(question: str) -> bool:
    text = _compact_query_text(question)
    return any(
        marker in text
        for marker in (
            "我是谁",
            "我叫什么",
            "我的名字",
            "我的微信名",
            "号主是谁",
            "账号主人是谁",
            "账户主人是谁",
            "当前微信账号主人",
            "聊天记录中的我是谁",
            "谁是我",
        )
    )


def _metadata_is_excluded_contact(metadata: dict[str, Any]) -> tuple[bool, str]:
    values = {
        "conversation_type": str(metadata.get("conversation_type") or "").strip().casefold(),
        "contact_name": str(metadata.get("contact_name") or metadata.get("name") or "").strip().casefold(),
        "username": str(metadata.get("username") or metadata.get("user_name") or "").strip().casefold(),
        "contact_id": str(metadata.get("contact_id") or "").strip().casefold(),
        "partition_id": str(metadata.get("partition_id") or "").strip().casefold(),
    }
    if values["conversation_type"] in _PRIVATE_CONTACT_EXCLUDED_TYPES:
        return True, "system_or_file_helper" if "file" in values["conversation_type"] or values["conversation_type"] == "system" else "non_private_chat"
    joined = " ".join(values.values())
    if "filehelper" in joined or "文件传输助手" in joined:
        return True, "system_or_file_helper"
    if "公众号" in joined or "订阅号" in joined or "服务通知" in joined:
        return True, "system_or_file_helper"
    if "@chatroom" in joined:
        return True, "group_chat"
    return False, ""


def _metadata_is_private_contact(metadata: dict[str, Any], text: str) -> bool:
    excluded, _reason = _metadata_is_excluded_contact(metadata)
    if excluded:
        return False
    conversation_type = str(metadata.get("conversation_type") or "").strip().casefold()
    if conversation_type == "private":
        return True
    if any(str(metadata.get(key) or "").strip() for key in ("contact_id", "username", "contact_name", "conversation_id")):
        return True
    if str(metadata.get("partition_id") or "").startswith("contact:"):
        return True
    return "微信聊天记录" in str(text or "") or "WeChat" in str(text or "")


def _looks_like_private_contact_collection(collection_name: str, sample_items: list[dict[str, Any]]) -> bool:
    collection_hint = str(collection_name or "").casefold()
    if "wechat" in collection_hint or "weixin" in collection_hint or "private" in collection_hint:
        return True
    for item in sample_items:
        metadata = dict(item.get("metadata") or {}) if isinstance(item, dict) else {}
        if _metadata_is_private_contact(metadata, str(item.get("text") or "")):
            return True
    return False


def _should_run_private_contact_scan(question: str, collection_name: str, sample_items: list[dict[str, Any]]) -> bool:
    if not _is_private_contact_question(question):
        return False
    return _looks_like_private_contact_collection(collection_name, sample_items)


def _is_vague_collection_overview_question(question: str) -> bool:
    text = _compact_query_text(question)
    raw = str(question or "").casefold()
    if not text:
        return False
    markers = (
        "这里面讲的是什么",
        "里面讲的是什么",
        "讲的是什么",
        "知识库里有什么",
        "整体说一下",
        "整体介绍",
        "大概说一下",
        "主要讲什么",
        "主要内容",
        "随便总结",
        "总结一下",
        "概括一下",
        "这个资料里",
        "最值得关注",
        "最值得我关注",
        "值得关注的事情",
    )
    english_markers = (
        "what is this about",
        "summarize this",
        "overview",
        "what is in this corpus",
        "what should i pay attention to",
    )
    return any(marker in text for marker in markers) or any(marker in raw for marker in english_markers)


def _is_private_contact_overview_question(question: str) -> bool:
    text = _compact_query_text(question)
    if not text:
        return False
    return (
        ("重要的人" in text or "主要的人" in text or "人和关系" in text or "联系人关系" in text)
        or ("有哪些人" in text and ("关系" in text or "重要" in text))
        or ("联系人" in text and ("有哪些" in text or "关系" in text or "重要" in text))
    )


def _source_from_item(item: dict[str, Any], metadata: dict[str, Any]) -> str:
    return str(
        item.get("source")
        or metadata.get("source_file")
        or metadata.get("source")
        or metadata.get("filename")
        or metadata.get("file")
        or "unknown source"
    )


def _item_chunk_id(item: dict[str, Any], metadata: dict[str, Any], fallback: int) -> str:
    return str(item.get("id") or metadata.get("chunk_id") or metadata.get("record_id") or fallback)


def _sample_text_preview(text: str, limit: int = 220) -> str:
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    if not lines and str(text or "").strip():
        lines = [str(text).strip()]
    useful_lines = [
        line
        for line in lines
        if not line.lower().startswith(("attachments", "source_file", "metadata", "relative_path"))
    ]
    return _citation_preview(" / ".join(useful_lines[:3] or lines[:3]), limit=limit)


def _date_range_from_contacts(contacts: list[dict[str, Any]]) -> tuple[str, str]:
    starts = [str(item.get("first_date") or "").strip() for item in contacts if str(item.get("first_date") or "").strip()]
    ends = [str(item.get("last_date") or "").strip() for item in contacts if str(item.get("last_date") or "").strip()]
    return (min(starts) if starts else "", max(ends) if ends else "")


def _private_contact_rows_from_items(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    contacts: dict[str, dict[str, Any]] = {}
    excluded_reasons: dict[str, int] = {}
    for raw_index, item in enumerate(items, start=1):
        metadata = dict(item.get("metadata") or {}) if isinstance(item, dict) else {}
        text = str(item.get("text") or "")
        excluded, reason = _metadata_is_excluded_contact(metadata)
        if excluded:
            excluded_reasons[reason or "excluded"] = excluded_reasons.get(reason or "excluded", 0) + 1
            continue
        if not _metadata_is_private_contact(metadata, text):
            excluded_reasons["non_private_chat"] = excluded_reasons.get("non_private_chat", 0) + 1
            continue
        chunk_id = _item_chunk_id(item, metadata, raw_index)
        contact_id = _private_contact_id(metadata, fallback=f"contact:{raw_index}")
        contact = contacts.setdefault(
            contact_id,
            {
                "contact_id": contact_id,
                "contact_name": _private_contact_label(metadata, text, contact_id),
                "remark": str(metadata.get("remark") or "").strip(),
                "username": str(metadata.get("username") or "").strip(),
                "chunk_count": 0,
                "message_count": 0,
                "first_date": str(metadata.get("first_date") or "").strip(),
                "last_date": str(metadata.get("last_date") or "").strip(),
                "source": _source_from_item(item, metadata),
                "sample_chunk_id": chunk_id,
                "sample_text": _sample_text_preview(text),
            },
        )
        contact["chunk_count"] += 1
        try:
            contact["message_count"] = max(
                int(contact.get("message_count") or 0),
                int(metadata.get("message_count") or 0),
            )
        except (TypeError, ValueError):
            pass
        first_date = str(metadata.get("first_date") or "").strip()
        last_date = str(metadata.get("last_date") or "").strip()
        if first_date and (not contact["first_date"] or first_date < contact["first_date"]):
            contact["first_date"] = first_date
        if last_date and (not contact["last_date"] or last_date > contact["last_date"]):
            contact["last_date"] = last_date
    rows = list(contacts.values())
    rows.sort(key=lambda item: (-int(item.get("message_count") or 0), -int(item.get("chunk_count") or 0), str(item.get("contact_name") or "")))
    return rows, excluded_reasons


def _build_overview_citations_from_contacts(contacts: list[dict[str, Any]], source_type: str, limit: int = 10) -> list[dict[str, Any]]:
    citations: list[dict[str, Any]] = []
    for index, contact in enumerate(contacts[:limit], start=1):
        citations.append(
            {
                "id": f"T{index}",
                "source_type": source_type,
                "rank": index,
                "text": contact.get("sample_text") or contact.get("contact_name") or "",
                "source": contact.get("source") or "unknown source",
                "metadata": {
                    "contact_id": contact.get("contact_id"),
                    "contact_name": contact.get("contact_name"),
                    "username": contact.get("username"),
                    "first_date": contact.get("first_date"),
                    "last_date": contact.get("last_date"),
                    "message_count": contact.get("message_count"),
                    "chunk_count": contact.get("chunk_count"),
                    "chunk_id": contact.get("sample_chunk_id"),
                    "retrieval_path": source_type,
                },
                "raw_id": contact.get("sample_chunk_id") or contact.get("contact_id"),
            }
        )
    return citations


def _format_collection_overview_answer(report: dict[str, Any]) -> str:
    coverage = report["coverage_report"]
    top_contacts = report.get("top_contacts") or []
    date_range = coverage.get("date_range") or {}
    lines = [
        "Result:",
        f"- 当前集合：{coverage['collection']}",
        f"- 这是一个{coverage.get('collection_kind') or '文本'}集合；共 {coverage['scanned_chunks']} 个 chunk。",
    ]
    if coverage.get("private_contact_count") is not None:
        lines.append(
            f"- 识别到 {coverage['private_contact_count']} 个一对一私聊联系人，消息数约 {coverage.get('message_count_estimate', 0)} 条。"
        )
    if date_range.get("first") or date_range.get("last"):
        lines.append(f"- 时间范围：{date_range.get('first') or '未知'} 到 {date_range.get('last') or '未知'}。")
    if coverage.get("source_files"):
        lines.append("- 主要来源文件：" + "、".join(coverage["source_files"][:5]))
    if top_contacts:
        lines.append("")
        lines.append("Top contacts / partitions:")
        for index, contact in enumerate(top_contacts[:10], start=1):
            lines.append(
                f"{index}. {contact.get('contact_name') or contact.get('contact_id')} "
                f"(username: {contact.get('username') or 'unknown'}, messages: {contact.get('message_count') or 0}, chunks: {contact.get('chunk_count') or 0})"
            )
    if report.get("sample_evidence"):
        lines.append("")
        lines.append("Sample evidence:")
        for citation in report["sample_evidence"][:5]:
            lines.append(f"- [{citation['id']}] {citation.get('source')}: {_citation_preview(citation.get('text'))}")
    lines.extend(
        [
            "",
            "Conclusion:",
            "- 这个回答是确定性集合概览，不依赖随机 top-k 摘取；如果要问具体事实，后续会再按问题做定向检索或全量扫描。",
        ]
    )
    return "\n".join(lines)


def _run_collection_overview_analysis(
    *,
    text_retriever: _QueryCollectionTextRetriever,
    collection_name: str,
    question: str,
) -> dict[str, Any]:
    all_items = text_retriever.scan_all(limit=0)
    contacts, excluded_reasons = _private_contact_rows_from_items(all_items)
    source_counter: Counter[str] = Counter()
    kind_counter: Counter[str] = Counter()
    for item in all_items:
        metadata = dict(item.get("metadata") or {}) if isinstance(item, dict) else {}
        source_counter[_source_from_item(item, metadata)] += 1
        kind_counter[str(metadata.get("source_kind") or metadata.get("source_ext") or "unknown")] += 1
    first_date, last_date = _date_range_from_contacts(contacts)
    citations = _build_overview_citations_from_contacts(contacts, "text_collection_overview", limit=8)
    if not citations:
        for index, item in enumerate(all_items[:8], start=1):
            metadata = dict(item.get("metadata") or {}) if isinstance(item, dict) else {}
            citations.append(
                {
                    "id": f"T{index}",
                    "source_type": "text_collection_overview",
                    "rank": index,
                    "text": _sample_text_preview(str(item.get("text") or "")),
                    "source": _source_from_item(item, metadata),
                    "metadata": {**metadata, "chunk_id": _item_chunk_id(item, metadata, index), "retrieval_path": "collection_overview"},
                    "raw_id": _item_chunk_id(item, metadata, index),
                }
            )
    coverage = {
        "analysis_type": "collection_overview",
        "collection": collection_name,
        "collection_kind": "微信私聊" if contacts else "通用文本",
        "top_k_used": False,
        "scanned_chunks": len(all_items),
        "private_contact_count": len(contacts) if contacts else None,
        "message_count_estimate": sum(int(item.get("message_count") or 0) for item in contacts),
        "date_range": {"first": first_date, "last": last_date},
        "source_files": [name for name, _count in source_counter.most_common(10) if name and name != "unknown source"],
        "source_type_counts": dict(kind_counter.most_common(10)),
        "excluded_reasons": excluded_reasons,
    }
    report = {
        "question": question,
        "collection": collection_name,
        "coverage_report": coverage,
        "top_contacts": contacts[:20],
        "sample_evidence": citations,
    }
    return {
        "question": question,
        "answer": _format_collection_overview_answer(report),
        "context": orjson.dumps(report, option=orjson.OPT_INDENT_2).decode("utf-8"),
        "citations": citations,
        "evidence": citations,
        "context_only": False,
        "prompt": None,
        "advanced_mode": QueryRouteName.COMPREHENSIVE_ANALYSIS.value,
        "coverage_report": coverage,
        "steps": [
            {"index": 1, "type": "scan_collection_metadata", "evidence_count": len(all_items)},
            {"index": 2, "type": "summarize_contacts_and_sources", "evidence_count": len(contacts)},
            {"index": 3, "type": "build_collection_overview", "evidence_count": len(citations)},
        ],
        "collection_overview": report,
    }


def _format_private_contact_overview_answer(report: dict[str, Any]) -> str:
    coverage = report["coverage_report"]
    lines = [
        "Result:",
        f"- Scanned {coverage['private_contact_count']} private contact(s) across {coverage['scanned_chunks']} chunk(s).",
        "- This is a deterministic contact overview, not a top-k-only answer.",
        "",
        "Important people / contact partitions:",
    ]
    contacts = report.get("contacts") or []
    if not contacts:
        lines.append("- No private contact partitions were found in the current collection.")
    for index, contact in enumerate(contacts[:30], start=1):
        lines.append(
            f"{index}. {contact.get('contact_name') or contact.get('contact_id')} "
            f"(username: {contact.get('username') or 'unknown'}, messages: {contact.get('message_count') or 0}, "
            f"chunks: {contact.get('chunk_count') or 0}, date: {contact.get('first_date') or 'unknown'} - {contact.get('last_date') or 'unknown'})"
        )
    lines.extend(
        [
            "",
            "How to read this:",
            "- “重要” here means high message/chunk coverage in the imported private-chat corpus.",
            "- This does not judge emotional closeness by itself; affection or event questions trigger a separate original-text evidence scan.",
        ]
    )
    return "\n".join(lines)


def _run_private_contact_overview_analysis(
    *,
    text_retriever: _QueryCollectionTextRetriever,
    collection_name: str,
    question: str,
) -> dict[str, Any]:
    all_items = text_retriever.scan_all(limit=0)
    contacts, excluded_reasons = _private_contact_rows_from_items(all_items)
    citations = _build_overview_citations_from_contacts(contacts, "text_private_contact_overview", limit=12)
    coverage = {
        "analysis_type": "private_contact_overview",
        "collection": collection_name,
        "top_k_used": False,
        "scanned_chunks": len(all_items),
        "private_contact_count": len(contacts),
        "message_count_estimate": sum(int(item.get("message_count") or 0) for item in contacts),
        "excluded_reasons": excluded_reasons,
    }
    report = {
        "question": question,
        "collection": collection_name,
        "coverage_report": coverage,
        "contacts": contacts,
    }
    return {
        "question": question,
        "answer": _format_private_contact_overview_answer(report),
        "context": orjson.dumps(report, option=orjson.OPT_INDENT_2).decode("utf-8"),
        "citations": citations,
        "evidence": citations,
        "context_only": False,
        "prompt": None,
        "advanced_mode": QueryRouteName.COMPREHENSIVE_ANALYSIS.value,
        "coverage_report": coverage,
        "steps": [
            {"index": 1, "type": "scan_private_contact_metadata", "evidence_count": len(all_items)},
            {"index": 2, "type": "rank_contacts_by_coverage", "evidence_count": len(contacts)},
            {"index": 3, "type": "build_contact_overview", "evidence_count": len(citations)},
        ],
        "contact_overview": report,
    }


def _extract_private_contact_query_terms(question: str, *, full_affection_scan: bool) -> list[str]:
    if full_affection_scan:
        return list(_PRIVATE_CONTACT_AFFECTION_TERMS)
    text = _compact_query_text(question)
    terms = [term for term in _PRIVATE_CONTACT_EVENT_TERMS if term in text]
    if any(term in text for term in _PRIVATE_CONTACT_RENTAL_TERMS):
        terms.extend(term for term in _PRIVATE_CONTACT_RENTAL_TERMS if term not in terms)
    if terms:
        return terms[:12]
    for term in _extract_generic_query_terms(question):
        if len(term) >= 2 and term not in terms and term not in {"哪些人", "哪个人", "经常", "发生过"}:
            terms.append(term)
    return terms[:12]


def _private_contact_id(metadata: dict[str, Any], fallback: str) -> str:
    for key in ("username", "contact_id", "partition_id", "conversation_id", "contact_name", "name"):
        value = str(metadata.get(key) or "").strip()
        if value:
            return value
    return fallback


def _private_contact_label(metadata: dict[str, Any], text: str, contact_id: str) -> str:
    for key in ("contact_name", "remark", "nickname", "name", "username"):
        value = str(metadata.get(key) or "").strip()
        if value:
            return value
    match = re.search(r"(?:微信聊天记录|WeChat chat history)\s*[-—:：]\s*([^\n\r]{1,80})", str(text or ""), flags=re.I)
    return match.group(1).strip() if match else contact_id


def _line_matches_any_term(line: str, terms: list[str]) -> tuple[bool, list[str]]:
    folded = str(line or "").casefold()
    hits = [term for term in terms if str(term or "").casefold() in folded]
    return bool(hits), hits


def _extract_private_contact_evidence(
    *,
    text: str,
    metadata: dict[str, Any],
    chunk_id: str,
    contact_id: str,
    terms: list[str],
) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    if not lines and str(text or "").strip():
        lines = [str(text).strip()]
    for line_index, line in enumerate(lines, start=1):
        matched, hit_terms = _line_matches_any_term(line, terms)
        if not matched:
            continue
        evidence.append(
            {
                "contact_id": contact_id,
                "contact_name": _private_contact_label(metadata, text, contact_id),
                "username": str(metadata.get("username") or "").strip(),
                "date": _extract_line_date(line, metadata),
                "sender": _extract_line_sender(line, metadata),
                "chunk_id": str(metadata.get("chunk_id") or chunk_id or ""),
                "message_id": _metadata_text(
                    metadata,
                    ("message_id", "msg_id", "id", "record_id", "chroma_id"),
                    default=f"{chunk_id}#line-{line_index}",
                ),
                "line_index": line_index,
                "hit_terms": hit_terms,
                "text": line,
                "source": _metadata_text(metadata, ("source_file", "filename", "source")),
            }
        )
    return evidence


def _format_private_contact_analysis_answer(report: dict[str, Any]) -> str:
    coverage = report["coverage_report"]
    contacts = report["contacts"]
    lines = [
        "Result:",
        (
            f"- Scanned {coverage['private_contact_count']} private contact(s) across "
            f"{coverage['scanned_chunks']} chunk(s); {coverage['candidate_contact_count']} contact(s) have matching original-text evidence."
        ),
        "- This result is based on a full private-contact scan, not only top-k chunks.",
        "",
        "Contact evidence:",
    ]
    candidates = [item for item in contacts if item.get("evidence_count", 0) > 0]
    if not candidates:
        lines.append("- No private contact has matching original-text evidence for the requested terms.")
    for index, contact in enumerate(candidates[:50], start=1):
        lines.extend(
            [
                f"{index}. {contact.get('contact_name') or contact.get('contact_id')}",
                f"   - username: {contact.get('username') or 'unknown'}",
                f"   - judgement: {contact.get('judgement')}",
                f"   - evidence_count: {contact.get('evidence_count')}",
            ]
        )
        for row in contact.get("evidence", [])[:5]:
            lines.append(
                "   - {date} | {sender} | message_id={message_id} | chunk_id={chunk_id}: {text} [{citation}]".format(
                    date=row.get("date") or "unknown date",
                    sender=row.get("sender") or "unknown sender",
                    message_id=row.get("message_id") or "-",
                    chunk_id=row.get("chunk_id") or "-",
                    text=row.get("text") or "",
                    citation=row.get("citation_id") or "",
                )
            )
    lines.extend(
        [
            "",
            "Why other contacts are not counted:",
            "- contacts without matching original-text evidence are not counted as candidates.",
            "- group chats, official accounts, system notices, and File Transfer Assistant are excluded before judgement.",
        ]
    )
    return "\n".join(lines)


def _run_private_contact_comprehensive_analysis(
    *,
    text_retriever: _QueryCollectionTextRetriever,
    collection_name: str,
    question: str,
) -> dict[str, Any]:
    all_items = text_retriever.scan_all(limit=0)
    full_affection_scan = _is_private_contact_full_scan_question(question)
    terms = _extract_private_contact_query_terms(question, full_affection_scan=full_affection_scan)
    contacts: dict[str, dict[str, Any]] = {}
    excluded_reasons: dict[str, int] = {}
    evidence_rows: list[dict[str, Any]] = []

    for raw_index, item in enumerate(all_items, start=1):
        metadata = dict(item.get("metadata") or {}) if isinstance(item, dict) else {}
        text = str(item.get("text") or "")
        excluded, reason = _metadata_is_excluded_contact(metadata)
        if excluded:
            excluded_reasons[reason or "excluded"] = excluded_reasons.get(reason or "excluded", 0) + 1
            continue
        if not _metadata_is_private_contact(metadata, text):
            excluded_reasons["non_private_chat"] = excluded_reasons.get("non_private_chat", 0) + 1
            continue
        chunk_id = str(item.get("id") or metadata.get("chunk_id") or raw_index)
        contact_id = _private_contact_id(metadata, fallback=f"contact:{raw_index}")
        contact = contacts.setdefault(
            contact_id,
            {
                "contact_id": contact_id,
                "contact_name": _private_contact_label(metadata, text, contact_id),
                "remark": str(metadata.get("remark") or "").strip(),
                "username": str(metadata.get("username") or "").strip(),
                "chunk_count": 0,
                "message_count": 0,
                "evidence": [],
            },
        )
        contact["chunk_count"] += 1
        try:
            contact["message_count"] = max(
                int(contact.get("message_count") or 0),
                int(metadata.get("message_count") or 0),
            )
        except (TypeError, ValueError):
            pass
        contact["evidence"].extend(
            _extract_private_contact_evidence(
                text=text,
                metadata=metadata,
                chunk_id=chunk_id,
                contact_id=contact_id,
                terms=terms,
            )
        )

    citation_rank = 1
    normalized_contacts: list[dict[str, Any]] = []
    for contact in contacts.values():
        deduped: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()
        for row in contact["evidence"]:
            key = (str(row.get("contact_id") or ""), str(row.get("message_id") or ""), str(row.get("text") or ""))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(row)
        deduped.sort(key=lambda row: (-len(row.get("hit_terms") or []), str(row.get("date") or ""), int(row.get("line_index") or 0)))
        normalized_evidence: list[dict[str, Any]] = []
        for row in deduped:
            row = {**row, "citation_id": f"T{citation_rank}"}
            citation_rank += 1
            normalized_evidence.append(row)
            evidence_rows.append(row)
        normalized_contacts.append(
            {
                **{key: value for key, value in contact.items() if key != "evidence"},
                "judgement": "has_matching_evidence" if normalized_evidence else "no_matching_evidence",
                "evidence_count": len(normalized_evidence),
                "evidence": normalized_evidence,
                "evidence_truncated": len(normalized_evidence) > 5,
            }
        )

    normalized_contacts.sort(key=lambda item: (-int(item.get("evidence_count") or 0), str(item.get("contact_name") or "")))
    analysis_type = "private_contact_affection_evidence_sweep" if full_affection_scan else "private_contact_term_evidence_sweep"
    source_type = "text_full_contact_scan" if full_affection_scan else "text_full_contact_term_scan"
    coverage = {
        "analysis_type": analysis_type,
        "collection": collection_name,
        "top_k_used": False,
        "scanned_chunks": len(all_items),
        "private_contact_count": len(normalized_contacts),
        "contacts_analyzed": len(normalized_contacts),
        "candidate_contact_count": sum(1 for item in normalized_contacts if int(item.get("evidence_count") or 0) > 0),
        "contacts_without_evidence_count": sum(1 for item in normalized_contacts if int(item.get("evidence_count") or 0) <= 0),
        "excluded_reasons": excluded_reasons,
        "query_terms": terms,
    }
    citations = [
        {
            "id": row["citation_id"],
            "source_type": source_type,
            "rank": index,
            "text": row["text"],
            "source": row.get("source"),
            "metadata": {
                "contact_id": row.get("contact_id"),
                "contact_name": row.get("contact_name"),
                "username": row.get("username"),
                "date": row.get("date"),
                "sender": row.get("sender"),
                "chunk_id": row.get("chunk_id"),
                "message_id": row.get("message_id"),
                "hit_terms": row.get("hit_terms") or [],
                "retrieval_path": analysis_type,
            },
            "raw_id": row.get("message_id") or row.get("chunk_id"),
        }
        for index, row in enumerate(evidence_rows, start=1)
    ]
    report = {
        "question": question,
        "collection": collection_name,
        "coverage_report": coverage,
        "contacts": normalized_contacts,
    }
    context = "\n\n".join(
        [
            "## Private contact full scan coverage",
            orjson.dumps(coverage, option=orjson.OPT_INDENT_2).decode("utf-8"),
            "## Contacts",
            orjson.dumps(normalized_contacts, option=orjson.OPT_INDENT_2).decode("utf-8"),
        ]
    )
    return {
        "question": question,
        "answer": _format_private_contact_analysis_answer(report),
        "context": context,
        "citations": citations,
        "evidence": citations,
        "context_only": False,
        "prompt": None,
        "task_spec": {
            "original_question": question,
            "rewritten_question": question,
            "intent": "comprehensive",
            "route": QueryRouteName.COMPREHENSIVE_ANALYSIS.value,
            "objects": ["private_contacts"],
            "evidence_requirements": {
                "must_cite": True,
                "require_source_span": True,
                "no_evidence_policy": "return_insufficient_evidence",
                "coverage_report": True,
                "min_sources": 1,
            },
            "output_contract": {
                "format": "private_contact_evidence_ledger",
                "include_citations": True,
                "include_uncertainty": True,
            },
            "requires_planning": True,
            "route_reason": "deterministic private-contact full scan",
        },
        "advanced_mode": QueryRouteName.COMPREHENSIVE_ANALYSIS.value,
        "steps": [
            {"index": 1, "type": "detect_private_contact_collection", "evidence_count": len(all_items)},
            {"index": 2, "type": "scan_all_private_contact_chunks", "evidence_count": coverage["private_contact_count"]},
            {"index": 3, "type": "build_contact_evidence_ledger", "evidence_count": len(citations)},
        ],
        "coverage_report": coverage,
        "comparison_table": [],
        "analysis_profile": {
            "profile_id": "private_contact_evidence",
            "analysis_type": analysis_type,
            "partition_key": "contact_id",
            "query_terms": terms,
        },
        "contact_analysis": report,
        "partition_analysis": report,
    }


_IDENTITY_METADATA_KEYS = (
    "owner_name",
    "account_owner",
    "self_name",
    "me_name",
    "my_name",
    "local_name",
    "account_name",
    "current_user",
    "current_username",
    "wx_owner",
    "wechat_owner",
    "profile_name",
)

_IDENTITY_EXCLUDED_NAMES = {
    "",
    "我",
    "本人",
    "号主",
    "对方",
    "系统",
    "unknown",
    "unknown sender",
    "文件传输助手",
    "filehelper",
}
_IDENTITY_SCAN_LIMIT = 5000


def _clean_identity_candidate(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip(" \t\r\n:：-—")
    text = re.sub(r"^.*?[:：]\s*\[合并转发\]\s*", "", text).strip()
    text = re.sub(r"^\[合并转发\]\s*", "", text).strip()
    text = re.sub(r"(?:的)?聊天记录$", "", text).strip()
    if not text or len(text) > 48:
        return ""
    folded = text.casefold()
    if folded in _IDENTITY_EXCLUDED_NAMES or text in _IDENTITY_EXCLUDED_NAMES:
        return ""
    if text.startswith("[") or re.fullmatch(r"\d{1,2}|\d{1,2}:\d{2}(?::\d{2})?", text):
        return ""
    structural_tokens = (
        "@chatroom",
        "filehelper",
        "公众号",
        "服务通知",
        "attachments",
        "attachment",
        "size_bytes",
        "conversation_relative_path",
        "relative_path",
        "source_file",
        "metadata",
    )
    if any(token in folded for token in structural_tokens):
        return ""
    if " / " in text or "\\" in text:
        return ""
    return text


def _add_identity_candidate(
    candidates: dict[str, dict[str, Any]],
    *,
    name: str,
    score: float,
    reason: str,
    citation_seed: dict[str, Any],
) -> None:
    cleaned = _clean_identity_candidate(name)
    if not cleaned:
        return
    candidate = candidates.setdefault(
        cleaned,
        {
            "name": cleaned,
            "score": 0.0,
            "reasons": {},
            "evidence": [],
        },
    )
    candidate["score"] += score
    candidate["reasons"][reason] = candidate["reasons"].get(reason, 0) + 1
    if len(candidate["evidence"]) < 20:
        candidate["evidence"].append({**citation_seed, "candidate": cleaned, "reason": reason, "score": score})


def _identity_candidates_from_title(text: str) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    first_lines = "\n".join(str(text or "").splitlines()[:4])
    patterns = (
        r"(?:微信聊天记录|WeChat chat history)\s*[-—:：]\s*([^\n\r]{1,48}?)\s*与\s*([^\n\r]{1,48}?)(?:的聊天记录)?(?:\s|$)",
        r"([^\n\r]{1,48}?)\s*与\s*([^\n\r]{1,48}?)(?:的聊天记录)(?:\s|$)",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, first_lines, flags=re.I):
            owner = _clean_identity_candidate(match.group(1))
            contact = _clean_identity_candidate(match.group(2))
            if owner and contact and owner != contact:
                rows.append((owner, match.group(0).strip()))
    return rows


def _identity_sender_candidates(text: str, contact_names: set[str]) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for line in str(text or "").splitlines()[:50]:
        sender = _clean_identity_candidate(_extract_identity_sender_from_chat_line(line))
        if not sender or sender in contact_names:
            continue
        rows.append((sender, line.strip()))
    return rows


def _has_strong_identity_evidence(candidate: dict[str, Any]) -> bool:
    reasons = candidate.get("reasons") or {}
    return any(str(reason).startswith("metadata:") or reason == "conversation_title_owner" for reason in reasons)


def _extract_identity_sender_from_chat_line(line: str) -> str:
    cleaned = str(line or "").strip()
    if not cleaned:
        return ""
    patterns = (
        r"^\d{4}[-/年]\d{1,2}[-/月]\d{1,2}(?:日)?\s*(?:\[\d{1,2}:\d{2}(?::\d{2})?\])?\s*([^:：]{1,40})[:：]",
        r"^\[\d{1,2}:\d{2}(?::\d{2})?\]\s*([^:：]{1,40})[:：]",
    )
    for pattern in patterns:
        match = re.match(pattern, cleaned)
        if match:
            return match.group(1).strip()
    return ""


def _format_identity_analysis_answer(report: dict[str, Any]) -> str:
    coverage = report["coverage_report"]
    top = report.get("top_candidate")
    lines = [
        "Result:",
    ]
    if top:
        lines.extend(
            [
                f"- 当前集合里，最可能的号主 / 本人是：{top['name']}",
                f"- 置信度：{report['confidence']}",
                (
                    f"- 依据：扫描了 {coverage['scanned_chunks']} 个 chunk，"
                    f"找到 {coverage['candidate_count']} 个身份候选；该候选分数最高。"
                ),
            ]
        )
    else:
        lines.extend(
            [
                "- 目前无法从当前集合确认你的真实姓名或微信昵称。",
                "- 在本系统语义里，“我”仍指当前导入聊天记录的号主 / 本人；只是缺少可追溯的原文或元数据来命名这个人。",
                (
                    f"- 已扫描 {coverage['scanned_chunks']} 个 chunk，但没有找到 owner/self 元数据，"
                    "也没有找到“X与Y的聊天记录”这类能稳定指向号主的标题。"
                ),
                (
                    f"- 发现 {coverage.get('weak_candidate_count', 0)} 个仅由发送方模式产生的弱候选，"
                    "这些不能单独作为号主姓名证据。"
                ),
            ]
        )
    lines.extend(["", "Evidence:"])
    citations = report.get("citations") or []
    if not citations:
        lines.append("- No traceable identity evidence was found in the current collection.")
    for citation in citations[:10]:
        metadata = citation.get("metadata") or {}
        lines.append(
            "- [{id}] {reason} | chunk_id={chunk_id} | source={source}: {text}".format(
                id=citation.get("id"),
                reason=metadata.get("reason") or "identity evidence",
                chunk_id=metadata.get("chunk_id") or "-",
                source=citation.get("source") or "unknown source",
                text=_citation_preview(citation.get("text"), limit=180),
            )
        )
    lines.extend(
        [
            "",
            "Fallback rule:",
            "- 如果身份证据不足，系统必须返回“不足证据”的近似回答，而不是继续卡在 GraphRAG 或社区摘要路径。",
        ]
    )
    return "\n".join(lines)


def _run_self_identity_analysis(
    *,
    text_retriever: _QueryCollectionTextRetriever,
    collection_name: str,
    question: str,
) -> dict[str, Any]:
    all_items = text_retriever.scan_all(limit=_IDENTITY_SCAN_LIMIT)
    candidates: dict[str, dict[str, Any]] = {}
    contact_names: set[str] = set()

    for item in all_items:
        metadata = dict(item.get("metadata") or {}) if isinstance(item, dict) else {}
        for key in ("contact_name", "remark", "nickname", "name", "username"):
            value = _clean_identity_candidate(metadata.get(key))
            if value:
                contact_names.add(value)

    for raw_index, item in enumerate(all_items, start=1):
        metadata = dict(item.get("metadata") or {}) if isinstance(item, dict) else {}
        text = str(item.get("text") or "")
        chunk_id = str(item.get("id") or metadata.get("chunk_id") or raw_index)
        source = (
            item.get("source")
            or metadata.get("source_file")
            or metadata.get("source")
            or metadata.get("filename")
            or metadata.get("file")
        )
        seed = {
            "chunk_id": chunk_id,
            "source": source,
            "text": "",
            "metadata": metadata,
        }
        for key in _IDENTITY_METADATA_KEYS:
            value = metadata.get(key)
            if value:
                _add_identity_candidate(
                    candidates,
                    name=str(value),
                    score=12.0,
                    reason=f"metadata:{key}",
                    citation_seed={**seed, "text": f"{key}={value}"},
                )

        searchable_title_text = "\n".join(
            str(value or "")
            for value in (
                text,
                metadata.get("title"),
                metadata.get("source_file"),
                metadata.get("filename"),
                metadata.get("conversation_title"),
            )
        )
        for owner, matched_text in _identity_candidates_from_title(searchable_title_text):
            _add_identity_candidate(
                candidates,
                name=owner,
                score=6.0,
                reason="conversation_title_owner",
                citation_seed={**seed, "text": matched_text},
            )

        current_contact_names = {
            _clean_identity_candidate(metadata.get(key))
            for key in ("contact_name", "remark", "nickname", "name", "username")
        }
        current_contact_names = {name for name in current_contact_names if name}
        for sender, line in _identity_sender_candidates(text, current_contact_names):
            _add_identity_candidate(
                candidates,
                name=sender,
                score=1.0,
                reason="message_sender_not_current_contact",
                citation_seed={**seed, "text": line},
            )

    ranked = sorted(
        candidates.values(),
        key=lambda item: (
            -float(item.get("score") or 0.0),
            -sum(int(count) for count in (item.get("reasons") or {}).values()),
            str(item.get("name") or ""),
        ),
    )
    strong_ranked = [item for item in ranked if _has_strong_identity_evidence(item)]
    top = strong_ranked[0] if strong_ranked else None
    confidence = "insufficient"
    if top:
        score = float(top.get("score") or 0.0)
        reasons = top.get("reasons") or {}
        if score >= 18 or int(reasons.get("metadata:owner_name") or 0) > 0 or int(reasons.get("metadata:account_owner") or 0) > 0:
            confidence = "high"
        elif score >= 6:
            confidence = "medium"
        else:
            confidence = "low"

    evidence_rows = list((top or {}).get("evidence") or []) if top else []
    citations = [
        {
            "id": f"T{index}",
            "source_type": "text_identity_scan",
            "rank": index,
            "text": str(row.get("text") or ""),
            "source": row.get("source"),
            "score": row.get("score"),
            "metadata": {
                "candidate": row.get("candidate"),
                "reason": row.get("reason"),
                "chunk_id": row.get("chunk_id"),
                "retrieval_path": "self_identity_scan",
            },
            "raw_id": row.get("chunk_id"),
        }
        for index, row in enumerate(evidence_rows, start=1)
    ]
    coverage = {
        "analysis_type": "self_identity_scan",
        "collection": collection_name,
        "top_k_used": False,
        "scanned_chunks": len(all_items),
        "candidate_count": len(ranked),
        "strong_candidate_count": len(strong_ranked),
        "weak_candidate_count": max(0, len(ranked) - len(strong_ranked)),
        "evidence_count": len(citations),
        "identity_metadata_keys": list(_IDENTITY_METADATA_KEYS),
        "scan_limit": _IDENTITY_SCAN_LIMIT,
    }
    report = {
        "question": question,
        "collection": collection_name,
        "coverage_report": coverage,
        "top_candidate": {"name": top["name"], "score": top["score"], "reasons": top["reasons"]} if top else None,
        "confidence": confidence,
        "candidates": [
            {
                "name": item["name"],
                "score": item["score"],
                "reasons": item["reasons"],
                "evidence_count": len(item.get("evidence") or []),
            }
            for item in ranked[:20]
        ],
        "citations": citations,
    }
    context = "\n\n".join(
        [
            "## Self identity scan coverage",
            orjson.dumps(coverage, option=orjson.OPT_INDENT_2).decode("utf-8"),
            "## Identity candidates",
            orjson.dumps(report["candidates"], option=orjson.OPT_INDENT_2).decode("utf-8"),
        ]
    )
    return {
        "question": question,
        "answer": _format_identity_analysis_answer(report),
        "context": context,
        "citations": citations,
        "evidence": citations,
        "context_only": False,
        "prompt": None,
        "task_spec": {
            "original_question": question,
            "rewritten_question": question,
            "intent": "identity",
            "route": QueryRouteName.COMPREHENSIVE_ANALYSIS.value,
            "objects": ["account_owner"],
            "evidence_requirements": {
                "must_cite": True,
                "require_source_span": True,
                "no_evidence_policy": "return_insufficient_evidence",
                "coverage_report": True,
            },
            "output_contract": {
                "format": "identity_evidence_ledger",
                "include_citations": True,
                "include_uncertainty": True,
            },
            "requires_planning": False,
            "route_reason": "deterministic self-identity scan over imported chat records",
        },
        "advanced_mode": QueryRouteName.COMPREHENSIVE_ANALYSIS.value,
        "steps": [
            {"index": 1, "type": "scan_all_chunks_for_identity_markers", "evidence_count": len(all_items)},
            {"index": 2, "type": "rank_identity_candidates", "evidence_count": len(ranked)},
            {"index": 3, "type": "build_identity_evidence_ledger", "evidence_count": len(citations)},
        ],
        "coverage_report": coverage,
        "identity_analysis": report,
    }


def _resolve_first_nonempty_collection(persist_dir: Path) -> str | None:
    for item in _list_nonempty_collections_direct(persist_dir):
        return item["name"]
    return None


def _collection_count_direct(persist_dir: Path, collection_name: str) -> int | None:
    name = str(collection_name or "").strip()
    if not name:
        return None
    client = _create_client(persist_dir)
    try:
        collection = client.get_collection(name=name)
        return int(collection.count())
    except Exception:
        return None
    finally:
        _close_client(client)


def _list_nonempty_collections_direct(persist_dir: Path) -> list[dict[str, Any]]:
    client = _create_client(persist_dir)
    try:
        rows: list[dict[str, Any]] = []
        for raw_collection in client.list_collections():
            name = str(getattr(raw_collection, "name", raw_collection) or "").strip()
            if not name:
                continue
            try:
                collection = raw_collection if callable(getattr(raw_collection, "count", None)) else client.get_collection(name=name)
                count = int(collection.count())
            except Exception:
                continue
            if count > 0:
                rows.append({"name": name, "count": count})
        rows.sort(key=lambda item: (0 if _collection_name_looks_like_chat(item["name"]) else 1, item["name"]))
        return rows
    finally:
        _close_client(client)


def _collection_name_looks_like_chat(collection_name: str) -> bool:
    text = str(collection_name or "").casefold()
    return any(marker in text for marker in ("wechat", "weixin", "private", "chat", "微信", "聊天", "私聊"))


def _question_looks_like_chat_record_query(question: str) -> bool:
    text = _compact_query_text(question)
    return _is_self_identity_question(question) or any(
        marker in text
        for marker in (
            "聊天记录",
            "微信",
            "私聊",
            "联系人",
            "号主",
            "身份",
            "我是谁",
            "和我",
            "我和",
        )
    )


def _resolve_query_collection_name(
    persist_dir: Path,
    *,
    requested_collection: str,
    question: str,
) -> tuple[str | None, dict[str, Any]]:
    requested = str(requested_collection or "").strip()
    resolution: dict[str, Any] = {
        "requested_collection": requested,
        "resolved_collection": None,
        "reason": "no_collection_requested",
        "requested_count": None,
        "fallback_count": None,
    }
    requested_count = _collection_count_direct(persist_dir, requested) if requested else None
    resolution["requested_count"] = requested_count
    if requested and requested_count and requested_count > 0:
        resolution.update(
            {
                "resolved_collection": requested,
                "reason": "requested_collection_nonempty",
                "fallback_count": requested_count,
            }
        )
        return requested, resolution

    nonempty = _list_nonempty_collections_direct(persist_dir)
    if not nonempty:
        if requested:
            resolution["reason"] = "requested_collection_empty_no_fallback" if requested_count == 0 else "requested_collection_missing_no_fallback"
            resolution["resolved_collection"] = requested
            resolution["fallback_count"] = requested_count
            return requested, resolution
        return None, resolution

    prefer_chat = _question_looks_like_chat_record_query(question)
    fallback = None
    if prefer_chat:
        fallback = next((item for item in nonempty if _collection_name_looks_like_chat(item["name"])), None)
    fallback = fallback or nonempty[0]
    if requested:
        reason = "requested_collection_empty" if requested_count == 0 else "requested_collection_missing"
    elif prefer_chat and _collection_name_looks_like_chat(fallback["name"]):
        reason = "auto_selected_chat_collection"
    else:
        reason = "auto_selected_first_nonempty_collection"
    resolution.update(
        {
            "resolved_collection": fallback["name"],
            "reason": reason,
            "fallback_count": fallback["count"],
            "available_nonempty_collections": nonempty[:10],
        }
    )
    return fallback["name"], resolution


def _resolve_optional_graph_db_path(request: Request, raw_path: str) -> Path | None:
    raw_path = (raw_path or "").strip()
    candidates: list[Path] = []
    if raw_path:
        from .routes_graphrag import _resolve_graph_db_path

        return _resolve_graph_db_path(request, raw_path)

    for candidate in (
        request.app.state.persist_dir / "graph_store.sqlite",
        request.app.state.persist_dir / "graph_store.sqlite3",
        request.app.state.upload_dir / "graph_store.sqlite",
        request.app.state.upload_dir / "graph_store.sqlite3",
    ):
        candidates.append(Path(candidate))
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate.resolve()
    return None


def _build_optional_search_graph_retriever(request: Request, raw_path: str):
    if not (raw_path or "").strip():
        return None
    graph_path = _resolve_optional_graph_db_path(request, raw_path)
    if graph_path is None:
        return None
    graph_store = GraphStore(graph_path)
    graph_store.initialize(reset=False)
    return SQLiteGraphRetriever(graph_store, include_community_summaries=True)


def _build_query_llm(payload: UnifiedQueryRequest):
    if not payload.llm_api_key.strip():
        return None
    client = OpenAICompatibleLLMClient(
        api_key=payload.llm_api_key.strip(),
        base_url=(payload.llm_base_url or "https://api.openai.com/v1").strip(),
        model=(payload.llm_model or "gpt-4.1-mini").strip(),
        timeout=payload.llm_timeout_seconds,
    )
    return _ConfiguredLLMClient(
        client,
        temperature=payload.temperature,
        max_tokens=payload.max_tokens,
    )


class SearchRequest(BaseModel):
    collection: str = "power_equipment"
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=100)
    query_rewrite: bool | None = None
    reranker: str | None = Field(default=None, pattern="^(none|noop|cross_encoder)$")
    graph_db_path: str = ""
    filters: dict[str, Any] | None = None
    no_answer_min_score: float | None = Field(default=None, ge=0)
    no_answer_min_results: int | None = Field(default=None, ge=1)


class RetrievalPolicyPromotionRequest(BaseModel):
    collection: str = "power_equipment"
    settings: dict[str, Any] = Field(default_factory=dict)
    reviewer: str = ""
    review_note: str = ""
    source_report: str = ""


class RetrievalPolicyProposalRequest(BaseModel):
    collection: str = "power_equipment"
    settings: dict[str, Any] = Field(default_factory=dict)
    reviewer: str = ""
    reviewer_role: str = ""
    review_note: str = ""
    source_report: str = ""
    assigned_to: str = ""
    due_at: str = ""


class RetrievalPolicyNotificationDispatchRequest(BaseModel):
    recipient: str = ""
    status: str = "pending"
    delivery_mode: str = Field(default="outbox_file", pattern="^(outbox_file|webhook|smtp)$")
    outbox_path: str = ""
    webhook_url: str = ""
    webhook_timeout_seconds: float = Field(default=5.0, gt=0, le=30)
    webhook_template: str = Field(
        default="generic",
        pattern="^(generic|lark_text|dingtalk_text|wecom_text|pagerduty_event_v2|opsgenie_alert)$",
    )
    webhook_signing_secret_env: str = ""
    webhook_routing_key_env: str = ""
    webhook_auth_header_name: str = ""
    webhook_auth_token_env: str = ""
    webhook_auth_scheme: str = ""
    smtp_host: str = ""
    smtp_port: int = Field(default=25, ge=1, le=65535)
    smtp_from: str = ""
    smtp_to: str = ""
    smtp_subject: str = "RAG retrieval policy review notification"
    smtp_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    smtp_use_tls: bool = True
    smtp_username_env: str = ""
    smtp_password_env: str = ""
    dispatched_by: str = ""


class RetrievalPolicyApprovalRequest(BaseModel):
    proposal_id: str = Field(min_length=1)
    approver: str = ""
    approver_role: str = ""
    approval_note: str = ""


class RetrievalPolicyRejectionRequest(BaseModel):
    proposal_id: str = Field(min_length=1)
    approver: str = ""
    approver_role: str = ""
    rejection_note: str = ""


class RetrievalPolicyRoleUpsertRequest(BaseModel):
    subject: str = Field(min_length=1)
    roles: list[str] = Field(default_factory=list)
    assigned_collections: list[str] = Field(default_factory=list)
    updated_by: str = ""
    note: str = ""


class RetrievalPolicyNotificationRecipientUpsertRequest(BaseModel):
    subject: str = Field(min_length=1)
    email: str = ""
    webhook_url: str = ""
    webhook_template: str = Field(
        default="",
        pattern="^(|generic|lark_text|dingtalk_text|wecom_text|pagerduty_event_v2|opsgenie_alert)$",
    )
    webhook_signing_secret_env: str = ""
    webhook_routing_key_env: str = ""
    webhook_auth_header_name: str = ""
    webhook_auth_token_env: str = ""
    webhook_auth_scheme: str = ""
    preferred_delivery_mode: str = Field(default="", pattern="^(|smtp|webhook|outbox_file)$")
    updated_by: str = ""
    note: str = ""


class RetrievalPolicyDirectorySyncRequest(BaseModel):
    source_type: str = Field(default="scim", pattern="^(scim|directory_json)$")
    users: list[dict[str, Any]] = Field(default_factory=list)
    groups: list[dict[str, Any]] = Field(default_factory=list)
    role_group_mappings: dict[str, Any] = Field(default_factory=dict)
    recipient_defaults: dict[str, Any] = Field(default_factory=dict)
    updated_by: str = ""
    note: str = ""
    dry_run: bool = False


class RetrievalPolicyIdentityProviderUpsertRequest(BaseModel):
    provider: str = Field(default="oidc", pattern="^oidc$")
    enabled: bool = False
    issuer: str = ""
    audience: str = ""
    jwks_url: str = ""
    authorization_endpoint: str = ""
    token_endpoint: str = ""
    client_id: str = ""
    client_secret_env: str = ""
    redirect_uri: str = ""
    scopes: list[str] = Field(default_factory=lambda: ["openid", "email", "profile"])
    subject_claim: str = "email"
    groups_claim: str = "groups"
    algorithms: list[str] = Field(default_factory=lambda: ["RS256"])
    updated_by: str = ""
    note: str = ""


class RetrievalPolicyIdentityProviderLoginUrlRequest(BaseModel):
    redirect_uri: str = ""
    state: str = ""
    nonce: str = ""


class RetrievalPolicyIdentityProviderTokenRequest(BaseModel):
    code: str = Field(min_length=1)
    code_verifier: str = Field(min_length=1)
    redirect_uri: str = ""


class RetrievalPolicyRollbackRequest(BaseModel):
    collection: str = "power_equipment"
    reviewer: str = ""
    review_note: str = ""


class UnifiedQueryRequest(BaseModel):
    question: str = Field(min_length=1)
    collection: str = ""
    top_k: int = Field(default=8, ge=1, le=100)
    mode: str = Field(default="auto", pattern="^(auto|vector|local|global|aggregation)$")
    graph_db_path: str = ""
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4.1-mini"
    temperature: float = Field(default=0.7, ge=0, le=2)
    max_tokens: int = Field(default=8192, ge=64, le=131072)
    llm_timeout_seconds: float = Field(default=20.0, gt=0, le=60)
    global_community_limit: int = Field(default=12, ge=1, le=30)
    context_only: bool = False
    allow_unsafe_graph: bool = False


class BenchmarkRequest(BaseModel):
    collection: str = "benchmark_power_equipment"
    document_count: int = Field(default=500, ge=50, le=5000)
    batch_size: int = Field(default=100, ge=10, le=1000)
    query_count: int = Field(default=50, ge=10, le=1000)
    top_k: int = Field(default=5, ge=1, le=100)
    backend: str = "sentence-transformer"
    model_name: str | None = DEFAULT_SENTENCE_TRANSFORMER_MODEL
    cleanup: bool = True


class ProcessRequest(BaseModel):
    filenames: list[str] = Field(default_factory=list)
    collection: str = "power_equipment"
    parser_backend: str = Field(default="auto", pattern="^(auto|native|deepdoc|mineru|docling|unstructured)$")


class PublicBooksJsonIngestRequest(BaseModel):
    input_dir: str = Field(min_length=1)
    collection: str = "public_books_labelstudio"
    mode: str = Field(default="append", pattern="^(create|append)$")
    chunk_size: int = Field(default=900, ge=100, le=4000)
    overlap: int = Field(default=120, ge=0, le=1000)


class DeleteUploadsRequest(BaseModel):
    filenames: list[str] = Field(default_factory=list)
    purge_vectors: bool = False


def create_app(
    persist_dir: Path = DEFAULT_PERSIST_DIR,
    upload_dir: Path = DEFAULT_UPLOAD_DIR,
    log_dir: Path | None = None,
    frontend_dir: Path | str | None = None,
    deliverables_dir: Path | str | None = None,
    cors_origins: list[str] | tuple[str, ...] | None = None,
) -> FastAPI:
    resolved_frontend_dir = Path(frontend_dir) if frontend_dir is not None else _resolve_frontend_dir()
    resolved_deliverables_dir = Path(deliverables_dir) if deliverables_dir is not None else DEFAULT_DELIVERABLES_DIR
    allowed_cors_origins = list(cors_origins) if cors_origins is not None else _configured_cors_origins()

    app = FastAPI(
        title="Power Equipment Knowledge Base Console",
        description="File upload, vector indexing, ChromaDB management, hybrid retrieval, and RAG answering.",
        version="2.1.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_cors_origins,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Accept", "Authorization", "Content-Type", "Origin"],
    )

    app.state.persist_dir = Path(persist_dir)
    app.state.upload_dir = Path(upload_dir)
    app.state.log_dir = Path(log_dir) if log_dir else (
        DEFAULT_LOG_DIR if Path(upload_dir) == DEFAULT_UPLOAD_DIR else Path(upload_dir).parent / "logs"
    )
    app.state.persist_dir.mkdir(parents=True, exist_ok=True)
    app.state.upload_dir.mkdir(parents=True, exist_ok=True)
    app.state.log_dir.mkdir(parents=True, exist_ok=True)
    app.state.memory_db_path = app.state.persist_dir / "memory" / "conversation_memory.sqlite3"
    memory_vector_dir = os.environ.get("RAG_MEMORY_VECTOR_DIR", "").strip()
    app.state.memory_vector_persist_dir = Path(memory_vector_dir) if memory_vector_dir else None
    if app.state.memory_vector_persist_dir:
        app.state.memory_vector_persist_dir.mkdir(parents=True, exist_ok=True)

    # Register modular GraphRAG routes (community detection, global search, etc.)
    try:
        from .routes_graphrag import router as graphrag_router
        app.include_router(graphrag_router)
    except ImportError:
        pass  # Gracefully skip if root-level modules are not available

    try:
        from .routes_memory import router as memory_router
        app.include_router(memory_router)
    except ImportError:
        pass

    @app.get("/")
    async def index():
        if resolved_frontend_dir is None:
            return JSONResponse({"message": "?frontend/index.html"}, status_code=404)
        index_path = resolved_frontend_dir / "index.html"
        if index_path.exists():
            return FileResponse(
                index_path,
                media_type="text/html; charset=utf-8",
                headers={"Cache-Control": "no-store, max-age=0"},
            )
        return JSONResponse({"message": "?frontend/index.html"}, status_code=404)

    @app.get("/api/health")
    async def health():
        return {"status": "ok", "version": "2.1.0"}

    @app.post("/api/upload")
    async def upload_file(
        request: Request,
        file: UploadFile = File(...),
        relative_path: str | None = Form(default=None),
    ):
        source_name = Path(file.filename or "upload.bin").name
        logger = OperationLogger(
            request.app.state.log_dir,
            "upload",
            source_file=source_name,
            relative_path=relative_path,
        )
        try:
            display_name = relative_path.strip() if relative_path and relative_path.strip() else source_name
            stored_name = _safe_upload_name(display_name)
            if not is_supported_source(source_name) or not is_supported_source(stored_name):
                logger.warning(
                    "upload_unsupported_type",
                    source_file=source_name,
                    stored_name=stored_name,
                    supported_extensions=SUPPORTED_EXTENSIONS_LABEL,
                )
                raise HTTPException(
                    status_code=400,
                    detail=f"? {SUPPORTED_EXTENSIONS_LABEL}? {logger.file_name}",
                )

            with logger.stage("read_upload_stream", source_file=source_name):
                content = await file.read()
            if not content:
                logger.warning("upload_empty_file", source_file=source_name)
                raise HTTPException(status_code=400, detail=f"? {logger.file_name}")

            save_path = request.app.state.upload_dir / stored_name
            with logger.stage(
                "save_upload_file",
                source_file=source_name,
                stored_name=stored_name,
                size_bytes=len(content),
                size_mb=round(len(content) / (1024 * 1024), 3),
            ):
                save_path.write_bytes(content)
            _update_upload_entry(
                request.app.state.upload_dir,
                stored_name,
                display_name=display_name,
                status="uploaded",
                uploaded_at=time.time(),
                processed_at=None,
                source_kind=get_source_kind(stored_name),
                last_collection=None,
                last_records=0,
                last_chunks=0,
                last_error=None,
                last_log_file=logger.file_name,
            )

            response = {
                "status": "ok",
                "filename": stored_name,
                "display_name": display_name,
                "size_kb": round(len(content) / 1024, 1),
                "source_kind": get_source_kind(stored_name),
                **_operation_log_payload(logger),
            }
            logger.close(status="ok", stored_name=stored_name, size_bytes=len(content))
            return response
        except HTTPException as exc:
            logger.error("upload_rejected", status_code=exc.status_code, detail=exc.detail)
            logger.close(status="error", status_code=exc.status_code, detail=exc.detail)
            raise
        except Exception as exc:
            logger.exception("upload_failed", exc, source_file=source_name)
            logger.close(status="error", error=str(exc))
            raise HTTPException(status_code=500, detail=f": {exc}? {logger.file_name}") from exc

    @app.get("/api/uploads")
    async def list_uploads(request: Request):
        files = _collect_upload_entries(request.app.state.upload_dir)
        pending = [item for item in files if item.get("status") != "processed"]
        processed = [item for item in files if item.get("status") == "processed"]
        return {
            "files": files,
            "pending": pending,
            "processed": processed,
            "count": len(files),
            "pending_count": len(pending),
            "processed_count": len(processed),
        }

    @app.get("/api/logs")
    async def list_logs(request: Request, limit: int = 50):
        _enforce_log_same_origin(request)
        limit = max(1, min(int(limit), 200))
        return {"logs": _list_operation_logs(request.app.state.log_dir, limit=limit)}

    @app.get("/api/logs/{filename}")
    async def read_log(request: Request, filename: str):
        _enforce_log_same_origin(request)
        log_path = _resolve_log_path(request.app.state.log_dir, filename)
        return FileResponse(log_path, media_type="text/plain; charset=utf-8")

    @app.get("/api/logs/{filename}/progress")
    async def read_log_progress(request: Request, filename: str, recent_limit: int = 40):
        _enforce_log_same_origin(request)
        log_path = _resolve_log_path(request.app.state.log_dir, filename)
        return _operation_log_progress(log_path, recent_limit=recent_limit)

    @app.delete("/api/uploads/{filename}")
    async def delete_upload(request: Request, filename: str, purge_vectors: bool = False):
        stored_name, fpath = _resolve_upload_path(request.app.state.upload_dir, filename)
        manifest = _read_upload_manifest(request.app.state.upload_dir)
        if not fpath.exists() and stored_name not in manifest:
            raise HTTPException(status_code=404, detail="upload not found")

        purge_result = {"chunks_deleted": 0, "collections": {}}
        if purge_vectors:
            purge_result = _purge_vectors_by_source_files(request.app.state.persist_dir, [stored_name])

        if fpath.exists():
            fpath.unlink()
        _remove_upload_entries(request.app.state.upload_dir, [stored_name])
        return {"status": "ok", "deleted": stored_name, **purge_result}

    @app.post("/api/uploads/delete")
    async def delete_uploads(request: Request, payload: DeleteUploadsRequest):
        resolved = [
            _resolve_upload_path(request.app.state.upload_dir, name)
            for name in payload.filenames
            if str(name).strip()
        ]
        if not resolved:
            raise HTTPException(status_code=400, detail="request failed")
        filenames = [name for name, _ in resolved]

        purge_result = {"chunks_deleted": 0, "collections": {}}
        if payload.purge_vectors:
            purge_result = _purge_vectors_by_source_files(request.app.state.persist_dir, filenames)

        deleted: list[str] = []
        for filename, fpath in resolved:
            if fpath.exists():
                fpath.unlink()
            deleted.append(filename)

        _remove_upload_entries(request.app.state.upload_dir, deleted)
        return {"status": "ok", "deleted": deleted, **purge_result}

    @app.post("/api/process")
    async def process_files(
        request: Request,
        payload: ProcessRequest | None = None,
        mode: str = "replace",
    ):
        del mode  # ?replace/append

        entries = _collect_upload_entries(request.app.state.upload_dir)
        by_name = {entry["filename"]: entry for entry in entries}
        requested = [str(name).strip() for name in (payload.filenames if payload else []) if str(name).strip()]
        collection_name = (payload.collection if payload else "power_equipment").strip() or "power_equipment"
        parser_backend = (payload.parser_backend if payload else "auto").strip() or "auto"

        if requested:
            selected_entries = [
                by_name[name]
                for name in requested
                if name in by_name and by_name[name].get("status") != "processed"
            ]
            skipped_processed = [
                name
                for name in requested
                if name in by_name and by_name[name].get("status") == "processed"
            ]
        else:
            selected_entries = [entry for entry in entries if entry.get("status") != "processed"]
            skipped_processed = []

        logger = OperationLogger(
            request.app.state.log_dir,
            "process",
            collection_name=collection_name,
            requested_filenames=requested,
        )
        t0 = time.time()
        try:
            selected_names = [str(entry["filename"]) for entry in selected_entries]
            upload_files = [
                request.app.state.upload_dir / entry["filename"]
                for entry in selected_entries
                if (request.app.state.upload_dir / entry["filename"]).exists()
            ]
            missing_files = [
                name
                for name in selected_names
                if not (request.app.state.upload_dir / name).exists()
            ]
            logger.info(
                "process_selection",
                upload_count=len(entries),
                selected_count=len(selected_entries),
                selected_filenames=selected_names,
                skipped_already_processed=skipped_processed,
                missing_files=missing_files,
            )
            if not upload_files:
                logger.warning("process_no_files", selected_count=len(selected_entries), missing_files=missing_files)
                raise HTTPException(status_code=400, detail=f": {logger.file_name}")

            payloads: list[tuple[str, bytes]] = []
            with logger.stage("read_upload_files", file_count=len(upload_files)):
                for file_path in upload_files:
                    size_bytes = file_path.stat().st_size
                    with logger.stage(
                        "read_upload_file",
                        source_file=file_path.name,
                        size_bytes=size_bytes,
                        size_mb=round(size_bytes / (1024 * 1024), 3),
                    ):
                        payloads.append((file_path.name, file_path.read_bytes()))

            result = ingest_source_payloads(
                payloads=payloads,
                persist_dir=request.app.state.persist_dir,
                collection_name=collection_name,
                parser_backend=parser_backend,
                operation_logger=logger,
            )
            _mark_process_result(
                request.app.state.upload_dir,
                result=result,
                collection_name=collection_name,
                log_file=logger.file_name,
            )
            result["elapsed_s"] = round(time.time() - t0, 1)
            result["requested_filenames"] = [f.name for f in upload_files]
            result["skipped_already_processed"] = skipped_processed
            result.update(_operation_log_payload(logger))
            logger.close(
                status="ok",
                elapsed_s=result["elapsed_s"],
                files_succeeded=result.get("files_succeeded"),
                files_failed=result.get("files_failed"),
            )
            return result

        except HTTPException as exc:
            logger.error("process_rejected", status_code=exc.status_code, detail=exc.detail)
            logger.close(status="error", status_code=exc.status_code, detail=exc.detail)
            raise
        except Exception as exc:
            logger.exception("process_failed", exc, selected_filenames=[entry["filename"] for entry in selected_entries])
            for entry in selected_entries:
                _update_upload_entry(
                    request.app.state.upload_dir,
                    entry["filename"],
                    status="uploaded",
                    last_error=str(exc),
                    last_log_file=logger.file_name,
                )
            logger.close(status="error", error=str(exc))
            raise HTTPException(status_code=500, detail=f": {exc}? {logger.file_name}") from exc

    @app.post("/api/public-books-json/ingest")
    async def ingest_public_books_json(request: Request, payload: PublicBooksJsonIngestRequest):
        raw_input_dir = payload.input_dir
        collection_name = payload.collection.strip() or "public_books_labelstudio"
        logger = OperationLogger(
            request.app.state.log_dir,
            "public_books_json_ingest",
            input_dir=raw_input_dir,
            collection_name=collection_name,
            mode=payload.mode,
            chunk_size=payload.chunk_size,
            overlap=payload.overlap,
        )
        try:
            input_dir = _resolve_public_books_input_dir(request, raw_input_dir)

            with logger.stage("public_books_json_ingest_run", input_dir=str(input_dir)):
                result = ingest_latest_snapshot_to_chroma(
                    input_root=input_dir,
                    persist_dir=request.app.state.persist_dir,
                    collection_name=collection_name,
                    mode=payload.mode,
                    chunk_size=payload.chunk_size,
                    overlap=payload.overlap,
                )

            reports_dir = REPO_ROOT / "data_pipeline" / "reports"
            with logger.stage("write_public_books_json_ingest_summary", reports_dir=str(reports_dir)):
                result["summary_files"] = write_ingest_summary(result, reports_dir)
            result.update(_operation_log_payload(logger))
            logger.close(
                status="ok",
                collection=result.get("collection"),
                chunks_written=result.get("chunks_written"),
                records_written=result.get("records_written"),
            )
            return result
        except HTTPException as exc:
            logger.error("public_books_json_ingest_rejected", status_code=exc.status_code, detail=exc.detail)
            logger.close(status="error", status_code=exc.status_code, detail=exc.detail)
            raise
        except Exception as exc:
            logger.exception("public_books_json_ingest_failed", exc)
            logger.close(status="error", error=str(exc))
            raise HTTPException(status_code=500, detail=f"JSON : {exc}? {logger.file_name}") from exc

    @app.post("/api/ingest")
    async def ingest(
        request: Request,
        files: list[UploadFile] = File(...),
        collection: str = Form("power_equipment"),
        chunk_size: int = Form(500),
        overlap: int = Form(50),
        backend: str = Form("sentence-transformer"),
        model_name: str = Form(DEFAULT_SENTENCE_TRANSFORMER_MODEL),
        parser_backend: str = Form("auto"),
    ):
        collection_name = collection.strip() or "power_equipment"
        logger = OperationLogger(
            request.app.state.log_dir,
            "ingest",
            collection_name=collection_name,
            upload_count=len(files),
            chunk_size=chunk_size,
            overlap=overlap,
            backend=backend,
            model_name=model_name,
        )
        payloads: list[tuple[str, bytes]] = []
        saved_files: list[str] = []
        manifest_marked = False
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

        try:
            if not files:
                logger.warning("ingest_no_uploads")
                raise HTTPException(status_code=400, detail=f"No files uploaded? {logger.file_name}")

            for index, upload in enumerate(files):
                source_name = Path(upload.filename or f"upload-{index}.bin").name
                with logger.stage("read_ingest_upload", source_file=source_name, index=index):
                    raw_bytes = await upload.read()
                if not raw_bytes:
                    logger.warning("ingest_empty_upload_skipped", source_file=source_name, index=index)
                    continue
                if not is_supported_source(source_name):
                    logger.warning(
                        "ingest_unsupported_type",
                        source_file=source_name,
                        supported_extensions=SUPPORTED_EXTENSIONS_LABEL,
                    )
                    raise HTTPException(
                        status_code=400,
                        detail=f"{source_name} ? {SUPPORTED_EXTENSIONS_LABEL}? {logger.file_name}",
                    )
                saved_name = f"{timestamp}-{index}-{_safe_upload_name(source_name)}"
                target = request.app.state.upload_dir / saved_name
                with logger.stage(
                    "save_ingest_upload",
                    source_file=source_name,
                    stored_name=saved_name,
                    size_bytes=len(raw_bytes),
                    size_mb=round(len(raw_bytes) / (1024 * 1024), 3),
                ):
                    target.write_bytes(raw_bytes)
                _update_upload_entry(
                    request.app.state.upload_dir,
                    saved_name,
                    display_name=source_name,
                    status="uploaded",
                    uploaded_at=time.time(),
                    processed_at=None,
                    source_kind=get_source_kind(source_name),
                    last_collection=None,
                    last_records=0,
                    last_chunks=0,
                    last_error=None,
                    last_log_file=logger.file_name,
                )
                payloads.append((saved_name, raw_bytes))
                saved_files.append(str(target))

            if not payloads:
                logger.warning("ingest_no_readable_payloads", upload_count=len(files))
                raise HTTPException(status_code=400, detail=f"? {logger.file_name}")

            result = ingest_source_payloads(
                payloads=payloads,
                persist_dir=request.app.state.persist_dir,
                collection_name=collection_name,
                chunk_size=chunk_size,
                overlap=overlap,
                backend=backend,
                model_name=model_name,
                parser_backend=parser_backend,
                operation_logger=logger,
            )

            _mark_process_result(
                request.app.state.upload_dir,
                result=result,
                collection_name=collection_name,
                log_file=logger.file_name,
            )
            manifest_marked = True
            result["saved_files"] = saved_files
            result.update(_operation_log_payload(logger))
            logger.close(
                status="ok",
                files_succeeded=result.get("files_succeeded"),
                files_failed=result.get("files_failed"),
            )
            return result
        except HTTPException as exc:
            logger.error("ingest_rejected", status_code=exc.status_code, detail=exc.detail)
            logger.close(status="error", status_code=exc.status_code, detail=exc.detail)
            raise
        except Exception as exc:
            logger.exception("ingest_failed", exc)
            if not manifest_marked:
                for saved_name, _ in payloads:
                    _update_upload_entry(
                        request.app.state.upload_dir,
                        saved_name,
                        status="uploaded",
                        last_error=str(exc),
                        last_log_file=logger.file_name,
                    )
            logger.close(status="error", error=str(exc))
            raise HTTPException(status_code=400, detail=f"{exc}? {logger.file_name}") from exc

    @app.get("/api/stats")
    async def stats(request: Request, collection: str | None = None):
        logger = OperationLogger(request.app.state.log_dir, "stats", collection=collection)
        try:
            if collection:
                with logger.stage("collection_stats", collection_name=collection):
                    result = get_collection_stats(
                        persist_dir=request.app.state.persist_dir,
                        collection_name=collection,
                    )
            else:
                with logger.stage("all_stats"):
                    result = get_all_stats(persist_dir=request.app.state.persist_dir)
                if result.get("status") == "error":
                    logger.warning("all_stats_reported_error", error=result.get("error"))
            result.update(_operation_log_payload(logger))
            logger.close(status="ok", collection=collection)
            return result
        except HTTPException as exc:
            logger.error("stats_rejected", status_code=exc.status_code, detail=exc.detail)
            logger.close(status="error", status_code=exc.status_code, detail=exc.detail)
            raise
        except Exception as exc:
            logger.exception("stats_failed", exc, collection=collection)
            logger.close(status="error", error=str(exc))
            raise HTTPException(status_code=500, detail=f": {exc}? {logger.file_name}") from exc

    @app.get("/api/search")
    async def search_get(
        request: Request,
        q: str = "",
        top_k: int = 5,
        collection: str = "",
        query_rewrite: bool = False,
        reranker: str = "none",
        graph_db_path: str = "",
    ):
        top_k = _validate_top_k(top_k)
        logger = OperationLogger(
            request.app.state.log_dir,
            "search",
            method="GET",
            query=q,
            top_k=top_k,
            requested_collection=collection,
            query_rewrite=query_rewrite,
            reranker=reranker,
            graph_db_path=graph_db_path,
        )
        t0 = time.time()
        try:
            if not q.strip():
                logger.warning("search_empty_query")
                raise HTTPException(status_code=400, detail=f"? {logger.file_name}")

            search_collection = collection.strip() if collection.strip() else None
            if not search_collection:
                with logger.stage("resolve_search_collection"):
                    all_stats = get_all_stats(persist_dir=request.app.state.persist_dir)
                    for coll in all_stats.get("collections", []):
                        if coll["count"] > 0:
                            search_collection = coll["name"]
                            break
                if not search_collection:
                    logger.info("search_no_collection")
                    diagnostics = build_empty_hybrid_retrieval_diagnostics(
                        q,
                        collection_count=0,
                        no_answer_reason="empty_database",
                    )
                    result = {
                        "results": [],
                        "query": q,
                        "retrieval_diagnostics": diagnostics,
                        "message": "collection is empty",
                        **_operation_log_payload(logger),
                    }
                    logger.close(status="ok", result_count=0, reason="empty_database")
                    return result

            with logger.stage("query_collection", collection_name=search_collection, top_k=top_k):
                graph_retriever = _build_optional_search_graph_retriever(request, graph_db_path)
                result = query_collection(
                    query_text=q,
                    persist_dir=request.app.state.persist_dir,
                    collection_name=search_collection,
                    top_k=top_k,
                    query_rewrite=query_rewrite,
                    reranker=reranker,
                    graph_retriever=graph_retriever,
                )
            result["latency_ms"] = round((time.time() - t0) * 1000, 1)
            with logger.stage("search_total_stats"):
                result["total_in_db"] = sum(
                    c["count"] for c in get_all_stats(persist_dir=request.app.state.persist_dir).get("collections", [])
                )
            result.update(_operation_log_payload(logger))
            logger.close(status="ok", result_count=len(result.get("results") or []))
            return result
        except HTTPException as exc:
            logger.error("search_rejected", status_code=exc.status_code, detail=exc.detail)
            logger.close(status="error", status_code=exc.status_code, detail=exc.detail)
            raise
        except Exception as exc:
            logger.exception("search_failed", exc, query=q, collection=collection)
            logger.close(status="error", error=str(exc))
            raise HTTPException(status_code=400, detail=f"? {exc}? {logger.file_name}") from exc

    @app.post("/api/search")
    async def search_post(request: Request, payload: SearchRequest):
        logger = OperationLogger(
            request.app.state.log_dir,
            "search",
            method="POST",
            query=payload.query,
            top_k=payload.top_k,
            requested_collection=payload.collection,
            query_rewrite=payload.query_rewrite,
            reranker=payload.reranker,
            graph_db_path=payload.graph_db_path,
            filters_applied=payload.filters is not None,
            no_answer_min_score=payload.no_answer_min_score,
            no_answer_min_results=payload.no_answer_min_results,
        )
        t0 = time.time()
        try:
            with logger.stage("query_collection", collection_name=payload.collection, top_k=payload.top_k):
                graph_retriever = _build_optional_search_graph_retriever(request, payload.graph_db_path)
                result = query_collection(
                    query_text=payload.query,
                    persist_dir=request.app.state.persist_dir,
                    collection_name=payload.collection,
                    top_k=payload.top_k,
                    query_rewrite=payload.query_rewrite,
                    reranker=payload.reranker,
                    graph_retriever=graph_retriever,
                    filters=payload.filters,
                    no_answer_min_score=payload.no_answer_min_score,
                    no_answer_min_results=payload.no_answer_min_results,
                )
            result["latency_ms"] = round((time.time() - t0) * 1000, 1)
            result.update(_operation_log_payload(logger))
            logger.close(status="ok", result_count=len(result.get("results") or []))
            return result
        except Exception as exc:
            logger.exception("search_failed", exc, query=payload.query, collection=payload.collection)
            logger.close(status="error", error=str(exc))
            raise HTTPException(status_code=400, detail=f"? {exc}? {logger.file_name}") from exc

    @app.post("/api/retrieval/policies/promote")
    async def promote_retrieval_policy(request: Request, payload: RetrievalPolicyPromotionRequest):
        logger = OperationLogger(
            request.app.state.log_dir,
            "retrieval-policy-promote",
            collection=payload.collection,
            reviewer=payload.reviewer,
            source_report=payload.source_report,
        )
        try:
            promoted = promote_collection_retrieval_policy(
                request.app.state.persist_dir,
                payload.collection,
                payload.settings,
                reviewer=payload.reviewer,
                review_note=payload.review_note,
                source_report=payload.source_report,
            )
            promoted.update(_operation_log_payload(logger))
            logger.close(status="ok", collection=promoted["collection"])
            return promoted
        except Exception as exc:
            logger.exception("retrieval_policy_promote_failed", exc, collection=payload.collection)
            logger.close(status="error", error=str(exc))
            raise HTTPException(status_code=400, detail=f"? {exc}? {logger.file_name}") from exc

    @app.post("/api/retrieval/policies/roles/upsert")
    async def upsert_retrieval_policy_role_endpoint(request: Request, payload: RetrievalPolicyRoleUpsertRequest):
        logger = OperationLogger(
            request.app.state.log_dir,
            "retrieval-policy-role-upsert",
            subject=payload.subject,
            updated_by=payload.updated_by,
        )
        try:
            role_entry = upsert_retrieval_policy_role(
                request.app.state.persist_dir,
                payload.subject,
                payload.roles,
                assigned_collections=payload.assigned_collections,
                updated_by=payload.updated_by,
                note=payload.note,
            )
            role_entry.update(_operation_log_payload(logger))
            logger.close(status="ok", subject=role_entry["subject"], roles=role_entry["roles"])
            return role_entry
        except Exception as exc:
            logger.exception("retrieval_policy_role_upsert_failed", exc, subject=payload.subject)
            logger.close(status="error", error=str(exc))
            raise HTTPException(status_code=400, detail=f"? {exc}? {logger.file_name}") from exc

    @app.get("/api/retrieval/policies/notification-recipients")
    async def retrieval_policy_notification_recipients(request: Request):
        logger = OperationLogger(request.app.state.log_dir, "retrieval-policy-notification-recipients")
        try:
            recipients = list_retrieval_policy_notification_recipients(request.app.state.persist_dir)
            recipients.update(_operation_log_payload(logger))
            logger.close(status="ok", recipient_count=recipients["recipient_count"])
            return recipients
        except Exception as exc:
            logger.exception("retrieval_policy_notification_recipients_failed", exc)
            logger.close(status="error", error=str(exc))
            raise HTTPException(status_code=400, detail=f"retrieval policy notification recipients failed: {exc}; log: {logger.file_name}") from exc

    @app.post("/api/retrieval/policies/notification-recipients/upsert")
    async def upsert_retrieval_policy_notification_recipient_endpoint(
        request: Request,
        payload: RetrievalPolicyNotificationRecipientUpsertRequest,
    ):
        logger = OperationLogger(
            request.app.state.log_dir,
            "retrieval-policy-notification-recipient-upsert",
            subject=payload.subject,
            updated_by=payload.updated_by,
        )
        try:
            recipient_entry = upsert_retrieval_policy_notification_recipient(
                request.app.state.persist_dir,
                payload.subject,
                email=payload.email,
                webhook_url=payload.webhook_url,
                webhook_template=payload.webhook_template,
                webhook_signing_secret_env=payload.webhook_signing_secret_env,
                webhook_routing_key_env=payload.webhook_routing_key_env,
                webhook_auth_header_name=payload.webhook_auth_header_name,
                webhook_auth_token_env=payload.webhook_auth_token_env,
                webhook_auth_scheme=payload.webhook_auth_scheme,
                preferred_delivery_mode=payload.preferred_delivery_mode,
                updated_by=payload.updated_by,
                note=payload.note,
            )
            response_payload = {
                "recipient_entry": recipient_entry,
                **recipient_entry,
                **_operation_log_payload(logger),
            }
            logger.close(status="ok", subject=recipient_entry["subject"])
            return response_payload
        except Exception as exc:
            logger.exception("retrieval_policy_notification_recipient_upsert_failed", exc, subject=payload.subject)
            logger.close(status="error", error=str(exc))
            raise HTTPException(status_code=400, detail=f"retrieval policy notification recipient upsert failed: {exc}; log: {logger.file_name}") from exc

    @app.post("/api/retrieval/policies/directory/sync")
    async def sync_retrieval_policy_directory_endpoint(
        request: Request,
        payload: RetrievalPolicyDirectorySyncRequest,
    ):
        logger = OperationLogger(
            request.app.state.log_dir,
            "retrieval-policy-directory-sync",
            source_type=payload.source_type,
            updated_by=payload.updated_by,
        )
        try:
            synced = sync_retrieval_policy_identity_directory(
                request.app.state.persist_dir,
                source_type=payload.source_type,
                users=payload.users,
                groups=payload.groups,
                role_group_mappings=payload.role_group_mappings,
                recipient_defaults=payload.recipient_defaults,
                updated_by=payload.updated_by,
                note=payload.note,
                dry_run=payload.dry_run,
            )
            synced.update(_operation_log_payload(logger))
            logger.close(
                status="ok",
                synced_user_count=synced["synced_user_count"],
                role_upsert_count=synced["role_upsert_count"],
                recipient_upsert_count=synced["recipient_upsert_count"],
            )
            return synced
        except Exception as exc:
            logger.exception("retrieval_policy_directory_sync_failed", exc, source_type=payload.source_type)
            logger.close(status="error", error=str(exc))
            raise HTTPException(status_code=400, detail=f"retrieval policy directory sync failed: {exc}; log: {logger.file_name}") from exc

    @app.get("/api/retrieval/policies/identity-provider")
    async def retrieval_policy_identity_provider(request: Request):
        logger = OperationLogger(request.app.state.log_dir, "retrieval-policy-identity-provider")
        try:
            identity_provider = get_retrieval_policy_identity_provider_config(request.app.state.persist_dir)
            identity_provider.update(_operation_log_payload(logger))
            logger.close(status="ok")
            return identity_provider
        except Exception as exc:
            logger.exception("retrieval_policy_identity_provider_failed", exc)
            logger.close(status="error", error=str(exc))
            raise HTTPException(status_code=400, detail=f"retrieval policy identity provider failed: {exc}; log: {logger.file_name}") from exc

    @app.post("/api/retrieval/policies/identity-provider/upsert")
    async def upsert_retrieval_policy_identity_provider(
        request: Request,
        payload: RetrievalPolicyIdentityProviderUpsertRequest,
    ):
        logger = OperationLogger(
            request.app.state.log_dir,
            "retrieval-policy-identity-provider-upsert",
            provider=payload.provider,
            enabled=payload.enabled,
            updated_by=payload.updated_by,
        )
        try:
            identity_provider = upsert_retrieval_policy_identity_provider_config(
                request.app.state.persist_dir,
                provider=payload.provider,
                enabled=payload.enabled,
                issuer=payload.issuer,
                audience=payload.audience,
                jwks_url=payload.jwks_url,
                authorization_endpoint=payload.authorization_endpoint,
                token_endpoint=payload.token_endpoint,
                client_id=payload.client_id,
                client_secret_env=payload.client_secret_env,
                redirect_uri=payload.redirect_uri,
                scopes=payload.scopes,
                subject_claim=payload.subject_claim,
                groups_claim=payload.groups_claim,
                algorithms=payload.algorithms,
                updated_by=payload.updated_by,
                note=payload.note,
            )
            identity_provider.update(_operation_log_payload(logger))
            logger.close(status="ok", provider=payload.provider, enabled=payload.enabled)
            return identity_provider
        except Exception as exc:
            logger.exception("retrieval_policy_identity_provider_upsert_failed", exc, provider=payload.provider)
            logger.close(status="error", error=str(exc))
            raise HTTPException(status_code=400, detail=f"retrieval policy identity provider upsert failed: {exc}; log: {logger.file_name}") from exc

    @app.post("/api/retrieval/policies/identity-provider/login-url")
    async def retrieval_policy_identity_provider_login_url(
        request: Request,
        response: Response,
        payload: RetrievalPolicyIdentityProviderLoginUrlRequest,
    ):
        logger = OperationLogger(request.app.state.log_dir, "retrieval-policy-identity-provider-login-url")
        try:
            config = _retrieval_policy_oidc_login_config(request.app.state.persist_dir)
            redirect_uri = _resolve_oidc_redirect_uri(config, payload.redirect_uri)
            code_verifier = _new_pkce_verifier()
            code_challenge = _pkce_challenge(code_verifier)
            state = str(payload.state or "").strip() or secrets.token_urlsafe(24)
            nonce = str(payload.nonce or "").strip() or secrets.token_urlsafe(24)
            state_record = _store_retrieval_policy_oidc_state(
                request.app.state.persist_dir,
                state=state,
                nonce=nonce,
                code_verifier=code_verifier,
                redirect_uri=redirect_uri,
            )
            scopes = [
                str(scope or "").strip()
                for scope in config.get("scopes", ["openid", "email", "profile"])
                if str(scope or "").strip()
            ] or ["openid", "email", "profile"]
            params = {
                "response_type": "code",
                "client_id": str(config.get("client_id") or "").strip(),
                "redirect_uri": redirect_uri,
                "scope": " ".join(scopes),
                "state": state,
                "nonce": nonce,
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
            }
            separator = "&" if "?" in str(config.get("authorization_endpoint") or "") else "?"
            authorization_url = f"{str(config.get('authorization_endpoint')).strip()}{separator}{urlencode(params)}"
            response.set_cookie(
                RETRIEVAL_POLICY_OIDC_STATE_COOKIE,
                state,
                max_age=max(1, int(state_record["expires_at"]) - int(time.time())),
                httponly=True,
                secure=str(request.url.scheme).casefold() == "https",
                samesite="lax",
            )
            logger.close(status="ok", client_id=params["client_id"])
            return {
                "authorization_url": authorization_url,
                "state": state,
                "nonce": nonce,
                "code_verifier": code_verifier,
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
                "redirect_uri": redirect_uri,
                "scope": params["scope"],
                "provider": "oidc",
                **_operation_log_payload(logger),
            }
        except HTTPException:
            logger.close(status="error", error="oidc login url failed")
            raise
        except Exception as exc:
            logger.exception("retrieval_policy_identity_provider_login_url_failed", exc)
            logger.close(status="error", error=str(exc))
            raise HTTPException(status_code=400, detail=f"retrieval policy identity provider login URL failed: {exc}; log: {logger.file_name}") from exc

    @app.get("/api/retrieval/policies/identity-provider/callback")
    async def retrieval_policy_identity_provider_callback(
        request: Request,
        response: Response,
        code: str = "",
        state: str = "",
    ):
        logger = OperationLogger(request.app.state.log_dir, "retrieval-policy-identity-provider-callback")
        try:
            cookie_state = str(request.cookies.get(RETRIEVAL_POLICY_OIDC_STATE_COOKIE) or "").strip()
            requested_state = str(state or "").strip()
            if not requested_state:
                raise HTTPException(status_code=400, detail="OIDC callback state is required")
            if cookie_state and cookie_state != requested_state:
                raise HTTPException(status_code=400, detail="OIDC callback state does not match session cookie")
            config = _retrieval_policy_oidc_login_config(request.app.state.persist_dir)
            state_record = _consume_retrieval_policy_oidc_state(request.app.state.persist_dir, requested_state)
            redirect_uri = _resolve_oidc_redirect_uri(config, str(state_record.get("redirect_uri") or ""))
            token_payload = _exchange_oidc_authorization_code(
                config,
                code=code,
                code_verifier=str(state_record.get("code_verifier") or ""),
                redirect_uri=redirect_uri,
            )
            token = str(token_payload.get("id_token") or token_payload.get("access_token") or "").strip()
            if not token:
                raise HTTPException(status_code=502, detail="OIDC token endpoint did not return id_token or access_token")
            identity = _decode_retrieval_policy_oidc_token(token, _retrieval_policy_oidc_config(request.app.state.persist_dir))
            session_id, record = _create_retrieval_policy_session(request.app.state.persist_dir, identity, token_payload)
            response.set_cookie(
                RETRIEVAL_POLICY_SESSION_COOKIE,
                session_id,
                max_age=max(1, int(record["expires_at"]) - int(time.time())),
                httponly=True,
                secure=str(request.url.scheme).casefold() == "https",
                samesite="lax",
            )
            response.delete_cookie(RETRIEVAL_POLICY_OIDC_STATE_COOKIE)
            logger.close(status="ok", subject=record["subject"])
            return {
                "subject": record["subject"],
                "groups": record["groups"],
                "identity_source": record["identity_source"],
                "expires_at": record["expires_at"],
                "token_type": token_payload.get("token_type"),
                **_operation_log_payload(logger),
            }
        except HTTPException:
            logger.close(status="error", error="oidc callback failed")
            raise
        except Exception as exc:
            logger.exception("retrieval_policy_identity_provider_callback_failed", exc)
            logger.close(status="error", error=str(exc))
            raise HTTPException(status_code=400, detail=f"retrieval policy identity provider callback failed: {exc}; log: {logger.file_name}") from exc

    @app.post("/api/retrieval/policies/identity-provider/token")
    async def retrieval_policy_identity_provider_token(
        request: Request,
        payload: RetrievalPolicyIdentityProviderTokenRequest,
    ):
        logger = OperationLogger(request.app.state.log_dir, "retrieval-policy-identity-provider-token")
        try:
            config = _retrieval_policy_oidc_login_config(request.app.state.persist_dir)
            redirect_uri = _resolve_oidc_redirect_uri(config, payload.redirect_uri)
            token_payload = _exchange_oidc_authorization_code(
                config,
                code=payload.code,
                code_verifier=payload.code_verifier,
                redirect_uri=redirect_uri,
            )
            logger.close(status="ok", client_id=str(config.get("client_id") or ""))
            return {**token_payload, **_operation_log_payload(logger)}
        except HTTPException:
            logger.close(status="error", error="oidc token exchange failed")
            raise
        except Exception as exc:
            logger.exception("retrieval_policy_identity_provider_token_failed", exc)
            logger.close(status="error", error=str(exc))
            raise HTTPException(status_code=400, detail=f"retrieval policy identity provider token failed: {exc}; log: {logger.file_name}") from exc

    @app.post("/api/retrieval/policies/identity-provider/session")
    async def retrieval_policy_identity_provider_session(request: Request, response: Response):
        logger = OperationLogger(request.app.state.log_dir, "retrieval-policy-identity-provider-session")
        try:
            oidc_config = _retrieval_policy_oidc_config(request.app.state.persist_dir)
            if not oidc_config:
                raise HTTPException(status_code=400, detail="managed OIDC identity provider is not enabled")
            authorization = str(request.headers.get("authorization") or "").strip()
            if not authorization.lower().startswith("bearer "):
                raise HTTPException(status_code=401, detail="OIDC bearer token is required")
            token = authorization.split(" ", 1)[1].strip()
            if not token:
                raise HTTPException(status_code=401, detail="OIDC bearer token is required")
            identity = _decode_retrieval_policy_oidc_token(token, oidc_config)
            session_id, record = _create_retrieval_policy_session(request.app.state.persist_dir, identity)
            max_age = max(1, int(record["expires_at"]) - int(time.time()))
            response.set_cookie(
                RETRIEVAL_POLICY_SESSION_COOKIE,
                session_id,
                max_age=max_age,
                httponly=True,
                secure=str(request.url.scheme).casefold() == "https",
                samesite="lax",
            )
            logger.close(status="ok", subject=record["subject"])
            return {
                "subject": record["subject"],
                "groups": record["groups"],
                "identity_source": record["identity_source"],
                "expires_at": record["expires_at"],
                **_operation_log_payload(logger),
            }
        except HTTPException:
            logger.close(status="error", error="oidc session failed")
            raise
        except Exception as exc:
            logger.exception("retrieval_policy_identity_provider_session_failed", exc)
            logger.close(status="error", error=str(exc))
            raise HTTPException(status_code=400, detail=f"retrieval policy identity provider session failed: {exc}; log: {logger.file_name}") from exc

    @app.post("/api/retrieval/policies/identity-provider/session/refresh")
    async def retrieval_policy_identity_provider_session_refresh(request: Request, response: Response):
        logger = OperationLogger(request.app.state.log_dir, "retrieval-policy-identity-provider-session-refresh")
        try:
            config = _retrieval_policy_oidc_login_config(request.app.state.persist_dir)
            session_id = str(request.cookies.get(RETRIEVAL_POLICY_SESSION_COOKIE) or "").strip()
            if not session_id:
                raise HTTPException(status_code=401, detail="OIDC policy session cookie is required")
            sessions = _read_retrieval_policy_sessions(request.app.state.persist_dir)
            record = sessions.get(session_id)
            if not isinstance(record, dict):
                raise HTTPException(status_code=401, detail="OIDC policy session is invalid or expired")
            if int(record.get("expires_at") or 0) <= int(time.time()):
                sessions.pop(session_id, None)
                _write_retrieval_policy_sessions(request.app.state.persist_dir, sessions)
                raise HTTPException(status_code=401, detail="OIDC policy session is invalid or expired")
            refresh_token = _decrypt_retrieval_policy_session_secret(record)
            token_payload = _exchange_oidc_refresh_token(config, refresh_token=refresh_token)
            token = str(token_payload.get("id_token") or token_payload.get("access_token") or "").strip()
            if not token:
                raise HTTPException(status_code=502, detail="OIDC token endpoint did not return id_token or access_token")
            identity = _decode_retrieval_policy_oidc_token(token, _retrieval_policy_oidc_config(request.app.state.persist_dir))
            updated = _refresh_retrieval_policy_session_record(
                request.app.state.persist_dir,
                session_id,
                identity,
                token_payload,
            )
            max_age = max(1, int(updated["expires_at"]) - int(time.time()))
            response.set_cookie(
                RETRIEVAL_POLICY_SESSION_COOKIE,
                session_id,
                max_age=max_age,
                httponly=True,
                secure=str(request.url.scheme).casefold() == "https",
                samesite="lax",
            )
            logger.close(status="ok", subject=updated["subject"])
            return {
                "subject": updated["subject"],
                "groups": updated["groups"],
                "identity_source": updated["identity_source"],
                "expires_at": updated["expires_at"],
                "token_type": updated.get("token_type"),
                "refreshed": True,
                **_operation_log_payload(logger),
            }
        except HTTPException:
            logger.close(status="error", error="oidc session refresh failed")
            raise
        except Exception as exc:
            logger.exception("retrieval_policy_identity_provider_session_refresh_failed", exc)
            logger.close(status="error", error=str(exc))
            raise HTTPException(status_code=400, detail=f"retrieval policy identity provider session refresh failed: {exc}; log: {logger.file_name}") from exc

    @app.get("/api/retrieval/policies/identity-provider/sessions")
    async def retrieval_policy_identity_provider_sessions(request: Request):
        logger = OperationLogger(request.app.state.log_dir, "retrieval-policy-identity-provider-sessions")
        try:
            admin_identity = _resolve_retrieval_policy_session_admin_identity(request, request.app.state.persist_dir)
            sessions, expired_count = _list_retrieval_policy_session_records(request.app.state.persist_dir)
            logger.close(status="ok", admin=admin_identity["subject"], session_count=len(sessions))
            return {
                "sessions": sessions,
                "session_count": len(sessions),
                "expired_pruned_count": expired_count,
                "admin": admin_identity["subject"],
                "admin_role": admin_identity["admin_role"],
                "role_source": admin_identity["role_source"],
                **_operation_log_payload(logger),
            }
        except HTTPException:
            logger.close(status="error", error="oidc session list failed")
            raise
        except Exception as exc:
            logger.exception("retrieval_policy_identity_provider_sessions_failed", exc)
            logger.close(status="error", error=str(exc))
            raise HTTPException(status_code=400, detail=f"retrieval policy identity provider sessions failed: {exc}; log: {logger.file_name}") from exc

    @app.post("/api/retrieval/policies/identity-provider/sessions/rotate-key")
    async def retrieval_policy_identity_provider_session_rotate_key(request: Request):
        logger = OperationLogger(request.app.state.log_dir, "retrieval-policy-identity-provider-session-rotate-key")
        try:
            admin_identity = _resolve_retrieval_policy_session_admin_identity(request, request.app.state.persist_dir)
            rotated = _rotate_retrieval_policy_session_refresh_token_keys(request.app.state.persist_dir)
            audit_entry = _append_retrieval_policy_audit_entry(
                request.app.state.persist_dir,
                {
                    "action": "identity_provider_session_key_rotate",
                    "admin": admin_identity["subject"],
                    "admin_role": admin_identity["admin_role"],
                    "role_source": admin_identity["role_source"],
                    "active_key_id": rotated["active_key_id"],
                    "rotated_count": rotated["rotated_count"],
                    "skipped_count": rotated["skipped_count"],
                    "expired_pruned_count": rotated["expired_pruned_count"],
                    "session_count": rotated["session_count"],
                    "rotated_session_ids": rotated["rotated_session_ids"],
                },
            )
            logger.close(
                status="ok",
                admin=admin_identity["subject"],
                rotated_count=rotated["rotated_count"],
                active_key_id=rotated["active_key_id"],
            )
            return {
                **rotated,
                "admin": admin_identity["subject"],
                "admin_role": admin_identity["admin_role"],
                "role_source": admin_identity["role_source"],
                "audit_entry": audit_entry,
                **_operation_log_payload(logger),
            }
        except HTTPException:
            logger.close(status="error", error="oidc session key rotation failed")
            raise
        except Exception as exc:
            logger.exception("retrieval_policy_identity_provider_session_rotate_key_failed", exc)
            logger.close(status="error", error=str(exc))
            raise HTTPException(status_code=400, detail=f"retrieval policy identity provider session key rotation failed: {exc}; log: {logger.file_name}") from exc

    @app.get("/api/retrieval/policies/identity-provider/sessions/key-status")
    async def retrieval_policy_identity_provider_session_key_status(request: Request):
        logger = OperationLogger(request.app.state.log_dir, "retrieval-policy-identity-provider-session-key-status")
        try:
            admin_identity = _resolve_retrieval_policy_session_admin_identity(request, request.app.state.persist_dir)
            status = _summarize_retrieval_policy_session_key_status(request.app.state.persist_dir)
            logger.close(
                status="ok",
                admin=admin_identity["subject"],
                active_key_id=status["active_key_id"],
                rotation_due=status["rotation_due"],
            )
            return {
                **status,
                "admin": admin_identity["subject"],
                "admin_role": admin_identity["admin_role"],
                "role_source": admin_identity["role_source"],
                **_operation_log_payload(logger),
            }
        except HTTPException:
            logger.close(status="error", error="oidc session key status failed")
            raise
        except Exception as exc:
            logger.exception("retrieval_policy_identity_provider_session_key_status_failed", exc)
            logger.close(status="error", error=str(exc))
            raise HTTPException(status_code=400, detail=f"retrieval policy identity provider session key status failed: {exc}; log: {logger.file_name}") from exc

    @app.delete("/api/retrieval/policies/identity-provider/sessions/{session_id}")
    async def retrieval_policy_identity_provider_session_revoke(request: Request, session_id: str):
        logger = OperationLogger(request.app.state.log_dir, "retrieval-policy-identity-provider-session-revoke")
        try:
            admin_identity = _resolve_retrieval_policy_session_admin_identity(request, request.app.state.persist_dir)
            requested_session_id = str(session_id or "").strip()
            if not requested_session_id:
                raise HTTPException(status_code=400, detail="OIDC policy session id is required")
            sessions = _read_retrieval_policy_sessions(request.app.state.persist_dir)
            existed = requested_session_id in sessions
            if existed:
                sessions.pop(requested_session_id, None)
                _write_retrieval_policy_sessions(request.app.state.persist_dir, sessions)
            audit_entry = _append_retrieval_policy_audit_entry(
                request.app.state.persist_dir,
                {
                    "action": "identity_provider_session_revoke",
                    "admin": admin_identity["subject"],
                    "admin_role": admin_identity["admin_role"],
                    "role_source": admin_identity["role_source"],
                    "revoked_session_id": requested_session_id,
                    "revoked": existed,
                },
            )
            logger.close(status="ok", admin=admin_identity["subject"], revoked=existed)
            return {
                "status": "revoked" if existed else "not_found",
                "revoked": existed,
                "revoked_session_id": requested_session_id,
                "admin": admin_identity["subject"],
                "admin_role": admin_identity["admin_role"],
                "role_source": admin_identity["role_source"],
                "audit_entry": audit_entry,
                **_operation_log_payload(logger),
            }
        except HTTPException:
            logger.close(status="error", error="oidc session revoke failed")
            raise
        except Exception as exc:
            logger.exception("retrieval_policy_identity_provider_session_revoke_failed", exc)
            logger.close(status="error", error=str(exc))
            raise HTTPException(status_code=400, detail=f"retrieval policy identity provider session revoke failed: {exc}; log: {logger.file_name}") from exc

    @app.post("/api/retrieval/policies/identity-provider/logout")
    async def retrieval_policy_identity_provider_logout(request: Request, response: Response):
        logger = OperationLogger(request.app.state.log_dir, "retrieval-policy-identity-provider-logout")
        try:
            session_id = str(request.cookies.get(RETRIEVAL_POLICY_SESSION_COOKIE) or "").strip()
            _delete_retrieval_policy_session(request.app.state.persist_dir, session_id)
            response.delete_cookie(RETRIEVAL_POLICY_SESSION_COOKIE)
            logger.close(status="ok")
            return {"status": "ok", **_operation_log_payload(logger)}
        except Exception as exc:
            logger.exception("retrieval_policy_identity_provider_logout_failed", exc)
            logger.close(status="error", error=str(exc))
            raise HTTPException(status_code=400, detail=f"retrieval policy identity provider logout failed: {exc}; log: {logger.file_name}") from exc

    @app.post("/api/retrieval/policies/propose")
    async def propose_retrieval_policy(request: Request, payload: RetrievalPolicyProposalRequest):
        logger = OperationLogger(
            request.app.state.log_dir,
            "retrieval-policy-propose",
            collection=payload.collection,
            reviewer=payload.reviewer,
            reviewer_role=payload.reviewer_role,
            source_report=payload.source_report,
        )
        try:
            identity = _resolve_retrieval_policy_oidc_identity(request, request.app.state.persist_dir)
            reviewer = str(identity.get("subject") or payload.reviewer).strip()
            reviewer_role = "" if identity else payload.reviewer_role
            proposed = propose_collection_retrieval_policy(
                request.app.state.persist_dir,
                payload.collection,
                payload.settings,
                reviewer=reviewer,
                reviewer_role=reviewer_role,
                review_note=payload.review_note,
                source_report=payload.source_report,
                assigned_to=payload.assigned_to,
                due_at=payload.due_at,
            )
            proposed.update(_operation_log_payload(logger))
            logger.close(status="ok", collection=proposed["collection"], proposal_id=proposed["proposal_id"])
            return proposed
        except HTTPException:
            logger.close(status="error", error="oidc policy auth failed")
            raise
        except Exception as exc:
            logger.exception("retrieval_policy_propose_failed", exc, collection=payload.collection)
            logger.close(status="error", error=str(exc))
            raise HTTPException(status_code=400, detail=f"? {exc}? {logger.file_name}") from exc

    @app.post("/api/retrieval/policies/approve")
    async def approve_retrieval_policy(request: Request, payload: RetrievalPolicyApprovalRequest):
        logger = OperationLogger(
            request.app.state.log_dir,
            "retrieval-policy-approve",
            proposal_id=payload.proposal_id,
            approver=payload.approver,
            approver_role=payload.approver_role,
        )
        try:
            identity = _resolve_retrieval_policy_oidc_identity(request, request.app.state.persist_dir)
            approver = str(identity.get("subject") or payload.approver).strip()
            approver_role = "" if identity else payload.approver_role
            approved = approve_collection_retrieval_policy_proposal(
                request.app.state.persist_dir,
                payload.proposal_id,
                approver=approver,
                approver_role=approver_role,
                approval_note=payload.approval_note,
                identity_source=str(identity.get("identity_source") or "request"),
            )
            approved.update(_operation_log_payload(logger))
            logger.close(status="ok", collection=approved["collection"], proposal_id=approved["proposal_id"])
            return approved
        except HTTPException:
            logger.close(status="error", error="oidc policy auth failed")
            raise
        except Exception as exc:
            logger.exception("retrieval_policy_approve_failed", exc, proposal_id=payload.proposal_id)
            logger.close(status="error", error=str(exc))
            raise HTTPException(status_code=400, detail=f"? {exc}? {logger.file_name}") from exc

    @app.post("/api/retrieval/policies/reject")
    async def reject_retrieval_policy(request: Request, payload: RetrievalPolicyRejectionRequest):
        logger = OperationLogger(
            request.app.state.log_dir,
            "retrieval-policy-reject",
            proposal_id=payload.proposal_id,
            approver=payload.approver,
            approver_role=payload.approver_role,
        )
        try:
            identity = _resolve_retrieval_policy_oidc_identity(request, request.app.state.persist_dir)
            approver = str(identity.get("subject") or payload.approver).strip()
            approver_role = "" if identity else payload.approver_role
            rejected = reject_collection_retrieval_policy_proposal(
                request.app.state.persist_dir,
                payload.proposal_id,
                approver=approver,
                approver_role=approver_role,
                rejection_note=payload.rejection_note,
                identity_source=str(identity.get("identity_source") or "request"),
            )
            rejected.update(_operation_log_payload(logger))
            logger.close(status="ok", collection=rejected["collection"], proposal_id=rejected["proposal_id"])
            return rejected
        except HTTPException:
            logger.close(status="error", error="oidc policy auth failed")
            raise
        except Exception as exc:
            logger.exception("retrieval_policy_reject_failed", exc, proposal_id=payload.proposal_id)
            logger.close(status="error", error=str(exc))
            raise HTTPException(status_code=400, detail=f"? {exc}? {logger.file_name}") from exc

    @app.get("/api/retrieval/policies/history")
    async def retrieval_policy_history(request: Request, collection: str = "power_equipment"):
        logger = OperationLogger(
            request.app.state.log_dir,
            "retrieval-policy-history",
            collection=collection,
        )
        try:
            history = get_collection_retrieval_policy_history(request.app.state.persist_dir, collection)
            history.update(_operation_log_payload(logger))
            logger.close(status="ok", collection=history["collection"], history_count=len(history["history"]))
            return history
        except Exception as exc:
            logger.exception("retrieval_policy_history_failed", exc, collection=collection)
            logger.close(status="error", error=str(exc))
            raise HTTPException(status_code=400, detail=f"? {exc}? {logger.file_name}") from exc

    @app.get("/api/retrieval/policies/notifications")
    async def retrieval_policy_notifications(request: Request, recipient: str = "", status: str = ""):
        logger = OperationLogger(
            request.app.state.log_dir,
            "retrieval-policy-notifications",
            recipient=recipient,
            notification_status=status,
        )
        try:
            notifications = list_retrieval_policy_notifications(
                request.app.state.persist_dir,
                recipient=recipient,
                status=status,
            )
            notifications.update(_operation_log_payload(logger))
            logger.close(status="ok", notification_count=notifications["notification_count"])
            return notifications
        except Exception as exc:
            logger.exception("retrieval_policy_notifications_failed", exc, recipient=recipient, status=status)
            logger.close(status="error", error=str(exc))
            raise HTTPException(status_code=400, detail=f": {exc}? {logger.file_name}") from exc

    @app.post("/api/retrieval/policies/notifications/dispatch")
    async def dispatch_retrieval_policy_notification_endpoint(
        request: Request,
        payload: RetrievalPolicyNotificationDispatchRequest,
    ):
        logger = OperationLogger(
            request.app.state.log_dir,
            "retrieval-policy-notification-dispatch",
            recipient=payload.recipient,
            notification_status=payload.status,
            delivery_mode=payload.delivery_mode,
        )
        try:
            dispatched = dispatch_retrieval_policy_notifications(
                request.app.state.persist_dir,
                recipient=payload.recipient,
                status=payload.status,
                delivery_mode=payload.delivery_mode,
                outbox_path=payload.outbox_path or None,
                webhook_url=payload.webhook_url,
                webhook_timeout_seconds=payload.webhook_timeout_seconds,
                webhook_template=payload.webhook_template,
                webhook_signing_secret_env=payload.webhook_signing_secret_env,
                webhook_routing_key_env=payload.webhook_routing_key_env,
                webhook_auth_header_name=payload.webhook_auth_header_name,
                webhook_auth_token_env=payload.webhook_auth_token_env,
                webhook_auth_scheme=payload.webhook_auth_scheme,
                smtp_host=payload.smtp_host,
                smtp_port=payload.smtp_port,
                smtp_from=payload.smtp_from,
                smtp_to=payload.smtp_to,
                smtp_subject=payload.smtp_subject,
                smtp_timeout_seconds=payload.smtp_timeout_seconds,
                smtp_use_tls=payload.smtp_use_tls,
                smtp_username_env=payload.smtp_username_env,
                smtp_password_env=payload.smtp_password_env,
                dispatched_by=payload.dispatched_by,
            )
            dispatched.update(_operation_log_payload(logger))
            logger.close(status="ok", dispatched_count=dispatched["dispatched_count"])
            return dispatched
        except Exception as exc:
            logger.exception("retrieval_policy_notification_dispatch_failed", exc, recipient=payload.recipient)
            logger.close(status="error", error=str(exc))
            raise HTTPException(status_code=400, detail=f"? {exc}? {logger.file_name}") from exc

    @app.post("/api/retrieval/policies/rollback")
    async def rollback_retrieval_policy(request: Request, payload: RetrievalPolicyRollbackRequest):
        logger = OperationLogger(
            request.app.state.log_dir,
            "retrieval-policy-rollback",
            collection=payload.collection,
            reviewer=payload.reviewer,
        )
        try:
            rolled_back = rollback_collection_retrieval_policy(
                request.app.state.persist_dir,
                payload.collection,
                reviewer=payload.reviewer,
                review_note=payload.review_note,
            )
            rolled_back.update(_operation_log_payload(logger))
            logger.close(status="ok", collection=rolled_back["collection"])
            return rolled_back
        except Exception as exc:
            logger.exception("retrieval_policy_rollback_failed", exc, collection=payload.collection)
            logger.close(status="error", error=str(exc))
            raise HTTPException(status_code=400, detail=f"? {exc}? {logger.file_name}") from exc

    @app.post("/api/query")
    async def unified_query(request: Request, payload: UnifiedQueryRequest):
        logger = OperationLogger(
            request.app.state.log_dir,
            "query",
            mode=payload.mode,
            question=payload.question,
            requested_collection=payload.collection,
            top_k=payload.top_k,
        )
        t0 = time.time()
        question = payload.question.strip()
        collection_name: str | None = payload.collection.strip() or None
        collection_resolution: dict[str, Any] = {
            "requested_collection": payload.collection.strip(),
            "resolved_collection": collection_name,
            "reason": "not_resolved",
        }
        graph_path: Path | None = None
        graph_quality = None
        try:
            semantic_spec = SemanticQueryAnalyzer().analyze(question)
            generic_comprehensive_analysis = (
                _is_generic_comprehensive_analysis_question(question)
            )
            planner_comprehensive_analysis = (
                not generic_comprehensive_analysis
                and semantic_spec.route == QueryRouteName.COMPREHENSIVE_ANALYSIS
                and getattr(semantic_spec.coverage_scope, "value", "local") != "local"
            )
            collection_name, collection_resolution = _resolve_query_collection_name(
                request.app.state.persist_dir,
                requested_collection=payload.collection,
                question=question,
            )
            if not collection_name:
                raise HTTPException(status_code=400, detail=f": {logger.file_name}")

            llm = _build_query_llm(payload)
            text_retriever = _QueryCollectionTextRetriever(
                persist_dir=request.app.state.persist_dir,
                collection_name=collection_name,
            )
            self_identity_analysis = _is_self_identity_question(question)
            collection_overview_analysis = _is_vague_collection_overview_question(question)
            private_contact_overview_analysis = _is_private_contact_overview_question(question)
            sample_for_private_or_identity = (
                _is_private_contact_question(question)
                or self_identity_analysis
                or collection_overview_analysis
                or private_contact_overview_analysis
            )
            private_contact_sample = text_retriever.scan_all(limit=25) if sample_for_private_or_identity else []
            looks_like_private_contact_collection = _looks_like_private_contact_collection(
                collection_name,
                private_contact_sample,
            )
            private_contact_analysis = _should_run_private_contact_scan(
                question,
                collection_name,
                private_contact_sample,
            )
            private_contact_overview_analysis = private_contact_overview_analysis and looks_like_private_contact_collection
            deterministic_full_scan = (
                self_identity_analysis
                or
                private_contact_analysis
                or private_contact_overview_analysis
                or collection_overview_analysis
                or generic_comprehensive_analysis
                or planner_comprehensive_analysis
            )
            text_only_fallback_reason = None
            if llm is None and not payload.context_only and not deterministic_full_scan:
                text_only_fallback_reason = "LLM is not configured, so I used text retrieval and returned the evidence directly."

            graph_path = _resolve_optional_graph_db_path(request, payload.graph_db_path)
            graph_retriever = _EmptyRetriever()
            global_searcher = None
            graph_store = None
            graph_quality = None
            if graph_path is not None:
                graph_store = GraphStore(graph_path)
                graph_store.initialize(reset=False)
                graph_retriever = SQLiteGraphRetriever(graph_store, include_community_summaries=True)
                if llm is not None:
                    global_searcher = GlobalSearchOrchestrator(
                        graph_store=graph_store,
                        llm_client=llm,
                        max_communities=min(payload.top_k, payload.global_community_limit),
                    )

            if payload.mode == "auto" and llm is not None:
                route_recorder = _RecordingQueryRouter(
                    AdaptiveQueryRouter(llm_client=llm),
                    default_strategy=RoutingDecision.LOCAL_SEARCH,
                    reason="Auto routing not yet evaluated",
                )
            else:
                route = _mode_to_route(payload.mode)
                route_recorder = _RecordingQueryRouter(
                    _StaticQueryRouter(route.strategy, route.reason, route.task_route),
                    default_strategy=route.strategy,
                    reason=route.reason,
                    default_task_route=route.task_route,
                )

            if self_identity_analysis:
                selected_route = QueryRoute(
                    RoutingDecision.GLOBAL_SEARCH,
                    "Detected self-identity question; executing deterministic identity scan over the current collection.",
                    QueryRouteName.COMPREHENSIVE_ANALYSIS,
                )
            elif private_contact_analysis:
                selected_route = QueryRoute(
                    RoutingDecision.GLOBAL_SEARCH,
                    "Detected WeChat/private-contact evidence question; executing deterministic full contact scan.",
                    QueryRouteName.COMPREHENSIVE_ANALYSIS,
                )
            elif private_contact_overview_analysis:
                selected_route = QueryRoute(
                    RoutingDecision.GLOBAL_SEARCH,
                    "Detected private-contact overview question; building deterministic contact overview.",
                    QueryRouteName.COMPREHENSIVE_ANALYSIS,
                )
            elif collection_overview_analysis:
                selected_route = QueryRoute(
                    RoutingDecision.GLOBAL_SEARCH,
                    "Detected vague corpus overview question; building deterministic collection overview.",
                    QueryRouteName.COMPREHENSIVE_ANALYSIS,
                )
            elif generic_comprehensive_analysis:
                selected_route = QueryRoute(
                    RoutingDecision.GLOBAL_SEARCH,
                    "Detected generic full-partition evidence analysis; executing deterministic full scan.",
                    QueryRouteName.COMPREHENSIVE_ANALYSIS,
                )
            elif planner_comprehensive_analysis:
                selected_route = QueryRoute(
                    RoutingDecision.GLOBAL_SEARCH,
                    f"Semantic planner selected {semantic_spec.coverage_scope.value} full-partition evidence scan.",
                    QueryRouteName.COMPREHENSIVE_ANALYSIS,
                )
            else:
                selected_route = route_recorder.route_query(question)
            route_recorder = _RecordingQueryRouter(
                _StaticQueryRouter(selected_route.strategy, selected_route.reason, selected_route.task_route),
                default_strategy=selected_route.strategy,
                reason=selected_route.reason,
                default_task_route=selected_route.task_route,
            )
            graph_quality_blocked_response = None
            if graph_store is not None and selected_route.strategy != RoutingDecision.VECTOR_ONLY and not deterministic_full_scan:
                graph_quality_report = evaluate_graph_quality(graph_store)
                graph_quality = graph_quality_report.to_dict()
                should_block_graph = _should_block_graph_quality(graph_quality_report)
                if graph_quality_report.gate_status != "pass" and not should_block_graph:
                    graph_quality = _mark_graph_quality_non_blocking(graph_quality)
                    logger.warning(
                        "graph_quality_gate_warn_only",
                        failures=graph_quality.get("quality_gate", {}).get("failures", []),
                        isolated_node_rate=graph_quality.get("metrics", {}).get("isolated_node_rate"),
                    )
                if should_block_graph and not payload.allow_unsafe_graph:
                    route_payload = {
                        "strategy": selected_route.strategy,
                        "reason": selected_route.reason,
                        "mode": payload.mode,
                        "task_route": selected_route.task_route.value if selected_route.task_route else None,
                    }
                    lightrag_diagnostics = _build_lightrag_diagnostics(
                        question=question,
                        route=route_payload,
                        top_k=payload.top_k,
                        citations=[],
                    )
                    triage_record = _write_graph_triage_record(
                        request,
                        question=question,
                        graph_db_path=graph_path,
                        route=route_payload,
                        graph_quality=graph_quality,
                        citations=[],
                        answer=None,
                        log_file=logger.file_name,
                        lightrag_diagnostics=lightrag_diagnostics,
                    )
                    detail = {
                        "error": "graph_quality_gate_failed",
                        "message": (
                            "Graph quality gate failed before GraphRAG answering; fix evidence, "
                            "confidence, community assignment, and summary citations, or pass "
                            "allow_unsafe_graph=true for debugging."
                        ),
                        "graph_quality": graph_quality,
                        "graph_db_path": str(graph_path),
                        "route": route_payload,
                        "lightrag_diagnostics": lightrag_diagnostics,
                        "triage_id": triage_record["id"],
                        "log_file": logger.file_name,
                    }
                    logger.error("graph_quality_gate_failed", **detail)
                    graph_quality_blocked_response = _build_graph_quality_fallback_response(
                        question=question,
                        text_retriever=text_retriever,
                        top_k=payload.top_k,
                        graph_quality=graph_quality,
                        gate_message=detail["message"],
                    )

            if graph_quality_blocked_response is not None:
                response = graph_quality_blocked_response
            elif text_only_fallback_reason is not None:
                response = _build_text_retrieval_fallback_response(
                    question=question,
                    text_retriever=text_retriever,
                    top_k=payload.top_k,
                    reason=text_only_fallback_reason,
                )
            elif self_identity_analysis:
                response = _run_self_identity_analysis(
                    text_retriever=text_retriever,
                    collection_name=collection_name,
                    question=question,
                )
            elif private_contact_analysis:
                response = _run_private_contact_comprehensive_analysis(
                    text_retriever=text_retriever,
                    collection_name=collection_name,
                    question=question,
                )
            elif private_contact_overview_analysis:
                response = _run_private_contact_overview_analysis(
                    text_retriever=text_retriever,
                    collection_name=collection_name,
                    question=question,
                )
            elif collection_overview_analysis:
                response = _run_collection_overview_analysis(
                    text_retriever=text_retriever,
                    collection_name=collection_name,
                    question=question,
                )
            elif generic_comprehensive_analysis or planner_comprehensive_analysis:
                response = _run_generic_partition_comprehensive_analysis(
                    text_retriever=text_retriever,
                    collection_name=collection_name,
                    question=question,
                )
            elif selected_route.task_route in ADVANCED_QUERY_ROUTES:
                task_spec = SemanticQueryAnalyzer().analyze(question)
                if selected_route.task_route is not None and task_spec.route != selected_route.task_route:
                    task_spec = replace(
                        task_spec,
                        route=selected_route.task_route,
                        requires_planning=selected_route.task_route == QueryRouteName.COMPREHENSIVE_ANALYSIS,
                        route_reason=selected_route.reason,
                    )
                executor = AdvancedQueryExecutor(
                    text_retriever=text_retriever,
                    graph_retriever=graph_retriever,
                    global_searcher=global_searcher,
                    llm=llm,
                )
                result = executor.execute(
                    task_spec,
                    top_k=payload.top_k,
                    context_only=payload.context_only,
                )
                response = result.to_dict()
            else:
                orchestrator = GraphRagQAOrchestrator(
                    text_retriever=text_retriever,
                    graph_retriever=graph_retriever,
                    global_searcher=global_searcher,
                    query_router=route_recorder,
                    llm=llm,
                )
                result = orchestrator.answer(
                    question,
                    top_k=payload.top_k,
                    context_only=payload.context_only,
                )
                response = result.to_dict()
            response = _ensure_unified_query_answer_contract(
                response,
                question=question,
                text_retriever=text_retriever,
                collection_name=collection_name,
                top_k=payload.top_k,
            )
            response["route"] = {
                "strategy": route_recorder.last_route.strategy,
                "reason": route_recorder.last_route.reason,
                "mode": payload.mode,
                "task_route": (
                    route_recorder.last_route.task_route.value
                    if route_recorder.last_route.task_route
                    else None
                ),
            }
            response["capabilities"] = {
                "text": True,
                "graph": graph_path is not None,
                "global": global_searcher is not None,
                "router": payload.mode == "auto" and llm is not None,
            }
            response["graph_quality"] = graph_quality
            response["graph_quality_bypassed"] = bool(
                graph_quality
                and graph_quality.get("quality_gate", {}).get("status") != "pass"
                and payload.allow_unsafe_graph
            )
            response["graph_quality_blocked"] = bool(response.get("graph_quality_blocked"))
            response["requested_collection"] = payload.collection.strip()
            response["resolved_collection"] = collection_name
            response["collection_resolution"] = collection_resolution
            response["graph_db_path"] = str(graph_path) if graph_path else None
            response["lightrag_diagnostics"] = _build_lightrag_diagnostics(
                question=question,
                route=response["route"],
                top_k=payload.top_k,
                citations=response.get("citations") or [],
            )
            if graph_store is not None and route_recorder.last_route.strategy != RoutingDecision.VECTOR_ONLY and not deterministic_full_scan:
                triage_record = _write_graph_triage_record(
                    request,
                    question=question,
                    graph_db_path=graph_path,
                    route=response["route"],
                    graph_quality=graph_quality,
                    citations=response.get("citations") or [],
                    answer=response.get("answer"),
                    log_file=logger.file_name,
                    lightrag_diagnostics=response["lightrag_diagnostics"],
                )
                response["triage_id"] = triage_record["id"]
            response["latency_ms"] = round((time.time() - t0) * 1000, 1)
            response.update(_operation_log_payload(logger))
            logger.close(
                status="ok",
                route=response["route"]["strategy"],
                citation_count=len(response.get("citations") or []),
            )
            return response
        except HTTPException as exc:
            logger.error("query_rejected", status_code=exc.status_code, detail=exc.detail)
            logger.close(status="error", status_code=exc.status_code, detail=exc.detail)
            raise
        except Exception as exc:
            logger.exception("query_failed", exc, mode=payload.mode)
            response = _build_resilient_query_failure_response(
                question=question,
                persist_dir=request.app.state.persist_dir,
                collection_name=collection_name,
                top_k=payload.top_k,
                error=exc,
            )
            response["route"] = {
                "strategy": RoutingDecision.VECTOR_ONLY,
                "reason": "Primary query path failed; returned resilient text fallback.",
                "mode": payload.mode,
                "task_route": None,
            }
            response["capabilities"] = {
                "text": True,
                "graph": graph_path is not None,
                "global": False,
                "router": False,
            }
            response["graph_quality"] = graph_quality
            response["graph_quality_bypassed"] = False
            response["graph_quality_blocked"] = False
            response["requested_collection"] = payload.collection.strip()
            response["resolved_collection"] = collection_name
            response["collection_resolution"] = collection_resolution
            response["graph_db_path"] = str(graph_path) if graph_path else None
            response["lightrag_diagnostics"] = _build_lightrag_diagnostics(
                question=question,
                route=response["route"],
                top_k=payload.top_k,
                citations=response.get("citations") or [],
                global_error=str(exc),
            )
            response["latency_ms"] = round((time.time() - t0) * 1000, 1)
            response.update(_operation_log_payload(logger))
            logger.close(
                status="fallback",
                error=str(exc),
                citation_count=len(response.get("citations") or []),
            )
            return response

    @app.post("/api/benchmark")
    async def benchmark(request: Request, payload: BenchmarkRequest):
        logger = OperationLogger(
            request.app.state.log_dir,
            "benchmark",
            collection_name=payload.collection,
            document_count=payload.document_count,
            batch_size=payload.batch_size,
            query_count=payload.query_count,
            top_k=payload.top_k,
            backend=payload.backend,
            model_name=payload.model_name,
            cleanup=payload.cleanup,
        )
        try:
            result = run_synthetic_benchmark(
                persist_dir=request.app.state.persist_dir,
                collection_name=payload.collection,
                document_count=payload.document_count,
                batch_size=payload.batch_size,
                query_count=payload.query_count,
                top_k=payload.top_k,
                backend=payload.backend,
                model_name=payload.model_name,
                cleanup=payload.cleanup,
                operation_logger=logger,
            )
            result.update(_operation_log_payload(logger))
            logger.close(
                status="ok",
                insert_docs_per_second=result.get("insert_docs_per_second"),
                query_qps=result.get("query_qps"),
            )
            return result
        except Exception as exc:
            logger.exception("benchmark_failed", exc)
            logger.close(status="error", error=str(exc))
            raise HTTPException(status_code=400, detail=f": {exc}? {logger.file_name}") from exc

    @app.delete("/api/collections/{name}")
    async def delete_collection(request: Request, name: str):
        persist_dir = request.app.state.persist_dir
        client = _create_client(persist_dir)
        try:
            client.delete_collection(name=name)
            return {"status": "ok", "deleted": name}
        except Exception as exc:
            raise HTTPException(status_code=404, detail=f"collection '{name}' not found") from exc
        finally:
            _close_client(client)

    @app.get("/api/export")
    async def export_all(request: Request):
        persist_dir = request.app.state.persist_dir
        if not persist_dir.exists() or not persist_dir.is_dir():
            raise HTTPException(status_code=404, detail="")

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_path in persist_dir.rglob("*"):
                if file_path.is_file():
                    arcname = file_path.relative_to(persist_dir)
                    zf.write(file_path, arcname)
        buffer.seek(0)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"chroma_db_export_{timestamp}.zip"
        return StreamingResponse(
            buffer,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.get("/api/chroma/export")
    async def export_chroma_db(request: Request):
        return await export_all(request)

    @app.get("/api/export/{collection_name}")
    async def export_collection(request: Request, collection_name: str):
        persist_dir = request.app.state.persist_dir
        client = _create_client(persist_dir)
        try:
            collection = client.get_collection(name=collection_name)
            count = collection.count()
            if count == 0:
                data = {"collection": collection_name, "count": 0, "ids": [], "documents": [], "metadatas": []}
            else:
                result = collection.get(
                    include=["documents", "metadatas"],
                    limit=count,
                )
                data = {
                    "collection": collection_name,
                    "count": count,
                    "ids": result.get("ids", []),
                    "documents": result.get("documents", []),
                    "metadatas": result.get("metadatas", []),
                }
        except Exception as exc:
            raise HTTPException(status_code=404, detail=f" '{collection_name}' : {exc}") from exc
        finally:
            _close_client(client)

        json_bytes = orjson.dumps(data, option=orjson.OPT_INDENT_2)
        buffer = io.BytesIO(json_bytes)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{collection_name}_{timestamp}.json"
        return StreamingResponse(
            buffer,
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    if resolved_frontend_dir is not None and resolved_frontend_dir.exists():
        libs_dir = resolved_frontend_dir / "libs"
        assets_dir = resolved_frontend_dir / "assets"
        if libs_dir.exists():
            app.mount("/libs", StaticFiles(directory=str(libs_dir)), name="libs")
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")
        app.mount("/static", StaticFiles(directory=str(resolved_frontend_dir)), name="static")
    if resolved_deliverables_dir.exists():
        app.mount("/deliverables", StaticFiles(directory=str(resolved_deliverables_dir)), name="deliverables")

    return app
