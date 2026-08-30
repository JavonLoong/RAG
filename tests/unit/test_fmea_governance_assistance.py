from __future__ import annotations

import pytest
from fmea_governance_fixtures import make_blocked_readiness_report, make_governance_actor

from core_domain.fmea.states import ActorType


def _implementation():
    try:
        from fmea_application.assistance_contracts import AssistanceKind, AssistanceSuggestion
        from fmea_application.governance_assistance_service import GovernanceAssistanceService
    except ModuleNotFoundError as exc:
        pytest.fail(f"Task 2 production implementation is missing: {exc}")
    return AssistanceKind, AssistanceSuggestion, GovernanceAssistanceService


def test_model_readiness_checklist_cannot_clear_a_blocker():
    AssistanceKind, AssistanceSuggestion, GovernanceAssistanceService = _implementation()
    report = make_blocked_readiness_report()
    actor = make_governance_actor(actor_type=ActorType.MODEL, roles=frozenset())
    suggestion = GovernanceAssistanceService().suggest_readiness_checklist(report, actor)
    assert isinstance(suggestion, AssistanceSuggestion)
    assert suggestion.kind is AssistanceKind.APPROVAL_READINESS_CHECKLIST
    assert suggestion.applied is False
    assert suggestion.payload["ready"] is False
    assert report.ready is False


def test_readiness_assistance_is_offline_and_immutable_by_default():
    _, _, GovernanceAssistanceService = _implementation()
    report = make_blocked_readiness_report()
    actor = make_governance_actor(actor_type=ActorType.MODEL, roles=frozenset())
    suggestion = GovernanceAssistanceService().suggest_readiness_checklist(report, actor)
    assert suggestion.model_hash == suggestion.model_hash.lower()
    assert len(suggestion.model_hash) == 64
    assert len(suggestion.prompt_hash) == 64
    with pytest.raises((AttributeError, TypeError)):
        suggestion.applied = True  # type: ignore[misc]


def test_human_actor_cannot_be_used_as_model_readiness_assistance():
    _, _, GovernanceAssistanceService = _implementation()
    human = make_governance_actor(actor_type=ActorType.HUMAN)
    with pytest.raises(ValueError, match="model actor"):
        GovernanceAssistanceService().suggest_readiness_checklist(make_blocked_readiness_report(), human)


def test_assistance_rejects_forged_mapping_report():
    _, _, GovernanceAssistanceService = _implementation()
    actor = make_governance_actor(actor_type=ActorType.MODEL, roles=frozenset())
    with pytest.raises(TypeError, match="PublicationReadinessReport"):
        GovernanceAssistanceService().suggest_readiness_checklist({"ready": False}, actor)


def test_assistance_rejects_string_false_from_generator():
    from fmea_application.revision_assembler import PublicationReadinessReport

    class MaliciousGenerator:
        def generate(self, _projection):
            return {
                "ready": "false",
                "blocking_codes": (),
                "checklist": (),
                "revision_id": "revision-1",
                "revision_hash": "a" * 64,
            }

    _, _, GovernanceAssistanceService = _implementation()
    actor = make_governance_actor(actor_type=ActorType.MODEL, roles=frozenset())
    report = PublicationReadinessReport(
        revision_id="revision-1",
        workspace_id="ws-1",
        analysis_id="analysis-1",
        revision_hash="a" * 64,
        target_record_version=1,
        evidence_pack_ids=("pack-1",),
        ready=False,
        issues=(),
        blocking_codes=("BLOCKED",),
    )
    with pytest.raises((TypeError, ValueError)):
        GovernanceAssistanceService(MaliciousGenerator()).suggest_readiness_checklist(report, actor)


def test_assistance_generator_receives_safe_bounded_projection():
    from fmea_application.revision_assembler import PublicationReadinessReport

    class CaptureGenerator:
        def __init__(self):
            self.projection = None

        def generate(self, projection):
            self.projection = projection
            return {
                "ready": False,
                "blocking_codes": ("BLOCKED",),
                "checklist": (),
                "revision_id": "revision-1",
                "revision_hash": "a" * 64,
            }

    _, _, GovernanceAssistanceService = _implementation()
    actor = make_governance_actor(actor_type=ActorType.MODEL, roles=frozenset())
    generator = CaptureGenerator()
    report = PublicationReadinessReport(
        revision_id="revision-1",
        workspace_id="ws-1",
        analysis_id="analysis-1",
        revision_hash="a" * 64,
        target_record_version=1,
        evidence_pack_ids=("C:\\private\\secret",),
        ready=False,
        issues=(),
        blocking_codes=("BLOCKED",),
    )
    GovernanceAssistanceService(generator).suggest_readiness_checklist(report, actor)
    assert generator.projection is not report
    assert "C:\\private\\secret" not in repr(generator.projection)


