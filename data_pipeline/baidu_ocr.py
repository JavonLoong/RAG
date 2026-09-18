"""Baidu Cloud OCR adapter for the governed M2 comparison workflow.

Credentials are read from environment variables and are never persisted.  The
adapter returns the page payload shape consumed by ``data_pipeline.m2_ocr``.
"""

# ruff: noqa: TRY003

from __future__ import annotations

import base64
import io
import os
import time
from dataclasses import dataclass
from typing import Any

import requests
from PIL import Image

TOKEN_URL = "https://aip.baidubce.com/oauth/2.0/token"  # noqa: S105 - public endpoint URL
OCR_ENDPOINTS = {
    "general_basic": "https://aip.baidubce.com/rest/2.0/ocr/v1/general_basic",
    "general": "https://aip.baidubce.com/rest/2.0/ocr/v1/general",
    "accurate_basic": "https://aip.baidubce.com/rest/2.0/ocr/v1/accurate_basic",
    "accurate": "https://aip.baidubce.com/rest/2.0/ocr/v1/accurate",
    "office": "https://aip.baidubce.com/rest/2.0/ocr/v1/doc_analysis_office",
    "table": "https://aip.baidubce.com/rest/2.0/ocr/v1/table",
}
MAX_ENCODED_BYTES = 4 * 1024 * 1024
MAX_IMAGE_SIDE = 4096


class BaiduOCRConfigurationError(RuntimeError):
    """Raised when the Baidu OCR application is not configured safely."""


class BaiduOCRResponseError(RuntimeError):
    """Raised when the Baidu OCR service rejects or cannot process a page."""


@dataclass(frozen=True, slots=True)
class BaiduOCRConfig:
    api_key: str
    secret_key: str
    model: str = "general"
    timeout_seconds: float = 30.0
    language_type: str = "CHN_ENG"

    @classmethod
    def from_env(cls) -> BaiduOCRConfig:
        api_key = os.environ.get("BAIDU_OCR_API_KEY", "").strip()
        secret_key = os.environ.get("BAIDU_OCR_SECRET_KEY", "").strip()
        if not api_key or not secret_key:
            raise BaiduOCRConfigurationError(
                "Set BAIDU_OCR_API_KEY and BAIDU_OCR_SECRET_KEY in the process environment"
            )
        model = os.environ.get("BAIDU_OCR_MODEL", "general").strip().lower()
        if model not in OCR_ENDPOINTS:
            raise BaiduOCRConfigurationError(f"BAIDU_OCR_MODEL must be one of: {', '.join(sorted(OCR_ENDPOINTS))}")
        timeout = float(os.environ.get("BAIDU_OCR_TIMEOUT_SECONDS", "30"))
        return cls(api_key=api_key, secret_key=secret_key, model=model, timeout_seconds=timeout)


class BaiduOCRClient:
    """Callable page OCR provider with in-memory access-token caching."""

    def __init__(self, config: BaiduOCRConfig, *, session: Any | None = None) -> None:
        self.config = config
        self.session = session or requests.Session()
        self._access_token: str | None = None
        self._token_expires_at = 0.0

    def __call__(self, image_bytes: bytes, page: int, source_name: str) -> dict[str, Any]:
        prepared, preprocessing = prepare_image_for_baidu(image_bytes)
        started = time.perf_counter()
        request_data = _request_data(self.config, prepared)
        response = _safe_post(
            self.session,
            OCR_ENDPOINTS[self.config.model],
            context="OCR request",
            params={"access_token": self._token()},
            data=request_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=self.config.timeout_seconds,
        )
        payload = _response_json(response, context="OCR request")
        if payload.get("error_code"):
            raise BaiduOCRResponseError(
                f"Baidu OCR error {payload.get('error_code')}: {payload.get('error_msg', 'unknown error')}"
            )
        normalizer = (
            normalize_baidu_office_response
            if self.config.model == "office"
            else normalize_baidu_table_response
            if self.config.model == "table"
            else normalize_baidu_response
        )
        return normalizer(
            payload,
            page=page,
            source_name=source_name,
            model=self.config.model,
            elapsed_seconds=time.perf_counter() - started,
            preprocessing=preprocessing,
        )

    def _token(self) -> str:
        now = time.time()
        if self._access_token and now < self._token_expires_at - 60:
            return self._access_token
        response = _safe_post(
            self.session,
            TOKEN_URL,
            context="token request",
            params={
                "grant_type": "client_credentials",
                "client_id": self.config.api_key,
                "client_secret": self.config.secret_key,
            },
            timeout=self.config.timeout_seconds,
        )
        payload = _response_json(response, context="token request")
        token = str(payload.get("access_token") or "")
        if not token:
            code = payload.get("error") or payload.get("error_code") or "unknown"
            message = payload.get("error_description") or payload.get("error_msg") or "token missing"
            raise BaiduOCRResponseError(f"Baidu OAuth error {code}: {message}")
        self._access_token = token
        self._token_expires_at = now + max(60, int(payload.get("expires_in") or 2592000))
        return token


