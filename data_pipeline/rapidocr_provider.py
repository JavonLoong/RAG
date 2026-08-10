"""Local RapidOCR provider normalized for the M2 benchmark contract."""

# ruff: noqa: TRY003

from __future__ import annotations

import io
import statistics
from importlib.metadata import PackageNotFoundError, version
from itertools import pairwise
from typing import Any

from PIL import Image


class RapidOCRUnavailable(RuntimeError):
    """Raised when the optional local OCR runtime is not installed."""


class RapidOCRProvider:
    """Callable adapter returning text, boxes, confidence and layout risk."""

    def __init__(self, *, engine: Any | None = None) -> None:
        if engine is None:
            try:
                from rapidocr import RapidOCR
            except ImportError as exc:  # pragma: no cover - dependency gate
                raise RapidOCRUnavailable(
                    "Install the local runtime with: uv pip install rapidocr onnxruntime"
                ) from exc
            engine = RapidOCR()
        self.engine = engine

    def __call__(self, image_bytes: bytes, page: int, source_name: str) -> dict[str, Any]:
        output = self.engine(image_bytes)
        texts = [str(item) for item in _as_list(getattr(output, "txts", None))]
        scores = [float(item) for item in _as_list(getattr(output, "scores", None))]
        raw_boxes = _as_list(getattr(output, "boxes", None))
        blocks = []
        for index, text in enumerate(texts):
            box = _box_to_list(raw_boxes[index]) if index < len(raw_boxes) else []
            blocks.append({
                "block_id": f"p{page}-b{index + 1}",
                "type": "Para",
                "order": index,
                "text": text,
                "confidence": scores[index] if index < len(scores) else None,
                "bbox": box,
            })
        with Image.open(io.BytesIO(image_bytes)) as image:
            width, height = image.size
        layout = classify_layout(blocks, width=width, height=height)
        reordered_blocks = reorder_two_column_blocks(blocks, width=width) if layout["two_column_candidate"] else blocks
        return {
            "page": page,
            "source_name": source_name,
            "text": "\n".join(texts),
            "confidence": statistics.mean(scores) if scores else None,
            "status": "ok",
            "blocks": blocks,
            "lines": blocks,
            "layout_reordered_text": "\n".join(str(item.get("text") or "") for item in reordered_blocks),
            "layout_reordered_block_ids": [str(item.get("block_id") or "") for item in reordered_blocks],
            "tables": [],
            "reading_order_risk": layout["reading_order_risk"],
            "layout": layout,
            "provider": "local",
            "engine": "rapidocr",
            "engine_version": _package_version("rapidocr"),
            "inference_engine": "onnxruntime",
            "inference_engine_version": _package_version("onnxruntime"),
            "elapsed_seconds": round(float(getattr(output, "elapse", 0.0) or 0.0), 4),
            "line_count": len(blocks),
        }


def classify_layout(blocks: list[dict[str, Any]], *, width: int, height: int) -> dict[str, Any]:
    del height  # retained in the signature for future vertical layout checks
    zones: list[str] = []
    left = 0
    right = 0
    wide = 0
    for block in blocks:
        box = block.get("bbox") or []
        if len(box) < 4:
            continue
        xs = [float(point[0]) for point in box if len(point) >= 2]
        if not xs:
            continue
        x0, x1 = min(xs), max(xs)
        if x1 < width * 0.52:
            left += 1
            zones.append("L")
        elif x0 > width * 0.48:
            right += 1
            zones.append("R")
        else:
            wide += 1
            zones.append("W")
    compact = [zone for zone in zones if zone in {"L", "R"}]
    transitions = sum(before != after for before, after in pairwise(compact))
    two_column = left >= 4 and right >= 4
    risk = "high" if two_column and transitions >= 4 else "medium" if two_column else "low"
    return {
        "mode": "box_audit",
        "reading_order_risk": risk,
        "two_column_candidate": two_column,
        "left_line_count": left,
        "right_line_count": right,
        "wide_line_count": wide,
        "left_right_transitions": transitions,
        "zone_sequence": "".join(zones),
        "image_width": width,
    }


def reorder_two_column_blocks(blocks: list[dict[str, Any]], *, width: int) -> list[dict[str, Any]]:
    """Return a reversible left-column-then-right-column candidate order."""

    left: list[dict[str, Any]] = []
    right: list[dict[str, Any]] = []
    unknown: list[dict[str, Any]] = []
    for block in blocks:
        points = [point for point in (block.get("bbox") or []) if len(point) >= 2]
        if not points:
            unknown.append(block)
            continue
        center_x = sum(float(point[0]) for point in points) / len(points)
        (left if center_x < width / 2 else right).append(block)
    key = lambda item: (_block_top(item), int(item.get("order") or 0))
    return [*sorted(left, key=key), *sorted(right, key=key), *sorted(unknown, key=key)]


def _box_to_list(box: Any) -> list[list[int]]:
    if hasattr(box, "tolist"):
        box = box.tolist()
    return [[round(float(point[0])), round(float(point[1]))] for point in box or [] if len(point) >= 2]


def _block_top(block: dict[str, Any]) -> float:
    points = [point for point in (block.get("bbox") or []) if len(point) >= 2]
    return min((float(point[1]) for point in points), default=float("inf"))


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if hasattr(value, "tolist"):
        value = value.tolist()
    return list(value)


def _package_version(package: str) -> str:
    try:
        return version(package)
    except PackageNotFoundError:  # pragma: no cover - optional metadata
        return "unknown"
