from __future__ import annotations

import os
import sys
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Literal

import orjson

from .external_document_parsers import ExternalParserUnavailable, load_docling_records

DocumentIntakeStatus = Literal["parsed", "needs_ocr", "failed"]
ParserBackend = Literal["auto", "native", "deepdoc", "mineru", "docling", "unstructured"]
ChunkingMethod = Literal["general", "manual", "paper", "book", "laws", "presentation", "one"]
OcrMode = Literal["auto", "always", "never"]

COMMON_QUALITY_GATES: tuple[str, ...] = (
    "source_identity",
    "record_identity",
    "chunk_identity",
    "citation_metadata",
    "chunk_size",
    "source_kind",
)
REQUIRED_CHUNK_METADATA: tuple[str, ...] = (
    "source_file",
    "record_id",
    "page_nums",
    "source_kind",
    "char_count",
    "estimated_tokens",
)
PDF_VISUAL_TASKS: tuple[str, ...] = (
    "ocr",
    "document_layout_recognition",
    "table_structure_recognition",
    "table_auto_rotation",
)
RAGFLOW_CHUNKING_METHODS: tuple[ChunkingMethod, ...] = (
    "general",
    "manual",
    "paper",
    "book",
    "laws",
    "presentation",
    "one",
)
CHUNKING_METHOD_DEFAULTS: dict[ChunkingMethod, tuple[int, int]] = {
    "general": (500, 50),
    "manual": (500, 50),
    "paper": (900, 120),
    "book": (800, 120),
    "laws": (700, 100),
    "presentation": (450, 40),
    "one": (1_000_000, 0),
}
DOCLING_ONLY_EXTENSIONS: dict[str, tuple[str, str, bool, bool, bool, tuple[str, ...], str]] = {
    ".pptx": (
        "PPTX",
        "presentation_document",
        False,
        True,
        False,
        ("slide_structure", "reading_order", "speaker_notes_risk"),
        "Parse slides through Docling so layout, titles, lists, and tables survive before chunking.",
    ),
    ".xlsx": (
        "Spreadsheet",
        "spreadsheet_document",
        False,
        False,
        True,
        ("sheet_names", "table_structure", "row_boundaries"),
        "Parse workbook sheets through Docling and preserve table boundaries before indexing.",
    ),
    ".xls": (
        "Spreadsheet",
        "spreadsheet_document",
        False,
        False,
        True,
        ("sheet_names", "table_structure", "row_boundaries"),
        "Parse workbook sheets through Docling and preserve table boundaries before indexing.",
    ),
    ".png": (
        "Image",
        "image_document",
        True,
        True,
        True,
        ("ocr_text", "layout_order", "image_caption_risk"),
        "Run OCR/layout recognition through Docling or an OCR backend before indexing.",
    ),
    ".jpg": (
        "Image",
        "image_document",
        True,
        True,
        True,
        ("ocr_text", "layout_order", "image_caption_risk"),
        "Run OCR/layout recognition through Docling or an OCR backend before indexing.",
    ),
    ".jpeg": (
        "Image",
        "image_document",
        True,
        True,
        True,
        ("ocr_text", "layout_order", "image_caption_risk"),
        "Run OCR/layout recognition through Docling or an OCR backend before indexing.",
    ),
    ".tif": (
        "Image",
        "image_document",
        True,
        True,
        True,
        ("ocr_text", "layout_order", "image_caption_risk"),
        "Run OCR/layout recognition through Docling or an OCR backend before indexing.",
    ),
    ".tiff": (
        "Image",
        "image_document",
        True,
        True,
        True,
        ("ocr_text", "layout_order", "image_caption_risk"),
        "Run OCR/layout recognition through Docling or an OCR backend before indexing.",
    ),
    ".bmp": (
        "Image",
        "image_document",
        True,
        True,
        True,
        ("ocr_text", "layout_order", "image_caption_risk"),
        "Run OCR/layout recognition through Docling or an OCR backend before indexing.",
    ),
}

