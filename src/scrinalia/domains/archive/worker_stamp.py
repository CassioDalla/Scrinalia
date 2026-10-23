import re
from collections.abc import Mapping
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as distribution_version
from typing import Any, Literal, get_args

from sqlalchemy import ColumnElement, func, or_

from scrinalia.core.content_hash import ContentHash

StampStatus = Literal["DONE", "ERROR"]

#: The statuses as a set, derived from the literal so a fourth one cannot be added to the type and
#: forgotten here. An identity-keyed stamp refuses every one of them: a status where a fingerprint is
#: expected is the defect this vocabulary exists to prevent.
STAMP_STATUS_VALUES: frozenset[str] = frozenset(get_args(StampStatus))

#: Stamp values that mean the unit failed. Every ledger uses the same ``ERROR``; the thumbnail's
#: failure lives under the ``thumbnail_failed`` key, so the *key* names the failure and the value
#: does not need a second spelling. ``"True"`` was that second spelling, a boolean serialised into
#: a status vocabulary, and issue #149 removed it.
FAILURE_STAMP_VALUES: tuple[str, ...] = ("ERROR",)

#: The named "producer unknown": a unit an identity-keyed worker did run over, whose producer the
#: stamp cannot name. It exists because the legacy rows carried ``"DONE"`` — a **legal status** that
#: read as a success while naming no extractor — and a reader of the slot has to be able to tell
#: "produced by this fingerprint" from "produced by something we cannot identify". It is deliberately
#: **not** a fingerprint: ``identity_stamp_conditions`` treats it as pending, so the next run heals
#: the row by itself. The issue is attribution and reporting, never the queue.
PRODUCER_UNKNOWN = "PRODUCER_UNKNOWN"

#: What a plain producer fingerprint looks like. ``producer_fingerprint`` is a ``ContentHash``, whose
#: value is the SHA-256 hexdigest; the pattern is the write path's own validation and the read
#: surface's own classifier, so "is this a fingerprint?" has one definition.
FINGERPRINT_PATTERN = re.compile(r"^[0-9a-f]{64}$")

#: The embedding composes the MD5 of the effective text it read with the producer identity
#: (``embedding_stamp_sql``), so its fingerprint is two hashes and not one. A row carrying the bare
#: MD5 is a text hash written before the identity was composed into it: it names no producer, which
#: is why the read surface has to recognise the shape instead of trusting the slot's presence.
EMBEDDING_FINGERPRINT_PATTERN = re.compile(r"^[0-9a-f]{32}:[0-9a-f]{64}$")

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
    stamp: "IdentityStamp",
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

    ``PRODUCER_UNKNOWN`` — and every ``"DONE"`` written before it had a name — is neither the
    current identity nor a failure, so those units are pending and the next run re-reads them,
    writing a real fingerprint. That self-healing is why this issue is about attribution and
    reporting and not about the queue: ``count_pending`` is already telling the truth about them.
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
class BaseStamp:
    """The part of a stamp that does not depend on what the slot holds: key, presence and erase."""

    key: str

    def applies_to(self, execution_log: dict[str, str] | None) -> bool:
        """True when the document has NOT been processed by this worker yet."""
        return not execution_log or self.key not in execution_log

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


@dataclass(frozen=True)
class WorkerStamp(BaseStamp):
    """
    Status-keyed slot of a worker run inside ``execution_log``.

    The thumbnail's failure mark, the hierarchy parent the source declared and a curator's own
    decision are ledgers of this shape: they hold a status or a short piece of free text that the
    next run reads, and none of them keys a queue on *what produced* the answer. That last case is
    :class:`IdentityStamp`, and the split is deliberate — a status in an identity slot is the defect
    issue #137 removed, so the two cannot share a writer.
    """

    status: StampStatus = "DONE"

    def mark(self, execution_log: dict[str, str] | None, status: StampStatus | None = None) -> dict[str, str]:
        """Returns a new log dict with this worker's key set to the given status."""
        new_log = dict(execution_log) if execution_log else {}
        new_log[self.key] = status or self.status
        return new_log

    def mark_value(self, execution_log: dict[str, str] | None, value: str) -> dict[str, str]:
        """Returns a new log dict with this worker's key set to a short free-text value."""
        new_log = dict(execution_log) if execution_log else {}
        new_log[self.key] = value
        return new_log


