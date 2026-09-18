from __future__ import annotations

from pathlib import Path
import sys

from fastapi.testclient import TestClient

from rag_orchestrator.triage import GraphRagTriageStore


REPO_ROOT = Path(__file__).resolve().parents[2]
CONSOLE_SRC = REPO_ROOT / "api_server" / "current_console" / "chroma_rag_poc" / "src"
if str(CONSOLE_SRC) not in sys.path:
    sys.path.insert(0, str(CONSOLE_SRC))


def test_graphrag_triage_store_summarizes_failure_analytics(tmp_path: Path) -> None:
    store = GraphRagTriageStore(tmp_path / "graphrag_triage.jsonl")
    store.append(
        {
            "question": "Why did global fail?",
            "created_at": "2026-06-19T01:00:00Z",
            "graph_quality_status": "fail",
            "route": {"strategy": "GLOBAL_SEARCH"},
            "source_evidence_count": 0,
            "graph_quality": {
                "quality_gate": {
                    "failures": [
                        {"metric": "summary_sentence_source_coverage"},
                        {"metric": "evidence_coverage"},
                    ]
                }
            },
        }
    )
    accepted = store.append(
        {
            "question": "Which local answer passed?",
            "created_at": "2026-06-20T02:00:00Z",
            "graph_quality_status": "pass",
            "route": {"strategy": "LOCAL_SEARCH"},
            "source_evidence_count": 2,
            "evaluation_case_id": "triage_local_pass",
        }
    )
    store.review(accepted["id"], review_status="accepted", review_note="grounded")

    analytics = store.analytics()

    assert analytics["total_count"] == 2
    assert analytics["by_graph_quality_status"] == {"fail": 1, "pass": 1}
    assert analytics["by_review_status"] == {"accepted": 1, "unreviewed": 1}
    assert analytics["by_route_strategy"] == {"GLOBAL_SEARCH": 1, "LOCAL_SEARCH": 1}
    assert analytics["promoted_case_count"] == 1
    assert analytics["source_evidence"]["covered_count"] == 1
    assert analytics["source_evidence"]["missing_count"] == 1
    assert analytics["by_failure_metric"] == {
        "evidence_coverage": 1,
        "summary_sentence_source_coverage": 1,
    }
    assert analytics["failure_trend"] == [
        {
            "date": "2026-06-19",
            "total_count": 1,
            "fail_count": 1,
            "pass_count": 0,
            "source_missing_count": 1,
            "promoted_case_count": 0,
        },
        {
            "date": "2026-06-20",
            "total_count": 1,
            "fail_count": 0,
            "pass_count": 1,
            "source_missing_count": 0,
            "promoted_case_count": 1,
        },
    ]
    route_drilldown = {item["route_strategy"]: item for item in analytics["route_drilldown"]}
    assert route_drilldown["GLOBAL_SEARCH"] == {
        "route_strategy": "GLOBAL_SEARCH",
        "total_count": 1,
        "pass_count": 0,
        "fail_count": 1,
        "accepted_count": 0,
        "rejected_count": 0,
        "unreviewed_count": 1,
        "source_coverage_rate": 0.0,
        "source_missing_count": 1,
        "promoted_case_count": 0,
        "failure_metrics": {
            "evidence_coverage": 1,
            "summary_sentence_source_coverage": 1,
        },
    }
    assert route_drilldown["LOCAL_SEARCH"]["source_coverage_rate"] == 1.0
    assert route_drilldown["LOCAL_SEARCH"]["accepted_count"] == 1
    assert route_drilldown["LOCAL_SEARCH"]["promoted_case_count"] == 1

    filtered = store.analytics(
        graph_quality_status="fail",
        review_status="unreviewed",
        route_strategy="GLOBAL_SEARCH",
    )

    assert filtered["total_count"] == 1
    assert filtered["by_graph_quality_status"] == {"fail": 1}
    assert filtered["by_review_status"] == {"unreviewed": 1}
    assert filtered["by_route_strategy"] == {"GLOBAL_SEARCH": 1}
    assert filtered["source_evidence"]["missing_count"] == 1
    assert filtered["by_failure_metric"] == {
        "evidence_coverage": 1,
        "summary_sentence_source_coverage": 1,
    }
    assert filtered["failure_trend"] == [
        {
            "date": "2026-06-19",
            "total_count": 1,
            "fail_count": 1,
            "pass_count": 0,
            "source_missing_count": 1,
            "promoted_case_count": 0,
        }
    ]
    assert len(filtered["route_drilldown"]) == 1
    assert filtered["route_drilldown"][0]["route_strategy"] == "GLOBAL_SEARCH"


def test_graphrag_triage_analytics_api_returns_same_summary(tmp_path: Path) -> None:
    from chroma_rag_poc.api import create_app

    persist_dir = tmp_path / "chroma"
    upload_dir = tmp_path / "uploads"
    store = GraphRagTriageStore(persist_dir / "graphrag_triage.jsonl")
    store.append(
        {
            "question": "Unsafe graph",
            "created_at": "2026-06-19T01:00:00Z",
            "graph_quality_status": "fail",
            "route": {"strategy": "GLOBAL_SEARCH"},
            "source_evidence_count": 0,
            "graph_quality": {"quality_gate": {"failures": [{"metric": "evidence_coverage"}]}},
        }
    )
    accepted = store.append(
        {
            "question": "Safe graph",
            "created_at": "2026-06-20T02:00:00Z",
            "graph_quality_status": "pass",
            "route": {"strategy": "LOCAL_SEARCH"},
            "source_evidence_count": 2,
        }
    )
    store.review(accepted["id"], review_status="accepted", review_note="grounded")

    client = TestClient(create_app(persist_dir=persist_dir, upload_dir=upload_dir))
    response = client.get(
        "/api/graphrag/triage/analytics",
        params={
            "graph_quality_status": "fail",
            "review_status": "unreviewed",
            "route_strategy": "GLOBAL_SEARCH",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_count"] == 1
    assert payload["by_graph_quality_status"] == {"fail": 1}
    assert payload["by_failure_metric"] == {"evidence_coverage": 1}
    assert payload["failure_trend"] == [
        {
            "date": "2026-06-19",
            "total_count": 1,
            "fail_count": 1,
            "pass_count": 0,
            "source_missing_count": 1,
            "promoted_case_count": 0,
        }
    ]
    assert payload["route_drilldown"][0]["route_strategy"] == "GLOBAL_SEARCH"
    assert payload["route_drilldown"][0]["failure_metrics"] == {"evidence_coverage": 1}
