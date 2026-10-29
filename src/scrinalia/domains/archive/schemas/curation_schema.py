import enum
from datetime import datetime

from pydantic import BaseModel, Field


class QueueKey(enum.StrEnum):
    """
    The stable identity of a queue on the home screen.

    The contract carries the key, not the card's copy or its destination: the SPA resolves the
    label, the one-line description and the screen from it (ADR 0020 §5, ADR 0021), so the copy
    pass and its gate can see the first screen. The values are the identity of an outcome, so they
    never change once released.
    """

    HIERARCHY_ORPHANS = "hierarchy_orphans"
    HIERARCHY_PLANS = "hierarchy_plans"
    TAG_MERGE_PROPOSALS = "tag_merge_proposals"
    CROSS_DOMAIN_CONFLICTS = "cross_domain_conflicts"
    SUBJECT_LOW_CONFIDENCE = "subject_low_confidence"
    ORPHAN_SUBJECT_TAGS = "orphan_subject_tags"
    TYPOLOGY_LOW_CONFIDENCE = "typology_low_confidence"
    ANOMALIES = "anomalies"
    UNREVIEWED_DOCUMENTS = "unreviewed_documents"


class CurationQueue(BaseModel):
    """
    One pending queue of the curator's work list.

    Every field exists so the home screen can be *a router* and nothing else: ``key`` is the stable
    identity the SPA resolves its copy and its destination from (ADR 0020 §5, ADR 0021), and
    ``count`` is what needs a decision. A queue with ``count == 0`` is still returned — the
    archivist has to know the queue exists and is empty, which is a different statement from the
    queue being absent from the contract.

    The label, the one-line description and the path of the screen that resolves the queue are
    **not** here: the first two are vocabulary, and the third is not text at all. Both live in the
    SPA catalogue, keyed by ``key``, so the copy pass and its gate can review the first screen and a
    screen rename never reaches the contract.
    """

    key: QueueKey
    count: int = Field(ge=0, description="How many items are waiting; zero is a valid answer.")


class CurationInbox(BaseModel):
    """
    The answer to "what needs me today?".

    Read-only and deliberately small. It carries counts, not samples: a sample per queue would add
    a query per card to a screen whose only job is to send the archivist to the right place, and
    the destination screen is where the sample belongs. ``generated_at`` is exposed so the UI can
    say how fresh the numbers are instead of implying they are live.
    """

    queues: list[CurationQueue] = Field(default_factory=list)
    generated_at: datetime
