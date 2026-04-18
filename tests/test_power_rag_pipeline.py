import unittest

from power_rag_pipeline.pipeline import Document, TextBlock, chunk_document, clean_blocks


class PowerRagPipelineTests(unittest.TestCase):
    def test_clean_blocks_merges_short_fragments(self) -> None:
        doc = Document(
            doc_id=1,
            filename="demo.pdf",
            total_pages=1,
            blocks=[
                TextBlock("系", "Para", 1, 1, 1.0),
                TextBlock("统", "Para", 1, 1, 2.0),
                TextBlock("完整的说明文本。", "Para", 1, 1, 3.0),
            ],
        )

        cleaned = clean_blocks(doc, min_chars=3)
        self.assertEqual(len(cleaned.blocks), 1)
        self.assertIn("系统", cleaned.blocks[0].text)

    def test_chunk_document_returns_chunks(self) -> None:
        doc = Document(
            doc_id=2,
            filename="demo.pdf",
            total_pages=1,
            blocks=[
                TextBlock("第一段文本。" * 20, "Para", 1, 2, 1.0),
                TextBlock("第二段文本。" * 20, "Para", 1, 2, 2.0),
            ],
        )

        chunks = chunk_document(doc, max_chars=80, overlap=10)
        self.assertGreaterEqual(len(chunks), 2)
        self.assertTrue(all(chunk.metadata["filename"] == "demo.pdf" for chunk in chunks))


if __name__ == "__main__":
    unittest.main()
