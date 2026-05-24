from __future__ import annotations

import json
import math
import re
import shutil
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Literal

try:
    import orjson
except Exception:  # pragma: no cover - stdlib fallback for minimal environments.
    orjson = None

from .chunking import split_text_with_overlap
from .pipeline import _close_client, _create_client, get_collection_handle, get_collection_stats
from .text_utils import estimate_token_count, normalize_text, safe_collection_name, stable_hash

Decision = Literal["accept", "review", "metadata", "reject"]
IngestMode = Literal["create", "append"]

SNAPSHOT_NAME_RE = re.compile(
    r"project-\d+-at-(?P<date>\d{4}-\d{2}-\d{2})-(?P<time>\d{2}-\d{2})(?:-\d{2})?-[^.]+\.json$",
    re.IGNORECASE,
)

DOMAIN_TERMS = (
    "燃机",
    "燃气轮机",
    "压气机",
    "涡轮",
    "燃烧",
    "故障",
    "振动",
    "叶片",
    "轴承",
    "滑油",
    "机匣",
    "转子",
    "温度",
    "压力",
    "机理",
)


@dataclass(frozen=True, slots=True)
class PublicBookBlock:
    task_id: str
    source_file: str
    filename: str
    doc_id: str
    page_num: int | None
    total_pages: int | None
    block_id: str
    label: str
    text: str
    x: float | None = None
    y: float | None = None
    width: float | None = None
    height: float | None = None
    order: int = 0


@dataclass(frozen=True, slots=True)
class FilteredBlock:
    block: PublicBookBlock
    decision: Decision
    reason: str


@dataclass(frozen=True, slots=True)
class PublicBookRecord:
    record_id: str
    source_file: str
    filename: str
    doc_id: str
    page_num: int | None
    text: str
    blocks: tuple[PublicBookBlock, ...]
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class PublicBookChunk:
    chunk_id: str
    text: str
    metadata: dict[str, str | int | float | bool]


def choose_latest_snapshot(input_root: str | Path) -> Path:
    root = Path(input_root)
    if root.is_file() and root.suffix.lower() == ".json":
        return root
    if not root.exists():
        raise FileNotFoundError(f"JSON directory does not exist: {root}")
    candidates = [path for path in root.rglob("*.json") if path.is_file()]
    if not candidates:
        raise FileNotFoundError(f"No Label Studio JSON snapshots found under: {root}")
    return max(candidates, key=_snapshot_sort_key)


def load_latest_labelstudio_snapshot(input_root: str | Path) -> tuple[Path, list[dict[str, Any]]]:
    snapshot_path = choose_latest_snapshot(input_root)
    raw = snapshot_path.read_bytes()
    if orjson is not None:
        payload = orjson.loads(raw)
    else:
        payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, list):
        raise ValueError("top-level JSON must be a list")
    return snapshot_path, [item for item in payload if isinstance(item, dict)]


def parse_labelstudio_export(payload: Any, source_file: str) -> list[PublicBookBlock]:
    if not isinstance(payload, list):
        raise ValueError("top-level JSON must be a list")

    blocks: list[PublicBookBlock] = []
    for task_index, task in enumerate(item for item in payload if isinstance(item, dict)):
        data = task.get("data") if isinstance(task.get("data"), dict) else {}
        task_id = str(task.get("id", task_index))
        filename = str(data.get("filename") or data.get("file") or data.get("image") or f"task-{task_id}")
        doc_id = str(data.get("doc_id") or filename)
        page_num = _coerce_int(data.get("page_num") or data.get("page"))
        total_pages = _coerce_int(data.get("total_pages"))

        for order, (block_id, raw_block) in enumerate(_collect_labelstudio_blocks(task).items()):
            text = normalize_text(str(raw_block.get("text") or ""))
            if not text:
                continue
            blocks.append(
                PublicBookBlock(
                    task_id=task_id,
                    source_file=source_file,
                    filename=filename,
                    doc_id=doc_id,
                    page_num=page_num,
                    total_pages=total_pages,
                    block_id=block_id,
                    label=str(raw_block.get("label") or "Para"),
                    text=text,
                    x=_as_float(raw_block.get("x")),
                    y=_as_float(raw_block.get("y")),
                    width=_as_float(raw_block.get("width")),
                    height=_as_float(raw_block.get("height")),
                    order=order,
                )
            )
    return sorted(blocks, key=_block_sort_key)


