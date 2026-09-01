"""Atomic latest-pointer and temporary-artifact regressions."""

from __future__ import annotations

from pathlib import Path

import pytest

import scripts.run_fmea_governance_acceptance as runner
from scripts.run_fmea_governance_acceptance import run_acceptance
from scripts.verify_fmea_governance_acceptance import verify_latest


def test_replace_failure_keeps_previous_latest(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = tmp_path / "acceptance"
    previous = run_acceptance(output_root=root)

    def fail_replace(_source: object, _destination: object) -> None:
        raise OSError("replace failed")  # noqa: TRY003

    monkeypatch.setattr(runner.os, "replace", fail_replace)
    with pytest.raises(OSError, match="replace failed"):
        run_acceptance(output_root=root)

    assert verify_latest(root).artifact_id == previous.artifact_id
    assert not tuple(root.glob(".acceptance-*.tmp"))


def test_failure_after_partial_write_cleans_temporary_artifact(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = tmp_path / "acceptance"
    original_write = runner._write_artifact
    writes = 0

    def fail_after_one(path: Path, payload: bytes) -> None:
        nonlocal writes
        original_write(path, payload)
        writes += 1
        if writes == 1:
            raise OSError("partial write failed")  # noqa: TRY003

    monkeypatch.setattr(runner, "_write_artifact", fail_after_one)
    with pytest.raises(OSError, match="partial write failed"):
        run_acceptance(output_root=root)

    assert writes == 1
    assert not root.exists() or not tuple(root.iterdir())


def test_latest_switch_waits_for_independent_verification(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "acceptance"

    def reject(_directory: Path):
        return runner.VerificationResult(False, "", "FMEA_ARTIFACT_VERIFICATION_FAILED")

    monkeypatch.setattr(runner, "verify_acceptance_directory", reject)
    with pytest.raises(runner.AcceptanceRunError, match="FMEA_ARTIFACT_VERIFICATION_FAILED"):
        run_acceptance(output_root=root)

    assert not root.exists() or not tuple(root.iterdir())
