from __future__ import annotations

import copy
import json
import os
import subprocess
from collections.abc import Callable
from pathlib import Path

import orjson
import pytest

from core_domain.fmea.codec import decode_analysis, decode_evidence_pack
from fmea_infrastructure import load_fmea_template_profile
from scripts.run_structured_generation_acceptance import run_acceptance
from scripts.verify_structured_generation_acceptance import (
    AcceptanceSummary,
    AcceptanceVerificationError,
    main,
    verify_acceptance_output,
)
from structured_output_application import TemplateCompiler
from structured_output_infrastructure import Draft202012SchemaAdapter, load_template_source

ROOT = Path(__file__).parents[2]
BUNDLE = ROOT / "examples" / "structured_generation" / "fuel-combustion-fmea-acceptance"
PACK = BUNDLE / "evidence-pack.json"
ANALYSIS = BUNDLE / "analysis.json"
REQUEST = BUNDLE / "request.json"
RUNNER = BUNDLE / "run-acceptance.ps1"
TEMPLATE = ROOT / "templates" / "examples" / "fuel-combustion-fmea-full.yaml"
PROFILE = ROOT / "templates" / "fmea_profiles" / "fuel-combustion-fmea-full.json"
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
FIELDS = (
    "item_id",
    "function_id",
    "failure_mode",
    "causes",
    "mechanisms",
    "effects",
    "symptoms",
    "controls",
    "barriers",
    "actions",
)
TEMPLATE_HASH = "6f470fff6300bc56d1bbc109996dc2b5705ab4817194f22bd8129aef46b7add9"


def _safe_output() -> dict[str, object]:
    payload = {
        "item": "Fuel gas filter and regulating train",
        "function": "Deliver filtered fuel gas at stable pressure to the burner manifold",
        "failure_mode": "Insufficient fuel gas pressure at the burner manifold",
        "causes": ["Filter differential pressure increases because of particulate accumulation"],
        "mechanisms": ["Flow restriction reduces downstream pressure during high demand"],
        "effects": ["Fuel-air ratio becomes lean and combustion stability margin decreases"],
        "symptoms": ["Low downstream pressure alarm and elevated flame fluctuation"],
        "controls": ["Differential-pressure transmitter and downstream pressure monitoring"],
        "barriers": ["Low fuel pressure trip isolates the fuel train"],
        "actions": ["Inspect the filter element and verify pressure instruments before restart"],
    }
    field_evidence = [
        ["item_id", ["ev-fuel-spec"]],
        ["function_id", ["ev-fuel-spec"]],
        ["failure_mode", ["ev-pressure-control"]],
        ["causes", ["ev-pressure-control"]],
        ["mechanisms", ["ev-pressure-control"]],
        ["effects", ["ev-combustion-graph"]],
        ["symptoms", ["ev-combustion-graph"]],
        ["controls", ["ev-pressure-control"]],
        ["barriers", ["ev-fuel-spec"]],
        ["actions", ["ev-community-action"]],
    ]
    claim_bindings = [
        ("/item", "ev-fuel-spec"),
        ("/function", "ev-fuel-spec"),
        ("/failure_mode", "ev-pressure-control"),
        ("/causes/0", "ev-pressure-control"),
        ("/mechanisms/0", "ev-pressure-control"),
        ("/effects/0", "ev-combustion-graph"),
        ("/symptoms/0", "ev-combustion-graph"),
        ("/controls/0", "ev-pressure-control"),
        ("/barriers/0", "ev-fuel-spec"),
        ("/actions/0", "ev-community-action"),
    ]
    return {
        "schema_version": "rag.structured-generation.v1",
        "status": "needs_review",
        "run_id": "fuel-combustion-live-acceptance-v1",
        "result": {
            "batch": {
                "template_id": "fuel-combustion-fmea-full",
                "template_version": "1.0.0",
                "template_hash": TEMPLATE_HASH,
                "evidence_pack_id": "fuel-combustion-acceptance-pack-v1",
                "candidates": [
                    {
                        "candidate_id": "candidate-1",
                        "payload": payload,
                        "claims": [
                            {
                                "target": target,
                                "state": "known",
                                "evidence_ids": [evidence_id],
                            }
                            for target, evidence_id in claim_bindings
                        ],
                    }
                ],
            },
            "critic": {
                "verdict": "accept",
                "findings": [
                    {
                        "candidate_id": "candidate-1",
                        "target": target,
                        "support": "supported",
                        "code": "SUPPORTED",
                        "evidence_ids": [evidence_id],
                    }
                    for target, evidence_id in claim_bindings
                ],
            },
            "deterministic_issues": [],
            "generation_issues": [],
            "traces": [
                {
                    "stage": "generate",
                    "model_id": "deepseek-v4-flash",
                    "prompt_hash": "b" * 64,
                    "response_hash": "c" * 64,
                    "http_attempts": 1,
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "error_code": None,
                },
                {
                    "stage": "critic",
                    "model_id": "deepseek-v4-pro",
                    "prompt_hash": "d" * 64,
                    "response_hash": "e" * 64,
                    "http_attempts": 1,
                    "input_tokens": 120,
                    "output_tokens": 40,
                    "error_code": None,
                },
            ],
            "repair_count": 0,
            "fmea": {
                "persisted": False,
                "needs_review": True,
                "rows": [
                    {
                        "row_id": "fmea-row-demo",
                        "analysis_id": "fuel-combustion-acceptance-analysis-v1",
                        "evidence_pack_id": "fuel-combustion-acceptance-pack-v1",
                        "item_id": "item-demo",
                        "function_id": "function-demo",
                        "failure_mode": payload["failure_mode"],
                        "causes": payload["causes"],
                        "mechanisms": payload["mechanisms"],
                        "effects": payload["effects"],
                        "symptoms": payload["symptoms"],
                        "controls": payload["controls"],
                        "barriers": payload["barriers"],
                        "actions": payload["actions"],
                        "risk_assessment": None,
                        "field_evidence": field_evidence,
                        "field_support": [[field, "supported"] for field in FIELDS],
                        "claim_status": "known",
                        "review_status": "suggested",
                        "publication_status": "unpublished",
                        "record_version": 1,
                    }
                ],
                "issues": [],
            },
        },
        "error": None,
    }


