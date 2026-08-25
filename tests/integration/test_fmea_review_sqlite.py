from __future__ import annotations

from core_domain.fmea.states import PublicationStatus, ReviewStatus
from fmea_application.review_contracts import ReviewCandidateBundle
from fmea_infrastructure.repository_sqlite import SqliteFmeaRepository


def test_repository_migrates_and_round_trips_review_candidate_bundle(
    tmp_path, fixture_analysis, fixture_pack, fixture_review_row, fixture_review_source, fixture_system_actor
) -> None:
    repository = SqliteFmeaRepository(tmp_path / "fmea.sqlite3")
    repository.initialize()
    rows = repository.save_review_candidate_bundle(
        ReviewCandidateBundle(
            fixture_analysis, fixture_pack, (fixture_review_row,), (fixture_review_source,)
        ),
        fixture_system_actor,
    )

    assert rows[0].review_status is ReviewStatus.SUGGESTED
    assert rows[0].publication_status is PublicationStatus.UNPUBLISHED
    assert repository.get_row("row-1", "ws-1") == rows[0]
    assert repository.get_evidence_pack("pack-1", "ws-1") == fixture_pack
    assert repository.get_review_source("row-1", "ws-1") == fixture_review_source
    assert repository.get_row("row-1", "other-workspace") is None
    assert repository.get_evidence_pack("pack-1", "other-workspace") is None
    assert repository.get_review_source("row-1", "other-workspace") is None
    assert repository.list_suggestions("row-1", "ws-1") == ()
    assert repository.list_decisions("row-1", "ws-1") == ()
