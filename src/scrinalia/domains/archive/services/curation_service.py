from datetime import UTC, datetime

from scrinalia.domains.archive.repository.curation_repo import CurationRepository
from scrinalia.domains.archive.schemas.curation_schema import CurationInbox, CurationQueue, QueueKey

#: The catalogue of queues. Order matters: it is the order the cards appear on the home screen, and
#: it goes from "the collection cannot be navigated" to "the record has a defect", because that is
#: the order in which the queues unblock each other.
#: ``route`` is a front-end path, carried by the API so the mapping lives in one place instead of
#: being duplicated in the UI. The label and the description are **not** here: they are vocabulary,
#: keyed by the same ``QueueKey`` in the SPA catalogue (ADR 0020 §5), where the copy pass and its
#: gate can review the first screen.
QUEUE_CATALOGUE: tuple[tuple[QueueKey, str], ...] = (
    (QueueKey.HIERARCHY_ORPHANS, "/arranjo/plano"),
    (QueueKey.HIERARCHY_PLANS, "/arranjo/plano"),
    (QueueKey.TAG_MERGE_PROPOSALS, "/assuntos/tags"),
    (QueueKey.CROSS_DOMAIN_CONFLICTS, "/entidades/conflitos"),
    (QueueKey.SUBJECT_LOW_CONFIDENCE, "/assuntos/tags?aba=classificar&subject_state=LOW_CONFIDENCE"),
    (QueueKey.ORPHAN_SUBJECT_TAGS, "/assuntos/tags?aba=classificar&subject_state=PENDING"),
    (QueueKey.TYPOLOGY_LOW_CONFIDENCE, "/arranjo/tipologias"),
    (QueueKey.ANOMALIES, "/qualidade/anomalias"),
    (QueueKey.UNREVIEWED_DOCUMENTS, "/acervo/lista?status=PENDING_AI"),
)


class CurationService:
    """
    The curator's work list.

    A read-only view of the domain: it counts what is pending and says which screen resolves it.
    It owns the order of the queues and the route each one opens; the label and the description live
    in the SPA catalogue, keyed by ``QueueKey`` (ADR 0020 §5). The repository owns the counting, so
    a new queue is a line in the catalogue plus a count in the repository — never a new route, and
    never seven requests from the browser.
    """

    def __init__(self, repo: CurationRepository) -> None:
        self.repo = repo

    def inbox(self) -> CurationInbox:
        counts = self.repo.count_pending()
        return CurationInbox(
            queues=[CurationQueue(key=key, count=counts[key], route=route) for key, route in QUEUE_CATALOGUE],
            generated_at=datetime.now(UTC),
        )
