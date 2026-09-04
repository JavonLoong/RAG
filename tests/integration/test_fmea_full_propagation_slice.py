from __future__ import annotations

import importlib.util
import sqlite3
import sys
from contextlib import closing
from dataclasses import replace
from pathlib import Path

import pytest

from core_domain.fmea.governance import canonical_hash
from core_domain.fmea.propagation import PropagationGraphRevision
from core_domain.fmea.states import PropagationStatus, RiskStatus
from fmea_infrastructure.propagation_repository_sqlite import SqlitePropagationRepository
from fmea_infrastructure.topology_json import JsonTopologyRepository


def _load_module(filename: str, module_name: str):
    root = Path(__file__).resolve().parents[2]
    source = root / "examples" / "fmea" / "full-acceptance" / filename
    spec = importlib.util.spec_from_file_location(module_name, source)
    if spec is None or spec.loader is None:
        raise AssertionError(f"{filename} helper is not loadable")  # noqa: TRY003 - test invariant
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_propagation_slice_runs_real_review_and_replays_without_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate_module = _load_module(
        "candidate_review_risk_slice.py", "fmea_candidate_review_risk_slice_for_propagation"
    )
    propagation_module = _load_module(
        "propagation_slice.py", "fmea_propagation_slice"
    )
    candidate = candidate_module.run_candidate_review_risk(tmp_path)
    database_path = tmp_path / "fmea.sqlite3"
    repository = SqlitePropagationRepository(database_path)
    repository.initialize()
    assert repository.count_propagation_records(candidate.evidence_pack.workspace_id) == 0
    original_row_hash = canonical_hash(candidate.row, prefixed=True)
    native_neighbors = JsonTopologyRepository.neighbors
    neighbor_calls = []

    def observed_neighbors(self, snapshot, entity_id):
        neighbor_calls.append((snapshot, entity_id))
        return native_neighbors(self, snapshot, entity_id)

    monkeypatch.setattr(JsonTopologyRepository, "neighbors", observed_neighbors)
    native_generate = propagation_module._DeterministicPropagationGenerator.generate
    model_requests = []

    def observed_generate(self, request):
        model_requests.append(request)
        return native_generate(self, request)

    monkeypatch.setattr(propagation_module._DeterministicPropagationGenerator, "generate", observed_generate)

    result = propagation_module.run_propagation(
        database_path=database_path,
        analysis=candidate.analysis,
        row=candidate.row,
        assessment=candidate.assessment,
        evidence_pack=candidate.evidence_pack,
        registry_root=tmp_path / "immutable-registries",
    )

    assert isinstance(result.graph, PropagationGraphRevision)
    assert result.graph.status is PropagationStatus.CONFIRMED
    assert [item["status"] for item in result.evidence["propagation_graphs"]] == [
        "proposed",
        "confirmed",
    ]
    assert result.evidence["steps"]
    assert {step["command"] for step in result.evidence["steps"]} == {
        "fmea.propagation.start",
        "fmea.propagation.review",
    }
    assert all(replay["same_persisted_result"] for replay in result.evidence["replays"])
    assert all(
        replay["event_counts_before"] == replay["event_counts_after"]
        and replay["propagation_records_before"] == replay["propagation_records_after"]
        for replay in result.evidence["replays"]
    )
    for replay in result.evidence["replays"]:
        assert replay["state_hash_before"].startswith("sha256:")
        assert replay["state_hash_before"] == replay["state_hash_after"]
    assert result.evidence["steps"][0]["before"]["propagation_records"] == 0
    assert neighbor_calls
    assert all(
        snapshot.workspace_id == candidate.evidence_pack.workspace_id
        and snapshot.analysis_id == candidate.analysis.analysis_id
        for snapshot, _ in neighbor_calls
    )
    assert any(entity_id == "fuel_filter" for _, entity_id in neighbor_calls)
    assert candidate.row.record_version == 2
    assert result.evidence["source_row_bindings"] == [{
        "row_id": candidate.row.row_id,
        "record_version": 2,
        "row_hash": original_row_hash,
        "persisted_row_hash_after": original_row_hash,
    }]
    assert repository.get_row(candidate.row.row_id, candidate.evidence_pack.workspace_id) == candidate.row
    assert canonical_hash(candidate.row, prefixed=True) == original_row_hash
    assert candidate.assessment.status is RiskStatus.CONFIRMED
    assert candidate.assessment.source_record_version == candidate.row.record_version == 2
    assert len(model_requests) == 1
    assert model_requests[0].source_rows == (replace(candidate.row, item_id="fuel_filter"),)
    lineage = result.evidence["source_row_lineage"]
    assert lineage == [
        {
            "graph_revision_id": graph["graph_revision_id"],
            "run_id": model_requests[0].run_id,
            "source_row_id": candidate.row.row_id,
            "record_version": 2,
            "canonical_row_hash": original_row_hash,
        }
        for graph in result.evidence["propagation_graphs"]
    ]
    assert model_requests[0].run_id == result.evidence["propagation_runs"][0]["run_id"]
    for graph in result.evidence["propagation_graphs"]:
        assert tuple(
            entry["source_row_id"] for entry in lineage if entry["graph_revision_id"] == graph["graph_revision_id"]
        ) == repository.get_graph_source_row_ids(graph["graph_revision_id"], candidate.evidence_pack.workspace_id)
    assert all(isinstance(item, dict) for key in ("audits", "outbox") for item in result.evidence[key])

    accepted_edges = [
        edge
        for graph in result.evidence["propagation_graphs"]
        for edge in graph["edges"]
        if edge["review_status"] == "accepted"
    ]
    assert accepted_edges
    assert {(edge["source_entity_id"], edge["target_entity_id"]) for edge in accepted_edges} == {
        ("fuel_filter", "fuel_manifold"),
    }
    pack_evidence_ids = {ref.evidence_id for ref in candidate.evidence_pack.refs}
    for edge in accepted_edges:
        assert edge["evidence_ids"] == ["fuel-evidence-ref-1"]
        assert set(edge["evidence_ids"]) <= pack_evidence_ids
    review_audits = [event for event in result.evidence["audits"] if event["command"] == "fmea.propagation.review"]
    assert len(review_audits) == 1
    assert review_audits[0]["actor_id"] == "fuel-propagation-reviewer"
    assert review_audits[0]["actor_type"] == "human"
    assert "propagation_reviewer" in review_audits[0]["actor_roles"]

    # Mutable row metadata can change in place without changing any counts.
    before_hash = propagation_module._persisted_state_hash(database_path)
    assert before_hash == result.evidence["replays"][-1]["state_hash_after"]
    before_counts = propagation_module._persisted_counts(database_path, repository, candidate.evidence_pack.workspace_id)
    with closing(sqlite3.connect(database_path)) as connection:
        original_updated_at = connection.execute(
            "SELECT updated_at FROM fmea_rows WHERE row_id = ?", (candidate.row.row_id,),
        ).fetchone()[0]
        connection.execute(
            "UPDATE fmea_rows SET updated_at = ? WHERE row_id = ?",
            ("2026-09-05T00:00:00Z", candidate.row.row_id),
        )
        connection.commit()
        try:
            assert propagation_module._persisted_counts(
                database_path, repository, candidate.evidence_pack.workspace_id,
            ) == before_counts
            assert propagation_module._persisted_state_hash(database_path) != before_hash
        finally:
            connection.execute(
                "UPDATE fmea_rows SET updated_at = ? WHERE row_id = ?",
                (original_updated_at, candidate.row.row_id),
            )
            connection.commit()
    assert propagation_module._persisted_state_hash(database_path) == before_hash
