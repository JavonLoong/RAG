import requests, os, json

API = "http://localhost:8001"
json_file = r"D:\虚拟C盘\清华云盘_专业书籍_20260524\解压后\公开书籍标注后\project-1-at-2026-05-21-06-17-203caed5.json"
fname = os.path.basename(json_file)

print("1. Uploading latest JSON (64 MB)...")
with open(json_file, "rb") as f:
    resp = requests.post(f"{API}/api/upload", files={"file": (fname, f, "application/json")})
print(f"   Status: {resp.status_code}")
print(f"   Result: {json.dumps(resp.json(), indent=2, ensure_ascii=False)[:500]}")

print()
print("2. Processing into ChromaDB (collection: professional_books)...")
resp2 = requests.post(
    f"{API}/api/process",
    json={"filenames": [fname], "collection": "professional_books"},
    timeout=600,
)
print(f"   Status: {resp2.status_code}")
r = resp2.json()
print(f"   Files succeeded: {r.get('files_succeeded')}")
print(f"   Chunks written: {r.get('chunks_written')}")
print(f"   Records processed: {r.get('records_processed')}")
print(f"   Elapsed: {r.get('elapsed_s')} s")

print()
print("3. Checking stats...")
resp3 = requests.get(f"{API}/api/stats")
stats = resp3.json()
print(f"   Collections: {len(stats.get('collections', []))}")
for c in stats.get("collections", []):
    print(f"     - {c['name']}: {c['count']} docs, ~{c.get('estimated_tokens',0)} tokens")
print(f"   Storage: {stats.get('storage_size_mb', 0)} MB")
