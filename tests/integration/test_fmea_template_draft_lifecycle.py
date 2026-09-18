from __future__ import annotations

import json
import shutil
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path
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
from fmea_application.review_contracts import IdempotencyScope, idempotency_key_hash
from fmea_application.template_patch_contracts import TemplatePatchDecision, normalize_source_mapping_key
from fmea_infrastructure.delivery_repository_sqlite import (
    SqliteFmeaDeliveryRepository,
    _contract_json,
    _json_value,
)
from fmea_infrastructure.repository_sqlite import SqliteFmeaRepository
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


def _durable_service(
    repository: SqliteFmeaDeliveryRepository,
    *,
    gateway: object | None = None,
    compiler: object | None = None,
    registry: object | None = None,
) -> tuple[DomainPackService, object, object]:
    actual_compiler = compiler or _Compiler()
    actual_registry = registry or _Registry()
    service = DomainPackService(
        importers={"xlsx": ExcelTemplateImporter(clock=lambda: TIMESTAMP)},
        patch_generator=TemplatePatchGenerator(gateway or _FakeGateway(), clock=lambda: TIMESTAMP),
        evidence_provider=_EvidenceProvider(),
        compiler=actual_compiler,
        registry=actual_registry,
        workflow_repository=repository,
        clock=lambda: TIMESTAMP,
    )
    return service, actual_compiler, actual_registry


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


def test_template_workflow_survives_service_restarts_with_versions_and_idempotency(tmp_path) -> None:
    repository = SqliteFmeaDeliveryRepository(tmp_path / "fmea.db")
    repository.initialize()
    compiler = _Compiler()
    registry = _Registry()

    def service() -> DomainPackService:
        return DomainPackService(
            importers={"xlsx": ExcelTemplateImporter(clock=lambda: TIMESTAMP)},
            patch_generator=TemplatePatchGenerator(_FakeGateway(), clock=lambda: TIMESTAMP),
            evidence_provider=_EvidenceProvider(),
            compiler=compiler,
            registry=registry,
            workflow_repository=repository,
            clock=lambda: TIMESTAMP,
        )

    draft = service().import_template(
        ImportTemplateCommand(
            raw_bytes=_xlsx(),
            filename="fmea.xlsx",
            workspace_id="ws-1",
            idempotency_key="00000000-0000-4000-8000-000000000601",
        ),
        _actor(roles=frozenset()),
    )
    reloaded_draft, draft_version = service().get_draft_record(draft.draft_id, _actor(roles=frozenset()))
    assert reloaded_draft == draft
    assert draft_version == 1

    suggestion = service().suggest_patch(
        replace(
            _suggest_command(draft.draft_id),
            idempotency_key="00000000-0000-4000-8000-000000000602",
        ),
        _actor(roles=frozenset(), actor_type=ActorType.MODEL),
    )
    reloaded_patch, patch_version = service().patch_for("patch-1", _actor(roles=frozenset()))
    assert reloaded_patch == suggestion
    assert patch_version == 1

    decision = service().reject_patch(
        RejectTemplatePatchCommand(
            suggestion_id=suggestion.suggestion_id,
            patch_id="patch-1",
            reason="ambiguous",
            expected_patch_version=1,
            idempotency_key="00000000-0000-4000-8000-000000000603",
        ),
        _actor(roles=frozenset({"template_admin"})),
    )
    reloaded_decision, decided_version = service().patch_for("patch-1", _actor(roles=frozenset()))
    assert reloaded_decision == decision
    assert decided_version == 2

    replayed = service().reject_patch(
        RejectTemplatePatchCommand(
            suggestion_id=suggestion.suggestion_id,
            patch_id="patch-1",
            reason="ambiguous",
            expected_patch_version=1,
            idempotency_key="00000000-0000-4000-8000-000000000603",
        ),
        _actor(roles=frozenset({"template_admin"})),
    )
    assert replayed == decision

    with pytest.raises(ReviewError, match="IDEMPOTENCY|different payload"):
        service().reject_patch(
            RejectTemplatePatchCommand(
                suggestion_id=suggestion.suggestion_id,
                patch_id="patch-1",
                reason="different reason",
                expected_patch_version=1,
                idempotency_key="00000000-0000-4000-8000-000000000603",
            ),
            _actor(roles=frozenset({"template_admin"})),
        )


