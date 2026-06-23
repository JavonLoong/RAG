from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from chroma_rag_poc.api import create_app
from chroma_rag_poc.observability import OperationLogger


class OperationLogProgressApiTest(unittest.TestCase):
    def test_log_progress_reports_running_and_finished_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log_dir = root / "logs"
            app = create_app(
                persist_dir=root / "chroma",
                upload_dir=root / "uploads",
                log_dir=log_dir,
                frontend_dir=root / "frontend",
            )
            client = TestClient(app)

            logger = OperationLogger(log_dir, "process", collection_name="demo")
            with logger.stage("read_upload_files", file_count=1):
                pass

            running = client.get(f"/api/logs/{logger.file_name}/progress").json()
            self.assertEqual(running["status"], "running")
            self.assertGreater(running["percent"], 0)
            self.assertEqual(running["current_stage"], "read_upload_files")
            self.assertGreaterEqual(running["event_count"], 3)

            logger.close(status="ok")
            finished = client.get(f"/api/logs/{logger.file_name}/progress").json()
            self.assertEqual(finished["status"], "ok")
            self.assertEqual(finished["percent"], 100)
            self.assertEqual(finished["last_event"], "operation_end")


if __name__ == "__main__":
    unittest.main()
