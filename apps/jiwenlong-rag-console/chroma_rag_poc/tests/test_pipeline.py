"""
单元测试 — 基于项目2 + 增强

覆盖：解析、清洗、分块、入库、检索、API、基准测试
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import orjson
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from chroma_rag_poc.api import create_app
from chroma_rag_poc.benchmark import run_synthetic_benchmark
from chroma_rag_poc.chunking import chunk_records, split_text_with_overlap
from chroma_rag_poc.cleaning import clean_records
from chroma_rag_poc.parsing import load_json_payload
from chroma_rag_poc.pipeline import get_collection_stats, ingest_json_payloads, query_collection, quality_report


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

        # 检索
        search = client.post(
            "/api/search",
            json={"collection": "api-demo", "query": "状态监测", "top_k": 2},
        )
        self.assertEqual(search.status_code, 200)
        self.assertTrue(search.json()["results"])

    def test_benchmark(self) -> None:
        """性能基准测试"""
        result = run_synthetic_benchmark(
            persist_dir=self.persist_dir,
            collection_name="bench-demo",
            document_count=120,
            batch_size=30,
            query_count=20,
            cleanup=True,
        )
        self.assertGreater(result["insert_docs_per_second"], 0)
        self.assertGreater(result["query_qps"], 0)


if __name__ == "__main__":
    unittest.main()