def test_import_key_reuse_with_different_source_is_rejected(tmp_path) -> None:
    repository = SqliteFmeaDeliveryRepository(tmp_path / "fmea.db")
    repository.initialize()
    service = DomainPackService(
        importers={"xlsx": ExcelTemplateImporter(clock=lambda: TIMESTAMP)},
        patch_generator=TemplatePatchGenerator(_FakeGateway(), clock=lambda: TIMESTAMP),
        evidence_provider=_EvidenceProvider(),
        compiler=_Compiler(),
        registry=_Registry(),
        workflow_repository=repository,
        clock=lambda: TIMESTAMP,
    )
    key = "00000000-0000-4000-8000-000000000621"
    actor = _actor(roles=frozenset())
    service.import_template(ImportTemplateCommand(_xlsx(), "fmea.xlsx", "ws-1", key), actor)
    different_source = _xlsx(sheet_xml='''<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
      <sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Effect</t></is></c></row></sheetData>
    </worksheet>''')
    with pytest.raises(ReviewError) as error:
        service.import_template(ImportTemplateCommand(different_source, "fmea.xlsx", "ws-1", key), actor)
    assert error.value.code == "FMEA_IDEMPOTENCY_CONFLICT"


def test_completed_patch_replay_does_not_require_model_availability(tmp_path) -> None:
    repository = SqliteFmeaDeliveryRepository(tmp_path / "fmea.db")
    repository.initialize()

    class UnavailableGateway:
        def generate(self, request: object) -> object:
            raise RuntimeError("provider unavailable on replay")  # noqa: TRY003

    def service(gateway: object) -> DomainPackService:
        return DomainPackService(
            importers={"xlsx": ExcelTemplateImporter(clock=lambda: TIMESTAMP)},
            patch_generator=TemplatePatchGenerator(gateway, clock=lambda: TIMESTAMP),
            evidence_provider=_EvidenceProvider(),
            compiler=_Compiler(),
            registry=_Registry(),
            workflow_repository=repository,
            clock=lambda: TIMESTAMP,
        )

    initial = service(_FakeGateway())
    draft = initial.import_template(
        ImportTemplateCommand(_xlsx(), "fmea.xlsx", "ws-1", "00000000-0000-4000-8000-000000000622"),
        _actor(roles=frozenset()),
    )
    command = replace(
        _suggest_command(draft.draft_id),
        idempotency_key="00000000-0000-4000-8000-000000000623",
    )
    model = _actor(roles=frozenset(), actor_type=ActorType.MODEL)
    original = initial.suggest_patch(command, model)
    replay = service(UnavailableGateway()).suggest_patch(command, model)
    assert replay == original


@pytest.mark.parametrize("action", ["accept", "reject"])
def test_durable_decision_binds_actual_suggestion_identity(tmp_path, action) -> None:
    repository = SqliteFmeaDeliveryRepository(tmp_path / "fmea.db")
    repository.initialize()

    class AlternateIdentityGenerator(TemplatePatchGenerator):
        def suggest(self, request):
            suggestion = super().suggest(request)
            return replace(
                suggestion,
                envelope=replace(suggestion.envelope, suggestion_id="provider-neutral-id", suggestion_hash=None),
            )

    service = DomainPackService(
        importers={"xlsx": ExcelTemplateImporter(clock=lambda: TIMESTAMP)},
        patch_generator=AlternateIdentityGenerator(_FakeGateway(), clock=lambda: TIMESTAMP),
        evidence_provider=_EvidenceProvider(),
        compiler=_Compiler(),
        registry=_Registry(),
        workflow_repository=repository,
        clock=lambda: TIMESTAMP,
    )
    admin = _actor(roles=frozenset({"template_admin"}))
    draft = service.import_template(
        ImportTemplateCommand(_xlsx(), "fmea.xlsx", "ws-1", "00000000-0000-4000-8000-000000000624"), admin
    )
    suggestion = service.suggest_patch(
        replace(_suggest_command(draft.draft_id), idempotency_key="00000000-0000-4000-8000-000000000625"),
        _actor(roles=frozenset(), actor_type=ActorType.MODEL),
    )
    key = "00000000-0000-4000-8000-000000000626"
    if action == "accept":
        service.accept_patch(
            replace(
                _accept_command(draft.draft_id, draft.source_sha256),
                suggestion_id=suggestion.suggestion_id,
                idempotency_key=key,
            ), admin,
        )
    else:
        service.reject_patch(RejectTemplatePatchCommand(suggestion.suggestion_id, "patch-1", "reviewed", 1, key), admin)
    stored, version = service.patch_for("patch-1", admin)
    assert stored.suggestion_id == "provider-neutral-id"
    assert stored.action == ("accepted" if action == "accept" else "rejected")
    assert version == 2


