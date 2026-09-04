from __future__ import annotations

import inspect
from dataclasses import replace

import pytest


def _implementation():
    try:
        from fmea_application.ports import GovernanceRepositoryProviders
        from fmea_infrastructure.composition import RepositoryGovernanceSource
    except (ImportError, ModuleNotFoundError) as exc:
        pytest.fail(f"Task 2 server-owned source adapter is missing: {exc}")
    return GovernanceRepositoryProviders, RepositoryGovernanceSource


def test_source_adapter_is_typed_and_has_no_callable_loader_seam():
    GovernanceRepositoryProviders, RepositoryGovernanceSource = _implementation()
    assert "loader" not in inspect.signature(RepositoryGovernanceSource).parameters
    assert "providers" in inspect.signature(RepositoryGovernanceSource).parameters
    assert GovernanceRepositoryProviders is not None


def test_source_adapter_load_inputs_only_accepts_server_scope():
    _, RepositoryGovernanceSource = _implementation()
    with pytest.raises(TypeError):
        RepositoryGovernanceSource(object()).load_inputs(
            "analysis-1",
            "ws-1",
            rows=(),
            evidence_packs=(),
        )


def test_source_exposes_no_issuer_or_verifier_instance_seam():
    from fmea_governance_fixtures import make_governance_inputs

    source = _source(make_governance_inputs())
    assert not hasattr(source, "_verifier")
    assert not hasattr(source, "_issue_inputs_attestation")
    assert not any("issue" in name or "verif" in name for name in dir(source))


def test_publication_body_entrypoint_is_runtime_owned_and_base_fails_closed():
    from fmea_governance_fixtures import make_governance_inputs

    base = make_governance_inputs()
    runtime = _source(base, return_runtime=True)
    revision = runtime.assembler.assemble(
        __import__("fmea_governance_fixtures", fromlist=["make_assemble_request"]).make_assemble_request(),
        runtime.source.load_inputs("analysis-1", "ws-1"),
    )

    with pytest.raises(TypeError, match="must be obtained from build_workspace_governance_runtime"):
        type(runtime.source).__mro__[1](runtime.source._providers).build_publication_body(
            revision,
            base,
            review_records=(),
        )
    assert callable(runtime.source.build_publication_body)


def test_publication_body_entrypoint_rejects_forged_runtime_inputs_before_projection():
    from fmea_governance_fixtures import make_assemble_request, make_governance_inputs

    runtime = _source(make_governance_inputs(), return_runtime=True)
    inputs = runtime.source.load_inputs("analysis-1", "ws-1")
    revision = runtime.assembler.assemble(make_assemble_request(), inputs)
    forged = replace(inputs, active_run_ids=("forged-run",))

    with pytest.raises(ValueError, match="attestation"):
        runtime.source.build_publication_body(revision, forged, review_records=())


def test_valid_source_rejects_client_state_overrides_at_load_boundary():
    from fmea_governance_fixtures import make_governance_inputs

    base = make_governance_inputs()
    source = _source(base)
    with pytest.raises(TypeError):
        source.load_inputs(
            "analysis-1",
            "ws-1",
            rows=(),
            evidence_packs=(),
            domain_pack=base.domain_pack,
            active_run_ids=(),
        )


def test_analysis_query_port_requires_scoped_resolved_analysis_record():
    from fmea_application.revision_assembler import ResolvedAnalysisRecord

    assert ResolvedAnalysisRecord is not None


def test_retrieval_provenance_is_a_server_query_port():
    from fmea_application.ports import RetrievalProvenanceQueryPort

    assert RetrievalProvenanceQueryPort is not None


def test_registry_ports_require_source_bytes_for_manifest_verification():
    from fmea_application.ports import DomainPackRegistry, PropagationRuleRegistry, ScoringRuleRegistry

    assert callable(DomainPackRegistry.get_source_bytes)
    assert callable(ScoringRuleRegistry.get_source_bytes)
    assert callable(PropagationRuleRegistry.get_source_bytes)


