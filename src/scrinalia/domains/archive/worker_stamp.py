from collections.abc import Mapping
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as distribution_version
from typing import Any, Literal

from sqlalchemy import ColumnElement, func, or_

from scrinalia.core.content_hash import ContentHash

StampStatus = Literal["DONE", "ERROR", "True"]

#: Stamp values that mean the unit failed. ``True`` is the thumbnail worker's failure mark
#: (``thumbnail_failed``), which predates the ``ERROR`` convention; both mean "do not retry
#: silently", and the operations panel counts them as one number.
FAILURE_STAMP_VALUES: tuple[str, ...] = ("ERROR", "True")

#: Options that control the **queue** instead of the answer: whether this run ignores a stamp
#: (``force``), how many units it may touch (``limit``) and the runner dataclass the panel
#: refuses (``config``). They stay out of the producer identity on purpose — a forced run writes
#: the identity of the model, not of the force, or the next plain run would re-queue everything
#: again.
STAMP_NEUTRAL_OPTIONS: frozenset[str] = frozenset({"config", "force", "limit"})

#: Installed libraries whose own version changes the answer **without** changing the preset.
#: The embedding stamp exists because a bump of ``torch``/``sentence-transformers`` silently
#: invalidated every vector while the preset stayed identical, so a hash of the preset alone
#: would not have caught the very failure that made this necessary. The versions are read from
#: the distribution metadata, which costs no import.
#:
#: Two producers are deliberately absent and the guide says so: the language model package
#: (``pt_core_news_lg``) spaCy loads for NER, and the model the Ollama server serves, whose
#: digest would take a network call on the panel's path.
AXIS_RUNTIME_DISTRIBUTIONS: dict[str, tuple[str, ...]] = {
    "NER": ("spacy",),
    "classification": ("torch", "transformers"),
    "embeddings": ("torch", "sentence-transformers"),
    "LLMs": (),
    "title_quality": ("torch", "transformers"),
}


def runtime_versions(axis: str | None) -> dict[str, str]:
    """
    Installed versions of the libraries that decide a worker's answer, per axis.

    A distribution that is not installed is reported as ``"absent"`` instead of raising: the
    panel counts a queue, and a screen that returns 500 because a heavy dependency is missing
    would hide the queue it exists to show. The value is deterministic, so the identity stays
    comparable between two processes.
    """
    versions: dict[str, str] = {}
    for package in AXIS_RUNTIME_DISTRIBUTIONS.get(axis or "", ()):
        try:
            versions[package] = distribution_version(package)
        except PackageNotFoundError:
            versions[package] = "absent"
    return versions


def producer_fingerprint(
    *,
    axis: str | None,
    engine_name: str | None,
    preset: str | None,
    engine_config: Mapping[str, Any] | None = None,
    worker_options: Mapping[str, Any] | None = None,
) -> str:
    """
    Stable identity of **what produced** a worker's answer: engine, preset and resolved config.

    ``engine_config`` is the ``describe_config`` output — the read-only twin of ``get_engine`` —
    so the identity names exactly what the engine receives and never a value re-derived from the
    preset. ``worker_options`` are the behavioural options the run resolved (a confidence
    threshold, the columns read); the queue controls in :data:`STAMP_NEUTRAL_OPTIONS` are dropped.

    Changing any of it changes the identity, and an identity-keyed stamp makes the affected units
    pending again by themselves — which is the whole point: a model bump used to leave every
    vector stale while the stamp stayed up to date and the queue stayed empty.
    """
    options = {key: value for key, value in (worker_options or {}).items() if key not in STAMP_NEUTRAL_OPTIONS}
    return str(
        ContentHash.of(
            {
                "axis": axis,
                "engine": engine_name,
                "preset": preset,
                "config": dict(engine_config or {}),
                "runtime": runtime_versions(axis),
                "options": options,
            }
        )
    )


