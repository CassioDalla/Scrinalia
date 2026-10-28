import enum
from datetime import datetime

from pydantic import BaseModel, Field


class QueueKey(enum.StrEnum):
    """
    The stable identity of a queue on the home screen.

    The contract carries the key, not the card's copy: the SPA resolves the label and the one-line
    description from it (ADR 0020 §5), so the copy pass and its gate can see the first screen. The
    values are the identity of an outcome, so they never change once released.
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
    One pending queue of the curator's work list, with the screen that resolves it.

    Every field exists so the home screen can be *a router* and nothing else: ``key`` is the stable
    identity the SPA resolves its copy from (ADR 0020 §5), ``count`` is what needs a decision and
    ``route`` is where that decision is taken. A queue with ``count == 0`` is still returned — the
    archivist has to know the queue exists and is empty, which is a different statement from the
    queue being absent from the contract.

    The label and the one-line description are **not** here: they are vocabulary, keyed by ``key``
    in the SPA catalogue, so the copy pass and its gate can review the first screen.
    """

    key: QueueKey
    count: int = Field(ge=0, description="How many items are waiting; zero is a valid answer.")
    route: str = Field(description="Screen that resolves the queue, already filtered.")


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