def test_client_cannot_override_registry_identity_or_active_run_state():
    GovernanceRepositoryProviders, RepositoryGovernanceSource = _implementation()
    assert "domain_pack" not in inspect.signature(RepositoryGovernanceSource.load_inputs).parameters
    assert "active_run_ids" not in inspect.signature(RepositoryGovernanceSource.load_inputs).parameters
    assert "domain_pack" not in inspect.signature(GovernanceRepositoryProviders).parameters


class _AnalysisProvider:
    def __init__(self, analysis):
        self.analysis = analysis

    def get_analysis(self, _analysis_id, _workspace_id):
        return self.analysis


class _ReviewProvider:
    def __init__(self, rows=()):
        self.rows = rows

    def list_rows(self, _analysis_id, _workspace_id):
        return self.rows


class _RiskProvider:
    def __init__(self, records=()):
        self.records = records

    def list_risk_records(self, _analysis_id, _workspace_id):
        return self.records


class _PropagationProvider:
    def __init__(self, graph=None):
        self.graph = graph

    def get_current_graph(self, _analysis_id, _workspace_id):
        return self.graph


class _EvidenceProvider:
    def __init__(self, packs=()):
        self.packs = packs

    def list_evidence_packs(self, _analysis_id, _workspace_id):
        return self.packs


class _ArtifactProvider:
    def __init__(self, artifacts):
        self.artifacts = artifacts

    def get_artifacts(self, _analysis_id, _workspace_id, _analysis):
        return self.artifacts


class _RunProvider:
    def __init__(self, run_ids=()):
        self.run_ids = run_ids

    def list_active_run_ids(self, _analysis_id, _workspace_id):
        return self.run_ids


class _AcknowledgementProvider:
    def __init__(self, references=()):
        self.references = references

    def list_human_acknowledgements(self, _analysis_id, _workspace_id):
        return self.references


class _RetrievalProvider:
    def __init__(self, provenance):
        self.provenance = provenance

    def get_provenance(self, _analysis_id, _workspace_id):
        return self.provenance


def _source(
    base,
    *,
    analysis=None,
    rows=(),
    risk_records=(),
    graph=None,
    packs=(),
    run_ids=(),
    acknowledgements=(),
    provenance=None,
    parent=None,
    return_runtime=False,
):
    GovernanceRepositoryProviders, RepositoryGovernanceSource = _implementation()
    providers = GovernanceRepositoryProviders(
        analysis=_AnalysisProvider(analysis or base.analysis),
        review=_ReviewProvider(rows),
        risk=_RiskProvider(risk_records),
        propagation=_PropagationProvider(graph),
        evidence=_EvidenceProvider(packs),
        artifacts=_ArtifactProvider(
            __import__("fmea_application.revision_assembler", fromlist=["GovernanceArtifactSet"]).GovernanceArtifactSet(
                domain_pack=base.domain_pack,
                domain_pack_identity=base.domain_pack_identity,
                template_identities=base.template_identities,
                scoring_rule_identities=base.scoring_rule_identities,
                propagation_rule_identity=base.propagation_rule_identity,
            )
        ),
        runs=_RunProvider(run_ids),
        acknowledgements=_AcknowledgementProvider(acknowledgements),
        retrieval=_RetrievalProvider(provenance or base.retrieval_provenance),
        parent=(
            type(
                "ParentProvider",
                (),
                {"get_parent_revision": lambda _self, _analysis_id, _workspace_id: parent},
            )()
            if parent is not None
            else None
        ),
    )
    from fmea_infrastructure.composition import build_workspace_governance_runtime

    runtime = build_workspace_governance_runtime(providers)
    return runtime if return_runtime else runtime.source


