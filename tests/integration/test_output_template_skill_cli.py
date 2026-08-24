from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from core_domain.fmea.codec import encode_json
from core_domain.fmea.value_objects import EvidencePack

ROOT = Path(__file__).parents[2]
SCRIPT = ROOT / "scripts" / "output_template_skill.py"
FMEA_TEMPLATE = ROOT / "tests" / "fixtures" / "structured_output" / "fmea.yaml"


def run_cli(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        [sys.executable, str(SCRIPT), *arguments],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def payload(result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    loaded = json.loads(result.stdout)
    assert isinstance(loaded, dict)
    return loaded


def test_validate_and_compile_emit_one_stable_json_object(tmp_path: Path) -> None:
    validation = run_cli("validate", str(FMEA_TEMPLATE))
    output_path = tmp_path / "compiled.json"
    compilation = run_cli("compile", str(FMEA_TEMPLATE), "--out", str(output_path))

    assert validation.returncode == compilation.returncode == 0
    assert payload(validation)["schema_version"] == "rag.structured-output.v1"
    assert payload(compilation)["status"] == "ok"
    assert output_path.read_text(encoding="utf-8").startswith("{")
    assert validation.stdout.count("\n") == compilation.stdout.count("\n") == 1
    assert validation.stderr == compilation.stderr == ""


def test_register_and_show_round_trip_across_processes(tmp_path: Path) -> None:
    registered = run_cli("register", str(FMEA_TEMPLATE), "--registry", str(tmp_path))
    shown = run_cli(
        "show",
        "fuel-combustion-fmea@1.0.0",
        "--registry",
        str(tmp_path),
    )

    assert registered.returncode == shown.returncode == 0
    assert payload(registered)["result"]["template_hash"] == payload(shown)["result"]["template_hash"]


def test_example_pretty_wrapper_is_explicit_and_deterministic(tmp_path: Path) -> None:
    assert run_cli("register", str(FMEA_TEMPLATE), "--registry", str(tmp_path)).returncode == 0

    first = run_cli(
        "example",
        "fuel-combustion-fmea@1.0.0",
        "--registry",
        str(tmp_path),
        "--pretty",
    )
    second = run_cli(
        "example",
        "fuel-combustion-fmea@1.0.0",
        "--registry",
        str(tmp_path),
        "--pretty",
    )

    assert first.returncode == second.returncode == 0
    assert payload(first) == payload(second)
    assert payload(first)["result"]["example_only"] is True
    assert "\n  \"" in first.stdout


def test_validate_candidate_round_trip_uses_registered_template_and_pack(
    tmp_path: Path,
    fixture_pack: EvidencePack,
) -> None:
    registry = tmp_path / "registry"
    registered = run_cli("register", str(FMEA_TEMPLATE), "--registry", str(registry))
    template_hash = payload(registered)["result"]["template_hash"]
    batch_path = tmp_path / "batch.json"
    pack_path = tmp_path / "pack.json"
    batch_path.write_text(
        json.dumps(
            {
                "template_id": "fuel-combustion-fmea",
                "template_version": "1.0.0",
                "template_hash": template_hash,
                "evidence_pack_id": fixture_pack.pack_id,
                "candidates": [
                    {
                        "candidate_id": "candidate-1",
                        "payload": {
                            "item": "fuel filter",
                            "failure_mode": "blockage",
                            "effects": ["low pressure"],
                        },
                        "claims": [
                            {"target": "/item", "state": "known", "evidence_ids": ["ev-1"]},
                            {
                                "target": "/failure_mode",
                                "state": "known",
                                "evidence_ids": ["ev-1"],
                            },
                            {"target": "/effects/0", "state": "known", "evidence_ids": ["ev-1"]},
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    pack_path.write_text(encode_json(fixture_pack), encoding="utf-8")

    result = run_cli(
        "validate-candidate",
        str(batch_path),
        "--pack",
        str(pack_path),
        "--registry",
        str(registry),
    )

    assert result.returncode == 0
    assert payload(result)["result"]["valid"] is True


def test_invalid_candidate_and_missing_registry_have_distinct_exit_classes(
    tmp_path: Path,
    fixture_pack: EvidencePack,
) -> None:
    registry = tmp_path / "registry"
    registered = run_cli("register", str(FMEA_TEMPLATE), "--registry", str(registry))
    template_hash = payload(registered)["result"]["template_hash"]
    batch_path = tmp_path / "invalid.json"
    pack_path = tmp_path / "pack.json"
    batch_path.write_text(
        json.dumps(
            {
                "template_id": "fuel-combustion-fmea",
                "template_version": "1.0.0",
                "template_hash": template_hash,
                "evidence_pack_id": fixture_pack.pack_id,
                "candidates": [
                    {
                        "candidate_id": "bad",
                        "payload": {"item": "x", "failure_mode": "y", "effects": ["z"]},
                        "claims": [],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    pack_path.write_text(encode_json(fixture_pack), encoding="utf-8")

    invalid = run_cli(
        "validate-candidate",
        str(batch_path),
        "--pack",
        str(pack_path),
        "--registry",
        str(registry),
    )
    missing = run_cli(
        "show",
        "fuel-combustion-fmea@9.9.9",
        "--registry",
        str(registry),
    )

    assert invalid.returncode == 2
    assert payload(invalid)["status"] == "error"
    assert missing.returncode == 3
    assert payload(missing)["error"]["code"] == "TEMPLATE_NOT_FOUND"


def test_parser_rejects_abbreviations_and_never_echoes_secret_arguments(tmp_path: Path) -> None:
    marker = "SECRET-MARKER-C:/private/customer"
    abbreviated = run_cli("reg", marker, "--registry", str(tmp_path))
    malformed = run_cli("show", marker, "--registry", str(tmp_path))

    assert abbreviated.returncode == malformed.returncode == 2
    assert payload(abbreviated)["error"]["code"] == "CLI_USAGE_INVALID"
    assert marker not in abbreviated.stdout + abbreviated.stderr + malformed.stdout + malformed.stderr


def test_tampered_registry_is_dependency_failure_without_private_content(tmp_path: Path) -> None:
    registered = run_cli("register", str(FMEA_TEMPLATE), "--registry", str(tmp_path))
    assert registered.returncode == 0
    compiled_path = tmp_path / "fuel-combustion-fmea" / "1.0.0" / "compiled.json"
    compiled_path.write_text('{"private":"DO-NOT-ECHO"}', encoding="utf-8")

    shown = run_cli(
        "show",
        "fuel-combustion-fmea@1.0.0",
        "--registry",
        str(tmp_path),
    )

    assert shown.returncode == 3
    assert payload(shown)["error"]["code"] == "TEMPLATE_HASH_MISMATCH"
    assert "DO-NOT-ECHO" not in shown.stdout + shown.stderr
