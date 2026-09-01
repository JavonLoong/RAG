from __future__ import annotations

import base64
import hashlib
import json

import pytest


def test_governance_requests_are_strict_and_bounded() -> None:
    from chroma_rag_poc.fmea_governance_contracts import (
        GovernanceEnvelope,
        PublicationBody,
        RevisionAssemblyBody,
        SupersessionBody,
    )
    from pydantic import ValidationError

    assert GovernanceEnvelope.model_fields["schema_version"].default == "graphrag.fmea.v1"
    assert RevisionAssemblyBody.model_validate({"confirm_human_approval": True}).confirm_human_approval is True
    with pytest.raises(ValidationError):
        PublicationBody.model_validate({"approval_id": "approval-1", "unexpected": "override"})
    with pytest.raises(ValidationError):
        SupersessionBody.model_validate({
            "replacement_publication_id": "publication-2",
            "replacement_record_version": 0,
            "reason": "replace",
            "confirm_supersession": True,
        })


def test_revision_projection_uses_repository_version_not_analysis_version() -> None:
    from chroma_rag_poc.fmea_governance_contracts import revision_data

    revision = type(
        "Revision",
        (),
        {
            "revision_id": "revision-1",
            "workspace_id": "ws-1",
            "analysis_id": "analysis-1",
            "analysis_record_version": 3,
            "analysis_hash": "sha256:" + "a" * 64,
            "parent_revision_id": None,
            "parent_revision_hash": None,
            "row_versions": (),
            "risk_versions": (),
            "propagation_graph_revision_id": None,
            "propagation_graph_hash": None,
            "evidence_pack_hashes": (),
            "retrieval_provenance": type(
                "Retrieval",
                (),
                {
                    "requested_profile": "default",
                    "resolved_profile": "default",
                    "evidence_types": (),
                    "source_counts": (),
                    "warnings": (),
                },
            )(),
            "domain_pack_identity": ("domain", "1.0.0", "sha256:" + "b" * 64),
            "template_identities": (),
            "scoring_rule_identities": (),
            "propagation_rule_identity": None,
            "unresolved_items": (),
            "revision_hash": "sha256:" + "c" * 64,
            "created_at": "2026-08-30T00:00:00Z",
        },
    )()

    projected = revision_data(revision, record_version=11)
    assert projected.record_version == 11
    assert projected.analysis_record_version == 3


def test_governance_service_exposes_repository_backed_revision_version() -> None:
    from fmea_governance_fixtures import make_fmea_revision, make_governance_actor

    from fmea_application.governance_service import RevisionGovernanceService

    revision = make_fmea_revision(analysis_record_version=3)

    class Repository:
        def get_revision(self, revision_id: str, workspace_id: str):
            return revision if (revision_id, workspace_id) == (revision.revision_id, revision.workspace_id) else None

        def get_revision_record_version(self, revision_id: str, workspace_id: str):
            return 11 if (revision_id, workspace_id) == (revision.revision_id, revision.workspace_id) else None

    actual, record_version = RevisionGovernanceService(Repository(), None, None).get_revision_record(
        revision.revision_id, make_governance_actor()
    )
    assert actual is revision
    assert record_version == 11


def test_default_governance_runtime_acquires_the_application_service_from_sqlite(tmp_path) -> None:
    from chroma_rag_poc.workspace_registry import WorkspaceConfig

    from core_domain.query_contracts import QueryMode
    from fmea_application.governance_service import RevisionGovernanceService
    from fmea_infrastructure.composition import build_default_workspace_governance_runtime

    workspace = WorkspaceConfig(
        workspace_id="ws-1",
        chroma_persist_dir=tmp_path / "chroma",
        chroma_collection="fmea",
        graph_db_path=tmp_path / "graph.sqlite3",
        fmea_db_path=tmp_path / "fmea.sqlite3",
        fmea_template_registry_path=tmp_path / "templates",
        supported_modes=frozenset({QueryMode.VECTOR}),
        default_mode=QueryMode.VECTOR,
    )
    runtime = build_default_workspace_governance_runtime(workspace)

    assert isinstance(runtime.service, RevisionGovernanceService)
    assert runtime.service._repository is runtime.repository


def test_history_cursor_is_signed_bound_and_does_not_expose_inner_cursor() -> None:
    from chroma_rag_poc.fmea_governance_contracts import decode_history_cursor, encode_history_cursor

    secret = b"s" * 32
    filter_hash = hashlib.sha256(b"{}").hexdigest()
    inner = "2026-08-30T00:00:00Z|event-1"
    cursor = encode_history_cursor(
        secret,
        workspace_id="ws-1",
        resource_type="revision",
        resource_id="revision-1",
        descending=False,
        page_size=25,
        filter_hash=filter_hash,
        repository_cursor=inner,
    )
    assert inner not in cursor
    outer_payload = base64.urlsafe_b64decode(cursor.split(".", 1)[0] + "==")
    assert inner.encode("ascii") not in outer_payload
    with pytest.raises((UnicodeDecodeError, ValueError, json.JSONDecodeError)):
        json.loads(outer_payload.decode("ascii"))
    assert (
        decode_history_cursor(
            secret,
            cursor,
            workspace_id="ws-1",
            resource_type="revision",
            resource_id="revision-1",
            descending=False,
            page_size=25,
            filter_hash=filter_hash,
        )
        == inner
    )
    for kwargs in (
        {"workspace_id": "ws-2"},
        {"resource_type": "publication"},
        {"resource_id": "revision-2"},
        {"page_size": 50},
        {"descending": True},
        {"filter_hash": hashlib.sha256(b"changed").hexdigest()},
    ):
        expected = {
            "workspace_id": "ws-1",
            "resource_type": "revision",
            "resource_id": "revision-1",
            "descending": False,
            "page_size": 25,
            "filter_hash": filter_hash,
        }
        expected.update(kwargs)
        with pytest.raises(ValueError):
            decode_history_cursor(secret, cursor, **expected)
    with pytest.raises(ValueError):
        decode_history_cursor(
            secret,
            cursor[:-1] + ("A" if cursor[-1] != "A" else "B"),
            workspace_id="ws-1",
            resource_type="revision",
            resource_id="revision-1",
            descending=False,
            page_size=25,
            filter_hash=filter_hash,
        )


def test_success_envelope_has_shared_schema_and_trace_metadata() -> None:
    from chroma_rag_poc.fmea_governance_contracts import governance_envelope

    payload = governance_envelope(
        "revision",
        {"revision_id": "revision-1"},
        request_id="request-1",
        trace_id="trace-1",
    )
    assert payload == {
        "schema_version": "graphrag.fmea.v1",
        "resource_type": "revision",
        "resource_version": "1.0.0",
        "request_id": "request-1",
        "trace_id": "trace-1",
        "data": {"revision_id": "revision-1"},
    }