def test_accepted_template_patch_decision_survives_service_restart(tmp_path) -> None:
    repository = SqliteFmeaDeliveryRepository(tmp_path / "fmea.db")
    repository.initialize()
    compiler = _Compiler()

    class _StatefulRegistry(_Registry):
        def __init__(self) -> None:
            super().__init__()
            self.templates = {("template-1", "1.0.0"): _Compiled()}

        def register(self, template: object, source_bytes: bytes, source_suffix: str) -> object:
            self.calls += 1
            assert isinstance(template, _Compiled)
            self.templates[(template.template_id, template.version)] = template
            return template

        def get(self, template_id: str, version: str) -> _Compiled:
            return self.templates[(template_id, version)]

    registry = _StatefulRegistry()

    def service() -> DomainPackService:
        return DomainPackService(
            importers={"xlsx": ExcelTemplateImporter(clock=lambda: TIMESTAMP)},
            patch_generator=TemplatePatchGenerator(_FakeGateway(), clock=lambda: TIMESTAMP),
            evidence_provider=_EvidenceProvider(),
            compiler=compiler,
            registry=registry,
            workflow_repository=repository,
            clock=lambda: TIMESTAMP,
        )

    draft = service().import_template(
        ImportTemplateCommand(_xlsx(), "fmea.xlsx", "ws-1", "00000000-0000-4000-8000-000000000611"),
        _actor(roles=frozenset()),
    )
    suggestion = service().suggest_patch(
        replace(
            _suggest_command(draft.draft_id),
            idempotency_key="00000000-0000-4000-8000-000000000612",
        ),
        _actor(roles=frozenset(), actor_type=ActorType.MODEL),
    )
    registered = service().accept_patch(
        replace(
            _accept_command(draft.draft_id, draft.source_sha256),
            suggestion_id=suggestion.suggestion_id,
            expected_patch_version=1,
            idempotency_key="00000000-0000-4000-8000-000000000613",
        ),
        _actor(roles=frozenset({"template_admin"})),
    )
    assert registered.version == "1.1.0"
    persisted, version = service().patch_for("patch-1", _actor(roles=frozenset()))
    assert persisted.action == "accepted"  # type: ignore[union-attr]
    assert version == 2


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


def test_durable_generation_claim_is_cross_process_and_fails_closed(tmp_path) -> None:
    database_path = tmp_path / "fmea.db"
    repository_one = SqliteFmeaDeliveryRepository(database_path)
    repository_two = SqliteFmeaDeliveryRepository(database_path)
    repository_one.initialize()
    entered = Event()
    release = Event()
    calls = 0

    class _BlockingGateway:
        def generate(self, request: object) -> object:
            nonlocal calls
            calls += 1
            if calls == 1:
                entered.set()
                assert release.wait(timeout=2)
                return {"diff": (), "evidence_ids": ()}
            raise AssertionError("the provider was called more than once")  # noqa: TRY003

    first, _, _ = _durable_service(repository_one, gateway=_BlockingGateway())
    second, _, _ = _durable_service(repository_two, gateway=_BlockingGateway())
    draft = first.import_template(
        ImportTemplateCommand(
            raw_bytes=_xlsx(),
            filename="fmea.xlsx",
            workspace_id="ws-1",
            idempotency_key="00000000-0000-4000-8000-000000000631",
        ),
        _actor(roles=frozenset()),
    )
    command = replace(
        _suggest_command(draft.draft_id),
        idempotency_key="00000000-0000-4000-8000-000000000632",
    )
    model = _actor(roles=frozenset(), actor_type=ActorType.MODEL)

    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(first.suggest_patch, command, model)
        assert entered.wait(timeout=2)
        with pytest.raises(ReviewError) as error:
            second.suggest_patch(command, model)
        assert error.value.code == "FMEA_REVIEW_STORAGE_UNAVAILABLE"
        assert error.value.retryable is True
        release.set()
        suggestion = pending.result(timeout=2)

    assert suggestion.candidate.patch_id == "patch-1"
    assert calls == 1