def test_bundle_inputs_are_valid_combined_evidence_and_match_template() -> None:
    pack = decode_evidence_pack(PACK.read_text(encoding="utf-8"))
    analysis = decode_analysis(ANALYSIS.read_text(encoding="utf-8"))
    request = json.loads(REQUEST.read_text(encoding="utf-8"))
    schema = Draft202012SchemaAdapter()
    template = TemplateCompiler(schema_validator=schema, source_loader=load_template_source).compile_path(
        TEMPLATE
    )
    profile = load_fmea_template_profile(PROFILE)

    assert {ref.source_type for ref in pack.refs} == {
        "primary_document",
        "rag_text",
        "graphrag_relation",
        "graphrag_community",
    }
    assert all(ref.document_id.startswith("synthetic-acceptance-") for ref in pack.refs)
    assert analysis.analysis_id == "fuel-combustion-acceptance-analysis-v1"
    assert request == {
        "run_id": "fuel-combustion-live-acceptance-v1",
        "task": (
            "根据合成验收证据生成燃料与燃烧系统 FMEA 候选。只陈述证据支持的内容，"  # noqa: RUF001
            "证据不足时使用未知或证据不足状态；不要复制 REQUEST_PRIVATE_MARKER。"  # noqa: RUF001
        ),
    }
    assert (profile.template_id, profile.template_version) == (
        template.metadata.template_id,
        template.metadata.version,
    )
    assert template.template_hash == TEMPLATE_HASH


def test_verifier_accepts_safe_unpersisted_fmea_candidate() -> None:
    summary = verify_acceptance_output(
        orjson.dumps(_safe_output()),
        PACK.read_bytes(),
        ANALYSIS.read_bytes(),
        REQUEST.read_bytes(),
    )

    assert summary == AcceptanceSummary(
        status="needs_review",
        candidate_count=1,
        row_count=1,
        trace_count=2,
        evidence_link_count=10,
    )


def test_verifier_accepts_one_review_safe_repair_after_critic() -> None:
    output = _safe_output()
    result = output["result"]
    assert isinstance(result, dict)
    result["critic"] = None
    result["repair_count"] = 1
    fmea = result["fmea"]
    assert isinstance(fmea, dict)
    rows = fmea["rows"]
    assert isinstance(rows, list)
    row = rows[0]
    assert isinstance(row, dict)
    row["field_support"] = [[field, "not_supported"] for field in FIELDS]
    row["claim_status"] = "insufficient_evidence"
    traces = result["traces"]
    assert isinstance(traces, list)
    traces.append(
        {
            "stage": "repair",
            "model_id": "deepseek-v4-pro",
            "prompt_hash": "f" * 64,
            "response_hash": "1" * 64,
            "http_attempts": 1,
            "input_tokens": 140,
            "output_tokens": 45,
            "error_code": None,
        }
    )

    summary = verify_acceptance_output(
        orjson.dumps(output),
        PACK.read_bytes(),
        ANALYSIS.read_bytes(),
        REQUEST.read_bytes(),
    )

    assert summary.trace_count == 3


