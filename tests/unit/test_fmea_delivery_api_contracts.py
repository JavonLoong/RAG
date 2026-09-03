from __future__ import annotations

import pytest
from chroma_rag_poc.fmea_delivery_contracts import (
    ExportNarrativeRunRequest,
    ExportRunRequest,
    MigrationConfirmationRequest,
    MigrationDryRunRequest,
    TemplatePatchAcceptanceRequest,
    TemplatePatchRunRequest,
)
from pydantic import ValidationError


def test_delivery_write_contracts_are_strict_and_server_owned() -> None:
    patch = {
        "input_template_version": "1.0.0",
        "target_template_id": "fmea-template",
        "target_template_version": "2.0.0",
        "target_template_hash": "sha256:" + "a" * 64,
        "domain_pack_id": "domain-pack",
        "domain_pack_version": "1.0.0",
        "domain_pack_hash": "sha256:" + "b" * 64,
        "evidence_pack_id": "evidence-pack",
        "evidence_pack_hash": "sha256:" + "c" * 64,
    }
    with pytest.raises(ValidationError):
        TemplatePatchRunRequest.model_validate({**patch, "provider": "client-controlled"})

    export = {
        "snapshot_id": "snapshot-1",
        "snapshot_hash": "sha256:" + "d" * 64,
        "format": "json",
        "draft_preview": True,
    }
    with pytest.raises(ValidationError):
        ExportRunRequest.model_validate({**export, "artifact_root": "C:/client"})

    assert "filename" not in ExportRunRequest.model_fields
    assert "repository" not in ExportRunRequest.model_fields
    assert "adapter" not in MigrationDryRunRequest.model_fields


def test_confirmation_contracts_require_exact_confirmation_values() -> None:
    acceptance = {
        "suggestion_id": "suggestion-1",
        "patch_id": "patch-1",
        "draft_id": "draft-1",
        "draft_sha256": "sha256:" + "a" * 64,
        "target_template_version": "2.0.0",
        "target_template_hash": "sha256:" + "b" * 64,
        "new_template_version": "2.1.0",
        "domain_pack_hash": "sha256:" + "c" * 64,
        "evidence_pack_hash": "sha256:" + "d" * 64,
        "confirm_template_change": True,
    }
    assert TemplatePatchAcceptanceRequest.model_validate(acceptance).confirm_template_change is True

    with pytest.raises(ValidationError):
        MigrationConfirmationRequest.model_validate({
            "migration_id": "migration-1",
            "report_hash": "sha256:" + "a" * 64,
            "source_revision_id": "revision-1",
            "source_revision_hash": "sha256:" + "b" * 64,
            "target_domain_pack_id": "domain-pack",
            "target_domain_pack_version": "1.0.0",
            "target_domain_pack_hash": "sha256:" + "c" * 64,
            "dry_run": {
                "migration_id": "migration-1",
                "source_revision_hash": "sha256:" + "b" * 64,
                "target_domain_pack_id": "domain-pack",
                "target_domain_pack_version": "1.0.0",
                "target_domain_pack_hash": "sha256:" + "c" * 64,
            },
            "confirm_migration": False,
        })


def test_narrative_request_is_suggestion_only() -> None:
    request = ExportNarrativeRunRequest.model_validate({
        "snapshot_id": "snapshot-1",
        "snapshot_hash": "sha256:" + "a" * 64,
    })
    assert request.model_dump() == {
        "snapshot_id": "snapshot-1",
        "snapshot_hash": "sha256:" + "a" * 64,
        "publication_id": None,
    }