def test_failed_durable_generation_claim_is_not_silently_stolen(tmp_path) -> None:
    database_path = tmp_path / "fmea.db"
    repository_one = SqliteFmeaDeliveryRepository(database_path)
    repository_two = SqliteFmeaDeliveryRepository(database_path)
    repository_one.initialize()
    calls = 0

    class _FailingGateway:
        def generate(self, request: object) -> object:
            nonlocal calls
            calls += 1
            raise RuntimeError("provider failed after the durable claim")  # noqa: TRY003

    first, _, _ = _durable_service(repository_one, gateway=_FailingGateway())
    second, _, _ = _durable_service(repository_two, gateway=_FailingGateway())
    draft = first.import_template(
        ImportTemplateCommand(
            raw_bytes=_xlsx(),
            filename="fmea.xlsx",
            workspace_id="ws-1",
            idempotency_key="00000000-0000-4000-8000-000000000633",
        ),
        _actor(roles=frozenset()),
    )
    command = replace(
        _suggest_command(draft.draft_id),
        idempotency_key="00000000-0000-4000-8000-000000000634",
    )
    model = _actor(roles=frozenset(), actor_type=ActorType.MODEL)

    with pytest.raises(ReviewError) as first_error:
        first.suggest_patch(command, model)
    assert first_error.value.code == "FMEA_MODEL_SUGGESTION_UNAVAILABLE"
    with pytest.raises(ReviewError) as second_error:
        second.suggest_patch(command, model)
    assert second_error.value.code == "FMEA_REVIEW_STORAGE_UNAVAILABLE"
    assert second_error.value.retryable is True
    assert calls == 1


def test_accept_claim_blocks_competing_rejection_before_registry_effect(tmp_path) -> None:
    database_path = tmp_path / "fmea.db"
    repository_one = SqliteFmeaDeliveryRepository(database_path)
    repository_two = SqliteFmeaDeliveryRepository(database_path)
    repository_one.initialize()
    entered = Event()
    release = Event()

    class _BlockingRegistry(_Registry):
        def register(self, template: object, source_bytes: bytes, source_suffix: str) -> object:
            self.calls += 1
            entered.set()
            assert release.wait(timeout=2)
            return template

    registry = _BlockingRegistry()
    first, _, _ = _durable_service(repository_one, registry=registry)
    second, _, _ = _durable_service(repository_two, registry=registry)
    draft = first.import_template(
        ImportTemplateCommand(
            raw_bytes=_xlsx(),
            filename="fmea.xlsx",
            workspace_id="ws-1",
            idempotency_key="00000000-0000-4000-8000-000000000635",
        ),
        _actor(roles=frozenset()),
    )
    first.suggest_patch(
        replace(
            _suggest_command(draft.draft_id),
            idempotency_key="00000000-0000-4000-8000-000000000636",
        ),
        _actor(roles=frozenset(), actor_type=ActorType.MODEL),
    )
    accept = replace(
        _accept_command(draft.draft_id, draft.source_sha256),
        idempotency_key="00000000-0000-4000-8000-000000000637",
    )
    reject = RejectTemplatePatchCommand(
        suggestion_id="template-patch-suggestion-patch-1",
        patch_id="patch-1",
        reason="competing review",
        idempotency_key="00000000-0000-4000-8000-000000000638",
    )
    admin = _actor(roles=frozenset({"template_admin"}))

    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(first.accept_patch, accept, admin)
        assert entered.wait(timeout=2)
        with pytest.raises(ReviewError) as error:
            second.reject_patch(reject, admin)
        assert error.value.code == "FMEA_REVIEW_STORAGE_UNAVAILABLE"
        assert error.value.retryable is True
        release.set()
        registered = pending.result(timeout=2)

    assert registered.version == "1.1.0"
    assert registry.calls == 1
    assert second.decision_for_patch("patch-1", admin).action == "accepted"  # type: ignore[union-attr]