_REPO_ROOT = Path(__file__).resolve().parents[1]
_CONSOLE_SRC = _REPO_ROOT / "api_server" / "current_console" / "chroma_rag_poc" / "src"
if _CONSOLE_SRC.exists() and str(_CONSOLE_SRC) not in sys.path:
    sys.path.insert(0, str(_CONSOLE_SRC))

from chroma_rag_poc.chunking import chunk_records  # noqa: E402
from chroma_rag_poc.cleaning import clean_records  # noqa: E402
from chroma_rag_poc.parsing import (  # noqa: E402
    dedupe_records,
    get_source_kind,
    is_supported_source,
    load_source_payload,
    parse_payload,
)
from chroma_rag_poc.schemas import ChunkRecord, SourceRecord, TextBlock  # noqa: E402


@dataclass(frozen=True, slots=True)
class DocumentIntakeOptions:
    parser_backend: ParserBackend = "auto"
    chunking_method: ChunkingMethod = "general"
    use_ocr: OcrMode = "auto"
    visual_tasks: tuple[str, ...] | None = None
    max_preview_chunks: int = 5
    external_parser_fallback: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class DocumentIntakeProfile:
    source_name: str
    source_kind: str
    extension: str
    parser_route: str
    requires_ocr: bool
    requires_layout_analysis: bool
    requires_table_structure_recognition: bool
    quality_gates: tuple[str, ...]
    risks: tuple[str, ...]
    recommended_next_step: str
    metadata_requirements: tuple[str, ...] = REQUIRED_CHUNK_METADATA

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class DocumentIntakeResult:
    profile: DocumentIntakeProfile
    status: DocumentIntakeStatus
    records: list[SourceRecord]
    chunks: list[ChunkRecord]
    quality: dict[str, Any]
    errors: list[str]
    warnings: list[str]
    processing_plan: dict[str, Any]
    page_diagnostics: list[dict[str, Any]]
    chunk_preview: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "profile": self.profile.to_dict(),
            "records_count": len(self.records),
            "chunk_count": len(self.chunks),
            "quality": self.quality,
            "processing_plan": self.processing_plan,
            "page_diagnostics": self.page_diagnostics,
            "chunk_preview": self.chunk_preview,
            "records": [_record_to_dict(record) for record in self.records],
            "chunks": [_chunk_to_dict(chunk) for chunk in self.chunks],
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True, slots=True)
class _ParsedPayload:
    records: list[SourceRecord]
    runtime: dict[str, Any]
    warnings: list[str]


