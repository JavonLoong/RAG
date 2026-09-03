from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from knowledge_base import (
    KnowledgeBaseError,
    KnowledgeBaseStore,
    M2HandoffService,
    M2IssueSeverity,
    M2QualityIssue,
    M2ReviewStatus,
    ReviewDecision,
    RevisionStatus,
    m2_handoff_from_payload,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
M2_EXAMPLE = REPO_ROOT / "configs" / "m2_to_m3.example.json"


class KnowledgeBaseInterfaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = KnowledgeBaseStore(Path(self.temp_dir.name) / "knowledge.sqlite3")
        self.handoff = m2_handoff_from_payload(json.loads(M2_EXAMPLE.read_text(encoding="utf-8")))

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_approved_m2_handoff_is_preserved_and_exported_for_m4(self) -> None:
        revision = M2HandoffService(self.store).accept(self.handoff, actor="m2-adapter")

        self.assertEqual(revision.status, RevisionStatus.PENDING_REVIEW)
        self.assertEqual(revision.review_decision, ReviewDecision.APPROVED)
        release = self.store.publish([revision.revision_id], actor="m3-publisher")
        snapshot = self.store.export_snapshot(release.version)

        self.assertEqual(snapshot.schema_version, "power-rag.m3-snapshot.v1")
        self.assertEqual(snapshot.release.manifest_sha256, release.manifest_sha256)
        self.assertEqual(len(snapshot.documents), 1)
        document = snapshot.documents[0]
        self.assertEqual(document.document_id, "gas-turbine-compressor-manual")
        self.assertEqual(document.metadata["m2_handoff"]["reviewer"], "m2-human-reviewer")
        self.assertEqual(document.pages[0].blocks[0].block_id, "page-7-title-1")
        self.assertEqual(document.assets[0].block_id, "page-7-paragraph-1")
        self.assertTrue(document.chunks)
        self.assertTrue(document.chunks[0].evidence)
        self.assertEqual(document.chunks[0].evidence[0].document_id, document.document_id)

    def test_m2_handoff_rejects_unapproved_incomplete_or_blocking_input(self) -> None:
        service = M2HandoffService(self.store)
        cases = (
            (
                replace(self.handoff, review_status=M2ReviewStatus.PENDING),
                "M2_REVIEW_NOT_APPROVED",
            ),
            (
                replace(self.handoff, evidence_coverage=0.99),
                "M2_EVIDENCE_INCOMPLETE",
            ),
            (
                replace(
                    self.handoff,
                    quality_issues=(
                        M2QualityIssue(
                            code="TABLE_ORDER_INVALID",
                            message="Table cells require review.",
                            severity=M2IssueSeverity.BLOCKING,
                        ),
                    ),
                ),
                "M2_BLOCKING_ISSUES",
            ),
        )
        for handoff, code in cases:
            with self.subTest(code=code), self.assertRaises(KnowledgeBaseError) as raised:
                service.accept(handoff, actor="m2-adapter")
            self.assertEqual(raised.exception.code, code)

    def test_accept_is_idempotent_for_the_same_approved_handoff(self) -> None:
        service = M2HandoffService(self.store)
        first = service.accept(self.handoff, actor="m2-adapter")
        second = service.accept(self.handoff, actor="m2-adapter")

        self.assertEqual(first.revision_id, second.revision_id)
        self.assertEqual(second.review_decision, ReviewDecision.APPROVED)


if __name__ == "__main__":
    unittest.main()
