import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from storage_layer.graph_store import GraphEdgeRecord, GraphStore


PACKAGE_SRC = Path(__file__).resolve().parents[2] / "api_server" / "current_console" / "chroma_rag_poc" / "src"
if str(PACKAGE_SRC) not in sys.path:
    sys.path.insert(0, str(PACKAGE_SRC))

from chroma_rag_poc.routes_graphrag import router  # noqa: E402


def test_graphrag_export_route_downloads_graph_json(tmp_path):
    db_path = tmp_path / "graph.sqlite"
    store = GraphStore(db_path)
    store.import_edges(
        [
            GraphEdgeRecord(
                triple_id="T-001",
                subject="Gas turbine",
                subject_type="Equipment",
                predicate="HAS_COMPONENT",
                object_name="Compressor",
                object_type="Component",
                evidence="A gas turbine includes a compressor.",
                confidence=0.91,
            )
        ],
        reset=True,
    )

    app = FastAPI()
    app.state.persist_dir = tmp_path
    app.state.upload_dir = tmp_path
    app.include_router(router)

    response = TestClient(app).get("/api/graphrag/export", params={"graph_db_path": str(db_path)})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert "attachment" in response.headers["content-disposition"]
    payload = response.json()
    assert payload["format"] == "graphrag_graph_export"
    assert payload["summary"]["node_count"] == 2
    assert payload["edges"][0]["subject"] == "Gas turbine"
    assert payload["edges"][0]["object"] == "Compressor"
