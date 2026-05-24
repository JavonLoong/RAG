import requests
try:
    resp3 = requests.get('http://localhost:8001/api/stats', timeout=10)
    stats = resp3.json()
    print(f"Collections: {len(stats.get('collections', []))}")
    for c in stats.get('collections', []):
        print(f"  - {c['name']}: {c['count']} docs, ~{c.get('estimated_tokens',0)} tokens")
    print(f"Storage: {stats.get('storage_size_mb', 0)} MB")
except Exception as e:
    print(e)
