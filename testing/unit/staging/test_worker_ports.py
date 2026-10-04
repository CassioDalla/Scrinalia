from collections.abc import Sequence
from unittest.mock import MagicMock

from memoria_curitibana.domains.staging.schemas import RawRecord, StagingDocumentDTO
from memoria_curitibana.domains.staging.worker import run_staging_pipeline


class InMemoryRawSource:
    """Fake input port: yields raw records from a plain list (no database)."""

    def __init__(self, records: Sequence[RawRecord]):
        self._records = list(records)

    def next_batch(self, force: bool = False) -> Sequence[RawRecord]:
        return self._records


class RecordingWriter:
    """Fake output port: records what the use case tried to persist."""

    def __init__(self):
        self.saved: list[StagingDocumentDTO] = []

    def save(self, record: StagingDocumentDTO) -> None:
        self.saved.append(record)


def test_run_staging_pipeline_uses_ports_without_database() -> None:
    """The use case must depend only on its ports, never on the ingestion ORM."""
    raw_records = [
        RawRecord(
            description_id="doc-1",
            content_hash="hash-1",
            payload={"title": "Ofício do Prefeito", "Data de Produção": "05/07/1929"},
        ),
        RawRecord(description_id="doc-2", content_hash="hash-2", payload={"title": "Planta do Mercado"}),
    ]

    source = InMemoryRawSource(raw_records)
    writer = RecordingWriter()

    # A plain MagicMock stands in for the ORM session: the ports never touch it here.
    db_session = MagicMock()

    run_staging_pipeline(db_session, source=source, writer=writer)

    assert [record.description_id for record in writer.saved] == ["doc-1", "doc-2"]
    assert writer.saved[0].title == "Ofício do Prefeito"
    # Each record is persisted inside a savepoint; the final commit goes through the UoW.
    assert db_session.begin_nested.call_count == 2


def test_run_staging_pipeline_commits_through_unit_of_work() -> None:
    """The worker must own the transaction via the UnitOfWork, not call commit on the session."""
    raw_records = [RawRecord(description_id="doc-1", content_hash="h", payload={"title": "Ok"})]
    db_session = MagicMock()
    uow = MagicMock()

    run_staging_pipeline(db_session, source=InMemoryRawSource(raw_records), writer=RecordingWriter(), uow=uow)

    uow.commit.assert_called_once()
    uow.rollback.assert_not_called()


def test_run_staging_pipeline_skips_invalid_records() -> None:
    """A record rejected by validation must not reach the writer and should not abort the batch."""
    raw_records = [
        # The first record carries a non-string content_hash; the schema must reject it.
        RawRecord.model_construct(description_id="bad", content_hash=123, payload={"title": None, "Data": "?"}),
        RawRecord(description_id="good", content_hash="h2", payload={"title": "Registro Válido"}),
    ]

    writer = RecordingWriter()
    db_session = MagicMock()

    run_staging_pipeline(db_session, source=InMemoryRawSource(raw_records), writer=writer)

    saved_ids = [record.description_id for record in writer.saved]
    assert "good" in saved_ids
