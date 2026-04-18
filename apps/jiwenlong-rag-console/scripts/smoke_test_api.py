"""Simple smoke test for the local FastAPI + Chroma console."""

from __future__ import annotations

import io
import sys
import time
from pathlib import Path

import requests

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE_URL = "http://localhost:8000"
APP_DIR = Path(__file__).resolve().parent.parent
MOCK_DIR = APP_DIR / "data" / "mock-data"


def upload_mock_files() -> None:
    files = sorted(MOCK_DIR.glob("*.json"))
    if not files:
        print(f"[WARN] No mock files found in {MOCK_DIR}")
        return

    print("=" * 50)
    print("Step 1: upload mock JSON files")
    print("=" * 50)
    for path in files:
        with path.open("rb") as handle:
            response = requests.post(
                f"{BASE_URL}/api/upload",
                files={"file": (path.name, handle, "application/json")},
                timeout=120,
            )
        response.raise_for_status()
        payload = response.json()
        print(
            f"  OK {path.name}: {payload.get('size_kb', '?')} KB, "
            f"{payload.get('source_kind', '?')}"
        )


def process_uploads() -> None:
    print("\n" + "=" * 50)
    print("Step 2: process uploaded files")
    print("=" * 50)
    started = time.time()
    response = requests.post(f"{BASE_URL}/api/process?mode=replace", timeout=600)
    response.raise_for_status()
    payload = response.json()
    elapsed = time.time() - started
    print(f"  files_processed: {payload.get('files_processed', 0)}")
    print(f"  records_processed: {payload.get('records_processed', 0)}")
    print(f"  chunks_written: {payload.get('chunks_written', 0)}")
    print(f"  elapsed: {elapsed:.1f}s")


def print_stats() -> None:
    print("\n" + "=" * 50)
    print("Step 3: collection stats")
    print("=" * 50)
    response = requests.get(f"{BASE_URL}/api/stats", timeout=120)
    response.raise_for_status()
    payload = response.json()
    print(f"  total_documents: {payload.get('total_documents', 0)}")
    print(f"  total_tokens_estimate: {payload.get('total_tokens_estimate', 0)}")
    print(f"  storage_size_mb: {payload.get('storage_size_mb', 0)}")
    for collection in payload.get("collections", []):
        print(f"  - {collection['name']}: {collection['count']} chunks")


def run_queries() -> None:
    print("\n" + "=" * 50)
    print("Step 4: semantic search")
    print("=" * 50)
    for query in [
        "燃气轮机故障诊断",
        "船舶柴油发动机燃油系统",
        "风力发电叶片检查",
    ]:
        response = requests.get(
            f"{BASE_URL}/api/search",
            params={"q": query, "top_k": 3},
            timeout=120,
        )
        response.raise_for_status()
        payload = response.json()
        print(f"\nquery: {query}")
        print(f"latency_ms: {payload.get('latency_ms', '?')}")
        for index, item in enumerate(payload.get("results", []), start=1):
            text = item.get("text", "").replace("\n", " ")
            print(f"  [{index}] {text[:80]}{'...' if len(text) > 80 else ''}")


def main() -> None:
    upload_mock_files()
    process_uploads()
    print_stats()
    run_queries()
    print("\nSmoke test completed.")


if __name__ == "__main__":
    main()