def test_source_reads_active_runs_server_side_and_returns_typed_inputs():
    from fmea_governance_fixtures import make_governance_inputs

    from fmea_application.revision_assembler import GovernanceInputs

    base = make_governance_inputs()
    inputs = _source(base, run_ids=("run-1",)).load_inputs("analysis-1", "ws-1")
    assert isinstance(inputs, GovernanceInputs)
    assert inputs.active_run_ids == ("run-1",)


def test_source_attestation_binds_replaced_input_components():
    from dataclasses import replace

    from fmea_governance_fixtures import _identity, make_governance_inputs

    base = make_governance_inputs()
    runtime = _source(base, return_runtime=True)
    inputs = runtime.source.load_inputs("analysis-1", "ws-1")
    assembler = runtime.assembler
    request = __import__("fmea_governance_fixtures", fromlist=["make_assemble_request"]).make_assemble_request()
    tampered_values = (
        replace(inputs, active_run_ids=("forged-run",)),
        replace(
            inputs,
            template_identities=(_identity("template", "generic-template", "1.0.0", "e" * 64),),
        ),
        replace(
            inputs,
            analysis=replace(
                inputs.analysis,
                analysis=replace(inputs.analysis.analysis, record_version=2),
                record_version=2,
                canonical_hash=__import__("core_domain.fmea.governance", fromlist=["canonical_hash"]).canonical_hash(
                    replace(inputs.analysis.analysis, record_version=2)
                ),
                source_hash=__import__("core_domain.fmea.governance", fromlist=["canonical_hash"]).canonical_hash(
                    replace(inputs.analysis.analysis, record_version=2)
                ),
            ),
        ),
    )
    for tampered in tampered_values:
        with pytest.raises(ValueError, match="attestation"):
            assembler.assemble(request, tampered)


def test_source_attestation_binds_acknowledgement_records():
    from dataclasses import replace

    from fmea_governance_fixtures import make_governance_acknowledgement_record, make_governance_inputs

    base = make_governance_inputs()
    runtime = _source(base, acknowledgements=(make_governance_acknowledgement_record(),), return_runtime=True)
    inputs = runtime.source.load_inputs("analysis-1", "ws-1")
    tampered = replace(inputs, acknowledgement_references=())
    with pytest.raises(ValueError, match="attestation"):
        runtime.assembler.assemble(
            __import__("fmea_governance_fixtures", fromlist=["make_assemble_request"]).make_assemble_request(),
            tampered,
        )


def test_source_attestation_has_no_public_constructor_or_module_signer():
    from fmea_governance_fixtures import make_governance_inputs

    import fmea_application.revision_assembler as revision_assembler

    inputs = make_governance_inputs()
    proof_type = type(inputs._source_attestation)
    with pytest.raises(TypeError):
        proof_type(object(), "a" * 64, "b" * 64)
    assert not hasattr(revision_assembler, "_ResolverCapability")
    assert not hasattr(revision_assembler, "_RESOLVER_CAPABILITY")


def test_cross_runtime_attestation_cannot_be_reused():
    from fmea_governance_fixtures import make_assemble_request, make_governance_inputs

    first = make_governance_inputs()
    second = make_governance_inputs()
    with pytest.raises(ValueError, match="attestation"):
        __import__("fmea_governance_fixtures", fromlist=["make_governance_assembler"]).make_governance_assembler(
            second
        ).assemble(make_assemble_request(), first)


@pytest.mark.parametrize(
    "field",
    ("requested_profile", "resolved_profile", "evidence_types", "source_counts", "warnings"),
)
def test_source_attestation_binds_every_retrieval_provenance_field(field):
    from fmea_governance_fixtures import make_governance_inputs

    base = make_governance_inputs()
    replacement = {
        "requested_profile": "rag_only",
        "resolved_profile": "rag_only",
        "evidence_types": ("text",),
        "source_counts": (("text", 2),),
        "warnings": ("changed-warning",),
    }
    tampered_provenance = replace(base.retrieval_provenance, **{field: replacement[field]})
    tampered = replace(base, retrieval_provenance=tampered_provenance)
    with pytest.raises(ValueError, match="attestation"):
        __import__("fmea_governance_fixtures", fromlist=["make_governance_assembler"]).make_governance_assembler(
            base
        ).assemble(
            __import__("fmea_governance_fixtures", fromlist=["make_assemble_request"]).make_assemble_request(),
            tampered,
        )