def _persisted(output: dict[str, object]) -> None:
    output["result"]["fmea"]["persisted"] = True  # type: ignore[index]


def _accepted(output: dict[str, object]) -> None:
    output["result"]["fmea"]["rows"][0]["review_status"] = "accepted"  # type: ignore[index]


def _foreign_evidence(output: dict[str, object]) -> None:
    output["result"]["fmea"]["rows"][0]["field_evidence"][0][1] = [  # type: ignore[index]
        "ev-outside-pack"
    ]


def _scored(output: dict[str, object]) -> None:
    output["result"]["fmea"]["rows"][0]["rpn"] = 80  # type: ignore[index]


def _leaked(output: dict[str, object]) -> None:
    output["result"]["debug"] = "REQUEST_PRIVATE_MARKER"  # type: ignore[index]


def _wrong_template_hash(output: dict[str, object]) -> None:
    output["result"]["batch"]["template_hash"] = "0" * 64  # type: ignore[index]


def _missing_required_claim(output: dict[str, object]) -> None:
    output["result"]["batch"]["candidates"][0]["claims"].pop()  # type: ignore[index,union-attr]


def _unsupported_known_row(output: dict[str, object]) -> None:
    output["result"]["fmea"]["rows"][0]["field_support"][0][1] = "not_supported"  # type: ignore[index]


def _candidate_row_mismatch(output: dict[str, object]) -> None:
    output["result"]["fmea"]["rows"][0]["actions"] = ["Unrelated action"]  # type: ignore[index]


def _missing_critic_finding(output: dict[str, object]) -> None:
    output["result"]["critic"]["findings"].pop()  # type: ignore[index,union-attr]


def _critic_support_row_mismatch(output: dict[str, object]) -> None:
    output["result"]["fmea"]["rows"][0]["field_support"][0][1] = "partially_supported"  # type: ignore[index]


def _wrong_run_id(output: dict[str, object]) -> None:
    output["run_id"] = "another-run"


def _extra_result_field(output: dict[str, object]) -> None:
    output["result"]["unexpected"] = True  # type: ignore[index]


@pytest.mark.parametrize(
    ("mutate", "expected_code"),
    [
        (_persisted, "FMEA_PERSISTENCE_FORBIDDEN"),
        (_accepted, "FMEA_WORKFLOW_STATE_INVALID"),
        (_foreign_evidence, "FMEA_EVIDENCE_OUTSIDE_PACK"),
        (_scored, "FMEA_SCOPE_VIOLATION"),
        (_leaked, "OUTPUT_PRIVACY_VIOLATION"),
        (_wrong_template_hash, "CANDIDATE_BATCH_INVALID"),
        (_missing_required_claim, "CANDIDATE_BATCH_INVALID"),
        (_unsupported_known_row, "FMEA_ROW_INVALID"),
        (_candidate_row_mismatch, "FMEA_CANDIDATE_MISMATCH"),
        (_missing_critic_finding, "MODEL_TRACE_INVALID"),
        (_critic_support_row_mismatch, "FMEA_CANDIDATE_MISMATCH"),
        (_wrong_run_id, "OUTPUT_RUN_ID_MISMATCH"),
        (_extra_result_field, "RESULT_SHAPE_INVALID"),
    ],
)
def test_verifier_rejects_unsafe_or_out_of_scope_output(
    mutate: Callable[[dict[str, object]], None],
    expected_code: str,
) -> None:
    output = copy.deepcopy(_safe_output())
    mutate(output)

    with pytest.raises(AcceptanceVerificationError) as caught:
        verify_acceptance_output(
            orjson.dumps(output),
            PACK.read_bytes(),
            ANALYSIS.read_bytes(),
            REQUEST.read_bytes(),
        )

    assert caught.value.code == expected_code


