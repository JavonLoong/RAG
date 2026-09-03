from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from knowledge_base import (
    BlockInput,
    DocumentInput,
    KnowledgeBaseError,
    KnowledgeBaseQueryService,
    KnowledgeBaseStore,
    PageInput,
    ReviewDecision,
    RevisionStatus,
    SearchMode,
)


class TinyEmbedder:
    def embed(self, texts: list[str]) -> list[list[float]]:
        return [
            [
                float(text.casefold().count("compressor") + text.count("压气机")),
                float(text.casefold().count("turbine") + text.count("燃气轮机")),
                float(text.casefold().count("wash") + text.count("清洗")),
            ]
            for text in texts
        ]

    def embed_query(self, text: str) -> list[float]:
        return self.embed([text])[0]


def document(document_id: str, text: str, *, page: int = 1) -> DocumentInput:
    return DocumentInput(
        document_id=document_id,
        title=f"Manual {document_id}",
        source_uri=f"sources/{document_id}.pdf",
        media_type="application/pdf",
        pages=(
            PageInput(
                page,
                (
                    BlockInput("压气机维护", "title", 0),
                    BlockInput(text, "paragraph", 1),
                ),
            ),
        ),
        metadata={"source_trust": "reviewed"},
    )


class KnowledgeBaseLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.store = KnowledgeBaseStore(self.root / "knowledge.sqlite3")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def approve(self, revision_id: str) -> None:
        pending = self.store.submit_for_review(revision_id, actor="parser-owner")
        self.assertEqual(pending.status, RevisionStatus.PENDING_REVIEW)
        approved = self.store.record_review(
            revision_id,
            decision=ReviewDecision.APPROVED,
            reviewer="domain-reviewer",
            comment="Evidence checked against the source page.",
        )
        self.assertEqual(approved.review_decision, ReviewDecision.APPROVED)

    def test_candidate_review_vector_index_publish_and_hybrid_query(self) -> None:
        revision = self.store.create_candidate(
            document("compressor", "压气机叶片积垢会降低效率，应按维护规程进行 compressor wash 清洗。"),
            created_by="m2",
            chunk_size=32,
            overlap=5,
        )
        duplicate = self.store.create_candidate(
            document("compressor", "压气机叶片积垢会降低效率，应按维护规程进行 compressor wash 清洗。"),
            created_by="m2",
            chunk_size=32,
            overlap=5,
        )
        self.assertEqual(duplicate.revision_id, revision.revision_id)

        self.approve(revision.revision_id)
        indexed = self.store.index_embeddings(
            revision_ids=[revision.revision_id],
            embedding_model="tiny-v1",
            embedder=TinyEmbedder(),
        )
        self.assertGreater(indexed["indexed"], 0)
        release = self.store.publish(
            [revision.revision_id],
            actor="publisher",
            expected_base_version=None,
            require_embeddings=True,
            embedding_model="tiny-v1",
        )
        self.assertEqual(release.version, 1)
        self.assertEqual(release.document_count, 1)
        self.assertEqual(self.store.get_revision(revision.revision_id).status, RevisionStatus.PUBLISHED)

        service = KnowledgeBaseQueryService(self.store)
        hits = service.search(
            "压气机为什么需要清洗",
            mode=SearchMode.HYBRID,
            version=release.version,
            embedder=TinyEmbedder(),
            embedding_model="tiny-v1",
        )
        self.assertTrue(hits)
        self.assertEqual(hits[0].document_id, "compressor")
        self.assertTrue(hits[0].evidence)
        self.assertEqual(hits[0].evidence[0].page_number, 1)
        self.assertIn("keyword", hits[0].component_scores)

        answer = service.answer("积垢如何处理？", mode=SearchMode.KEYWORD, version=1)
        self.assertFalse(answer.no_answer)
        self.assertTrue(answer.citations)
        self.assertEqual(answer.citations[0].source_uri, "sources/compressor.pdf")

    def test_incremental_release_compare_deprecate_and_rollback(self) -> None:
        first = self.store.create_candidate(document("a", "燃气轮机 compressor inspection guidance。"), created_by="m2")
        self.approve(first.revision_id)
        release_one = self.store.publish([first.revision_id], actor="publisher")

        second = self.store.create_candidate(document("b", "Turbine bearing inspection guidance。"), created_by="m2")
        self.approve(second.revision_id)
        release_two = self.store.publish(
            [second.revision_id], actor="publisher", expected_base_version=release_one.version
        )
        diff = self.store.compare_versions(1, 2)
        self.assertEqual(diff.added, ("b",))
        self.assertEqual(diff.unchanged, ("a",))

        release_three = self.store.deprecate_document("a", actor="publisher", expected_base_version=release_two.version)
        self.assertEqual(self.store.compare_versions(2, 3).removed, ("a",))

        rollback = self.store.rollback(1, actor="publisher", expected_base_version=release_three.version)
        self.assertEqual(rollback.action, "rollback")
        self.assertEqual(self.store.compare_versions(1, rollback.version).unchanged, ("a",))
        self.assertEqual(
            KnowledgeBaseQueryService(self.store).search("bearing", mode=SearchMode.KEYWORD),
            [],
        )
        self.assertTrue(self.store.verify_version(rollback.version).passed)

    def test_review_and_optimistic_version_gates_reject_invalid_transitions(self) -> None:
        revision = self.store.create_candidate(document("a", "compressor inspection"), created_by="m2")
        with self.assertRaisesRegex(KnowledgeBaseError, "approved review"):
            self.store.publish([revision.revision_id], actor="publisher")
        self.approve(revision.revision_id)
        self.store.publish([revision.revision_id], actor="publisher")

        next_revision = self.store.create_candidate(document("a", "updated compressor inspection"), created_by="m2")
        self.approve(next_revision.revision_id)
        with self.assertRaises(KnowledgeBaseError) as raised:
            self.store.publish([next_revision.revision_id], actor="publisher", expected_base_version=99)
        self.assertEqual(raised.exception.code, "VERSION_CONFLICT")

    def test_transform_fingerprint_rebuilds_chunks_and_old_release_keeps_source_snapshot(self) -> None:
        original = document("snapshot", "compressor inspection and wash guidance")
        first = self.store.create_candidate(original, created_by="m2", chunk_size=800)
        rebuilt = self.store.create_candidate(original, created_by="m2", chunk_size=24, overlap=4)
        self.assertNotEqual(first.revision_id, rebuilt.revision_id)
        self.assertNotEqual(first.pipeline_fingerprint, rebuilt.pipeline_fingerprint)

        self.approve(first.revision_id)
        self.store.publish([first.revision_id], actor="publisher")
        changed_source = DocumentInput(
            document_id=original.document_id,
            title="Renamed manual",
            source_uri="sources/renamed.pdf",
            pages=original.pages,
            media_type=original.media_type,
            metadata=original.metadata,
        )
        changed = self.store.create_candidate(changed_source, created_by="m2")
        self.approve(changed.revision_id)
        self.store.publish([changed.revision_id], actor="publisher", expected_base_version=1)

        service = KnowledgeBaseQueryService(self.store)
        old_hit = service.search("compressor", mode=SearchMode.KEYWORD, version=1)[0]
        new_hit = service.search("compressor", mode=SearchMode.KEYWORD, version=2)[0]
        self.assertEqual(old_hit.source_uri, "sources/snapshot.pdf")
        self.assertEqual(old_hit.title, "Manual snapshot")
        self.assertEqual(new_hit.source_uri, "sources/renamed.pdf")
        self.assertEqual(new_hit.title, "Renamed manual")

    def test_embedding_index_can_skip_or_force_rebuild(self) -> None:
        revision = self.store.create_candidate(document("vector", "compressor wash"), created_by="m2")
        first = self.store.index_embeddings(
            revision_ids=[revision.revision_id], embedding_model="tiny-v1", embedder=TinyEmbedder()
        )
        skipped = self.store.index_embeddings(
            revision_ids=[revision.revision_id], embedding_model="tiny-v1", embedder=TinyEmbedder()
        )
        rebuilt = self.store.index_embeddings(
            revision_ids=[revision.revision_id],
            embedding_model="tiny-v1",
            embedder=TinyEmbedder(),
            force=True,
        )
        self.assertGreater(first["indexed"], 0)
        self.assertEqual(skipped["indexed"], 0)
        self.assertEqual(skipped["skipped"], first["indexed"])
        self.assertEqual(rebuilt["indexed"], first["indexed"])

    def test_no_answer_access_filter_and_explicit_conflict_are_reported(self) -> None:
        revisions = []
        for document_id, statement in (
            ("source-a", "compressor wash interval is 100 hours"),
            ("source-b", "compressor wash interval is 200 hours"),
        ):
            base = document(document_id, statement)
            restricted = DocumentInput(
                document_id=base.document_id,
                title=base.title,
                source_uri=base.source_uri,
                pages=base.pages,
                media_type=base.media_type,
                metadata={
                    "required_access_labels": ["internal-research"],
                    "conflict_group": "compressor-wash-interval",
                },
            )
            revision = self.store.create_candidate(restricted, created_by="m2")
            self.approve(revision.revision_id)
            revisions.append(revision.revision_id)
        self.store.publish(revisions, actor="publisher")
        service = KnowledgeBaseQueryService(self.store)

        denied = service.answer(
            "compressor wash interval",
            mode=SearchMode.KEYWORD,
            allowed_access_labels={"public"},
        )
        self.assertTrue(denied.no_answer)
        self.assertEqual(denied.citations, ())

        allowed = service.answer(
            "compressor wash interval",
            mode=SearchMode.KEYWORD,
            allowed_access_labels={"internal-research"},
        )
        self.assertFalse(allowed.no_answer)
        self.assertEqual(len(allowed.conflicts), 1)
        self.assertEqual(allowed.conflicts[0].document_ids, ("source-a", "source-b"))

    def test_backup_checksum_and_restore_recover_a_known_version(self) -> None:
        revision = self.store.create_candidate(document("a", "compressor wash"), created_by="m2")
        self.approve(revision.revision_id)
        self.store.publish([revision.revision_id], actor="publisher")
        backup = self.store.create_backup(self.root / "backups", name="verified-v1")

        restored = KnowledgeBaseStore(self.root / "restored.sqlite3")
        report = restored.restore_backup(backup.database_path, backup.manifest_path)
        self.assertTrue(report.passed)
        self.assertEqual(restored.current_version(), 1)
        self.assertTrue(restored.keyword_search("compressor"))


if __name__ == "__main__":
    unittest.main()
