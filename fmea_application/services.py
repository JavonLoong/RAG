"""Deterministic FMEA application persistence services."""

from __future__ import annotations

from dataclasses import replace

from core_domain.fmea.contracts import (
    ActorType,
    EvidencePack,
    FmeaAnalysis,
    FmeaRow,
    PropagationEdge,
    PublicationStatus,
    ReviewStatus,
)
from core_domain.fmea.errors import FmeaDomainError
from core_domain.fmea.policies import validate_row_evidence
from core_domain.fmea.propagation import validate_propagation_edge

from .ports import FmeaRepository


class FmeaService:
    def __init__(self, repository: FmeaRepository) -> None:
        self._repository = repository

    def create_analysis(
        self,
        analysis: FmeaAnalysis,
        *,
        actor_id: str,
        actor_type: ActorType,
        expected_record_version: int | None = None,
    ) -> FmeaAnalysis:
        return self._repository.save_analysis(
            analysis,
            actor_id=actor_id,
            actor_type=actor_type,
            expected_record_version=expected_record_version,
        )

    def register_evidence_pack(
        self,
        pack: EvidencePack,
        *,
        actor_id: str,
        actor_type: ActorType,
    ) -> EvidencePack:
        return self._repository.save_evidence_pack(pack, actor_id=actor_id, actor_type=actor_type)

    def save_row(
        self,
        row: FmeaRow,
        *,
        actor_id: str,
        actor_type: ActorType,
        expected_record_version: int | None = None,
    ) -> FmeaRow:
        return self._repository.save_row(
            row,
            actor_id=actor_id,
            actor_type=actor_type,
            expected_record_version=expected_record_version,
        )

    def save_propagation_edge(
        self,
        edge: PropagationEdge,
        *,
        actor_id: str,
        actor_type: ActorType,
        expected_record_version: int | None = None,
    ) -> PropagationEdge:
        return self._repository.save_propagation_edge(
            edge,
            actor_id=actor_id,
            actor_type=actor_type,
            expected_record_version=expected_record_version,
        )

    def persist_candidate_bundle(
        self,
        analysis: FmeaAnalysis,
        evidence_pack: EvidencePack,
        rows: tuple[FmeaRow, ...],
        edges: tuple[PropagationEdge, ...],
        actor_id: str,
        actor_type: ActorType,
    ) -> tuple[tuple[FmeaRow, ...], tuple[PropagationEdge, ...]]:
        row_candidates: list[FmeaRow] = []
        for row in tuple(rows):
            if row.analysis_id != analysis.analysis_id:
                raise FmeaDomainError("row analysis_id does not match analysis")  # noqa: TRY003
            validate_row_evidence(row, evidence_pack)
            row_candidates.append(
                replace(
                    row,
                    review_status=ReviewStatus.SUGGESTED,
                    publication_status=PublicationStatus.UNPUBLISHED,
                )
            )

        edge_candidates: list[PropagationEdge] = []
        for edge in tuple(edges):
            if edge.analysis_id != analysis.analysis_id:
                raise FmeaDomainError("edge analysis_id does not match analysis")  # noqa: TRY003
            validate_propagation_edge(edge, evidence_pack)
            edge_candidates.append(
                replace(
                    edge,
                    review_status=(
                        ReviewStatus.SUGGESTED
                        if edge.auto_accept_allowed
                        else ReviewStatus.IN_REVIEW
                    ),
                    publication_status=PublicationStatus.UNPUBLISHED,
                )
            )

        self._repository.save_evidence_pack(
            evidence_pack,
            actor_id=actor_id,
            actor_type=actor_type,
        )
        saved_rows = tuple(
            self._repository.save_row(row, actor_id=actor_id, actor_type=actor_type)
            for row in row_candidates
        )
        saved_edges = tuple(
            self._repository.save_propagation_edge(edge, actor_id=actor_id, actor_type=actor_type)
            for edge in edge_candidates
        )
        return saved_rows, saved_edges