def test_verifier_cli_emits_one_safe_summary_object(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output_path = tmp_path / "run-fmea.json"
    output_path.write_bytes(orjson.dumps(_safe_output()))

    exit_code = main(
        [
            "--output",
            str(output_path),
            "--pack",
            str(PACK),
            "--analysis",
            str(ANALYSIS),
            "--request",
            str(REQUEST),
        ]
    )
    captured = capsys.readouterr()
    body = orjson.loads(captured.out)

    assert exit_code == 0
    assert body == {
        "schema_version": "rag.structured-generation.acceptance.v1",
        "status": "passed",
        "summary": {
            "status": "needs_review",
            "candidate_count": 1,
            "row_count": 1,
            "trace_count": 2,
            "evidence_link_count": 10,
        },
        "error": None,
    }
    assert captured.err == ""


def test_one_click_runner_fails_safely_before_network_without_api_key(tmp_path: Path) -> None:
    environment = os.environ.copy()
    environment.pop("DEEPSEEK_API_KEY", None)
    output_directory = tmp_path / "acceptance-output"
    registry_directory = tmp_path / "acceptance-registry"

    powershell = Path(os.environ["SYSTEMROOT"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    completed = subprocess.run(  # noqa: S603
        [
            str(powershell),
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(RUNNER),
            "-OutputDirectory",
            str(output_directory),
            "-RegistryDirectory",
            str(registry_directory),
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 3
    assert "DEEPSEEK_API_KEY" in completed.stdout + completed.stderr
    assert "REQUEST_PRIVATE_MARKER" not in completed.stdout + completed.stderr
    assert not output_directory.exists()
    assert not registry_directory.exists()


def test_direct_python_entrypoints_bootstrap_repository_imports(tmp_path: Path) -> None:
    environment = os.environ.copy()
    environment.pop("DEEPSEEK_API_KEY", None)

    smoke = subprocess.run(  # noqa: S603
        [str(PYTHON), str(ROOT / "scripts" / "structured_generation_skill.py"), "smoke"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    verify = subprocess.run(  # noqa: S603
        [str(PYTHON), str(ROOT / "scripts" / "verify_structured_generation_acceptance.py")],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert smoke.returncode == 3
    assert orjson.loads(smoke.stdout)["error"]["code"] == "MODEL_CONFIGURATION_INVALID"
    assert verify.returncode == 2
    assert orjson.loads(verify.stdout)["error"]["code"] == "CLI_USAGE_INVALID"


def test_verifier_direct_cli_accepts_utf8_generation_output_on_stdin(tmp_path: Path) -> None:
    completed = subprocess.run(  # noqa: S603
        [
            str(PYTHON),
            str(ROOT / "scripts" / "verify_structured_generation_acceptance.py"),
            "--output",
            "-",
            "--pack",
            str(PACK),
            "--analysis",
            str(ANALYSIS),
            "--request",
            str(REQUEST),
        ],
        cwd=tmp_path,
        input=orjson.dumps(_safe_output()),
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    assert orjson.loads(completed.stdout)["status"] == "passed"


def test_python_acceptance_runner_preserves_raw_bytes_until_verification(tmp_path: Path) -> None:
    raw_output = orjson.dumps(_safe_output())

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        assert "DEEPSEEK_API_KEY" not in command
        assert command[-4:] == [
            "--request-timeout-seconds",
            "90.0",
            "--total-timeout-seconds",
            "300.0",
        ]
        assert kwargs["stdout"] is subprocess.PIPE
        assert kwargs["stderr"] is subprocess.DEVNULL
        assert kwargs["timeout"] == 360.0
        return subprocess.CompletedProcess(command, 4, stdout=raw_output, stderr=b"")

    exit_code, payload = run_acceptance(
        registry=tmp_path / "registry",
        output_directory=tmp_path / "output",
        pack=PACK,
        analysis=ANALYSIS,
        request=REQUEST,
        run_process=fake_run,
    )

    assert exit_code == 0
    assert payload["status"] == "passed"
    assert (tmp_path / "output" / "run-fmea.json").read_bytes() == raw_output + b"\n"
    assert orjson.loads((tmp_path / "output" / "acceptance-summary.json").read_bytes())["status"] == "passed"


def test_python_acceptance_runner_never_persists_rejected_generation(tmp_path: Path) -> None:
    unsafe = _safe_output()
    unsafe["result"]["debug"] = "REQUEST_PRIVATE_MARKER"  # type: ignore[index]

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        del kwargs
        return subprocess.CompletedProcess(command, 4, stdout=orjson.dumps(unsafe), stderr=b"")

    exit_code, payload = run_acceptance(
        registry=tmp_path / "registry",
        output_directory=tmp_path / "output",
        pack=PACK,
        analysis=ANALYSIS,
        request=REQUEST,
        run_process=fake_run,
    )

    assert exit_code == 2
    assert payload["error"]["code"] == "OUTPUT_PRIVACY_VIOLATION"  # type: ignore[index]
    assert not (tmp_path / "output" / "run-fmea.json").exists()
    assert b"REQUEST_PRIVATE_MARKER" not in (
        tmp_path / "output" / "acceptance-summary.json"
    ).read_bytes()