def test_accepted_decision_intent_recovers_after_registration_boundary_failure(tmp_path) -> None:
    database_path = tmp_path / "fmea.db"
    inner_repository = SqliteFmeaDeliveryRepository(database_path)
    inner_repository.initialize()

    class _FailOnceDecisionSave:
        def __init__(self, repository: SqliteFmeaDeliveryRepository) -> None:
            self._repository = repository
            self.failed = False

        def __getattr__(self, name: str) -> object:
            return getattr(self._repository, name)

        def save_template_patch_decision(self, *args: object, **kwargs: object) -> object:
            if not self.failed:
                self.failed = True
                raise RuntimeError("process stopped after registry registration")  # noqa: TRY003
            return self._repository.save_template_patch_decision(*args, **kwargs)

    registry = _Registry()
    first, _, _ = _durable_service(_FailOnceDecisionSave(inner_repository), registry=registry)  # type: ignore[arg-type]
    draft = first.import_template(
        ImportTemplateCommand(
            raw_bytes=_xlsx(),
            filename="fmea.xlsx",
            workspace_id="ws-1",
            idempotency_key="00000000-0000-4000-8000-000000000639",
        ),
        _actor(roles=frozenset()),
    )
    first.suggest_patch(
        replace(
            _suggest_command(draft.draft_id),
            idempotency_key="00000000-0000-4000-8000-000000000640",
        ),
        _actor(roles=frozenset(), actor_type=ActorType.MODEL),
    )
    command = replace(
        _accept_command(draft.draft_id, draft.source_sha256),
        idempotency_key="00000000-0000-4000-8000-000000000641",
    )
    admin = _actor(roles=frozenset({"template_admin"}))

    with pytest.raises(ReviewError):
        first.accept_patch(command, admin)
    with sqlite3.connect(database_path) as connection:
        intent = connection.execute(
            "SELECT state, decision_id FROM fmea_template_patch_decision_intents "
            "WHERE workspace_id=? AND patch_id=?",
            ("ws-1", "patch-1"),
        ).fetchone()
        assert intent == ("reserved", "template-patch-decision-patch-1")
        assert connection.execute(
            "SELECT COUNT(*) FROM fmea_template_patch_decisions WHERE workspace_id=? AND patch_id=?",
            ("ws-1", "patch-1"),
        ).fetchone()[0] == 0

    second, _, _ = _durable_service(inner_repository, registry=registry)
    registered = second.accept_patch(command, admin)
    assert registered.version == "1.1.0"
    assert registry.calls == 2
    assert second.decision_for_patch("patch-1", admin).action == "accepted"  # type: ignore[union-attr]


def test_invalid_compilation_does_not_leave_accepted_intent_blocking_rejection(tmp_path) -> None:
    database_path = tmp_path / "fmea.db"
    repository = SqliteFmeaDeliveryRepository(database_path)
    repository.initialize()

    class _FailingCompiler(_Compiler):
        def compile(self, source: object) -> _Compiled:
            self.calls += 1
            raise ValueError("deterministic schema validation failure")  # noqa: TRY003

    failing = _FailingCompiler()
    registry = _Registry()
    first, _, _ = _durable_service(repository, compiler=failing, registry=registry)
    draft = first.import_template(
        ImportTemplateCommand(
            raw_bytes=_xlsx(),
            filename="fmea.xlsx",
            workspace_id="ws-1",
            idempotency_key="00000000-0000-4000-8000-000000000649",
        ),
        _actor(roles=frozenset()),
    )
    first.suggest_patch(
        replace(
            _suggest_command(draft.draft_id),
            idempotency_key="00000000-0000-4000-8000-000000000650",
        ),
        _actor(roles=frozenset(), actor_type=ActorType.MODEL),
    )
    admin = _actor(roles=frozenset({"template_admin"}))
    with pytest.raises(ReviewError) as error:
        first.accept_patch(
            replace(
                _accept_command(draft.draft_id, draft.source_sha256),
                idempotency_key="00000000-0000-4000-8000-000000000651",
            ),
            admin,
        )
    assert error.value.code == "FMEA_REVIEW_STORAGE_UNAVAILABLE"

    second, _, _ = _durable_service(repository, registry=registry)
    decision = second.reject_patch(
        RejectTemplatePatchCommand(
            suggestion_id="template-patch-suggestion-patch-1",
            patch_id="patch-1",
            reason="schema validation failed",
            idempotency_key="00000000-0000-4000-8000-000000000652",
        ),
        admin,
    )

    assert decision.action == "rejected"
    assert registry.calls == 0