def classify_document(source_name: str, raw_bytes: bytes | None = None) -> DocumentIntakeProfile:
    extension = Path(source_name).suffix.lower()
    source_kind = get_source_kind(source_name) if is_supported_source(source_name) else "Other"

    if extension == ".pdf":
        risks = ["layout_sensitive", "table_or_formula_risk", "scanned_pdf_possible"]
        if raw_bytes is not None and raw_bytes[:5] != b"%PDF-":
            risks.append("malformed_pdf_header")
        return DocumentIntakeProfile(
            source_name=source_name,
            source_kind="PDF",
            extension=extension,
            parser_route="pdf_deepdoc_ready",
            requires_ocr=False,
            requires_layout_analysis=True,
            requires_table_structure_recognition=True,
            quality_gates=COMMON_QUALITY_GATES + ("page_metadata", "layout_order", "table_structure_risk"),
            risks=tuple(risks),
            recommended_next_step=(
                "Try native PDF text extraction first; if text is missing, route to OCR/layout/table recognition "
                "before indexing."
            ),
        )

    if extension == ".docx":
        return DocumentIntakeProfile(
            source_name=source_name,
            source_kind="DOCX",
            extension=extension,
            parser_route="office_document",
            requires_ocr=False,
            requires_layout_analysis=False,
            requires_table_structure_recognition=True,
            quality_gates=COMMON_QUALITY_GATES + ("heading_structure", "table_row_serialization"),
            risks=("embedded_table_risk", "image_caption_risk"),
            recommended_next_step="Parse paragraphs and tables, then inspect chunk previews for heading/table boundaries.",
        )

    if extension in DOCLING_ONLY_EXTENSIONS:
        (
            source_kind,
            parser_route,
            requires_ocr,
            requires_layout_analysis,
            requires_table_structure_recognition,
            gates,
            recommended_next_step,
        ) = DOCLING_ONLY_EXTENSIONS[extension]
        return DocumentIntakeProfile(
            source_name=source_name,
            source_kind=source_kind,
            extension=extension,
            parser_route=parser_route,
            requires_ocr=requires_ocr,
            requires_layout_analysis=requires_layout_analysis,
            requires_table_structure_recognition=requires_table_structure_recognition,
            quality_gates=COMMON_QUALITY_GATES + gates,
            risks=("requires_docling_runtime",),
            recommended_next_step=recommended_next_step,
        )

    if extension in {".csv", ".tsv"}:
        return DocumentIntakeProfile(
            source_name=source_name,
            source_kind=source_kind,
            extension=extension,
            parser_route="tabular_document",
            requires_ocr=False,
            requires_layout_analysis=False,
            requires_table_structure_recognition=True,
            quality_gates=COMMON_QUALITY_GATES + ("column_headers", "row_boundaries"),
            risks=("table_semantics_require_metadata",),
            recommended_next_step="Preserve column names and row boundaries before retrieval indexing.",
        )

    if extension in {".jsonl", ".ndjson"}:
        return DocumentIntakeProfile(
            source_name=source_name,
            source_kind="JSON",
            extension=extension,
            parser_route="structured_json_lines",
            requires_ocr=False,
            requires_layout_analysis=False,
            requires_table_structure_recognition=False,
            quality_gates=COMMON_QUALITY_GATES + ("structured_record_boundaries",),
            risks=("schema_drift_risk",),
            recommended_next_step="Parse each JSON line as a separate source record and preserve record boundaries.",
        )

    if extension in {".json", ".ipynb"}:
        return DocumentIntakeProfile(
            source_name=source_name,
            source_kind="JSON",
            extension=extension,
            parser_route="structured_json",
            requires_ocr=False,
            requires_layout_analysis=False,
            requires_table_structure_recognition=False,
            quality_gates=COMMON_QUALITY_GATES + ("structured_record_boundaries",),
            risks=("schema_drift_risk",),
            recommended_next_step="Extract title/text/body fields and preserve source record IDs.",
        )

    if source_kind in {"Text", "Markdown", "Log", "Code"}:
        return DocumentIntakeProfile(
            source_name=source_name,
            source_kind=source_kind,
            extension=extension,
            parser_route="text_document",
            requires_ocr=False,
            requires_layout_analysis=False,
            requires_table_structure_recognition=False,
            quality_gates=COMMON_QUALITY_GATES + ("paragraph_boundaries",),
            risks=("plain_text_structure_loss",) if source_kind in {"Log", "Code"} else (),
            recommended_next_step="Parse text blocks, clean short OCR-like fragments, then chunk with overlap.",
        )

    return DocumentIntakeProfile(
        source_name=source_name,
        source_kind=source_kind,
        extension=extension,
        parser_route="unsupported",
        requires_ocr=False,
        requires_layout_analysis=False,
        requires_table_structure_recognition=False,
        quality_gates=COMMON_QUALITY_GATES,
        risks=("unsupported_extension",),
        recommended_next_step="Convert the file to PDF, DOCX, TXT, Markdown, CSV, TSV, JSON, JSONL, or NDJSON.",
    )