def identity_stamp_conditions(
    column: Any,
    stamp: "WorkerStamp",
    identity: str,
    *,
    force: bool = False,
) -> list[ColumnElement[bool]]:
    """
    The stamp clause of an identity-keyed queue, shared by ``pending_conditions`` and the panel.

    Pending is "no stamp, or a stamp that is neither this identity nor a failure mark": a unit
    processed with a **different** producer is pending again, and a unit the worker marked as
    failed stays out of the plain queue — retrying it inside the same run is what ``force`` is
    for, and a caller that asks for ``force`` gets an empty list here on purpose, because the
    worker also advances by cursor and the two together are what keeps a forced run finite.
    """
    if force:
        return []
    value = func.coalesce(column[stamp.key].astext, "")
    return [
        or_(
            column.is_(None),
            ~column.has_key(stamp.key),
            value.not_in((identity, *FAILURE_STAMP_VALUES)),
        )
    ]


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

        Used by the identity-keyed workers: the stamp is the producer fingerprint (and, for the
        embedding, also the hash of the text it read), so a different model — or a text change —
        makes the unit pending again.
        """
        new_log = dict(execution_log) if execution_log else {}
        new_log[self.key] = value
        return new_log

    def clear(self, execution_log: dict[str, str] | None) -> dict[str, str]:
        """
        Returns a new log dict without this worker's key.

        The failure marks are why this exists: a document that failed for a reason which is gone —
        a bucket that was down for an afternoon — has to be able to lose the mark when a forced
        retry succeeds, or the panel keeps counting a repaired document as failed.
        """
        new_log = dict(execution_log) if execution_log else {}
        new_log.pop(self.key, None)
        return new_log


# Canonical stamps. Keeping them as module constants prevents the "worker_ner_v2"
# string from being duplicated (and drifting) across queries and workers.
#
# The three classifiers below carry the **producer identity** as their value (see
# ``producer_fingerprint``), not a status: a document classified by another engine, preset or
# threshold is pending again by itself. A failure is still the plain ``"ERROR"``.
NER = WorkerStamp("worker_ner_v2")
TYPOLOGY = WorkerStamp("worker_typology_classifier_v2")
# Stamp written on ``ArchiveTag.execution_log`` (tags have their own ledger). Its value is the
# label set **and** the producer identity, so a curator rewriting a label and a model changing
# both put the orphan tags back in the queue.
MACRO_CATEGORY = WorkerStamp("worker_macro_category_v1")
# Unlike the classifiers, this one stores the hash of the embedded text *and* the producer
# identity, so a human edit and a model bump each put the document back in the queue.
EMBEDDING = WorkerStamp("worker_embedding_v1")
THUMBNAIL = WorkerStamp("thumbnail")
THUMBNAIL_FAILED = WorkerStamp("thumbnail_failed", status="True")
# Structural anomaly validation (Fase 3.5-C). Identity-keyed like the other classifiers: its
# producer is the engine of the active ``LLM_CHECK`` rule, and its reasons also depend on the
# catalog, which is what ``force`` is for.
QUALITY_VALIDATOR = WorkerStamp("worker_quality_validator_v1")

#: The parent the source declared, when that parent had not arrived yet. The value is not a
#: status: it is ``"PENDING:<code>"`` while the child waits and ``"DONE:<description_id>"``
#: once the link exists. Values instead of statuses because the retry has to remember *which*
#: parent was missing — a bare ``PENDING`` would lose the code the origin sent.
HIERARCHY_PARENT = WorkerStamp("hierarchy_parent_v1")
HIERARCHY_PARENT_PENDING = "PENDING:"
HIERARCHY_PARENT_RESOLVED = "DONE:"

#: Not a worker: the mark a **curator's** decision leaves in a tag's log. It reuses the stamp
#: shape so the JSONB ledger has one format, and it exists so a tag a person reclassified is
#: visibly curated instead of looking like an unclassified tag whose drawer appeared by magic.
#: The value is free text (who and when), which is why it is written with ``mark_value``.
CURATED_MACRO_CATEGORY = WorkerStamp("curated_macro_category")


def cleaning_rule_stamp(rule_id: int) -> WorkerStamp:
    """Builds the per-rule stamp used by the dynamic cleaning rules."""
    return WorkerStamp(f"cleaning_rule_{rule_id}")


#: Stamps that must be invalidated when the AI text composition changes (an excerpt
#: approved, edited or undone). The embedding is deliberately absent: its stamp *is* a
#: hash of the effective text, so it re-queues by itself and needs no help.
TEXT_DEPENDENT_STAMPS: tuple[WorkerStamp, ...] = (NER, TYPOLOGY, QUALITY_VALIDATOR)