def test_source_rejects_provider_records_from_a_mixed_analysis_scope(fixture_row):
    from fmea_governance_fixtures import make_governance_inputs

    base = make_governance_inputs()
    foreign_row = replace(fixture_row, analysis_id="analysis-foreign")
    with pytest.raises(ValueError, match="analysis"):
        _source(base, rows=(foreign_row,)).load_inputs("analysis-1", "ws-1")


def test_source_rejects_same_analysis_id_with_foreign_analysis_workspace():
    from fmea_governance_fixtures import make_governance_inputs

    from fmea_application.revision_assembler import ResolvedAnalysisRecord

    base = make_governance_inputs()
    foreign_analysis = ResolvedAnalysisRecord(
        "ws-foreign",
        base.analysis.analysis,
        base.analysis.record_version,
        base.analysis.canonical_hash,
        base.analysis.source_hash,
    )
    with pytest.raises(ValueError, match="workspace"):
        _source(base, analysis=foreign_analysis).load_inputs("analysis-1", "ws-1")


def test_scoped_analysis_record_rejects_forged_hashes():
    from fmea_governance_fixtures import make_governance_inputs

    from fmea_application.revision_assembler import ResolvedAnalysisRecord

    base = make_governance_inputs()
    with pytest.raises(ValueError, match="canonical/source hash"):
        ResolvedAnalysisRecord(
            "ws-1",
            base.analysis.analysis,
            1,
            "a" * 64,
            "a" * 64,
        )


def test_source_rejects_foreign_acknowledgement_scope():
    from fmea_governance_fixtures import make_governance_acknowledgement_record, make_governance_inputs

    base = make_governance_inputs()
    reference = make_governance_acknowledgement_record(
        workspace_id="ws-foreign",
        analysis_id="analysis-1",
        issue_code="BLOCKED",
        issue_source_type="row",
        issue_source_id="row-1",
        evidence_ids=(),
    )
    with pytest.raises(ValueError, match="scope"):
        _source(base, acknowledgements=(reference,)).load_inputs("analysis-1", "ws-1")


def test_source_rejects_foreign_parent_scope_before_attestation():
    from fmea_governance_fixtures import make_fmea_revision, make_governance_inputs

    base = make_governance_inputs()
    foreign_parent = make_fmea_revision(workspace_id="ws-foreign", analysis_id="analysis-foreign")
    with pytest.raises(ValueError, match="parent"):
        _source(base, parent=foreign_parent).load_inputs("analysis-1", "ws-1")


@pytest.mark.parametrize(
    "record_overrides",
    (
        {"status": "rejected"},
        {"decision_hash": "b" * 64},
    ),
)
def test_source_does_not_resolve_unaccepted_or_unbound_acknowledgement_records(record_overrides):
    from dataclasses import replace

    from fmea_governance_fixtures import make_governance_acknowledgement_record, make_governance_inputs

    base = make_governance_inputs()
    record = make_governance_acknowledgement_record(**{
        key: value for key, value in record_overrides.items() if key != "decision_hash"
    })
    if "decision_hash" in record_overrides:
        record = replace(record, decision_hash=record_overrides["decision_hash"])
    with pytest.raises(ValueError):
        _source(base, acknowledgements=(record,)).load_inputs("analysis-1", "ws-1")


