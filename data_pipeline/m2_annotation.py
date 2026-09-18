"""Language, lossless repair, structural IDs, and aligned translation for M2."""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any, Protocol
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from chroma_rag_poc.schemas import SourceRecord, TextBlock
from chroma_rag_poc.text_utils import normalize_text

LanguageCode = str


class TranslationUnavailable(RuntimeError):
    """Raised when aligned translation was requested without a usable provider."""


class TranslationProvider(Protocol):
    def __call__(self, text: str, source_language: str, target_language: str) -> str: ...


@dataclass(frozen=True, slots=True)
class AnnotationSummary:
    detected_languages: tuple[str, ...]
    repair_count: int
    translation_target: str | None
    translated_block_count: int
    alignment_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "detected_languages": list(self.detected_languages),
            "repair_count": self.repair_count,
            "translation_target": self.translation_target,
            "translated_block_count": self.translated_block_count,
            "alignment_count": self.alignment_count,
        }


def detect_language(text: str) -> LanguageCode:
    """Return ``zh``, ``en``, ``mixed``, or ``unknown`` without external models."""

    han = len(re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    meaningful = han + latin
    if meaningful == 0:
        return "unknown"
    if han and latin and min(han, latin) / meaningful >= 0.12:
        return "mixed"
    return "zh" if han > latin else "en"


def repair_sentence_breaks(text: str) -> tuple[str, list[dict[str, Any]]]:
    """Repair conservative OCR line breaks while retaining a reversible audit."""

    original = str(text or "")
    repaired = original.replace("\r\n", "\n").replace("\r", "\n")
    operations: list[dict[str, Any]] = []
    rules = (
        ("latin_hyphenation", re.compile(r"(?<=[A-Za-z])-\n(?=[A-Za-z])"), ""),
        ("cjk_soft_linebreak", re.compile(r"(?<=[\u3400-\u9fff])\n(?=[\u3400-\u9fff])"), ""),
        ("latin_soft_linebreak", re.compile(r"(?<=[a-z,;:])\n(?=[a-z])"), " "),
    )
    for name, pattern, replacement in rules:
        repaired, count = pattern.subn(replacement, repaired)
        if count:
            operations.append({"rule": name, "replacements": count})
    repaired = normalize_text(repaired)
    return repaired, operations


def configured_http_translator() -> TranslationProvider | None:
    """Create an HTTP translator from ``POWER_RAG_TRANSLATION_URL`` when set.

    The endpoint receives ``text``, ``source``, and ``target`` and may return
    either ``translated_text`` or the LibreTranslate-compatible
    ``translatedText`` field.
    """

    endpoint = os.environ.get("POWER_RAG_TRANSLATION_URL", "").strip()
    if not endpoint:
        return None
    if urlparse(endpoint).scheme not in {"http", "https"}:
        raise TranslationUnavailable("POWER_RAG_TRANSLATION_URL must use http or https")
    timeout = float(os.environ.get("POWER_RAG_TRANSLATION_TIMEOUT_SECONDS", "20"))

    def translate(text: str, source_language: str, target_language: str) -> str:
        body = json.dumps(
            {"text": text, "q": text, "source": source_language, "target": target_language},
            ensure_ascii=False,
        ).encode("utf-8")
        request = Request(  # noqa: S310 - scheme is validated above
            endpoint,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - operator-configured endpoint
            payload = json.loads(response.read().decode("utf-8"))
        translated = str(payload.get("translated_text") or payload.get("translatedText") or "").strip()
        if not translated:
            raise TranslationUnavailable("Translation provider returned no translated text")
        return translated

    return translate


def annotate_records(
    records: list[SourceRecord],
    *,
    translation_target: str | None = None,
    translator: TranslationProvider | Callable[[str, str, str], str] | None = None,
) -> tuple[list[SourceRecord], AnnotationSummary]:
    target = str(translation_target or "").strip().lower() or None
    if target not in {None, "zh", "en"}:
        raise ValueError("translation_target must be zh, en, or omitted")
    translator = translator or (configured_http_translator() if target else None)
    if target and translator is None:
        raise TranslationUnavailable(
            "Aligned translation was requested but no provider is configured; "
            "set POWER_RAG_TRANSLATION_URL or inject app.state.m2_translation_provider."
        )

    output: list[SourceRecord] = []
    languages: set[str] = set()
    repair_count = 0
    translated_count = 0
    alignment_count = 0

    for record in records:
        annotated_blocks: list[TextBlock] = []
        alignments: list[dict[str, Any]] = []
        repair_audit: list[dict[str, Any]] = []
        for order, block in enumerate(record.blocks):
            original_text = str(block.text or "")
            repaired_text, operations = repair_sentence_breaks(original_text)
            language = detect_language(original_text)
            languages.add(language)
            block_id = block.block_id or _stable_block_id(record, block, order)
            metadata = {
                **dict(block.metadata),
                "detected_language": language,
                "original_text": original_text,
                "original_text_sha256": _sha256(original_text),
                "repair_operations": operations,
            }
            if operations:
                repair_count += 1
                repair_audit.append({"block_id": block_id, "operations": operations})

            if target:
                if language == target:
                    translated = repaired_text
                    translation_status = "identity"
                else:
                    if translator is None:  # defensive: target validation above requires it
                        raise TranslationUnavailable("Translation provider is unavailable")
                    translated = str(translator(repaired_text, language, target)).strip()
                    if not translated:
                        raise TranslationUnavailable(f"No translation returned for block {block_id}")
                    translated_count += 1
                    translation_status = "translated"
                alignments.append(
                    {
                        "alignment_id": f"{block_id}:{target}",
                        "block_id": block_id,
                        "source_language": language,
                        "target_language": target,
                        "source_text": repaired_text,
                        "translated_text": translated,
                        "status": translation_status,
                    }
                )
                alignment_count += 1

            annotated_blocks.append(
                replace(
                    block,
                    text=repaired_text,
                    order=order,
                    block_id=block_id,
                    metadata=metadata,
                )
            )

        if not annotated_blocks and record.text:
            repaired_text, operations = repair_sentence_breaks(record.text)
            language = detect_language(record.text)
            languages.add(language)
            block = TextBlock(
                text=repaired_text,
                block_type="Para",
                order=0,
                page_num=record.page_num if record.page_num is not None else -1,
                block_id=_stable_id(record.record_id, "block", "0"),
                metadata={
                    "detected_language": language,
                    "original_text": record.text,
                    "original_text_sha256": _sha256(record.text),
                    "repair_operations": operations,
                },
            )
            annotated_blocks.append(block)
            if operations:
                repair_count += 1

        record_language = _combine_languages(
            [str(block.metadata.get("detected_language") or "unknown") for block in annotated_blocks]
        )
        record_metadata = {
            **dict(record.metadata),
            "detected_language": record_language,
            "original_text": record.text,
            "original_text_sha256": _sha256(record.text),
            "repair_audit_json": json.dumps(repair_audit, ensure_ascii=False),
            "translation_target": target or "",
            "translation_status": "complete" if target else "not_requested",
            "translation_alignment_json": json.dumps(alignments, ensure_ascii=False),
        }
        output.append(
            replace(
                record,
                text=_structured_text(annotated_blocks),
                blocks=annotated_blocks,
                metadata=record_metadata,
            )
        )

    return output, AnnotationSummary(
        detected_languages=tuple(sorted(languages)),
        repair_count=repair_count,
        translation_target=target,
        translated_block_count=translated_count,
        alignment_count=alignment_count,
    )


def _stable_block_id(record: SourceRecord, block: TextBlock, order: int) -> str:
    page = block.page_num if block.page_num >= 0 else record.page_num or -1
    return _stable_id(record.record_id, str(page), str(order), block.block_type, block.text)


def _stable_id(*parts: str) -> str:
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"BLK-{digest}"


def _sha256(text: str) -> str:
    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()


def _combine_languages(values: list[str]) -> str:
    meaningful = {value for value in values if value != "unknown"}
    if not meaningful:
        return "unknown"
    return next(iter(meaningful)) if len(meaningful) == 1 else "mixed"


def _structured_text(blocks: list[TextBlock]) -> str:
    return "\n\n".join(block.text for block in blocks if block.text.strip())
