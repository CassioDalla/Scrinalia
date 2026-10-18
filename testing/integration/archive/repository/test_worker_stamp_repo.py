"""The stamp breakdown: what an identity slot really holds, told apart by its own vocabulary.

Issue #137: one "processed" number stood for a fingerprint, for the legacy ``"DONE"`` and for a
failure alike, and for NER it was the legacy value all along. The panel owes the operator the
difference, and the classifier is the slot's own pattern — the same expression ``mark_value``
validates against — so the read cannot disagree with the write.
"""

import pytest

from scrinalia.domains.archive.models import ArchiveTag
from scrinalia.domains.archive.repository.worker_stamp_repo import StampBreakdown, WorkerStampRepository
from scrinalia.domains.archive.worker_stamp import EMBEDDING, MACRO_CATEGORY, NER, PRODUCER_UNKNOWN
from scrinalia.domains.archive.workers.catalogue import WORKER_CATALOGUE

#: A value the plain fingerprint pattern accepts. The breakdown classifies the *shape*; whether the
#: hash names the producer the next run would use is ``pending``'s question, not this one's.
FINGERPRINT = "ab" * 32


def test_the_breakdown_tells_the_fingerprint_from_the_legacy_value_and_the_failure(
    db_session, generate_archive_doc
) -> None:
    generate_archive_doc(original_title="Com produtor", execution_log={NER.key: FINGERPRINT})
    generate_archive_doc(original_title="Legado", execution_log={NER.key: "DONE"})
    generate_archive_doc(original_title="Desconhecido", execution_log={NER.key: PRODUCER_UNKNOWN})
    generate_archive_doc(original_title="Falhou", execution_log={NER.key: "ERROR"})
    generate_archive_doc(original_title="Sem registro")

    breakdown = WorkerStampRepository(db_session).count_stamp_breakdown(WORKER_CATALOGUE["ner"])

    assert breakdown == StampBreakdown(fingerprinted=1, legacy=2, failed=1, unrecorded=1)
    # ``processed`` is the old number, now derived: the four buckets add up to the model's count, and
    # the fingerprint alone is what used to be hidden inside it.
    assert breakdown.processed == 4
    assert breakdown.fingerprinted + breakdown.legacy + breakdown.failed + breakdown.unrecorded == 5


def test_the_embedding_reports_the_bare_text_hash_as_no_producer(db_session, generate_archive_doc) -> None:
    """The composed value names the model; the bare MD5 name only the text it read."""
    generate_archive_doc(original_title="Com identidade", execution_log={EMBEDDING.key: f"{'a' * 32}:{FINGERPRINT}"})
    generate_archive_doc(original_title="Só o texto", execution_log={EMBEDDING.key: "b" * 32})

    breakdown = WorkerStampRepository(db_session).count_stamp_breakdown(WORKER_CATALOGUE["embedding"])

    assert breakdown.fingerprinted == 1
    assert breakdown.legacy == 1


def test_the_breakdown_reads_the_tag_ledger_too(db_session) -> None:
    """The macro-category's unit is the tag, so its slot lives in ``archive_tags``."""
    db_session.add(ArchiveTag(name="com-produtor", execution_log={MACRO_CATEGORY.key: FINGERPRINT}))
    db_session.add(ArchiveTag(name="legada", execution_log={MACRO_CATEGORY.key: "DONE"}))
    db_session.add(ArchiveTag(name="sem-registro"))
    db_session.flush()

    breakdown = WorkerStampRepository(db_session).count_stamp_breakdown(WORKER_CATALOGUE["macro-category"])

    assert breakdown == StampBreakdown(fingerprinted=1, legacy=1, failed=0, unrecorded=1)


def test_a_worker_whose_ledger_is_not_a_stamp_is_refused(db_session) -> None:
    """``thumbnail`` records its work in the storage URI; asking it for a stamp breakdown is a bug."""
    with pytest.raises(ValueError, match="no stamp"):
        WorkerStampRepository(db_session).count_stamp_breakdown(WORKER_CATALOGUE["thumbnail"])
