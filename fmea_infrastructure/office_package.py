"""Shared fail-closed inspection for bounded OPC Office packages."""

# XML is parsed only after ZIP limits and contained member-name checks.
# ruff: noqa: TRY003

from __future__ import annotations

import io
import math
import posixpath
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath
from types import MappingProxyType
from urllib.parse import unquote, urlsplit
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile, ZipFile

from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import fromstring as safe_xml_fromstring

from core_domain.fmea.filename_policy import validate_filename
from core_domain.fmea.template_migration import ProposedFieldMapping


class TemplateImportError(ValueError):
    """Stable, public-safe Office import failure."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class OfficePackageLimits:
    max_source_bytes: int = 8_000_000
    max_members: int = 256
    max_uncompressed_member_bytes: int = 4_000_000
    max_total_uncompressed_bytes: int = 16_000_000
    max_compression_ratio: float = 200.0
    max_sheets: int = 32
    max_rows: int = 10_000
    max_columns: int = 256
    max_cells: int = 100_000
    max_paragraphs: int = 10_000
    max_tables: int = 256
    max_relationships: int = 512
    max_text_length: int = 4_096
    max_structure_items: int = 4_096

    def __post_init__(self) -> None:
        for name in (
            "max_source_bytes",
            "max_members",
            "max_uncompressed_member_bytes",
            "max_total_uncompressed_bytes",
            "max_sheets",
            "max_rows",
            "max_columns",
            "max_cells",
            "max_paragraphs",
            "max_tables",
            "max_relationships",
            "max_text_length",
            "max_structure_items",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if (
            isinstance(self.max_compression_ratio, bool)
            or not isinstance(self.max_compression_ratio, int | float)
            or not math.isfinite(self.max_compression_ratio)
            or self.max_compression_ratio <= 1
        ):
            raise ValueError("max_compression_ratio must be greater than one")


@dataclass(frozen=True, slots=True)
class InspectedOfficePackage:
    members: Mapping[str, bytes]
    relationship_count: int


_REL_NAMESPACE = "http://schemas.openxmlformats.org/package/2006/relationships"
_CONTENT_TYPE_NAMESPACE = "http://schemas.openxmlformats.org/package/2006/content-types"
_RELATIONSHIP_CONTENT_TYPE = "application/vnd.openxmlformats-package.relationships+xml"
_WORD_FIELDS = frozenset({"fldsimple", "fldchar", "instrtext"})
_WORD_EXECUTABLE = frozenset({"altchunk", "oleobject", "object", "embeddedpackage", "embeddedobject"})
_REL_PREFIXES = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/",
    "http://purl.oclc.org/ooxml/officeDocument/relationships/",
    "http://schemas.openxmlformats.org/package/2006/relationships/metadata/",
)
_SAFE_RELATIONSHIP_SUFFIXES = {
    "xlsx": frozenset({
        "officeDocument",
        "worksheet",
        "sharedStrings",
        "styles",
        "theme",
        "table",
        "comments",
        "drawing",
        "image",
        "calcChain",
        "core-properties",
        "extended-properties",
        "custom-properties",
    }),
    "docx": frozenset({
        "officeDocument",
        "styles",
        "stylesWithEffects",
        "settings",
        "webSettings",
        "fontTable",
        "numbering",
        "theme",
        "header",
        "footer",
        "footnotes",
        "endnotes",
        "comments",
        "image",
        "core-properties",
        "extended-properties",
        "custom-properties",
    }),
}
_EXECUTABLE_PART_MARKERS = (
    "/activex/",
    "/embeddings/",
    "/oleobjects/",
    "/controls/",
    "/customui/",
    "vbaproject.bin",
)


def _error(code: str, message: str) -> TemplateImportError:
    return TemplateImportError(code, message)


def _text(value: object, field: str, *, limit: int = 256) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _error("FMEA_TEMPLATE_IMPORT_INVALID", f"{field} is invalid")
    normalized = value.strip()
    if len(normalized) > limit:
        raise _error("FMEA_TEMPLATE_LIMIT_EXCEEDED", f"{field} exceeds the configured limit")
    return normalized


def _parse_xml(raw: bytes, *, label: str):
    try:
        return safe_xml_fromstring(raw, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    except DefusedXmlException as exc:
        raise _error("FMEA_TEMPLATE_EXECUTABLE_CONTENT", f"{label} contains unsupported XML declarations") from exc
    except ParseError as exc:
        raise _error("FMEA_TEMPLATE_CONTAINER_INVALID", f"{label} is malformed") from exc


def _unsafe_member_name(name: str) -> bool:
    path = PurePosixPath(name)
    return (
        not name
        or "\\" in name
        or name.startswith("/")
        or any(part in {"", ".", ".."} for part in path.parts)
        or "\x00" in name
    )


def _relationship_source(relationship_part: str) -> str:
    if relationship_part == "_rels/.rels":
        return ""
    marker = "/_rels/"
    if marker not in relationship_part or not relationship_part.endswith(".rels"):
        raise _error("FMEA_TEMPLATE_CONTAINER_INVALID", "Office relationship part path is invalid")
    prefix, filename = relationship_part.rsplit(marker, 1)
    source_filename = filename[:-5]
    if not source_filename:
        raise _error("FMEA_TEMPLATE_CONTAINER_INVALID", "Office relationship part path is invalid")
    return f"{prefix}/{source_filename}"


def _resolve_part_target(source_part: str, target: str) -> str:
    if not isinstance(target, str) or not target or "\\" in target or "\x00" in target:
        raise _error("FMEA_TEMPLATE_PATH_INVALID", "Office relationship target path is invalid")
    decoded = unquote(target)
    parsed = urlsplit(decoded)
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
        raise _error("FMEA_TEMPLATE_PATH_INVALID", "Office relationship target path is invalid")
    if decoded.startswith("/"):
        candidate = decoded.lstrip("/")
    else:
        candidate = posixpath.join(posixpath.dirname(source_part), decoded)
    resolved = posixpath.normpath(candidate)
    if resolved in {"", ".", ".."} or resolved.startswith("../") or _unsafe_member_name(resolved):
        raise _error("FMEA_TEMPLATE_PATH_INVALID", "Office relationship target path is invalid")
    return resolved


def _relationship_suffix(value: str) -> str:
    return value.rsplit("/", 1)[-1]


def _validate_relationships(  # noqa: C901 - each OPC relationship invariant fails independently
    members: Mapping[str, bytes],
    content_types: Mapping[str, str],
    *,
    kind: str,
    limits: OfficePackageLimits,
) -> int:
    allowed = _SAFE_RELATIONSHIP_SUFFIXES[kind]
    total = 0
    for name, payload in members.items():
        if content_types.get(name) != _RELATIONSHIP_CONTENT_TYPE:
            continue
        if not name.casefold().endswith(".rels"):
            raise _error("FMEA_TEMPLATE_CONTAINER_INVALID", "Office relationship part path is invalid")
        source_part = _relationship_source(name)
        root = _parse_xml(payload, label="relationship part")
        if root.tag != f"{{{_REL_NAMESPACE}}}Relationships":
            raise _error("FMEA_TEMPLATE_CONTAINER_INVALID", "Office relationship root is invalid")
        identifiers: set[str] = set()
        for relationship in root:
            if relationship.tag != f"{{{_REL_NAMESPACE}}}Relationship":
                raise _error("FMEA_TEMPLATE_CONTAINER_INVALID", "Office relationship entry is invalid")
            total += 1
            if total > limits.max_relationships:
                raise _error("FMEA_TEMPLATE_LIMIT_EXCEEDED", "Office package has too many relationships")
            relationship_id = relationship.attrib.get("Id", "")
            relationship_type = relationship.attrib.get("Type", "")
            target = relationship.attrib.get("Target", "")
            if not relationship_id or relationship_id in identifiers:
                raise _error("FMEA_TEMPLATE_CONTAINER_INVALID", "Office relationship IDs are invalid")
            identifiers.add(relationship_id)
            if not any(relationship_type.startswith(prefix) for prefix in _REL_PREFIXES):
                raise _error("FMEA_TEMPLATE_RELATIONSHIP_UNSUPPORTED", "Office relationship type is unsupported")
            if relationship.attrib.get("TargetMode", "").casefold() == "external":
                raise _error("FMEA_TEMPLATE_EXTERNAL_CONTENT", "external Office relationships are unsupported")
            if _relationship_suffix(relationship_type) not in allowed:
                raise _error("FMEA_TEMPLATE_RELATIONSHIP_UNSUPPORTED", "Office relationship type is unsupported")
            resolved = _resolve_part_target(source_part, target)
            if resolved not in members:
                raise _error("FMEA_TEMPLATE_CONTAINER_INVALID", "Office relationship target is missing")
            target_content_type = content_types.get(resolved, "")
            suffix = _relationship_suffix(relationship_type)
            target_is_xml = target_content_type == "application/xml" or target_content_type.endswith("+xml")
            if (suffix == "image" and not target_content_type.startswith("image/")) or (
                suffix != "image" and not target_is_xml
            ):
                raise _error(
                    "FMEA_TEMPLATE_CONTENT_TYPE_UNSUPPORTED",
                    "Office relationship target content type is unsupported",
                )
    return total


def _validate_content_types(  # noqa: C901 - content-type binding stays explicit and auditable
    members: Mapping[str, bytes], *, kind: str
) -> Mapping[str, str]:
    raw = members.get("[Content_Types].xml")
    if raw is None:
        raise _error("FMEA_TEMPLATE_CONTAINER_INVALID", "Office content types are missing")
    root = _parse_xml(raw, label="content types")
    if root.tag != f"{{{_CONTENT_TYPE_NAMESPACE}}}Types":
        raise _error("FMEA_TEMPLATE_CONTAINER_INVALID", "Office content types root is invalid")
    defaults: dict[str, str] = {}
    overrides: dict[str, str] = {}
    for element in root:
        local_name = element.tag.rsplit("}", 1)[-1]
        if local_name == "Default":
            extension = element.attrib.get("Extension", "").casefold()
            content_type = element.attrib.get("ContentType", "").casefold()
            if not extension or not content_type or extension in defaults:
                raise _error("FMEA_TEMPLATE_CONTAINER_INVALID", "Office default content type is invalid")
            defaults[extension] = content_type
        elif local_name == "Override":
            part_name = element.attrib.get("PartName", "")
            content_type = element.attrib.get("ContentType", "").casefold()
            if not part_name.startswith("/") or not content_type:
                raise _error("FMEA_TEMPLATE_CONTAINER_INVALID", "Office override content type is invalid")
            normalized = part_name[1:]
            if normalized in overrides or normalized not in members:
                raise _error("FMEA_TEMPLATE_CONTAINER_INVALID", "Office override content type is invalid")
            overrides[normalized] = content_type
        else:
            raise _error("FMEA_TEMPLATE_CONTAINER_INVALID", "Office content type entry is invalid")
    required_part, required_type = {
        "xlsx": (
            "xl/workbook.xml",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml",
        ),
        "docx": (
            "word/document.xml",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml",
        ),
    }[kind]
    if overrides.get(required_part) != required_type:
        raise _error("FMEA_TEMPLATE_CONTENT_TYPE_UNSUPPORTED", "Office content types are unsupported")
    effective: dict[str, str] = {}
    for name in members:
        if name == "[Content_Types].xml":
            continue
        extension = name.rsplit(".", 1)[-1].casefold() if "." in name else ""
        if name not in overrides and extension not in defaults:
            raise _error("FMEA_TEMPLATE_CONTENT_TYPE_UNSUPPORTED", "Office package member has no content type")
        effective[name] = overrides.get(name, defaults.get(extension, ""))
        if name.casefold().endswith(".rels") != (effective[name] == _RELATIONSHIP_CONTENT_TYPE):
            raise _error("FMEA_TEMPLATE_CONTENT_TYPE_UNSUPPORTED", "Office relationship content type is invalid")
    return MappingProxyType(effective)


def _scan_xml_parts(members: Mapping[str, bytes], content_types: Mapping[str, str], *, kind: str) -> None:
    for name, payload in members.items():
        content_type = content_types.get(name, "")
        lower_name = name.casefold()
        declared_xml = content_type == "application/xml" or content_type.endswith("+xml")
        if not declared_xml and not lower_name.endswith((".xml", ".rels")):
            continue
        root = _parse_xml(payload, label=name)
        local_names = {element.tag.rsplit("}", 1)[-1].casefold() for element in root.iter()}
        if kind == "xlsx" and lower_name.startswith("xl/") and local_names & {"f", "definedname"}:
            raise _error("FMEA_TEMPLATE_FORMULA_UNSUPPORTED", "formula or defined-name content is unsupported")
        if kind == "docx" and lower_name.startswith("word/"):
            if local_names & _WORD_FIELDS:
                raise _error("FMEA_TEMPLATE_FIELD_UNSUPPORTED", "Word fields are unsupported")
            if local_names & _WORD_EXECUTABLE:
                raise _error("FMEA_TEMPLATE_EXECUTABLE_CONTENT", "Word executable content is unsupported")


def inspect_office_zip(  # noqa: C901
    raw_bytes: bytes,
    filename: str,
    *,
    kind: str,
    limits: OfficePackageLimits | None = None,
) -> InspectedOfficePackage:
    """Read and validate a complete bounded package before an Office parser sees it."""

    if kind not in {"xlsx", "docx"}:
        raise _error("FMEA_TEMPLATE_IMPORT_INVALID", "Office source type is unsupported")
    active_limits = limits or OfficePackageLimits()
    if type(raw_bytes) is not bytes:
        raise _error("FMEA_TEMPLATE_IMPORT_INVALID", "source bytes are invalid")
    if len(raw_bytes) > active_limits.max_source_bytes:
        raise _error("FMEA_TEMPLATE_LIMIT_EXCEEDED", "source bytes exceed the configured limit")
    try:
        validate_filename(filename, "source_filename", expected_extension=kind)
    except ValueError as exc:
        raise _error("FMEA_TEMPLATE_IMPORT_INVALID", "source filename is invalid") from exc
    try:
        archive = ZipFile(io.BytesIO(raw_bytes), "r")
    except (BadZipFile, OSError, ValueError) as exc:
        raise _error("FMEA_TEMPLATE_CONTAINER_INVALID", "Office container is malformed") from exc
    with archive:
        infos = archive.infolist()
        if len(infos) > active_limits.max_members:
            raise _error("FMEA_TEMPLATE_LIMIT_EXCEEDED", "Office container has too many members")
        members: dict[str, bytes] = {}
        casefold_names: set[str] = set()
        total = 0
        for info in infos:
            name = info.filename
            folded = name.casefold()
            if _unsafe_member_name(name):
                raise _error("FMEA_TEMPLATE_PATH_INVALID", "Office container member path is invalid")
            if name in members or folded in casefold_names:
                raise _error(
                    "FMEA_TEMPLATE_DUPLICATE_MEMBER", "Office container has duplicate or case-colliding members"
                )
            casefold_names.add(folded)
            if info.flag_bits & 0x1:
                raise _error("FMEA_TEMPLATE_CONTAINER_INVALID", "encrypted Office members are unsupported")
            if info.file_size > active_limits.max_uncompressed_member_bytes:
                raise _error("FMEA_TEMPLATE_LIMIT_EXCEEDED", "Office member exceeds the configured limit")
            if info.compress_size and info.file_size > 65_536:
                ratio = info.file_size / info.compress_size
                if ratio > active_limits.max_compression_ratio:
                    raise _error("FMEA_TEMPLATE_LIMIT_EXCEEDED", "Office member compression ratio is unsafe")
            total += info.file_size
            if total > active_limits.max_total_uncompressed_bytes:
                raise _error("FMEA_TEMPLATE_LIMIT_EXCEEDED", "Office container exceeds the configured limit")
            try:
                payload = archive.read(info)
            except (BadZipFile, OSError, RuntimeError, ValueError) as exc:
                raise _error("FMEA_TEMPLATE_CONTAINER_INVALID", "Office member cannot be read") from exc
            if len(payload) != info.file_size:
                raise _error("FMEA_TEMPLATE_CONTAINER_INVALID", "Office member size changed during read")
            members[name] = payload

    lower_names = tuple(name.casefold() for name in members)
    if any(any(marker in f"/{name}" for marker in _EXECUTABLE_PART_MARKERS) for name in lower_names):
        raise _error("FMEA_TEMPLATE_EXECUTABLE_CONTENT", "executable or plugin Office content is unsupported")
    if kind == "xlsx" and any(name.startswith("xl/externallinks/") for name in lower_names):
        raise _error("FMEA_TEMPLATE_EXTERNAL_CONTENT", "external workbook links are unsupported")
    content_types = _validate_content_types(members, kind=kind)
    _scan_xml_parts(members, content_types, kind=kind)
    relationship_count = _validate_relationships(
        members,
        content_types,
        kind=kind,
        limits=active_limits,
    )
    return InspectedOfficePackage(MappingProxyType(members), relationship_count)


_FIELD_ALIASES: dict[str, frozenset[str]] = {
    "item": frozenset({"item", "item id", "item no", "编号", "项目"}),
    "function": frozenset({"function", "功能"}),
    "failure_mode": frozenset({"failure mode", "failure modes", "失效模式"}),
    "causes": frozenset({"cause", "causes", "失效原因", "原因"}),
    "mechanisms": frozenset({"cause", "mechanism", "mechanisms", "cause mechanism", "机理"}),
    "effects": frozenset({"effect", "effects", "失效影响", "影响"}),
    "symptoms": frozenset({"symptom", "symptoms", "现象"}),
    "controls": frozenset({"control", "controls", "现有控制"}),
    "barriers": frozenset({"barrier", "barriers", "屏障"}),
    "recommended_actions": frozenset({"recommended action", "recommended actions", "建议措施"}),
}


def _normalized_label(label: str) -> str:
    return " ".join(label.casefold().split())


def _field_matches(label: str) -> tuple[str, ...]:
    normalized = _normalized_label(label)
    return tuple(field for field, aliases in _FIELD_ALIASES.items() if normalized in aliases)


def classify_source_fields(
    headers: Sequence[tuple[str, str]],
) -> tuple[tuple[ProposedFieldMapping, ...], tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    """Classify headers without silently collapsing normalized source/target collisions."""

    records: list[tuple[str, str, tuple[str, ...], str]] = []
    source_counts: dict[str, int] = {}
    target_counts: dict[str, int] = {}
    identified: list[str] = []
    for label, locator in headers:
        normalized = _normalized_label(label)
        matches = _field_matches(label)
        records.append((label, locator, matches, normalized))
        source_counts[normalized] = source_counts.get(normalized, 0) + 1
        for field in matches:
            target_counts[field] = target_counts.get(field, 0) + 1
            if field not in identified:
                identified.append(field)
    proposed: list[ProposedFieldMapping] = []
    unknown: list[str] = []
    ambiguous: list[str] = []
    for label, locator, matches, normalized in records:
        if not matches:
            unknown.append(label)
        elif len(matches) != 1 or source_counts[normalized] > 1 or target_counts[matches[0]] > 1:
            ambiguous.append(label)
        else:
            proposed.append(ProposedFieldMapping(source_key=label, target_field=matches[0], source_locator=locator))
    return tuple(proposed), tuple(unknown), tuple(ambiguous), tuple(identified)


__all__ = [
    "InspectedOfficePackage",
    "OfficePackageLimits",
    "TemplateImportError",
    "_error",
    "_parse_xml",
    "_resolve_part_target",
    "_text",
    "classify_source_fields",
    "inspect_office_zip",
]
