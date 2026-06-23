"""
单元测试 — 基于项目2 + 增强

覆盖：解析、清洗、分块、入库、检索、API、基准测试
"""
from __future__ import annotations

import sys
import tempfile
import threading
import unittest
import sqlite3
import hashlib
import hmac
import socketserver
from email import message_from_bytes
from http.server import BaseHTTPRequestHandler, HTTPServer
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
from chroma_rag_poc.pipeline import _close_client, _create_client, get_all_stats, get_collection_stats, ingest_json_payloads, query_collection, quality_report


class FakeUnifiedQueryLLM:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def generate(self, prompt: str, **_: object) -> str:
        self.prompts.append(prompt)
        if "smart query router" in prompt:
            return '{"strategy":"GLOBAL_SEARCH","reason":"question asks for corpus-level synthesis"}'
        if "Community Summary" in prompt:
            return "社区摘要指出燃气轮机维护主题与状态监测相关。"
        return "统一问答已结合文本证据和全局社区上下文回答 [T1]。"

    def complete(self, prompt: str, **kwargs: object) -> str:
        return self.generate(prompt, **kwargs)


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

    def test_wechat_json_contact_metadata_survives_chunking(self) -> None:
        payload = [
            {
                "id": "chunk-1",
                "contact_id": "contact-abc",
                "conversation_id": "wechat-private-0001-abc",
                "partition_id": "contact:wxid_abc",
                "conversation_type": "private",
                "conversation_index": 1,
                "contact_name": "小琳",
                "username": "wxid_abc",
                "message_count": 2,
                "first_date": "2026-01-01",
                "last_date": "2026-01-01",
                "text": "微信聊天记录 — 小琳\n[12:00:00] 小琳: 你好\n[12:01:00] 我: 你好",
            }
        ]

        records = load_json_payload(orjson.dumps(payload), "wechat_private_chunks_rag.json")
        chunks = chunk_records(records, chunk_size=500, overlap=50)

        self.assertEqual(records[0].metadata["contact_name"], "小琳")
        self.assertEqual(records[0].metadata["username"], "wxid_abc")
        self.assertEqual(chunks[0].metadata["contact_id"], "contact-abc")
        self.assertEqual(chunks[0].metadata["conversation_id"], "wechat-private-0001-abc")
        self.assertEqual(chunks[0].metadata["conversation_index"], 1)
        self.assertEqual(chunks[0].metadata["contact_name"], "小琳")
        self.assertEqual(chunks[0].metadata["username"], "wxid_abc")

    def test_unified_query_full_private_contact_analysis_scans_all_contacts_without_llm(self) -> None:
        payload = [
            {
                "id": "chunk-1",
                "contact_id": "contact-a",
                "conversation_id": "wechat-private-0001-a",
                "partition_id": "contact:wxid_a",
                "conversation_type": "private",
                "contact_name": "王佳乐",
                "username": "wxid_a",
                "message_count": 2,
                "first_date": "2026-01-01",
                "last_date": "2026-01-01",
                "text": "微信聊天记录 - 王佳乐\n2026-01-01 [12:00:00] 王佳乐: 我想你了 想要你陪陪我",
            },
            {
                "id": "chunk-2",
                "contact_id": "contact-b",
                "conversation_id": "wechat-private-0002-b",
                "partition_id": "contact:wxid_b",
                "conversation_type": "private",
                "contact_name": "徐明阳",
                "username": "wxid_b",
                "message_count": 1,
                "first_date": "2026-01-02",
                "last_date": "2026-01-02",
                "text": "微信聊天记录 - 徐明阳\n2026-01-02 [13:00:00] 徐明阳: 我们讨论一下哲学问题。",
            },
            {
                "id": "chunk-3",
                "contact_id": "filehelper",
                "conversation_id": "wechat-private-filehelper",
                "partition_id": "contact:filehelper",
                "conversation_type": "filehelper",
                "contact_name": "文件传输助手",
                "username": "filehelper",
                "message_count": 1,
                "first_date": "2026-01-03",
                "last_date": "2026-01-03",
                "text": "微信聊天记录 - 文件传输助手\n2026-01-03 [14:00:00] 我: 宝宝 草稿",
            },
        ]
        ingest_json_payloads(
            payloads=[("wechat_private_chunks_rag.json", orjson.dumps(payload))],
            persist_dir=self.persist_dir,
            collection_name="wechat_private_test",
            chunk_size=1000,
            overlap=0,
            backend="hashing",
        )

        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)
        response = client.post(
            "/api/query",
            json={
                "question": "请执行全量私聊联系人级暧昧关系分析，不要只基于 top-k chunk。",
                "collection": "wechat_private_test",
                "top_k": 1,
                "mode": "auto",
            },
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result["route"]["task_route"], "COMPREHENSIVE_ANALYSIS")
        self.assertEqual(result["advanced_mode"], "COMPREHENSIVE_ANALYSIS")
        self.assertEqual(result["coverage_report"]["top_k_used"], False)
        self.assertEqual(result["coverage_report"]["private_contact_count"], 2)
        self.assertEqual(result["coverage_report"]["contacts_analyzed"], 2)
        self.assertEqual(result["coverage_report"]["candidate_contact_count"], 1)
        self.assertEqual(result["coverage_report"]["excluded_reasons"]["system_or_file_helper"], 1)
        contacts = result["contact_analysis"]["contacts"]
        self.assertEqual(contacts[0]["contact_name"], "王佳乐")
        self.assertEqual(contacts[0]["username"], "wxid_a")
        self.assertEqual(contacts[0]["evidence_count"], 1)
        self.assertIn("我想你了", contacts[0]["evidence"][0]["text"])
        self.assertTrue(result["citations"])
        self.assertEqual(result["citations"][0]["source_type"], "text_full_contact_scan")

    def test_unified_query_generic_comprehensive_analysis_scans_partitions_without_llm(self) -> None:
        payload = [
            {
                "id": "doc-a",
                "document_id": "manual-a.md",
                "section": "bearing case",
                "text": "2026-01-01 Pump A reported bearing overheating and high vibration. Corrective action: replace bearing.",
            },
            {
                "id": "doc-b",
                "document_id": "manual-b.md",
                "section": "normal inspection",
                "text": "2026-01-02 Pump B inspection was normal.",
            },
        ]
        ingest_json_payloads(
            payloads=[("generic_docs.json", orjson.dumps(payload))],
            persist_dir=self.persist_dir,
            collection_name="generic_profile_test",
            chunk_size=1000,
            overlap=0,
            backend="hashing",
        )

        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)
        response = client.post(
            "/api/query",
            json={
                "question": "Run a full corpus evidence analysis across all documents for bearing overheating. Do not only use top-k chunks.",
                "collection": "generic_profile_test",
                "top_k": 1,
                "mode": "auto",
            },
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result["route"]["task_route"], "COMPREHENSIVE_ANALYSIS")
        self.assertEqual(result["advanced_mode"], "COMPREHENSIVE_ANALYSIS")
        self.assertEqual(result["coverage_report"]["analysis_type"], "generic_partition_evidence_sweep")
        self.assertEqual(result["coverage_report"]["top_k_used"], False)
        self.assertEqual(result["coverage_report"]["partitions_analyzed"], 2)
        self.assertEqual(result["coverage_report"]["candidate_partition_count"], 1)
        self.assertEqual(result["analysis_profile"]["partition_key"], "document_id")
        self.assertIn("Result:", result["answer"])
        self.assertNotIn("Generic full-partition evidence analysis executed", result["answer"])
        candidates = result["partition_analysis"]["candidates"]
        self.assertEqual(candidates[0]["partition_id"], "manual-a.md")
        self.assertIn("bearing overheating", candidates[0]["evidence"][0]["text"])
        self.assertEqual(result["citations"][0]["source_type"], "text_full_partition_scan")

    def test_unified_query_without_llm_returns_text_retrieval_result(self) -> None:
        payload = [
            {
                "id": "doc-a",
                "document_id": "manual-a.md",
                "section": "bearing case",
                "text": "Pump A failure was caused by bearing overheating and high vibration.",
            }
        ]
        ingest_json_payloads(
            payloads=[("generic_docs.json", orjson.dumps(payload))],
            persist_dir=self.persist_dir,
            collection_name="no_llm_text_fallback_test",
            chunk_size=1000,
            overlap=0,
            backend="hashing",
        )

        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)
        response = client.post(
            "/api/query",
            json={
                "question": "What caused Pump A failure?",
                "collection": "no_llm_text_fallback_test",
                "top_k": 3,
                "mode": "auto",
            },
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertIn("Result:", result["answer"])
        self.assertIn("text retrieval", result["answer"])
        self.assertTrue(result["citations"])
        self.assertIn("bearing overheating", result["citations"][0]["text"])

    def test_unified_query_self_identity_uses_deterministic_scan(self) -> None:
        payload = [
            {
                "id": "chunk-1",
                "contact_id": "contact-xiaolin",
                "conversation_id": "wechat-private-0001-xiaolin",
                "partition_id": "contact:wxid_xiaolin",
                "conversation_type": "private",
                "contact_name": "\u5c0f\u7433",
                "username": "wxid_xiaolin",
                "message_count": 2,
                "first_date": "2026-01-01",
                "last_date": "2026-01-01",
                "text": "\u5fae\u4fe1\u804a\u5929\u8bb0\u5f55 - JavonLoong\u4e0e\u5c0f\u7433\u7684\u804a\u5929\u8bb0\u5f55\n2026-01-01 [12:00:00] JavonLoong: \u4f60\u597d\n2026-01-01 [12:01:00] \u5c0f\u7433: \u4f60\u597d",
            },
            {
                "id": "chunk-2",
                "contact_id": "contact-xumingyang",
                "conversation_id": "wechat-private-0002-xumingyang",
                "partition_id": "contact:wxid_xumingyang",
                "conversation_type": "private",
                "contact_name": "\u5f90\u660e\u9633",
                "username": "wxid_xumingyang",
                "message_count": 1,
                "first_date": "2026-01-02",
                "last_date": "2026-01-02",
                "text": "\u5fae\u4fe1\u804a\u5929\u8bb0\u5f55 - JavonLoong\u4e0e\u5f90\u660e\u9633\u7684\u804a\u5929\u8bb0\u5f55\n2026-01-02 [13:00:00] JavonLoong: \u8ba8\u8bba\u4e00\u4e0b\u4f5c\u4e1a",
            },
            {
                "id": "chunk-3",
                "contact_id": "contact-forward",
                "conversation_id": "wechat-private-0003-forward",
                "partition_id": "contact:wxid_forward",
                "conversation_type": "private",
                "contact_name": "\u4e50\u66c8\u5b66\u59d0",
                "username": "wxid_forward",
                "message_count": 1,
                "text": "\u4e50\u66c8\u5b66\u59d0: [\u5408\u5e76\u8f6c\u53d1] JavonLoong\u4e0e\u4e8c\u80d6\u7684\u804a\u5929\u8bb0\u5f55",
            },
        ]
        ingest_json_payloads(
            payloads=[("wechat_private_chunks_rag.json", orjson.dumps(payload))],
            persist_dir=self.persist_dir,
            collection_name="wechat_identity_test",
            chunk_size=1000,
            overlap=0,
            backend="hashing",
        )

        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)

        class NoCallLLM:
            def __init__(self, **_: object) -> None:
                pass

            def generate(self, prompt: str, **_: object) -> str:
                raise AssertionError("identity questions must bypass LLM routing and generation")

        with patch("chroma_rag_poc.api.OpenAICompatibleLLMClient", NoCallLLM):
            response = client.post(
                "/api/query",
                json={
                    "question": "\u6211\u662f\u8c01\uff1f",
                    "collection": "wechat_identity_test",
                    "top_k": 100,
                    "mode": "auto",
                    "llm_api_key": "test-key",
                },
            )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result["route"]["task_route"], "COMPREHENSIVE_ANALYSIS")
        self.assertEqual(result["advanced_mode"], "COMPREHENSIVE_ANALYSIS")
        self.assertEqual(result["coverage_report"]["analysis_type"], "self_identity_scan")
        self.assertFalse(result["coverage_report"]["top_k_used"])
        self.assertEqual(result["identity_analysis"]["top_candidate"]["name"], "JavonLoong")
        self.assertNotIn("\u5408\u5e76\u8f6c\u53d1", result["identity_analysis"]["top_candidate"]["name"])
        self.assertIn("JavonLoong", result["answer"])
        self.assertTrue(result["citations"])
        self.assertEqual(result["citations"][0]["source_type"], "text_identity_scan")

    def test_unified_query_identity_falls_back_from_empty_selected_collection_to_chat_collection(self) -> None:
        ingest_json_payloads(
            payloads=[("empty.json", orjson.dumps([{"id": "empty", "text": ""}]))],
            persist_dir=self.persist_dir,
            collection_name="power_rag_corpus",
            chunk_size=1000,
            overlap=0,
            backend="hashing",
        )
        # Remove the placeholder so the selected collection exists but has zero usable chunks.
        client_for_empty = _create_client(self.persist_dir)
        try:
            client_for_empty.delete_collection("power_rag_corpus")
            client_for_empty.create_collection("power_rag_corpus", embedding_function=HashingEmbeddingFunction())
        finally:
            _close_client(client_for_empty)

        payload = [
            {
                "id": "chunk-1",
                "contact_id": "contact-forward",
                "conversation_id": "wechat-private-0001-forward",
                "partition_id": "contact:wxid_forward",
                "conversation_type": "private",
                "contact_name": "\u4e50\u66c8\u5b66\u59d0",
                "username": "wxid_forward",
                "message_count": 1,
                "text": "\u4e50\u66c8\u5b66\u59d0: [\u5408\u5e76\u8f6c\u53d1] JavonLoong\u4e0e\u4e8c\u80d6\u7684\u804a\u5929\u8bb0\u5f55",
            },
        ]
        ingest_json_payloads(
            payloads=[("wechat_private_chunks_rag.json", orjson.dumps(payload))],
            persist_dir=self.persist_dir,
            collection_name="wechat_private_chunks_rag",
            chunk_size=1000,
            overlap=0,
            backend="hashing",
        )

        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)
        response = client.post(
            "/api/query",
            json={
                "question": "\u6839\u636e\u6211\u4eec\u7684\u804a\u5929\u8bb0\u5f55\u5224\u65ad\u4e00\u4e0b\u6211\u662f\u8c01\uff0c\u5224\u65ad\u4e00\u4e0b\u6211\u7684\u8eab\u4efd\u3002",
                "collection": "power_rag_corpus",
                "top_k": 100,
                "mode": "global",
            },
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result["resolved_collection"], "wechat_private_chunks_rag")
        self.assertEqual(result["requested_collection"], "power_rag_corpus")
        self.assertEqual(result["collection_resolution"]["reason"], "requested_collection_empty")
        self.assertGreater(result["coverage_report"]["scanned_chunks"], 0)
        self.assertEqual(result["identity_analysis"]["top_candidate"]["name"], "JavonLoong")

    def test_unified_query_self_identity_does_not_treat_attachment_fields_as_sender(self) -> None:
        payload = [
            {
                "id": "chunk-1",
                "contact_id": "contact-printer",
                "conversation_id": "wechat-private-0001-printer",
                "partition_id": "contact:wxid_printer",
                "conversation_type": "private",
                "contact_name": "AAA\u6253\u5370\u5ba4",
                "username": "wxid_printer",
                "message_count": 2,
                "text": "\u5fae\u4fe1\u804a\u5929\u8bb0\u5f55 - AAA\u6253\u5370\u5ba4\nattachments / path: 0026_AAA/AAA\u6253\u5370\u5ba4/\u6587\u4ef6/demo.pdf\nattachments / size_bytes: 1024\n[12:00:00] \u6211: \u4f60\u597d\n[12:01:00] AAA\u6253\u5370\u5ba4: \u6536\u5230\n[15:48:12] \u5317\u4ea4\u5927\u4e8c \u5546\u52a1\u7ba1\u7406,\u56fd\u9645\u672c\u79d1: \u6211\u662f\u94ae\u795c\u7984\u306e\u82f1\u7f8e",
            }
        ]
        ingest_json_payloads(
            payloads=[("wechat_private_chunks_rag.json", orjson.dumps(payload))],
            persist_dir=self.persist_dir,
            collection_name="wechat_identity_attachment_noise_test",
            chunk_size=1000,
            overlap=0,
            backend="hashing",
        )

        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)
        response = client.post(
            "/api/query",
            json={
                "question": "\u6211\u662f\u8c01\uff1f",
                "collection": "wechat_identity_attachment_noise_test",
                "top_k": 100,
                "mode": "auto",
            },
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result["coverage_report"]["analysis_type"], "self_identity_scan")
        self.assertIsNone(result["identity_analysis"]["top_candidate"])
        self.assertGreaterEqual(result["coverage_report"]["weak_candidate_count"], 1)
        self.assertFalse(result["citations"])
        self.assertIn("\u65e0\u6cd5", result["answer"])

    def test_unified_query_returns_resilient_fallback_when_primary_path_fails(self) -> None:
        payload = [
            {
                "id": "doc-a",
                "document_id": "manual-a.md",
                "section": "bearing case",
                "text": "Pump A failure was caused by bearing overheating and high vibration.",
            }
        ]
        ingest_json_payloads(
            payloads=[("generic_docs.json", orjson.dumps(payload))],
            persist_dir=self.persist_dir,
            collection_name="resilient_fallback_test",
            chunk_size=1000,
            overlap=0,
            backend="hashing",
        )

        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)
        with patch("chroma_rag_poc.api.GraphRagQAOrchestrator.answer", side_effect=RuntimeError("boom")):
            response = client.post(
                "/api/query",
                json={
                    "question": "What caused Pump A failure?",
                    "collection": "resilient_fallback_test",
                    "top_k": 3,
                    "mode": "vector",
                    "llm_api_key": "test-key",
                },
            )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertTrue(result["resilient_fallback"])
        self.assertEqual(result["query_error"]["message"], "boom")
        self.assertTrue(result["citations"])
        self.assertIn("bearing overheating", result["citations"][0]["text"])

    def test_unified_query_replaces_empty_primary_answer_with_universal_fallback(self) -> None:
        payload = [
            {
                "id": "doc-a",
                "document_id": "manual-a.md",
                "section": "bearing case",
                "text": "Pump A failure was caused by bearing overheating and high vibration.",
            },
            {
                "id": "doc-b",
                "document_id": "manual-b.md",
                "section": "routine inspection",
                "text": "Pump B inspection was normal.",
            },
        ]
        ingest_json_payloads(
            payloads=[("generic_docs.json", orjson.dumps(payload))],
            persist_dir=self.persist_dir,
            collection_name="universal_fallback_test",
            chunk_size=1000,
            overlap=0,
            backend="hashing",
        )

        class EmptyGraphRagResult:
            def to_dict(self) -> dict:
                return {
                    "question": "What caused Pump A failure?",
                    "answer": "",
                    "context": "No text retrieval evidence returned.\nNo graph retrieval evidence returned.",
                    "citations": [],
                    "evidence": [],
                    "context_only": False,
                    "prompt": None,
                }

        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)
        with patch("chroma_rag_poc.api.GraphRagQAOrchestrator.answer", return_value=EmptyGraphRagResult()):
            response = client.post(
                "/api/query",
                json={
                    "question": "What caused Pump A failure?",
                    "collection": "universal_fallback_test",
                    "top_k": 3,
                    "mode": "vector",
                    "llm_api_key": "test-key",
                },
            )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertTrue(result["universal_answer_fallback"])
        self.assertEqual(result["answer_quality"]["status"], "fallback")
        self.assertTrue(result["citations"])
        self.assertIn("bearing overheating", result["answer"])
        self.assertIn("bearing overheating", result["citations"][0]["text"])

    def test_unified_query_replaces_irrelevant_cited_answer_with_keyword_fallback(self) -> None:
        payload = [
            {
                "id": "doc-a",
                "document_id": "manual-a.md",
                "section": "bearing case",
                "text": "Pump A failure was caused by bearing overheating and high vibration.",
            },
            {
                "id": "doc-b",
                "document_id": "manual-b.md",
                "section": "routine inspection",
                "text": "Pump B inspection was normal.",
            },
        ]
        ingest_json_payloads(
            payloads=[("generic_docs.json", orjson.dumps(payload))],
            persist_dir=self.persist_dir,
            collection_name="irrelevant_cited_answer_test",
            chunk_size=1000,
            overlap=0,
            backend="hashing",
        )

        class IrrelevantGraphRagResult:
            def to_dict(self) -> dict:
                return {
                    "question": "What caused bearing overheating?",
                    "answer": "Pump B inspection was normal. [T1]",
                    "context": "[T1] Pump B inspection was normal.",
                    "citations": [
                        {
                            "id": "T1",
                            "source_type": "text",
                            "rank": 1,
                            "text": "Pump B inspection was normal.",
                            "source": "manual-b.md",
                            "metadata": {},
                        }
                    ],
                    "evidence": [],
                    "context_only": False,
                    "prompt": None,
                }

        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)
        with patch("chroma_rag_poc.api.GraphRagQAOrchestrator.answer", return_value=IrrelevantGraphRagResult()):
            response = client.post(
                "/api/query",
                json={
                    "question": "What caused bearing overheating?",
                    "collection": "irrelevant_cited_answer_test",
                    "top_k": 3,
                    "mode": "vector",
                    "llm_api_key": "test-key",
                },
            )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertTrue(result["universal_answer_fallback"])
        self.assertIn("no_query_term_overlap", result["answer_quality"]["reason"])
        self.assertEqual(result["citations"][0]["source_type"], "text_universal_keyword_scan")
        self.assertIn("bearing overheating", result["citations"][0]["text"])

    def test_private_contact_abstract_affection_question_expands_to_evidence_terms(self) -> None:
        payload = [
            {
                "id": "chunk-1",
                "contact_id": "contact-a",
                "conversation_id": "wechat-private-0001-a",
                "partition_id": "contact:wxid_a",
                "conversation_type": "private",
                "contact_name": "\u5c0f\u7433",
                "username": "wxid_a",
                "message_count": 1,
                "first_date": "2026-01-01",
                "last_date": "2026-01-01",
                "text": "\u5fae\u4fe1\u804a\u5929\u8bb0\u5f55 - \u5c0f\u7433\n2026-01-01 [22:00:00] \u5c0f\u7433: \u6211\u60f3\u4f60\u4e86\uff0c\u4e5f\u559c\u6b22\u4f60\u3002",
            },
            {
                "id": "chunk-2",
                "contact_id": "contact-b",
                "conversation_id": "wechat-private-0002-b",
                "partition_id": "contact:wxid_b",
                "conversation_type": "private",
                "contact_name": "\u5f90\u660e\u9633",
                "username": "wxid_b",
                "message_count": 1,
                "first_date": "2026-01-02",
                "last_date": "2026-01-02",
                "text": "\u5fae\u4fe1\u804a\u5929\u8bb0\u5f55 - \u5f90\u660e\u9633\n2026-01-02 [13:00:00] \u5f90\u660e\u9633: \u6211\u4eec\u8ba8\u8bba\u4e00\u4e0b\u4f5c\u4e1a\u3002",
            },
        ]
        ingest_json_payloads(
            payloads=[("wechat_private_chunks_rag.json", orjson.dumps(payload))],
            persist_dir=self.persist_dir,
            collection_name="wechat_private_abstract_affection_test",
            chunk_size=1000,
            overlap=0,
            backend="hashing",
        )

        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)
        response = client.post(
            "/api/query",
            json={
                "question": "\u54ea\u4e9b\u4eba\u548c\u6211\u597d\u611f\u5ea6\u6bd4\u8f83\u9ad8\uff1f",
                "collection": "wechat_private_abstract_affection_test",
                "top_k": 1,
                "mode": "auto",
            },
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result["coverage_report"]["candidate_contact_count"], 1)
        self.assertIn("\u60f3\u4f60", result["coverage_report"]["query_terms"])
        contacts = result["contact_analysis"]["contacts"]
        self.assertEqual(contacts[0]["contact_name"], "\u5c0f\u7433")
        self.assertIn("\u559c\u6b22\u4f60", contacts[0]["evidence"][0]["text"])

    def test_unified_query_vague_wechat_overview_returns_deterministic_collection_summary(self) -> None:
        payload = [
            {
                "id": "chunk-1",
                "contact_id": "contact-a",
                "conversation_id": "wechat-private-0001-a",
                "partition_id": "contact:wxid_a",
                "conversation_type": "private",
                "contact_name": "\u5c0f\u7433",
                "username": "wxid_a",
                "message_count": 2,
                "first_date": "2026-01-01",
                "last_date": "2026-01-03",
                "text": "\u5fae\u4fe1\u804a\u5929\u8bb0\u5f55 - \u5c0f\u7433\n2026-01-01 [22:00:00] \u5c0f\u7433: \u6211\u60f3\u4f60\u4e86\n2026-01-03 [09:00:00] \u6211: \u4eca\u5929\u4f5c\u4e1a\u5f88\u591a",
            },
            {
                "id": "chunk-2",
                "contact_id": "contact-b",
                "conversation_id": "wechat-private-0002-b",
                "partition_id": "contact:wxid_b",
                "conversation_type": "private",
                "contact_name": "\u623f\u4e1c\u5f20\u54e5",
                "username": "wxid_b",
                "message_count": 1,
                "first_date": "2026-01-02",
                "last_date": "2026-01-02",
                "text": "\u5fae\u4fe1\u804a\u5929\u8bb0\u5f55 - \u623f\u4e1c\u5f20\u54e5\n2026-01-02 [10:00:00] \u623f\u4e1c\u5f20\u54e5: \u6211\u8fd9\u91cc\u6709\u623f\u5b50\u51fa\u79df\uff0c\u623f\u79df\u53ef\u4ee5\u9762\u8c08",
            },
        ]
        ingest_json_payloads(
            payloads=[("wechat_private_chunks_rag.json", orjson.dumps(payload))],
            persist_dir=self.persist_dir,
            collection_name="wechat_private_overview_test",
            chunk_size=1000,
            overlap=0,
            backend="hashing",
        )

        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)
        response = client.post(
            "/api/query",
            json={
                "question": "\u8fd9\u91cc\u9762\u8bb2\u7684\u662f\u4ec0\u4e48\uff1f",
                "collection": "wechat_private_overview_test",
                "top_k": 3,
                "mode": "auto",
            },
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result["coverage_report"]["analysis_type"], "collection_overview")
        self.assertFalse(result["coverage_report"]["top_k_used"])
        self.assertIn("\u5fae\u4fe1\u79c1\u804a\u96c6\u5408", result["answer"])
        self.assertIn("\u5c0f\u7433", result["answer"])
        self.assertTrue(result["citations"])
        self.assertEqual(result["citations"][0]["source_type"], "text_collection_overview")

    def test_unified_query_vague_people_relationships_returns_contact_overview(self) -> None:
        payload = [
            {
                "id": "chunk-1",
                "contact_id": "contact-a",
                "conversation_id": "wechat-private-0001-a",
                "partition_id": "contact:wxid_a",
                "conversation_type": "private",
                "contact_name": "\u5c0f\u7433",
                "username": "wxid_a",
                "message_count": 5,
                "first_date": "2026-01-01",
                "last_date": "2026-01-03",
                "text": "\u5fae\u4fe1\u804a\u5929\u8bb0\u5f55 - \u5c0f\u7433\n2026-01-01 [22:00:00] \u5c0f\u7433: \u6211\u60f3\u4f60\u4e86",
            },
            {
                "id": "chunk-2",
                "contact_id": "contact-b",
                "conversation_id": "wechat-private-0002-b",
                "partition_id": "contact:wxid_b",
                "conversation_type": "private",
                "contact_name": "\u5f90\u660e\u9633",
                "username": "wxid_b",
                "message_count": 2,
                "first_date": "2026-01-02",
                "last_date": "2026-01-02",
                "text": "\u5fae\u4fe1\u804a\u5929\u8bb0\u5f55 - \u5f90\u660e\u9633\n2026-01-02 [13:00:00] \u5f90\u660e\u9633: \u6211\u4eec\u8ba8\u8bba\u4e00\u4e0b\u4f5c\u4e1a",
            },
        ]
        ingest_json_payloads(
            payloads=[("wechat_private_chunks_rag.json", orjson.dumps(payload))],
            persist_dir=self.persist_dir,
            collection_name="wechat_private_contacts_overview_test",
            chunk_size=1000,
            overlap=0,
            backend="hashing",
        )

        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)
        response = client.post(
            "/api/query",
            json={
                "question": "\u6709\u54ea\u4e9b\u91cd\u8981\u7684\u4eba\u548c\u5173\u7cfb\uff1f",
                "collection": "wechat_private_contacts_overview_test",
                "top_k": 3,
                "mode": "auto",
            },
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result["coverage_report"]["analysis_type"], "private_contact_overview")
        self.assertIn("\u5c0f\u7433", result["answer"])
        self.assertIn("\u5f90\u660e\u9633", result["answer"])
        self.assertTrue(result["contact_overview"]["contacts"])

    def test_private_contact_overview_does_not_sum_repeated_message_count_per_chunk(self) -> None:
        payload = [
            {
                "id": "chunk-1",
                "contact_id": "contact-a",
                "conversation_id": "wechat-private-0001-a",
                "partition_id": "contact:wxid_a",
                "conversation_type": "private",
                "contact_name": "\u5c0f\u7433",
                "username": "wxid_a",
                "message_count": 10,
                "first_date": "2026-01-01",
                "last_date": "2026-01-02",
                "text": "\u5fae\u4fe1\u804a\u5929\u8bb0\u5f55 - \u5c0f\u7433\n2026-01-01 [22:00:00] \u5c0f\u7433: \u7b2c\u4e00\u6bb5",
            },
            {
                "id": "chunk-2",
                "contact_id": "contact-a",
                "conversation_id": "wechat-private-0001-a",
                "partition_id": "contact:wxid_a",
                "conversation_type": "private",
                "contact_name": "\u5c0f\u7433",
                "username": "wxid_a",
                "message_count": 10,
                "first_date": "2026-01-03",
                "last_date": "2026-01-04",
                "text": "\u5fae\u4fe1\u804a\u5929\u8bb0\u5f55 - \u5c0f\u7433\n2026-01-03 [22:00:00] \u5c0f\u7433: \u7b2c\u4e8c\u6bb5",
            },
        ]
        ingest_json_payloads(
            payloads=[("wechat_private_chunks_rag.json", orjson.dumps(payload))],
            persist_dir=self.persist_dir,
            collection_name="wechat_private_message_count_test",
            chunk_size=1000,
            overlap=0,
            backend="hashing",
        )

        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)
        response = client.post(
            "/api/query",
            json={
                "question": "\u6709\u54ea\u4e9b\u91cd\u8981\u7684\u4eba\u548c\u5173\u7cfb\uff1f",
                "collection": "wechat_private_message_count_test",
                "top_k": 3,
                "mode": "auto",
            },
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result["coverage_report"]["message_count_estimate"], 10)
        self.assertEqual(result["contact_overview"]["contacts"][0]["message_count"], 10)

    def test_private_contact_vague_affection_and_rental_questions_use_full_scan(self) -> None:
        payload = [
            {
                "id": "chunk-1",
                "contact_id": "contact-a",
                "conversation_id": "wechat-private-0001-a",
                "partition_id": "contact:wxid_a",
                "conversation_type": "private",
                "contact_name": "\u5c0f\u7433",
                "username": "wxid_a",
                "message_count": 1,
                "first_date": "2026-01-01",
                "last_date": "2026-01-01",
                "text": "\u5fae\u4fe1\u804a\u5929\u8bb0\u5f55 - \u5c0f\u7433\n2026-01-01 [22:00:00] \u5c0f\u7433: \u6211\u60f3\u4f60\u4e86\uff0c\u559c\u6b22\u4f60\u3002",
            },
            {
                "id": "chunk-2",
                "contact_id": "contact-rent",
                "conversation_id": "wechat-private-0002-rent",
                "partition_id": "contact:wxid_rent",
                "conversation_type": "private",
                "contact_name": "\u623f\u4e1c\u5f20\u54e5",
                "username": "wxid_rent",
                "message_count": 1,
                "first_date": "2026-01-02",
                "last_date": "2026-01-02",
                "text": "\u5fae\u4fe1\u804a\u5929\u8bb0\u5f55 - \u623f\u4e1c\u5f20\u54e5\n2026-01-02 [10:00:00] \u623f\u4e1c\u5f20\u54e5: \u6211\u8fd9\u91cc\u6709\u623f\u5b50\u51fa\u79df\uff0c\u623f\u79df\u53ef\u4ee5\u9762\u8c08",
            },
        ]
        ingest_json_payloads(
            payloads=[("wechat_private_chunks_rag.json", orjson.dumps(payload))],
            persist_dir=self.persist_dir,
            collection_name="wechat_private_vague_scan_test",
            chunk_size=1000,
            overlap=0,
            backend="hashing",
        )

        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)
        affection_response = client.post(
            "/api/query",
            json={
                "question": "\u6709\u6ca1\u6709\u4ec0\u4e48\u503c\u5f97\u6ce8\u610f\u7684\u60c5\u7eea\u6216\u66a7\u6627\u7ebf\u7d22\uff1f",
                "collection": "wechat_private_vague_scan_test",
                "top_k": 1,
                "mode": "auto",
            },
        )
        rental_response = client.post(
            "/api/query",
            json={
                "question": "\u5e2e\u6211\u627e\u4e00\u4e0b\u53ef\u80fd\u548c\u79df\u623f\u6709\u5173\u7684\u4eba\u3002",
                "collection": "wechat_private_vague_scan_test",
                "top_k": 1,
                "mode": "auto",
            },
        )

        self.assertEqual(affection_response.status_code, 200)
        affection = affection_response.json()
        self.assertEqual(affection["coverage_report"]["analysis_type"], "private_contact_affection_evidence_sweep")
        self.assertEqual(affection["coverage_report"]["candidate_contact_count"], 1)
        self.assertIn("\u5c0f\u7433", affection["answer"])

        self.assertEqual(rental_response.status_code, 200)
        rental = rental_response.json()
        self.assertEqual(rental["coverage_report"]["analysis_type"], "private_contact_term_evidence_sweep")
        self.assertEqual(rental["coverage_report"]["candidate_contact_count"], 1)
        self.assertIn("\u623f\u4e1c\u5f20\u54e5", rental["answer"])

    def test_unified_query_private_contact_event_sweep_bypasses_graph_gate(self) -> None:
        from storage_layer.graph_store import GraphEdgeRecord, GraphStore

        payload = [
            {
                "id": "chunk-1",
                "contact_id": "contact-a",
                "conversation_id": "wechat-private-0001-a",
                "partition_id": "contact:wxid_a",
                "conversation_type": "private",
                "contact_name": "\u5c0f\u7433",
                "username": "wxid_a",
                "message_count": 2,
                "first_date": "2026-01-01",
                "last_date": "2026-01-01",
                "text": "\u5fae\u4fe1\u804a\u5929\u8bb0\u5f55 - \u5c0f\u7433\n2026-01-01 [12:00:00] \u5c0f\u7433: \u6628\u5929\u6211\u4eec\u5435\u67b6\u540e\u8fd8\u6709\u4e89\u6267\uff0c\u4f60\u5bf9\u4e0d\u8d77\u6211\u3002",
            },
            {
                "id": "chunk-2",
                "contact_id": "contact-b",
                "conversation_id": "wechat-private-0002-b",
                "partition_id": "contact:wxid_b",
                "conversation_type": "private",
                "contact_name": "\u5f90\u660e\u9633",
                "username": "wxid_b",
                "message_count": 1,
                "first_date": "2026-01-02",
                "last_date": "2026-01-02",
                "text": "\u5fae\u4fe1\u804a\u5929\u8bb0\u5f55 - \u5f90\u660e\u9633\n2026-01-02 [13:00:00] \u5f90\u660e\u9633: \u6211\u4eec\u8ba8\u8bba\u4e00\u4e0b\u54f2\u5b66\u95ee\u9898\u3002",
            },
            {
                "id": "chunk-3",
                "contact_id": "filehelper",
                "conversation_id": "wechat-private-filehelper",
                "partition_id": "contact:filehelper",
                "conversation_type": "filehelper",
                "contact_name": "\u6587\u4ef6\u4f20\u8f93\u52a9\u624b",
                "username": "filehelper",
                "message_count": 1,
                "first_date": "2026-01-03",
                "last_date": "2026-01-03",
                "text": "\u5fae\u4fe1\u804a\u5929\u8bb0\u5f55 - \u6587\u4ef6\u4f20\u8f93\u52a9\u624b\n2026-01-03 [14:00:00] \u6211: \u5435\u67b6 \u4e89\u6267",
            },
        ]
        ingest_json_payloads(
            payloads=[("wechat_private_chunks_rag.json", orjson.dumps(payload))],
            persist_dir=self.persist_dir,
            collection_name="wechat_private_event_test",
            chunk_size=1000,
            overlap=0,
            backend="hashing",
        )
        graph_db_path = self.persist_dir / "unsafe_graph.sqlite"
        store = GraphStore(graph_db_path)
        store.initialize(reset=True)
        store.import_edges(
            [
                GraphEdgeRecord(
                    triple_id="unsafe-1",
                    subject="A",
                    predicate="RELATES_TO",
                    object_name="B",
                    confidence=0.1,
                    evidence=None,
                    source_file="unsafe.md",
                )
            ],
            reset=False,
        )

        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)
        response = client.post(
            "/api/query",
            json={
                "question": "\u6211\u548c\u54ea\u4e9b\u4eba\u53d1\u751f\u8fc7\u4e89\u6267?",
                "collection": "wechat_private_event_test",
                "graph_db_path": str(graph_db_path),
                "top_k": 1,
                "mode": "auto",
            },
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result["route"]["task_route"], "COMPREHENSIVE_ANALYSIS")
        self.assertEqual(result["advanced_mode"], "COMPREHENSIVE_ANALYSIS")
        self.assertEqual(result["coverage_report"]["analysis_type"], "private_contact_term_evidence_sweep")
        self.assertEqual(result["coverage_report"]["top_k_used"], False)
        self.assertEqual(result["coverage_report"]["private_contact_count"], 2)
        self.assertEqual(result["coverage_report"]["candidate_contact_count"], 1)
        self.assertEqual(result["coverage_report"]["excluded_reasons"]["system_or_file_helper"], 1)
        self.assertIn("Result:", result["answer"])
        self.assertNotIn("Full private-contact evidence sweep executed", result["answer"])
        contacts = result["contact_analysis"]["contacts"]
        self.assertEqual(contacts[0]["contact_name"], "\u5c0f\u7433")
        self.assertEqual(contacts[0]["judgement"], "has_matching_evidence")
        self.assertIn("\u4e89\u6267", contacts[0]["evidence"][0]["text"])
        self.assertEqual(result["citations"][0]["source_type"], "text_full_contact_term_scan")

    def test_unified_query_corpus_wide_question_uses_generic_full_scan_without_graph_gate(self) -> None:
        from storage_layer.graph_store import GraphEdgeRecord, GraphStore

        payload = [
            {
                "id": "doc-a",
                "document_id": "manual-a.md",
                "section": "bearing case",
                "text": "2026-01-01 Pump A reported bearing overheating and high vibration.",
            },
            {
                "id": "doc-b",
                "document_id": "manual-b.md",
                "section": "normal inspection",
                "text": "2026-01-02 Pump B inspection was normal.",
            },
        ]
        ingest_json_payloads(
            payloads=[("generic_docs.json", orjson.dumps(payload))],
            persist_dir=self.persist_dir,
            collection_name="generic_router_profile_test",
            chunk_size=1000,
            overlap=0,
            backend="hashing",
        )
        graph_db_path = self.persist_dir / "unsafe_generic_graph.sqlite"
        store = GraphStore(graph_db_path)
        store.initialize(reset=True)
        store.import_edges(
            [
                GraphEdgeRecord(
                    triple_id="unsafe-1",
                    subject="A",
                    predicate="RELATES_TO",
                    object_name="B",
                    confidence=0.1,
                    evidence=None,
                    source_file="unsafe.md",
                )
            ],
            reset=False,
        )

        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)
        response = client.post(
            "/api/query",
            json={
                "question": "Which documents mention bearing overheating, and what evidence supports each document?",
                "collection": "generic_router_profile_test",
                "graph_db_path": str(graph_db_path),
                "top_k": 1,
                "mode": "auto",
            },
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result["route"]["task_route"], "COMPREHENSIVE_ANALYSIS")
        self.assertEqual(result["coverage_report"]["analysis_type"], "generic_partition_evidence_sweep")
        self.assertEqual(result["coverage_report"]["top_k_used"], False)
        self.assertEqual(result["coverage_report"]["candidate_partition_count"], 1)
        candidates = result["partition_analysis"]["candidates"]
        self.assertEqual(candidates[0]["partition_id"], "manual-a.md")
        self.assertIn("bearing overheating", candidates[0]["evidence"][0]["text"])

    def test_unified_query_private_contact_question_uses_generic_contact_sweep(self) -> None:
        from storage_layer.graph_store import GraphEdgeRecord, GraphStore

        payload = [
            {
                "id": "chunk-1",
                "contact_id": "contact-a",
                "conversation_id": "wechat-private-0001-a",
                "partition_id": "contact:wxid_a",
                "conversation_type": "private",
                "contact_name": "\u679c\u679c",
                "username": "wxid_a",
                "message_count": 2,
                "first_date": "2026-01-01",
                "last_date": "2026-01-01",
                "text": "\u5fae\u4fe1\u804a\u5929\u8bb0\u5f55 - \u679c\u679c\n2026-01-01 [12:00:00] \u679c\u679c: \u522b\u96be\u8fc7\uff0c\u6211\u6765\u5b89\u6170\u4f60\u4e00\u4e0b\u3002",
            },
            {
                "id": "chunk-2",
                "contact_id": "contact-b",
                "conversation_id": "wechat-private-0002-b",
                "partition_id": "contact:wxid_b",
                "conversation_type": "private",
                "contact_name": "\u5f90\u660e\u9633",
                "username": "wxid_b",
                "message_count": 1,
                "first_date": "2026-01-02",
                "last_date": "2026-01-02",
                "text": "\u5fae\u4fe1\u804a\u5929\u8bb0\u5f55 - \u5f90\u660e\u9633\n2026-01-02 [13:00:00] \u5f90\u660e\u9633: \u6211\u4eec\u8ba8\u8bba\u4e00\u4e0b\u54f2\u5b66\u95ee\u9898\u3002",
            },
        ]
        ingest_json_payloads(
            payloads=[("wechat_private_chunks_rag.json", orjson.dumps(payload))],
            persist_dir=self.persist_dir,
            collection_name="wechat_private_generic_contact_query_test",
            chunk_size=1000,
            overlap=0,
            backend="hashing",
        )
        graph_db_path = self.persist_dir / "unsafe_graph_generic_contact.sqlite"
        store = GraphStore(graph_db_path)
        store.initialize(reset=True)
        store.import_edges(
            [
                GraphEdgeRecord(
                    triple_id="unsafe-1",
                    subject="A",
                    predicate="RELATES_TO",
                    object_name="B",
                    confidence=0.1,
                    evidence=None,
                    source_file="unsafe.md",
                )
            ],
            reset=False,
        )

        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)
        response = client.post(
            "/api/query",
            json={
                "question": "\u8c01\u7ecf\u5e38\u5b89\u6170\u6211?",
                "collection": "wechat_private_generic_contact_query_test",
                "graph_db_path": str(graph_db_path),
                "top_k": 1,
                "mode": "auto",
            },
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result["route"]["task_route"], "COMPREHENSIVE_ANALYSIS")
        self.assertEqual(result["coverage_report"]["analysis_type"], "private_contact_term_evidence_sweep")
        self.assertEqual(result["coverage_report"]["query_terms"], ["\u5b89\u6170"])
        contacts = result["contact_analysis"]["contacts"]
        self.assertEqual(contacts[0]["contact_name"], "\u679c\u679c")
        self.assertIn("\u5b89\u6170", contacts[0]["evidence"][0]["text"])

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
        query_text = "status monitoring"
        search = client.post(
            "/api/search",
            json={"collection": "api-demo", "query": query_text, "top_k": 2},
        )
        self.assertEqual(search.status_code, 200)
        search_payload = search.json()
        self.assertTrue(search_payload["results"])
        diagnostics = search_payload["retrieval_diagnostics"]
        self.assertEqual(diagnostics["original_query"], query_text)
        self.assertEqual(diagnostics["rewritten_queries"], [query_text])
        self.assertEqual(diagnostics["retrieval_path"], "hybrid")
        self.assertEqual(diagnostics["fusion_mode"], "rrf")
        self.assertGreaterEqual(diagnostics["raw_candidate_count"], len(search_payload["results"]))
        self.assertGreaterEqual(diagnostics["filtered_candidate_count"], len(search_payload["results"]))
        self.assertEqual(diagnostics["final_candidate_count"], len(search_payload["results"]))
        self.assertFalse(diagnostics["filters_applied"])
        self.assertIsNone(diagnostics["reranker_error"])
        self.assertFalse(diagnostics["no_answer"])
        self.assertIsNone(diagnostics["no_answer_reason"])
        retriever_names = {item["name"] for item in diagnostics["retrievers"]}
        self.assertIn("chroma_vector", retriever_names)
        self.assertIn("keyword", retriever_names)
        self.assertTrue(
            any("rrf:chroma_vector" in result["metadata"].get("component_scores", {}) for result in search_payload["results"])
        )
        self.assertTrue(search_payload.get("log_file"))
        self.assertNotIn("log_path", search_payload)

    def test_api_search_can_enable_query_rewrite_and_noop_reranker(self) -> None:
        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)

        ingest = client.post(
            "/api/ingest",
            data={
                "collection": "rewrite-demo",
                "chunk_size": "50",
                "overlap": "10",
                "backend": "hashing",
            },
            files=[
                ("files", ("demo.json", build_label_studio_payload(), "application/json")),
            ],
        )
        self.assertEqual(ingest.status_code, 200)

        search = client.post(
            "/api/search",
            json={
                "collection": "rewrite-demo",
                "query": "status monitoring",
                "top_k": 2,
                "query_rewrite": True,
                "reranker": "noop",
            },
        )

        self.assertEqual(search.status_code, 200)
        payload = search.json()
        diagnostics = payload["retrieval_diagnostics"]
        self.assertEqual(diagnostics["fusion_mode"], "rrf")
        self.assertGreater(len(diagnostics["rewritten_queries"]), 1)
        self.assertEqual(diagnostics["reranker_name"], "noop")
        self.assertIsNone(diagnostics["reranker_error"])
        self.assertTrue(payload["results"])
        self.assertTrue(
            any("reranker" in result["metadata"].get("component_scores", {}) for result in payload["results"])
        )

    def test_api_search_applies_collection_retrieval_policy_defaults(self) -> None:
        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)

        ingest = client.post(
            "/api/ingest",
            data={
                "collection": "policy-demo",
                "chunk_size": "50",
                "overlap": "10",
                "backend": "hashing",
            },
            files=[
                ("files", ("demo.json", build_label_studio_payload(), "application/json")),
            ],
        )
        self.assertEqual(ingest.status_code, 200)
        (self.persist_dir / "retrieval_policies.json").write_text(
            orjson.dumps(
                {
                    "collections": {
                        "policy-demo": {
                            "query_rewrite": True,
                            "reranker": "noop",
                        }
                    }
                },
                option=orjson.OPT_INDENT_2,
            ).decode("utf-8"),
            encoding="utf-8",
        )

        search = client.post(
            "/api/search",
            json={
                "collection": "policy-demo",
                "query": "status monitoring",
                "top_k": 2,
            },
        )

        self.assertEqual(search.status_code, 200)
        payload = search.json()
        diagnostics = payload["retrieval_diagnostics"]
        self.assertTrue(diagnostics["retrieval_policy"]["applied"])
        self.assertEqual(diagnostics["retrieval_policy"]["settings"]["reranker"], "noop")
        self.assertGreater(len(diagnostics["rewritten_queries"]), 1)
        self.assertEqual(diagnostics["reranker_name"], "noop")

    def test_api_promotes_retrieval_policy_with_audit_and_applies_it(self) -> None:
        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)

        ingest = client.post(
            "/api/ingest",
            data={
                "collection": "promotion-demo",
                "chunk_size": "50",
                "overlap": "10",
                "backend": "hashing",
            },
            files=[
                ("files", ("demo.json", build_label_studio_payload(), "application/json")),
            ],
        )
        self.assertEqual(ingest.status_code, 200)

        promotion = client.post(
            "/api/retrieval/policies/promote",
            json={
                "collection": "promotion-demo",
                "settings": {"query_rewrite": True, "reranker": "noop"},
                "reviewer": "unit-reviewer",
                "review_note": "Promote smoke policy after evaluation pass.",
                "source_report": "evaluation/reports/unit.json",
            },
        )

        self.assertEqual(promotion.status_code, 200)
        promoted = promotion.json()
        self.assertEqual(promoted["collection"], "promotion-demo")
        self.assertTrue(promoted["settings"]["query_rewrite"])
        self.assertEqual(promoted["settings"]["reranker"], "noop")
        self.assertEqual(promoted["audit_entry"]["reviewer"], "unit-reviewer")
        policy_file = self.persist_dir / "retrieval_policies.json"
        self.assertTrue(policy_file.exists())
        saved_policy = orjson.loads(policy_file.read_bytes())
        self.assertEqual(saved_policy["collections"]["promotion-demo"]["reranker"], "noop")
        self.assertEqual(saved_policy["audit"][-1]["review_note"], "Promote smoke policy after evaluation pass.")

        search = client.post(
            "/api/search",
            json={
                "collection": "promotion-demo",
                "query": "status monitoring",
                "top_k": 2,
            },
        )

        self.assertEqual(search.status_code, 200)
        diagnostics = search.json()["retrieval_diagnostics"]
        self.assertTrue(diagnostics["retrieval_policy"]["applied"])
        self.assertEqual(diagnostics["reranker_name"], "noop")
        self.assertGreater(len(diagnostics["rewritten_queries"]), 1)

    def test_api_rolls_back_retrieval_policy_to_previous_audited_version(self) -> None:
        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)

        first = client.post(
            "/api/retrieval/policies/promote",
            json={
                "collection": "rollback-demo",
                "settings": {"query_rewrite": True, "reranker": "noop"},
                "reviewer": "unit-reviewer",
                "review_note": "first policy",
            },
        )
        self.assertEqual(first.status_code, 200)
        second = client.post(
            "/api/retrieval/policies/promote",
            json={
                "collection": "rollback-demo",
                "settings": {"query_rewrite": False, "reranker": "none"},
                "reviewer": "unit-reviewer",
                "review_note": "second policy",
            },
        )
        self.assertEqual(second.status_code, 200)

        rollback = client.post(
            "/api/retrieval/policies/rollback",
            json={
                "collection": "rollback-demo",
                "reviewer": "unit-reviewer",
                "review_note": "rollback to first policy",
            },
        )

        self.assertEqual(rollback.status_code, 200)
        payload = rollback.json()
        self.assertEqual(payload["collection"], "rollback-demo")
        self.assertEqual(payload["settings"]["reranker"], "noop")
        self.assertTrue(payload["settings"]["query_rewrite"])
        self.assertEqual(payload["audit_entry"]["action"], "rollback")
        saved_policy = orjson.loads((self.persist_dir / "retrieval_policies.json").read_bytes())
        self.assertEqual(saved_policy["collections"]["rollback-demo"]["reranker"], "noop")
        self.assertEqual(saved_policy["audit"][-1]["review_note"], "rollback to first policy")

    def test_api_returns_retrieval_policy_history_with_latest_diff(self) -> None:
        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)

        first = client.post(
            "/api/retrieval/policies/promote",
            json={
                "collection": "history-demo",
                "settings": {"query_rewrite": True, "reranker": "noop"},
                "reviewer": "unit-reviewer",
                "review_note": "first policy",
            },
        )
        self.assertEqual(first.status_code, 200)
        second = client.post(
            "/api/retrieval/policies/promote",
            json={
                "collection": "history-demo",
                "settings": {"query_rewrite": False, "reranker": "none", "no_answer_min_results": 2},
                "reviewer": "unit-reviewer",
                "review_note": "second policy",
            },
        )
        self.assertEqual(second.status_code, 200)

        history = client.get("/api/retrieval/policies/history", params={"collection": "history-demo"})

        self.assertEqual(history.status_code, 200)
        payload = history.json()
        self.assertEqual(payload["collection"], "history-demo")
        self.assertEqual(payload["current_policy"]["reranker"], "none")
        self.assertEqual(len(payload["history"]), 2)
        self.assertEqual(payload["latest_diff"]["changed"]["reranker"], {"from": "noop", "to": "none"})
        self.assertEqual(payload["latest_diff"]["changed"]["query_rewrite"], {"from": True, "to": False})
        self.assertEqual(payload["latest_diff"]["added"]["no_answer_min_results"], 2)

    def test_api_proposes_retrieval_policy_without_applying_it(self) -> None:
        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)

        proposal = client.post(
            "/api/retrieval/policies/propose",
            json={
                "collection": "approval-demo",
                "settings": {"query_rewrite": True, "reranker": "noop"},
                "reviewer": "unit-reviewer",
                "reviewer_role": "reviewer",
                "review_note": "Needs approval before runtime default.",
                "source_report": "evaluation/reports/approval.json",
            },
        )

        self.assertEqual(proposal.status_code, 200)
        body = proposal.json()
        self.assertEqual(body["collection"], "approval-demo")
        self.assertEqual(body["status"], "pending")
        self.assertTrue(body["proposal_id"])
        saved_policy = orjson.loads((self.persist_dir / "retrieval_policies.json").read_bytes())
        self.assertNotIn("approval-demo", saved_policy.get("collections", {}))
        self.assertEqual(saved_policy["proposals"][body["proposal_id"]]["status"], "pending")

        history = client.get("/api/retrieval/policies/history", params={"collection": "approval-demo"})
        self.assertEqual(history.status_code, 200)
        self.assertEqual(history.json()["pending_proposals"][0]["proposal_id"], body["proposal_id"])

    def test_api_approves_retrieval_policy_proposal_with_role_gate(self) -> None:
        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)

        proposal = client.post(
            "/api/retrieval/policies/propose",
            json={
                "collection": "approval-demo",
                "settings": {"query_rewrite": True, "reranker": "noop"},
                "reviewer": "unit-reviewer",
                "reviewer_role": "reviewer",
            },
        )
        self.assertEqual(proposal.status_code, 200)
        proposal_id = proposal.json()["proposal_id"]

        rejected_role = client.post(
            "/api/retrieval/policies/approve",
            json={
                "proposal_id": proposal_id,
                "approver": "unit-reviewer",
                "approver_role": "reviewer",
                "approval_note": "Reviewer cannot self-approve runtime defaults.",
            },
        )
        self.assertEqual(rejected_role.status_code, 400)

        approved = client.post(
            "/api/retrieval/policies/approve",
            json={
                "proposal_id": proposal_id,
                "approver": "unit-approver",
                "approver_role": "approver",
                "approval_note": "Approved after eval review.",
            },
        )

        self.assertEqual(approved.status_code, 200)
        body = approved.json()
        self.assertEqual(body["status"], "approved")
        self.assertEqual(body["settings"]["reranker"], "noop")
        self.assertEqual(body["audit_entry"]["action"], "approve")
        self.assertEqual(body["audit_entry"]["approver"], "unit-approver")
        saved_policy = orjson.loads((self.persist_dir / "retrieval_policies.json").read_bytes())
        self.assertEqual(saved_policy["collections"]["approval-demo"]["reranker"], "noop")
        self.assertEqual(saved_policy["proposals"][proposal_id]["status"], "approved")

    def test_api_rejects_retrieval_policy_self_approval(self) -> None:
        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)

        proposal = client.post(
            "/api/retrieval/policies/propose",
            json={
                "collection": "self-approval-demo",
                "settings": {"query_rewrite": True, "reranker": "noop"},
                "reviewer": "same-person",
                "reviewer_role": "reviewer",
            },
        )
        self.assertEqual(proposal.status_code, 200)

        response = client.post(
            "/api/retrieval/policies/approve",
            json={
                "proposal_id": proposal.json()["proposal_id"],
                "approver": "same-person",
                "approver_role": "approver",
                "approval_note": "Self approval should not be allowed.",
            },
        )

        self.assertEqual(response.status_code, 400)
        saved_policy = orjson.loads((self.persist_dir / "retrieval_policies.json").read_bytes())
        self.assertNotIn("self-approval-demo", saved_policy.get("collections", {}))
        self.assertEqual(saved_policy["proposals"][proposal.json()["proposal_id"]]["status"], "pending")

    def test_api_rejects_retrieval_policy_proposal_with_audit(self) -> None:
        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)

        proposal = client.post(
            "/api/retrieval/policies/propose",
            json={
                "collection": "reject-demo",
                "settings": {"query_rewrite": True, "reranker": "noop"},
                "reviewer": "unit-reviewer",
                "reviewer_role": "reviewer",
            },
        )
        self.assertEqual(proposal.status_code, 200)
        proposal_id = proposal.json()["proposal_id"]

        rejected = client.post(
            "/api/retrieval/policies/reject",
            json={
                "proposal_id": proposal_id,
                "approver": "unit-approver",
                "approver_role": "approver",
                "rejection_note": "Threshold evidence is not strong enough.",
            },
        )

        self.assertEqual(rejected.status_code, 200)
        body = rejected.json()
        self.assertEqual(body["status"], "rejected")
        self.assertEqual(body["audit_entry"]["action"], "reject")
        self.assertEqual(body["audit_entry"]["rejection_note"], "Threshold evidence is not strong enough.")
        saved_policy = orjson.loads((self.persist_dir / "retrieval_policies.json").read_bytes())
        self.assertNotIn("reject-demo", saved_policy.get("collections", {}))
        self.assertEqual(saved_policy["proposals"][proposal_id]["status"], "rejected")

    def test_api_uses_server_role_registry_for_retrieval_policy_approval(self) -> None:
        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)

        allowed_role = client.post(
            "/api/retrieval/policies/roles/upsert",
            json={
                "subject": "unit-approver",
                "roles": ["approver"],
                "assigned_collections": ["rbac-demo"],
                "updated_by": "unit-admin",
                "note": "service-side approver role",
            },
        )
        self.assertEqual(allowed_role.status_code, 200)
        blocked_role = client.post(
            "/api/retrieval/policies/roles/upsert",
            json={
                "subject": "blocked-user",
                "roles": ["reviewer"],
                "assigned_collections": ["rbac-demo"],
                "updated_by": "unit-admin",
            },
        )
        self.assertEqual(blocked_role.status_code, 200)

        proposal = client.post(
            "/api/retrieval/policies/propose",
            json={
                "collection": "rbac-demo",
                "settings": {"query_rewrite": True, "reranker": "noop"},
                "reviewer": "unit-reviewer",
                "reviewer_role": "reviewer",
            },
        )
        self.assertEqual(proposal.status_code, 200)
        proposal_id = proposal.json()["proposal_id"]

        blocked = client.post(
            "/api/retrieval/policies/approve",
            json={
                "proposal_id": proposal_id,
                "approver": "blocked-user",
                "approver_role": "approver",
                "approval_note": "client-side role should not be trusted",
            },
        )
        self.assertEqual(blocked.status_code, 400)

        approved = client.post(
            "/api/retrieval/policies/approve",
            json={
                "proposal_id": proposal_id,
                "approver": "unit-approver",
                "approver_role": "reviewer",
                "approval_note": "server registry role should win",
            },
        )
        self.assertEqual(approved.status_code, 200)
        body = approved.json()
        self.assertEqual(body["audit_entry"]["approver_role"], "approver")
        self.assertEqual(body["audit_entry"]["role_source"], "role_registry")
        saved_policy = orjson.loads((self.persist_dir / "retrieval_policies.json").read_bytes())
        self.assertEqual(saved_policy["collections"]["rbac-demo"]["reranker"], "noop")
        self.assertEqual(saved_policy["role_registry"]["unit-approver"]["roles"], ["approver"])

    def test_api_syncs_scim_directory_into_policy_role_and_recipient_registries(self) -> None:
        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)

        synced = client.post(
            "/api/retrieval/policies/directory/sync",
            json={
                "source_type": "scim",
                "updated_by": "unit-idp-sync",
                "note": "nightly directory sync",
                "role_group_mappings": {
                    "RAG Approvers": {
                        "roles": ["approver"],
                        "assigned_collections": ["directory-sync-demo"],
                    }
                },
                "recipient_defaults": {"preferred_delivery_mode": "smtp"},
                "users": [
                    {
                        "id": "user-1",
                        "userName": "approver@example.com",
                        "displayName": "Unit Approver",
                        "active": True,
                        "emails": [{"value": "approver@example.com", "primary": True}],
                    },
                    {
                        "id": "user-2",
                        "userName": "disabled@example.com",
                        "displayName": "Disabled User",
                        "active": False,
                        "emails": [{"value": "disabled@example.com", "primary": True}],
                    },
                ],
                "groups": [
                    {
                        "id": "group-approvers",
                        "displayName": "RAG Approvers",
                        "members": [{"value": "user-1"}, {"value": "user-2"}],
                    }
                ],
            },
        )
        self.assertEqual(synced.status_code, 200)
        body = synced.json()
        self.assertEqual(body["source_type"], "scim")
        self.assertEqual(body["synced_user_count"], 2)
        self.assertEqual(body["active_user_count"], 1)
        self.assertEqual(body["disabled_user_count"], 1)
        self.assertEqual(body["role_upsert_count"], 1)
        self.assertEqual(body["recipient_upsert_count"], 1)
        self.assertEqual(body["disabled_subjects"], ["disabled@example.com"])

        proposal = client.post(
            "/api/retrieval/policies/propose",
            json={
                "collection": "directory-sync-demo",
                "settings": {"query_rewrite": True, "reranker": "noop"},
                "reviewer": "unit-reviewer",
                "reviewer_role": "reviewer",
            },
        )
        self.assertEqual(proposal.status_code, 200)

        approved = client.post(
            "/api/retrieval/policies/approve",
            json={
                "proposal_id": proposal.json()["proposal_id"],
                "approver": "approver@example.com",
                "approver_role": "reviewer",
                "approval_note": "directory role should win",
            },
        )
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(approved.json()["audit_entry"]["role_source"], "role_registry")

        blocked_proposal = client.post(
            "/api/retrieval/policies/propose",
            json={
                "collection": "directory-sync-demo",
                "settings": {"query_rewrite": False, "reranker": "noop"},
                "reviewer": "unit-reviewer-2",
                "reviewer_role": "reviewer",
            },
        )
        self.assertEqual(blocked_proposal.status_code, 200)
        blocked = client.post(
            "/api/retrieval/policies/approve",
            json={
                "proposal_id": blocked_proposal.json()["proposal_id"],
                "approver": "disabled@example.com",
                "approver_role": "owner",
                "approval_note": "inactive directory account must not approve",
            },
        )
        self.assertEqual(blocked.status_code, 400)

        saved_policy = orjson.loads((self.persist_dir / "retrieval_policies.json").read_bytes())
        self.assertEqual(saved_policy["role_registry"]["approver@example.com"]["roles"], ["approver"])
        self.assertEqual(
            saved_policy["role_registry"]["approver@example.com"]["assigned_collections"],
            ["directory-sync-demo"],
        )
        self.assertTrue(saved_policy["role_registry"]["approver@example.com"]["active"])
        self.assertFalse(saved_policy["role_registry"]["disabled@example.com"]["active"])
        self.assertEqual(saved_policy["role_registry"]["disabled@example.com"]["roles"], [])
        self.assertEqual(saved_policy["notification_recipient_registry"]["approver@example.com"]["email"], "approver@example.com")
        self.assertEqual(
            saved_policy["notification_recipient_registry"]["approver@example.com"]["preferred_delivery_mode"],
            "smtp",
        )
        self.assertTrue(any(entry.get("action") == "directory_sync" for entry in saved_policy["audit"]))

    def test_api_uses_oidc_bearer_identity_for_policy_approval_when_required(self) -> None:
        import base64
        import time

        import jwt
        from cryptography.hazmat.primitives.asymmetric import rsa

        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public_numbers = private_key.public_key().public_numbers()

        def b64url_int(value: int) -> str:
            raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
            return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

        jwks = {
            "keys": [
                {
                    "kty": "RSA",
                    "use": "sig",
                    "kid": "unit-oidc-key",
                    "alg": "RS256",
                    "n": b64url_int(public_numbers.n),
                    "e": b64url_int(public_numbers.e),
                }
            ]
        }

        class JwksHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 - stdlib handler hook
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(orjson.dumps(jwks))

            def log_message(self, *_: object) -> None:
                return

        jwks_server = HTTPServer(("127.0.0.1", 0), JwksHandler)
        thread = threading.Thread(target=jwks_server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(jwks_server.server_close)
        self.addCleanup(jwks_server.shutdown)
        jwks_url = f"http://127.0.0.1:{jwks_server.server_address[1]}/.well-known/jwks.json"

        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)
        synced = client.post(
            "/api/retrieval/policies/directory/sync",
            json={
                "source_type": "scim",
                "updated_by": "unit-idp-sync",
                "role_group_mappings": {
                    "RAG Approvers": {
                        "roles": ["approver"],
                        "assigned_collections": ["oidc-approval-demo"],
                    }
                },
                "users": [
                    {
                        "id": "oidc-user-1",
                        "userName": "sso-approver@example.com",
                        "active": True,
                        "emails": [{"value": "sso-approver@example.com", "primary": True}],
                    }
                ],
                "groups": [
                    {
                        "displayName": "RAG Approvers",
                        "members": [{"value": "oidc-user-1"}],
                    }
                ],
            },
        )
        self.assertEqual(synced.status_code, 200)

        proposal = client.post(
            "/api/retrieval/policies/propose",
            json={
                "collection": "oidc-approval-demo",
                "settings": {"query_rewrite": True, "reranker": "noop"},
                "reviewer": "unit-reviewer",
                "reviewer_role": "reviewer",
            },
        )
        self.assertEqual(proposal.status_code, 200)

        token = jwt.encode(
            {
                "iss": "https://idp.example.test/",
                "aud": "rag-console",
                "sub": "oidc-user-1",
                "email": "sso-approver@example.com",
                "groups": ["RAG Approvers"],
                "exp": int(time.time()) + 300,
                "iat": int(time.time()),
            },
            private_key,
            algorithm="RS256",
            headers={"kid": "unit-oidc-key"},
        )

        with patch.dict(
            "os.environ",
            {
                "RAG_POLICY_OIDC_REQUIRED": "1",
                "RAG_POLICY_OIDC_ISSUER": "https://idp.example.test/",
                "RAG_POLICY_OIDC_AUDIENCE": "rag-console",
                "RAG_POLICY_OIDC_JWKS_URL": jwks_url,
                "RAG_POLICY_OIDC_SUBJECT_CLAIM": "email",
            },
        ):
            blocked_without_token = client.post(
                "/api/retrieval/policies/approve",
                json={
                    "proposal_id": proposal.json()["proposal_id"],
                    "approver": "attacker@example.com",
                    "approver_role": "owner",
                    "approval_note": "request body must not define identity",
                },
            )
            self.assertEqual(blocked_without_token.status_code, 401)

            approved = client.post(
                "/api/retrieval/policies/approve",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "proposal_id": proposal.json()["proposal_id"],
                    "approver": "attacker@example.com",
                    "approver_role": "owner",
                    "approval_note": "token identity should win",
                },
            )

        self.assertEqual(approved.status_code, 200)
        body = approved.json()
        self.assertEqual(body["audit_entry"]["approver"], "sso-approver@example.com")
        self.assertEqual(body["audit_entry"]["approver_role"], "approver")
        self.assertEqual(body["audit_entry"]["role_source"], "role_registry")
        self.assertEqual(body["audit_entry"]["identity_source"], "oidc")
        self.assertNotEqual(body["audit_entry"]["approver"], "attacker@example.com")

    def test_api_uses_persisted_oidc_identity_provider_config_for_policy_approval(self) -> None:
        import base64
        import time

        import jwt
        from cryptography.hazmat.primitives.asymmetric import rsa

        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public_numbers = private_key.public_key().public_numbers()

        def b64url_int(value: int) -> str:
            raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
            return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

        jwks = {
            "keys": [
                {
                    "kty": "RSA",
                    "use": "sig",
                    "kid": "persisted-oidc-key",
                    "alg": "RS256",
                    "n": b64url_int(public_numbers.n),
                    "e": b64url_int(public_numbers.e),
                }
            ]
        }

        class JwksHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 - stdlib handler hook
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(orjson.dumps(jwks))

            def log_message(self, *_: object) -> None:
                return

        jwks_server = HTTPServer(("127.0.0.1", 0), JwksHandler)
        thread = threading.Thread(target=jwks_server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(jwks_server.server_close)
        self.addCleanup(jwks_server.shutdown)
        jwks_url = f"http://127.0.0.1:{jwks_server.server_address[1]}/jwks.json"

        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)
        configured = client.post(
            "/api/retrieval/policies/identity-provider/upsert",
            json={
                "provider": "oidc",
                "enabled": True,
                "issuer": "https://managed-idp.example.test/",
                "audience": "rag-console-managed",
                "jwks_url": jwks_url,
                "subject_claim": "email",
                "groups_claim": "groups",
                "algorithms": ["RS256"],
                "client_secret": "must-not-be-stored",
                "updated_by": "unit-admin",
                "note": "managed IdP config",
            },
        )
        self.assertEqual(configured.status_code, 200)
        self.assertTrue(configured.json()["identity_provider"]["enabled"])

        loaded_config = client.get("/api/retrieval/policies/identity-provider")
        self.assertEqual(loaded_config.status_code, 200)
        self.assertEqual(loaded_config.json()["identity_provider"]["issuer"], "https://managed-idp.example.test/")

        synced = client.post(
            "/api/retrieval/policies/directory/sync",
            json={
                "source_type": "scim",
                "role_group_mappings": {
                    "RAG Approvers": {
                        "roles": ["approver"],
                        "assigned_collections": ["managed-oidc-demo"],
                    }
                },
                "users": [
                    {
                        "id": "managed-oidc-user-1",
                        "userName": "managed-approver@example.com",
                        "active": True,
                        "emails": [{"value": "managed-approver@example.com", "primary": True}],
                    }
                ],
                "groups": [
                    {
                        "displayName": "RAG Approvers",
                        "members": [{"value": "managed-oidc-user-1"}],
                    }
                ],
            },
        )
        self.assertEqual(synced.status_code, 200)

        proposal = client.post(
            "/api/retrieval/policies/propose",
            json={
                "collection": "managed-oidc-demo",
                "settings": {"query_rewrite": True, "reranker": "noop"},
                "reviewer": "unit-reviewer",
                "reviewer_role": "reviewer",
            },
        )
        self.assertEqual(proposal.status_code, 401)

        proposal_token = jwt.encode(
            {
                "iss": "https://managed-idp.example.test/",
                "aud": "rag-console-managed",
                "sub": "managed-reviewer-1",
                "email": "managed-reviewer@example.com",
                "groups": ["RAG Reviewers"],
                "exp": int(time.time()) + 300,
                "iat": int(time.time()),
            },
            private_key,
            algorithm="RS256",
            headers={"kid": "persisted-oidc-key"},
        )
        proposal = client.post(
            "/api/retrieval/policies/propose",
            headers={"Authorization": f"Bearer {proposal_token}"},
            json={
                "collection": "managed-oidc-demo",
                "settings": {"query_rewrite": True, "reranker": "noop"},
                "reviewer": "request-reviewer@example.com",
                "reviewer_role": "owner",
            },
        )
        self.assertEqual(proposal.status_code, 200)
        self.assertEqual(proposal.json()["proposal"]["reviewer"], "managed-reviewer@example.com")

        approval_token = jwt.encode(
            {
                "iss": "https://managed-idp.example.test/",
                "aud": "rag-console-managed",
                "sub": "managed-oidc-user-1",
                "email": "managed-approver@example.com",
                "groups": ["RAG Approvers"],
                "exp": int(time.time()) + 300,
                "iat": int(time.time()),
            },
            private_key,
            algorithm="RS256",
            headers={"kid": "persisted-oidc-key"},
        )
        approved = client.post(
            "/api/retrieval/policies/approve",
            headers={"Authorization": f"Bearer {approval_token}"},
            json={
                "proposal_id": proposal.json()["proposal_id"],
                "approver": "attacker@example.com",
                "approver_role": "owner",
            },
        )
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(approved.json()["audit_entry"]["approver"], "managed-approver@example.com")
        self.assertEqual(approved.json()["audit_entry"]["identity_source"], "oidc")

        saved_policy = orjson.loads((self.persist_dir / "retrieval_policies.json").read_bytes())
        serialized_policy = orjson.dumps(saved_policy).decode("utf-8")
        self.assertNotIn("must-not-be-stored", serialized_policy)
        self.assertEqual(saved_policy["identity_provider"]["oidc"]["issuer"], "https://managed-idp.example.test/")
        self.assertTrue(any(entry.get("action") == "identity_provider_upsert" for entry in saved_policy["audit"]))

    def test_api_builds_oidc_pkce_login_url_and_exchanges_code_without_storing_secret(self) -> None:
        import urllib.parse

        captured_token_request: dict[str, str] = {}

        class OidcHandler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802 - stdlib handler hook
                raw_body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                captured_token_request.update(
                    {
                        key: values[-1]
                        for key, values in urllib.parse.parse_qs(raw_body.decode("utf-8")).items()
                    }
                )
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(
                    orjson.dumps(
                        {
                            "access_token": "access-token-from-idp",
                            "id_token": "id-token-from-idp",
                            "token_type": "Bearer",
                            "expires_in": 300,
                            "refresh_token": "refresh-token-from-idp",
                        }
                    )
                )

            def log_message(self, *_: object) -> None:
                return

        oidc_server = HTTPServer(("127.0.0.1", 0), OidcHandler)
        thread = threading.Thread(target=oidc_server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(oidc_server.server_close)
        self.addCleanup(oidc_server.shutdown)
        token_endpoint = f"http://127.0.0.1:{oidc_server.server_address[1]}/token"

        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)
        configured = client.post(
            "/api/retrieval/policies/identity-provider/upsert",
            json={
                "provider": "oidc",
                "enabled": True,
                "issuer": "https://login.example.test/",
                "audience": "rag-console",
                "jwks_url": "https://login.example.test/.well-known/jwks.json",
                "authorization_endpoint": "https://login.example.test/oauth2/v1/authorize",
                "token_endpoint": token_endpoint,
                "client_id": "rag-console-client",
                "client_secret_env": "RAG_OIDC_CLIENT_SECRET",
                "redirect_uri": "http://127.0.0.1:8766/oidc/callback",
                "scopes": ["openid", "email", "profile", "groups"],
                "client_secret": "must-not-be-stored",
            },
        )
        self.assertEqual(configured.status_code, 200)
        identity_provider = configured.json()["identity_provider"]
        self.assertEqual(identity_provider["authorization_endpoint"], "https://login.example.test/oauth2/v1/authorize")
        self.assertEqual(identity_provider["token_endpoint"], token_endpoint)
        self.assertEqual(identity_provider["client_id"], "rag-console-client")
        self.assertEqual(identity_provider["client_secret_env"], "RAG_OIDC_CLIENT_SECRET")
        self.assertEqual(identity_provider["redirect_uri"], "http://127.0.0.1:8766/oidc/callback")
        self.assertEqual(identity_provider["scopes"], ["openid", "email", "profile", "groups"])

        login = client.post(
            "/api/retrieval/policies/identity-provider/login-url",
            json={"redirect_uri": "http://127.0.0.1:8766/oidc/callback"},
        )
        self.assertEqual(login.status_code, 200)
        login_payload = login.json()
        parsed = urllib.parse.urlparse(login_payload["authorization_url"])
        params = urllib.parse.parse_qs(parsed.query)
        self.assertEqual(f"{parsed.scheme}://{parsed.netloc}{parsed.path}", "https://login.example.test/oauth2/v1/authorize")
        self.assertEqual(params["client_id"], ["rag-console-client"])
        self.assertEqual(params["redirect_uri"], ["http://127.0.0.1:8766/oidc/callback"])
        self.assertEqual(params["response_type"], ["code"])
        self.assertEqual(params["scope"], ["openid email profile groups"])
        self.assertEqual(params["code_challenge_method"], ["S256"])
        self.assertEqual(params["code_challenge"], [login_payload["code_challenge"]])
        self.assertTrue(login_payload["state"])
        self.assertTrue(login_payload["nonce"])
        self.assertTrue(login_payload["code_verifier"])
        self.assertNotIn("client_secret", login_payload)

        with patch.dict("os.environ", {"RAG_OIDC_CLIENT_SECRET": "env-secret"}, clear=False):
            exchanged = client.post(
                "/api/retrieval/policies/identity-provider/token",
                json={
                    "code": "authorization-code",
                    "code_verifier": login_payload["code_verifier"],
                    "redirect_uri": "http://127.0.0.1:8766/oidc/callback",
                },
            )
        self.assertEqual(exchanged.status_code, 200)
        self.assertEqual(exchanged.json()["access_token"], "access-token-from-idp")
        self.assertEqual(exchanged.json()["id_token"], "id-token-from-idp")
        self.assertEqual(exchanged.json()["refresh_token"], "refresh-token-from-idp")
        self.assertEqual(captured_token_request["grant_type"], "authorization_code")
        self.assertEqual(captured_token_request["client_id"], "rag-console-client")
        self.assertEqual(captured_token_request["client_secret"], "env-secret")
        self.assertEqual(captured_token_request["code"], "authorization-code")
        self.assertEqual(captured_token_request["code_verifier"], login_payload["code_verifier"])
        self.assertEqual(captured_token_request["redirect_uri"], "http://127.0.0.1:8766/oidc/callback")

        saved_policy = orjson.loads((self.persist_dir / "retrieval_policies.json").read_bytes())
        serialized_policy = orjson.dumps(saved_policy).decode("utf-8")
        self.assertNotIn("must-not-be-stored", serialized_policy)
        self.assertIn("RAG_OIDC_CLIENT_SECRET", serialized_policy)

    def test_api_oidc_callback_exchanges_code_and_creates_session_cookie(self) -> None:
        import base64
        import time
        import urllib.parse

        import jwt
        from cryptography.hazmat.primitives.asymmetric import rsa

        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public_numbers = private_key.public_key().public_numbers()

        def b64url_int(value: int) -> str:
            raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
            return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

        jwks = {
            "keys": [
                {
                    "kty": "RSA",
                    "use": "sig",
                    "kid": "callback-oidc-key",
                    "alg": "RS256",
                    "n": b64url_int(public_numbers.n),
                    "e": b64url_int(public_numbers.e),
                }
            ]
        }
        captured_token_request: dict[str, str] = {}

        class OidcHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 - stdlib handler hook
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(orjson.dumps(jwks))

            def do_POST(self) -> None:  # noqa: N802 - stdlib handler hook
                raw_body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                captured_token_request.update(
                    {
                        key: values[-1]
                        for key, values in urllib.parse.parse_qs(raw_body.decode("utf-8")).items()
                    }
                )
                now = int(time.time())
                id_token = jwt.encode(
                    {
                        "iss": "https://callback-idp.example.test/",
                        "aud": "rag-console-callback",
                        "sub": "callback-user",
                        "email": "callback-user@example.com",
                        "groups": ["RAG Reviewers"],
                        "exp": now + 300,
                        "iat": now,
                    },
                    private_key,
                    algorithm="RS256",
                    headers={"kid": "callback-oidc-key"},
                )
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(
                    orjson.dumps(
                        {
                            "access_token": "callback-access-token",
                            "id_token": id_token,
                            "token_type": "Bearer",
                            "expires_in": 300,
                        }
                    )
                )

            def log_message(self, *_: object) -> None:
                return

        oidc_server = HTTPServer(("127.0.0.1", 0), OidcHandler)
        thread = threading.Thread(target=oidc_server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(oidc_server.server_close)
        self.addCleanup(oidc_server.shutdown)
        oidc_base = f"http://127.0.0.1:{oidc_server.server_address[1]}"

        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)
        configured = client.post(
            "/api/retrieval/policies/identity-provider/upsert",
            json={
                "provider": "oidc",
                "enabled": True,
                "issuer": "https://callback-idp.example.test/",
                "audience": "rag-console-callback",
                "jwks_url": f"{oidc_base}/jwks.json",
                "authorization_endpoint": "https://callback-idp.example.test/oauth2/v1/authorize",
                "token_endpoint": f"{oidc_base}/token",
                "client_id": "rag-console-callback-client",
                "redirect_uri": "http://127.0.0.1:8766/api/retrieval/policies/identity-provider/callback",
                "scopes": ["openid", "email", "profile"],
            },
        )
        self.assertEqual(configured.status_code, 200)

        login = client.post(
            "/api/retrieval/policies/identity-provider/login-url",
            json={
                "redirect_uri": "http://127.0.0.1:8766/api/retrieval/policies/identity-provider/callback"
            },
        )
        self.assertEqual(login.status_code, 200)
        self.assertIn("HttpOnly", login.headers.get("set-cookie", ""))
        state = login.json()["state"]

        callback = client.get(
            "/api/retrieval/policies/identity-provider/callback",
            params={"code": "callback-code", "state": state},
        )
        self.assertEqual(callback.status_code, 200)
        self.assertIn("HttpOnly", callback.headers.get("set-cookie", ""))
        self.assertEqual(callback.json()["subject"], "callback-user@example.com")
        self.assertEqual(callback.json()["identity_source"], "oidc_session")
        self.assertEqual(captured_token_request["grant_type"], "authorization_code")
        self.assertEqual(captured_token_request["client_id"], "rag-console-callback-client")
        self.assertEqual(captured_token_request["code"], "callback-code")
        self.assertEqual(
            captured_token_request["redirect_uri"],
            "http://127.0.0.1:8766/api/retrieval/policies/identity-provider/callback",
        )
        self.assertTrue(captured_token_request["code_verifier"])

        proposal = client.post(
            "/api/retrieval/policies/propose",
            json={
                "collection": "callback-session-demo",
                "settings": {"query_rewrite": True},
                "reviewer": "attacker@example.com",
                "reviewer_role": "owner",
            },
        )
        self.assertEqual(proposal.status_code, 200)
        self.assertEqual(proposal.json()["proposal"]["reviewer"], "callback-user@example.com")

    def test_api_refreshes_oidc_session_with_server_side_refresh_token(self) -> None:
        import base64
        import time
        import urllib.parse

        import jwt
        from cryptography.hazmat.primitives.asymmetric import rsa

        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public_numbers = private_key.public_key().public_numbers()

        def b64url_int(value: int) -> str:
            raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
            return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

        def issue_token(groups: list[str]) -> str:
            now = int(time.time())
            return jwt.encode(
                {
                    "iss": "https://refresh-idp.example.test/",
                    "aud": "rag-console-refresh",
                    "sub": "refresh-user",
                    "email": "refresh-user@example.com",
                    "groups": groups,
                    "exp": now + 300,
                    "iat": now,
                },
                private_key,
                algorithm="RS256",
                headers={"kid": "refresh-oidc-key"},
            )

        jwks = {
            "keys": [
                {
                    "kty": "RSA",
                    "use": "sig",
                    "kid": "refresh-oidc-key",
                    "alg": "RS256",
                    "n": b64url_int(public_numbers.n),
                    "e": b64url_int(public_numbers.e),
                }
            ]
        }
        captured_token_requests: list[dict[str, str]] = []

        class OidcHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 - stdlib handler hook
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(orjson.dumps(jwks))

            def do_POST(self) -> None:  # noqa: N802 - stdlib handler hook
                raw_body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                form = {
                    key: values[-1]
                    for key, values in urllib.parse.parse_qs(raw_body.decode("utf-8")).items()
                }
                captured_token_requests.append(form)
                grant_type = form.get("grant_type")
                if grant_type == "authorization_code":
                    body = {
                        "access_token": "initial-access-token",
                        "id_token": issue_token(["RAG Reviewers"]),
                        "token_type": "Bearer",
                        "expires_in": 300,
                        "refresh_token": "server-refresh-token",
                    }
                elif grant_type == "refresh_token":
                    body = {
                        "access_token": "refreshed-access-token",
                        "id_token": issue_token(["RAG Reviewers", "RAG Approvers"]),
                        "token_type": "Bearer",
                        "expires_in": 600,
                        "refresh_token": "rotated-refresh-token",
                    }
                else:
                    self.send_response(400)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(orjson.dumps(body))

            def log_message(self, *_: object) -> None:
                return

        oidc_server = HTTPServer(("127.0.0.1", 0), OidcHandler)
        thread = threading.Thread(target=oidc_server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(oidc_server.server_close)
        self.addCleanup(oidc_server.shutdown)
        oidc_base = f"http://127.0.0.1:{oidc_server.server_address[1]}"

        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)
        configured = client.post(
            "/api/retrieval/policies/identity-provider/upsert",
            json={
                "provider": "oidc",
                "enabled": True,
                "issuer": "https://refresh-idp.example.test/",
                "audience": "rag-console-refresh",
                "jwks_url": f"{oidc_base}/jwks.json",
                "authorization_endpoint": "https://refresh-idp.example.test/oauth2/v1/authorize",
                "token_endpoint": f"{oidc_base}/token",
                "client_id": "rag-console-refresh-client",
                "client_secret_env": "RAG_REFRESH_CLIENT_SECRET",
                "redirect_uri": "http://127.0.0.1:8766/api/retrieval/policies/identity-provider/callback",
                "scopes": ["openid", "email", "profile"],
            },
        )
        self.assertEqual(configured.status_code, 200)

        login = client.post(
            "/api/retrieval/policies/identity-provider/login-url",
            json={
                "redirect_uri": "http://127.0.0.1:8766/api/retrieval/policies/identity-provider/callback"
            },
        )
        self.assertEqual(login.status_code, 200)

        with patch.dict("os.environ", {"RAG_REFRESH_CLIENT_SECRET": "refresh-client-secret"}, clear=False):
            callback = client.get(
                "/api/retrieval/policies/identity-provider/callback",
                params={"code": "refresh-code", "state": login.json()["state"]},
            )
            self.assertEqual(callback.status_code, 200)
            refreshed = client.post("/api/retrieval/policies/identity-provider/session/refresh")

        self.assertEqual(refreshed.status_code, 200, refreshed.text)
        refreshed_payload = refreshed.json()
        self.assertEqual(refreshed_payload["subject"], "refresh-user@example.com")
        self.assertEqual(refreshed_payload["groups"], ["RAG Reviewers", "RAG Approvers"])
        self.assertEqual(refreshed_payload["identity_source"], "oidc_session")
        self.assertTrue(refreshed_payload["refreshed"])
        self.assertNotIn("refresh_token", refreshed_payload)
        self.assertIn("HttpOnly", refreshed.headers.get("set-cookie", ""))

        self.assertEqual(captured_token_requests[0]["grant_type"], "authorization_code")
        self.assertEqual(captured_token_requests[1]["grant_type"], "refresh_token")
        self.assertEqual(captured_token_requests[1]["refresh_token"], "server-refresh-token")
        self.assertEqual(captured_token_requests[1]["client_id"], "rag-console-refresh-client")
        self.assertEqual(captured_token_requests[1]["client_secret"], "refresh-client-secret")

        sessions = orjson.loads((self.persist_dir / "retrieval_policy_sessions.json").read_bytes())
        self.assertEqual(len(sessions), 1)
        record = next(iter(sessions.values()))
        self.assertEqual(record["refresh_token"], "rotated-refresh-token")
        self.assertEqual(record["groups"], ["RAG Reviewers", "RAG Approvers"])
        self.assertEqual(record["token_type"], "Bearer")
        self.assertGreater(record["token_expires_at"], int(time.time()))

    def test_api_encrypts_oidc_session_refresh_token_and_reencrypts_with_active_key(self) -> None:
        import base64
        import time
        import urllib.parse

        import jwt
        from cryptography.hazmat.primitives.asymmetric import rsa

        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public_numbers = private_key.public_key().public_numbers()

        def b64url_int(value: int) -> str:
            raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
            return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

        def b64url_key(raw: bytes) -> str:
            return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

        def issue_token(groups: list[str]) -> str:
            now = int(time.time())
            return jwt.encode(
                {
                    "iss": "https://encrypted-refresh-idp.example.test/",
                    "aud": "rag-console-encrypted-refresh",
                    "sub": "encrypted-refresh-user",
                    "email": "encrypted-refresh-user@example.com",
                    "groups": groups,
                    "exp": now + 300,
                    "iat": now,
                },
                private_key,
                algorithm="RS256",
                headers={"kid": "encrypted-refresh-oidc-key"},
            )

        jwks = {
            "keys": [
                {
                    "kty": "RSA",
                    "use": "sig",
                    "kid": "encrypted-refresh-oidc-key",
                    "alg": "RS256",
                    "n": b64url_int(public_numbers.n),
                    "e": b64url_int(public_numbers.e),
                }
            ]
        }
        captured_token_requests: list[dict[str, str]] = []

        class OidcHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 - stdlib handler hook
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(orjson.dumps(jwks))

            def do_POST(self) -> None:  # noqa: N802 - stdlib handler hook
                raw_body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                form = {
                    key: values[-1]
                    for key, values in urllib.parse.parse_qs(raw_body.decode("utf-8")).items()
                }
                captured_token_requests.append(form)
                if form.get("grant_type") == "authorization_code":
                    body = {
                        "access_token": "encrypted-initial-access-token",
                        "id_token": issue_token(["RAG Reviewers"]),
                        "token_type": "Bearer",
                        "expires_in": 300,
                        "refresh_token": "encrypted-server-refresh-token",
                    }
                elif form.get("grant_type") == "refresh_token":
                    body = {
                        "access_token": "encrypted-refreshed-access-token",
                        "id_token": issue_token(["RAG Reviewers", "RAG Approvers"]),
                        "token_type": "Bearer",
                        "expires_in": 600,
                        "refresh_token": "encrypted-rotated-refresh-token",
                    }
                else:
                    self.send_response(400)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(orjson.dumps(body))

            def log_message(self, *_: object) -> None:
                return

        oidc_server = HTTPServer(("127.0.0.1", 0), OidcHandler)
        thread = threading.Thread(target=oidc_server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(oidc_server.server_close)
        self.addCleanup(oidc_server.shutdown)
        oidc_base = f"http://127.0.0.1:{oidc_server.server_address[1]}"

        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)
        configured = client.post(
            "/api/retrieval/policies/identity-provider/upsert",
            json={
                "provider": "oidc",
                "enabled": True,
                "issuer": "https://encrypted-refresh-idp.example.test/",
                "audience": "rag-console-encrypted-refresh",
                "jwks_url": f"{oidc_base}/jwks.json",
                "authorization_endpoint": "https://encrypted-refresh-idp.example.test/oauth2/v1/authorize",
                "token_endpoint": f"{oidc_base}/token",
                "client_id": "rag-console-encrypted-refresh-client",
                "client_secret_env": "RAG_ENCRYPTED_REFRESH_CLIENT_SECRET",
                "redirect_uri": "http://127.0.0.1:8766/api/retrieval/policies/identity-provider/callback",
                "scopes": ["openid", "email", "profile"],
            },
        )
        self.assertEqual(configured.status_code, 200)

        login = client.post(
            "/api/retrieval/policies/identity-provider/login-url",
            json={
                "redirect_uri": "http://127.0.0.1:8766/api/retrieval/policies/identity-provider/callback"
            },
        )
        self.assertEqual(login.status_code, 200)

        old_key = b64url_key(b"1" * 32)
        new_key = b64url_key(b"2" * 32)
        with patch.dict(
            "os.environ",
            {
                "RAG_POLICY_SESSION_SECRET_KEYS": f"old:{old_key}",
                "RAG_ENCRYPTED_REFRESH_CLIENT_SECRET": "encrypted-refresh-client-secret",
            },
            clear=False,
        ):
            callback = client.get(
                "/api/retrieval/policies/identity-provider/callback",
                params={"code": "encrypted-refresh-code", "state": login.json()["state"]},
            )
        self.assertEqual(callback.status_code, 200)
        raw_session_file = (self.persist_dir / "retrieval_policy_sessions.json").read_text(encoding="utf-8")
        self.assertNotIn("encrypted-server-refresh-token", raw_session_file)
        created_sessions = orjson.loads(raw_session_file.encode("utf-8"))
        created_record = next(iter(created_sessions.values()))
        self.assertNotIn("refresh_token", created_record)
        self.assertEqual(created_record["refresh_token_encrypted"]["kid"], "old")
        self.assertEqual(created_record["refresh_token_encrypted"]["alg"], "AESGCM")

        with patch.dict(
            "os.environ",
            {
                "RAG_POLICY_SESSION_SECRET_KEYS": f"new:{new_key},old:{old_key}",
                "RAG_ENCRYPTED_REFRESH_CLIENT_SECRET": "encrypted-refresh-client-secret",
            },
            clear=False,
        ):
            refreshed = client.post("/api/retrieval/policies/identity-provider/session/refresh")

        self.assertEqual(refreshed.status_code, 200, refreshed.text)
        self.assertEqual(captured_token_requests[1]["grant_type"], "refresh_token")
        self.assertEqual(captured_token_requests[1]["refresh_token"], "encrypted-server-refresh-token")

        rotated_raw_session_file = (self.persist_dir / "retrieval_policy_sessions.json").read_text(encoding="utf-8")
        self.assertNotIn("encrypted-server-refresh-token", rotated_raw_session_file)
        self.assertNotIn("encrypted-rotated-refresh-token", rotated_raw_session_file)
        rotated_sessions = orjson.loads(rotated_raw_session_file.encode("utf-8"))
        rotated_record = next(iter(rotated_sessions.values()))
        self.assertNotIn("refresh_token", rotated_record)
        self.assertEqual(rotated_record["refresh_token_encrypted"]["kid"], "new")
        self.assertEqual(rotated_record["groups"], ["RAG Reviewers", "RAG Approvers"])

    def test_api_admin_rotates_existing_oidc_session_refresh_token_encryption_key(self) -> None:
        import base64
        import time
        import urllib.parse

        import jwt
        from cryptography.hazmat.primitives.asymmetric import rsa

        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public_numbers = private_key.public_key().public_numbers()

        def b64url_int(value: int) -> str:
            raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
            return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

        def b64url_key(raw: bytes) -> str:
            return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

        def issue_token(email: str, groups: list[str]) -> str:
            now = int(time.time())
            return jwt.encode(
                {
                    "iss": "https://rotate-key-idp.example.test/",
                    "aud": "rag-console-rotate-key",
                    "sub": email,
                    "email": email,
                    "groups": groups,
                    "exp": now + 300,
                    "iat": now,
                },
                private_key,
                algorithm="RS256",
                headers={"kid": "rotate-key-oidc-key"},
            )

        jwks = {
            "keys": [
                {
                    "kty": "RSA",
                    "use": "sig",
                    "kid": "rotate-key-oidc-key",
                    "alg": "RS256",
                    "n": b64url_int(public_numbers.n),
                    "e": b64url_int(public_numbers.e),
                }
            ]
        }
        captured_token_requests: list[dict[str, str]] = []

        class OidcHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 - stdlib handler hook
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(orjson.dumps(jwks))

            def do_POST(self) -> None:  # noqa: N802 - stdlib handler hook
                raw_body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                form = {
                    key: values[-1]
                    for key, values in urllib.parse.parse_qs(raw_body.decode("utf-8")).items()
                }
                captured_token_requests.append(form)
                if form.get("grant_type") == "authorization_code":
                    body = {
                        "access_token": "rotate-initial-access-token",
                        "id_token": issue_token("rotate-user@example.com", ["RAG Reviewers"]),
                        "token_type": "Bearer",
                        "expires_in": 300,
                        "refresh_token": "rotate-key-refresh-token",
                    }
                elif form.get("grant_type") == "refresh_token":
                    body = {
                        "access_token": "rotate-refreshed-access-token",
                        "id_token": issue_token("rotate-user@example.com", ["RAG Reviewers"]),
                        "token_type": "Bearer",
                        "expires_in": 300,
                        "refresh_token": "rotate-key-refresh-token-2",
                    }
                else:
                    self.send_response(400)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(orjson.dumps(body))

            def log_message(self, *_: object) -> None:
                return

        oidc_server = HTTPServer(("127.0.0.1", 0), OidcHandler)
        thread = threading.Thread(target=oidc_server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(oidc_server.server_close)
        self.addCleanup(oidc_server.shutdown)
        oidc_base = f"http://127.0.0.1:{oidc_server.server_address[1]}"

        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)
        configured = client.post(
            "/api/retrieval/policies/identity-provider/upsert",
            json={
                "provider": "oidc",
                "enabled": True,
                "issuer": "https://rotate-key-idp.example.test/",
                "audience": "rag-console-rotate-key",
                "jwks_url": f"{oidc_base}/jwks.json",
                "authorization_endpoint": "https://rotate-key-idp.example.test/oauth2/v1/authorize",
                "token_endpoint": f"{oidc_base}/token",
                "client_id": "rag-console-rotate-key-client",
                "redirect_uri": "http://127.0.0.1:8766/api/retrieval/policies/identity-provider/callback",
                "scopes": ["openid", "email", "profile"],
            },
        )
        self.assertEqual(configured.status_code, 200)
        admin_role = client.post(
            "/api/retrieval/policies/roles/upsert",
            json={
                "subject": "rotate-admin@example.com",
                "roles": ["admin"],
                "updated_by": "bootstrap",
            },
        )
        self.assertEqual(admin_role.status_code, 200)

        login = client.post(
            "/api/retrieval/policies/identity-provider/login-url",
            json={
                "redirect_uri": "http://127.0.0.1:8766/api/retrieval/policies/identity-provider/callback"
            },
        )
        self.assertEqual(login.status_code, 200)

        old_key = b64url_key(b"a" * 32)
        new_key = b64url_key(b"b" * 32)
        with patch.dict("os.environ", {"RAG_POLICY_SESSION_SECRET_KEYS": f"old:{old_key}"}, clear=False):
            callback = client.get(
                "/api/retrieval/policies/identity-provider/callback",
                params={"code": "rotate-code", "state": login.json()["state"]},
            )
        self.assertEqual(callback.status_code, 200)
        before_sessions = orjson.loads((self.persist_dir / "retrieval_policy_sessions.json").read_bytes())
        session_id = next(iter(before_sessions))
        self.assertEqual(before_sessions[session_id]["refresh_token_encrypted"]["kid"], "old")

        admin_token = issue_token("rotate-admin@example.com", ["Tenant Admins"])
        with patch.dict("os.environ", {"RAG_POLICY_SESSION_SECRET_KEYS": f"new:{new_key},old:{old_key}"}, clear=False):
            rotated = client.post(
                "/api/retrieval/policies/identity-provider/sessions/rotate-key",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        self.assertEqual(rotated.status_code, 200, rotated.text)
        rotated_payload = rotated.json()
        self.assertEqual(rotated_payload["rotated_count"], 1)
        self.assertEqual(rotated_payload["active_key_id"], "new")
        serialized_payload = orjson.dumps(rotated_payload).decode("utf-8")
        self.assertNotIn("rotate-key-refresh-token", serialized_payload)
        self.assertNotIn("ciphertext", serialized_payload)

        after_sessions = orjson.loads((self.persist_dir / "retrieval_policy_sessions.json").read_bytes())
        self.assertEqual(after_sessions[session_id]["refresh_token_encrypted"]["kid"], "new")
        serialized_sessions = orjson.dumps(after_sessions).decode("utf-8")
        self.assertNotIn("rotate-key-refresh-token", serialized_sessions)

        with patch.dict("os.environ", {"RAG_POLICY_SESSION_SECRET_KEYS": f"new:{new_key}"}, clear=False):
            refreshed = client.post("/api/retrieval/policies/identity-provider/session/refresh")
        self.assertEqual(refreshed.status_code, 200, refreshed.text)
        self.assertEqual(captured_token_requests[-1]["grant_type"], "refresh_token")
        self.assertEqual(captured_token_requests[-1]["refresh_token"], "rotate-key-refresh-token")

    def test_api_admin_lists_and_revokes_oidc_policy_sessions_without_secret_leakage(self) -> None:
        import base64
        import time

        import jwt
        from cryptography.hazmat.primitives.asymmetric import rsa

        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public_numbers = private_key.public_key().public_numbers()

        def b64url_int(value: int) -> str:
            raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
            return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

        def issue_token(email: str, groups: list[str]) -> str:
            now = int(time.time())
            return jwt.encode(
                {
                    "iss": "https://session-admin-idp.example.test/",
                    "aud": "rag-console-session-admin",
                    "sub": email,
                    "email": email,
                    "groups": groups,
                    "exp": now + 300,
                    "iat": now,
                },
                private_key,
                algorithm="RS256",
                headers={"kid": "session-admin-oidc-key"},
            )

        jwks = {
            "keys": [
                {
                    "kty": "RSA",
                    "use": "sig",
                    "kid": "session-admin-oidc-key",
                    "alg": "RS256",
                    "n": b64url_int(public_numbers.n),
                    "e": b64url_int(public_numbers.e),
                }
            ]
        }

        class JwksHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 - stdlib handler hook
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(orjson.dumps(jwks))

            def log_message(self, *_: object) -> None:
                return

        jwks_server = HTTPServer(("127.0.0.1", 0), JwksHandler)
        thread = threading.Thread(target=jwks_server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(jwks_server.server_close)
        self.addCleanup(jwks_server.shutdown)

        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)
        configured = client.post(
            "/api/retrieval/policies/identity-provider/upsert",
            json={
                "provider": "oidc",
                "enabled": True,
                "issuer": "https://session-admin-idp.example.test/",
                "audience": "rag-console-session-admin",
                "jwks_url": f"http://127.0.0.1:{jwks_server.server_address[1]}/jwks.json",
                "subject_claim": "email",
                "groups_claim": "groups",
                "algorithms": ["RS256"],
            },
        )
        self.assertEqual(configured.status_code, 200)
        admin_role = client.post(
            "/api/retrieval/policies/roles/upsert",
            json={
                "subject": "tenant-admin@example.com",
                "roles": ["admin"],
                "updated_by": "bootstrap",
                "note": "tenant session administrator",
            },
        )
        self.assertEqual(admin_role.status_code, 200)

        user_token = issue_token("session-user@example.com", ["RAG Reviewers"])
        session = client.post(
            "/api/retrieval/policies/identity-provider/session",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        self.assertEqual(session.status_code, 200)
        sessions = orjson.loads((self.persist_dir / "retrieval_policy_sessions.json").read_bytes())
        session_id = next(iter(sessions))
        sessions[session_id]["refresh_token"] = "must-not-leak-refresh-token"
        sessions[session_id]["refresh_token_encrypted"] = {
            "alg": "AESGCM",
            "kid": "old",
            "nonce": "must-not-leak-nonce",
            "ciphertext": "must-not-leak-ciphertext",
        }
        (self.persist_dir / "retrieval_policy_sessions.json").write_bytes(orjson.dumps(sessions, option=orjson.OPT_INDENT_2))

        reviewer_token = issue_token("ordinary-reviewer@example.com", ["RAG Reviewers"])
        blocked = client.get(
            "/api/retrieval/policies/identity-provider/sessions",
            headers={"Authorization": f"Bearer {reviewer_token}"},
        )
        self.assertEqual(blocked.status_code, 403)

        admin_token = issue_token("tenant-admin@example.com", ["Tenant Admins"])
        listed = client.get(
            "/api/retrieval/policies/identity-provider/sessions",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        self.assertEqual(listed.status_code, 200, listed.text)
        listed_payload = listed.json()
        self.assertEqual(listed_payload["session_count"], 1)
        self.assertEqual(listed_payload["sessions"][0]["session_id"], session_id)
        self.assertEqual(listed_payload["sessions"][0]["subject"], "session-user@example.com")
        self.assertTrue(listed_payload["sessions"][0]["has_refresh_token"])
        serialized_list = orjson.dumps(listed_payload).decode("utf-8")
        self.assertNotIn("must-not-leak-refresh-token", serialized_list)
        self.assertNotIn("must-not-leak-ciphertext", serialized_list)
        self.assertNotIn("refresh_token_encrypted", serialized_list)

        revoked = client.delete(
            f"/api/retrieval/policies/identity-provider/sessions/{session_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        self.assertEqual(revoked.status_code, 200, revoked.text)
        self.assertEqual(revoked.json()["revoked_session_id"], session_id)

        rejected = client.post(
            "/api/retrieval/policies/propose",
            json={
                "collection": "session-admin-demo",
                "settings": {"query_rewrite": True},
                "reviewer": "session-user@example.com",
                "reviewer_role": "reviewer",
            },
        )
        self.assertEqual(rejected.status_code, 401)

    def test_api_audits_oidc_session_revoke_and_key_rotation_without_secret_leakage(self) -> None:
        import base64
        from datetime import datetime, timedelta
        import time

        import jwt
        from cryptography.hazmat.primitives.asymmetric import rsa

        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public_numbers = private_key.public_key().public_numbers()

        def b64url_int(value: int) -> str:
            raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
            return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

        def b64url_key(raw: bytes) -> str:
            return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

        def issue_token(email: str, groups: list[str]) -> str:
            now = int(time.time())
            return jwt.encode(
                {
                    "iss": "https://session-audit-idp.example.test/",
                    "aud": "rag-console-session-audit",
                    "sub": email,
                    "email": email,
                    "groups": groups,
                    "exp": now + 300,
                    "iat": now,
                },
                private_key,
                algorithm="RS256",
                headers={"kid": "session-audit-oidc-key"},
            )

        jwks = {
            "keys": [
                {
                    "kty": "RSA",
                    "use": "sig",
                    "kid": "session-audit-oidc-key",
                    "alg": "RS256",
                    "n": b64url_int(public_numbers.n),
                    "e": b64url_int(public_numbers.e),
                }
            ]
        }

        class JwksHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 - stdlib handler hook
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(orjson.dumps(jwks))

            def log_message(self, *_: object) -> None:
                return

        jwks_server = HTTPServer(("127.0.0.1", 0), JwksHandler)
        thread = threading.Thread(target=jwks_server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(jwks_server.server_close)
        self.addCleanup(jwks_server.shutdown)

        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)
        configured = client.post(
            "/api/retrieval/policies/identity-provider/upsert",
            json={
                "provider": "oidc",
                "enabled": True,
                "issuer": "https://session-audit-idp.example.test/",
                "audience": "rag-console-session-audit",
                "jwks_url": f"http://127.0.0.1:{jwks_server.server_address[1]}/jwks.json",
                "subject_claim": "email",
                "groups_claim": "groups",
                "algorithms": ["RS256"],
            },
        )
        self.assertEqual(configured.status_code, 200)
        admin_role = client.post(
            "/api/retrieval/policies/roles/upsert",
            json={
                "subject": "audit-admin@example.com",
                "roles": ["admin"],
                "updated_by": "bootstrap",
            },
        )
        self.assertEqual(admin_role.status_code, 200)

        user_token = issue_token("audit-user@example.com", ["RAG Reviewers"])
        created = client.post(
            "/api/retrieval/policies/identity-provider/session",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        self.assertEqual(created.status_code, 200, created.text)
        sessions = orjson.loads((self.persist_dir / "retrieval_policy_sessions.json").read_bytes())
        session_id = next(iter(sessions))
        sessions[session_id]["refresh_token"] = "audit-refresh-token"
        (self.persist_dir / "retrieval_policy_sessions.json").write_bytes(
            orjson.dumps(sessions, option=orjson.OPT_INDENT_2)
        )

        admin_token = issue_token("audit-admin@example.com", ["Tenant Admins"])
        new_key = b64url_key(b"z" * 32)
        with patch.dict("os.environ", {"RAG_POLICY_SESSION_SECRET_KEYS": f"new:{new_key}"}, clear=False):
            rotated = client.post(
                "/api/retrieval/policies/identity-provider/sessions/rotate-key",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        self.assertEqual(rotated.status_code, 200, rotated.text)
        self.assertEqual(rotated.json()["active_key_id"], "new")
        self.assertEqual(rotated.json()["rotated_count"], 1)

        revoked = client.delete(
            f"/api/retrieval/policies/identity-provider/sessions/{session_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        self.assertEqual(revoked.status_code, 200, revoked.text)
        self.assertTrue(revoked.json()["revoked"])

        policy = orjson.loads((self.persist_dir / "retrieval_policies.json").read_bytes())
        audit = policy.get("audit", [])
        rotate_entries = [
            entry
            for entry in audit
            if isinstance(entry, dict) and entry.get("action") == "identity_provider_session_key_rotate"
        ]
        revoke_entries = [
            entry
            for entry in audit
            if isinstance(entry, dict) and entry.get("action") == "identity_provider_session_revoke"
        ]
        self.assertTrue(rotate_entries)
        self.assertTrue(revoke_entries)
        rotate_entry = rotate_entries[-1]
        self.assertEqual(rotate_entry["admin"], "audit-admin@example.com")
        self.assertEqual(rotate_entry["admin_role"], "admin")
        self.assertEqual(rotate_entry["role_source"], "role_registry")
        self.assertEqual(rotate_entry["active_key_id"], "new")
        self.assertEqual(rotate_entry["rotated_count"], 1)
        self.assertEqual(rotate_entry["rotated_session_ids"], [session_id])
        revoke_entry = revoke_entries[-1]
        self.assertEqual(revoke_entry["admin"], "audit-admin@example.com")
        self.assertEqual(revoke_entry["role_source"], "role_registry")
        self.assertEqual(revoke_entry["revoked_session_id"], session_id)
        self.assertTrue(revoke_entry["revoked"])
        serialized_audit = orjson.dumps(audit).decode("utf-8")
        self.assertNotIn("audit-refresh-token", serialized_audit)
        self.assertNotIn("refresh_token_encrypted", serialized_audit)
        self.assertNotIn("ciphertext", serialized_audit)

    def test_api_reports_oidc_session_key_status_without_secret_leakage(self) -> None:
        import base64
        from datetime import datetime, timedelta
        import time

        import jwt
        from cryptography.hazmat.primitives.asymmetric import rsa

        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public_numbers = private_key.public_key().public_numbers()

        def b64url_int(value: int) -> str:
            raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
            return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

        def b64url_key(raw: bytes) -> str:
            return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

        def issue_token(email: str, groups: list[str]) -> str:
            now = int(time.time())
            return jwt.encode(
                {
                    "iss": "https://session-key-status-idp.example.test/",
                    "aud": "rag-console-session-key-status",
                    "sub": email,
                    "email": email,
                    "groups": groups,
                    "exp": now + 300,
                    "iat": now,
                },
                private_key,
                algorithm="RS256",
                headers={"kid": "session-key-status-oidc-key"},
            )

        jwks = {
            "keys": [
                {
                    "kty": "RSA",
                    "use": "sig",
                    "kid": "session-key-status-oidc-key",
                    "alg": "RS256",
                    "n": b64url_int(public_numbers.n),
                    "e": b64url_int(public_numbers.e),
                }
            ]
        }

        class JwksHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 - stdlib handler hook
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(orjson.dumps(jwks))

            def log_message(self, *_: object) -> None:
                return

        jwks_server = HTTPServer(("127.0.0.1", 0), JwksHandler)
        thread = threading.Thread(target=jwks_server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(jwks_server.server_close)
        self.addCleanup(jwks_server.shutdown)

        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)
        configured = client.post(
            "/api/retrieval/policies/identity-provider/upsert",
            json={
                "provider": "oidc",
                "enabled": True,
                "issuer": "https://session-key-status-idp.example.test/",
                "audience": "rag-console-session-key-status",
                "jwks_url": f"http://127.0.0.1:{jwks_server.server_address[1]}/jwks.json",
                "subject_claim": "email",
                "groups_claim": "groups",
                "algorithms": ["RS256"],
            },
        )
        self.assertEqual(configured.status_code, 200)
        admin_role = client.post(
            "/api/retrieval/policies/roles/upsert",
            json={
                "subject": "key-status-admin@example.com",
                "roles": ["admin"],
                "updated_by": "bootstrap",
            },
        )
        self.assertEqual(admin_role.status_code, 200)

        policy_path = self.persist_dir / "retrieval_policies.json"
        policy = orjson.loads(policy_path.read_bytes())
        policy.setdefault("audit", []).append(
            {
                "timestamp": (datetime.now() - timedelta(seconds=120)).isoformat(timespec="seconds"),
                "action": "identity_provider_session_key_rotate",
                "admin": "key-status-admin@example.com",
                "active_key_id": "old",
                "rotated_count": 1,
            }
        )
        policy_path.write_bytes(orjson.dumps(policy, option=orjson.OPT_INDENT_2))

        now = int(time.time())
        sessions = {
            "active-session": {
                "subject": "active@example.com",
                "expires_at": now + 600,
                "refresh_token_encrypted": {"alg": "AESGCM", "kid": "new", "nonce": "nonce", "ciphertext": "secret-ciphertext"},
            },
            "old-session": {
                "subject": "old@example.com",
                "expires_at": now + 600,
                "refresh_token_encrypted": {"alg": "AESGCM", "kid": "old", "nonce": "nonce", "ciphertext": "old-secret-ciphertext"},
            },
            "plain-session": {
                "subject": "plain@example.com",
                "expires_at": now + 600,
                "refresh_token": "legacy-refresh-token",
            },
            "missing-session": {
                "subject": "missing@example.com",
                "expires_at": now + 600,
            },
            "expired-session": {
                "subject": "expired@example.com",
                "expires_at": now - 1,
                "refresh_token": "expired-refresh-token",
            },
        }
        (self.persist_dir / "retrieval_policy_sessions.json").write_bytes(
            orjson.dumps(sessions, option=orjson.OPT_INDENT_2)
        )

        new_key = b64url_key(b"n" * 32)
        old_key = b64url_key(b"o" * 32)
        admin_token = issue_token("key-status-admin@example.com", ["Tenant Admins"])
        with patch.dict(
            "os.environ",
            {
                "RAG_POLICY_SESSION_SECRET_KEYS": f"new:{new_key},old:{old_key}",
                "RAG_POLICY_SESSION_KEY_MAX_AGE_SECONDS": "60",
            },
            clear=False,
        ):
            response = client.get(
                "/api/retrieval/policies/identity-provider/sessions/key-status",
                headers={"Authorization": f"Bearer {admin_token}"},
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["key_source"], "RAG_POLICY_SESSION_SECRET_KEYS")
        self.assertEqual(payload["active_key_id"], "new")
        self.assertEqual(payload["key_count"], 2)
        self.assertEqual(payload["active_encrypted_session_count"], 1)
        self.assertEqual(payload["stale_encrypted_session_count"], 1)
        self.assertEqual(payload["plain_refresh_session_count"], 1)
        self.assertEqual(payload["missing_refresh_session_count"], 1)
        self.assertEqual(payload["expired_pruned_count"], 1)
        self.assertTrue(payload["rotation_due"])
        self.assertEqual(payload["rotation_due_reasons"], ["last_rotation_exceeded_max_age", "stale_or_plain_sessions"])
        self.assertEqual(payload["last_rotation"]["active_key_id"], "old")
        self.assertEqual(payload["admin"], "key-status-admin@example.com")
        self.assertEqual(payload["role_source"], "role_registry")
        serialized_payload = orjson.dumps(payload).decode("utf-8")
        self.assertNotIn(new_key, serialized_payload)
        self.assertNotIn(old_key, serialized_payload)
        self.assertNotIn("legacy-refresh-token", serialized_payload)
        self.assertNotIn("secret-ciphertext", serialized_payload)
        self.assertNotIn("refresh_token_encrypted", serialized_payload)

    def test_api_uses_oidc_session_cookie_for_policy_approval(self) -> None:
        import base64
        import time

        import jwt
        from cryptography.hazmat.primitives.asymmetric import rsa

        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public_numbers = private_key.public_key().public_numbers()

        def b64url_int(value: int) -> str:
            raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
            return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

        jwks = {
            "keys": [
                {
                    "kty": "RSA",
                    "use": "sig",
                    "kid": "session-oidc-key",
                    "alg": "RS256",
                    "n": b64url_int(public_numbers.n),
                    "e": b64url_int(public_numbers.e),
                }
            ]
        }

        class JwksHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 - stdlib handler hook
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(orjson.dumps(jwks))

            def log_message(self, *_: object) -> None:
                return

        jwks_server = HTTPServer(("127.0.0.1", 0), JwksHandler)
        thread = threading.Thread(target=jwks_server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(jwks_server.server_close)
        self.addCleanup(jwks_server.shutdown)
        jwks_url = f"http://127.0.0.1:{jwks_server.server_address[1]}/jwks.json"

        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)
        configured = client.post(
            "/api/retrieval/policies/identity-provider/upsert",
            json={
                "provider": "oidc",
                "enabled": True,
                "issuer": "https://session-idp.example.test/",
                "audience": "rag-console-session",
                "jwks_url": jwks_url,
                "subject_claim": "email",
                "groups_claim": "groups",
                "algorithms": ["RS256"],
            },
        )
        self.assertEqual(configured.status_code, 200)

        synced = client.post(
            "/api/retrieval/policies/directory/sync",
            json={
                "source_type": "scim",
                "role_group_mappings": {
                    "RAG Approvers": {
                        "roles": ["approver"],
                        "assigned_collections": ["session-oidc-demo"],
                    }
                },
                "users": [
                    {
                        "id": "session-approver",
                        "userName": "session-approver@example.com",
                        "active": True,
                        "emails": [{"value": "session-approver@example.com", "primary": True}],
                    }
                ],
                "groups": [
                    {
                        "displayName": "RAG Approvers",
                        "members": [{"value": "session-approver"}],
                    }
                ],
            },
        )
        self.assertEqual(synced.status_code, 200)

        reviewer_token = jwt.encode(
            {
                "iss": "https://session-idp.example.test/",
                "aud": "rag-console-session",
                "sub": "session-reviewer",
                "email": "session-reviewer@example.com",
                "groups": ["RAG Reviewers"],
                "exp": int(time.time()) + 300,
                "iat": int(time.time()),
            },
            private_key,
            algorithm="RS256",
            headers={"kid": "session-oidc-key"},
        )
        session = client.post(
            "/api/retrieval/policies/identity-provider/session",
            headers={"Authorization": f"Bearer {reviewer_token}"},
        )
        self.assertEqual(session.status_code, 200)
        self.assertEqual(session.json()["subject"], "session-reviewer@example.com")
        self.assertIn("HttpOnly", session.headers.get("set-cookie", ""))

        proposal = client.post(
            "/api/retrieval/policies/propose",
            json={
                "collection": "session-oidc-demo",
                "settings": {"query_rewrite": True, "reranker": "noop"},
                "reviewer": "attacker@example.com",
                "reviewer_role": "owner",
            },
        )
        self.assertEqual(proposal.status_code, 200)
        self.assertEqual(proposal.json()["proposal"]["reviewer"], "session-reviewer@example.com")

        approver_token = jwt.encode(
            {
                "iss": "https://session-idp.example.test/",
                "aud": "rag-console-session",
                "sub": "session-approver",
                "email": "session-approver@example.com",
                "groups": ["RAG Approvers"],
                "exp": int(time.time()) + 300,
                "iat": int(time.time()),
            },
            private_key,
            algorithm="RS256",
            headers={"kid": "session-oidc-key"},
        )
        session = client.post(
            "/api/retrieval/policies/identity-provider/session",
            headers={"Authorization": f"Bearer {approver_token}"},
        )
        self.assertEqual(session.status_code, 200)
        approved = client.post(
            "/api/retrieval/policies/approve",
            json={
                "proposal_id": proposal.json()["proposal_id"],
                "approver": "attacker@example.com",
                "approver_role": "owner",
            },
        )
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(approved.json()["audit_entry"]["approver"], "session-approver@example.com")
        self.assertEqual(approved.json()["audit_entry"]["identity_source"], "oidc_session")

        logout = client.post("/api/retrieval/policies/identity-provider/logout")
        self.assertEqual(logout.status_code, 200)
        rejected = client.post(
            "/api/retrieval/policies/propose",
            json={
                "collection": "session-oidc-demo",
                "settings": {"query_rewrite": False},
                "reviewer": "session-reviewer@example.com",
                "reviewer_role": "reviewer",
            },
        )
        self.assertEqual(rejected.status_code, 401)

    def test_api_proposes_retrieval_policy_with_assignment_notification(self) -> None:
        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)

        proposal = client.post(
            "/api/retrieval/policies/propose",
            json={
                "collection": "assignment-demo",
                "settings": {"query_rewrite": True, "reranker": "noop"},
                "reviewer": "unit-reviewer",
                "reviewer_role": "reviewer",
                "assigned_to": "policy-approver",
                "due_at": "2026-06-21T12:00:00",
                "review_note": "Needs assigned approval.",
            },
        )

        self.assertEqual(proposal.status_code, 200)
        body = proposal.json()
        self.assertEqual(body["proposal"]["assigned_to"], "policy-approver")
        self.assertEqual(body["assignment_notification"]["recipient"], "policy-approver")
        self.assertEqual(body["assignment_notification"]["status"], "pending")
        self.assertEqual(body["assignment_notification"]["due_at"], "2026-06-21T12:00:00")

        notifications = client.get(
            "/api/retrieval/policies/notifications",
            params={"recipient": "policy-approver", "status": "pending"},
        )

        self.assertEqual(notifications.status_code, 200)
        payload = notifications.json()
        self.assertEqual(payload["notification_count"], 1)
        self.assertEqual(payload["notifications"][0]["proposal_id"], body["proposal_id"])
        saved_policy = orjson.loads((self.persist_dir / "retrieval_policies.json").read_bytes())
        self.assertEqual(saved_policy["notifications"][0]["recipient"], "policy-approver")

    def test_api_dispatches_retrieval_policy_notifications_to_outbox(self) -> None:
        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)
        outbox_path = self.persist_dir / "policy_notification_outbox.jsonl"

        proposal = client.post(
            "/api/retrieval/policies/propose",
            json={
                "collection": "dispatch-demo",
                "settings": {"query_rewrite": True, "reranker": "noop"},
                "reviewer": "unit-reviewer",
                "reviewer_role": "reviewer",
                "assigned_to": "policy-approver",
                "due_at": "2026-06-22T09:00:00",
                "review_note": "Needs delivered approval notification.",
            },
        )
        self.assertEqual(proposal.status_code, 200)

        dispatched = client.post(
            "/api/retrieval/policies/notifications/dispatch",
            json={
                "recipient": "policy-approver",
                "status": "pending",
                "delivery_mode": "outbox_file",
                "outbox_path": str(outbox_path),
                "dispatched_by": "unit-dispatcher",
            },
        )

        self.assertEqual(dispatched.status_code, 200)
        body = dispatched.json()
        self.assertEqual(body["dispatched_count"], 1)
        self.assertEqual(body["delivery_mode"], "outbox_file")
        self.assertEqual(body["notifications"][0]["status"], "delivered")
        self.assertEqual(body["notifications"][0]["delivery"]["mode"], "outbox_file")
        self.assertTrue(outbox_path.exists())
        outbox_event = orjson.loads(outbox_path.read_bytes().splitlines()[0])
        self.assertEqual(outbox_event["recipient"], "policy-approver")
        self.assertEqual(outbox_event["proposal_id"], proposal.json()["proposal_id"])

        pending = client.get(
            "/api/retrieval/policies/notifications",
            params={"recipient": "policy-approver", "status": "pending"},
        )
        self.assertEqual(pending.status_code, 200)
        self.assertEqual(pending.json()["notification_count"], 0)
        saved_policy = orjson.loads((self.persist_dir / "retrieval_policies.json").read_bytes())
        self.assertEqual(saved_policy["notifications"][0]["status"], "delivered")
        self.assertEqual(saved_policy["audit"][-1]["action"], "dispatch_notification")

    def test_api_rejects_notification_dispatch_outbox_outside_persist_dir(self) -> None:
        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)
        outside_outbox = self.upload_dir / "outside_policy_notifications.jsonl"

        proposal = client.post(
            "/api/retrieval/policies/propose",
            json={
                "collection": "dispatch-security-demo",
                "settings": {"query_rewrite": True, "reranker": "noop"},
                "reviewer": "unit-reviewer",
                "reviewer_role": "reviewer",
                "assigned_to": "policy-approver",
            },
        )
        self.assertEqual(proposal.status_code, 200)

        dispatched = client.post(
            "/api/retrieval/policies/notifications/dispatch",
            json={
                "recipient": "policy-approver",
                "delivery_mode": "outbox_file",
                "outbox_path": str(outside_outbox),
            },
        )

        self.assertEqual(dispatched.status_code, 400)
        self.assertFalse(outside_outbox.exists())

    def test_api_dispatches_retrieval_policy_notifications_to_webhook(self) -> None:
        received_events: list[dict] = []

        class WebhookHandler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802 - stdlib handler hook
                length = int(self.headers.get("Content-Length", "0"))
                received_events.append(orjson.loads(self.rfile.read(length)))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"ok")

            def log_message(self, *_: object) -> None:
                return

        server = HTTPServer(("127.0.0.1", 0), WebhookHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        webhook_url = f"http://127.0.0.1:{server.server_address[1]}/policy-notifications"

        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)
        proposal = client.post(
            "/api/retrieval/policies/propose",
            json={
                "collection": "dispatch-webhook-demo",
                "settings": {"query_rewrite": True, "reranker": "noop"},
                "reviewer": "unit-reviewer",
                "reviewer_role": "reviewer",
                "assigned_to": "policy-approver",
                "due_at": "2026-06-22T10:30:00",
            },
        )
        self.assertEqual(proposal.status_code, 200)

        dispatched = client.post(
            "/api/retrieval/policies/notifications/dispatch",
            json={
                "recipient": "policy-approver",
                "status": "pending",
                "delivery_mode": "webhook",
                "webhook_url": webhook_url,
                "dispatched_by": "unit-dispatcher",
            },
        )

        self.assertEqual(dispatched.status_code, 200)
        body = dispatched.json()
        self.assertEqual(body["delivery_mode"], "webhook")
        self.assertEqual(body["dispatched_count"], 1)
        self.assertEqual(body["notifications"][0]["delivery"]["mode"], "webhook")
        self.assertEqual(body["notifications"][0]["delivery"]["target"], webhook_url)
        self.assertEqual(received_events[0]["recipient"], "policy-approver")
        self.assertEqual(received_events[0]["proposal_id"], proposal.json()["proposal_id"])
        saved_policy = orjson.loads((self.persist_dir / "retrieval_policies.json").read_bytes())
        self.assertEqual(saved_policy["notifications"][0]["status"], "delivered")
        self.assertEqual(saved_policy["audit"][-1]["delivery_mode"], "webhook")

    def test_api_dispatches_signed_lark_template_webhook_notifications(self) -> None:
        received: list[dict] = []

        class SignedWebhookHandler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802 - stdlib handler hook
                body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                received.append(
                    {
                        "body": body,
                        "payload": orjson.loads(body),
                        "timestamp": self.headers.get("X-RAG-Notification-Timestamp"),
                        "signature": self.headers.get("X-RAG-Notification-Signature"),
                        "algorithm": self.headers.get("X-RAG-Notification-Signature-Alg"),
                    }
                )
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"ok")

            def log_message(self, *_: object) -> None:
                return

        server = HTTPServer(("127.0.0.1", 0), SignedWebhookHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        webhook_url = f"http://127.0.0.1:{server.server_address[1]}/lark-policy-notifications"
        secret = "unit-test-webhook-secret"

        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)
        proposal = client.post(
            "/api/retrieval/policies/propose",
            json={
                "collection": "signed-webhook-demo",
                "settings": {"query_rewrite": True, "reranker": "noop"},
                "reviewer": "unit-reviewer",
                "reviewer_role": "reviewer",
                "assigned_to": "policy-approver",
                "due_at": "2026-06-22T11:00:00",
            },
        )
        self.assertEqual(proposal.status_code, 200)

        with patch.dict("os.environ", {"RAG_POLICY_WEBHOOK_SECRET": secret}):
            dispatched = client.post(
                "/api/retrieval/policies/notifications/dispatch",
                json={
                    "recipient": "policy-approver",
                    "status": "pending",
                    "delivery_mode": "webhook",
                    "webhook_url": webhook_url,
                    "webhook_template": "lark_text",
                    "webhook_signing_secret_env": "RAG_POLICY_WEBHOOK_SECRET",
                    "dispatched_by": "unit-dispatcher",
                },
            )

        self.assertEqual(dispatched.status_code, 200)
        self.assertEqual(received[0]["payload"]["msg_type"], "text")
        text = received[0]["payload"]["content"]["text"]
        self.assertIn(proposal.json()["proposal_id"], text)
        self.assertIn("signed-webhook-demo", text)
        self.assertEqual(received[0]["algorithm"], "hmac-sha256")
        expected = hmac.new(
            secret.encode("utf-8"),
            f"{received[0]['timestamp']}.".encode("utf-8") + received[0]["body"],
            hashlib.sha256,
        ).hexdigest()
        self.assertEqual(received[0]["signature"], expected)
        delivery = dispatched.json()["notifications"][0]["delivery"]
        self.assertEqual(delivery["template"], "lark_text")
        self.assertTrue(delivery["signed"])
        self.assertNotIn(secret, orjson.dumps(dispatched.json()).decode("utf-8"))

    def test_api_dispatches_dingtalk_and_wecom_text_webhook_notifications(self) -> None:
        for template in ("dingtalk_text", "wecom_text"):
            with self.subTest(template=template):
                received: list[dict] = []

                class BotWebhookHandler(BaseHTTPRequestHandler):
                    def do_POST(self) -> None:  # noqa: N802 - stdlib handler hook
                        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                        received.append(orjson.loads(body))
                        self.send_response(200)
                        self.end_headers()
                        self.wfile.write(b"ok")

                    def log_message(self, *_: object) -> None:
                        return

                server = HTTPServer(("127.0.0.1", 0), BotWebhookHandler)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                self.addCleanup(server.server_close)
                self.addCleanup(server.shutdown)
                webhook_url = f"http://127.0.0.1:{server.server_address[1]}/{template}"

                app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
                client = TestClient(app)
                proposal = client.post(
                    "/api/retrieval/policies/propose",
                    json={
                        "collection": f"{template}-demo",
                        "settings": {"query_rewrite": True, "reranker": "noop"},
                        "reviewer": "unit-reviewer",
                        "reviewer_role": "reviewer",
                        "assigned_to": f"{template}-approver",
                        "due_at": "2026-06-23T10:00:00",
                    },
                )
                self.assertEqual(proposal.status_code, 200)

                dispatched = client.post(
                    "/api/retrieval/policies/notifications/dispatch",
                    json={
                        "recipient": f"{template}-approver",
                        "status": "pending",
                        "delivery_mode": "webhook",
                        "webhook_url": webhook_url,
                        "webhook_template": template,
                        "dispatched_by": "unit-dispatcher",
                    },
                )

                self.assertEqual(dispatched.status_code, 200)
                self.assertEqual(received[0]["msgtype"], "text")
                text = received[0]["text"]["content"]
                self.assertIn(proposal.json()["proposal_id"], text)
                self.assertIn(f"{template}-demo", text)
                delivery = dispatched.json()["notifications"][0]["delivery"]
                self.assertEqual(delivery["template"], template)

    def test_api_dispatches_incident_management_webhook_templates_without_storing_secrets(self) -> None:
        received: list[dict] = []

        class IncidentWebhookHandler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802 - stdlib handler hook
                body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                received.append(
                    {
                        "path": self.path,
                        "headers": dict(self.headers),
                        "body": body,
                        "payload": orjson.loads(body),
                    }
                )
                self.send_response(202)
                self.end_headers()
                self.wfile.write(b"accepted")

            def log_message(self, *_: object) -> None:
                return

        server = HTTPServer(("127.0.0.1", 0), IncidentWebhookHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        base_url = f"http://127.0.0.1:{server.server_address[1]}"

        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)
        secret_values = {
            "RAG_PAGERDUTY_ROUTING_KEY": "pagerduty-routing-secret",
            "RAG_OPSGENIE_API_KEY": "opsgenie-api-secret",
        }

        with patch.dict("os.environ", secret_values):
            for template in ("pagerduty_event_v2", "opsgenie_alert"):
                proposal = client.post(
                    "/api/retrieval/policies/propose",
                    json={
                        "collection": f"{template}-demo",
                        "settings": {"query_rewrite": True, "reranker": "noop"},
                        "reviewer": "unit-reviewer",
                        "reviewer_role": "reviewer",
                        "assigned_to": f"{template}-approver",
                        "due_at": "2026-06-27T10:00:00",
                    },
                )
                self.assertEqual(proposal.status_code, 200)
                request_body = {
                    "recipient": f"{template}-approver",
                    "status": "pending",
                    "delivery_mode": "webhook",
                    "webhook_url": f"{base_url}/{template}",
                    "webhook_template": template,
                    "dispatched_by": "unit-dispatcher",
                }
                if template == "pagerduty_event_v2":
                    request_body["webhook_routing_key_env"] = "RAG_PAGERDUTY_ROUTING_KEY"
                else:
                    request_body.update(
                        {
                            "webhook_auth_header_name": "Authorization",
                            "webhook_auth_scheme": "GenieKey",
                            "webhook_auth_token_env": "RAG_OPSGENIE_API_KEY",
                        }
                    )

                dispatched = client.post(
                    "/api/retrieval/policies/notifications/dispatch",
                    json=request_body,
                )

                self.assertEqual(dispatched.status_code, 200)
                delivery = dispatched.json()["notifications"][0]["delivery"]
                self.assertEqual(delivery["template"], template)
                self.assertNotIn(secret_values["RAG_PAGERDUTY_ROUTING_KEY"], orjson.dumps(dispatched.json()).decode("utf-8"))
                self.assertNotIn(secret_values["RAG_OPSGENIE_API_KEY"], orjson.dumps(dispatched.json()).decode("utf-8"))

        pagerduty_payload = next(item["payload"] for item in received if item["path"] == "/pagerduty_event_v2")
        self.assertEqual(pagerduty_payload["routing_key"], secret_values["RAG_PAGERDUTY_ROUTING_KEY"])
        self.assertEqual(pagerduty_payload["event_action"], "trigger")
        self.assertEqual(pagerduty_payload["payload"]["severity"], "warning")
        self.assertIn("pagerduty_event_v2-demo", pagerduty_payload["payload"]["summary"])
        self.assertEqual(pagerduty_payload["payload"]["custom_details"]["recipient"], "pagerduty_event_v2-approver")

        opsgenie_request = next(item for item in received if item["path"] == "/opsgenie_alert")
        self.assertEqual(opsgenie_request["headers"]["Authorization"], f"GenieKey {secret_values['RAG_OPSGENIE_API_KEY']}")
        self.assertIn("opsgenie_alert-demo", opsgenie_request["payload"]["message"])
        self.assertIn("opsgenie_alert-demo", opsgenie_request["payload"]["description"])
        self.assertEqual(opsgenie_request["payload"]["priority"], "P3")
        self.assertEqual(opsgenie_request["payload"]["details"]["recipient"], "opsgenie_alert-approver")

        saved_policy = orjson.loads((self.persist_dir / "retrieval_policies.json").read_bytes())
        serialized_policy = orjson.dumps(saved_policy).decode("utf-8")
        self.assertNotIn(secret_values["RAG_PAGERDUTY_ROUTING_KEY"], serialized_policy)
        self.assertNotIn(secret_values["RAG_OPSGENIE_API_KEY"], serialized_policy)

    def test_api_resolves_incident_webhook_template_from_notification_recipient_registry(self) -> None:
        received: list[dict] = []

        class IncidentWebhookHandler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802 - stdlib handler hook
                body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                received.append(
                    {
                        "path": self.path,
                        "headers": dict(self.headers),
                        "payload": orjson.loads(body),
                    }
                )
                self.send_response(202)
                self.end_headers()
                self.wfile.write(b"accepted")

            def log_message(self, *_: object) -> None:
                return

        server = HTTPServer(("127.0.0.1", 0), IncidentWebhookHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        base_url = f"http://127.0.0.1:{server.server_address[1]}"

        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)
        secret_values = {
            "RAG_PAGERDUTY_ROUTING_KEY": "registry-pagerduty-routing-secret",
            "RAG_OPSGENIE_API_KEY": "registry-opsgenie-api-secret",
        }

        pagerduty_recipient = client.post(
            "/api/retrieval/policies/notification-recipients/upsert",
            json={
                "subject": "pagerduty-registry-approver",
                "webhook_url": f"{base_url}/pagerduty-registry",
                "webhook_template": "pagerduty_event_v2",
                "webhook_routing_key_env": "RAG_PAGERDUTY_ROUTING_KEY",
                "preferred_delivery_mode": "webhook",
                "updated_by": "unit-admin",
            },
        )
        self.assertEqual(pagerduty_recipient.status_code, 200)
        self.assertEqual(pagerduty_recipient.json()["recipient_entry"]["webhook_template"], "pagerduty_event_v2")

        opsgenie_recipient = client.post(
            "/api/retrieval/policies/notification-recipients/upsert",
            json={
                "subject": "opsgenie-registry-approver",
                "webhook_url": f"{base_url}/opsgenie-registry",
                "webhook_template": "opsgenie_alert",
                "webhook_auth_header_name": "Authorization",
                "webhook_auth_scheme": "GenieKey",
                "webhook_auth_token_env": "RAG_OPSGENIE_API_KEY",
                "preferred_delivery_mode": "webhook",
                "updated_by": "unit-admin",
            },
        )
        self.assertEqual(opsgenie_recipient.status_code, 200)
        self.assertEqual(opsgenie_recipient.json()["recipient_entry"]["webhook_auth_token_env"], "RAG_OPSGENIE_API_KEY")

        with patch.dict("os.environ", secret_values):
            for recipient, collection in (
                ("pagerduty-registry-approver", "pagerduty-registry-demo"),
                ("opsgenie-registry-approver", "opsgenie-registry-demo"),
            ):
                proposal = client.post(
                    "/api/retrieval/policies/propose",
                    json={
                        "collection": collection,
                        "settings": {"query_rewrite": True, "reranker": "noop"},
                        "reviewer": "unit-reviewer",
                        "reviewer_role": "reviewer",
                        "assigned_to": recipient,
                        "due_at": "2026-06-28T10:00:00",
                    },
                )
                self.assertEqual(proposal.status_code, 200)

                dispatched = client.post(
                    "/api/retrieval/policies/notifications/dispatch",
                    json={
                        "recipient": recipient,
                        "status": "pending",
                        "delivery_mode": "webhook",
                        "dispatched_by": "unit-dispatcher",
                    },
                )
                self.assertEqual(dispatched.status_code, 200)
                delivery = dispatched.json()["notifications"][0]["delivery"]
                self.assertEqual(delivery["recipient_source"], "notification_recipient_registry")
                self.assertNotIn(secret_values["RAG_PAGERDUTY_ROUTING_KEY"], orjson.dumps(dispatched.json()).decode("utf-8"))
                self.assertNotIn(secret_values["RAG_OPSGENIE_API_KEY"], orjson.dumps(dispatched.json()).decode("utf-8"))

        pagerduty_payload = next(item["payload"] for item in received if item["path"] == "/pagerduty-registry")
        self.assertEqual(pagerduty_payload["routing_key"], secret_values["RAG_PAGERDUTY_ROUTING_KEY"])
        self.assertIn("pagerduty-registry-demo", pagerduty_payload["payload"]["summary"])

        opsgenie_request = next(item for item in received if item["path"] == "/opsgenie-registry")
        self.assertEqual(opsgenie_request["headers"]["Authorization"], f"GenieKey {secret_values['RAG_OPSGENIE_API_KEY']}")
        self.assertIn("opsgenie-registry-demo", opsgenie_request["payload"]["message"])

        saved_policy = orjson.loads((self.persist_dir / "retrieval_policies.json").read_bytes())
        self.assertEqual(
            saved_policy["notification_recipient_registry"]["pagerduty-registry-approver"]["webhook_routing_key_env"],
            "RAG_PAGERDUTY_ROUTING_KEY",
        )
        serialized_policy = orjson.dumps(saved_policy).decode("utf-8")
        self.assertNotIn(secret_values["RAG_PAGERDUTY_ROUTING_KEY"], serialized_policy)
        self.assertNotIn(secret_values["RAG_OPSGENIE_API_KEY"], serialized_policy)

    def test_api_records_failed_webhook_notification_delivery(self) -> None:
        class FailingWebhookHandler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802 - stdlib handler hook
                self.rfile.read(int(self.headers.get("Content-Length", "0")))
                self.send_response(500)
                self.end_headers()
                self.wfile.write(b"failed")

            def log_message(self, *_: object) -> None:
                return

        server = HTTPServer(("127.0.0.1", 0), FailingWebhookHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        webhook_url = f"http://127.0.0.1:{server.server_address[1]}/failing-policy-notifications"

        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)
        proposal = client.post(
            "/api/retrieval/policies/propose",
            json={
                "collection": "failing-webhook-demo",
                "settings": {"query_rewrite": True, "reranker": "noop"},
                "reviewer": "unit-reviewer",
                "reviewer_role": "reviewer",
                "assigned_to": "policy-approver",
                "due_at": "2026-06-24T10:00:00",
            },
        )
        self.assertEqual(proposal.status_code, 200)

        dispatched = client.post(
            "/api/retrieval/policies/notifications/dispatch",
            json={
                "recipient": "policy-approver",
                "status": "pending",
                "delivery_mode": "webhook",
                "webhook_url": webhook_url,
                "webhook_template": "generic",
                "dispatched_by": "unit-dispatcher",
            },
        )

        self.assertEqual(dispatched.status_code, 200)
        body = dispatched.json()
        self.assertEqual(body["dispatched_count"], 0)
        self.assertEqual(body["failed_count"], 1)
        notification = body["notifications"][0]
        self.assertEqual(notification["status"], "failed")
        self.assertEqual(notification["proposal_id"], proposal.json()["proposal_id"])
        self.assertEqual(notification["delivery"]["response"]["status_code"], 500)
        self.assertTrue(notification["delivery"]["response"]["failed"])
        saved_policy = orjson.loads((self.persist_dir / "retrieval_policies.json").read_bytes())
        self.assertEqual(saved_policy["notifications"][0]["status"], "failed")
        self.assertEqual(saved_policy["audit"][-1]["attempted_count"], 1)
        self.assertEqual(saved_policy["audit"][-1]["dispatched_count"], 0)
        self.assertEqual(saved_policy["audit"][-1]["failed_count"], 1)

    def test_api_dispatches_smtp_email_notifications_without_storing_password(self) -> None:
        class CapturingSmtpServer(socketserver.TCPServer):
            allow_reuse_address = True

        class CapturingSmtpHandler(socketserver.StreamRequestHandler):
            def handle(self) -> None:
                self.wfile.write(b"220 localhost ESMTP test\r\n")
                in_data = False
                data_lines: list[bytes] = []
                while True:
                    line = self.rfile.readline()
                    if not line:
                        break
                    text = line.decode("utf-8", "replace").rstrip("\r\n")
                    if in_data:
                        if text == ".":
                            self.server.messages.append(b"".join(data_lines))  # type: ignore[attr-defined]
                            data_lines = []
                            in_data = False
                            self.wfile.write(b"250 queued\r\n")
                        else:
                            data_lines.append(line)
                        continue
                    command = text.split(" ", 1)[0].upper()
                    self.server.commands.append(text)  # type: ignore[attr-defined]
                    if command in {"EHLO", "HELO"}:
                        self.wfile.write(b"250-localhost\r\n250-AUTH PLAIN LOGIN\r\n250 HELP\r\n")
                    elif command == "AUTH":
                        self.wfile.write(b"235 2.7.0 Authentication successful\r\n")
                    elif command in {"MAIL", "RCPT", "RSET"}:
                        self.wfile.write(b"250 ok\r\n")
                    elif command == "DATA":
                        in_data = True
                        self.wfile.write(b"354 End data with <CR><LF>.<CR><LF>\r\n")
                    elif command == "QUIT":
                        self.wfile.write(b"221 bye\r\n")
                        break
                    else:
                        self.wfile.write(b"250 ok\r\n")

        server = CapturingSmtpServer(("127.0.0.1", 0), CapturingSmtpHandler)
        server.messages = []  # type: ignore[attr-defined]
        server.commands = []  # type: ignore[attr-defined]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)

        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)
        proposal = client.post(
            "/api/retrieval/policies/propose",
            json={
                "collection": "smtp-policy-demo",
                "settings": {"query_rewrite": True, "reranker": "noop"},
                "reviewer": "unit-reviewer",
                "reviewer_role": "reviewer",
                "assigned_to": "policy-approver",
                "due_at": "2026-06-25T10:00:00",
            },
        )
        self.assertEqual(proposal.status_code, 200)
        secret = "smtp-password-secret"

        with patch.dict(
            "os.environ",
            {
                "RAG_POLICY_SMTP_USER": "rag-policy-bot",
                "RAG_POLICY_SMTP_PASSWORD": secret,
            },
        ):
            dispatched = client.post(
                "/api/retrieval/policies/notifications/dispatch",
                json={
                    "recipient": "policy-approver",
                    "status": "pending",
                    "delivery_mode": "smtp",
                    "smtp_host": "127.0.0.1",
                    "smtp_port": server.server_address[1],
                    "smtp_from": "rag-policy@example.com",
                    "smtp_to": "approver@example.com",
                    "smtp_subject": "RAG policy approval needed",
                    "smtp_use_tls": False,
                    "smtp_username_env": "RAG_POLICY_SMTP_USER",
                    "smtp_password_env": "RAG_POLICY_SMTP_PASSWORD",
                    "dispatched_by": "unit-dispatcher",
                },
            )

        self.assertEqual(dispatched.status_code, 200)
        body = dispatched.json()
        self.assertEqual(body["delivery_mode"], "smtp")
        self.assertEqual(body["dispatched_count"], 1)
        self.assertEqual(body["failed_count"], 0)
        self.assertEqual(len(server.messages), 1)  # type: ignore[attr-defined]
        message = message_from_bytes(server.messages[0])  # type: ignore[attr-defined]
        self.assertEqual(message["From"], "rag-policy@example.com")
        self.assertEqual(message["To"], "approver@example.com")
        self.assertEqual(message["Subject"], "RAG policy approval needed")
        payload = message.get_payload(decode=True).decode("utf-8")
        self.assertIn(proposal.json()["proposal_id"], payload)
        self.assertIn("smtp-policy-demo", payload)
        delivery = body["notifications"][0]["delivery"]
        self.assertEqual(delivery["mode"], "smtp")
        self.assertTrue(delivery["authenticated"])
        self.assertFalse(delivery["response"]["failed"])
        self.assertNotIn(secret, orjson.dumps(body).decode("utf-8"))
        saved_policy = orjson.loads((self.persist_dir / "retrieval_policies.json").read_bytes())
        self.assertEqual(saved_policy["notifications"][0]["status"], "delivered")
        self.assertEqual(saved_policy["audit"][-1]["delivery_mode"], "smtp")
        self.assertEqual(saved_policy["audit"][-1]["attempted_count"], 1)
        self.assertEqual(saved_policy["audit"][-1]["dispatched_count"], 1)
        self.assertEqual(saved_policy["audit"][-1]["failed_count"], 0)
        self.assertNotIn(secret, orjson.dumps(saved_policy).decode("utf-8"))

    def test_api_resolves_smtp_recipient_from_notification_recipient_registry(self) -> None:
        class CapturingSmtpServer(socketserver.TCPServer):
            allow_reuse_address = True

        class CapturingSmtpHandler(socketserver.StreamRequestHandler):
            def handle(self) -> None:
                self.wfile.write(b"220 localhost ESMTP test\r\n")
                in_data = False
                data_lines: list[bytes] = []
                while True:
                    line = self.rfile.readline()
                    if not line:
                        break
                    text = line.decode("utf-8", "replace").rstrip("\r\n")
                    if in_data:
                        if text == ".":
                            self.server.messages.append(b"".join(data_lines))  # type: ignore[attr-defined]
                            data_lines = []
                            in_data = False
                            self.wfile.write(b"250 queued\r\n")
                        else:
                            data_lines.append(line)
                        continue
                    command = text.split(" ", 1)[0].upper()
                    if command in {"EHLO", "HELO"}:
                        self.wfile.write(b"250 localhost\r\n")
                    elif command in {"MAIL", "RCPT", "RSET"}:
                        self.wfile.write(b"250 ok\r\n")
                    elif command == "DATA":
                        in_data = True
                        self.wfile.write(b"354 End data with <CR><LF>.<CR><LF>\r\n")
                    elif command == "QUIT":
                        self.wfile.write(b"221 bye\r\n")
                        break
                    else:
                        self.wfile.write(b"250 ok\r\n")

        server = CapturingSmtpServer(("127.0.0.1", 0), CapturingSmtpHandler)
        server.messages = []  # type: ignore[attr-defined]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)

        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)
        registered = client.post(
            "/api/retrieval/policies/notification-recipients/upsert",
            json={
                "subject": "policy-approver",
                "email": "approver@example.com",
                "preferred_delivery_mode": "smtp",
                "updated_by": "unit-admin",
                "note": "local directory mapping",
            },
        )
        self.assertEqual(registered.status_code, 200)
        self.assertEqual(registered.json()["recipient_entry"]["email"], "approver@example.com")

        proposal = client.post(
            "/api/retrieval/policies/propose",
            json={
                "collection": "directory-smtp-demo",
                "settings": {"query_rewrite": True, "reranker": "noop"},
                "reviewer": "unit-reviewer",
                "reviewer_role": "reviewer",
                "assigned_to": "policy-approver",
                "due_at": "2026-06-26T10:00:00",
            },
        )
        self.assertEqual(proposal.status_code, 200)

        dispatched = client.post(
            "/api/retrieval/policies/notifications/dispatch",
            json={
                "recipient": "policy-approver",
                "status": "pending",
                "delivery_mode": "smtp",
                "smtp_host": "127.0.0.1",
                "smtp_port": server.server_address[1],
                "smtp_from": "rag-policy@example.com",
                "smtp_subject": "Directory resolved policy approval",
                "smtp_use_tls": False,
                "dispatched_by": "unit-dispatcher",
            },
        )

        self.assertEqual(dispatched.status_code, 200)
        body = dispatched.json()
        self.assertEqual(body["dispatched_count"], 1)
        message = message_from_bytes(server.messages[0])  # type: ignore[attr-defined]
        self.assertEqual(message["To"], "approver@example.com")
        delivery = body["notifications"][0]["delivery"]
        self.assertEqual(delivery["smtp_to"], "approver@example.com")
        self.assertEqual(delivery["recipient_source"], "notification_recipient_registry")
        saved_policy = orjson.loads((self.persist_dir / "retrieval_policies.json").read_bytes())
        self.assertEqual(saved_policy["notification_recipient_registry"]["policy-approver"]["email"], "approver@example.com")
        self.assertEqual(saved_policy["audit"][-1]["recipient_source"], "notification_recipient_registry")

    def test_api_search_can_include_graph_retriever_in_hybrid_adapter(self) -> None:
        from storage_layer.graph_store import GraphEdgeRecord, GraphStore

        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)

        ingest = client.post(
            "/api/ingest",
            data={
                "collection": "graph-search-demo",
                "chunk_size": "50",
                "overlap": "10",
                "backend": "hashing",
            },
            files=[("files", ("ops.txt", b"general maintenance baseline", "text/plain"))],
        )
        self.assertEqual(ingest.status_code, 200)

        graph_db_path = self.persist_dir / "graph_store.sqlite"
        store = GraphStore(graph_db_path)
        store.initialize(reset=True)
        store.import_edges(
            [
                GraphEdgeRecord(
                    triple_id="G1",
                    subject="pump",
                    predicate="CAUSES",
                    object_name="vibration",
                    confidence=0.95,
                    evidence="Pump vibration is a graph-backed maintenance signal.",
                    source_file="graph.md",
                )
            ],
            reset=False,
        )

        search = client.post(
            "/api/search",
            json={
                "collection": "graph-search-demo",
                "query": "pump vibration",
                "top_k": 5,
                "graph_db_path": str(graph_db_path),
            },
        )

        self.assertEqual(search.status_code, 200)
        payload = search.json()
        retriever_names = {item["name"] for item in payload["retrieval_diagnostics"]["retrievers"]}
        self.assertIn("graph", retriever_names)
        self.assertTrue(
            any("rrf:graph" in result["metadata"].get("component_scores", {}) for result in payload["results"])
        )

    def test_api_search_applies_metadata_filters_in_hybrid_adapter(self) -> None:
        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)

        ingest = client.post(
            "/api/ingest",
            data={
                "collection": "filter-demo",
                "chunk_size": "80",
                "overlap": "10",
                "backend": "hashing",
            },
            files=[
                ("files", ("pump.txt", b"pump maintenance text source", "text/plain")),
                ("files", ("pump.md", b"pump maintenance markdown source", "text/markdown")),
            ],
        )
        self.assertEqual(ingest.status_code, 200)

        search = client.post(
            "/api/search",
            json={
                "collection": "filter-demo",
                "query": "pump maintenance",
                "top_k": 5,
                "filters": {"field": "meta.source_ext", "operator": "==", "value": ".md"},
            },
        )

        self.assertEqual(search.status_code, 200)
        payload = search.json()
        self.assertTrue(payload["results"])
        self.assertTrue(payload["retrieval_diagnostics"]["filters_applied"])
        self.assertTrue(all(result["metadata"].get("source_ext") == ".md" for result in payload["results"]))

    def test_api_search_extracts_source_type_filter_from_natural_language_query(self) -> None:
        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)

        ingest = client.post(
            "/api/ingest",
            data={
                "collection": "nl-filter-demo",
                "chunk_size": "80",
                "overlap": "10",
                "backend": "hashing",
            },
            files=[
                ("files", ("pump.txt", b"pump maintenance text source", "text/plain")),
                ("files", ("pump.md", b"pump maintenance markdown source", "text/markdown")),
            ],
        )
        self.assertEqual(ingest.status_code, 200)

        search = client.post(
            "/api/search",
            json={
                "collection": "nl-filter-demo",
                "query": "only search markdown for pump maintenance",
                "top_k": 5,
            },
        )

        self.assertEqual(search.status_code, 200)
        payload = search.json()
        self.assertTrue(payload["results"])
        diagnostics = payload["retrieval_diagnostics"]
        self.assertTrue(diagnostics["filters_applied"])
        self.assertEqual(diagnostics["auto_filters"][0]["field"], "meta.source_ext")
        self.assertEqual(diagnostics["auto_filters"][0]["value"], ".md")
        self.assertTrue(all(result["metadata"].get("source_ext") == ".md" for result in payload["results"]))

    def test_api_search_extracts_source_filename_filter_from_natural_language_query(self) -> None:
        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)

        ingest = client.post(
            "/api/ingest",
            data={
                "collection": "filename-filter-demo",
                "chunk_size": "80",
                "overlap": "10",
                "backend": "hashing",
            },
            files=[
                ("files", ("pump-guide.md", b"maintenance shared topic for pump", "text/markdown")),
                ("files", ("compressor-guide.md", b"maintenance shared topic for compressor", "text/markdown")),
            ],
        )
        self.assertEqual(ingest.status_code, 200)

        search = client.post(
            "/api/search",
            json={
                "collection": "filename-filter-demo",
                "query": "only search pump-guide.md for maintenance",
                "top_k": 5,
            },
        )

        self.assertEqual(search.status_code, 200)
        payload = search.json()
        self.assertTrue(payload["results"])
        auto_filters = payload["retrieval_diagnostics"]["auto_filters"]
        self.assertTrue(
            any(item["field"] == "meta.source_file" and item["value"] == "pump-guide.md" for item in auto_filters)
        )
        self.assertTrue(all("pump-guide.md" in result["metadata"].get("source_file", "") for result in payload["results"]))

    def test_api_search_extracts_year_filter_from_natural_language_query(self) -> None:
        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)

        ingest = client.post(
            "/api/ingest",
            data={
                "collection": "year-filter-demo",
                "chunk_size": "80",
                "overlap": "10",
                "backend": "hashing",
            },
            files=[
                ("files", ("2024-maintenance.md", b"maintenance annual report previous", "text/markdown")),
                ("files", ("2025-maintenance.md", b"maintenance annual report current", "text/markdown")),
            ],
        )
        self.assertEqual(ingest.status_code, 200)

        search = client.post(
            "/api/search",
            json={
                "collection": "year-filter-demo",
                "query": "only search 2025 maintenance annual report",
                "top_k": 5,
            },
        )

        self.assertEqual(search.status_code, 200)
        payload = search.json()
        self.assertTrue(payload["results"])
        auto_filters = payload["retrieval_diagnostics"]["auto_filters"]
        self.assertTrue(
            any(item["field"] == "meta.source_file" and item["value"] == "2025" for item in auto_filters)
        )
        self.assertTrue(all("2025" in result["metadata"].get("source_file", "") for result in payload["results"]))

    def test_api_search_extracts_business_metadata_filters_from_natural_language_query(self) -> None:
        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)

        ingest = client.post(
            "/api/ingest",
            data={
                "collection": "business-filter-demo",
                "chunk_size": "80",
                "overlap": "10",
                "backend": "hashing",
            },
            files=[
                ("files", ("business-policy.md", b"Pump inspection policy and maintenance handoff.", "text/markdown")),
            ],
        )
        self.assertEqual(ingest.status_code, 200)

        search = client.post(
            "/api/search",
            json={
                "collection": "business-filter-demo",
                "query": "author: Alice department: Engineering product: Pump-7 from 2024-01-01 to 2024-12-31 maintenance",
                "top_k": 5,
            },
        )

        self.assertEqual(search.status_code, 200)
        auto_filters = search.json()["retrieval_diagnostics"]["auto_filters"]
        self.assertTrue(
            any(item["field"] == "meta.author" and item["operator"] == "contains" and item["value"] == "Alice" for item in auto_filters)
        )
        self.assertTrue(
            any(item["field"] == "meta.department" and item["operator"] == "contains" and item["value"] == "Engineering" for item in auto_filters)
        )
        self.assertTrue(
            any(item["field"] == "meta.product" and item["operator"] == "contains" and item["value"] == "Pump-7" for item in auto_filters)
        )
        self.assertTrue(
            any(item["field"] == "meta.source_date" and item["operator"] == ">=" and item["value"] == 20240101 for item in auto_filters)
        )
        self.assertTrue(
            any(item["field"] == "meta.source_date" and item["operator"] == "<=" and item["value"] == 20241231 for item in auto_filters)
        )

    def test_api_search_applies_policy_metadata_field_aliases_to_auto_filters(self) -> None:
        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)

        ingest = client.post(
            "/api/ingest",
            data={
                "collection": "alias-filter-demo",
                "chunk_size": "80",
                "overlap": "10",
                "backend": "hashing",
            },
            files=[
                ("files", ("alias-policy.md", b"Pump inspection policy and maintenance handoff.", "text/markdown")),
            ],
        )
        self.assertEqual(ingest.status_code, 200)

        promoted = client.post(
            "/api/retrieval/policies/promote",
            json={
                "collection": "alias-filter-demo",
                "settings": {
                    "metadata_field_aliases": {
                        "meta.author": "meta.owner",
                        "meta.source_date": "meta.document_date",
                    }
                },
                "reviewer": "unit-reviewer",
            },
        )
        self.assertEqual(promoted.status_code, 200)

        search = client.post(
            "/api/search",
            json={
                "collection": "alias-filter-demo",
                "query": "author: Alice from 2024-01-01 to 2024-12-31 maintenance",
                "top_k": 5,
            },
        )

        self.assertEqual(search.status_code, 200)
        diagnostics = search.json()["retrieval_diagnostics"]
        self.assertEqual(
            diagnostics["retrieval_policy"]["settings"]["metadata_field_aliases"]["meta.source_date"],
            "meta.document_date",
        )
        conditions = diagnostics["effective_filters"]["conditions"]
        self.assertTrue(any(item["field"] == "meta.owner" and item["value"] == "Alice" for item in conditions))
        self.assertTrue(any(item["field"] == "meta.document_date" and item["operator"] == ">=" for item in conditions))
        self.assertTrue(any(item["field"] == "meta.document_date" and item["operator"] == "<=" for item in conditions))

    def test_api_search_no_answer_gate_blocks_low_confidence_results(self) -> None:
        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)

        ingest = client.post(
            "/api/ingest",
            data={
                "collection": "no-answer-demo",
                "chunk_size": "80",
                "overlap": "10",
                "backend": "hashing",
            },
            files=[("files", ("ops.txt", b"pump maintenance baseline", "text/plain"))],
        )
        self.assertEqual(ingest.status_code, 200)

        search = client.post(
            "/api/search",
            json={
                "collection": "no-answer-demo",
                "query": "pump maintenance",
                "top_k": 3,
                "no_answer_min_score": 0.5,
            },
        )

        self.assertEqual(search.status_code, 200)
        payload = search.json()
        self.assertEqual(payload["results"], [])
        diagnostics = payload["retrieval_diagnostics"]
        self.assertTrue(diagnostics["no_answer"])
        self.assertEqual(diagnostics["no_answer_reason"], "best_score_below_threshold")
        self.assertEqual(diagnostics["final_candidate_count"], 0)

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

    def test_api_upload_accepts_docling_document_formats(self) -> None:
        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)

        samples = [
            (
                "slides.pptx",
                b"PK\x03\x04fake-presentation",
                "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                "PPTX",
            ),
            (
                "workbook.xlsx",
                b"PK\x03\x04fake-workbook",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "Spreadsheet",
            ),
            ("scan.png", b"\x89PNG\r\n\x1a\nfake-image", "image/png", "Image"),
        ]
        for filename, content, media_type, source_kind in samples:
            response = client.post(
                "/api/upload",
                files={"file": (filename, content, media_type)},
            )

            self.assertEqual(response.status_code, 200, response.text)
            body = response.json()
            self.assertEqual(body["filename"], filename)
            self.assertEqual(body["source_kind"], source_kind)

    def test_api_process_passes_parser_backend_to_ingest_pipeline(self) -> None:
        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)

        upload = client.post(
            "/api/upload",
            files={"file": ("ops.md", b"# Pump\n\nInspect vibration.", "text/markdown")},
        )
        self.assertEqual(upload.status_code, 200)
        uploaded = upload.json()
        captured: dict = {}

        def fake_ingest_source_payloads(**kwargs):
            captured.update(kwargs)
            return {
                "collection": kwargs["collection_name"],
                "files_processed": 1,
                "files_succeeded": 1,
                "files_failed": 0,
                "files_needing_ocr": 0,
                "records_processed": 1,
                "chunks_written": 1,
                "chunk_size": 500,
                "overlap": 50,
                "parser_backend": kwargs.get("parser_backend"),
                "embedding_backend": "hashing",
                "embedding_model": "hashing",
                "embedding_warning": None,
                "file_summaries": [
                    {
                        "source_file": uploaded["filename"],
                        "status": "ok",
                        "records_extracted": 1,
                    }
                ],
                "document_intake": {
                    "files_parsed": 1,
                    "files_needing_ocr": 0,
                    "files_failed": 0,
                    "parser_backends": [kwargs.get("parser_backend")],
                    "parse_chunk_decoupled": True,
                },
                "stats": {},
                "quality_report": {},
            }

        with patch("chroma_rag_poc.api.ingest_source_payloads", side_effect=fake_ingest_source_payloads):
            response = client.post(
                "/api/process",
                json={
                    "filenames": [uploaded["filename"]],
                    "collection": "process-demo",
                    "parser_backend": "docling",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured["parser_backend"], "docling")
        self.assertEqual(response.json()["parser_backend"], "docling")

    def test_api_ingest_passes_parser_backend_to_ingest_pipeline(self) -> None:
        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)
        captured: dict = {}

        def fake_ingest_source_payloads(**kwargs):
            captured.update(kwargs)
            source_file = kwargs["payloads"][0][0]
            return {
                "collection": kwargs["collection_name"],
                "files_processed": 1,
                "files_succeeded": 1,
                "files_failed": 0,
                "files_needing_ocr": 0,
                "records_processed": 1,
                "chunks_written": 1,
                "chunk_size": kwargs["chunk_size"],
                "overlap": kwargs["overlap"],
                "parser_backend": kwargs.get("parser_backend"),
                "embedding_backend": "hashing",
                "embedding_model": "hashing",
                "embedding_warning": None,
                "file_summaries": [
                    {
                        "source_file": source_file,
                        "status": "ok",
                        "records_extracted": 1,
                    }
                ],
                "document_intake": {
                    "files_parsed": 1,
                    "files_needing_ocr": 0,
                    "files_failed": 0,
                    "parser_backends": [kwargs.get("parser_backend")],
                    "parse_chunk_decoupled": True,
                },
                "stats": {},
                "quality_report": {},
            }

        with patch("chroma_rag_poc.api.ingest_source_payloads", side_effect=fake_ingest_source_payloads):
            response = client.post(
                "/api/ingest",
                data={
                    "collection": "api-docling",
                    "backend": "hashing",
                    "parser_backend": "docling",
                },
                files=[("files", ("manual.md", b"# Pump\n\nInspect vibration.", "text/markdown"))],
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured["parser_backend"], "docling")
        self.assertEqual(response.json()["parser_backend"], "docling")

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
        index_response = client.get("/")

        self.assertEqual(lib_response.status_code, 200)
        self.assertEqual(asset_response.status_code, 200)
        self.assertEqual(index_response.status_code, 200)
        self.assertIn("no-store", index_response.headers.get("cache-control", ""))

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

    def test_api_search_empty_database_returns_retrieval_diagnostics(self) -> None:
        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)

        response = client.get("/api/search", params={"q": "status monitoring", "top_k": 2})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["results"], [])
        diagnostics = payload["retrieval_diagnostics"]
        self.assertEqual(diagnostics["original_query"], "status monitoring")
        self.assertEqual(diagnostics["rewritten_queries"], ["status monitoring"])
        self.assertEqual(diagnostics["retrieval_path"], "hybrid")
        self.assertEqual(diagnostics["fusion_mode"], "rrf")
        self.assertTrue(diagnostics["no_answer"])
        self.assertEqual(diagnostics["no_answer_reason"], "empty_database")
        self.assertEqual(diagnostics["final_candidate_count"], 0)

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

    def test_stats_repairs_legacy_chroma_default_tenant_metadata(self) -> None:
        legacy_chroma = Path(self.tempdir.name) / "legacy-chroma"
        legacy_chroma.mkdir()
        db_path = legacy_chroma / "chroma.sqlite3"
        con = sqlite3.connect(db_path)
        try:
            con.execute("CREATE TABLE tenants (id TEXT PRIMARY KEY)")
            con.execute("CREATE TABLE databases (id TEXT PRIMARY KEY, name TEXT NOT NULL, tenant_id TEXT NOT NULL)")
            con.execute("CREATE TABLE collections (id TEXT PRIMARY KEY, name TEXT NOT NULL, database_id TEXT)")
            con.execute("INSERT INTO collections(id, name, database_id) VALUES (?, ?, ?)", ("c1", "legacy", ""))
            con.commit()
        finally:
            con.close()

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
            stats = get_all_stats(legacy_chroma)

        self.assertEqual(stats["status"], "ok")
        self.assertEqual(calls, [legacy_chroma, legacy_chroma])
        self.assertFalse(list(legacy_chroma.parent.glob("legacy-chroma_broken_*")))
        self.assertTrue(list(legacy_chroma.glob("chroma.sqlite3.repair_backup_*")))

        con = sqlite3.connect(db_path)
        try:
            tenant = con.execute("SELECT id FROM tenants WHERE id = ?", ("default_tenant",)).fetchone()
            database = con.execute(
                "SELECT id, tenant_id FROM databases WHERE name = ?",
                ("default_database",),
            ).fetchone()
            collection_db = con.execute("SELECT database_id FROM collections WHERE id = ?", ("c1",)).fetchone()
        finally:
            con.close()

        self.assertEqual(tenant, ("default_tenant",))
        self.assertEqual(database, ("00000000-0000-0000-0000-000000000000", "default_tenant"))
        self.assertEqual(collection_db, ("00000000-0000-0000-0000-000000000000",))

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
        from chroma_rag_poc.embeddings import DEFAULT_SENTENCE_TRANSFORMER_MODEL, resolve_sentence_transformer_model_path

        local_root = Path(self.tempdir.name) / "models"
        model_dir = local_root / "Qwen" / "Qwen3-Embedding-0.6B"
        model_dir.mkdir(parents=True)

        resolved = resolve_sentence_transformer_model_path(DEFAULT_SENTENCE_TRANSFORMER_MODEL, local_roots=[local_root])

        self.assertEqual(Path(resolved), model_dir)

    def test_sentence_transformer_default_uses_qwen3_embedding_0_6b_profile(self) -> None:
        from chroma_rag_poc import embeddings

        self.assertEqual(embeddings.DEFAULT_SENTENCE_TRANSFORMER_MODEL, "Qwen/Qwen3-Embedding-0.6B")
        self.assertEqual(embeddings.infer_sentence_transformer_dimension(None), 1024)
        self.assertEqual(embeddings.infer_sentence_transformer_dimension("Qwen/Qwen3-Embedding-8B"), 4096)
        self.assertEqual(embeddings.infer_sentence_transformer_dimension("Qwen/Qwen3-Embedding-4B"), 2560)
        self.assertEqual(embeddings.infer_sentence_transformer_dimension("Qwen/Qwen3-Embedding-0.6B"), 1024)

    def test_sentence_transformer_missing_local_model_does_not_download_by_default(self) -> None:
        from chroma_rag_poc import embeddings

        embeddings._resolve_embedding_backend.cache_clear()
        with patch("chroma_rag_poc.embeddings._online_model_loading_allowed", return_value=False):
            resolved = create_embedding_backend(
                backend="sentence-transformer",
                model_name=None,
                dimension=32,
            )
        embeddings._resolve_embedding_backend.cache_clear()

        self.assertEqual(resolved.name, "hashing")
        self.assertEqual(resolved.dimension, 32)
        self.assertIn("Local sentence-transformer model not found", resolved.warning or "")
        self.assertIn("Qwen/Qwen3-Embedding-0.6B", resolved.warning or "")

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
        self.assertIn("stripKgRuntimeArtifacts", html)
        self.assertIn("KG_GRAPH_RENDER_NODE_LIMIT", html)
        self.assertIn("shouldRenderKgGraph", html)
        self.assertIn("renderKgGraphLimitNotice", html)
        self.assertIn("kgCommunityTopMembers", html)
        self.assertIn("renderKgCommunityDetails", html)
        self.assertIn('id="kgGraphDetails"', html)
        self.assertIn("sentenceRows", html)
        self.assertIn("source_chunk_id", html)
        self.assertIn("preserve_isolated_nodes", html)
        self.assertIn("const KG_MAX_GENERATIVE_ENTITIES = 50000", html)
        self.assertIn("KG_RELATION_ENTITY_LIMIT", html)
        self.assertIn("KG_MAX_RELATION_SENTENCES", html)
        self.assertIn("KG_MAX_GRAPH_EDGES", html)
        self.assertIn("selectRelationEntityNames", html)
        self.assertIn("selectRelationSentences", html)
        self.assertIn("resolveKgQueryCollection", html)
        self.assertIn("collection: resolveKgQueryCollection()", html)
        self.assertIn("ACTIVE_COLLECTION_STORAGE_KEY", html)
        self.assertIn("function activateRagCollection", html)
        self.assertIn("syncActiveCollectionInputs", html)
        self.assertIn("rememberActiveCollection", html)
        self.assertIn('id="kgPublicBooksJsonCollection" type="text" value="power_rag_corpus"', html)
        self.assertIn('id="kgQuestionFlow"', html)
        self.assertIn('data-flow-node="router"', html)
        self.assertIn('data-flow-node="full-contact-scan"', html)
        self.assertIn('data-flow-node="evidence-audit"', html)
        self.assertIn('id="kgSearchTopK" type="number" min="1" max="100" value="100"', html)
        self.assertIn('id="searchTopK" type="number" min="1" max="100" value="100"', html)
        self.assertIn('id="benchTopK" type="number" min="1" max="100" value="5"', html)
        self.assertIn("Math.min(100, topK", html)
        self.assertIn('topK: Number($("kgSearchTopK")?.value || 100)', html)
        self.assertIn('topK: Number(els.searchTopK?.value || 100)', html)
        self.assertIn('top_k: String(Number(els.searchTopK?.value || 100))', html)
        self.assertIn("edges.size >= KG_MAX_GRAPH_EDGES", html)
        self.assertNotIn("entityNames.filter(e => sentence.includes(e))", html)
        self.assertIn("saveLocalWorkspaceSnapshot", html)
        self.assertIn("restoreLocalWorkspaceSnapshot", html)
        self.assertIn("await restoreLocalWorkspaceSnapshot()", html)
        self.assertIn('void saveLocalWorkspaceSnapshot("process")', html)
        self.assertIn('void saveLocalWorkspaceSnapshot("kg-build")', html)
        self.assertNotIn("kgGraph: serializeKgGraphSnapshot()", html)
        self.assertNotIn("hydrateKgGraphSnapshot(snapshot.kgGraph)", html)
        self.assertNotIn('void syncKgGraphToBackend("restore")', html)
        self.assertIn('await resetKgBackendGraph("restore")', html)

    def test_unified_query_accepts_100_evidence_items(self) -> None:
        api_path = PROJECT_ROOT / "src" / "chroma_rag_poc" / "api.py"
        source = api_path.read_text(encoding="utf-8")

        self.assertIn("top_k: int = Field(default=8, ge=1, le=100)", source)
        self.assertIn("top_k: int = Field(default=5, ge=1, le=100)", source)
        self.assertIn("global_community_limit: int = Field(default=12, ge=1, le=30)", source)
        self.assertIn("max_communities=min(payload.top_k, payload.global_community_limit)", source)

        routes_path = PROJECT_ROOT / "src" / "chroma_rag_poc" / "routes_graphrag.py"
        routes_source = routes_path.read_text(encoding="utf-8")
        self.assertIn("max_communities: int = Field(default=100, ge=1, le=100", routes_source)

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

    def test_graphrag_import_snapshot_creates_default_graph_store(self) -> None:
        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)

        response = client.post(
            "/api/graphrag/import",
            json={
                "graph": {
                    "nodes": [
                        {"id": "Alice", "type": "Person"},
                        {"id": "Bob", "type": "Person"},
                        {"id": "Carol", "type": "Person"},
                    ],
                    "links": [
                        {
                            "id": "edge-1",
                            "source": "Alice",
                            "target": "Bob",
                            "relation": "RELATES_TO",
                            "weight": 2,
                            "evidence": "Alice and Bob exchanged intimate messages.",
                        }
                    ],
                }
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["node_count"], 2)
        self.assertEqual(payload["edge_count"], 1)
        self.assertEqual(payload["evidence_count"], 1)
        self.assertEqual(payload["community_count"], 1)
        self.assertFalse(payload["isolated_nodes_preserved"])
        self.assertEqual(Path(payload["graph_db_path"]), self.persist_dir / "graph_store.sqlite")
        self.assertTrue((self.persist_dir / "graph_store.sqlite").exists())

        stats_response = client.post("/api/graphrag/stats", json={"graph_db_path": "graph_store.sqlite"})
        self.assertEqual(stats_response.status_code, 200)
        self.assertEqual(stats_response.json()["node_count"], 2)
        self.assertEqual(stats_response.json()["community_info"]["summary_count"], 1)
        from rag_orchestrator.graph_quality import evaluate_graph_quality
        from storage_layer.graph_store import GraphStore

        store = GraphStore(self.persist_dir / "graph_store.sqlite")
        export = store.export_graph()
        summary_metadata = export["community_summaries"][0]["metadata"]
        self.assertEqual(summary_metadata["evidence_triple_ids"], ["edge-1"])
        self.assertEqual(evaluate_graph_quality(store).gate_status, "pass")

    def test_graphrag_reset_removes_default_graph_store(self) -> None:
        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)

        import_response = client.post(
            "/api/graphrag/import",
            json={
                "graph": {
                    "nodes": [
                        {"id": "Alice", "type": "Person"},
                        {"id": "Bob", "type": "Person"},
                    ],
                    "links": [
                        {
                            "source": "Alice",
                            "target": "Bob",
                            "relation": "RELATES_TO",
                            "evidence": "Alice and Bob exchanged messages.",
                        }
                    ],
                }
            },
        )
        self.assertEqual(import_response.status_code, 200)
        graph_db_path = self.persist_dir / "graph_store.sqlite"
        self.assertTrue(graph_db_path.exists())

        reset_response = client.post("/api/graphrag/reset", json={"graph_db_path": "graph_store.sqlite"})

        self.assertEqual(reset_response.status_code, 200)
        payload = reset_response.json()
        self.assertEqual(Path(payload["graph_db_path"]), graph_db_path)
        self.assertTrue(payload["deleted"])
        self.assertFalse(graph_db_path.exists())
        self.assertFalse(Path(str(graph_db_path) + "-wal").exists())
        self.assertFalse(Path(str(graph_db_path) + "-shm").exists())

    def test_graphrag_triage_history_starts_empty(self) -> None:
        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)

        response = client.get("/api/graphrag/triage")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"items": []})

    def test_graphrag_triage_filters_export_and_promotes_regression_case(self) -> None:
        from rag_orchestrator.triage import GraphRagTriageStore

        store = GraphRagTriageStore(self.persist_dir / "graphrag_triage.jsonl")
        failing = store.append(
            {
                "question": "Why did the graph summary fail?",
                "graph_quality_status": "fail",
                "route": {"strategy": "GLOBAL_SEARCH"},
                "source_evidence_count": 0,
                "citation_count": 0,
            }
        )
        store.review(failing["id"], review_status="rejected", review_note="summary has no source span")
        passing = store.append(
            {
                "question": "Which evidence passed?",
                "graph_quality_status": "pass",
                "route": {"strategy": "LOCAL_SEARCH"},
                "source_evidence_count": 2,
                "citation_count": 3,
            }
        )
        store.review(passing["id"], review_status="accepted", review_note="looks grounded")

        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)

        filtered = client.get(
            "/api/graphrag/triage",
            params={
                "graph_quality_status": "fail",
                "review_status": "rejected",
                "route_strategy": "GLOBAL_SEARCH",
            },
        )
        self.assertEqual(filtered.status_code, 200)
        filtered_items = filtered.json()["items"]
        self.assertEqual([item["id"] for item in filtered_items], [failing["id"]])

        export_response = client.get(
            "/api/graphrag/triage/export",
            params={"graph_quality_status": "fail"},
        )
        self.assertEqual(export_response.status_code, 200)
        self.assertIn("application/x-ndjson", export_response.headers["content-type"])
        exported = [orjson.loads(line) for line in export_response.text.splitlines() if line.strip()]
        self.assertEqual([item["id"] for item in exported], [failing["id"]])

        promote_response = client.post(
            f"/api/graphrag/triage/{failing['id']}/promote",
            json={
                "expected_evidence_keywords": ["source span", "graph quality"],
                "reference_answer": "Graph answers must have source evidence before they can be trusted.",
                "grading_notes": "Regression case promoted from rejected triage.",
            },
        )
        self.assertEqual(promote_response.status_code, 200)
        promoted = promote_response.json()
        self.assertEqual(promoted["case"]["question"], "Why did the graph summary fail?")
        self.assertEqual(promoted["case"]["task_type"], "graphrag_triage")
        self.assertEqual(promoted["case"]["expected_modes"], ["global"])
        dataset_path = Path(promoted["dataset_path"])
        self.assertTrue(dataset_path.exists())
        dataset_records = [orjson.loads(line) for line in dataset_path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(dataset_records[0]["id"], promoted["case"]["id"])
        self.assertEqual(dataset_records[0]["expected_evidence_keywords"], ["source span", "graph quality"])

        refreshed = client.get(f"/api/graphrag/triage/{failing['id']}")
        self.assertEqual(refreshed.status_code, 200)
        self.assertEqual(refreshed.json()["evaluation_case_id"], promoted["case"]["id"])

    def test_graph_retriever_falls_back_to_community_summary_for_broad_queries(self) -> None:
        from retrieval_engine.graph import SQLiteGraphRetriever
        from storage_layer.graph_store import GraphEdgeRecord, GraphStore

        graph_db_path = self.persist_dir / "graph_store.sqlite"
        store = GraphStore(graph_db_path)
        store.initialize(reset=True)
        store.import_edges(
            [
                GraphEdgeRecord(
                    triple_id="T1",
                    subject="小琳",
                    predicate="RELATES_TO",
                    object_name="喜欢你",
                    evidence="小琳说喜欢你。",
                    source_file="wechat_private_chunks_rag.json",
                )
            ],
            reset=False,
        )
        store.store_communities(
            [{"community_id": "C0", "node_name": "小琳"}],
            level=0,
        )
        store.store_community_summaries(
            [
                {
                    "community_id": "C0",
                    "title": "私聊暧昧关系",
                    "summary": "该社区包含私聊联系人、喜欢你、宝宝、想你等暧昧关系线索。",
                    "entity_count": 12,
                    "edge_count": 4,
                }
            ],
            level=0,
        )

        retriever = SQLiteGraphRetriever(store, include_community_summaries=True)
        results = retriever.retrieve("请执行全量私聊联系人级暧昧关系分析", top_k=5)

        self.assertTrue(results)
        self.assertEqual(results[0].retriever_name, "graph")
        self.assertIn("暧昧关系线索", results[0].chunk.text)

    def test_unified_query_route_uses_router_text_and_global_context(self) -> None:
        """Unified query should connect router, text retrieval, and community global context."""
        from storage_layer.graph_store import GraphEdgeRecord, GraphStore

        graph_db_path = self.persist_dir / "graph_store.sqlite"
        store = GraphStore(graph_db_path)
        store.initialize(reset=True)
        store.import_edges(
            [
                GraphEdgeRecord(
                    triple_id="T1",
                    subject="燃气轮机维护",
                    predicate="关注",
                    object_name="状态监测",
                    confidence=0.9,
                    evidence="维护记录强调状态监测、温度和振动趋势。",
                    source_file="maintenance.md",
                )
            ],
            reset=False,
        )
        store.store_communities(
            [
                {"community_id": "C0", "node_name": "燃气轮机维护"},
                {"community_id": "C0", "node_name": "状态监测"},
            ],
            level=0,
        )
        store.store_community_summaries(
            [
                {
                    "community_id": "C0",
                    "title": "维护与监测",
                    "summary": "该社区总结了燃气轮机维护、状态监测、温度和振动趋势之间的关系。",
                    "entity_count": 2,
                    "edge_count": 1,
                    "metadata": {
                        "evidence_triple_ids": ["T1"],
                        "sentence_evidence": [
                            {
                                "sentence_index": 0,
                                "evidence_triple_ids": ["T1"],
                                "source_evidence": [
                                    {
                                        "triple_id": "T1",
                                        "text": "维护记录强调状态监测、温度和振动趋势。",
                                        "source_file": "maintenance.md",
                                    }
                                ],
                            }
                        ],
                    },
                }
            ],
            level=0,
        )

        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)
        fake_llm = FakeUnifiedQueryLLM()

        with patch("chroma_rag_poc.api.OpenAICompatibleLLMClient", return_value=fake_llm), patch(
            "chroma_rag_poc.api.query_collection",
            return_value={
                "results": [
                    {
                        "id": "chunk-1",
                        "text": "燃气轮机维护需要结合温度、振动和状态监测记录。",
                        "source": "maintenance.md",
                        "score": 0.92,
                        "metadata": {"source_file": "maintenance.md", "chunk_index": 0},
                    }
                ]
            },
        ):
            response = client.post(
                "/api/query",
                json={
                    "question": "整体上燃气轮机维护最常见的问题是什么？",
                    "collection": "api-demo",
                    "graph_db_path": str(graph_db_path),
                    "llm_api_key": "test-key",
                    "llm_base_url": "https://llm.example/v1",
                    "llm_model": "fake-model",
                    "top_k": 3,
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["route"]["strategy"], "GLOBAL_SEARCH")
        self.assertEqual(payload["route"]["task_route"], "GLOBAL_SUMMARY")
        self.assertIn("统一问答已结合文本证据", payload["answer"])
        self.assertIn("## Text retrieval evidence", payload["context"])
        self.assertIn("## Global context", payload["context"])
        self.assertTrue(any(item["source_type"] == "text" for item in payload["citations"]))
        self.assertTrue(any(item["source_type"] == "graph" for item in payload["citations"]))
        community_sources = [
            item
            for item in payload["citations"]
            if item["source_type"] == "graph_community_source"
        ]
        self.assertTrue(community_sources)
        self.assertEqual(community_sources[0]["raw_id"], "T1")
        self.assertEqual(community_sources[0]["source"], "maintenance.md")
        self.assertEqual(community_sources[0]["metadata"]["community_id"], "C0")
        self.assertNotIn("No graph retrieval evidence returned.", payload["context"])
        self.assertEqual(payload["capabilities"]["text"], True)
        self.assertEqual(payload["capabilities"]["graph"], True)
        self.assertEqual(payload["capabilities"]["global"], True)
        self.assertEqual(payload["graph_quality"]["quality_gate"]["status"], "pass")
        diagnostics = payload["lightrag_diagnostics"]
        self.assertEqual(diagnostics["question"], "整体上燃气轮机维护最常见的问题是什么？")
        self.assertEqual(diagnostics["mode"], "mix")
        self.assertEqual(diagnostics["route_strategy"], "GLOBAL_SEARCH")
        self.assertEqual(diagnostics["naive_count"], 1)
        self.assertGreaterEqual(diagnostics["local_count"], 1)
        self.assertEqual(diagnostics["global_count"], 1)
        self.assertEqual(diagnostics["final_count"], len(payload["citations"]))
        self.assertIn("global", diagnostics["active_paths"])
        self.assertRegex(payload["triage_id"], r"^triage-")

        triage_response = client.get("/api/graphrag/triage")
        self.assertEqual(triage_response.status_code, 200)
        triage_items = triage_response.json()["items"]
        self.assertEqual(len(triage_items), 1)
        self.assertEqual(triage_items[0]["id"], payload["triage_id"])
        self.assertEqual(triage_items[0]["graph_quality_status"], "pass")
        self.assertEqual(triage_items[0]["source_evidence_count"], 1)
        self.assertEqual(triage_items[0]["review_status"], "unreviewed")
        self.assertEqual(triage_items[0]["lightrag_diagnostics"]["route_strategy"], "GLOBAL_SEARCH")

        review_response = client.post(
            f"/api/graphrag/triage/{payload['triage_id']}/review",
            json={"review_status": "accepted", "review_note": "evidence matches the answer"},
        )
        self.assertEqual(review_response.status_code, 200)
        self.assertEqual(review_response.json()["review_status"], "accepted")

    def test_unified_query_returns_user_facing_fallback_when_graph_quality_fails(self) -> None:
        from storage_layer.graph_store import GraphEdgeRecord, GraphStore

        graph_db_path = self.persist_dir / "unsafe_graph.sqlite"
        store = GraphStore(graph_db_path)
        store.initialize(reset=True)
        store.import_edges(
            [
                GraphEdgeRecord(
                    triple_id="unsafe-1",
                    subject="Combustor",
                    predicate="CAUSES",
                    object_name="Noise",
                    confidence=0.2,
                    evidence=None,
                    source_file="unsafe.md",
                )
            ],
            reset=False,
        )

        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)

        with patch("chroma_rag_poc.api.OpenAICompatibleLLMClient", return_value=FakeUnifiedQueryLLM()), patch(
            "chroma_rag_poc.api.query_collection",
            return_value={"results": [{"text": "text evidence", "metadata": {"source_file": "manual.md"}}]},
        ):
            response = client.post(
                "/api/query",
                json={
                    "question": "What does the unsafe graph say?",
                    "collection": "api-demo",
                    "graph_db_path": str(graph_db_path),
                    "llm_api_key": "test-key",
                    "mode": "local",
                    "top_k": 3,
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["graph_quality"]["quality_gate"]["status"], "fail")
        self.assertEqual(payload["graph_quality_blocked"], True)
        self.assertIn("Result:", payload["answer"])
        self.assertIn("text retrieval", payload["answer"])
        self.assertIn("text evidence", payload["answer"])
        self.assertNotIn("Graph quality gate failed before GraphRAG answering", payload["answer"])
        self.assertNotRegex(payload["answer"], r"edge-\d+")
        failure_metrics = {failure["metric"] for failure in payload["graph_quality"]["quality_gate"]["failures"]}
        self.assertIn("evidence_coverage", failure_metrics)
        self.assertIn("low_confidence_edge_rate", failure_metrics)

    def test_unified_query_global_summary_ignores_isolated_noise_nodes(self) -> None:
        from storage_layer.graph_store import GraphEdgeRecord, GraphStore

        graph_db_path = self.persist_dir / "isolated_noise_graph.sqlite"
        store = GraphStore(graph_db_path)
        store.initialize(reset=True)
        store.import_edges(
            [
                GraphEdgeRecord(
                    triple_id="T1",
                    subject="Rental chat corpus",
                    predicate="HAS_TOPIC",
                    object_name="Housing discussion",
                    confidence=0.9,
                    evidence="The corpus contains WeChat records about housing and rental discussion.",
                    source_file="wechat_private_chunks_rag.json",
                    source_chunk_id="chunk-1",
                )
            ],
            reset=False,
        )
        store.upsert_nodes([{"id": "qlogo", "type": "metadata_noise"}])
        store.store_communities(
            [
                {"community_id": "C0", "node_name": "Rental chat corpus"},
                {"community_id": "C0", "node_name": "Housing discussion"},
                {"community_id": "C0", "node_name": "qlogo"},
            ],
            level=0,
        )
        store.store_community_summaries(
            [
                {
                    "community_id": "C0",
                    "title": "Corpus overview",
                    "summary": "The community summarizes the dataset as private chat records discussing housing and rental topics.",
                    "entity_count": 3,
                    "edge_count": 1,
                    "metadata": {
                        "evidence_triple_ids": ["T1"],
                        "sentence_evidence": [
                            {
                                "sentence_index": 0,
                                "evidence_triple_ids": ["T1"],
                                "source_evidence": [
                                    {
                                        "triple_id": "T1",
                                        "text": "The corpus contains WeChat records about housing and rental discussion.",
                                        "source_file": "wechat_private_chunks_rag.json",
                                        "source_chunk_id": "chunk-1",
                                    }
                                ],
                            }
                        ],
                    },
                }
            ],
            level=0,
        )

        app = create_app(persist_dir=self.persist_dir, upload_dir=self.upload_dir)
        client = TestClient(app)
        with patch("chroma_rag_poc.api.OpenAICompatibleLLMClient", return_value=FakeUnifiedQueryLLM()), patch(
            "chroma_rag_poc.api.query_collection",
            return_value={"results": []},
        ):
            response = client.post(
                "/api/query",
                json={
                    "question": "Overall, what kind of material did I input here?",
                    "collection": "api-demo",
                    "graph_db_path": str(graph_db_path),
                    "llm_api_key": "test-key",
                    "llm_base_url": "https://llm.example/v1",
                    "llm_model": "fake-model",
                    "mode": "global",
                    "top_k": 3,
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["route"]["strategy"], "GLOBAL_SEARCH")
        self.assertEqual(payload["route"]["task_route"], "GLOBAL_SUMMARY")
        self.assertFalse(payload["graph_quality_blocked"])
        self.assertEqual(payload["graph_quality"]["quality_gate"]["status"], "pass")
        self.assertGreaterEqual(payload["graph_quality"]["metrics"]["ignored_isolated_node_count"], 1)
        self.assertIn("qlogo", payload["graph_quality"]["details"]["ignored_isolated_noise_nodes"])
        failure_metrics = {failure["metric"] for failure in payload["graph_quality"]["quality_gate"]["failures"]}
        self.assertEqual(failure_metrics, set())
        self.assertNotIn("the graph was not used", payload["answer"])
        self.assertGreaterEqual(payload["lightrag_diagnostics"]["global_count"], 1)
        self.assertGreaterEqual(payload["lightrag_diagnostics"]["final_count"], 1)
        self.assertTrue(any(item["source_type"] == "graph_community_source" for item in payload["citations"]))

    def test_frontend_rag_ask_calls_unified_query_api(self) -> None:
        repo_root = PROJECT_ROOT.parents[2]
        frontend_path = repo_root / "frontend_app" / "current_console" / "index.html"
        html = frontend_path.read_text(encoding="utf-8")

        self.assertIn("async function requestUnifiedQuery", html)
        self.assertIn('requestJson("/api/query"', html)
        self.assertIn("renderUnifiedQueryAnswer", html)
        self.assertIn("formatContactAnalysisMarkdown", html)
        self.assertIn("private_contact_affection_sweep", html)
        self.assertIn("formatPartitionAnalysisMarkdown", html)
        self.assertIn("generic_partition_evidence_sweep", html)
        self.assertIn("formatGraphQualityGateMarkdown", html)
        self.assertIn("formatUnifiedQueryErrorMarkdown", html)
        self.assertIn("formatCollectionResolutionMarkdown", html)
        self.assertIn("result?.resolved_collection", html)
        self.assertIn("query-resolved-collection", html)
        self.assertIn("syncFilesToBackendRagIndex", html)
        self.assertIn('requestJson("/api/ingest"', html)
        self.assertIn("Clearing backend RAG collection", html)
        self.assertIn("graph_quality_bypassed", html)
        self.assertIn("graph_quality_gate_failed", html)
        self.assertIn("error.detail = payload.detail", html)
        self.assertIn("runKgAskBackend", html)
        self.assertIn("private_contact_term_evidence_sweep", html)
        self.assertIn("async function syncKgGraphToBackend", html)
        self.assertIn('await syncKgGraphToBackend("kg-build")', html)
        self.assertIn('await clearKgRuntimeState("kg-build-start"', html)
        self.assertNotIn('void syncKgGraphToBackend("restore")', html)

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
