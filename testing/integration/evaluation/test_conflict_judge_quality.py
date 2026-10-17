"""
Integration tests for the conflict-judge bench's gabarito (issue #114).

The load-bearing rule of this bench is which rows it reads: the human half of the ledger, minus the
decisions a human reversed, and only the snapshots. Those three are the difference between a
measurement and the judge scoring itself, and none of them can be pinned without a database.
"""

from __future__ import annotations

from datetime import UTC, datetime

from scrinalia.domains.archive.models.governance import ArchiveConflictResolutionLog
from testing.evaluation.conflict_judge_quality import HUMAN, JUDGE, ledger_census, read_ledger


def ledger_row(
    resolution_id: int,
    *,
    source: str = HUMAN,
    winner: str = "ENTITY",
    entity_type: str = "LOC",
    undone_at: datetime | None = None,
) -> ArchiveConflictResolutionLog:
    """One resolution, with the snapshots the bench is supposed to read and the ids it is not."""
    return ArchiveConflictResolutionLog(
        resolution_id=resolution_id,
        winner=winner,
        source=source,
        tag_id=1000 + resolution_id,
        tag_name=f"grafia extraída {resolution_id}",
        entity_id=2000 + resolution_id,
        entity_name=f"Grafia Canônica {resolution_id}",
        entity_type=entity_type,
        loser_snapshot={"name": f"grafia extraída {resolution_id}"},
        transferred_document_ids=[],
        created_link_ids=[],
        synonym_names=[],
        ban_kind="STOPWORD",
        ban_term=f"grafia extraída {resolution_id}",
        ban_created=True,
        decided_by="Admin",
        undone_at=undone_at,
    )


def test_read_ledger_keeps_the_human_resolutions_and_drops_the_judges(
    use_test_db,
    db_session,
):
    """
    The gabarito is the human half. Scoring the judge's own auto-resolutions against the judge is
    not a measurement, and a ledger where the judge outnumbers the curator is exactly the case the
    split exists for.
    """
    db_session.add_all(
        [
            ledger_row(1, source=HUMAN),
            ledger_row(2, source=JUDGE, winner="TAG", entity_type="PER"),
            ledger_row(3, source=HUMAN, winner="TAG", entity_type="ORG"),
        ]
    )
    db_session.flush()

    rows = read_ledger(db_session, HUMAN)

    assert [row.resolution_id for row in rows] == [1, 3]
    assert {row.source for row in rows} == {HUMAN}


def test_read_ledger_drops_a_decision_a_human_reversed(use_test_db, db_session):
    """An undone resolution is not truth any more: the institution already withdrew the answer."""
    db_session.add_all(
        [
            ledger_row(1),
            ledger_row(2, undone_at=datetime.now(UTC)),
        ]
    )
    db_session.flush()

    rows = read_ledger(db_session, HUMAN)

    assert [row.resolution_id for row in rows] == [1]


def test_read_ledger_carries_the_snapshots_and_not_a_live_reference(use_test_db, db_session):
    """
    The resolution deletes the losing row, so the pair only survives in the snapshot. The bench has
    to be able to ask the judge about a pair whose rows are gone.
    """
    db_session.add(ledger_row(7, winner="ENTITY", entity_type="LOC"))
    db_session.flush()

    row = read_ledger(db_session, HUMAN)[0]

    assert (row.tag_name, row.entity_name, row.entity_type) == ("grafia extraída 7", "Grafia Canônica 7", "LOC")
    assert row.winner == "ENTITY"


def test_the_census_shows_the_split_and_the_undone_rows(use_test_db, db_session):
    """The composition of the ledger is what tells the reader whether the score means anything."""
    db_session.add_all(
        [
            ledger_row(1, source=HUMAN),
            ledger_row(2, source=HUMAN),
            ledger_row(3, source=JUDGE, winner="TAG"),
            ledger_row(4, source=HUMAN, undone_at=datetime.now(UTC)),
        ]
    )
    db_session.flush()

    census = ledger_census(db_session)

    assert census["human"] == 3
    assert census["judge"] == 1
    assert census["undone"] == 1
    assert census["total"] == 4