def filter_blocks(blocks: Iterable[PublicBookBlock]) -> list[FilteredBlock]:
    block_list = list(blocks)
    duplicate_counts = Counter(_compact_text(block.text) for block in block_list if block.text)
    return [
        FilteredBlock(block=block, decision=decision, reason=reason)
        for block in block_list
        for decision, reason in [_classify_block(block, duplicate_counts[_compact_text(block.text)])]
    ]


def merge_blocks_to_records(
    filtered_blocks: Iterable[FilteredBlock],
    include_review: bool = False,
    include_title_metadata: bool = True,
) -> list[PublicBookRecord]:
    included: list[FilteredBlock] = []
    for item in filtered_blocks:
        if item.decision == "accept" or (include_review and item.decision == "review"):
            included.append(item)
        elif include_title_metadata and item.decision == "metadata" and item.block.label == "Title":
            included.append(item)

    groups: dict[tuple[str, str, int | None], list[FilteredBlock]] = defaultdict(list)
    for item in included:
        groups[(item.block.doc_id, item.block.filename, item.block.page_num)].append(item)

    records: list[PublicBookRecord] = []
    for (doc_id, filename, page_num), items in sorted(groups.items(), key=lambda entry: _record_group_sort_key(entry[0])):
        ordered = sorted(items, key=lambda item: _block_sort_key(item.block))
        text = normalize_text("\n".join(item.block.text for item in ordered))
        if not text:
            continue
        source_file = ordered[0].block.source_file
        decisions = Counter(item.decision for item in ordered)
        labels = Counter(item.block.label for item in ordered)
        record_id = f"{doc_id}:{page_num if page_num is not None else 'unknown'}:{stable_hash(text)[:12]}"
        blocks = tuple(item.block for item in ordered)
        records.append(
            PublicBookRecord(
                record_id=record_id,
                source_file=source_file,
                filename=filename,
                doc_id=doc_id,
                page_num=page_num,
                text=text,
                blocks=blocks,
                metadata={
                    "source_file": source_file,
                    "filename": filename,
                    "doc_id": doc_id,
                    "page_num": page_num if page_num is not None else -1,
                    "accepted_block_count": len(blocks),
                    "decision_counts": dict(decisions),
                    "label_counts": dict(labels),
                    "first_block_id": blocks[0].block_id if blocks else "",
                    "last_block_id": blocks[-1].block_id if blocks else "",
                    "total_pages": blocks[0].total_pages if blocks and blocks[0].total_pages is not None else -1,
                },
            )
        )
    return records


def chunk_public_book_records(
    records: Iterable[PublicBookRecord],
    chunk_size: int = 900,
    overlap: int = 120,
) -> list[PublicBookChunk]:
    chunks: list[PublicBookChunk] = []
    for record in records:
        for chunk_index, text in enumerate(split_text_with_overlap(record.text, chunk_size=chunk_size, overlap=overlap)):
            text_hash = stable_hash(text)
            chunks.append(
                PublicBookChunk(
                    chunk_id=stable_hash(f"{record.record_id}:{chunk_index}:{text_hash}"),
                    text=text,
                    metadata={
                        "source_file": record.source_file,
                        "filename": record.filename,
                        "doc_id": record.doc_id,
                        "page_num": record.page_num if record.page_num is not None else -1,
                        "record_id": record.record_id,
                        "chunk_index": chunk_index,
                        "block_count": len(record.blocks),
                        "char_count": len(text),
                        "estimated_tokens": estimate_token_count(text),
                        "source_kind": "JSON",
                        "pipeline": "public_books_labelstudio_filter_v1",
                    },
                )
            )
    return chunks


