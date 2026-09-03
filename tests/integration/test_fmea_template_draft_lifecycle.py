from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from threading import Event

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
from fmea_application.template_patch_contracts import normalize_source_mapping_key
from fmea_infrastructure.template_import_excel import ExcelTemplateImporter
from fmea_infrastructure.template_patch_generator import TemplatePatchGenerator
from structured_output_application import TemplateCompiler
from structured_output_infrastructure import Draft202012SchemaAdapter, FileTemplateRegistry, load_template_source
from tests.unit.test_fmea_template_import_excel import _xlsx
from tests.unit.test_fmea_template_patch_generator import PACK

HASH = "a" * 64
TIMESTAMP = "2026-08-27T12:00:00Z"


class _FakeGateway:
    def generate(self, request: object) -> object:
        return {
            "diff": (
                {
                    "op": "replace",
                    "path": "/fields/failure_mode",
                    "value": {"type": "string", "title": "Failure Mode"},
                },
            ),
            "evidence_ids": (),
        }


@dataclass
class _Compiled:
    template_id: str = "template-1"
    version: str = "1.0.0"
    template_hash: str = HASH
    canonical_json: str = json.dumps(
        {
            "template": {
                "id": "template-1",
                "version": "1.0.0",
                "title": "Base",
                "description": "",
                "domain_tags": ["generic-fmea"],
                "schema_dialect": "https://json-schema.org/draft/2020-12/schema",
            },
            "output_schema": {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "properties": {"failure_mode": {"type": "string"}},
                "additionalProperties": False,
            },
            "evidence_bindings": [],
        },
        sort_keys=True,
        separators=(",", ":"),
    )


class _Compiler:
    def __init__(self) -> None:
        self.calls = 0

    def compile(self, source: object) -> _Compiled:
        self.calls += 1
        assert isinstance(source, dict)
        metadata = source["template"]
        assert isinstance(metadata, dict)
        return _Compiled(
            version=str(metadata["version"]), canonical_json=json.dumps(source, sort_keys=True, separators=(",", ":"))
        )


class _Registry:
    def __init__(self) -> None:
        self.calls = 0

    def register(self, template: object, source_bytes: bytes, source_suffix: str) -> object:
        self.calls += 1
        return template

    def get(self, template_id: str, version: str) -> _Compiled:
        assert (template_id, version) == ("template-1", "1.0.0")
        return _Compiled()


class _EvidenceProvider:
    def load_pack(self, workspace_id: str, pack_id: str):
        assert (workspace_id, pack_id) == (PACK.workspace_id, PACK.pack_id)
        return PACK


def _actor(*, roles: frozenset[str], actor_type: ActorType = ActorType.HUMAN) -> ActorContext:
    return ActorContext(actor_id="actor-1", actor_type=actor_type, roles=roles, workspace_id="ws-1")


