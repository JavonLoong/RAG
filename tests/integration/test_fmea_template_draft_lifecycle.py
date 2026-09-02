from __future__ import annotations

from dataclasses import dataclass, replace

import pytest

from core_domain.fmea.states import ActorType
from fmea_application import ActorContext, ReviewError
from fmea_application.domain_pack_service import (
    AcceptTemplatePatchCommand,
    DomainPackService,
    ImportTemplateCommand,
    RejectTemplatePatchCommand,
    SuggestTemplatePatchCommand,
)
from fmea_infrastructure.template_import_excel import ExcelTemplateImporter
from fmea_infrastructure.template_patch_generator import TemplatePatchGenerator
from tests.unit.test_fmea_template_import_excel import _xlsx

HASH = "a" * 64
TIMESTAMP = "2026-08-27T12:00:00Z"


class _FakeGateway:
    def generate(self, request: object) -> object:
        return {
            "diff": ({"op": "replace", "path": "/fields/failure_mode", "value": "Failure Mode"},),
            "evidence_ids": (),
        }


@dataclass
class _Compiled:
    template_id: str = "template-1"
    version: str = "1.0.0"


class _Compiler:
    def __init__(self) -> None:
        self.calls = 0

    def compile(self, source: object) -> _Compiled:
        self.calls += 1
        return _Compiled()


class _Registry:
    def __init__(self) -> None:
        self.calls = 0

    def register(self, template: object, source_bytes: bytes, source_suffix: str) -> object:
        self.calls += 1
        return template


def _actor(*, roles: frozenset[str], actor_type: ActorType = ActorType.HUMAN) -> ActorContext:
    return ActorContext(actor_id="actor-1", actor_type=actor_type, roles=roles, workspace_id="ws-1")


def _service() -> tuple[DomainPackService, _Compiler, _Registry]:
    compiler = _Compiler()
    registry = _Registry()
    service = DomainPackService(
        importers={"xlsx": ExcelTemplateImporter(clock=lambda: TIMESTAMP)},
        patch_generator=TemplatePatchGenerator(_FakeGateway(), clock=lambda: TIMESTAMP),
        compiler=compiler,
        registry=registry,
        clock=lambda: TIMESTAMP,
    )
    return service, compiler, registry


def _suggest_command(draft_id: str) -> SuggestTemplatePatchCommand:
    return SuggestTemplatePatchCommand(
        draft_id=draft_id,
        patch_id="patch-1",
        input_template_version="1.0.0",
        target_template_id="template-1",
        target_template_version="1.0.0",
        target_template_hash=HASH,
        domain_pack_id="generic-domain",
        domain_pack_version="1.0.0",
        domain_pack_hash=HASH,
        evidence_pack_id="evidence-pack-1",
        evidence_pack_hash=HASH,
        run_id="run-1",
        trace_id="trace-1",
        model_version="deterministic-fake",
        prompt_version="template-mapping-v1",
    )


def _accept_command(draft_id: str = "draft-1", draft_sha256: str = HASH) -> AcceptTemplatePatchCommand:
    return AcceptTemplatePatchCommand(
        suggestion_id="template-patch-suggestion-patch-1",
        patch_id="patch-1",
        draft_id=draft_id,
        draft_sha256=draft_sha256,
        target_template_version="1.0.0",
        target_template_hash=HASH,
        domain_pack_hash=HASH,
        evidence_pack_hash=HASH,
        confirm_template_change=True,
    )


def test_import_and_suggest_create_only_immutable_draft_and_patch_suggestion() -> None:
    service, compiler, registry = _service()
    draft = service.import_template(
        ImportTemplateCommand(raw_bytes=_xlsx(), filename="fmea.xlsx", workspace_id="ws-1"),
        _actor(roles=frozenset()),
    )
    suggestion = service.suggest_patch(
        _suggest_command(draft.draft_id), _actor(roles=frozenset(), actor_type=ActorType.MODEL)
    )

    assert draft.status.value == "draft"
    assert suggestion.applied is False
    assert compiler.calls == 0
    assert registry.calls == 0


def test_model_and_non_admin_cannot_accept_but_template_admin_compiles_and_registers_once() -> None:
    service, compiler, registry = _service()
    draft = service.import_template(
        ImportTemplateCommand(raw_bytes=_xlsx(), filename="fmea.xlsx", workspace_id="ws-1"),
        _actor(roles=frozenset()),
    )
    service.suggest_patch(_suggest_command(draft.draft_id), _actor(roles=frozenset(), actor_type=ActorType.MODEL))

    with pytest.raises(ReviewError, match="FMEA_TEMPLATE_ADMIN_REQUIRED"):
        service.accept_patch(_accept_command(), _actor(roles=frozenset({"template_admin"}), actor_type=ActorType.MODEL))
    with pytest.raises(ReviewError, match="FMEA_TEMPLATE_ADMIN_REQUIRED"):
        service.accept_patch(_accept_command(), _actor(roles=frozenset({"reviewer"})))

    compiled = service.accept_patch(
        _accept_command(draft.draft_id, draft.source_sha256), _actor(roles=frozenset({"template_admin"}))
    )
    assert compiled.template_id == "template-1"
    assert (compiler.calls, registry.calls) == (1, 1)
    with pytest.raises(ReviewError, match="already|decided|replay"):
        service.accept_patch(
            _accept_command(draft.draft_id, draft.source_sha256), _actor(roles=frozenset({"template_admin"}))
        )


def test_stale_cross_workspace_and_rejected_candidates_fail_closed() -> None:
    service, compiler, registry = _service()
    draft = service.import_template(
        ImportTemplateCommand(raw_bytes=_xlsx(), filename="fmea.xlsx", workspace_id="ws-1"),
        _actor(roles=frozenset()),
    )
    service.suggest_patch(_suggest_command(draft.draft_id), _actor(roles=frozenset(), actor_type=ActorType.MODEL))
    with pytest.raises(ReviewError, match="version|hash|stale"):
        service.accept_patch(
            replace(_accept_command(draft.draft_id, draft.source_sha256), draft_sha256="b" * 64),
            _actor(roles=frozenset({"template_admin"})),
        )
    rejected = service.reject_patch(
        RejectTemplatePatchCommand(
            suggestion_id="template-patch-suggestion-patch-1", patch_id="patch-1", reason="ambiguous"
        ),
        _actor(roles=frozenset({"template_admin"})),
    )
    assert rejected.status.value == "suggested"
    assert compiler.calls == registry.calls == 0