def ingest_latest_snapshot_to_chroma(
    input_root: str | Path,
    persist_dir: str | Path,
    collection_name: str = "public_books_labelstudio",
    mode: IngestMode = "append",
    chunk_size: int = 900,
    overlap: int = 120,
    batch_size: int = 200,
) -> dict[str, Any]:
    if mode not in {"create", "append"}:
        raise ValueError("mode must be 'create' or 'append'")
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be between 0 and chunk_size - 1")

    started = datetime.now()
    latest_path, tasks = load_latest_labelstudio_snapshot(input_root)
    blocks = parse_labelstudio_export(tasks, source_file=latest_path.name)
    filtered = filter_blocks(blocks)
    records = merge_blocks_to_records(filtered)
    chunks = chunk_public_book_records(records, chunk_size=chunk_size, overlap=overlap)
    safe_name = safe_collection_name(collection_name)
    persist_path = Path(persist_dir)

    collection_existed = _collection_exists(persist_path, safe_name)
    if mode == "create" and collection_existed:
        _delete_collection_if_exists(persist_path, safe_name)
        collection_existed = True

    client = None
    try:
        client, collection, resolved_backend = get_collection_handle(
            persist_dir=persist_path,
            collection_name=safe_name,
            backend="hashing",
            model_name=None,
        )
        for start in range(0, len(chunks), batch_size):
            batch = chunks[start:start + batch_size]
            if not batch:
                continue
            collection.upsert(
                ids=[chunk.chunk_id for chunk in batch],
                documents=[chunk.text for chunk in batch],
                metadatas=[chunk.metadata for chunk in batch],
            )
    finally:
        if client is not None:
            _close_client(client)

    stats = get_collection_stats(persist_dir=persist_path, collection_name=safe_name)
    decision_counts = Counter(item.decision for item in filtered)
    label_counts = Counter(item.block.label for item in filtered)

    return {
        "status": "ok",
        "input_root": str(Path(input_root)),
        "latest_snapshot": str(latest_path),
        "latest_snapshot_name": latest_path.name,
        "collection": safe_name,
        "mode": mode,
        "collection_existed": collection_existed,
        "tasks": len(tasks),
        "blocks_total": len(blocks),
        "decision_counts": dict(decision_counts),
        "label_counts": dict(label_counts),
        "records_written": len(records),
        "chunks_written": len(chunks),
        "chunk_size": chunk_size,
        "overlap": overlap,
        "embedding_backend": "hashing",
        "elapsed_s": round((datetime.now() - started).total_seconds(), 3),
        "stats": stats,
    }


def export_chroma_database(persist_dir: str | Path, output_zip: str | Path) -> Path:
    persist_path = Path(persist_dir)
    if not persist_path.exists() or not persist_path.is_dir():
        raise FileNotFoundError(f"ChromaDB directory does not exist: {persist_path}")
    output_path = Path(output_zip)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in persist_path.rglob("*"):
            if file_path.is_file():
                zf.write(file_path, file_path.relative_to(persist_path))
    return output_path


def write_ingest_summary(summary: dict[str, Any], output_dir: str | Path) -> dict[str, str]:
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = target_dir / f"public_books_json_ingest_summary_{timestamp}.json"
    md_path = target_dir / f"public_books_json_ingest_summary_{timestamp}.md"

    payload = json.dumps(summary, ensure_ascii=False, indent=2)
    json_path.write_text(payload, encoding="utf-8")
    md_path.write_text(_summary_to_markdown(summary), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}


def _snapshot_sort_key(path: Path) -> tuple[int, str, float, str]:
    match = SNAPSHOT_NAME_RE.search(path.name)
    if match:
        return (1, f"{match.group('date')}-{match.group('time')}", path.stat().st_mtime, path.name)
    return (0, "", path.stat().st_mtime, path.name)


def _collect_labelstudio_blocks(task: dict[str, Any]) -> dict[str, dict[str, Any]]:
    annotations = task.get("annotations") if isinstance(task.get("annotations"), list) else []
    annotation = annotations[0] if annotations and isinstance(annotations[0], dict) else {}
    results = annotation.get("result") if isinstance(annotation.get("result"), list) else []
    by_id: dict[str, dict[str, Any]] = defaultdict(dict)
    for order, result in enumerate(item for item in results if isinstance(item, dict)):
        result_id = str(result.get("id") or f"item-{order}")
        value = result.get("value") if isinstance(result.get("value"), dict) else {}
        item_type = result.get("type")
        payload = by_id[result_id]
        payload.setdefault("order", order)
        if item_type == "rectanglelabels":
            labels = value.get("rectanglelabels") if isinstance(value.get("rectanglelabels"), list) else []
            payload["label"] = str(labels[0]) if labels else payload.get("label", "")
            for key in ("x", "y", "width", "height"):
                if key in value:
                    payload[key] = value.get(key)
        elif item_type == "textarea":
            text_value = value.get("text")
            if isinstance(text_value, list):
                payload["text"] = "\n".join(str(item) for item in text_value if item is not None)
            elif text_value is not None:
                payload["text"] = str(text_value)
    return dict(by_id)