def test_repository_rejects_decision_bound_to_non_persisted_suggestion_id(tmp_path) -> None:
    repository = SqliteFmeaDeliveryRepository(tmp_path / "fmea.db")
    repository.initialize()
    service, _, _ = _durable_service(repository)
    draft = service.import_template(
        ImportTemplateCommand(
            raw_bytes=_xlsx(),
            filename="fmea.xlsx",
            workspace_id="ws-1",
            idempotency_key="00000000-0000-4000-8000-000000000642",
        ),
        _actor(roles=frozenset()),
    )
    suggestion = service.suggest_patch(
        replace(
            _suggest_command(draft.draft_id),
            idempotency_key="00000000-0000-4000-8000-000000000643",
        ),
        _actor(roles=frozenset(), actor_type=ActorType.MODEL),
    )
    admin = _actor(roles=frozenset({"template_admin"}))
    forged = TemplatePatchDecision(
        decision_id="template-patch-decision-forged",
        suggestion_id="provider-neutral-id",
        patch_id="patch-1",
        workspace_id="ws-1",
        actor_id=admin.actor_id,
        actor_type=ActorType.HUMAN,
        action="accepted",
        reason="forged suggestion binding",
        base_template_id=suggestion.candidate.target_template_id,
        base_template_version=suggestion.candidate.target_template_version,
        base_template_hash=suggestion.candidate.target_template_hash,
        candidate=suggestion.candidate,
        new_template_version="1.1.0",
        created_at=TIMESTAMP,
    )
    scope = IdempotencyScope(
        workspace_id="ws-1",
        actor_id=admin.actor_id,
        command="fmea.template.patch.accept",
        resource_path="/fmea/template-patches/patch-1/acceptance",
        key_hash=idempotency_key_hash("00000000-0000-4000-8000-000000000644"),
    )
    with pytest.raises(ReviewError) as error:
        repository.save_template_patch_decision(
            forged,
            scope,
            "sha256:" + "b" * 64,
            expected_patch_version=1,
        )
    assert error.value.code == "FMEA_REVIEW_STORAGE_UNAVAILABLE"


def test_template_state_audit_and_outbox_are_committed_with_each_transition(tmp_path) -> None:
    database_path = tmp_path / "fmea.db"
    repository = SqliteFmeaDeliveryRepository(database_path)
    repository.initialize()
    service, _, _ = _durable_service(repository)
    draft = service.import_template(
        ImportTemplateCommand(
            raw_bytes=_xlsx(),
            filename="fmea.xlsx",
            workspace_id="ws-1",
            idempotency_key="00000000-0000-4000-8000-000000000645",
        ),
        _actor(roles=frozenset()),
    )
    suggestion = service.suggest_patch(
        replace(
            _suggest_command(draft.draft_id),
            idempotency_key="00000000-0000-4000-8000-000000000646",
        ),
        _actor(roles=frozenset(), actor_type=ActorType.MODEL),
    )
    admin = _actor(roles=frozenset({"template_admin"}))
    service.accept_patch(
        replace(
            _accept_command(draft.draft_id, draft.source_sha256),
            suggestion_id=suggestion.suggestion_id,
            idempotency_key="00000000-0000-4000-8000-000000000647",
        ),
        admin,
    )

    with sqlite3.connect(database_path) as connection:
        audits = connection.execute(
            "SELECT command, action, suggestion_id, decision_id, actor_id, actor_type "
            "FROM fmea_template_audit_events "
            "WHERE workspace_id=? AND patch_id=? "
            "ORDER BY CASE action WHEN 'suggested' THEN 1 WHEN 'accepted' THEN 2 ELSE 3 END",
            ("ws-1", "patch-1"),
        ).fetchall()
        outbox = connection.execute(
            "SELECT event_type, aggregate_type, aggregate_id, status FROM fmea_outbox_events "
            "WHERE workspace_id=? AND aggregate_id=? "
            "ORDER BY CASE event_type WHEN 'template.suggested' THEN 1 WHEN 'template.accepted' THEN 2 ELSE 3 END",
            ("ws-1", "patch-1"),
        ).fetchall()
        import_audit = connection.execute(
            "SELECT command, action, patch_id, suggestion_id, decision_id FROM fmea_template_audit_events "
            "WHERE workspace_id=? AND draft_id=? AND action='imported'",
            ("ws-1", draft.draft_id),
        ).fetchall()
        import_outbox = connection.execute(
            "SELECT event_type, aggregate_type, aggregate_id, status FROM fmea_outbox_events "
            "WHERE workspace_id=? AND aggregate_type='template_draft' AND aggregate_id=?",
            ("ws-1", draft.draft_id),
        ).fetchall()

    assert [(row[0], row[1], row[2]) for row in audits] == [
        ("fmea.template.patch.suggest", "suggested", suggestion.suggestion_id),
        ("fmea.template.patch.accept", "accepted", suggestion.suggestion_id),
    ]
    assert audits[0][3] is None
    assert audits[1][3] == "template-patch-decision-patch-1"
    assert [(row[4], row[5]) for row in audits] == [("actor-1", "model"), ("actor-1", "human")]
    assert [(row[0], row[1], row[2], row[3]) for row in outbox] == [
        ("template.suggested", "template_patch", "patch-1", "pending"),
        ("template.accepted", "template_patch", "patch-1", "pending"),
    ]
    assert import_audit == [("fmea.template.import", "imported", None, None, None)]
    assert import_outbox == [("template.imported", "template_draft", draft.draft_id, "pending")]


