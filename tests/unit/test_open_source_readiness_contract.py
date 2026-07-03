from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[2]


def test_project_front_door_mentions_required_paths():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    required = [
        "npm run check",
        "npm run desktop",
        "api_server/current_console/server.py",
        "frontend_app/current_console/index.html",
        "electron/main.cjs",
        "storage_layer/graph_store.py",
        "rag_orchestrator/",
    ]
    for text in required:
        assert text in readme


def test_desktop_one_click_contract_is_present():
    html = (ROOT / "frontend_app/current_console/index.html").read_text(encoding="utf-8")
    required = [
        "btnKgWechatOneClick",
        "WECHAT_AFFECTION_QUESTION",
        "applyWechatAffectionGraphPreset",
        "runWechatAffectionOneClick",
        "kgPublicBooksJsonMode",
        "generative",
    ]
    for text in required:
        assert text in html


def test_electron_local_file_picker_contract_is_present():
    main = (ROOT / "electron/main.cjs").read_text(encoding="utf-8")
    preload = (ROOT / "electron/preload.cjs").read_text(encoding="utf-8")
    assert "power-rag:pick-wechat-rag-corpus" in main
    assert "findDefaultWechatRagCorpus" in main
    assert "pickWechatRagCorpus" in preload


def test_electron_desktop_starts_ocr_service_contract():
    main = (ROOT / "electron/main.cjs").read_text(encoding="utf-8")
    assert 'path.join(REPO_ROOT, "frontend_app", "current_console")' in main
    assert '"ocr_server.py"' in main
    assert "OCR_HEALTH_URL" in main
    assert "startOcrServerIfNeeded" in main
    assert "stopOcrServer" in main


def test_ocr_server_runtime_dependencies_are_declared():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = "\n".join(pyproject["project"]["dependencies"]).lower()
    assert "pymupdf" in dependencies
    assert "pillow" in dependencies


def test_github_pages_index_uses_same_graph_renderer_contract():
    root_index = (ROOT / "index.html").read_text(encoding="utf-8")
    console_index = (ROOT / "frontend_app/current_console/index.html").read_text(encoding="utf-8")
    required = [
        "buildKgCommunityGraph",
        "renderKgD3GraphView",
        "renderKgCommunityOverview",
        "renderKgCommunitySubgraph",
        "KG_COMMUNITY_SUBGRAPH_NODE_LIMIT",
        "Graph rendered as community overview",
    ]
    for text in required:
        assert text in root_index
        assert text in console_index
