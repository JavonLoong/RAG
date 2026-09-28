"""Connected M2 OCR, quality, source comparison, and review workflow."""

from __future__ import annotations

import base64
import io
import mimetypes
from pathlib import Path
from typing import Any

from data_pipeline.m2_ocr import (
    OCRBackendUnavailable,
    OCRProvider,
    detect_table_misalignment,
    render_source_preview,
    run_ocr,
)
from storage_layer.governance_store import GovernanceStore


class M2DeliveryService:
    def __init__(self, store: GovernanceStore, *, ocr_provider: OCRProvider | None = None) -> None:
        self.store = store
        self.ocr_provider = ocr_provider

    def register_source(
        self,
        *,
        document_id: str,
        source_name: str,
        content: bytes,
        created_by: str = "system",
    ) -> dict[str, Any]:
        return self.store.register_source_asset(
            document_id=document_id,
            source_name=source_name,
            content=content,
            mime_type=mimetypes.guess_type(source_name)[0] or "application/octet-stream",
            page_count=_source_page_count(source_name, content),
            created_by=created_by,
        )

    def create_review_task(self, version, source_asset_id: str | None) -> dict[str, Any]:
        return self.store.create_document_review_task(
            document_version_id=version.version_id,
            source_asset_id=source_asset_id,
            reasons=[item.to_dict() for item in version.quality_issues]
            or [{"code": "publication_approval", "message": "Human approval is required before publication."}],
        )

    def queue_ocr(
        self,
        *,
        document_id: str,
        source_asset_id: str,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        backend = "injected" if self.ocr_provider is not None else "configured-command"
        return self.store.create_ocr_job(
            document_id=document_id,
            source_asset_id=source_asset_id,
            backend=backend,
            timeout_seconds=timeout_seconds,
        )

    def execute_ocr(self, job_id: str) -> dict[str, Any]:
        job = self.store.get_ocr_job(job_id)
        asset = self.store.get_source_asset(str(job["source_asset_id"]), include_content=True)
        self.store.update_ocr_job(job_id, status="running", increment_attempt=True)
        try:
            result = run_ocr(
                bytes(asset["content"]),
                str(asset["source_name"]),
                provider=self.ocr_provider,
                page_timeout_seconds=float(job["timeout_seconds"]),
            )
            version, quality, review_task = self.ingest_ocr_result(
                document_id=str(job["document_id"]),
                source_name=str(asset["source_name"]),
                pages=[dict(item) for item in result.pages],
                expected_pages=result.expected_pages,
                low_confidence_threshold=0.6,
                source_asset_id=str(asset["asset_id"]),
                job_id=job_id,
                timeout_pages=list(result.timeout_pages),
                failed_pages=list(result.failed_pages),
                metadata={"ocr_backend": str(job["backend"])},
                created_by=str(asset.get("created_by") or "system"),
            )
            return {
                "ocr_job": self.store.get_ocr_job(job_id),
                "document_version": version.to_dict(),
                "ocr_quality": quality,
                "review_task": review_task,
            }
        except OCRBackendUnavailable as exc:
            job = self.store.update_ocr_job(job_id, status="blocked", errors=[str(exc)])
            return {"ocr_job": job, "document_version": None, "ocr_quality": None, "review_task": None}
        except Exception as exc:
            self.store.update_ocr_job(job_id, status="failed", errors=[str(exc)])
            raise

    def retry_ocr_pages(self, job_id: str, page_numbers: list[int]) -> dict[str, Any]:
        """Retry selected OCR pages while preserving successful pages from the prior run."""

        requested_pages = sorted({int(page) for page in page_numbers})
        if not requested_pages or requested_pages[0] < 1:
            raise ValueError("OCR retry requires positive page numbers")  # noqa: TRY003
        job = self.store.get_ocr_job(job_id)
        asset = self.store.get_source_asset(str(job["source_asset_id"]), include_content=True)
        prior_pages = {
            int(item.get("page") or 0): dict(item)
            for item in job.get("pages") or []
            if int(item.get("page") or 0) > 0
        }
        self.store.update_ocr_job(job_id, status="running", increment_attempt=True)
        try:
            result = run_ocr(
                bytes(asset["content"]),
                str(asset["source_name"]),
                provider=self.ocr_provider,
                page_timeout_seconds=float(job["timeout_seconds"]),
                page_numbers=requested_pages,
            )
            for page in result.pages:
                prior_pages[int(page["page"])] = dict(page)
            combined_pages = [prior_pages[page] for page in sorted(prior_pages)]
            failed_pages = [
                int(page["page"])
                for page in combined_pages
                if str(page.get("status") or "ok") == "error"
            ]
            timeout_pages = [
                int(page["page"])
                for page in combined_pages
                if str(page.get("status") or "ok") == "timeout"
            ]
            version, quality, review_task = self.ingest_ocr_result(
                document_id=str(job["document_id"]),
                source_name=str(asset["source_name"]),
                pages=combined_pages,
                expected_pages=result.expected_pages,
                low_confidence_threshold=0.6,
                source_asset_id=str(asset["asset_id"]),
                job_id=job_id,
                timeout_pages=timeout_pages,
                failed_pages=failed_pages,
                metadata={
                    "ocr_backend": str(job["backend"]),
                    "retry_of_version_id": job.get("result_version_id"),
                    "retried_pages": requested_pages,
                },
                created_by=str(asset.get("created_by") or "system"),
            )
            return {
                "ocr_job": self.store.get_ocr_job(job_id),
                "document_version": version.to_dict(),
                "ocr_quality": quality,
                "review_task": review_task,
                "retried_pages": requested_pages,
            }
        except OCRBackendUnavailable as exc:
            job = self.store.update_ocr_job(job_id, status="blocked", errors=[str(exc)])
            return {
                "ocr_job": job,
                "document_version": None,
                "ocr_quality": None,
                "review_task": None,
                "retried_pages": requested_pages,
            }
        except Exception as exc:
            self.store.update_ocr_job(job_id, status="failed", errors=[str(exc)])
            raise

    def ingest_ocr_result(
        self,
        *,
        document_id: str,
        source_name: str,
        pages: list[dict[str, Any]],
        expected_pages: int,
        low_confidence_threshold: float,
        source_asset_id: str | None = None,
        job_id: str | None = None,
        timeout_pages: list[int] | None = None,
        failed_pages: list[int] | None = None,
        metadata: dict[str, Any] | None = None,
        created_by: str = "system",
    ):
        page_numbers = [int(item.get("page") or 0) for item in pages]
        if not page_numbers or any(page < 1 for page in page_numbers):
            raise ValueError("OCR pages must use positive page numbers")  # noqa: TRY003
        if len(page_numbers) != len(set(page_numbers)):
            raise ValueError("OCR pages must use unique page numbers")  # noqa: TRY003

        missing_pages = sorted(set(range(1, expected_pages + 1)) - set(page_numbers))
        blank_pages = sorted(
            int(item.get("page") or 0) for item in pages if not str(item.get("text") or "").strip()
        )
        low_confidence_pages = sorted(
            int(item.get("page") or 0)
            for item in pages
            if item.get("confidence") is not None and float(item["confidence"]) < low_confidence_threshold
        )
        layout_risk_pages = sorted(
            int(item.get("page") or 0)
            for item in pages
            if str(item.get("reading_order_risk") or "unknown") in {"medium", "high"}
        )
        timeout_pages = sorted(
            set(timeout_pages or [])
            | {int(item.get("page") or 0) for item in pages if item.get("status") == "timeout"}
        )
        failed_pages = sorted(
            set(failed_pages or [])
            | {int(item.get("page") or 0) for item in pages if item.get("status") == "error"}
        )
        table_issues = [
            dict(issue)
            for page in pages
            for issue in (page.get("table_misalignment") or detect_table_misalignment(page))
        ]
        chunks = _ocr_chunks(source_name, pages)
        blocking = bool(missing_pages or failed_pages or timeout_pages or table_issues or not chunks)
        warnings = [
            *(f"Blank OCR page: {page}" for page in blank_pages),
            *(f"Low OCR confidence page: {page}" for page in low_confidence_pages),
            *(f"Reading-order review required for page: {page}" for page in layout_risk_pages),
            *(f"Table alignment review required for page: {item.get('page')}" for item in table_issues),
        ]
        errors = [
            *(f"Missing OCR page: {page}" for page in missing_pages),
            *(f"OCR page failed: {page}" for page in failed_pages),
            *(f"OCR page timed out: {page}" for page in timeout_pages),
        ]
        quality = {
            "quality_gate_status": "fail" if blocking else "pass",
            "expected_pages": expected_pages,
            "received_pages": len(page_numbers),
            "text_pages": len({
                int(item["page"]) for item in pages if str(item.get("text") or "").strip()
            }),
            "missing_pages": missing_pages,
            "blank_pages": blank_pages,
            "low_confidence_pages": low_confidence_pages,
            "layout_risk_pages": layout_risk_pages,
            "table_misalignment": table_issues,
            "timeout_pages": timeout_pages,
            "failed_pages": failed_pages,
            "low_confidence_threshold": low_confidence_threshold,
        }
        version = self.store.create_document_candidate(
            document_id=document_id,
            source_name=source_name,
            chunks=chunks,
            intake_status="partial" if blocking else "parsed",
            quality=quality,
            warnings=warnings,
            errors=errors,
            metadata={
                **dict(metadata or {}),
                "ocr_quality": quality,
                "intake_route": "ocr_result",
                "source_asset_id": source_asset_id,
                "ocr_job_id": job_id,
            },
            created_by=created_by,
        )
        review_task = self.create_review_task(version, source_asset_id)
        if job_id:
            self.store.update_ocr_job(
                job_id,
                status="needs_review" if version.quality_issues else "completed",
                expected_pages=expected_pages,
                result_version_id=version.version_id,
                pages=pages,
                errors=errors,
            )
        return version, quality, review_task

    def review_package(self, version_id: str, *, page: int = 1) -> dict[str, Any]:
        version = self.store.get_document_version(version_id)
        tasks = self.store.list_document_review_tasks(version_id)
        source_asset_id = str(version.metadata.get("source_asset_id") or "") or (
            str(tasks[-1].get("source_asset_id") or "") if tasks else ""
        )
        preview: dict[str, Any] | None = None
        if source_asset_id:
            asset = self.store.get_source_asset(source_asset_id, include_content=True)
            try:
                image, mime_type = render_source_preview(
                    bytes(asset["content"]), str(asset["source_name"]), page=page
                )
                preview = {
                    "asset_id": source_asset_id,
                    "source_name": asset["source_name"],
                    "page": page,
                    "page_count": asset.get("page_count"),
                    "mime_type": mime_type,
                    "content_base64": base64.b64encode(image).decode("ascii"),
                    "content_hash": asset["content_hash"],
                }
            except ValueError as exc:
                preview = {"asset_id": source_asset_id, "page": page, "error": str(exc)}
        evidence = [item.to_dict() for item in version.evidence if item.page in {None, str(page)}]
        return {
            "document_version": version.to_dict(include_evidence=False),
            "source_preview": preview,
            "editable_candidate": evidence,
            "quality_issues": [item.to_dict() for item in version.quality_issues],
            "review_tasks": tasks,
            "review_history": [item.to_dict() for item in self.store.list_reviews("document", version_id)],
        }

    def source_page(self, asset_id: str, *, page: int = 1) -> tuple[bytes, str]:
        asset = self.store.get_source_asset(asset_id, include_content=True)
        return render_source_preview(bytes(asset["content"]), str(asset["source_name"]), page=page)


def _source_page_count(source_name: str, content: bytes) -> int | None:
    suffix = Path(source_name).suffix.lower()
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader

            return len(PdfReader(io.BytesIO(content)).pages)
        except Exception:  # pragma: no cover - corrupt/encrypted source remains reviewable
            return None
    if suffix in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif", ".txt", ".md"}:
        return 1
    return None


def _ocr_chunks(source_name: str, pages: list[dict[str, Any]]) -> list[dict[str, Any]]:  # noqa: C901
    chunks: list[dict[str, Any]] = []
    for page in pages:
        page_number = int(page.get("page") or 0)
        blocks = [dict(item) for item in page.get("blocks") or [] if isinstance(item, dict)]
        represented_tables = {str(item.get("table_id")) for item in blocks if item.get("table_id")}
        if blocks:
            for index, block in enumerate(sorted(blocks, key=lambda item: int(item.get("order", 0))), start=1):
                block_id = str(block.get("block_id") or f"p{page_number}-b{index}")
                block_type = str(block.get("type") or block.get("block_type") or "Para")
                text = str(block.get("text") or "").strip()
                if not text and block_type.casefold() == "image":
                    text = f"[Image {block.get('image_id') or block_id}]"
                if not text:
                    continue
                chunks.append({
                    "chunk_id": block_id,
                    "text": text,
                    "source_file": source_name,
                    "page": page_number,
                    "block_id": block_id,
                    "table_id": block.get("table_id"),
                    "image_id": block.get("image_id"),
                    "metadata": {
                        **dict(block.get("metadata") or {}),
                        "block_type": block_type,
                        "reading_order": int(block.get("order", index - 1)),
                        "bbox": block.get("bbox"),
                        "caption_for": block.get("caption_for"),
                        "ocr_confidence": page.get("confidence"),
                        "reading_order_risk": page.get("reading_order_risk"),
                    },
                })
        elif str(page.get("text") or "").strip():
            chunks.append({
                "chunk_id": str(page.get("block_id") or f"page-{page_number:05d}"),
                "text": str(page.get("text") or ""),
                "source_file": source_name,
                "page": page_number,
                "block_id": page.get("block_id"),
                "table_id": page.get("table_id"),
                "image_id": page.get("image_id"),
                "metadata": {
                    **dict(page.get("metadata") or {}),
                    "ocr_confidence": page.get("confidence"),
                    "reading_order_risk": page.get("reading_order_risk"),
                },
            })
        for table_index, table in enumerate(page.get("tables") or [], start=1):
            table = dict(table)
            table_id = str(table.get("table_id") or f"p{page_number}-t{table_index}")
            if table_id in represented_tables:
                continue
            for row_index, row in enumerate(table.get("rows") or []):
                text = " | ".join(str(cell) for cell in row)
                if text.strip(" |"):
                    chunks.append({
                        "chunk_id": f"{table_id}-r{row_index}",
                        "text": text,
                        "source_file": source_name,
                        "page": page_number,
                        "block_id": f"{table_id}-r{row_index}",
                        "table_id": table_id,
                        "metadata": {
                            **dict(table.get("metadata") or {}),
                            "block_type": "Table",
                            "row_index": row_index,
                            "expected_columns": table.get("expected_columns"),
                            "bbox": table.get("bbox"),
                        },
                    })
    return chunks
