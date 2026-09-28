# -*- coding: utf-8 -*-
"""Download one Tsinghua-cloud share link into data_pipeline/raw/<name>."""

from __future__ import annotations

import argparse
import json
import sys
import time
import zipfile
from pathlib import Path

import requests

BASE = "https://cloud.tsinghua.edu.cn"
ROOT = Path(__file__).resolve().parent


def list_dirents(token: str) -> list[dict]:
    url = f"{BASE}/api/v2.1/share-links/{token}/dirents/"
    response = requests.get(url, params={"path": "/"}, timeout=120)
    response.raise_for_status()
    return [item for item in response.json().get("dirent_list") or [] if not item.get("is_dir")]


def make_zip_task(token: str, names: list[str]) -> str:
    url = f"{BASE}/api/v2.1/share-link-zip-task/"
    headers = {
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json, text/plain, */*",
        "Referer": f"{BASE}/d/{token}/",
        "User-Agent": "Mozilla/5.0",
    }
    response = requests.post(
        url,
        headers=headers,
        json={"token": token, "parent_dir": "/", "dirents": names},
        timeout=180,
    )
    response.raise_for_status()
    payload = response.json()
    zip_token = str(payload.get("zip_token") or "")
    if not zip_token:
        raise RuntimeError(f"no zip_token in {payload}")
    return zip_token


def wait_zip(zip_token: str, *, timeout_seconds: float = 3600.0) -> None:
    deadline = time.time() + timeout_seconds
    while True:
        response = requests.get(
            f"{BASE}/api/v2.1/query-zip-progress/",
            params={"token": zip_token},
            timeout=120,
        )
        response.raise_for_status()
        progress = response.json()
        if progress.get("failed") == 1:
            raise RuntimeError(f"zip task failed: {progress.get('failed_reason')}")
        if progress.get("total") and progress.get("total") == progress.get("zipped"):
            return
        if time.time() > deadline:
            raise TimeoutError("zip task timed out")
        time.sleep(3)


def download_zip(zip_token: str, dest_zip: Path) -> None:
    url = f"{BASE}/seafhttp/zip/{zip_token}"
    with requests.get(url, stream=True, timeout=1800) as response:
        response.raise_for_status()
        total = int(response.headers.get("Content-Length") or 0)
        written = 0
        with dest_zip.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1 << 20):
                if not chunk:
                    continue
                handle.write(chunk)
                written += len(chunk)
                if total:
                    print(f"  {written / total * 100:5.1f}%  {written >> 20} / {total >> 20} MiB", end="\r")
    print()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("token")
    parser.add_argument("--dest-name", required=True)
    parser.add_argument("--batch-size", type=int, default=15)
    args = parser.parse_args()

    dest_dir = ROOT / "data_pipeline" / "raw" / args.dest_name
    dest_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir = dest_dir / ".download_tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    items = list_dirents(args.token)
    print(f"share has {len(items)} files")

    manifest: list[dict] = []
    total_bytes = sum(int(item.get("size") or 0) for item in items)

    for index in range(0, len(items), args.batch_size):
        batch = items[index : index + args.batch_size]
        names = [str(item["file_name"]) for item in batch]
        zip_path = tmp_dir / f"batch_{index // args.batch_size:03d}.zip"
        if zip_path.exists():
            zip_path.unlink()
        print(f"batch {index // args.batch_size + 1}: {len(names)} files")
        zip_token = make_zip_task(args.token, names)
        wait_zip(zip_token)
        time.sleep(2)
        download_zip(zip_token, zip_path)
        with zipfile.ZipFile(zip_path) as archive:
            for member in archive.infolist():
                if member.is_dir():
                    continue
                out = dest_dir / Path(member.filename).name
                with archive.open(member) as source, out.open("wb") as handle:
                    while True:
                        chunk = source.read(1 << 20)
                        if not chunk:
                            break
                        handle.write(chunk)
                manifest.append(
                    {"file_name": out.name, "size": out.stat().st_size, "origin": member.filename}
                )
        zip_path.unlink()

    (dest_dir / "download_manifest.json").write_text(
        json.dumps(
            {
                "token": args.token,
                "dest_dir": str(dest_dir),
                "file_count": len(manifest),
                "total_bytes": total_bytes,
                "files": manifest,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    try:
        tmp_dir.rmdir()
    except OSError:
        pass
    print(f"ALL_DONE {len(manifest)} files -> {dest_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