def _service(gateway: object | None = None) -> tuple[DomainPackService, _Compiler, _Registry]:
    compiler = _Compiler()
    registry = _Registry()
    service = DomainPackService(
        importers={"xlsx": ExcelTemplateImporter(clock=lambda: TIMESTAMP)},
        patch_generator=TemplatePatchGenerator(gateway or _FakeGateway(), clock=lambda: TIMESTAMP),
        evidence_provider=_EvidenceProvider(),
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
        evidence_pack_hash=PACK.pack_hash,
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
        new_template_version="1.1.0",
        domain_pack_hash=HASH,
        evidence_pack_hash=PACK.pack_hash,
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
    assert suggestion.payload.patch_id == "patch-1"
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
    assert rejected.action == "rejected"
    assert rejected.reason == "ambiguous"
    assert service.decision_for_patch("patch-1", _actor(roles=frozenset())) == rejected
    assert compiler.calls == registry.calls == 0


def test_accept_applies_exact_patch_to_verified_base_and_registers_new_version(tmp_path) -> None:
    schema_adapter = Draft202012SchemaAdapter()
    compiler = TemplateCompiler(schema_validator=schema_adapter, source_loader=load_template_source)
    registry = FileTemplateRegistry(tmp_path / "registry")
    base_source = {
        "template": {
            "id": "template-1",
            "version": "1.0.0",
            "title": "Base FMEA",
            "description": "base",
            "domain_tags": ["generic-fmea"],
            "schema_dialect": "https://json-schema.org/draft/2020-12/schema",
        },
        "output_schema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {"failure_mode": {"type": "string", "title": "Old"}},
            "additionalProperties": False,
        },
        "evidence_bindings": [],
    }
    base_bytes = json.dumps(base_source, sort_keys=True, separators=(",", ":")).encode()
    base = registry.register(compiler.compile(base_source), base_bytes, ".json")

    class _SemanticGateway:
        def generate(self, request: object) -> object:
            return {
                "diff": (
                    {
                        "op": "replace",
                        "path": "/fields/failure_mode",
                        "value": {"type": "string", "title": "Failure Mode"},
                    },
                    {
                        "op": "add",
                        "path": "/fields/criticality",
                        "value": {"type": "integer", "minimum": 1, "maximum": 5},
                    },
                    {
                        "op": "add",
                        "path": f"/mappings/{normalize_source_mapping_key('Legacy Criticality')}",
                        "value": "criticality",
                    },
                ),
                "evidence_ids": (),
            }

    service = DomainPackService(
        importers={"xlsx": ExcelTemplateImporter(clock=lambda: TIMESTAMP)},
        patch_generator=TemplatePatchGenerator(_SemanticGateway(), clock=lambda: TIMESTAMP),
        evidence_provider=_EvidenceProvider(),
        compiler=compiler,
        registry=registry,
        clock=lambda: TIMESTAMP,
    )
    draft = service.import_template(
        ImportTemplateCommand(raw_bytes=_xlsx(), filename="fmea.xlsx", workspace_id="ws-1"),
        _actor(roles=frozenset()),
    )
    command = replace(_suggest_command(draft.draft_id), target_template_hash=base.template_hash)
    service.suggest_patch(command, _actor(roles=frozenset(), actor_type=ActorType.MODEL))
    registered = service.accept_patch(
        replace(
            _accept_command(draft.draft_id, draft.source_sha256),
            target_template_hash=base.template_hash,
            new_template_version="1.1.0",
        ),
        _actor(roles=frozenset({"template_admin"})),
    )

    assert registered.metadata.version == "1.1.0"
    assert registry.get("template-1", "1.0.0").template_hash == base.template_hash
    stored = registry.get("template-1", "1.1.0")
    assert stored.output_schema["properties"] == {
        "failure_mode": {"type": "string", "title": "Failure Mode"},
        "criticality": {"type": "integer", "minimum": 1, "maximum": 5},
    }
    assert stored.source_mappings == {
        normalize_source_mapping_key("Failure Mode"): "failure_mode",
        normalize_source_mapping_key("Legacy Criticality"): "criticality",
    }

    class _SecondGateway:
        def generate(self, request: object) -> object:
            return {
                "diff": (
                    {
                        "op": "replace",
                        "path": "/fields/criticality",
                        "value": {"type": "integer", "minimum": 1, "maximum": 10},
                    },
                ),
                "evidence_ids": (),
            }

    second_service = DomainPackService(
        importers={"xlsx": ExcelTemplateImporter(clock=lambda: TIMESTAMP)},
        patch_generator=TemplatePatchGenerator(_SecondGateway(), clock=lambda: TIMESTAMP),
        evidence_provider=_EvidenceProvider(),
        compiler=compiler,
        registry=registry,
        clock=lambda: TIMESTAMP,
    )
    second_draft = second_service.import_template(
        ImportTemplateCommand(raw_bytes=_xlsx(), filename="fmea.xlsx", workspace_id="ws-1"),
        _actor(roles=frozenset()),
    )
    second_suggest = replace(
        _suggest_command(second_draft.draft_id),
        patch_id="patch-2",
        input_template_version="1.1.0",
        target_template_version="1.1.0",
        target_template_hash=stored.template_hash,
        run_id="run-2",
        trace_id="trace-2",
    )
    second_service.suggest_patch(
        second_suggest,
        _actor(roles=frozenset(), actor_type=ActorType.MODEL),
    )
    second_registered = second_service.accept_patch(
        replace(
            _accept_command(second_draft.draft_id, second_draft.source_sha256),
            suggestion_id="template-patch-suggestion-patch-2",
            patch_id="patch-2",
            target_template_version="1.1.0",
            target_template_hash=stored.template_hash,
            new_template_version="1.2.0",
        ),
        _actor(roles=frozenset({"template_admin"})),
    )

    assert second_registered.metadata.version == "1.2.0"
    assert second_registered.output_schema["properties"]["criticality"]["maximum"] == 10
    assert second_registered.source_mappings == stored.source_mappings


def test_accept_is_process_local_serialized_and_records_one_decision() -> None:
    service, compiler, registry = _service()
    draft = service.import_template(
        ImportTemplateCommand(raw_bytes=_xlsx(), filename="fmea.xlsx", workspace_id="ws-1"),
        _actor(roles=frozenset()),
    )
    service.suggest_patch(_suggest_command(draft.draft_id), _actor(roles=frozenset(), actor_type=ActorType.MODEL))
    command = _accept_command(draft.draft_id, draft.source_sha256)
    admin = _actor(roles=frozenset({"template_admin"}))

    def accept_once() -> str:
        try:
            service.accept_patch(command, admin)
        except ReviewError:
            return "conflict"
        return "accepted"

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = tuple(executor.map(lambda _index: accept_once(), range(4)))

    assert results.count("accepted") == 1
    assert (compiler.calls, registry.calls) == (1, 1)
    decision = service.decision_for_patch("patch-1", admin)
    assert decision is not None and decision.action == "accepted"
    assert decision.new_template_version == "1.1.0"
    assert decision.candidate.diff[0]["path"] == "/fields/failure_mode"