def prepare_image_for_baidu(image_bytes: bytes) -> tuple[bytes, dict[str, Any]]:
    """Fit a page image inside the conservative cloud API size constraints."""

    with Image.open(io.BytesIO(image_bytes)) as opened:
        image = opened.convert("RGB")
        original_size = image.size
        longest = max(image.size)
        resized = False
        if longest > MAX_IMAGE_SIDE:
            ratio = MAX_IMAGE_SIDE / longest
            image = image.resize(
                (max(15, round(image.width * ratio)), max(15, round(image.height * ratio))),
                Image.Resampling.LANCZOS,
            )
            resized = True

        quality = 92
        prepared = _encode_jpeg(image, quality)
        while len(base64.b64encode(prepared)) > MAX_ENCODED_BYTES and quality >= 55:
            quality -= 7
            prepared = _encode_jpeg(image, quality)
        if len(base64.b64encode(prepared)) > MAX_ENCODED_BYTES:
            raise BaiduOCRResponseError(
                "Page remains above the 4 MiB encoded upload limit after safe resizing/compression"
            )
        return prepared, {
            "original_width": original_size[0],
            "original_height": original_size[1],
            "uploaded_width": image.width,
            "uploaded_height": image.height,
            "resized": resized,
            "jpeg_quality": quality,
            "uploaded_bytes": len(prepared),
        }


def normalize_baidu_response(
    payload: dict[str, Any],
    *,
    page: int,
    source_name: str,
    model: str,
    elapsed_seconds: float,
    preprocessing: dict[str, Any],
) -> dict[str, Any]:
    words = payload.get("words_result") or []
    blocks: list[dict[str, Any]] = []
    confidences: list[float] = []
    for index, item in enumerate(words):
        if not isinstance(item, dict):
            continue
        text = str(item.get("words") or "").strip()
        probability = item.get("probability") or {}
        confidence = _optional_probability(probability.get("average"))
        if confidence is not None:
            confidences.append(confidence)
        location = item.get("location") or {}
        blocks.append({
            "block_id": f"p{page}-b{index + 1}",
            "type": "Para",
            "order": index,
            "text": text,
            "confidence": confidence,
            "bbox": _location_to_bbox(location),
            "location": dict(location) if isinstance(location, dict) else {},
        })
    return {
        "page": page,
        "source_name": source_name,
        "text": "\n".join(item["text"] for item in blocks if item["text"]),
        "confidence": sum(confidences) / len(confidences) if confidences else None,
        "status": "ok",
        "blocks": blocks,
        "tables": [],
        "reading_order_risk": "unknown" if not blocks else "low",
        "provider": "baidu",
        "model": model,
        "elapsed_seconds": round(elapsed_seconds, 4),
        "words_result_num": int(payload.get("words_result_num") or len(blocks)),
        "direction": payload.get("direction"),
        "preprocessing": preprocessing,
    }


