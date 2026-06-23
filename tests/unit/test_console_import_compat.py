from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path


class ConsoleImportCompatTests(unittest.TestCase):
    def test_console_api_imports_with_installed_chromadb_numpy_stack(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        console_src = repo_root / "api_server" / "current_console" / "chroma_rag_poc" / "src"
        code = (
            "import sys; "
            f"sys.path.insert(0, {str(console_src)!r}); "
            "import chroma_rag_poc.api; "
            "print('console-api-import-ok')"
        )

        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=repo_root,
            text=True,
            capture_output=True,
            timeout=45,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("console-api-import-ok", result.stdout)

    def test_numpy_alias_patch_restores_missing_legacy_aliases(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        console_src = repo_root / "api_server" / "current_console" / "chroma_rag_poc" / "src"
        code = (
            "import sys; "
            f"sys.path.insert(0, {str(console_src)!r}); "
            "import numpy as np; "
            "deleted = []; "
            "\nfor alias in ('float_', 'complex_'):\n"
            "    if hasattr(np, alias):\n"
            "        delattr(np, alias)\n"
            "        deleted.append(alias)\n"
            "import chroma_rag_poc; "
            "assert np.float_ is np.float64; "
            "assert np.complex_ is np.complex128; "
            "print('numpy-alias-patch-ok', ','.join(deleted))"
        )

        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=repo_root,
            text=True,
            capture_output=True,
            timeout=45,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("numpy-alias-patch-ok", result.stdout)

    def test_chromadb_sqlite_seq_id_patch_accepts_integer_seq_ids(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        console_src = repo_root / "api_server" / "current_console" / "chroma_rag_poc" / "src"
        code = (
            "import sys; "
            f"sys.path.insert(0, {str(console_src)!r}); "
            "import chroma_rag_poc; "
            "import chromadb.segment.impl.metadata.sqlite as sqlite_metadata; "
            "assert sqlite_metadata._decode_seq_id(29704) == 29704; "
            "assert sqlite_metadata._decode_seq_id((5).to_bytes(8, 'big')) == 5; "
            "print('chromadb-seq-id-patch-ok')"
        )

        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=repo_root,
            text=True,
            capture_output=True,
            timeout=45,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("chromadb-seq-id-patch-ok", result.stdout)


if __name__ == "__main__":
    unittest.main()
