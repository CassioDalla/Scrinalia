from dataclasses import dataclass
from typing import Literal

StampStatus = Literal["DONE", "ERROR", "True"]


@dataclass(frozen=True)
class WorkerStamp:
    """
    Typed identity of a worker run inside ``ArchiveDocument.execution_log``.

    Workers use this instead of raw string literals so the idempotency key is defined
    once, is rename-safe and can be asserted in tests. It carries both the read side
    (``key``) and the write side (``status``).
    """

    key: str
    status: StampStatus = "DONE"

    def applies_to(self, execution_log: dict[str, str] | None) -> bool:
        """True when the document has NOT been processed by this worker yet."""
        return not execution_log or self.key not in execution_log

    def mark(self, execution_log: dict[str, str] | None, status: StampStatus | None = None) -> dict[str, str]:
        """Returns a new log dict with this worker's key set to the given status."""
        new_log = dict(execution_log) if execution_log else {}
        new_log[self.key] = status or self.status
        return new_log

    def mark_value(self, execution_log: dict[str, str] | None, value: str) -> dict[str, str]:
        """
        Returns a new log dict with this worker's key set to an arbitrary value.

        Used by the content-keyed workers: the stamp is the hash of the text they
        processed, so a later text change makes the document pending again.
        """
        new_log = dict(execution_log) if execution_log else {}
        new_log[self.key] = value
        return new_log


# Canonical stamps. Keeping them as module constants prevents the "worker_ner_v2"
# string from being duplicated (and drifting) across queries and workers.
NER = WorkerStamp("worker_ner_v2")
TYPOLOGY = WorkerStamp("worker_typology_classifier_v2")
# Stamp written on ``ArchiveTag.execution_log`` (tags have their own ledger).
MACRO_CATEGORY = WorkerStamp("worker_macro_category_v1")
# Unlike the others, this one stores the hash of the embedded text instead of a status,
# so a human edit that changes the text puts the document back in the queue.
EMBEDDING = WorkerStamp("worker_embedding_v1")
THUMBNAIL = WorkerStamp("thumbnail")
THUMBNAIL_FAILED = WorkerStamp("thumbnail_failed", status="True")
# Structural anomaly validation (Fase 3.5-C). Status-stamped: its reasons depend on the
# catalog, not only on the document text, so a catalog change re-queues explicitly.
QUALITY_VALIDATOR = WorkerStamp("worker_quality_validator_v1")


def cleaning_rule_stamp(rule_id: int) -> WorkerStamp:
    """Builds the per-rule stamp used by the dynamic cleaning rules."""
    return WorkerStamp(f"cleaning_rule_{rule_id}")


#: Stamps that must be invalidated when the AI text composition changes (an excerpt
#: approved, edited or undone). The embedding is deliberately absent: its stamp *is* a
#: hash of the effective text, so it re-queues by itself and needs no help.
TEXT_DEPENDENT_STAMPS: tuple[WorkerStamp, ...] = (NER, TYPOLOGY, QUALITY_VALIDATOR)
