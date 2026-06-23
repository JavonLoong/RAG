from __future__ import annotations

import unittest

from rag_orchestrator.global_search import GlobalSearchOrchestrator


class FakeGraphStore:
    def get_community_summaries(self, *, level: int = 0):
        return [
            {
                "community_id": f"C{i}",
                "title": f"Community {i}",
                "summary": f"Summary text {i}",
                "entity_count": 100 - i,
                "metadata": {
                    "sentence_evidence": [
                        {
                            "sentence_index": 0,
                            "source_evidence": [
                                {
                                    "triple_id": f"edge-{i}",
                                    "text": f"source evidence {i}",
                                    "source_file": "fixture.json",
                                }
                            ],
                        }
                    ]
                },
            }
            for i in range(10)
        ]


class ExplodingLLM:
    def generate(self, prompt: str) -> str:
        raise AssertionError("context_only global search must not call the LLM")


class GlobalSearchContextOnlyTests(unittest.TestCase):
    def test_context_only_returns_summary_context_without_map_llm_calls(self) -> None:
        searcher = GlobalSearchOrchestrator(
            graph_store=FakeGraphStore(),
            llm_client=ExplodingLLM(),
            max_communities=3,
        )

        result = searcher.search("我是谁？", context_only=True)

        self.assertTrue(result.context_only)
        self.assertEqual(result.communities_searched, 3)
        self.assertEqual(result.communities_relevant, 3)
        self.assertEqual([item["community_id"] for item in result.partial_answers], ["C0", "C1", "C2"])
        self.assertEqual(result.partial_answers[0]["answer"], "Summary text 0")
        self.assertEqual(result.partial_answers[0]["source_evidence"][0]["text"], "source evidence 0")


if __name__ == "__main__":
    unittest.main()
