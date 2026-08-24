"""Adapt one query response into an immutable FMEA evidence snapshot."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from hashlib import sha256
from typing import Any, Protocol

from core_domain.fmea.contracts import ActorType, EvidencePack, EvidenceRef
from core_domain.fmea.errors import FmeaDomainError
from core_domain.query_contracts import (
    Citation,
    CitationType,
    QueryMode,
    QueryRequest,
    QueryResponse,
    selected_citation_types,
)
from fmea_application.ports import EvidenceRequest, EvidenceSnapshot, FmeaRepository


class QueryPort(Protocol):
    """Structural query boundary used by the FMEA evidence adapter."""

    def query(self, request: QueryRequest) -> QueryResponse: ...


_SOURCE_ORDER = (CitationType.TEXT, CitationType.GRAPH, CitationType.COMMUNITY)
_SOURCE_NAMES = {
    CitationType.TEXT: "rag_text",
    CitationType.GRAPH: "graphrag_relation",
    CitationType.COMMUNITY: "graphrag_community",
}


class QueryServiceEvidenceProvider:
    """Turn query citations into provenance-limited FMEA evidence refs."""

    def __init__(
        self,
        query_service: QueryPort,
        repository: FmeaRepository,
        *,
        clock: Callable[[], str],
        pack_id_factory: Callable[[], str],
    ) -> None:
        self._query_service = query_service
        self._repository = repository
        self._clock = clock
        self._pack_id_factory = pack_id_factory

    def create_snapshot(self, request: EvidenceRequest) -> EvidenceSnapshot:
        query_request = QueryRequest(
            query=request.query,
            workspace_id=request.workspace_id,
            mode=QueryMode.AUTO,
            top_k=request.max_hits,
            include_context=True,
            evidence_only=True,
            evidence_profile=request.evidence_profile,
            evidence_types=request.evidence_types,
        )
        response = self._query_service.query(query_request)
        warnings = [f"{warning.code}: {warning.message}" for warning in response.warnings]
        source_counts = tuple(
            (source_type, sum(citation.type is source_type for citation in response.citations))
            for source_type in _SOURCE_ORDER
        )
        created_at = self._clock()
        refs, identity_warnings = self._build_refs(request, response.citations, created_at)
        warnings.extend(identity_warnings)

        expected_types = selected_citation_types(query_request)
        if expected_types is None:
            incomplete = bool(warnings) or not response.citations
        else:
            counts = dict(source_counts)
            incomplete = bool(warnings) or any(counts[source_type] == 0 for source_type in expected_types)

        pack = EvidencePack.build(
            pack_id=self._pack_id_factory(),
            workspace_id=request.workspace_id,
            acl_scope=request.acl_scope,
            versions=request.versions,
            refs=tuple(refs),
            created_at=created_at,
            expires_at=None,
        )
        saved_pack = self._repository.save_evidence_pack(
            pack,
            actor_id="evidence-provider",
            actor_type=ActorType.SYSTEM,
        )
        return EvidenceSnapshot(
            pack=saved_pack,
            profile=request.evidence_profile,
            source_counts=source_counts,
            warnings=tuple(warnings),
            incomplete=incomplete,
        )

    def read_refs(self, pack: EvidencePack, evidence_ids: tuple[str, ...]) -> tuple[EvidenceRef, ...]:
        refs: list[EvidenceRef] = []
        for evidence_id in evidence_ids:
            ref = pack.ref_by_id(evidence_id)
            if ref is None:
                raise FmeaDomainError(f"evidence ID {evidence_id} is absent from EvidencePack")  # noqa: TRY003
            refs.append(ref)
        return tuple(refs)

    def load_pack(self, workspace_id: str, pack_id: str) -> EvidencePack:
        pack = self._repository.get_evidence_pack(pack_id)
        if pack is None:
            raise FmeaDomainError(f"EvidencePack {pack_id} was not found")  # noqa: TRY003
        if pack.workspace_id != workspace_id:
            raise FmeaDomainError("EvidencePack workspace_id does not match requested workspace")  # noqa: TRY003
        return pack

    def _build_refs(
        self,
        request: EvidenceRequest,
        citations: list[Citation],
        created_at: str,
    ) -> tuple[tuple[EvidenceRef, ...], tuple[str, ...]]:
        refs: list[EvidenceRef] = []
        warnings: list[str] = []
        identity_variants: dict[tuple[Any, ...], set[tuple[str, str]]] = {}
        refs_by_hash: dict[str, int] = {}
        metadata_conflicts: set[str] = set()
        conflict_reported = False

        for source_type in _SOURCE_ORDER:
            for citation in citations:
                if citation.type is not source_type:
                    continue
                material = _citation_material(request, citation)
                if material is None:
                    warnings.append(
                        f"INVALID_EVIDENCE_CITATION: citation {citation.id!r} has empty or invalid material."
                    )
                    continue
                document_id, document_version, locator, normalized_quote, quote, source_trust, is_primary = material
                variant = (locator, normalized_quote)
                identity_json = _canonical_json(
                    {
                        "source_type": _SOURCE_NAMES[source_type],
                        "document_id": document_id,
                        "document_version": document_version,
                        "locator": locator,
                        "normalized_quote": normalized_quote,
                    }
                )
                evidence_hash = sha256(identity_json.encode("utf-8")).hexdigest()
                existing_index = refs_by_hash.get(evidence_hash)
                if existing_index is not None:
                    existing_ref = refs[existing_index]
                    trust_conflict = existing_ref.source_trust != source_trust
                    primary_conflict = existing_ref.is_primary != is_primary
                    if trust_conflict or primary_conflict:
                        refs[existing_index] = replace(
                            existing_ref,
                            source_trust="conflict" if trust_conflict else existing_ref.source_trust,
                            is_primary=False if primary_conflict else existing_ref.is_primary,
                        )
                        if evidence_hash not in metadata_conflicts:
                            warnings.append(
                                "EVIDENCE_METADATA_CONFLICT: identical evidence identity has conflicting "
                                "allowlisted metadata."
                            )
                            metadata_conflicts.add(evidence_hash)
                    continue

                conflict_key = (citation.type.value, citation.id, document_id, document_version)
                variants = identity_variants.setdefault(conflict_key, set())
                if variants and variant not in variants and not conflict_reported:
                    warnings.append(
                        "EVIDENCE_IDENTITY_CONFLICT: citation identity has conflicting allowlisted provenance."
                    )
                    conflict_reported = True
                variants.add(variant)

                evidence_id = f"ev-{evidence_hash[:24]}"
                refs.append(
                    EvidenceRef(
                        evidence_id=evidence_id,
                        workspace_id=request.workspace_id,
                        document_id=document_id,
                        document_version=document_version,
                        content_hash=sha256(normalized_quote.encode("utf-8")).hexdigest(),
                        locator=locator,
                        quote=quote,
                        normalized_quote=normalized_quote,
                        evidence_hash=evidence_hash,
                        acl_scope=request.acl_scope,
                        source_type=_SOURCE_NAMES[source_type],
                        source_trust=source_trust,
                        is_primary=is_primary,
                        created_at=created_at,
                        expires_at=None,
                    )
                )
                refs_by_hash[evidence_hash] = len(refs) - 1
        return tuple(refs), tuple(warnings)


def _citation_material(
    request: EvidenceRequest,
    citation: Citation,
) -> tuple[str, str, str, str, str, str, bool] | None:
    normalized_quote = " ".join(citation.quote.split())
    if not citation.id.strip() or not normalized_quote:
        return None

    source_type = citation.type
    metadata = citation.metadata
    document_version = _metadata_string(metadata, "document_version")
    source = citation.source
    if source_type is CitationType.TEXT:
        document_id = _source_string(source, "document_id") or f"text:{request.workspace_id}:{citation.id}"
        document_version = document_version or request.versions.data_version
        locator_data = _present_fields(
            {
                "document_id": _source_value(source, "document_id"),
                "file": _source_value(source, "file"),
                "page": _source_value(source, "page"),
                "chunk_id": _source_value(source, "chunk_id"),
            }
        )
    elif source_type is CitationType.GRAPH:
        triple = citation.triple
        if triple is None or not all(value.strip() for value in (triple.subject, triple.predicate, triple.object)):
            return None
        document_id = _source_string(source, "document_id") or f"graph:{request.versions.graph_version}:{citation.id}"
        document_version = document_version or request.versions.graph_version
        locator_data = {
            "subject": triple.subject,
            "predicate": triple.predicate,
            "object": triple.object,
            "edge_id": citation.id,
        }
        source_document_id = _source_string(source, "document_id")
        if source_document_id is not None:
            locator_data["document_id"] = source_document_id
    elif source_type is CitationType.COMMUNITY:
        document_id = f"community:{request.versions.graph_version}:{citation.id}"
        document_version = document_version or request.versions.graph_version
        locator_data = {"community_id": citation.id}
        title = metadata.get("title")
        if isinstance(title, str):
            locator_data["title"] = title
    else:
        return None

    source_trust = _metadata_string(metadata, "source_trust") or "unrated"
    is_primary = metadata.get("is_primary") is True
    return (
        document_id,
        document_version,
        _canonical_json(locator_data),
        normalized_quote,
        citation.quote,
        source_trust,
        is_primary,
    )


def _canonical_json(value: dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _metadata_string(metadata: dict[str, Any], key: str) -> str | None:
    value = metadata.get(key)
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _source_value(source: Any, field_name: str) -> Any:
    return getattr(source, field_name, None) if source is not None else None


def _source_string(source: Any, field_name: str) -> str | None:
    value = _source_value(source, field_name)
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _present_fields(values: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value is not None and value != ""}


__all__ = ["QueryPort", "QueryServiceEvidenceProvider"]
