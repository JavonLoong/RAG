from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CLI = REPO_ROOT / "scripts" / "knowledge_base_cli.py"
EXAMPLE = REPO_ROOT / "configs" / "knowledge_base.example.json"
M2_EXAMPLE = REPO_ROOT / "configs" / "m2_to_m3.example.json"


class KnowledgeBaseCliTests(unittest.TestCase):
    def test_candidate_review_publish_verify_and_search_commands(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "knowledge.sqlite3"

            init = self.run_cli(database, "init")
            self.assertEqual(init["status"], "ok")
            candidate = self.run_cli(
                database,
                "create-candidate",
                "--input",
                str(EXAMPLE),
                "--actor",
                "m2-parser",
            )
            revision_id = candidate["revision_id"]
            self.run_cli(database, "submit-review", "--revision", revision_id, "--actor", "m2-parser")
            self.run_cli(
                database,
                "review",
                "--revision",
                revision_id,
                "--decision",
                "approved",
                "--reviewer",
                "domain-reviewer",
            )
            release = self.run_cli(
                database,
                "publish",
                "--revision",
                revision_id,
                "--actor",
                "m3-publisher",
            )
            self.assertEqual(release["version"], 1)
            report = self.run_cli(database, "verify", "--version", "1")
            self.assertTrue(report["passed"])
            hits = self.run_cli(database, "search", "压气机清洗", "--mode", "keyword")
            self.assertTrue(hits)
            self.assertEqual(hits[0]["document_id"], "gas-turbine-compressor-manual")

            snapshot_path = Path(directory) / "m3-snapshot.json"
            exported = self.run_cli(
                database,
                "export-snapshot",
                "--version",
                "1",
                "--output",
                str(snapshot_path),
            )
            self.assertEqual(exported["schema_version"], "power-rag.m3-snapshot.v1")
            snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
            self.assertEqual(snapshot["release"]["version"], 1)
            self.assertTrue(snapshot["documents"][0]["chunks"])

    def test_accept_m2_command_imports_approved_review_package(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "knowledge.sqlite3"
            revision = self.run_cli(
                database,
                "accept-m2",
                "--input",
                str(M2_EXAMPLE),
                "--actor",
                "m2-adapter",
            )
            self.assertEqual(revision["status"], "pending_review")
            self.assertEqual(revision["review_decision"], "approved")

    @staticmethod
    def run_cli(database: Path, *arguments: str):
        completed = subprocess.run(  # noqa: S603 -- executable and arguments are fixed test fixtures.
            [sys.executable, str(CLI), "--db", str(database), *arguments],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        return json.loads(completed.stdout)


if __name__ == "__main__":
    unittest.main()
