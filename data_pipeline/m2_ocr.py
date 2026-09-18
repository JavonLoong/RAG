"""Recoverable OCR execution and page-level M2 quality diagnostics."""
# ruff: noqa: TRY003

from __future__ import annotations

import json
import os
import shlex
import subprocess
import tempfile
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any, Protocol


class OCRBackendUnavailable(RuntimeError):
    pass


class OCRProvider(Protocol):
    def __call__(self, image_bytes: bytes, page: int, source_name: str) -> dict[str, Any]: ...


@dataclass(frozen=True, slots=True)
class OCRRunResult:
    pages: tuple[dict[str, Any], ...]
    expected_pages: int
    status: str
    failed_pages: tuple[int, ...]
    timeout_pages: tuple[int, ...]
    table_misalignment: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "pages": list(self.pages),
            "expected_pages": self.expected_pages,
            "status": self.status,
            "failed_pages": list(self.failed_pages),
            "timeout_pages": list(self.timeout_pages),
            "table_misalignment": list(self.table_misalignment),
        }


def configured_command_ocr_provider() -> OCRProvider | None:
    """Return an OCR provider backed by ``POWER_RAG_M2_OCR_COMMAND``.

    The command receives ``--input``, ``--page`` and ``--source`` and must
    print a JSON object containing at least ``text``.  Shell execution is not
    used, keeping operator-supplied arguments explicit and auditable.
    """

    raw_command = os.environ.get("POWER_RAG_M2_OCR_COMMAND", "").strip()
    if not raw_command:
        return None
    command = shlex.split(raw_command, posix=os.name != "nt")
    process_timeout = float(os.environ.get("POWER_RAG_M2_OCR_PROCESS_TIMEOUT_SECONDS", "120"))

    def recognize(image_bytes: bytes, page: int, source_name: str) -> dict[str, Any]:
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as handle:
                handle.write(image_bytes)
                temp_path = Path(handle.name)
            completed = subprocess.run(  # noqa: S603 - explicit operator-configured argv, shell disabled
                [*command, "--input", str(temp_path), "--page", str(page), "--source", source_name],
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=process_timeout,
            )
            payload = json.loads(completed.stdout)
            if not isinstance(payload, dict):
                raise TypeError("OCR command must return one JSON object")
            return payload
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)

    return recognize


def run_ocr(
    raw_bytes: bytes,
    source_name: str,
    *,
    provider: OCRProvider | Callable[[bytes, int, str], dict[str, Any]] | None = None,
    page_timeout_seconds: float = 120.0,
    render_scale: float = 1.5,
    page_numbers: tuple[int, ...] | list[int] | None = None,
) -> OCRRunResult:
    provider = provider or configured_command_ocr_provider()
    if provider is None:
        raise OCRBackendUnavailable(
            "No OCR provider is configured; set POWER_RAG_M2_OCR_COMMAND or inject app.state.m2_ocr_provider."
        )
    all_rendered_pages = render_source_pages(raw_bytes, source_name, scale=render_scale)
    expected_pages = len(all_rendered_pages)
    requested_pages = None if page_numbers is None else {int(page) for page in page_numbers}
    if requested_pages is not None:
        if not requested_pages or min(requested_pages) < 1 or max(requested_pages) > expected_pages:
            raise ValueError(f"OCR page selection must be within 1..{expected_pages}")
        rendered_pages = [item for item in all_rendered_pages if item[0] in requested_pages]
    else:
        rendered_pages = all_rendered_pages
    pages: list[dict[str, Any]] = []
    failed: list[int] = []
    timed_out: list[int] = []
    table_issues: list[dict[str, Any]] = []

    provider_name = str(
        getattr(provider, "provider_id", "")
        or getattr(provider, "__name__", "")
        or type(provider).__name__
    )
    for page_number, image_bytes in rendered_pages:
        started_at = perf_counter()
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"m2-ocr-{page_number}")
        future = executor.submit(provider, image_bytes, page_number, source_name)
        try:
            raw_page = future.result(timeout=page_timeout_seconds)
            page = normalize_ocr_page(raw_page, page=page_number, source_name=source_name)
        except FutureTimeout:
            future.cancel()
            timed_out.append(page_number)
            failed.append(page_number)
            page = {
                "page": page_number,
                "text": "",
                "confidence": 0.0,
                "status": "timeout",
                "error": f"OCR page timed out after {page_timeout_seconds} seconds",
                "blocks": [],
                "tables": [],
                "reading_order_risk": "unknown",
            }
        except Exception as exc:  # page failure is governed data, not a batch abort
            failed.append(page_number)
            page = {
                "page": page_number,
                "text": "",
                "confidence": 0.0,
                "status": "error",
                "error": str(exc),
                "error_type": type(exc).__name__,
                "blocks": [],
                "tables": [],
                "reading_order_risk": "unknown",
            }
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
        page["ocr_engine"] = provider_name
        page["duration_ms"] = max(0, round((perf_counter() - started_at) * 1000, 3))
        page_table_issues = detect_table_misalignment(page)
        page["table_misalignment"] = page_table_issues
        table_issues.extend(page_table_issues)
        pages.append(page)

    status = "completed" if not failed and not table_issues else "needs_review"
    return OCRRunResult(
        pages=tuple(pages),
        expected_pages=expected_pages,
        status=status,
        failed_pages=tuple(sorted(set(failed))),
        timeout_pages=tuple(sorted(set(timed_out))),
        table_misalignment=tuple(table_issues),
    )