def test_suggestion_payload_does_not_echo_unsafe_report_identifiers():
    from core_domain.fmea.governance import ReadinessIssue
    from fmea_application.revision_assembler import PublicationReadinessReport

    class CaptureGenerator:
        def generate(self, projection):
            return {
                "ready": False,
                "blocking_codes": projection.blocking_codes,
                "checklist": tuple(
                    {
                        "code": issue.code,
                        "severity": issue.severity,
                        "source_type": issue.source_type,
                        "source_id": issue.source_id,
                        "evidence_ids": issue.evidence_ids,
                        "acknowledgement_decision_id": issue.acknowledgement_decision_id,
                    }
                    for issue in projection.issues
                ),
                "revision_id": projection.revision_id,
                "revision_hash": projection.revision_hash,
            }

    unsafe = ("C:\\private\\secret", "https://example.invalid/token")
    issue = ReadinessIssue(
        code=unsafe[1],
        severity="critical",
        source_type="row",
        source_id="/var/private/row",
        evidence_ids=("TOKEN=do-not-echo",),
        acknowledgement_decision_id=None,
    )
    report = PublicationReadinessReport(
        revision_id="revision-1",
        workspace_id="ws-1",
        analysis_id="analysis-1",
        revision_hash="a" * 64,
        target_record_version=1,
        evidence_pack_ids=unsafe,
        ready=False,
        issues=(issue,),
        blocking_codes=unsafe,
    )
    actor = make_governance_actor(actor_type=ActorType.MODEL, roles=frozenset())
    _, _, GovernanceAssistanceService = _implementation()
    suggestion = GovernanceAssistanceService(CaptureGenerator()).suggest_readiness_checklist(report, actor)
    payload = repr(suggestion.payload)
    assert all(value not in payload for value in unsafe)
    assert "TOKEN=do-not-echo" not in payload


def test_assistance_rejects_generator_authority_changes_and_unknown_fields():
    from fmea_application.revision_assembler import PublicationReadinessReport

    class MaliciousGenerator:
        def generate(self, _projection):
            return {
                "ready": False,
                "blocking_codes": (),
                "checklist": (),
                "revision_id": "revision-1",
                "revision_hash": "a" * 64,
                "authority": "publisher",
            }

    _, _, GovernanceAssistanceService = _implementation()
    actor = make_governance_actor(actor_type=ActorType.MODEL, roles=frozenset())
    report = PublicationReadinessReport(
        revision_id="revision-1",
        workspace_id="ws-1",
        analysis_id="analysis-1",
        revision_hash="a" * 64,
        target_record_version=1,
        evidence_pack_ids=("pack-1",),
        ready=True,
        issues=(),
        blocking_codes=(),
    )
    with pytest.raises(TypeError, match="schema"):
        GovernanceAssistanceService(MaliciousGenerator()).suggest_readiness_checklist(report, actor)


def test_assistance_rejects_generator_acknowledgement_replacement():
    from fmea_application.revision_assembler import PublicationReadinessReport

    class MaliciousGenerator:
        def generate(self, _projection):
            return {
                "ready": False,
                "blocking_codes": ("ACK_REQUIRED",),
                "checklist": (
                    {
                        "code": "ACK_REQUIRED",
                        "severity": "critical",
                        "source_type": "row",
                        "source_id": "row-1",
                        "evidence_ids": ("ev-1",),
                        "acknowledgement_decision_id": "forged-decision",
                    },
                ),
                "revision_id": "revision-1",
                "revision_hash": "a" * 64,
            }

    _, _, GovernanceAssistanceService = _implementation()
    actor = make_governance_actor(actor_type=ActorType.MODEL, roles=frozenset())
    issue = {
        "code": "ACK_REQUIRED",
        "severity": "critical",
        "source_type": "row",
        "source_id": "row-1",
        "evidence_ids": ("ev-1",),
        "acknowledgement_decision_id": "decision-1",
    }
    from core_domain.fmea.governance import ReadinessIssue

    report = PublicationReadinessReport(
        revision_id="revision-1",
        workspace_id="ws-1",
        analysis_id="analysis-1",
        revision_hash="a" * 64,
        target_record_version=1,
        evidence_pack_ids=("pack-1",),
        ready=False,
        issues=(ReadinessIssue(**issue),),
        blocking_codes=("ACK_REQUIRED",),
    )
    with pytest.raises(ValueError, match="acknowledgement"):
        GovernanceAssistanceService(MaliciousGenerator()).suggest_readiness_checklist(report, actor)


def test_assistance_rejects_duplicate_checklist_items():
    from fmea_application.revision_assembler import PublicationReadinessReport

    class MaliciousGenerator:
        def generate(self, _projection):
            item = {
                "code": "BLOCKED",
                "severity": "blocking",
                "source_type": "row",
                "source_id": "row-1",
                "evidence_ids": (),
                "acknowledgement_decision_id": None,
            }
            return {
                "ready": False,
                "blocking_codes": ("BLOCKED",),
                "checklist": (item, item),
                "revision_id": "revision-1",
                "revision_hash": "a" * 64,
            }

    _, _, GovernanceAssistanceService = _implementation()
    actor = make_governance_actor(actor_type=ActorType.MODEL, roles=frozenset())
    from core_domain.fmea.governance import ReadinessIssue

    report = PublicationReadinessReport(
        revision_id="revision-1",
        workspace_id="ws-1",
        analysis_id="analysis-1",
        revision_hash="a" * 64,
        target_record_version=1,
        evidence_pack_ids=("pack-1",),
        ready=False,
        issues=(ReadinessIssue("BLOCKED", "blocking", "row", "row-1", (), None),),
        blocking_codes=("BLOCKED",),
    )
    with pytest.raises(ValueError, match="checklist"):
        GovernanceAssistanceService(MaliciousGenerator()).suggest_readiness_checklist(report, actor)


def test_unavailable_generator_degrades_to_offline_without_changing_readiness():
    from fmea_application.governance_assistance_service import GovernanceAssistanceUnavailable

    class UnavailableGenerator:
        def generate(self, _projection):
            raise GovernanceAssistanceUnavailable("offline")

    _, _, GovernanceAssistanceService = _implementation()
    actor = make_governance_actor(actor_type=ActorType.MODEL, roles=frozenset())
    report = make_blocked_readiness_report()
    suggestion = GovernanceAssistanceService(UnavailableGenerator()).suggest_readiness_checklist(report, actor)
    assert suggestion.applied is False
    assert suggestion.payload["ready"] is False
    assert tuple(suggestion.payload["blocking_codes"]) == report.blocking_codes