def normalize_baidu_office_response(
    payload: dict[str, Any],
    *,
    page: int,
    source_name: str,
    model: str,
    elapsed_seconds: float,
    preprocessing: dict[str, Any],
) -> dict[str, Any]:
    """Normalize office-document OCR while preserving layout and table evidence."""

    blocks: list[dict[str, Any]] = []
    confidences: list[float] = []
    for item in payload.get("results") or []:
        if not isinstance(item, dict):
            continue
        word_items = item.get("words")
        if isinstance(word_items, dict):
            word_items = [word_items]
        if not isinstance(word_items, list):
            continue
        for word_item in word_items:
            if not isinstance(word_item, dict):
                continue
            text = str(word_item.get("word") or word_item.get("words") or "").strip()
            probability = word_item.get("line_probability") or item.get("line_probability") or {}
            confidence = _optional_probability(probability.get("average")) if isinstance(probability, dict) else None
            if confidence is not None:
                confidences.append(confidence)
            location = word_item.get("words_location") or word_item.get("location") or {}
            index = len(blocks)
            blocks.append({
                "block_id": f"p{page}-b{index + 1}",
                "type": "Para",
                "order": index,
                "text": text,
                "confidence": confidence,
                "bbox": _location_to_bbox(location),
                "location": dict(location) if isinstance(location, dict) else {},
                "words_type": item.get("words_type"),
            })

    layouts = payload.get("layouts") if isinstance(payload.get("layouts"), list) else []
    sections = payload.get("sections") if isinstance(payload.get("sections"), list) else []
    sec_cols = int(payload.get("sec_cols") or 0)
    reordered_ids = _office_reading_order(sections, len(blocks))
    reordered_blocks = [blocks[index] for index in reordered_ids]
    result = {
        "page": page,
        "source_name": source_name,
        "text": "\n".join(item["text"] for item in blocks if item["text"]),
        "confidence": sum(confidences) / len(confidences) if confidences else None,
        "status": "ok",
        "blocks": blocks,
        "tables": payload.get("tables_result") if isinstance(payload.get("tables_result"), list) else [],
        "reading_order_risk": "high" if sec_cols > 1 else "low" if blocks else "unknown",
        "layout": {
            "mode": "baidu_office",
            "reading_order_risk": "high" if sec_cols > 1 else "low" if blocks else "unknown",
            "sec_rows": int(payload.get("sec_rows") or 0),
            "sec_cols": sec_cols,
            "layouts": layouts,
            "sections": sections,
        },
        "provider": "baidu",
        "model": model,
        "elapsed_seconds": round(elapsed_seconds, 4),
        "words_result_num": len(blocks),
        "direction": payload.get("img_direction"),
        "preprocessing": preprocessing,
    }
    if reordered_blocks and reordered_ids != list(range(len(blocks))):
        result["layout_reordered_text"] = "\n".join(item["text"] for item in reordered_blocks if item["text"])
        result["layout_reordered_block_ids"] = [item["block_id"] for item in reordered_blocks]
    return result


def normalize_baidu_table_response(
    payload: dict[str, Any],
    *,
    page: int,
    source_name: str,
    model: str,
    elapsed_seconds: float,
    preprocessing: dict[str, Any],
) -> dict[str, Any]:
    """Normalize Table OCR V2 without discarding row/column coordinates."""

    tables = payload.get("tables_result") if isinstance(payload.get("tables_result"), list) else []
    blocks: list[dict[str, Any]] = []
    for table_index, table in enumerate(tables):
        if not isinstance(table, dict):
            continue
        ordered_items: list[tuple[int, int, str, Any, str]] = []
        for item in table.get("header") or []:
            if isinstance(item, dict):
                ordered_items.append((
                    -1,
                    len(ordered_items),
                    str(item.get("words") or "").strip(),
                    item.get("location"),
                    "TableHeader",
                ))
        for item in table.get("body") or []:
            if isinstance(item, dict):
                ordered_items.append((
                    int(item.get("row_start") or 0),
                    int(item.get("col_start") or 0),
                    str(item.get("words") or "").strip(),
                    item.get("cell_location"),
                    "TableCell",
                ))
        for item in table.get("footer") or []:
            if isinstance(item, dict):
                ordered_items.append((
                    10**9,
                    len(ordered_items),
                    str(item.get("words") or "").strip(),
                    item.get("location"),
                    "TableFooter",
                ))
        for row, column, text, location, block_type in sorted(ordered_items, key=lambda value: (value[0], value[1])):
            index = len(blocks)
            blocks.append({
                "block_id": f"p{page}-t{table_index + 1}-b{index + 1}",
                "type": block_type,
                "order": index,
                "text": text,
                "confidence": None,
                "bbox": _points_to_bbox(location),
                "row": None if row in {-1, 10**9} else row,
                "column": None if row in {-1, 10**9} else column,
            })
    return {
        "page": page,
        "source_name": source_name,
        "text": "\n".join(item["text"] for item in blocks if item["text"]),
        "confidence": None,
        "status": "ok",
        "blocks": blocks,
        "tables": tables,
        "reading_order_risk": "low" if tables else "unknown",
        "provider": "baidu",
        "model": model,
        "elapsed_seconds": round(elapsed_seconds, 4),
        "words_result_num": len(blocks),
        "table_num": int(payload.get("table_num") or len(tables)),
        "preprocessing": preprocessing,
    }


