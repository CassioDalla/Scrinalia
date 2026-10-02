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


# Canonical stamps. Keeping them as module constants prevents the "worker_ner_v1"
# string from being duplicated (and drifting) across queries and workers.
NER = WorkerStamp("worker_ner_v1")
TYPOLOGY = WorkerStamp("worker_typology_classifier_v1")
THUMBNAIL = WorkerStamp("thumbnail")
THUMBNAIL_FAILED = WorkerStamp("thumbnail_failed", status="True")


def cleaning_rule_stamp(rule_id: int) -> WorkerStamp:
    """Builds the per-rule stamp used by the dynamic cleaning rules."""
    return WorkerStamp(f"cleaning_rule_{rule_id}")