def test_source_rejects_acknowledgement_version_tampering():
    from dataclasses import replace

    from fmea_governance_fixtures import make_governance_acknowledgement_record, make_governance_inputs

    base = make_governance_inputs()
    record = make_governance_acknowledgement_record()
    tampered = replace(record, decision_record_version=record.decision_record_version + 1)
    with pytest.raises(ValueError, match="hash"):
        _source(base, acknowledgements=(tampered,)).load_inputs("analysis-1", "ws-1")


def test_source_preserves_server_retrieval_provenance_without_defaulting_to_combined():
    from dataclasses import replace

    from fmea_governance_fixtures import make_governance_inputs

    base = make_governance_inputs()
    provenance = replace(
        base.retrieval_provenance,
        requested_profile="graphrag_only",
        resolved_profile="graphrag_only",
        evidence_types=("graph", "community"),
    )
    inputs = _source(base, provenance=provenance).load_inputs("analysis-1", "ws-1")
    assert inputs.requested_profile == "graphrag_only"
    assert inputs.evidence_types == ("community", "graph")


def test_source_rejects_foreign_retrieval_provenance_scope():
    from dataclasses import replace

    from fmea_governance_fixtures import make_governance_inputs

    base = make_governance_inputs()
    provenance = replace(base.retrieval_provenance, workspace_id="ws-foreign")
    with pytest.raises(ValueError, match="scope"):
        _source(base, provenance=provenance).load_inputs("analysis-1", "ws-1")


@pytest.mark.parametrize(
    "provenance_overrides",
    (
        {"requested_profile": "unknown-profile"},
        {"warnings": ("https://private.example/secret",)},
        {"warnings": tuple(f"warning-{index}" for index in range(65))},
    ),
)
def test_retrieval_provenance_rejects_unknown_or_unsafe_provider_values(provenance_overrides):
    from fmea_application.revision_assembler import GovernanceRetrievalProvenance

    values = {
        "workspace_id": "ws-1",
        "analysis_id": "analysis-1",
        "requested_profile": "combined",
        "resolved_profile": "combined",
        "evidence_types": ("text",),
        "source_counts": (("text", 1),),
        "warnings": (),
    }
    values.update(provenance_overrides)
    with pytest.raises(ValueError):
        GovernanceRetrievalProvenance(**values)


def test_source_rejects_mixed_risk_graph_and_evidence_scopes(fixture_pack):
    from dataclasses import replace

    from fmea_governance_fixtures import make_governance_inputs
    from fmea_propagation_fixtures import _graph

    from core_domain.fmea.scoring import RiskAssessmentRecord
    from core_domain.fmea.states import RiskStatus

    base = make_governance_inputs()
    foreign_risk = RiskAssessmentRecord(
        assessment_id="assessment-1",
        workspace_id="ws-foreign",
        row_id="row-1",
        source_record_version=1,
        evidence_pack_id="pack-1",
        domain_pack_id="generic-domain",
        domain_pack_version="1.0.0",
        rule_pack_id="generic-scoring",
        rule_pack_version="1.0.0",
        status=RiskStatus.PROPOSED,
        dimensions=(),
        derived=None,
        proposal_id="proposal-1",
        assistance_suggestion_id=None,
        confirmer_actor_id=None,
        invalidated_reason=None,
        record_version=1,
        created_at="2026-08-30T00:00:00Z",
        updated_at="2026-08-30T00:00:00Z",
    )
    with pytest.raises(ValueError, match="workspace"):
        _source(base, risk_records=(foreign_risk,)).load_inputs("analysis-1", "ws-1")

    foreign_pack = replace(fixture_pack, workspace_id="ws-foreign")
    with pytest.raises(ValueError, match="workspace"):
        _source(base, packs=(foreign_pack,)).load_inputs("analysis-1", "ws-1")

    foreign_graph = replace(_graph("ws-1"), workspace_id="ws-foreign")
    with pytest.raises(ValueError, match="workspace"):
        _source(base, graph=foreign_graph).load_inputs("analysis-1", "ws-1")