def test_template_suggestion_state_audit_and_outbox_rollback_together(tmp_path) -> None:
    def fail(step: str) -> None:
        if step == "template_patch_before_commit":
            raise RuntimeError("fault before template patch commit")  # noqa: TRY003

    database_path = tmp_path / "fmea.db"
    repository = SqliteFmeaDeliveryRepository(database_path, fault_injector=fail)
    repository.initialize()
    service, _, _ = _durable_service(repository)
    draft = service.import_template(
        ImportTemplateCommand(
            raw_bytes=_xlsx(),
            filename="fmea.xlsx",
            workspace_id="ws-1",
            idempotency_key="00000000-0000-4000-8000-000000000653",
        ),
        _actor(roles=frozenset()),
    )

    with pytest.raises(ReviewError) as error:
        service.suggest_patch(
            replace(
                _suggest_command(draft.draft_id),
                idempotency_key="00000000-0000-4000-8000-000000000654",
            ),
            _actor(roles=frozenset(), actor_type=ActorType.MODEL),
        )
    assert error.value.code == "FMEA_REVIEW_STORAGE_UNAVAILABLE"
    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM fmea_template_patch_candidates WHERE patch_id=?", ("patch-1",)
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM fmea_template_audit_events WHERE patch_id=?", ("patch-1",)
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM fmea_outbox_events WHERE aggregate_type='template_patch' AND aggregate_id=?",
            ("patch-1",),
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT state FROM idempotency_records WHERE resource_id=?", ("patch-1",)
        ).fetchone()[0] == "reserved"


def test_template_decision_state_audit_and_outbox_rollback_together(tmp_path) -> None:
    def fail(step: str) -> None:
        if step == "template_decision_before_commit":
            raise RuntimeError("fault before template decision commit")  # noqa: TRY003

    database_path = tmp_path / "fmea.db"
    repository = SqliteFmeaDeliveryRepository(database_path, fault_injector=fail)
    repository.initialize()
    service, _, _ = _durable_service(repository)
    draft = service.import_template(
        ImportTemplateCommand(
            raw_bytes=_xlsx(),
            filename="fmea.xlsx",
            workspace_id="ws-1",
            idempotency_key="00000000-0000-4000-8000-000000000655",
        ),
        _actor(roles=frozenset()),
    )
    service.suggest_patch(
        replace(
            _suggest_command(draft.draft_id),
            idempotency_key="00000000-0000-4000-8000-000000000656",
        ),
        _actor(roles=frozenset(), actor_type=ActorType.MODEL),
    )

    with pytest.raises(ReviewError) as error:
        service.reject_patch(
            RejectTemplatePatchCommand(
                suggestion_id="template-patch-suggestion-patch-1",
                patch_id="patch-1",
                reason="transaction rollback probe",
                idempotency_key="00000000-0000-4000-8000-000000000657",
            ),
            _actor(roles=frozenset({"template_admin"})),
        )
    assert error.value.code == "FMEA_REVIEW_STORAGE_UNAVAILABLE"
    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM fmea_template_patch_decisions WHERE patch_id=?", ("patch-1",)
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM fmea_template_audit_events WHERE patch_id=? AND action='rejected'",
            ("patch-1",),
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM fmea_outbox_events "
            "WHERE aggregate_type='template_patch' AND aggregate_id=? AND event_type='template.rejected'",
            ("patch-1",),
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT state FROM fmea_template_patch_decision_intents WHERE patch_id=?", ("patch-1",)
        ).fetchone()[0] == "reserved"


