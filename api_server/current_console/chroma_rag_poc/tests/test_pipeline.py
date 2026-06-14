"""
单元测试 — 基于项目2 + 增强

覆盖：解析、清洗、分块、入库、检索、API、基准测试
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import orjson
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from chroma_rag_poc.api import create_app, _resolve_log_path
from chroma_rag_poc.benchmark import run_synthetic_benchmark
from chroma_rag_poc.chunking import chunk_records, split_text_with_overlap
from chroma_rag_poc.cleaning import clean_records
from chroma_rag_poc.embeddings import HashingEmbeddingFunction, create_embedding_backend
from chroma_rag_poc.observability import OperationLogger
from chroma_rag_poc.parsing import load_json_payload
from chroma_rag_poc.pipeline import get_all_stats, get_collection_stats, ingest_json_payloads, query_collection, quality_report


def build_label_studio_payload() -> bytes:
    payload = [
        {
            "id": 1,
            "annotations": [
                {
                    "id": 10,
                    "result": [
                        {
                            "id": "a1",
                            "type": "rectanglelabels",
                            "value": {"x": 10, "y": 10, "rectanglelabels": ["Title"]},
                        },
                        {
                            "id": "a1",
                            "type": "textarea",
                            "value": {"text": ["燃气轮机健康管理"]},
                        },
                        {
                            "id": "a2",
                            "type": "rectanglelabels",
                            "value": {"x": 10, "y": 20, "rectanglelabels": ["Para"]},
                        },
                        {
                            "id": "a2",
                            "type": "textarea",
                            "value": {"text": ["燃气轮机的状态监测应覆盖振动、温度、压力和润滑状态。"]},
                        },
                        {
                            "id": "a3",
                            "type": "rectanglelabels",
                            "value": {"x": 10, "y": 30, "rectanglelabels": ["Para"]},
                        },
                        {
                            "id": "a3",
                            "type": "textarea",
                            "value": {"text": ["压气机喘振通常与进气畸变、叶片污染和控制策略有关。"]},
                        },
                        {
                            "id": "a4",
                            "type": "rectanglelabels",
                            "value": {"x": 10, "y": 40, "rectanglelabels": ["List"]},
                        },
                        {
                            "id": "a4",
                            "type": "textarea",
                            "value": {"text": ["检查进气过滤系统"]},
                        },
                    ],
                }
            ],
            "data": {
                "filename": "demo.pdf",
                "page_num": 1,
                "total_pages": 1,
                "doc_id": 1,
            },
        }
    ]
    return orjson.dumps(payload)


def build_generic_payload() -> bytes:
    payload = [
        {
            "id": "g-1",
            "title": "维护建议",
            "content": "检索链路需要同时测试写入速度、查询速度和容量统计。",
        }
    ]
    return orjson.dumps(payload)


class PipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.persist_dir = Path(self.tempdir.name) / "chroma"
        self.upload_dir = Path(self.tempdir.name) / "uploads"
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        try:
            self.tempdir.cleanup()
        except PermissionError:
            pass

    def test_parse_label_studio(self) -> None:
        """Label Studio 格式解析 + List 标签支持"""
        records = load_json_payload(build_label_studio_payload(), "test.json")
        self.assertGreaterEqual(len(records), 1)
        # 验证 List 标签被正确解析
        blocks = records[0].blocks
        list_blocks = [b for b in blocks if b.block_type == "List"]
        self.assertGreaterEqual(len(list_blocks), 1, "应该识别 List 标签")

    def test_parse_generic_json(self) -> None:
        """通用 JSON 格式自动检测"""
        records = load_json_payload(build_generic_payload(), "generic.json")
        self.assertGreaterEqual(len(records), 1)

    def test_clean_records(self) -> None:
        """短文本合并测试"""
        from chroma_rag_poc.schemas import SourceRecord, TextBlock
        short_record = SourceRecord(
            source_file="test",
            record_id="test::1",
            filename="test.json",
            page_num=1,
            text="AB长文本测试内容CDEF",
            blocks=[
                TextBlock(text="AB", block_type="Para", order=0, y=0),
                TextBlock(text="长文本测试内容CDEF长文本测试内容CDEF", block_type="Para", order=1, y=10),
            ],
        )
        cleaned = clean_records([short_record], min_chars=10)
        # 短块 "AB" 应该被合并
        self.assertEqual(len(cleaned[0].blocks), 1)

    def test_split_text_with_overlap(self) -> None:
        """多级断点分块测试"""
        text = "第一段内容。第二段内容。第三段内容。第四段内容。"
        chunks = split_text_with_overlap(text, chunk_size=12, overlap=4)
        self.assertGreaterEqual(len(chunks), 2)
        self.assertTrue(all(chunks))

    def test_ingest_search_and_stats(self) -> None:
        """完整入库→检索→统计流程"""
        result = ingest_json_payloads(
            payloads=[
                ("labelstudio.json", build_label_studio_payload()),
                ("generic.json", build_generic_payload()),
            ],
            persist_dir=self.persist_dir,
            collection_name="test_collection",
            chunk_size=40,
            overlap=10,
            backend="hashing",
        )
        self.assertEqual(result["files_processed"], 2)
        self.assertGreaterEqual(result["records_processed"], 2)
        self.assertGreaterEqual(result["chunks_written"], 1)

        # 统计
        stats = get_collection_stats(
            persist_dir=self.persist_dir,
            collection_name="test_collection",
        )
        self.assertGreater(stats["chunk_count"], 0)

        # 检索
        search = query_collection(
            query_text="压气机喘振原因",
            persist_dir=self.persist_dir,
            collection_name="test_collection",
            top_k=3,
        )
        self.assertTrue(search["results"])

    def test_quality_report(self) -> None:
        """数据质量报告"""
        records = load_json_payload(build_label_studio_payload(), "test.json")
        from chroma_rag_poc.chunking import chunk_records
        chunks = chunk_records(records, chunk_size=100, overlap=10)
        report = quality_report(records, chunks)
        self.assertIn("documents", report)
        self.assertIn("chunks", report)

    def test_api_ingest_and_search(self) -> None:
        """API 集成测试"""
        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)

        # 健康检查
        response = client.get("/api/health")
        self.assertEqual(response.status_code, 200)

        # 入库
        response = client.post(
            "/api/ingest",
            data={
                "collection": "api-demo",
                "chunk_size": "50",
                "overlap": "10",
                "backend": "hashing",
                "model_name": "BAAI/bge-small-zh-v1.5",
            },
            files=[
                ("files", ("demo.json", build_label_studio_payload(), "application/json")),
            ],
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertGreaterEqual(payload["chunks_written"], 1)
        self.assertTrue(payload.get("log_file"))
        self.assertNotIn("log_path", payload)

        logs = client.get("/api/logs")
        self.assertEqual(logs.status_code, 200)
        self.assertIn(payload["log_file"], [item["filename"] for item in logs.json()["logs"]])

        log_text = client.get(f"/api/logs/{payload['log_file']}")
        self.assertEqual(log_text.status_code, 200)
        self.assertIn("ingest_start", log_text.text)

        # 检索
        search = client.post(
            "/api/search",
            json={"collection": "api-demo", "query": "状态监测", "top_k": 2},
        )
        self.assertEqual(search.status_code, 200)
        search_payload = search.json()
        self.assertTrue(search_payload["results"])
        self.assertTrue(search_payload.get("log_file"))
        self.assertNotIn("log_path", search_payload)

    def test_api_upload_process_writes_log(self) -> None:
        """分步上传和处理时写入可追踪的 .log 文件"""
        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)

        upload = client.post(
            "/api/upload",
            files={"file": ("ops.txt", "设备维护需要记录温度、压力和振动趋势。".encode("utf-8"), "text/plain")},
        )
        self.assertEqual(upload.status_code, 200)
        uploaded = upload.json()
        self.assertTrue(uploaded.get("log_file"))
        self.assertNotIn("log_path", uploaded)

        process = client.post(
            "/api/process",
            json={"filenames": [uploaded["filename"]], "collection": "process-demo"},
        )
        self.assertEqual(process.status_code, 200)
        result = process.json()
        self.assertTrue(result.get("log_file"))
        self.assertNotIn("log_path", result)
        self.assertGreaterEqual(result["chunks_written"], 1)

        log_text = client.get(f"/api/logs/{result['log_file']}")
        self.assertEqual(log_text.status_code, 200)
        self.assertIn("process_selection", log_text.text)
        self.assertIn("ingest_result", log_text.text)

        uploads = client.get("/api/uploads")
        self.assertEqual(uploads.status_code, 200)
        processed = uploads.json()["processed"]
        self.assertEqual(processed[0]["last_log_file"], result["log_file"])

    def test_api_module_does_not_create_app_at_import_time(self) -> None:
        """api.py 只暴露工厂，避免导入时创建默认应用实例。"""
        import chroma_rag_poc.api as api_module

        self.assertNotIn("app", vars(api_module))

    def test_index_returns_404_when_frontend_dir_is_missing(self) -> None:
        """前端目录不存在时根路由应优雅降级，而不是依赖导入期 next()。"""
        app = create_app(
            persist_dir=self.persist_dir,
            upload_dir=self.upload_dir,
            frontend_dir=Path(self.tempdir.name) / "missing-frontend",
        )
        client = TestClient(app)

        response = client.get("/")

        self.assertEqual(response.status_code, 404)

    def test_frontend_libs_and_assets_are_served_from_root_paths(self) -> None:
        """index.html 以 /libs 与 /assets 相对根路径加载本地前端依赖。"""
        frontend_dir = Path(self.tempdir.name) / "frontend"
        (frontend_dir / "libs").mkdir(parents=True)
        (frontend_dir / "assets").mkdir(parents=True)
        (frontend_dir / "index.html").write_text("<!doctype html><title>demo</title>", encoding="utf-8")
        (frontend_dir / "libs" / "demo.js").write_text("window.demoLib = true;", encoding="utf-8")
        (frontend_dir / "assets" / "hero.webp").write_bytes(b"WEBP")

        app = create_app(
            persist_dir=self.persist_dir,
            upload_dir=self.upload_dir,
            frontend_dir=frontend_dir,
        )
        client = TestClient(app)

        lib_response = client.get("/libs/demo.js")
        asset_response = client.get("/assets/hero.webp")

        self.assertEqual(lib_response.status_code, 200)
        self.assertEqual(asset_response.status_code, 200)

    def test_deliverable_assets_are_served_from_stable_root_path(self) -> None:
        """前端演示页引用的静态资产应可通过稳定 URL 访问，避免浏览器 404。"""
        deliverables_dir = Path(self.tempdir.name) / "docs" / "project_deliverables"
        kg_dir = deliverables_dir / "06_四本书KG工具跑通演示"
        kg_dir.mkdir(parents=True)
        (kg_dir / "knowledge_graph.svg").write_text("<svg></svg>", encoding="utf-8")

        app = create_app(
            persist_dir=self.persist_dir,
            upload_dir=self.upload_dir,
            deliverables_dir=deliverables_dir,
        )
        client = TestClient(app)

        response = client.get("/deliverables/06_%E5%9B%9B%E6%9C%AC%E4%B9%A6KG%E5%B7%A5%E5%85%B7%E8%B7%91%E9%80%9A%E6%BC%94%E7%A4%BA/knowledge_graph.svg")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.text, "<svg></svg>")

    def test_frontend_exposes_kg_graph_export_action_in_graph_toolbar(self) -> None:
        frontend_path = PROJECT_ROOT.parents[2] / "frontend_app" / "current_console" / "index.html"
        html = frontend_path.read_text(encoding="utf-8")
        toolbar_start = html.index('id="kgGraphStats"')
        toolbar_end = html.index('id="kgGraphContainer"', toolbar_start)
        toolbar_html = html[toolbar_start:toolbar_end]

        self.assertIn('id="btnKgExportGraph"', toolbar_html)
        self.assertIn("lucide:download", toolbar_html)
        self.assertIn('$("btnKgExportGraph")?.addEventListener("click", exportKgGraphSnapshot);', html)
        self.assertNotIn("btnKgPublicBooksExportChroma", html)

    def test_graphrag_export_route_returns_downloadable_json(self) -> None:
        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)
        graph_db_path = self.persist_dir / "graph_store.sqlite"
        graph_db_path.write_bytes(b"")

        response = client.get("/api/graphrag/export", params={"graph_db_path": str(graph_db_path)})

        self.assertEqual(response.status_code, 200)
        self.assertIn("application/json", response.headers.get("content-type", ""))
        self.assertIn("attachment", response.headers.get("content-disposition", ""))
        payload = response.json()
        self.assertEqual(payload["format"], "graphrag_graph_export")
        self.assertIn("nodes", payload)
        self.assertIn("edges", payload)

    def test_default_cors_rejects_untrusted_origin(self) -> None:
        """默认 CORS 只允许本地控制台来源，不能对任意站点开放。"""
        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)

        rejected = client.options(
            "/api/health",
            headers={
                "Origin": "https://evil.example",
                "Access-Control-Request-Method": "GET",
            },
        )
        allowed = client.options(
            "/api/health",
            headers={
                "Origin": "http://localhost:8000",
                "Access-Control-Request-Method": "GET",
            },
        )

        self.assertIsNone(rejected.headers.get("access-control-allow-origin"))
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(allowed.headers.get("access-control-allow-origin"), "http://localhost:8000")

    def test_api_upload_rejects_unsupported_relative_path_extension(self) -> None:
        """relative_path 不能把已校验的上传伪装成不可处理的最终文件名"""
        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)

        response = client.post(
            "/api/upload",
            data={"relative_path": "nested/unsafe.exe"},
            files={"file": ("safe.txt", b"processable text", "text/plain")},
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse((self.upload_dir / "nested__unsafe.exe").exists())

    def test_api_search_get_rejects_out_of_range_top_k(self) -> None:
        """GET 搜索需要与 POST 搜索保持相同 top_k 边界，避免昂贵或无效查询。"""
        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)

        response = client.get("/api/search", params={"q": "状态监测", "top_k": 999})

        self.assertEqual(response.status_code, 400)
        self.assertIn("top_k", response.json()["detail"])

    def test_graphrag_routes_reject_graph_db_outside_runtime_roots(self) -> None:
        """GraphRAG 路由不能通过请求体任意打开运行目录外的本地 SQLite 文件。"""
        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)
        outside_graph = Path(self.tempdir.name).parent / "outside_graph.sqlite"
        outside_graph.write_bytes(b"")

        def cleanup_outside_graph() -> None:
            try:
                outside_graph.unlink(missing_ok=True)
            except PermissionError:
                pass

        self.addCleanup(cleanup_outside_graph)

        response = client.post("/api/graphrag/stats", json={"graph_db_path": str(outside_graph)})

        self.assertEqual(response.status_code, 400)
        self.assertIn("Graph database path", response.json()["detail"])

    def test_public_books_json_ingest_rejects_input_dir_outside_allowed_roots(self) -> None:
        """本地 JSON 入库接口不能通过请求体扫描白名单外的任意目录。"""
        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)
        outside_dir = Path(self.tempdir.name).parent / "outside-public-books-json"
        outside_dir.mkdir(exist_ok=True)

        def cleanup_outside_dir() -> None:
            try:
                outside_dir.rmdir()
            except OSError:
                pass

        self.addCleanup(cleanup_outside_dir)

        response = client.post(
            "/api/public-books-json/ingest",
            json={"input_dir": str(outside_dir)},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("not allowed", response.json()["detail"])

    def test_observability_hardening_edges(self) -> None:
        """日志和文件名边界不能悄悄越界或写出重复结束事件"""
        hasher = HashingEmbeddingFunction(dimension=16)
        single_query_vector = hasher.embed_query("abc")
        self.assertEqual(len(single_query_vector), 16)
        batch_query_vectors = hasher.embed_query(["abc", "def"])
        self.assertEqual(len(batch_query_vectors), 2)
        self.assertEqual(len(batch_query_vectors[0]), 16)

        log_dir = Path(self.tempdir.name) / "logs"
        logger = OperationLogger(log_dir, "unit")
        logger.close(status="ok")
        logger.close(status="error")
        log_text = logger.file_path.read_text(encoding="utf-8")
        end_lines = [line for line in log_text.splitlines() if " operation_end " in line]
        self.assertEqual(len(end_lines), 1)
        self.assertIn("operation_close_ignored", log_text)

        with self.assertRaises(Exception) as invalid_log:
            _resolve_log_path(log_dir, "../secret.log")
        self.assertEqual(getattr(invalid_log.exception, "status_code", None), 400)

        with self.assertRaises(ValueError):
            create_embedding_backend(backend="typo-backend")

        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)
        outside = Path(self.tempdir.name) / "outside.txt"
        outside.write_text("keep", encoding="utf-8")
        response = client.post("/api/uploads/delete", json={"filenames": ["../outside.txt"]})
        self.assertEqual(response.status_code, 400)
        self.assertTrue(outside.exists())

        cross_origin_logs = client.get("/api/logs", headers={"origin": "http://evil.example"})
        self.assertEqual(cross_origin_logs.status_code, 403)

        stats_response = client.get("/api/stats")
        self.assertEqual(stats_response.status_code, 200)
        stats_payload = stats_response.json()
        self.assertTrue(stats_payload.get("log_file"))
        self.assertNotIn("log_path", stats_payload)

        empty_search = client.get("/api/search?q=")
        self.assertEqual(empty_search.status_code, 400)
        self.assertIn(".log", empty_search.json()["detail"])

        bad_persist = Path(self.tempdir.name) / "not-a-dir"
        bad_persist.write_text("not a directory", encoding="utf-8")
        broken_app = create_app(
            persist_dir=self.persist_dir,
            upload_dir=Path(self.tempdir.name) / "broken-uploads",
        )
        broken_app.state.persist_dir = bad_persist
        broken_client = TestClient(broken_app)
        broken_stats = broken_client.get("/api/stats?collection=broken")
        self.assertEqual(broken_stats.status_code, 500)
        self.assertIn(".log", broken_stats.json()["detail"])

    def test_stats_handles_chroma_tenant_validation_error(self) -> None:
        broken_chroma = Path(self.tempdir.name) / "broken-chroma"
        broken_chroma.mkdir()
        error = ValueError("Could not connect to tenant default_tenant. Are you sure it exists?")

        with patch("chroma_rag_poc.pipeline._create_client", side_effect=error):
            stats = get_all_stats(broken_chroma)

        self.assertEqual(stats["status"], "error")
        self.assertEqual(stats["collections"], [])
        self.assertIn("default_tenant", stats["error"])

        app = create_app(persist_dir=broken_chroma, upload_dir=self.upload_dir)
        client = TestClient(app)
        with patch("chroma_rag_poc.pipeline._create_client", side_effect=error):
            response = client.get("/api/stats")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "error")
        self.assertIn("default_tenant", payload["error"])

    def test_stats_recovers_unusable_chroma_store(self) -> None:
        broken_chroma = Path(self.tempdir.name) / "recoverable-chroma"
        broken_chroma.mkdir()
        (broken_chroma / "chroma.sqlite3").write_text("not a sqlite database", encoding="utf-8")
        error = ValueError("Could not connect to tenant default_tenant. Are you sure it exists?")
        calls = []

        class FakeSystem:
            def stop(self) -> None:
                pass

        class FakeClient:
            _system = FakeSystem()

            def list_collections(self) -> list:
                return []

            def clear_system_cache(self) -> None:
                pass

        def fake_open(path: Path):
            calls.append(path)
            if len(calls) == 1:
                raise error
            return FakeClient()

        with patch("chroma_rag_poc.pipeline._open_chroma_client", side_effect=fake_open):
            stats = get_all_stats(broken_chroma)

        self.assertEqual(stats["status"], "ok")
        self.assertEqual(calls, [broken_chroma, broken_chroma])
        self.assertTrue(broken_chroma.exists())
        backups = sorted(broken_chroma.parent.glob("recoverable-chroma_broken_*"))
        self.assertEqual(len(backups), 1)
        self.assertTrue((backups[0] / "chroma.sqlite3").exists())
        self.assertTrue((backups[0] / "RECOVERY_NOTICE.json").exists())

    def test_sentence_transformer_default_prefers_local_model_dir(self) -> None:
        from chroma_rag_poc.embeddings import resolve_sentence_transformer_model_path

        local_root = Path(self.tempdir.name) / "models"
        model_dir = local_root / "BAAI" / "bge-m3"
        model_dir.mkdir(parents=True)

        resolved = resolve_sentence_transformer_model_path("BAAI/bge-m3", local_roots=[local_root])

        self.assertEqual(Path(resolved), model_dir)

    def test_sentence_transformer_missing_local_model_does_not_download_by_default(self) -> None:
        from chroma_rag_poc import embeddings

        embeddings._resolve_embedding_backend.cache_clear()
        with patch("chroma_rag_poc.embeddings._online_model_loading_allowed", return_value=False):
            resolved = create_embedding_backend(
                backend="sentence-transformer",
                model_name="BAAI/bge-m3",
                dimension=32,
            )
        embeddings._resolve_embedding_backend.cache_clear()

        self.assertEqual(resolved.name, "hashing")
        self.assertEqual(resolved.dimension, 32)
        self.assertIn("Local sentence-transformer model not found", resolved.warning or "")

    def test_memory_routes_persist_turns_across_app_instances(self) -> None:
        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)

        session_response = client.post(
            "/api/memory/sessions",
            json={"session_id": "meeting-session", "title": "组会问答"},
        )
        self.assertEqual(session_response.status_code, 200)

        turn_response = client.post(
            "/api/memory/sessions/meeting-session/turns",
            json={
                "user": "本地模型应该从哪里读取？",
                "assistant": "应该优先读取本地模型目录，避免默认联网下载。",
            },
        )
        self.assertEqual(turn_response.status_code, 200)
        self.assertEqual(turn_response.json()["context"]["message_count"], 2)

        restored_app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        restored_client = TestClient(restored_app)
        context_response = restored_client.get(
            "/api/memory/sessions/meeting-session/context",
            params={"query": "本地模型", "recent_limit": 4},
        )

        self.assertEqual(context_response.status_code, 200)
        context = context_response.json()
        self.assertEqual(context["message_count"], 2)
        self.assertEqual([item["role"] for item in context["recent_messages"]], ["user", "assistant"])
        self.assertTrue((self.persist_dir / "memory" / "conversation_memory.sqlite3").exists())

    def test_frontend_has_persistent_local_workspace_snapshot_contract(self) -> None:
        repo_root = PROJECT_ROOT.parents[2]
        frontend_path = repo_root / "frontend_app" / "current_console" / "index.html"
        html = frontend_path.read_text(encoding="utf-8")

        self.assertIn("LOCAL_WORKSPACE_DB_NAME", html)
        self.assertIn("indexedDB.open", html)
        self.assertIn("serializeKgGraphSnapshot", html)
        self.assertIn("saveLocalWorkspaceSnapshot", html)
        self.assertIn("restoreLocalWorkspaceSnapshot", html)
        self.assertIn("await restoreLocalWorkspaceSnapshot()", html)
        self.assertIn('void saveLocalWorkspaceSnapshot("process")', html)
        self.assertIn('void saveLocalWorkspaceSnapshot("kg-build")', html)

    def test_graphrag_community_detection_route_uses_available_detector(self) -> None:
        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)
        graph_db_path = Path(self.tempdir.name) / "graph.sqlite"
        graph_db_path.write_bytes(b"")

        class FakeDetectionResult:
            def to_dict(self) -> dict:
                return {
                    "total_nodes": 3,
                    "total_edges": 2,
                    "num_communities": 1,
                    "level": 0,
                    "community_sizes": {"C0": 3},
                }

        with patch("kg_pipeline.community_detection.run_leiden_detection", return_value=FakeDetectionResult()) as detector:
            response = client.post(
                "/api/graphrag/community/detect",
                json={"graph_db_path": str(graph_db_path), "resolution": 1.0, "level": 0},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["num_communities"], 1)
        detector.assert_called_once()

    def test_benchmark(self) -> None:
        """性能基准测试"""
        log_dir = Path(self.tempdir.name) / "logs"
        logger = OperationLogger(log_dir, "benchmark-test")
        result = run_synthetic_benchmark(
            persist_dir=self.persist_dir,
            collection_name="bench-demo",
            document_count=120,
            batch_size=30,
            query_count=20,
            cleanup=True,
            operation_logger=logger,
        )
        logger.close(status="ok")
        self.assertGreater(result["insert_docs_per_second"], 0)
        self.assertGreater(result["query_qps"], 0)
        log_text = logger.file_path.read_text(encoding="utf-8")
        self.assertIn("benchmark_start", log_text)
        self.assertIn("benchmark_insert", log_text)
        self.assertIn("benchmark_query", log_text)

    def test_api_benchmark_writes_log(self) -> None:
        """/api/benchmark 返回日志文件名，且日志接口可读取完整压测事件"""
        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)

        response = client.post(
            "/api/benchmark",
            json={
                "collection": "bench-api-demo",
                "document_count": 50,
                "batch_size": 25,
                "query_count": 10,
                "top_k": 3,
                "backend": "hashing",
                "cleanup": True,
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get("log_file"))
        self.assertNotIn("log_path", payload)
        self.assertGreater(payload["insert_docs_per_second"], 0)
        self.assertGreater(payload["query_qps"], 0)

        log_text = client.get(f"/api/logs/{payload['log_file']}")
        self.assertEqual(log_text.status_code, 200)
        self.assertIn("benchmark_start", log_text.text)
        self.assertIn("benchmark_result", log_text.text)


if __name__ == "__main__":
    unittest.main()
