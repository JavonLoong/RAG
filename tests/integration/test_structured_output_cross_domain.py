from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from core_domain.fmea.value_objects import EvidencePack
from core_domain.structured_output import (
    CandidateClaim,
    ClaimState,
    StructuredCandidate,
    StructuredCandidateBatch,
)
from structured_output_application import (
    StructuredCandidateValidator,
    StructuredOutputService,
    TemplateCompiler,
)
from structured_output_infrastructure import (
    Draft202012SchemaAdapter,
    FileTemplateRegistry,
    load_template_source,
)

ROOT = Path(__file__).parents[2]
EXAMPLES = ROOT / "templates" / "examples"
SCRIPT = ROOT / "scripts" / "output_template_skill.py"

CASES = (
    (
        "fuel-combustion-fmea.yaml",
        {
            "item": "fuel filter",
            "failure_mode": "blockage",
            "effects": ["low pressure"],
        },
        ("/item", "/failure_mode", "/effects/0"),
    ),
    (
        "maintenance-checklist.yaml",
        {
            "asset_id": "asset-1",
            "checks": [{"result": "pass", "note": "observed"}],
        },
        ("/asset_id", "/checks/0/result"),
    ),
    (
        "research-summary.yaml",
        {
            "paper_id": "paper-1",
            "claims": [{"statement": "claim", "limitations": "limited sample"}],
        },
        ("/paper_id", "/claims/0/statement"),
    ),
)


def service(root: Path) -> StructuredOutputService:
    schema = Draft202012SchemaAdapter()
    compiler = TemplateCompiler(schema_validator=schema, source_loader=load_template_source)
    return StructuredOutputService(
        compiler=compiler,
        registry=FileTemplateRegistry(root),
        schema_validator=schema,
        candidate_validator=StructuredCandidateValidator(schema),
    )


@pytest.mark.parametrize(("filename", "payload", "targets"), CASES)
def test_one_service_runs_the_full_cross_domain_handoff(
    tmp_path: Path,
    fixture_pack: EvidencePack,
    filename: str,
    payload: dict[str, object],
    targets: tuple[str, ...],
) -> None:
    source = EXAMPLES / filename
    output = service(tmp_path / "registry")

    loaded_source = load_template_source(source)
    compiled = output.compile_source(source)
    registered = output.register_source(source)
    reloaded = output.get_template(compiled.metadata.template_id, compiled.metadata.version)
    example = output.make_example(compiled.metadata.template_id, compiled.metadata.version)
    candidate = StructuredCandidate(
        candidate_id="candidate-1",
        payload=payload,
        claims=tuple(
            CandidateClaim(target=target, state=ClaimState.KNOWN, evidence_ids=("ev-1",))
            for target in targets
        ),
    )
    batch = StructuredCandidateBatch(
        template_id=compiled.metadata.template_id,
        template_version=compiled.metadata.version,
        template_hash=compiled.template_hash,
        evidence_pack_id=fixture_pack.pack_id,
        candidates=(candidate,),
    )
    report = output.validate_candidates(batch, fixture_pack)

    assert loaded_source["template"]["id"] == compiled.metadata.template_id
    assert registered == reloaded == compiled
    assert output.make_example(compiled.metadata.template_id, compiled.metadata.version) == example
    assert Draft202012SchemaAdapter().validate(
        example.candidates[0].payload,
        compiled.output_schema,
    ) == ()
    assert report.valid is True


@pytest.mark.parametrize("filename", [case[0] for case in CASES])
def test_one_cli_contract_validates_every_production_domain(filename: str) -> None:
    result = subprocess.run(  # noqa: S603
        [sys.executable, str(SCRIPT), "validate", str(EXAMPLES / filename)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode == 0
    envelope = json.loads(result.stdout)
    assert envelope["schema_version"] == "rag.structured-output.v1"
    assert envelope["status"] == "ok"


def test_generic_import_boundary_excludes_query_storage_models_and_fmea_layers() -> None:
    code = """
import json
import sys
import core_domain.structured_output
import structured_output_application
forbidden = (
    'fmea_application',
    'fmea_infrastructure',
    'storage_layer.graph_store',
    'chroma_rag_poc.query_service',
    'chromadb',
    'openai',
    'deepseek',
)
loaded = sorted(name for name in sys.modules if name.startswith(forbidden))
print(json.dumps({'loaded': loaded}))
"""
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", code],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode == 0
    assert json.loads(result.stdout) == {"loaded": []}