def test_v012_undecided_patch_with_envelope_survives_013_upgrade_and_accepts(tmp_path) -> None:
    database_path = tmp_path / "fmea.db"
    legacy_migrations = tmp_path / "migrations-v012"
    legacy_migrations.mkdir()
    source_migrations = Path(__file__).resolve().parents[2] / "fmea_infrastructure" / "migrations"
    for migration in source_migrations.glob("*.sql"):
        if int(migration.name[:3]) <= 12:
            shutil.copy2(migration, legacy_migrations / migration.name)

    legacy_repository = SqliteFmeaRepository(database_path)
    legacy_repository._migrations_path = legacy_migrations  # type: ignore[attr-defined]
    legacy_repository.initialize()
    in_memory, _, _ = _service()
    draft = in_memory.import_template(
        ImportTemplateCommand(raw_bytes=_xlsx(), filename="fmea.xlsx", workspace_id="ws-1"),
        _actor(roles=frozenset()),
    )
    suggestion = in_memory.suggest_patch(
        _suggest_command(draft.draft_id),
        _actor(roles=frozenset(), actor_type=ActorType.MODEL),
    )
    draft_json, draft_hash = _contract_json(draft)
    candidate = suggestion.candidate
    candidate_json, candidate_hash = _contract_json(candidate)
    suggestion_json = json.dumps(
        _json_value(suggestion.envelope), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            "INSERT INTO fmea_template_drafts "
            "(workspace_id,draft_id,source_filename,source_sha256,source_type,structure_json,"
            "proposed_fields_json,unknown_fields_json,ambiguous_fields_json,parser_warnings_json,"
            "identified_fields_json,status,draft_json,canonical_json_hash,created_at,record_version) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)",
            (
                draft.workspace_id,
                draft.draft_id,
                draft.source_filename,
                draft.source_sha256,
                draft.source_type,
                json.dumps(_json_value(draft.structure), sort_keys=True, separators=(",", ":")),
                json.dumps(_json_value(draft.proposed_fields), sort_keys=True, separators=(",", ":")),
                json.dumps(_json_value(draft.unknown_fields), sort_keys=True, separators=(",", ":")),
                json.dumps(_json_value(draft.ambiguous_fields), sort_keys=True, separators=(",", ":")),
                json.dumps(_json_value(draft.parser_warnings), sort_keys=True, separators=(",", ":")),
                json.dumps(_json_value(draft.identified_fields), sort_keys=True, separators=(",", ":")),
                draft.status.value,
                draft_json,
                draft_hash,
                draft.created_at,
            ),
        )
        connection.execute(
            "INSERT INTO fmea_template_patch_candidates "
            "(workspace_id,patch_id,draft_id,input_template_version,target_template_id,"
            "target_template_version,target_template_hash,domain_pack_id,domain_pack_version,domain_pack_hash,"
            "evidence_pack_id,evidence_pack_hash,run_id,trace_id,model_version,prompt_version,diff_json,"
            "evidence_ids_json,status,applied,candidate_json,canonical_json_hash,created_at,suggestion_json,"
            "record_version) VALUES ("
            "?,?,?,?,?,?,?,?,?,?,"
            "?,?,?,?,?,?,?,?,?,?,"
            "?,?,?,?,1)",
            (
                draft.workspace_id,
                candidate.patch_id,
                candidate.draft_id,
                candidate.input_template_version,
                candidate.target_template_id,
                candidate.target_template_version,
                candidate.target_template_hash,
                candidate.domain_pack_id,
                candidate.domain_pack_version,
                candidate.domain_pack_hash,
                candidate.evidence_pack_id,
                candidate.evidence_pack_hash,
                candidate.run_id,
                candidate.trace_id,
                candidate.model_version,
                candidate.prompt_version,
                json.dumps(_json_value(candidate.diff), sort_keys=True, separators=(",", ":")),
                json.dumps(_json_value(candidate.evidence_ids), sort_keys=True, separators=(",", ":")),
                candidate.status.value,
                0,
                candidate_json,
                candidate_hash,
                candidate.created_at,
                suggestion_json,
            ),
        )

    upgraded = SqliteFmeaDeliveryRepository(database_path)
    upgraded.initialize()
    service, _, registry = _durable_service(upgraded)
    decision = service.accept_patch(
        replace(
            _accept_command(draft.draft_id, draft.source_sha256),
            idempotency_key="00000000-0000-4000-8000-000000000648",
        ),
        _actor(roles=frozenset({"template_admin"})),
    )

    assert decision.version == "1.1.0"
    assert registry.calls == 1
    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT suggestion_id FROM fmea_template_patch_candidates WHERE patch_id=?", (candidate.patch_id,)
        ).fetchone()[0] is None
        assert connection.execute(
            "SELECT suggestion_id, action FROM fmea_template_patch_decisions WHERE patch_id=?", (candidate.patch_id,)
        ).fetchone() == (suggestion.suggestion_id, "accepted")