@dataclass(frozen=True)
class IdentityStamp(BaseStamp):
    """
    Identity-keyed slot: the value is the **producer**, and nothing else may be written there.

    There is no ``mark`` here on purpose. A writer that wants to record "this producer ran" writes
    :meth:`mark_value` with a fingerprint the slot's own :attr:`fingerprint_pattern` accepts; one
    that wants to record a failure writes :meth:`mark_failed`, which is the plain ``"ERROR"`` and is
    still what keeps a failed unit out of the plain queue. ``"DONE"`` — a legal status, and the value
    1,691 NER rows really carry — cannot be written at all, which is the difference between a
    convention and a vocabulary.

    The pattern is not decoration: :meth:`WorkerStampRepository.count_stamp_breakdown` classifies the
    stored rows with the same expression, so "this slot carries a fingerprint" cannot mean one thing
    on the way in and another on the way out.
    """

    fingerprint_pattern: re.Pattern[str] = FINGERPRINT_PATTERN

    def mark_value(self, execution_log: dict[str, str] | None, fingerprint: str) -> dict[str, str]:
        """
        Returns a new log dict with this worker's key set to a producer fingerprint.

        Raises ``ValueError`` for anything the slot's pattern does not accept, which includes every
        :data:`StampStatus`, :data:`PRODUCER_UNKNOWN` and an empty string. That is a programming error
        in the worker and not something a client did, which is why it is not a ``DomainException``:
        the API owns no status for a caller that cannot reach this path.

        The pattern is applied with ``fullmatch``, not ``match``: Python's ``$`` also matches just
        before a trailing newline, while PostgreSQL's does not, so ``match`` would accept a value the
        read surface then classifies as legacy — the write and the report disagreeing about the same
        slot, which is the defect this type exists to prevent.
        """
        if not self.fingerprint_pattern.fullmatch(fingerprint):
            raise ValueError(
                f"'{self.key}' holds a producer fingerprint, not '{fingerprint}'. "
                "Use mark_failed() to record a failure."
            )
        new_log = dict(execution_log) if execution_log else {}
        new_log[self.key] = fingerprint
        return new_log

    def mark_failed(self, execution_log: dict[str, str] | None) -> dict[str, str]:
        """
        Returns a new log dict with this worker's key set to the failure mark.

        The failure is not an identity and does not pretend to be one: it is the plain ``"ERROR"``
        every queue predicate already treats as "out of the plain queue, back with ``--force``".
        """
        new_log = dict(execution_log) if execution_log else {}
        new_log[self.key] = "ERROR"
        return new_log


# Canonical stamps. Keeping them as module constants prevents the "worker_ner_v2"
# string from being duplicated (and drifting) across queries and workers.
#
# The five workers below carry the **producer identity** as their value (see
# ``producer_fingerprint``), not a status: a document classified by another engine, preset or
# threshold is pending again by itself. A failure is still the plain ``"ERROR"``, written through
# ``mark_failed``; a legacy row reads ``PRODUCER_UNKNOWN`` until a run names its producer again.
NER = IdentityStamp("worker_ner_v2")
TYPOLOGY = IdentityStamp("worker_typology_classifier_v2")
# Stamp written on ``ArchiveTag.execution_log`` (tags have their own ledger). Its value is the
# label set **and** the producer identity, so a curator rewriting a label and a model changing
# both put the orphan tags back in the queue.
MACRO_CATEGORY = IdentityStamp("worker_macro_category_v1")
# Unlike the classifiers, this one stores the hash of the embedded text *and* the producer
# identity, so a human edit and a model bump each put the document back in the queue.
EMBEDDING = IdentityStamp("worker_embedding_v1", fingerprint_pattern=EMBEDDING_FINGERPRINT_PATTERN)
THUMBNAIL = WorkerStamp("thumbnail")
THUMBNAIL_FAILED = WorkerStamp("thumbnail_failed", status="ERROR")
# Structural anomaly validation (Fase 3.5-C). Identity-keyed like the other classifiers: its
# producer is the engine of the active ``LLM_CHECK`` rule, and its reasons also depend on the
# catalog, which is what ``force`` is for.
QUALITY_VALIDATOR = IdentityStamp("worker_quality_validator_v1")

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
TEXT_DEPENDENT_STAMPS: tuple[IdentityStamp, ...] = (NER, TYPOLOGY, QUALITY_VALIDATOR)
