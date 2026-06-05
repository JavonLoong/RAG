from __future__ import annotations

import unittest
import re
from pathlib import Path


class FrontendDemoModeContractTests(unittest.TestCase):
    def setUp(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        self.html = (repo_root / "frontend_app" / "current_console" / "index.html").read_text(encoding="utf-8")

    def test_public_demo_search_uses_browser_local_search_path(self) -> None:
        self.assertRegex(
            self.html,
            re.compile(r"async function runSearch\(\)\s*\{\s*if \(state\.localMode \|\| state\.publicDemo\)"),
        )

    def test_kg_artifacts_only_link_existing_served_files(self) -> None:
        self.assertIn('const KG_ARTIFACT_BASE = "/deliverables/06_四本书KG工具跑通演示/";', self.html)
        self.assertIn('const KG_FILE_ARTIFACT_BASE = "../../docs/project_deliverables/06_四本书KG工具跑通演示/";', self.html)
        self.assertIn('window.location.protocol === "file:"', self.html)
        self.assertIn('{ file: "triples.csv"', self.html)
        self.assertIn('{ file: "run_report.md"', self.html)
        self.assertNotIn('{ file: "schema.json"', self.html)
        self.assertNotIn('{ file: "triples.json"', self.html)
        self.assertNotIn('{ file: "graph.json"', self.html)

    def test_disabling_demo_mode_refreshes_backend_state(self) -> None:
        self.assertIn("state.localMode = FORCE_LOCAL_RUNTIME;", self.html)
        self.assertIn("await refreshAll();", self.html)


if __name__ == "__main__":
    unittest.main()