def test_registry_adapter_rejects_registry_manifest_hash_mismatch():
    from fmea_governance_fixtures import make_governance_inputs

    from fmea_infrastructure.composition import RegistryGovernanceArtifactProvider

    base = make_governance_inputs()

    class BadDomainRegistry:
        def get(self, _pack_id, _version):
            return replace(base.domain_pack, content_hash="b" * 64)

    with pytest.raises((TypeError, ValueError), match="domain[_ ]pack registry"):
        RegistryGovernanceArtifactProvider(
            domain_pack=base.domain_pack,
            domain_pack_registry=BadDomainRegistry(),
            template_registry=object(),
            scoring_rule_registry=object(),
            propagation_rule_registry=object(),
        ).get_artifacts("analysis-1", "ws-1", base.analysis)


def test_registry_adapter_uses_one_verified_source_load_without_get_fallback():
    from fmea_governance_fixtures import make_governance_inputs

    from fmea_infrastructure.composition import RegistryGovernanceArtifactProvider

    base = make_governance_inputs()

    class SourceOnlyDomainRegistry:
        def get(self, _pack_id, _version):
            raise AssertionError("registry model must come from the verified source load")  # noqa: TRY003

        def get_source_bytes(self, _pack_id, _version):
            return b"invalid-domain-source"

    with pytest.raises(ValueError, match="domain_pack registry source"):
        RegistryGovernanceArtifactProvider(
            domain_pack=base.domain_pack,
            domain_pack_registry=SourceOnlyDomainRegistry(),
            template_registry=object(),
            scoring_rule_registry=object(),
            propagation_rule_registry=object(),
        ).get_artifacts("analysis-1", "ws-1", base.analysis)


def test_registry_adapter_rejects_source_bytes_not_matching_typed_artifact():
    from pathlib import Path

    from fmea_governance_fixtures import make_governance_inputs

    from core_domain.fmea.domain_pack import DomainPackManifest
    from fmea_infrastructure.composition import RegistryGovernanceArtifactProvider
    from fmea_infrastructure.domain_pack_registry import domain_pack_content_hash
    from structured_output_application import TemplateCompiler
    from structured_output_infrastructure import Draft202012SchemaAdapter, load_template_source

    base = make_governance_inputs()
    template = TemplateCompiler(
        schema_validator=Draft202012SchemaAdapter(),
        source_loader=load_template_source,
    ).compile_path(Path(__file__).parents[2] / "templates" / "examples" / "fmea-row-review.yaml")
    domain = DomainPackManifest(
        pack_id="generic-domain",
        version="1.0.0",
        content_hash="0" * 64,
        compatible_schema_ids=("graphrag.fmea.v1",),
        analysis_types=("fuel_system",),
        template_identities=((template.metadata.template_id, template.metadata.version),),
        scoring_rule_identities=(),
        propagation_rule_identities=(),
        extension_fields=(),
    )
    domain = replace(domain, content_hash=domain_pack_content_hash(domain))

    class DomainRegistry:
        def get(self, _object_id, _version):
            return domain

        def get_source_bytes(self, _object_id, _version):
            return b"domain-source"

    class TemplateRegistry:
        def get(self, _object_id, _version):
            return template

        def get_source_bytes(self, _object_id, _version):
            return b"not-the-registered-template"

    class EmptyRegistry:
        def get(self, _object_id, _version):
            raise AssertionError("undeclared registry must not be queried")  # noqa: TRY003

        def get_source_bytes(self, _object_id, _version):
            raise AssertionError("undeclared registry must not be queried")  # noqa: TRY003

    with pytest.raises(ValueError, match="source"):
        RegistryGovernanceArtifactProvider(
            domain_pack=domain,
            domain_pack_registry=DomainRegistry(),
            template_registry=TemplateRegistry(),
            scoring_rule_registry=EmptyRegistry(),
            propagation_rule_registry=EmptyRegistry(),
        ).get_artifacts("analysis-1", "ws-1", base.analysis)