def _classify_block(block: PublicBookBlock, duplicate_count: int) -> tuple[Decision, str]:
    text = block.text
    label = block.label
    length = len(text)
    noise = _symbol_ratio(text)

    if not text:
        return "reject", "empty_text"
    if _is_probable_page_noise(text):
        return "reject", "page_or_tiny_noise"
    if duplicate_count >= 8 and length <= 40:
        return "reject", "repeated_header_footer"
    if noise > 0.45:
        return "review", "high_symbol_noise"
    if label in {"Para", "Title"} and length >= 20:
        return "accept", "main_text"
    if label == "List" and length >= 20:
        return "accept", "list_text"
    if label in {"Para", "List"} and 8 <= length < 20 and _has_domain_term(text):
        return "review", "short_domain_text"
    if label == "Title" and 4 <= length < 20:
        return "metadata", "title_metadata"
    if label == "Figure":
        if length >= 12 and _has_domain_term(text):
            return "review", "figure_caption_with_domain_term"
        return "metadata", "figure_caption"
    if label == "Formula":
        return "review", "formula_needs_context"
    if label == "Table":
        if length >= 30 and _has_domain_term(text):
            return "review", "table_needs_manual_check"
        return "reject", "table_too_short_or_no_domain_term"
    if length < 20:
        return "reject", "too_short"
    return "review", "unknown_label_or_rule_gap"


def _collection_exists(persist_dir: Path, collection_name: str) -> bool:
    if not persist_dir.exists():
        return False
    client = _create_client(persist_dir)
    try:
        try:
            client.get_collection(name=collection_name)
            return True
        except Exception:
            return False
    finally:
        _close_client(client)


def _delete_collection_if_exists(persist_dir: Path, collection_name: str) -> None:
    if not persist_dir.exists():
        return
    client = _create_client(persist_dir)
    try:
        try:
            client.delete_collection(name=collection_name)
        except Exception:
            pass
    finally:
        _close_client(client)


def _summary_to_markdown(summary: dict[str, Any]) -> str:
    decision_counts = summary.get("decision_counts") or {}
    lines = [
        "# 公开书籍 JSON 入库摘要",
        "",
        f"- 最新快照：`{summary.get('latest_snapshot_name', '')}`",
        f"- 集合：`{summary.get('collection', '')}`",
        f"- 模式：`{summary.get('mode', '')}`",
        f"- 任务数：{summary.get('tasks', 0)}",
        f"- 文本块：{summary.get('blocks_total', 0)}",
        f"- 写入记录：{summary.get('records_written', 0)}",
        f"- 写入 chunk：{summary.get('chunks_written', 0)}",
        f"- 筛选结果：accept {decision_counts.get('accept', 0)}，review {decision_counts.get('review', 0)}，metadata {decision_counts.get('metadata', 0)}，reject {decision_counts.get('reject', 0)}",
    ]
    return "\n".join(lines) + "\n"


def _coerce_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        numeric = float(value)
        if math.isnan(numeric) or math.isinf(numeric):
            return None
        return numeric
    except (TypeError, ValueError):
        return None


def _compact_text(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def _symbol_ratio(text: str) -> float:
    if not text:
        return 1.0
    meaningful = sum(1 for char in text if "\u4e00" <= char <= "\u9fff" or char.isalnum())
    return 1.0 - meaningful / max(len(text), 1)


def _is_probable_page_noise(text: str) -> bool:
    compact = _compact_text(text)
    if re.fullmatch(r"[-—–]*\d{1,4}[-—–]*", compact):
        return True
    if re.fullmatch(r"第?\d{1,4}页", compact):
        return True
    return len(compact) <= 2


def _has_domain_term(text: str) -> bool:
    return any(term in text for term in DOMAIN_TERMS)


def _block_sort_key(block: PublicBookBlock) -> tuple[str, int, float, float, int]:
    return (
        block.filename,
        block.page_num if block.page_num is not None else -1,
        block.y if block.y is not None else float("inf"),
        block.x if block.x is not None else float("inf"),
        block.order,
    )


def _record_group_sort_key(key: tuple[str, str, int | None]) -> tuple[str, str, int]:
    doc_id, filename, page_num = key
    return doc_id, filename, page_num if page_num is not None else -1