def run_document_intake(
    source_name: str,
    raw_bytes: bytes,
    *,
    chunk_size: int = 500,
    overlap: int = 50,
    clean: bool = True,
    allow_partial: bool = True,
    options: DocumentIntakeOptions | None = None,
) -> DocumentIntakeResult:
    options = options or DocumentIntakeOptions()
    profile = classify_document(source_name, raw_bytes)
    chunk_size, overlap = _effective_chunk_settings(
        profile=profile,
        raw_chunk_size=chunk_size,
        raw_overlap=overlap,
        options=options,
    )
    processing_plan = _build_processing_plan(
        profile=profile,
        options=options,
        status="parsed",
        chunk_size=chunk_size,
        overlap=overlap,
    )
    errors: list[str] = []
    warnings: list[str] = []

    if profile.parser_route == "unsupported":
        errors.append(f"Unsupported source extension: {profile.extension or 'unknown'}")
        if not allow_partial:
            raise ValueError(errors[0])
        return _empty_result(
            profile=profile,
            status="failed",
            errors=errors,
            warnings=warnings,
            processing_plan=processing_plan,
            options=options,
        )

    try:
        parsed = _load_records_for_profile(profile, raw_bytes, options)
        records = parsed.records
        warnings.extend(parsed.warnings)
        if clean:
            records = clean_records(records)
        chunks = chunk_records(records, chunk_size=chunk_size, overlap=overlap)
        warnings.extend(_profile_warnings(profile, records, chunks))
        quality = _build_quality(
            profile=profile,
            records=records,
            chunks=chunks,
            status="parsed",
            processing_plan=processing_plan,
        )
        status: DocumentIntakeStatus = "parsed" if chunks and quality["quality_gate_status"] == "pass" else "failed"
        processing_plan = _build_processing_plan(
            profile=profile,
            options=options,
            status=status,
            chunk_size=chunk_size,
            overlap=overlap,
            runtime=parsed.runtime,
        )
        return DocumentIntakeResult(
            profile=profile,
            status=status,
            records=records,
            chunks=chunks,
            quality=quality,
            errors=errors,
            warnings=warnings,
            processing_plan=processing_plan,
            page_diagnostics=_build_page_diagnostics(records),
            chunk_preview=_build_chunk_preview(chunks, limit=options.max_preview_chunks),
        )
    except Exception as exc:
        errors.append(str(exc))
        if profile.source_kind == "PDF":
            ocr_profile = _mark_pdf_as_needing_ocr(profile)
            warnings.append("Native PDF parsing failed; OCR/layout/table recognition is required before indexing.")
            processing_plan = _build_processing_plan(
                profile=ocr_profile,
                options=options,
                status="needs_ocr",
                chunk_size=chunk_size,
                overlap=overlap,
            )
            return _empty_result(
                profile=ocr_profile,
                status="needs_ocr",
                errors=errors,
                warnings=warnings,
                processing_plan=processing_plan,
                options=options,
            )
        if not allow_partial:
            raise
        processing_plan = _build_processing_plan(
            profile=profile,
            options=options,
            status="failed",
            chunk_size=chunk_size,
            overlap=overlap,
        )
        return _empty_result(
            profile=profile,
            status="failed",
            errors=errors,
            warnings=warnings,
            processing_plan=processing_plan,
            options=options,
        )


