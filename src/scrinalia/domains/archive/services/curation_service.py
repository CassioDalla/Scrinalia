from datetime import UTC, datetime

from scrinalia.domains.archive.repository.curation_repo import CurationRepository
from scrinalia.domains.archive.schemas.curation_schema import CurationInbox, CurationQueue, QueueKey

#: The catalogue of queues. Order matters: it is the order the cards appear on the home screen, and
#: it goes from "the collection cannot be navigated" to "the record has a defect", because that is
#: the order in which the queues unblock each other.
#: The catalogue carries the **identity** of each queue, never the screen that resolves it: the
#: label, the description and the destination are SPA vocabulary, keyed by the same ``QueueKey`` in
#: ``apps/curator/src/lib/queues.ts`` (ADR 0020 §5, ADR 0021). A path is not text, so it is owned by
#: the screens catalogue and by the copy gate that pins it to the router.
QUEUE_CATALOGUE: tuple[QueueKey, ...] = (
    QueueKey.HIERARCHY_ORPHANS,
    QueueKey.HIERARCHY_PLANS,
    QueueKey.TAG_MERGE_PROPOSALS,
    QueueKey.CROSS_DOMAIN_CONFLICTS,
    QueueKey.SUBJECT_LOW_CONFIDENCE,
    QueueKey.ORPHAN_SUBJECT_TAGS,
    QueueKey.TYPOLOGY_LOW_CONFIDENCE,
    QueueKey.ANOMALIES,
    QueueKey.UNREVIEWED_DOCUMENTS,
)


class CurationService:
    """
    The curator's work list.

    A read-only view of the domain: it counts what is pending, and the SPA says which screen
    resolves each queue and which filters it opens with. It owns the order of the queues; the
    label, the description and the destination live in the SPA catalogue, keyed by ``QueueKey``
    (ADR 0020 §5, ADR 0021). The repository owns the counting, so a new queue is a line in the
    catalogue plus a count in the repository — never a new route, and never seven requests from the
    browser.
    """

    def __init__(self, repo: CurationRepository) -> None:
        self.repo = repo

    def inbox(self) -> CurationInbox:
        counts = self.repo.count_pending()
        return CurationInbox(
            queues=[CurationQueue(key=key, count=counts[key]) for key in QUEUE_CATALOGUE],
            generated_at=datetime.now(UTC),
        )