def render_source_pages(raw_bytes: bytes, source_name: str, *, scale: float = 1.5) -> list[tuple[int, bytes]]:
    suffix = Path(source_name).suffix.lower()
    if suffix == ".pdf":
        try:
            import fitz
        except ImportError as exc:  # pragma: no cover - dependency gate
            raise OCRBackendUnavailable("PyMuPDF is required to render PDF pages for OCR") from exc
        document = fitz.open(stream=raw_bytes, filetype="pdf")
        matrix = fitz.Matrix(scale, scale)
        return [
            (index + 1, document.load_page(index).get_pixmap(matrix=matrix, alpha=False).tobytes("png"))
            for index in range(document.page_count)
        ]
    if suffix in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}:
        return [(1, raw_bytes)]
    raise ValueError(f"OCR rendering is not supported for {suffix or 'unknown'}")


def render_source_preview(raw_bytes: bytes, source_name: str, page: int = 1) -> tuple[bytes, str]:
    pages = render_source_pages(raw_bytes, source_name, scale=1.25)
    match = next((payload for number, payload in pages if number == page), None)
    if match is None:
        raise ValueError(f"Source page {page} does not exist")
    return match, "image/png"


def normalize_ocr_page(payload: dict[str, Any], *, page: int, source_name: str) -> dict[str, Any]:
    normalized = dict(payload or {})
    normalized["page"] = page
    normalized["source_name"] = source_name
    normalized["text"] = str(normalized.get("text") or "").strip()
    normalized["confidence"] = _optional_float(
        normalized.get("confidence", normalized.get("avg_confidence"))
    )
    normalized["status"] = str(normalized.get("status") or "ok")
    normalized["blocks"] = _normalize_blocks(normalized.get("blocks") or [], page)
    normalized["tables"] = [dict(item) for item in normalized.get("tables") or [] if isinstance(item, dict)]
    normalized["reading_order_risk"] = _reading_order_risk(normalized["blocks"], normalized)
    if not normalized["text"] and normalized["blocks"]:
        normalized["text"] = "\n".join(str(block.get("text") or "") for block in normalized["blocks"]).strip()
    return normalized


def detect_table_misalignment(page: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    page_number = int(page.get("page") or 0)
    for index, table in enumerate(page.get("tables") or [], start=1):
        table_id = str(table.get("table_id") or f"page-{page_number}-table-{index}")
        rows = table.get("rows") or []
        widths = [len(row) for row in rows if isinstance(row, list)]
        expected = int(table.get("expected_columns") or (max(widths) if widths else 0))
        malformed_rows = [row_index for row_index, width in enumerate(widths) if width != expected]
        if not rows or expected == 0 or malformed_rows:
            issues.append(
                {
                    "code": "table_misalignment",
                    "page": page_number,
                    "table_id": table_id,
                    "expected_columns": expected,
                    "row_widths": widths,
                    "malformed_rows": malformed_rows,
                }
            )
    return issues


def _normalize_blocks(raw_blocks: list[Any], page: int) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for index, item in enumerate(raw_blocks):
        if not isinstance(item, dict):
            continue
        block = dict(item)
        block["block_id"] = str(block.get("block_id") or f"p{page}-b{index + 1}")
        block["type"] = str(block.get("type") or block.get("block_type") or "Para")
        block["order"] = int(block.get("order", index))
        block["text"] = str(block.get("text") or "")
        blocks.append(block)
    return blocks


def _reading_order_risk(blocks: list[dict[str, Any]], payload: dict[str, Any]) -> str:
    explicit = str(payload.get("reading_order_risk") or "").lower()
    if explicit in {"low", "medium", "high"}:
        return explicit
    if not blocks:
        return "unknown"
    orders = [int(block.get("order", index)) for index, block in enumerate(blocks)]
    if len(orders) != len(set(orders)):
        return "high"
    return "medium" if orders != sorted(orders) else "low"


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return max(0.0, min(1.0, float(value)))