def _load_records_for_profile(
    profile: DocumentIntakeProfile,
    raw_bytes: bytes,
    options: DocumentIntakeOptions,
) -> _ParsedPayload:
    if options.parser_backend == "docling" or _requires_docling_backend(profile):
        if not _should_attempt_docling_runtime():
            if not options.external_parser_fallback:
                raise ExternalParserUnavailable(
                    "Docling runtime is disabled for this process. Set POWER_RAG_ENABLE_DOCLING_RUNTIME=1 to enable it."
                )
            records = _load_native_records(profile, raw_bytes)
            return _ParsedPayload(
                records=records,
                runtime={
                    "name": "docling",
                    "status": "fallback_to_native",
                    "error": "Docling runtime disabled; set POWER_RAG_ENABLE_DOCLING_RUNTIME=1 to enable it.",
                },
                warnings=["Docling runtime disabled; native parser fallback was used."],
            )
        try:
            records = load_docling_records(raw_bytes, source_name=profile.source_name)
            return _ParsedPayload(
                records=records,
                runtime={"name": "docling", "status": "used"},
                warnings=[],
            )
        except ExternalParserUnavailable as exc:
            if not options.external_parser_fallback:
                raise
            records = _load_native_records(profile, raw_bytes)
            return _ParsedPayload(
                records=records,
                runtime={"name": "docling", "status": "fallback_to_native", "error": str(exc)},
                warnings=[str(exc)],
            )
        except Exception as exc:
            if not options.external_parser_fallback:
                raise
            records = _load_native_records(profile, raw_bytes)
            return _ParsedPayload(
                records=records,
                runtime={"name": "docling", "status": "fallback_to_native", "error": str(exc)},
                warnings=[f"Docling failed; native parser fallback was used: {exc}"],
            )
    return _ParsedPayload(
        records=_load_native_records(profile, raw_bytes),
        runtime={"name": "native", "status": "used"},
        warnings=[],
    )


def _should_attempt_docling_runtime() -> bool:
    if getattr(load_docling_records, "__module__", "") != "data_pipeline.external_document_parsers":
        return True
    return os.environ.get("POWER_RAG_ENABLE_DOCLING_RUNTIME", "").strip().lower() in {"1", "true", "yes", "on"}


def _load_native_records(profile: DocumentIntakeProfile, raw_bytes: bytes) -> list[SourceRecord]:
    if profile.parser_route == "structured_json_lines":
        return _load_json_lines(raw_bytes, profile.source_name)
    return load_source_payload(raw_bytes, source_name=profile.source_name)


def _requires_docling_backend(profile: DocumentIntakeProfile) -> bool:
    return profile.extension in DOCLING_ONLY_EXTENSIONS


