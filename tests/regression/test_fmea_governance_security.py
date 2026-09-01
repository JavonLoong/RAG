"""Security regressions for canonical governance acceptance artifacts."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

import scripts.run_fmea_governance_acceptance as runner
from scripts.run_fmea_governance_acceptance import run_acceptance
from scripts.verify_fmea_governance_acceptance import verify


def test_verifier_does_not_import_runner_validation_functions() -> None:
    source = Path("scripts/verify_fmea_governance_acceptance.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported_modules.update(
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    )
    assert not any(name and name.endswith("run_fmea_governance_acceptance") for name in imported_modules)


def test_verifier_rejects_private_markers_before_hash_replay(tmp_path: Path) -> None:
    result = run_acceptance(output_root=tmp_path / "acceptance")
    snapshot_path = result.artifact_dir / "snapshots.json"
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    payload["items"][0]["private_path"] = "C:\\Users\\private\\evidence"
    snapshot_path.write_bytes((json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"))

    assert verify(result.artifact_dir).error_code == "FMEA_PRIVATE_MARKER"


def test_component_walk_rejects_non_directory_without_symlink_privilege(tmp_path: Path) -> None:
    blocked = tmp_path / "blocked-component"
    blocked.write_text("not a directory", encoding="utf-8")

    with pytest.raises(runner.AcceptanceRunError) as error:
        runner._safe_output_root(blocked / "nested")

    assert error.value.code == "OUTPUT_ROOT_INVALID"


def test_verifier_rejects_noncanonical_json(tmp_path: Path) -> None:
    result = run_acceptance(output_root=tmp_path / "acceptance")
    summary_path = result.artifact_dir / "acceptance-summary.json"
    summary_path.write_bytes(summary_path.read_bytes().replace(b"{", b"{ ", 1))

    assert verify(result.artifact_dir).error_code == "FMEA_NON_CANONICAL_JSON"
