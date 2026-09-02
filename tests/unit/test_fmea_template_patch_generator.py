from __future__ import annotations

from dataclasses import replace

import pytest

from fmea_application.assistance_contracts import AssistanceKind, AssistanceSuggestion
from fmea_infrastructure.template_import_excel import ExcelTemplateImporter
from fmea_infrastructure.template_patch_generator import TemplatePatchGenerator, TemplatePatchRequest
from tests.unit.test_fmea_template_import_excel import _xlsx

HASH = "a" * 64
TIMESTAMP = "2026-08-27T12:00:00Z"


class _FakeGateway:
    def __init__(self, response: object) -> None:
        self.response = response
        self.requests: list[object] = []

    def generate(self, request: object) -> object:
        self.requests.append(request)
        return self.response


def _request(**overrides: object) -> TemplatePatchRequest:
    draft = ExcelTemplateImporter(clock=lambda: TIMESTAMP).parse(_xlsx(), "fmea.xlsx", workspace_id="ws-1")
    values: dict[str, object] = {
        "patch_id": "patch-1",
        "draft": draft,
        "input_template_version": "1.0.0",
        "target_template_id": "template-1",
        "target_template_version": "1.0.0",
        "target_template_hash": HASH,
        "domain_pack_id": "generic-domain",
        "domain_pack_version": "1.0.0",
        "domain_pack_hash": HASH,
        "evidence_pack_id": "evidence-pack-1",
        "evidence_pack_hash": HASH,
        "run_id": "run-1",
        "trace_id": "trace-1",
        "model_version": "deterministic-fake",
        "prompt_version": "template-mapping-v1",
        "created_at": TIMESTAMP,
    }
    values.update(overrides)
    return TemplatePatchRequest(**values)


def test_provider_neutral_generator_returns_unapplied_suggestion_with_exact_provenance() -> None:
    gateway = _FakeGateway({
        "diff": ({"op": "replace", "path": "/fields/failure_mode", "value": "Failure Mode"},),
        "evidence_ids": ("evidence-1",),
    })
    suggestion = TemplatePatchGenerator(gateway, clock=lambda: TIMESTAMP).suggest(_request())

    assert isinstance(suggestion, AssistanceSuggestion)
    assert suggestion.kind is AssistanceKind.TEMPLATE_FIELD_MAPPING
    assert suggestion.applied is False
    assert suggestion.payload["patch_id"] == "patch-1"
    assert suggestion.payload["target_template_hash"] == HASH
    assert suggestion.payload["domain_pack_hash"] == HASH
    assert suggestion.payload["evidence_pack_hash"] == HASH
    assert suggestion.payload["run_id"] == "run-1"
    assert suggestion.payload["trace_id"] == "trace-1"
    assert len(gateway.requests) == 1


@pytest.mark.parametrize(
    "response",
    (
        {"diff": ({"op": "add", "path": "/fields/x", "value": "https://example.invalid"},), "evidence_ids": ()},
        {"diff": ({"op": "add", "path": "/fields/x", "value": {"code": "exec('x')"}},), "evidence_ids": ()},
        {"diff": (), "evidence_ids": (), "unexpected": True},
    ),
)
def test_patch_generator_rejects_injection_extra_keys_and_non_declarative_values(response: object) -> None:
    with pytest.raises(Exception, match="invalid|declarative|unsupported|forbidden"):
        TemplatePatchGenerator(_FakeGateway(response)).suggest(_request())


def test_patch_request_is_immutable_and_bound_to_the_draft_workspace() -> None:
    request = _request()
    with pytest.raises((AttributeError, TypeError)):
        request.patch_id = "changed"  # type: ignore[misc]
    with pytest.raises(Exception, match="workspace|draft"):
        TemplatePatchGenerator(_FakeGateway({"diff": (), "evidence_ids": ()})).suggest(
            replace(request, draft=object())  # type: ignore[arg-type]
        )
