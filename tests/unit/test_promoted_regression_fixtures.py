from __future__ import annotations

import json
from pathlib import Path

from evaluation import (
    LocalChromaRegressionRag,
    WECHAT_PRIVATE_CONTACT_CASE,
    run_graphrag_triage_regression,
    seed_promoted_graphrag_regression_fixture,
)
from evaluation.smoke import SMOKE_COLLECTION


def test_seed_promoted_private_contact_case_is_nonempty_and_evaluable(tmp_path: Path) -> None:
    persist_dir = tmp_path / "chroma"
    dataset_path = tmp_path / "evaluation" / "graphrag_triage_regression.jsonl"
    report_dir = tmp_path / "reports"

    seed_result = seed_promoted_graphrag_regression_fixture(
        persist_dir=persist_dir,
        dataset_path=dataset_path,
        collection_name=SMOKE_COLLECTION,
        backend="hashing",
    )

    assert seed_result["seeded_case_id"] == WECHAT_PRIVATE_CONTACT_CASE.id
    records = [json.loads(line) for line in dataset_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert [record["id"] for record in records] == [WECHAT_PRIVATE_CONTACT_CASE.id]
    assert records[0]["task_type"] == "private_contact_affection_sweep"
    assert "晚安宝贝抱抱" in records[0]["expected_evidence_keywords"]

    result = run_graphrag_triage_regression(
        rag_system=LocalChromaRegressionRag(
            persist_dir=persist_dir,
            collection_name=SMOKE_COLLECTION,
            top_k=10,
            backend="hashing",
        ),
        dataset_path=dataset_path,
        report_dir=report_dir,
        top_k=10,
    )

    assert result["gate_status"] == "pass"
    assert result["case_count"] == 1
    assert Path(result["reports"]["json"]).exists()