def _request_data(config: BaiduOCRConfig, prepared: bytes) -> dict[str, str]:
    image = base64.b64encode(prepared).decode("ascii")
    if config.model == "table":
        return {"image": image, "cell_contents": "true", "return_excel": "false"}
    if config.model == "office":
        return {
            "image": image,
            "language_type": config.language_type,
            "detect_direction": "true",
            "result_type": "big",
            "line_probability": "true",
            "disp_line_poly": "true",
            "layout_analysis": "true",
            "recg_tables": "true",
        }
    return {
        "image": image,
        "language_type": config.language_type,
        "detect_direction": "true",
        "paragraph": "true",
        "probability": "true",
    }


def _office_reading_order(sections: list[Any], block_count: int) -> list[int]:
    ordered: list[tuple[int, int, int]] = []
    for section in sections:
        if not isinstance(section, dict) or section.get("attribute") != "section":
            continue
        raw_indices = section.get("sec_idx")
        index_items = raw_indices if isinstance(raw_indices, list) else [raw_indices]
        for item in index_items:
            if not isinstance(item, dict):
                continue
            row_values = _int_values(item.get("row_idx"))
            column_values = _int_values(item.get("col_idx"))
            row = row_values[0] if row_values else 0
            column = column_values[0] if column_values else 0
            for index in _int_values(item.get("idx")):
                if 0 <= index < block_count:
                    ordered.append((row, column, index))
    result = [index for _row, _column, index in sorted(ordered)]
    seen = set(result)
    result.extend(index for index in range(block_count) if index not in seen)
    return result


def _int_values(value: Any) -> list[int]:
    values = value if isinstance(value, list) else [value]
    result: list[int] = []
    for item in values:
        try:
            result.append(int(item))
        except (TypeError, ValueError):
            continue
    return result


def _encode_jpeg(image: Image.Image, quality: int) -> bytes:
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=quality, optimize=True)
    return output.getvalue()


def _response_json(response: Any, *, context: str) -> dict[str, Any]:
    try:
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        raise BaiduOCRResponseError(f"Baidu {context} failed: {type(exc).__name__}") from None
    if not isinstance(payload, dict):
        raise BaiduOCRResponseError(f"Baidu {context} returned a non-object response")
    return payload


def _safe_post(session: Any, url: str, *, context: str, **kwargs: Any) -> Any:
    try:
        return session.post(url, **kwargs)
    except Exception as exc:
        # Suppress the original request exception because it may render query
        # parameters containing an access token or API credentials.
        raise BaiduOCRResponseError(f"Baidu {context} failed: {type(exc).__name__}") from None


def _optional_probability(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return max(0.0, min(1.0, float(value)))


def _location_to_bbox(location: Any) -> list[list[int]]:
    if not isinstance(location, dict):
        return []
    left = int(location.get("left") or 0)
    top = int(location.get("top") or 0)
    width = int(location.get("width") or 0)
    height = int(location.get("height") or 0)
    return [
        [left, top],
        [left + width, top],
        [left + width, top + height],
        [left, top + height],
    ]


def _points_to_bbox(points: Any) -> list[list[int]]:
    if not isinstance(points, list):
        return []
    result: list[list[int]] = []
    for point in points:
        if not isinstance(point, dict):
            continue
        result.append([int(point.get("x") or 0), int(point.get("y") or 0)])
    return result
