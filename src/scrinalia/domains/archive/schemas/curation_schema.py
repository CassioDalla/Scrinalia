from datetime import datetime

from pydantic import BaseModel, Field


class CurationQueue(BaseModel):
    """
    One pending queue of the curator's work list, with the screen that resolves it.

    Every field exists so the home screen can be *a router* and nothing else: ``key`` is the stable
    identity (safe to i18n later), ``label`` is what a person reads, ``count`` is what needs a
    decision and ``route`` is where that decision is taken. A queue with ``count == 0`` is still
    returned — the archivist has to know the queue exists and is empty, which is a different
    statement from the queue being absent from the contract.
    """

    key: str = Field(description="Stable identifier of the queue, e.g. 'tag_merge_proposals'.")
    label: str = Field(description="Text the archivist reads on the card.")
    count: int = Field(ge=0, description="How many items are waiting; zero is a valid answer.")
    route: str = Field(description="Screen that resolves the queue, already filtered.")
    description: str = Field(description="One line explaining what the queue is, for an empty card.")


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