def _load_json_lines(raw_bytes: bytes, source_name: str) -> list[SourceRecord]:
    payload: list[Any] = []
    for line_number, raw_line in enumerate(raw_bytes.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload.append(orjson.loads(line))
        except orjson.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSONL at line {line_number}: {exc}") from exc
    if not payload:
        raise ValueError("JSONL file is empty or contains no valid records")
    return dedupe_records(parse_payload(payload, source_name=source_name))


def _mark_pdf_as_needing_ocr(profile: DocumentIntakeProfile) -> DocumentIntakeProfile:
    risks = list(profile.risks)
    if "scanned_pdf_or_image_only" not in risks:
        risks.append("scanned_pdf_or_image_only")
    return replace(
        profile,
        requires_ocr=True,
        risks=tuple(risks),
        recommended_next_step=(
            "Run OCR plus layout/table recognition, then send the extracted text blocks back through document intake."
        ),
    )


def _profile_warnings(
    profile: DocumentIntakeProfile,
    records: list[SourceRecord],
    chunks: list[ChunkRecord],
) -> list[str]:
    warnings: list[str] = []
    if profile.requires_table_structure_recognition and profile.parser_route != "tabular_document":
        warnings.append("Table-heavy documents should be previewed before indexing because table structure may be flattened.")
    if profile.requires_layout_analysis and not any(record.page_num for record in records):
        warnings.append("No page metadata was extracted; citation quality should be inspected before retrieval use.")
    if records and not chunks:
        warnings.append("Records were parsed but no chunks were produced.")
    return warnings


def _build_quality(
    *,
    profile: DocumentIntakeProfile,
    records: list[SourceRecord],
    chunks: list[ChunkRecord],
    status: DocumentIntakeStatus,
    processing_plan: dict[str, Any],
) -> dict[str, Any]:
    missing_metadata: list[str] = []
    for chunk in chunks:
        for key in REQUIRED_CHUNK_METADATA:
            value = chunk.metadata.get(key)
            if value is None or value == "":
                missing_metadata.append(f"{chunk.chunk_id or '<missing_chunk_id>'}:{key}")
        if not chunk.chunk_id:
            missing_metadata.append("<missing_chunk_id>:chunk_id")
        if not chunk.text:
            missing_metadata.append(f"{chunk.chunk_id or '<missing_chunk_id>'}:text")

    total_record_chars = sum(len(record.text or "") for record in records)
    total_chunk_chars = sum(len(chunk.text or "") for chunk in chunks)
    gate_status = "pass" if status == "parsed" and chunks and not missing_metadata else "fail"
    return {
        "quality_gate_status": gate_status,
        "parser_route": profile.parser_route,
        "record_count": len(records),
        "chunk_count": len(chunks),
        "total_record_chars": total_record_chars,
        "total_chunk_chars": total_chunk_chars,
        "missing_required_metadata": missing_metadata,
        "required_chunk_metadata": list(REQUIRED_CHUNK_METADATA),
        "quality_gates": list(profile.quality_gates),
        "pending_visual_tasks": list(processing_plan.get("next_queue") or []),
    }


def _empty_result(
    *,
    profile: DocumentIntakeProfile,
    status: DocumentIntakeStatus,
    errors: list[str],
    warnings: list[str],
    processing_plan: dict[str, Any],
    options: DocumentIntakeOptions,
) -> DocumentIntakeResult:
    quality = {
        "quality_gate_status": "needs_ocr" if status == "needs_ocr" else "fail",
        "parser_route": profile.parser_route,
        "record_count": 0,
        "chunk_count": 0,
        "total_record_chars": 0,
        "total_chunk_chars": 0,
        "missing_required_metadata": [],
        "required_chunk_metadata": list(REQUIRED_CHUNK_METADATA),
        "quality_gates": list(profile.quality_gates),
        "pending_visual_tasks": list(processing_plan.get("next_queue") or []),
    }
    return DocumentIntakeResult(
        profile=profile,
        status=status,
        records=[],
        chunks=[],
        quality=quality,
        errors=errors,
        warnings=warnings,
        processing_plan=processing_plan,
        page_diagnostics=[],
        chunk_preview=[],
    )


def _effective_chunk_settings(
    *,
    profile: DocumentIntakeProfile,
    raw_chunk_size: int,
    raw_overlap: int,
    options: DocumentIntakeOptions,
) -> tuple[int, int]:
    if options.chunking_method == "one":
        return CHUNKING_METHOD_DEFAULTS["one"]
    if raw_chunk_size == CHUNKING_METHOD_DEFAULTS["general"][0] and raw_overlap == CHUNKING_METHOD_DEFAULTS["general"][1]:
        return CHUNKING_METHOD_DEFAULTS.get(options.chunking_method, (raw_chunk_size, raw_overlap))
    return raw_chunk_size, raw_overlap


def _build_processing_plan(
    *,
    profile: DocumentIntakeProfile,
    options: DocumentIntakeOptions,
    status: DocumentIntakeStatus,
    chunk_size: int,
    overlap: int,
    runtime: dict[str, Any] | None = None,
) -> dict[str, Any]:
    parser_backend = _resolve_parser_backend(profile, options.parser_backend)
    visual_tasks = list(_resolve_visual_tasks(profile, options))
    next_queue = visual_tasks if status == "needs_ocr" else []
    return {
        "parser_backend": parser_backend,
        "chunking_method": options.chunking_method,
        "supported_chunking_methods": list(RAGFLOW_CHUNKING_METHODS),
        "parse_chunk_decoupled": True,
        "visual_tasks": visual_tasks,
        "next_queue": next_queue,
        "runtime": runtime or {"name": parser_backend, "status": "planned"},
        "effective_chunk_size": chunk_size,
        "effective_overlap": overlap,
        "stages": [
            {"name": "classify", "status": "done"},
            {"name": "parse", "status": "blocked" if status == "needs_ocr" else "done"},
            {"name": "visual_parse", "status": "queued" if status == "needs_ocr" else "not_required"},
            {"name": "clean", "status": "skipped" if status != "parsed" else "done"},
            {"name": "chunk", "status": "skipped" if status != "parsed" else "done"},
            {"name": "quality_gate", "status": "needs_ocr" if status == "needs_ocr" else status},
        ],
        "options": options.to_dict(),
    }


def _resolve_parser_backend(profile: DocumentIntakeProfile, requested: ParserBackend) -> str:
    if requested != "auto":
        return requested
    if _requires_docling_backend(profile):
        return "docling"
    if profile.source_kind == "PDF":
        return "deepdoc"
    if profile.parser_route in {"office_document", "tabular_document", "structured_json", "structured_json_lines"}:
        return "native"
    return "native"


def _resolve_visual_tasks(profile: DocumentIntakeProfile, options: DocumentIntakeOptions) -> tuple[str, ...]:
    if options.visual_tasks is not None:
        return tuple(options.visual_tasks)
    if profile.source_kind != "PDF":
        return ()
    tasks = list(PDF_VISUAL_TASKS)
    if options.use_ocr == "never":
        tasks = [task for task in tasks if task != "ocr"]
    elif options.use_ocr == "always" and "ocr" not in tasks:
        tasks.insert(0, "ocr")
    return tuple(tasks)


def _build_page_diagnostics(records: list[SourceRecord]) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    for record in records:
        label_counts: dict[str, int] = {}
        for block in record.blocks:
            label_counts[block.block_type] = label_counts.get(block.block_type, 0) + 1
        page_num = record.page_num if record.page_num is not None else -1
        diagnostics.append(
            {
                "source_file": record.source_file,
                "record_id": record.record_id,
                "page_num": page_num,
                "total_pages": record.total_pages,
                "char_count": len(record.text or ""),
                "block_count": len(record.blocks),
                "label_counts": label_counts,
                "has_page_metadata": page_num != -1,
            }
        )
    return diagnostics


def _build_chunk_preview(chunks: list[ChunkRecord], *, limit: int) -> list[dict[str, Any]]:
    preview: list[dict[str, Any]] = []
    for chunk in chunks[: max(limit, 0)]:
        metadata = dict(chunk.metadata)
        source_file = str(metadata.get("source_file") or "")
        page_nums = str(metadata.get("page_nums") or "")
        chunk_index = metadata.get("chunk_index", "")
        anchor_suffix = page_nums if page_nums and page_nums != "[-1]" else f"chunk-{chunk_index}"
        preview.append(
            {
                "chunk_id": chunk.chunk_id,
                "citation_anchor": f"{source_file}#{anchor_suffix}",
                "source_file": source_file,
                "record_id": metadata.get("record_id"),
                "page_nums": page_nums,
                "char_count": metadata.get("char_count"),
                "estimated_tokens": metadata.get("estimated_tokens"),
                "text_preview": (chunk.text or "")[:240],
            }
        )
    return preview


def _record_to_dict(record: SourceRecord) -> dict[str, Any]:
    return {
        "source_file": record.source_file,
        "record_id": record.record_id,
        "filename": record.filename,
        "page_num": record.page_num,
        "total_pages": record.total_pages,
        "doc_id": record.doc_id,
        "char_count": len(record.text or ""),
        "block_count": len(record.blocks),
        "metadata": dict(record.metadata),
        "text_preview": (record.text or "")[:500],
    }


def _chunk_to_dict(chunk: ChunkRecord) -> dict[str, Any]:
    return {
        "chunk_id": chunk.chunk_id,
        "text": chunk.text,
        "metadata": dict(chunk.metadata),
    }