def test_suggest_reserves_patch_identity_before_model_generation() -> None:
    entered = Event()
    release = Event()

    class _BlockingGateway:
        def generate(self, request: object) -> object:
            entered.set()
            assert release.wait(timeout=2)
            return {"diff": (), "evidence_ids": ()}

    service, _, _ = _service(_BlockingGateway())
    draft = service.import_template(
        ImportTemplateCommand(raw_bytes=_xlsx(), filename="fmea.xlsx", workspace_id="ws-1"),
        _actor(roles=frozenset()),
    )
    command = _suggest_command(draft.draft_id)
    model = _actor(roles=frozenset(), actor_type=ActorType.MODEL)

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(service.suggest_patch, command, model)
        assert entered.wait(timeout=2)
        with pytest.raises(ReviewError, match="already|progress|reserved"):
            service.suggest_patch(command, model)
        release.set()
        suggestion = first.result(timeout=2)

    assert suggestion.candidate.patch_id == "patch-1"


def test_failed_registration_leaves_no_decision_and_allows_bounded_retry() -> None:
    class _FailOnceRegistry(_Registry):
        def register(self, template: object, source_bytes: bytes, source_suffix: str) -> object:
            self.calls += 1
            if self.calls == 1:
                raise OSError("temporary")
            return template

    compiler = _Compiler()
    registry = _FailOnceRegistry()
    service = DomainPackService(
        importers={"xlsx": ExcelTemplateImporter(clock=lambda: TIMESTAMP)},
        patch_generator=TemplatePatchGenerator(_FakeGateway(), clock=lambda: TIMESTAMP),
        evidence_provider=_EvidenceProvider(),
        compiler=compiler,
        registry=registry,
        clock=lambda: TIMESTAMP,
    )
    admin = _actor(roles=frozenset({"template_admin"}))
    draft = service.import_template(
        ImportTemplateCommand(raw_bytes=_xlsx(), filename="fmea.xlsx", workspace_id="ws-1"),
        _actor(roles=frozenset()),
    )
    service.suggest_patch(_suggest_command(draft.draft_id), _actor(roles=frozenset(), actor_type=ActorType.MODEL))
    command = _accept_command(draft.draft_id, draft.source_sha256)

    with pytest.raises(ReviewError, match="storage|registration"):
        service.accept_patch(command, admin)
    assert service.decision_for_patch("patch-1", admin) is None
    service.accept_patch(command, admin)
    assert service.decision_for_patch("patch-1", admin).action == "accepted"  # type: ignore[union-attr]
    assert registry.calls == 2


def test_accept_rejects_non_higher_output_version_before_compilation() -> None:
    service, compiler, registry = _service()
    draft = service.import_template(
        ImportTemplateCommand(raw_bytes=_xlsx(), filename="fmea.xlsx", workspace_id="ws-1"),
        _actor(roles=frozenset()),
    )
    service.suggest_patch(_suggest_command(draft.draft_id), _actor(roles=frozenset(), actor_type=ActorType.MODEL))
    with pytest.raises(ReviewError, match="higher"):
        service.accept_patch(
            replace(_accept_command(draft.draft_id, draft.source_sha256), new_template_version="1.0.0"),
            _actor(roles=frozenset({"template_admin"})),
        )
    assert (compiler.calls, registry.calls) == (0, 0)


def test_mapping_operations_use_imported_mapping_state_exactly() -> None:
    class _MappingGateway:
        def generate(self, request: object) -> object:
            return {
                "diff": (
                    {
                        "op": "add",
                        "path": f"/mappings/{normalize_source_mapping_key('Failure Mode')}",
                        "value": "failure_mode",
                    },
                ),
                "evidence_ids": (),
            }

    service, compiler, registry = _service(_MappingGateway())
    draft = service.import_template(
        ImportTemplateCommand(raw_bytes=_xlsx(), filename="fmea.xlsx", workspace_id="ws-1"),
        _actor(roles=frozenset()),
    )
    service.suggest_patch(_suggest_command(draft.draft_id), _actor(roles=frozenset(), actor_type=ActorType.MODEL))
    with pytest.raises(ReviewError, match="already exists"):
        service.accept_patch(
            _accept_command(draft.draft_id, draft.source_sha256),
            _actor(roles=frozenset({"template_admin"})),
        )
    assert (compiler.calls, registry.calls) == (0, 0)
