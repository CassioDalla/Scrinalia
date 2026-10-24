"""
The NER bench (issue #113): what the extractor finds, and how it gets the boundary wrong.

There is no human gabarito for named entities in this collection. ``archive_document_entities``
holds 64.504 links over 4.811 documents, and the ones that exist today were all written by the
worker itself (``bulk_link_entities``) — scoring the model against its own output measures nothing.
The link records its origin now (#135), so the bench can tell a link a person made from one an
extraction wrote, and only the second is a proposal. There is also no second source:
``domain_ner_exclusions`` has three rows and ``archive_entity_merge_log`` has none.

So this bench is built the other way round, and the way round is the whole design: **the gold comes
from correcting the stored output**. ``--propose`` reads the links the last run wrote and writes a
skeleton where the model's own extraction is ``proposed`` and ``expected`` is left empty, plus a
sheet where a curator marks what is wrong and what is missing. That is a proposal, never a gabarito:
a pre-annotated gold drags the annotator toward the model's answer, and the bias has to be declared
wherever the set is described — here, in ``testing/evaluation/README.md`` and in the file's own
``instructions_for_the_curator``.

**The two modes are not two views of one thing:**

``--predictions stored``
    Reads the links in ``archive_document_entities``. It is free and covers the whole collection, and
    it answers "how did the run that shipped do?". It compares the **term string only**, because the
    link is ``(description_id, entity_id)`` and carries no offsets. It also cannot separate a wrong
    boundary from a different producer's output, which is why the boundary breakdown is not measured
    here: the report prints the producer identities the documents carry instead, and a ``stored``
    score must not look like it measured a boundary.

``--predictions live``
    Runs the engine over the composed text and compares what it returns. The text is the worker's
    own — same columns, same ``NER`` rules, same ``". "`` separator, same ``_clean_raw_text`` — and a
    test pins the pair, because a bench that composed the text itself would score a text the worker
    never sees.

**The boundary breakdown is a token measure, not a character one.** ``ArchiveEntityDTO`` carries
``name`` and ``entity_type`` and no offsets, so neither mode can compare ``start_char``/``end_char``.
What the bench measures is whether one token sequence contains the other ("Curitiba" against
"Curitiba - Paraná"), which is what the token-boundary blocking of #69 produces. It is a count of
the defect, not of where it happened, and the report says so.

Run it from the repository root, against the real database::

    uv run python -m testing.evaluation.ner_quality --propose
    uv run python -m testing.evaluation.ner_quality --sheet
    uv run python -m testing.evaluation.ner_quality --predictions stored
    uv run python -m testing.evaluation.ner_quality --config spacy_ner:gpu \\
        --config spacy_ner:gpu:original_title,scope_content
"""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import math
import re
import time
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from typing import Any, cast

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from scrinalia.core.config import settings
from scrinalia.core.database import get_db
from scrinalia.core.logger import logger
from scrinalia.core.runner_config import NerRunnerConfig
from scrinalia.domains.archive.domain.text_quality import AI_TEXT_COLUMNS
from scrinalia.domains.archive.engines.NER.registry import (
    EngineName,
    PresetName,
    describe_config,
    get_engine,
)
from scrinalia.domains.archive.models import (
    ArchiveDocument,
    ArchiveDocumentEntity,
    ArchiveEntity,
    ArchiveEntityOrigin,
)
from scrinalia.domains.archive.repository import EntityRepository
from scrinalia.domains.archive.repository.governance import ai_writable_documents
from scrinalia.domains.archive.repository.text_quality_repo import (
    TextQualityRepository,
    composed_text_sql,
)
from scrinalia.domains.archive.worker_stamp import NER
from scrinalia.domains.archive.workers.worker_ner import (
    _clean_raw_text,
    execute,
    is_blocked_entity_name,
    load_entity_blacklist,
    producer_identity,
    resolved_columns,
)
from testing.evaluation import MIN_POSITIVES
from testing.evaluation.dataset import DATA_DIR, load_dataset

PAIRS_FILENAME = "ner_pairs.json"
SHEET_FILENAME = "ner_pairs.sheet.md"

#: Ordering key of the proposal. Recorded in ``sampling`` so the same run can be reproduced: the
#: proposal sorts every bucket by ``md5(seed:description_id)``, never by insertion order, so a
#: re-run after the collection grew proposes the same rows for the rows that already existed.
DEFAULT_SEED = "scrinalia-ner-v1"

#: What ``ArchiveEntityDTO`` is allowed to return. It is the engine's own contract, named here so a
#: report can print a type the collection does not currently have instead of hiding it.
ENTITY_TYPES = ("PER", "ORG", "LOC")

#: The row a type-less mention falls into. Neither the engine nor the model can produce one today,
#: and a gabarito can: a curator who knows the term is an entity but not which kind writes this, and
#: the report counts it separately instead of pretending it is a wrong type.
NO_TYPE = "(sem tipo)"

#: The aggregate row of the per-type table, and the bucket of a mention that was predicted while no
#: gold mention was waiting for it. English on purpose: it is a bucket of the metric and not a word
#: the curator writes in the file — the same reason ``ABSTAINED`` reads the way it does in the
#: typology bench.
OVERALL = "(overall)"

#: How many rows one entity type contributes to the proposal, and how many the documents with no
#: stored entity at all contribute. Without the second bucket recall has no denominator: the
#: documents the model found nothing in are exactly the ones absent from its own output, which is
#: the same trap the validator bench names.
DEFAULT_PER_TYPE = 40
DEFAULT_EMPTY_ROWS = 25

#: ``confidence`` is the curator's own certainty, the same vocabulary the other sets use.
CONFIDENCE_VALUES = ("alta", "media", "baixa")

#: The token splitter of the boundary measure. One definition, built once, because the metric and
#: the pairing both read it and two patterns would be two answers to the same question.
_TOKEN_SPLIT = re.compile(r"\W+")


# =============================================================================
# Metrics — pure functions, no session and no model
# =============================================================================
#
# This is the part a unit test can hold: the arithmetic that turns a gold list and a predicted list
# into a number. The model and the database are exercised elsewhere, so a defect in the metrics
# cannot hide behind "it needs a GPU".


@dataclass(frozen=True, order=True)
class Mention:
    """One extracted entity: the term as the engine returned it, and its type."""

    term: str
    type: str

    @property
    def normalized(self) -> str:
        """The term as the comparison reads it: case-folded and whitespace-collapsed."""
        return " ".join(self.term.split()).casefold()

    @property
    def tokens(self) -> tuple[str, ...]:
        """The term as a token sequence, which is what the boundary measure compares."""
        return tuple(token for token in _TOKEN_SPLIT.split(self.normalized) if token)


@dataclass(frozen=True)
class Match:
    """The one-to-one pairing of a gold list with a prediction, split by how each pair failed."""

    hits: tuple[tuple[Mention, Mention], ...] = ()
    boundary: tuple[tuple[Mention, Mention], ...] = ()
    type_confusions: tuple[tuple[Mention, Mention], ...] = ()
    missing: tuple[Mention, ...] = ()
    spurious: tuple[Mention, ...] = ()

    @property
    def misses(self) -> int:
        """Everything the gold asked for and the exact rule did not get."""
        return len(self.boundary) + len(self.type_confusions) + len(self.missing)


def _is_boundary(gold: Mention, predicted: Mention) -> bool:
    """
    True when one token sequence contains the other, and they are not the same string.

    This is the measurable form of #69's token-boundary defect: the model found the entity and
    returned a span that starts or ends in the wrong place ("Curitiba" for "Curitiba - Paraná").
    A reordering is *not* a boundary error — "Silva, João" does not contain "João Silva" as a
    contiguous run — and it falls through to a missing term plus a spurious one, which is what it is.
    """
    left, right = gold.tokens, predicted.tokens
    if not left or not right or left == right:
        return False
    shorter, longer = (left, right) if len(left) < len(right) else (right, left)
    return any(longer[index : index + len(shorter)] == shorter for index in range(len(longer) - len(shorter) + 1))


def match_mentions(gold: Sequence[Mention], predicted: Sequence[Mention]) -> Match:
    """
    Pairs the gold with the prediction in one pass, exact first and then by how it failed.

    The ladder is the metric's definition and the reason it is written down once:

    1. same type and same string — a **hit**;
    2. same string and a different type — a **type confusion**, which is neither a boundary error nor
       a term the model failed to see, and was invisible while it was folded into the other two;
    3. same type and one token run inside the other — a **boundary** miss;
    4. otherwise the term is **missing**, and every prediction nothing claimed is **spurious**.

    Both sides are sorted, so the pairing does not depend on the order the curator happened to write
    the rows in — a set re-ordered by hand must not produce a different score.
    """
    remaining = sorted(predicted)
    gold_sorted = sorted(gold)
    hits: list[tuple[Mention, Mention]] = []
    boundary: list[tuple[Mention, Mention]] = []
    type_confusions: list[tuple[Mention, Mention]] = []
    missing: list[Mention] = []

    def claim(index: int) -> Mention:
        return remaining.pop(index)

    for expected in gold_sorted:
        exact = next(
            (
                index
                for index, seen in enumerate(remaining)
                if seen.type == expected.type and seen.normalized == expected.normalized
            ),
            None,
        )
        if exact is not None:
            hits.append((expected, claim(exact)))
            continue

        same_term = next(
            (index for index, seen in enumerate(remaining) if seen.normalized == expected.normalized),
            None,
        )
        if same_term is not None:
            type_confusions.append((expected, claim(same_term)))
            continue

        near = next(
            (
                index
                for index, seen in enumerate(remaining)
                if seen.type == expected.type and _is_boundary(expected, seen)
            ),
            None,
        )
        if near is not None:
            boundary.append((expected, claim(near)))
            continue

        missing.append(expected)

    return Match(
        hits=tuple(hits),
        boundary=tuple(boundary),
        type_confusions=tuple(type_confusions),
        missing=tuple(missing),
        spurious=tuple(sorted(remaining)),
    )


@dataclass(frozen=True)
class Truth:
    """What the curator said, once the correction is signed: the terms that should have been found."""

    mentions: tuple[Mention, ...]

    @property
    def is_empty(self) -> bool:
        """
        No entity is the right answer for this document.

        It is a real answer and not a missing one: a description that carries no name at all is the
        only thing that turns "the model invented an entity" into a measured false positive instead
        of an invisible one.
        """
        return not self.mentions


@dataclass(frozen=True)
class Extraction:
    """What the engine returned for one document, and — when the run was timed — how long it took."""

    mentions: tuple[Mention, ...]


@dataclass(frozen=True)
class ScoredRow:
    """One labelled document after the extractor answered it."""

    description_id: str
    truth: Truth
    extraction: Extraction

    @property
    def match(self) -> Match:
        return match_mentions(self.truth.mentions, self.extraction.mentions)

    @property
    def correct(self) -> bool:
        """
        Agreement with the signed gabarito, under the exact rule **and no other**.

        A mention the curator left out is right exactly when the engine found none. The partial rule
        may be reported next to this one but never instead of it: a boundary that counts as a hit is
        how a defect of exactly this shape stops being visible.
        """
        match = self.match
        return not (match.missing or match.boundary or match.type_confusions or match.spurious)


@dataclass
class TypeMetrics:
    """
    Precision, recall and F1 of one entity type — or of the whole set.

    ``support`` is how many mentions of this type the gabarito asked for, and it is the number the
    floor is applied to. ``false_positives`` is every prediction of this type the exact rule did not
    match, which is the spurious terms *and* the ones that were found with a wrong boundary or a
    wrong type: they are outputs, and under exact match each one is wrong.
    """

    label: str
    support: int = 0
    true_positives: int = 0
    boundary: int = 0
    type_confusions: int = 0
    spurious: int = 0
    min_positives: int = MIN_POSITIVES

    @property
    def measured(self) -> bool:
        return self.support >= self.min_positives

    @property
    def false_positives(self) -> int:
        return self.spurious + self.boundary + self.type_confusions

    @property
    def false_negatives(self) -> int:
        return max(0, self.support - self.true_positives)

    @property
    def precision(self) -> float:
        denominator = self.true_positives + self.false_positives
        return self.true_positives / denominator if denominator else 0.0

    @property
    def recall(self) -> float:
        return self.true_positives / self.support if self.support else 0.0

    @property
    def f1(self) -> float:
        precision, recall = self.precision, self.recall
        return 2 * precision * recall / (precision + recall) if precision + recall else 0.0

    @property
    def relaxed_recall(self) -> float:
        """
        Recall when a boundary miss counts as found — printed **next to** the exact number.

        It is the number that answers "how much of the miss is the boundary?", and it never replaces
        ``recall``: on the day the boundary rule is fixed this is the score the model already earns,
        and on any other day quoting it alone would hide the defect the bench exists to count.
        """
        found = self.true_positives + self.boundary
        return found / self.support if self.support else 0.0


def _blank_metrics(labels: Sequence[str], min_positives: int) -> dict[str, TypeMetrics]:
    return {label: TypeMetrics(label=label, min_positives=min_positives) for label in labels}


def observed_types(rows: Sequence[ScoredRow]) -> list[str]:
    """Every type the gold or the prediction used, plus the engine's own three, sorted."""
    seen = {mention.type for row in rows for mention in (*row.truth.mentions, *row.extraction.mentions)}
    return sorted(seen | set(ENTITY_TYPES))


def _apply(
    metrics: dict[str, TypeMetrics],
    match: Match,
    label_of: Callable[[str], str],
    min_positives: int,
) -> None:
    """
    Folds one document's pairing into a metrics table, under the key ``label_of`` chooses.

    The same function fills the per-type table and the ``(overall)`` row, which is what keeps them
    from disagreeing: ``label_of`` is the identity for a type and a constant for the aggregate.

    Where each bucket is credited is the metric's definition. ``boundary`` is one *miss* for the gold
    type and, because the prediction carries that same type, one false positive for it too. A
    ``type_confusion`` is a miss for the type the gabarito asked for and a false positive for the
    type the engine answered — the two types are genuinely different rows, and crediting both is
    what makes the table add up.
    """

    def row(label: str) -> TypeMetrics:
        key = label_of(label)
        if key not in metrics:
            metrics[key] = TypeMetrics(label=key, min_positives=min_positives)
        return metrics[key]

    for expected, _seen in match.hits:
        row(expected.type).support += 1
        row(expected.type).true_positives += 1
    for expected, _seen in match.boundary:
        row(expected.type).support += 1
        row(expected.type).boundary += 1
    for expected, seen in match.type_confusions:
        row(expected.type).support += 1
        row(seen.type).type_confusions += 1
    for expected in match.missing:
        row(expected.type).support += 1
    for seen in match.spurious:
        row(seen.type).spurious += 1


def per_type(
    rows: Sequence[ScoredRow], types: Sequence[str], min_positives: int = MIN_POSITIVES
) -> dict[str, TypeMetrics]:
    """The per-type table, plus the ``(overall)`` row, from the same pairing the row already has."""
    metrics = _blank_metrics([*types, OVERALL], min_positives)
    for row in rows:
        match = row.match
        _apply(metrics, match, lambda label: label, min_positives)
        _apply(metrics, match, lambda _label: OVERALL, min_positives)
    return metrics


def macro_f1(metrics: dict[str, TypeMetrics]) -> float:
    """Mean F1 over the **measured** types only: an unmeasured type is absent, not zero."""
    measured = [metric.f1 for label, metric in metrics.items() if label != OVERALL and metric.measured]
    return sum(measured) / len(measured) if measured else 0.0


def agreement(rows: Sequence[ScoredRow]) -> float:
    """Share of the scored documents whose extraction matched the gabarito exactly."""
    return sum(1 for row in rows if row.correct) / len(rows) if rows else 0.0


def empty_rate(rows: Sequence[ScoredRow]) -> float:
    """Share of the scored documents the extractor returned nothing for."""
    return sum(1 for row in rows if not row.extraction.mentions) / len(rows) if rows else 0.0


def boundary_breakdown(rows: Sequence[ScoredRow]) -> Counter[str]:
    """
    The defect as counts: what the gold asked for, and how each miss failed.

    This is the number #69 could only describe in prose ("the token-boundary blocking is a measurable
    defect"). It is a partition of the gold: every expected mention is exactly one of ``hits``,
    ``boundary``, ``type`` or ``missing``, so the four add up to the support and a reader can see the
    arithmetic instead of trusting it.
    """
    counts: Counter[str] = Counter()
    for row in rows:
        match = row.match
        counts["hits"] += len(match.hits)
        counts["boundary"] += len(match.boundary)
        counts["type_confusions"] += len(match.type_confusions)
        counts["missing"] += len(match.missing)
        counts["spurious"] += len(match.spurious)
    return counts


def type_distribution(rows: Sequence[ScoredRow], side: str) -> Counter[str]:
    """How many mentions each type took, on the gold side or on the predicted side."""
    if side == "gold":
        return Counter(mention.type for row in rows for mention in row.truth.mentions)
    return Counter(mention.type for row in rows for mention in row.extraction.mentions)


def largest_share(counts: Counter[str]) -> tuple[str, float]:
    """The biggest predicted type and its share: the collapse detector, as in the sibling benches."""
    total = sum(counts.values())
    if not counts or total <= 0:
        return ("", 0.0)
    label, count = counts.most_common(1)[0]
    return (label, count / total)


def entropy_bits(counts: Counter[str]) -> float:
    """
    Shannon entropy of the predicted types, in bits.

    Over the types the engine used, so a model that answers ``ORG`` to everything is a single bucket
    with zero bits — the same collapse the typology bench measures, in the vocabulary of this axis.
    ``max(0.0, ...)`` because one bucket gives ``-0.0`` and "-0.00 bits" reads like a broken metric.
    """
    total = sum(counts.values())
    if total <= 0:
        return 0.0
    return max(0.0, -sum((count / total) * math.log2(count / total) for count in counts.values() if count > 0))


# =============================================================================
# Configurations
# =============================================================================


@dataclass(frozen=True)
class BenchConfig:
    """One scored configuration: the three things ``worker_ner.producer_identity`` signs."""

    engine: str
    preset: str | None
    columns: tuple[str, ...]

    @property
    def label(self) -> str:
        return f"{self.engine}:{self.preset or '-'}:{','.join(self.columns)}"


def parse_config(text: str, default_columns: tuple[str, ...]) -> BenchConfig:
    """
    Reads ``engine[:preset[:columns]]``, filling the empty fields from the worker.

    The fields are exactly what ``worker_ner.producer_identity`` signs, and that is the point: the
    bench can only measure a configuration the worker can be told to run. The model is never named
    here — a new model is a property of the language profile, not an edit to this script.
    """
    parts = text.split(":")
    if len(parts) > 3:
        raise SystemExit(f"--config {text!r} has {len(parts)} fields; expected engine[:preset[:columns]].")
    engine = parts[0].strip()
    if not engine:
        raise SystemExit(f"--config {text!r} names no engine.")
    preset = parts[1].strip() if len(parts) > 1 and parts[1].strip() else None
    columns = (
        tuple(part.strip() for part in parts[2].split(",") if part.strip())
        if len(parts) > 2 and parts[2].strip()
        else default_columns
    )
    unknown = [column for column in columns if column not in AI_TEXT_COLUMNS]
    if unknown:
        raise SystemExit(
            f"--config {text!r} names columns the AI text does not have: {unknown}. Known: {AI_TEXT_COLUMNS}"
        )
    return BenchConfig(engine=engine, preset=preset, columns=columns)


def worker_default_config() -> str:
    """
    The configuration the worker runs with when nobody says otherwise, read from its own signature.

    Retyping ``"spacy_ner:gpu"`` here would be a second definition of the worker's default, and the
    day it changes the bench would keep scoring the old one while calling it "the current
    configuration".
    """
    parameters = inspect.signature(execute).parameters
    return f"{parameters['engine_name'].default}:{parameters['preset'].default}"


# =============================================================================
# Reading the collection and the labelled set
# =============================================================================


@dataclass(frozen=True)
class Candidate:
    """One document the proposal considers, with what the stored run already found in it."""

    description_id: str
    title: str
    stored: tuple[Mention, ...]
    #: The bucket this row was **drawn for** and not the first type it happens to contain. The two
    #: differ often: a photograph whose text names a place and a person carries both, and labelling
    #: it by the first would report a PER quota as if it had found nothing (measured: 40 rows drawn
    #: for PER and ORG each, all of them labelled LOC).
    proposed_by: str


def read_composed_text(db: Session, description_ids: Sequence[str], columns: Sequence[str]) -> dict[str, str]:
    """
    The text the worker hands the engine, for these ids and columns.

    Composed by ``composed_text_sql`` — the expression ``worker_ner.execute`` builds — with the
    worker's own scope (``NER``) and separator (``". "``), and then cleaned by the worker's own
    ``_clean_raw_text``, which strips URLs and e-mails before inference. The pinning test runs the
    real worker with a fake engine and compares what it handed to the model with what this function
    returns: a bench that composed the text itself would measure a text the worker never saw.
    """
    if not description_ids:
        return {}
    rules = TextQualityRepository(db).get_active_rules("NER")
    text_expression = composed_text_sql(columns, rules, separator=". ")
    stmt = select(ArchiveDocument.description_id, text_expression).where(
        ArchiveDocument.description_id.in_(list(description_ids))
    )
    return {
        description_id: _clean_raw_text(" ".join((text or "").split()))
        for description_id, text in db.execute(stmt).all()
    }


def worker_scope_ids(db: Session, description_ids: Sequence[str]) -> set[str]:
    """
    The labelled documents the worker is allowed to read at all.

    The scope is ``ai_writable_documents`` and the rule that there is text to read — deliberately
    **not** ``pending_conditions``. The stamp in that predicate is a queue cursor: it excludes the
    documents this producer already wrote, which are exactly the ones a bench has to score. A
    HUMAN_APPROVED document is out of scope, because the worker will never touch it again, and
    scoring it would attribute a human's curation to the model.
    """
    if not description_ids:
        return set()
    filters = [getattr(ArchiveDocument, column).is_not(None) for column in NerRunnerConfig().columns_to_extract]
    stmt = select(ArchiveDocument.description_id).where(
        ArchiveDocument.description_id.in_(list(description_ids)),
        ai_writable_documents(),
        or_(*filters),
    )
    return {description_id for (description_id,) in db.execute(stmt).all()}


def stored_mentions(db: Session, description_ids: Sequence[str]) -> dict[str, list[Mention]]:
    """
    What the last run left in ``archive_document_entities``, per document.

    The links the worker wrote through ``bulk_link_entities``. They are the model's own output, which
    is why they are a **proposal** and never a gold: the curator corrects them, and the correction is
    the gabarito (see the module docstring). A link a person made is excluded — it is the curator's
    decision about this description, and counting it as the model's proposal would credit the model
    for a correction (#135). ``UNKNOWN`` stays in: every link that predates the origin column was
    written by a run, and the column says "not attributed", not "not the model's".
    """
    if not description_ids:
        return {}
    stmt = (
        select(ArchiveDocumentEntity.description_id, ArchiveEntity.name, ArchiveEntity.entity_type)
        .join(ArchiveEntity, ArchiveEntity.entity_id == ArchiveDocumentEntity.entity_id)
        .where(
            ArchiveDocumentEntity.description_id.in_(list(description_ids)),
            ArchiveDocumentEntity.origin != ArchiveEntityOrigin.HUMAN,
        )
    )
    mentions: dict[str, list[Mention]] = {}
    for description_id, name, entity_type in db.execute(stmt).all():
        mentions.setdefault(description_id, []).append(Mention(term=name, type=entity_type))
    return mentions


def stored_producers(db: Session, description_ids: Sequence[str]) -> Counter[str]:
    """
    The producer identities the scored documents carry, so a ``stored`` score can name its author.

    This is the honest substitute for the boundary breakdown in this mode: the links have no offsets
    *and* no attribution, so the report says which run wrote them instead of implying the
    configuration under test did. A document with no stamp is named, not dropped.
    """
    if not description_ids:
        return Counter()
    stmt = select(ArchiveDocument.description_id, ArchiveDocument.execution_log).where(
        ArchiveDocument.description_id.in_(list(description_ids))
    )
    counts: Counter[str] = Counter()
    for _description_id, log in db.execute(stmt).all():
        counts[str((log or {}).get(NER.key, "(sem carimbo)"))] += 1
    return counts


def read_candidates(db: Session, per_type: int, empty_rows: int, seed: str) -> list[Candidate]:
    """
    The documents the proposal draws from: those with stored entities, plus those with none.

    Both halves are necessary. The first is where a correction can be made — there is an answer to
    fix; the second is where recall is looked for, because a document the model found nothing in is
    absent from its own output and a sample drawn only from that output can never see it.
    """
    stmt = select(ArchiveDocument.description_id, ArchiveDocument.original_title).where(ai_writable_documents())
    rows = [(description_id, title or "") for description_id, title in db.execute(stmt).all()]
    stored = stored_mentions(db, [description_id for description_id, _title in rows])
    candidates = [
        Candidate(
            description_id=row_id,
            title=title,
            stored=tuple(sorted(stored.get(row_id, []))),
            proposed_by=NO_TYPE,
        )
        for row_id, title in rows
    ]

    with_stored = sorted(
        (candidate for candidate in candidates if candidate.stored), key=lambda c: _order_key(seed, c.description_id)
    )
    without = sorted(
        (candidate for candidate in candidates if not candidate.stored),
        key=lambda c: _order_key(seed, c.description_id),
    )

    picked: list[Candidate] = []
    seen: set[str] = set()
    for entity_type in ENTITY_TYPES:
        taken = 0
        for candidate in with_stored:
            if taken >= per_type:
                break
            if candidate.description_id in seen:
                continue
            if entity_type not in {mention.type for mention in candidate.stored}:
                continue
            picked.append(replace(candidate, proposed_by=entity_type))
            seen.add(candidate.description_id)
            taken += 1
    for candidate in without[:empty_rows]:
        if candidate.description_id not in seen:
            picked.append(replace(candidate, proposed_by=NO_TYPE))
            seen.add(candidate.description_id)
    return sorted(picked, key=lambda c: c.description_id)


def _order_key(seed: str, description_id: str) -> str:
    """The deterministic ordering key of the proposal, recorded in ``sampling``."""
    return hashlib.md5(f"{seed}:{description_id}".encode()).hexdigest()


# =============================================================================
# Reading the labelled set
# =============================================================================


@dataclass(frozen=True)
class LabelledRow:
    """One row of the labelled set, as the scorer needs it."""

    description_id: str
    truth: Truth
    needs_decision: bool
    note: str
    #: Whether a person left a mark on this row. ``expected: null`` is both "no entity should have
    #: been found" and the proposal's own placeholder, so the certainty or the note is the only
    #: thing that tells a correction from a line nobody opened — see :func:`scorable_rows`.
    reviewed: bool = True


def _mention(value: Any, index: int, description_id: str) -> Mention:
    """Validates one ``{term, type}`` object of a gold or proposed list."""
    if not isinstance(value, dict):
        raise SystemExit(
            f"row {index} ({description_id}) has {value!r} in a mention list; expected an object "
            'like {"term": "Curitiba", "type": "LOC"}. The shape is in testing/evaluation/README.md.'
        )
    term = str(value.get("term", "")).strip()
    if not term:
        raise SystemExit(f"row {index} ({description_id}) has a mention with no 'term'.")
    entity_type = str(value.get("type", "")).strip() or NO_TYPE
    return Mention(term=term, type=entity_type)


def _mentions(value: Any, index: int, description_id: str, field: str) -> tuple[Mention, ...]:
    """Validates one list field of a row: a list of ``{term, type}``, or null for an empty one."""
    if value is None:
        return ()
    if not isinstance(value, list):
        raise SystemExit(
            f"row {index} ({description_id}) has '{field}': {value!r}; expected a list of mentions or null."
        )
    return tuple(_mention(item, index, description_id) for item in value)


def load_labelled(path: Path, allow_draft: bool) -> tuple[list[LabelledRow], dict[str, Any]]:
    """
    Reads the labelled set, refusing a draft unless ``--allow-draft`` says otherwise.

    The human signature is what makes the number quotable: a set nobody reviewed produces a figure
    that reads exactly like a reviewed one, and the pre-annotation makes that failure more likely
    here than anywhere else, because the wrong answer is already written in the file.
    """
    payload = load_payload(path)
    status = str(payload.get("status", ""))
    if status.strip().lower().startswith("draft") and not allow_draft:
        raise SystemExit(
            f"{path} still says {status!r}. The bench refuses to score a set no curator signed, "
            "because the number would be quoted as if someone had — and because every row already "
            "carries the model's own answer in 'proposed'. Correct the rows, write the signature into "
            "'status', or pass --allow-draft to explore."
        )

    rows: list[LabelledRow] = []
    for index, pair in enumerate(payload.get("pairs", []), start=1):
        if "expected" not in pair:
            raise SystemExit(
                f"row {index} ({pair.get('description_id')}) has no 'expected' field. A row left as the "
                "proposal was written is not labelled: delete the row or write what should have been found."
            )
        description_id = str(pair.get("description_id", "")).strip()
        if not description_id:
            raise SystemExit(f"row {index} has no 'description_id'.")
        confidence = pair.get("confidence")
        if confidence is not None and confidence not in CONFIDENCE_VALUES:
            raise SystemExit(
                f"row {index} ({description_id}) has confidence {confidence!r}; expected one of {CONFIDENCE_VALUES} or null."
            )
        rows.append(
            LabelledRow(
                description_id=description_id,
                truth=Truth(mentions=_mentions(pair["expected"], index, description_id, "expected")),
                needs_decision=bool(pair.get("needs_decision", False)),
                note=str(pair.get("note", "")),
                reviewed=confidence is not None or bool(str(pair.get("note", "")).strip()),
            )
        )
    return rows, payload


def scorable_rows(rows: Sequence[LabelledRow]) -> tuple[list[LabelledRow], list[str], int]:
    """
    Splits the set into what may be scored, what nobody read, and what needs a policy decision.

    A row with no ``confidence`` and no ``note`` is one a person never opened — the proposal wrote
    ``expected`` there, and scoring it would measure the model against the answer the model itself
    gave, which is the anchoring failure this bench is built around. It leaves the score and is
    **printed**, never dropped in silence: a report that quietly shrank its own denominator would
    hide how much of the set a curator actually worked through.
    """
    unread = [row.description_id for row in rows if not row.reviewed and not row.needs_decision]
    scoreable = [row for row in rows if row.reviewed and not row.needs_decision]
    needs_decision = sum(1 for row in rows if row.needs_decision)
    return scoreable, unread, needs_decision


def load_payload(path: Path) -> dict[str, Any]:
    """
    Reads the labelled set, through the shared drawer loader when it lives in the standard place.

    Going through ``dataset.load_dataset`` is what makes a missing file say where it belongs and why
    it is not versioned, instead of a bare ``FileNotFoundError`` whose reflex fix is to recreate the
    set from the code — the one thing that must not happen. An explicit path elsewhere still fails
    with the same instruction.
    """
    if path.parent.resolve() == DATA_DIR.resolve():
        return load_dataset(path.name)
    if not path.exists():
        raise SystemExit(
            f"{path} does not exist. Build it with `--propose`, correct it by hand, then score it. The "
            "expected shape is documented in testing/evaluation/README.md."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def blocked_gold_terms(db: Session, rows: Sequence[LabelledRow]) -> list[str]:
    """
    Gold terms the worker's blacklist refuses to extract, which are misses no model can avoid.

    ``is_blocked_entity_name`` is what the worker applies after inference, so the bench mirrors it —
    and a term a curator decided belongs to the subject axis would otherwise read as the model
    failing, when the institution asked for it. Reported, not removed: the row stays in the score.
    """
    blacklist = load_entity_blacklist(db)
    return sorted(
        {
            mention.term
            for row in rows
            for mention in row.truth.mentions
            if is_blocked_entity_name(mention.term, blacklist)
        }
    )


# =============================================================================
# Scoring
# =============================================================================


def score_stored(db: Session, rows: Sequence[LabelledRow]) -> list[ScoredRow]:
    """
    Scores the links the last run wrote, without loading a model.

    This is the "how did the run that shipped do?" question, and it is also the only view that
    covers the whole collection for free. Two things it cannot do, and both are said in the report:
    it compares the term string only, because the link carries no offsets, and it attributes nothing
    to the configuration under test — the producer identity is whatever the document carries.
    """
    ids = [row.description_id for row in rows]
    stored = stored_mentions(db, ids)
    return [
        ScoredRow(
            description_id=row.description_id,
            truth=row.truth,
            extraction=Extraction(mentions=tuple(stored.get(row.description_id, []))),
        )
        for row in rows
    ]


def score_live(
    db: Session,
    config: BenchConfig,
    rows: Sequence[LabelledRow],
    limit: int | None = None,
    engine: Any | None = None,
) -> tuple[list[ScoredRow], float]:
    """
    Runs the engine over the composed text and mirrors the worker's decision exactly.

    The mirror is the point, and it is three rules: the text is composed and cleaned the way
    ``execute`` does it, a document whose text is empty never reaches the model (the worker stamps it
    and moves on), and the blacklist filters the output. A bench that skipped any of the three would
    score an inference the worker does not perform.

    ``engine`` lets a caller sweeping several configurations over one set build the model once: the
    load is a cost of the run, not of an answer, and charging it per configuration would distort the
    seconds per document the report prints.

    Returns the scored rows and the **seconds per document the engine actually saw** — not per row
    of the set, because a document with empty text never reaches the model and counting it would
    understate the cost of a run.
    """
    # Annotated ``Any`` on purpose: the engine is a Protocol the registry injects, and naming a
    # concrete type here would be a second definition of the contract.
    runner: Any = engine if engine is not None else build_engine(db, config)

    selected = list(rows[:limit] if limit else rows)
    texts = read_composed_text(db, [row.description_id for row in selected], config.columns)
    blacklist = load_entity_blacklist(db)

    # The empty-text rule is the worker's: a document with nothing to read is stamped and skipped,
    # so the engine is never asked, and its extraction is empty rather than missing.
    askable = [row for row in selected if texts.get(row.description_id, "")]
    asked_texts = [texts[row.description_id] for row in askable]

    started = time.monotonic()
    results = runner.extract(asked_texts) if asked_texts else []
    seconds_per_document = (time.monotonic() - started) / len(asked_texts) if asked_texts else 0.0

    found: dict[str, tuple[Mention, ...]] = {}
    for row, dtos in zip(askable, results, strict=True):
        found[row.description_id] = tuple(
            Mention(term=dto.name, type=dto.entity_type)
            for dto in dtos
            if not is_blocked_entity_name(dto.name, blacklist)
        )

    return [
        ScoredRow(
            description_id=row.description_id,
            truth=row.truth,
            extraction=Extraction(mentions=found.get(row.description_id, ())),
        )
        for row in selected
    ], seconds_per_document


def build_engine(db: Session, config: BenchConfig) -> Any:
    """
    The engine the worker would build, with the installation's own synonym rules.

    ``get_engine`` is handed ``EntityRepository.get_ner_synonyms_rules()`` exactly as ``execute``
    does, because those rules rewrite what the extractor returns and a bench without them would
    measure a pipeline nobody runs.
    """
    rules = EntityRepository(db).get_ner_synonyms_rules()
    return get_engine(
        engine_name=cast(EngineName, config.engine),
        preset=cast(PresetName, config.preset),
        custom_rules=rules,
    )


def describe(config: BenchConfig) -> dict[str, Any]:
    """The effective engine configuration, without loading the pipeline (``describe_config``)."""
    return describe_config(cast(EngineName, config.engine), cast(PresetName, config.preset))


def identity_for(config: BenchConfig) -> str:
    """The stamp a run of this configuration writes, so the report names the producer it measures."""
    return producer_identity(
        engine_name=cast(EngineName, config.engine),
        preset=cast(PresetName, config.preset),
        columns_to_extract=list(config.columns),
        engine_kwargs={},
    )


# =============================================================================
# The proposal: skeleton and sheet
# =============================================================================


def build_payload(candidates: Sequence[Candidate], seed: str, per_type: int, empty_rows: int) -> dict[str, Any]:
    """The skeleton of the labelled set: the model's extraction as ``proposed``, ``expected`` empty."""
    pairs = [
        {
            "description_id": candidate.description_id,
            "proposed_by": candidate.proposed_by,
            "title": candidate.title,
            "proposed": [{"term": mention.term, "type": mention.type} for mention in candidate.stored],
            "expected": None,
            "confidence": None,
            "needs_decision": False,
            "note": "",
        }
        for candidate in candidates
    ]
    return {
        "description": (
            "Gabarito de entidades nomeadas (NER) construído por CORREÇÃO da saída gravada: cada linha "
            "traz o que a última execução extraiu em 'proposed', e o curador escreve em 'expected' o que "
            "deveria ter sido encontrado. Não é uma medida do modelo contra si mesmo."
        ),
        "collection": "",
        "sampling": (
            f"seed={seed} · {per_type} linha(s) por tipo de entidade ({', '.join(ENTITY_TYPES)}) a partir dos "
            f"documentos com vínculo gravado, mais {empty_rows} documento(s) sem nenhuma entidade gravada — "
            "sem esse segundo balde o recall não tem denominador."
        ),
        "instructions_for_the_curator": [
            "ATENÇÃO, viés de pré-anotação: 'proposed' é a resposta do PRÓPRIO modelo. Ela está na "
            + "linha para poupar digitação, e é a razão pela qual este conjunto precisa de você: "
            + "apagar o que está certo é fácil, notar o que FALTOU não é. Releia o texto antes de "
            + "aceitar qualquer linha.",
            '\'expected\' é a lista do que deveria ter sido encontrado: [{"term": "Curitiba", '
            + '"type": "LOC"}]. Lista vazia (ou null) significa que nenhuma entidade deveria ter '
            + "sido encontrada — é a resposta certa para uma descrição sem nome próprio, e é o que "
            + "transforma uma invenção do modelo em falso positivo medido.",
            "Os tipos são PER (pessoa), ORG (instituição) e LOC (lugar). Se você souber que o termo é "
            + 'entidade mas não qual tipo, use "(sem tipo)": o relatório conta isso em separado.',
            "Corrija o limite: 'Curitiba - Paraná' quando o modelo devolveu só 'Curitiba' é um erro de "
            + "fronteira, e é a metade do defeito que este conjunto existe para medir.",
            "'confidence' é a SUA certeza: alta, media ou baixa. Ela, ou uma 'note', é o que diz "
            + "que uma pessoa passou pela linha — uma linha sem as duas faz a bancada recusar o "
            + "conjunto, porque 'expected: null' também é o que a proposta escreve.",
            "Se você apagou tudo o que o modelo propôs, escreva o motivo em 'note': sem isso não há "
            + "como distinguir a sua correção de uma linha que ninguém leu.",
            "Marque 'needs_decision': true quando a dúvida for da política e não sua (o termo é "
            + "entidade ou é assunto?). O relatório exclui essas linhas do placar e as conta em separado.",
            "Escreva o motivo em 'note': é a parte que um leitor posterior precisa.",
            "Quando terminar, troque 'status' por 'aprovado por <quem> em <data>' e registre em "
            + "'approved_note' o que mudou. A bancada se recusa a pontuar um conjunto 'draft'.",
        ],
        "pairs": pairs,
        "status": "draft — nenhum curador revisou este conjunto ainda",
        "approved_note": "",
    }


def _labelled(payload: dict[str, Any]) -> int:
    """How many rows a human already touched, so a re-run can say what it would discard."""
    return sum(
        1 for pair in payload.get("pairs", []) if pair.get("expected") or pair.get("confidence") or pair.get("note")
    )


def write_skeleton(out: Path, payload: dict[str, Any], force: bool) -> None:
    """
    Writes the skeleton, refusing to overwrite a curator's work.

    A re-run of the proposal would destroy a correction that has no undo, so the default is to
    refuse. The preview of what would die is printed before ``--force`` does it (principle VI).
    """
    if out.exists() and not force:
        existing = json.loads(out.read_text(encoding="utf-8"))
        raise SystemExit(
            f"{out} already exists with {_labelled(existing)} corrected row(s). The labelled set is a "
            "curator's work and re-running the proposal would overwrite it. Pass --force only if you "
            "mean to discard it, or point --out at another file."
        )
    if out.exists():
        existing = json.loads(out.read_text(encoding="utf-8"))
        logger.warning(f"⚠️ --force discards {_labelled(existing)} corrected row(s) in {out}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    logger.success(f"💾 skeleton written to {out} ({len(payload['pairs'])} rows, nothing written to the database)")


def _fmt(mentions: Sequence[Mention]) -> str:
    """A mention list as the sheet reads it: one ``termo (TIPO)`` per item, or an explicit 'nenhuma'."""
    if not mentions:
        return "_nenhuma_"
    return "; ".join(f"{mention.term} ({mention.type})" for mention in mentions)


def sheet_lines(payload: dict[str, Any], effective_text: dict[str, str]) -> list[str]:
    """
    The human sheet: what the curator reads to correct each row, in the file's own order.

    The text comes from the database and never from the file, so the sheet cannot disagree with what
    the scorer will read — and the anchoring warning is printed at the top of every page of rows, not
    once in the README where the person labelling will not look.
    """
    lines = [
        "# Conjunto rotulado de entidades nomeadas — folha de correção",
        "",
        f"Coleção: {payload.get('collection', '')}",
        "",
        f"Status: {payload.get('status', '')}",
        "",
        "> **Viés de pré-anotação:** `proposed` é a resposta do próprio modelo. Ela está aqui para",
        "> poupar digitação, não para ser aceita. O erro que este conjunto mais precisa pegar é o",
        "> termo que **faltou**, e uma linha pré-preenchida não chama atenção para o que não está nela.",
        "",
    ]
    for index, pair in enumerate(payload["pairs"], start=1):
        lines.append(f"## {index}. `{pair['description_id']}` — {pair.get('proposed_by', '')}")
        lines.append("")
        lines.append(f"- **Título:** {pair.get('title', '')}")
        text = effective_text.get(pair["description_id"], "")
        if text and text != pair.get("title"):
            lines.append(f"- **Texto que o modelo lê:** {text}")
        proposed = [Mention(term=item["term"], type=item["type"]) for item in pair.get("proposed") or []]
        lines.append(f"- **proposto pelo modelo:** {_fmt(proposed)}")
        expected = pair.get("expected")
        corrected = (
            [Mention(term=item["term"], type=item["type"]) for item in expected] if isinstance(expected, list) else []
        )
        shown = _fmt(corrected) if expected is not None else "_(ainda não corrigido)_"
        lines.append(f"- **esperado:** {shown}   _(confiança: {pair.get('confidence') or '—'})_")
        if pair.get("needs_decision"):
            lines.append("- **decisão de política pendente**")
        if pair.get("note"):
            lines.append(f"- **nota:** {pair['note']}")
        lines.append("")
    return lines


def print_sheet(payload: dict[str, Any], out: Path) -> None:
    """Writes the sheet next to the labelled set; the text comes from the database, never from the file."""
    ids = [pair["description_id"] for pair in payload["pairs"]]
    columns = resolved_columns(None, None)
    with get_db() as db:
        effective = read_composed_text(db, ids, columns)
        db.rollback()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(sheet_lines(payload, effective)) + "\n", encoding="utf-8")
    logger.success(f"📄 sheet written to {out} ({len(ids)} rows)")


# =============================================================================
# Report
# =============================================================================


def report_for(
    config: BenchConfig,
    scored: Sequence[ScoredRow],
    labelled: int,
    needs_decision: int,
    missing: int,
    out_of_scope: int,
    unread: int,
    seconds_per_document: float,
    min_positives: int,
    predictions: str,
    producers: Counter[str] | None = None,
    blocked: Sequence[str] = (),
) -> dict[str, Any]:
    """Everything the decision needs about one configuration, as data the JSON can carry."""
    types = observed_types(scored)
    metrics = per_type(scored, types, min_positives)
    predicted = type_distribution(scored, "predicted")
    gold = type_distribution(scored, "gold")
    label, share = largest_share(predicted)
    breakdown = boundary_breakdown(scored)
    return {
        "config": config.label,
        "engine": config.engine,
        "preset": config.preset,
        "columns": list(config.columns),
        "engine_config": describe(config),
        "producer_identity": identity_for(config),
        "predictions": predictions,
        "rows": {
            "labelled": labelled,
            "scored": len(scored),
            "needs_decision": needs_decision,
            "missing_from_collection": missing,
            "out_of_scope": out_of_scope,
            "unread": unread,
        },
        "mentions": {
            "gold": sum(gold.values()),
            "predicted": sum(predicted.values()),
            "seconds_per_document": seconds_per_document,
        },
        "agreement": agreement(scored),
        "empty_rate": empty_rate(scored),
        "macro_f1": macro_f1(metrics),
        "measured_types": sum(1 for entry in metrics.values() if entry.label != OVERALL and entry.measured),
        "largest_type": [label, share],
        "entropy_bits": entropy_bits(predicted),
        "distribution": {"gold": dict(gold), "predicted": dict(predicted)},
        "breakdown": dict(breakdown),
        "types": [
            {
                "label": entry.label,
                "support": entry.support,
                "true_positives": entry.true_positives,
                "boundary": entry.boundary,
                "type_confusions": entry.type_confusions,
                "spurious": entry.spurious,
                "precision": entry.precision,
                "recall": entry.recall,
                "relaxed_recall": entry.relaxed_recall,
                "f1": entry.f1,
                "measured": entry.measured,
            }
            for entry in sorted(metrics.values(), key=lambda m: (m.label != OVERALL, -m.support, m.label))
        ],
        "unmeasured": [entry.label for entry in metrics.values() if entry.label != OVERALL and not entry.measured],
        "producers": dict(producers or {}),
        "blocked_gold_terms": list(blocked),
        "notes": [],
        "misses": [
            {
                "description_id": row.description_id,
                "boundary": [f"{g.term} → {p.term}" for g, p in row.match.boundary],
                "type_confusions": [f"{g.term} ({g.type}) → {p.term} ({p.type})" for g, p in row.match.type_confusions],
                "missing": [f"{mention.term} ({mention.type})" for mention in row.match.missing],
                "spurious": [f"{mention.term} ({mention.type})" for mention in row.match.spurious],
            }
            for row in scored
            if not row.correct
        ],
    }


def _f1(report: dict[str, Any]) -> str:
    """
    Macro-F1, or an em dash when no type was measured.

    "0.000" next to "no type was measured" reads like a bad extractor, when the truth is that this
    collection does not have the examples. The dash says which of the two it is.
    """
    return f"{report['macro_f1']:.3f}" if report.get("measured_types") else "—"


def summary_table(reports: Sequence[dict[str, Any]]) -> str:
    """The comparison: one line per configuration, ordered by agreement."""
    lines = [
        "| Configuração | Modo | Concordância | Macro-F1 | Vazio | Maior tipo | Entropia (bits) | s/doc |",
        "| --- | --- | ---: | ---: | ---: | --- | ---: | ---: |",
    ]
    for report in sorted(reports, key=lambda r: -r["agreement"]):
        label, share = report["largest_type"]
        lines.append(
            f"| `{report['config']}` | `{report['predictions']}` | {report['agreement']:.3f} | {_f1(report)} "
            f"| {report['empty_rate']:.3f} | {label} ({share:.0%}) | {report['entropy_bits']:.2f} "
            f"| {report['mentions']['seconds_per_document']:.2f} |"
        )
    return "\n".join(lines)


def detail_lines(report: dict[str, Any]) -> list[str]:
    """Per-configuration detail: the type table, the boundary breakdown and the misses."""
    rows = report["rows"]
    mentions = report["mentions"]
    breakdown = report["breakdown"]
    gold_total = max(1, sum(report["distribution"]["gold"].values()))
    lines = [
        f"### `{report['config']}` · `{report['predictions']}`",
        "",
        f"- motor: `{report['engine_config']}` · colunas: {', '.join(report['columns'])}",
        f"- produtor desta configuração: `{report['producer_identity'][:12]}`",
        f"- linhas: {rows['labelled']} no conjunto, {rows['scored']} pontuadas, "
        + f"{rows['needs_decision']} com `needs_decision` (fora do placar), {rows['missing_from_collection']} ausentes do banco, "
        + f"{rows['out_of_scope']} fora do escopo do worker, {rows['unread']} sem sinal de revisão",
        f"- menções: {mentions['gold']} no gabarito, {mentions['predicted']} preditas · "
        + f"concordância por documento: **{report['agreement']:.3f}** · macro-F1 (tipos medidos): {_f1(report)}",
        f"- documentos sem nenhuma entidade: {report['empty_rate']:.3f} · maior tipo: {report['largest_type'][0]} "
        + f"({report['largest_type'][1]:.0%}) · entropia: {report['entropy_bits']:.2f} bits",
        f"- segundos por documento: {mentions['seconds_per_document']:.2f}",
        "",
    ]

    if report["predictions"] == "stored":
        lines += [
            "> **Modo `stored`:** compara só a **string do termo**, porque `archive_document_entities` é "
            + "`(description_id, entity_id)` e não guarda deslocamento nenhum.",
            "> **A quebra de fronteira abaixo descreve o que está GRAVADO, não esta configuração.** Ela "
            + "vem dos vínculos que uma execução anterior escreveu — as identidades estão logo abaixo, e "
            + "nenhuma delas é necessariamente a pedida. Uma pontuação `stored` não mediu a fronteira "
            + "desta configuração; o modo `live` é o único que mede.",
        ]
    else:
        lines += [
            "> **Modo `live`:** o motor roda sobre o texto composto pelo worker. A quebra de fronteira "
            + "abaixo é medida por **tokens** (um termo contido no outro), não por deslocamento de "
            + "caractere: `ArchiveEntityDTO` carrega `name` e `entity_type`, e nenhum offset.",
        ]
    lines.append("")

    if report["producers"]:
        lines += ["| produtor gravado | documentos |", "| --- | ---: |"]
        lines += [
            f"| `{name[:16]}` | {count} |" for name, count in sorted(report["producers"].items(), key=lambda kv: -kv[1])
        ]
        lines.append("")

    lines += [
        "| Tipo | suporte | precisão | recall | recall frouxo | F1 |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for entry in report["types"]:
        shown = entry["label"] if entry["label"] != OVERALL else "**todos**"
        if entry["measured"] or entry["label"] == OVERALL:
            lines.append(
                f"| {shown} | {entry['support']} | {entry['precision']:.3f} | {entry['recall']:.3f} "
                f"| {entry['relaxed_recall']:.3f} | {entry['f1']:.3f} |"
            )
        else:
            lines.append(f"| {shown} | {entry['support']} | — | — | — | — *(não medida)* |")
    lines += [
        "",
        "O **recall frouxo** conta a quebra de fronteira como acerto e é impresso ao lado do exato, "
        + "nunca no lugar dele: no dia em que a fronteira for corrigida esse é o número que o modelo já "
        + "ganha, e em qualquer outro dia citá-lo sozinho esconderia o defeito.",
    ]
    if report["unmeasured"]:
        lines += [
            f"**Não medidas** (menos de {MIN_POSITIVES} exemplos rotulados): {', '.join(report['unmeasured'])}. "
            + "Estes tipos não existem nesta coleção em quantidade suficiente e o relatório se recusa a "
            + "imprimir um F1 de dois exemplos.",
        ]

    lines += [
        "",
        "| O que aconteceu com o gabarito | menções | do total |",
        "| --- | ---: | ---: |",
        f"| acerto exato | {breakdown.get('hits', 0)} | {breakdown.get('hits', 0) / gold_total:.1%} |",
        f"| **fronteira** (achou, string diferente) | {breakdown.get('boundary', 0)} | {breakdown.get('boundary', 0) / gold_total:.1%} |",
        f"| **tipo trocado** (termo certo, tipo errado) | {breakdown.get('type_confusions', 0)} | {breakdown.get('type_confusions', 0) / gold_total:.1%} |",
        f"| **faltou** (termo não encontrado) | {breakdown.get('missing', 0)} | {breakdown.get('missing', 0) / gold_total:.1%} |",
        f"| sobrou (predito sem gabarito) | {breakdown.get('spurious', 0)} | — |",
        "",
    ]
    if report["predictions"] == "stored" and breakdown.get("boundary"):
        lines += [
            "> As fronteiras acima vêm de uma execução que **não** é a configuração pedida: leia-as como "
            + "a forma do que está gravado, não como medida desta configuração.",
            "",
        ]
    if report["blocked_gold_terms"]:
        lines += [
            f"**{len(report['blocked_gold_terms'])} termo(s) do gabarito estão bloqueados** pela lista de "
            + "stopwords/exclusões do worker e são erro garantido, por decisão da instituição: "
            + f"{', '.join(report['blocked_gold_terms'][:10])}.",
            "",
        ]

    if report["misses"]:
        lines += ["", f"**{len(report['misses'])} documento(s) com discordância**, os primeiros 20:", ""]
        for miss in report["misses"][:20]:
            parts = []
            if miss["boundary"]:
                parts.append("fronteira: " + "; ".join(miss["boundary"]))
            if miss["type_confusions"]:
                parts.append("tipo: " + "; ".join(miss["type_confusions"]))
            if miss["missing"]:
                parts.append("faltou: " + "; ".join(miss["missing"]))
            if miss["spurious"]:
                parts.append("sobrou: " + "; ".join(miss["spurious"]))
            lines.append(f"- `{miss['description_id']}`: " + " · ".join(parts))
        lines += [
            "",
            "_O motor de NER não devolve confiança — `ArchiveEntityDTO` carrega `name` e "
            + "`entity_type` —, então a discordância é listada pelo que aconteceu e não por um score._",
        ]
    lines.append("")
    return lines


def print_report(reports: Sequence[dict[str, Any]]) -> None:
    """Prints the comparison first and the detail after, so the table is the answer and not a preface."""
    print()
    print(summary_table(reports))
    print()
    for report in reports:
        print("\n".join(detail_lines(report)))


# =============================================================================
# CLI
# =============================================================================


def _today() -> str:
    return date.today().isoformat()


def run_propose(out: Path, sheet_out: Path, seed: str, per_type: int, empty_rows: int, force: bool) -> int:
    """Reads the stored extraction, proposes the sample and writes the skeleton and its sheet."""
    with get_db() as db:
        candidates = read_candidates(db, per_type, empty_rows, seed)
        total = int(db.scalar(select(func.count()).select_from(ArchiveDocument).where(ai_writable_documents())) or 0)
        db.rollback()

    if not candidates:
        raise SystemExit(
            "Nenhum documento elegível para propor: a coleção não tem descrição gravada que o worker "
            "possa ler. Sem acervo não há o que corrigir."
        )

    payload = build_payload(candidates, seed, per_type, empty_rows)
    payload["collection"] = (
        f"{settings.DB_NAME} — {total} documento(s) elegíveis em archive_documents (fora do escopo do "
        f"worker excluídos); proposto em {_today()}."
    )
    write_skeleton(out, payload, force)

    for bucket in [*ENTITY_TYPES, NO_TYPE]:
        count = sum(1 for candidate in candidates if candidate.proposed_by == bucket)
        logger.info(f"   {bucket:<10} {count:>3} propostos")
    print_sheet(payload, sheet_out)
    return 0


def run_sheet(pairs: Path, sheet_out: Path) -> int:
    """Regenerates the sheet from the labelled set already on disk."""
    print_sheet(load_payload(pairs), sheet_out)
    return 0


def run_score(args: argparse.Namespace) -> int:
    """Scores every requested configuration against the labelled set and prints the comparison."""
    default_columns = resolved_columns(None, None)
    configs = [parse_config(text, tuple(default_columns)) for text in args.config]

    with get_db() as db:
        rows, payload = load_labelled(args.pairs, args.allow_draft)
        if args.status:
            logger.info(f"📄 {args.pairs} · {payload.get('status', '')}")

        scored_rows, unread, needs_decision = scorable_rows(rows)
        if unread:
            logger.warning(
                f"⚠️ {len(unread)} linha(s) não têm 'confidence' nem 'note': ninguém as leu, e elas saem do "
                f"placar em vez de pontuar o modelo contra a própria resposta (primeiras: {unread[:3]})."
            )
        if not scored_rows:
            raise SystemExit(
                f"Nenhuma linha pontuável em {args.pairs}: {len(unread)} sem 'confidence'/'note' e "
                f"{needs_decision} marcadas 'needs_decision'. Corrija as linhas e escreva a sua certeza — "
                "sem isso o placar mediria o modelo contra a resposta que ele mesmo escreveu."
            )

        # The worker's own document selection, minus the stamp: a document it will never read cannot
        # be scored against it, and leaving one in would read as a model failure that never happened.
        in_scope = worker_scope_ids(db, [row.description_id for row in scored_rows])
        present = {
            description_id
            for (description_id,) in db.execute(
                select(ArchiveDocument.description_id).where(
                    ArchiveDocument.description_id.in_([row.description_id for row in scored_rows])
                )
            ).all()
        }
        absent = [row for row in scored_rows if row.description_id not in present]
        if absent:
            logger.warning(f"⚠️ {len(absent)} linha(s) do gabarito não existem mais na coleção e saem do placar.")
        out_of_scope = [
            row for row in scored_rows if row.description_id in present and row.description_id not in in_scope
        ]
        if out_of_scope:
            logger.warning(
                f"⚠️ {len(out_of_scope)} linha(s) estão fora do escopo do worker (HUMAN_APPROVED ou sem texto "
                "nas colunas lidas) e saem do placar: o worker nunca as leria."
            )
        scoreable = [row for row in scored_rows if row.description_id in in_scope]

        blocked = blocked_gold_terms(db, scoreable)
        if blocked:
            logger.warning(
                f"⚠️ {len(blocked)} termo(s) do gabarito estão na lista de bloqueio do worker: são erro "
                "garantido por decisão da instituição."
            )

        reports: list[dict[str, Any]] = []
        engines: dict[str, Any] = {}
        for config in configs:
            producers: Counter[str] | None = None
            if args.predictions == "stored":
                scored = score_stored(db, scoreable)
                seconds = 0.0
                producers = stored_producers(db, [row.description_id for row in scoreable])
            else:
                to_score = min(len(scoreable), args.limit) if args.limit else len(scoreable)
                logger.info(f"🧠 {config.label}: carregando o motor e extraindo de {to_score} documento(s)...")
                # One model per configuration: the load is the run's cost, and charging it to every
                # configuration would inflate the seconds per document the report prints.
                if config.engine not in engines:
                    engines[config.engine] = build_engine(db, config)
                scored, seconds = score_live(db, config, scoreable, limit=args.limit, engine=engines[config.engine])
            reports.append(
                report_for(
                    config,
                    scored,
                    labelled=len(rows),
                    needs_decision=needs_decision,
                    missing=len(absent),
                    out_of_scope=len(out_of_scope),
                    unread=len(unread),
                    seconds_per_document=seconds,
                    min_positives=args.min_positives,
                    predictions=args.predictions,
                    producers=producers,
                    blocked=blocked,
                )
            )
        db.rollback()

    print_report(reports)

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(
                {"mode": args.predictions, "measured_at": _today(), "reports": reports}, ensure_ascii=False, indent=2
            )
            + "\n",
            encoding="utf-8",
        )
        logger.success(f"💾 relatório escrito em {args.json}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="The NER bench: propose the set from the stored run, then score it.")
    parser.add_argument(
        "--propose",
        action="store_true",
        help="Propose rows from the stored extraction and write the skeleton and its sheet.",
    )
    parser.add_argument("--sheet", action="store_true", help="Regenerate the human sheet from the labelled set.")
    parser.add_argument("--out", type=Path, default=DATA_DIR / PAIRS_FILENAME, help="Where the labelled set lives.")
    parser.add_argument("--sheet-out", type=Path, default=DATA_DIR / SHEET_FILENAME, help="Where the sheet goes.")
    parser.add_argument("--seed", default=DEFAULT_SEED, help="Ordering seed of the proposal; recorded in the file.")
    parser.add_argument("--per-type", type=int, default=DEFAULT_PER_TYPE, help="Rows proposed per entity type.")
    parser.add_argument(
        "--empty-rows",
        type=int,
        default=DEFAULT_EMPTY_ROWS,
        help="Rows proposed from the documents with no stored entity, so recall has a denominator.",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite an existing set (discards corrections).")
    parser.add_argument("--pairs", type=Path, default=None, help="The labelled set to score (default: --out).")
    parser.add_argument(
        "--config",
        action="append",
        default=[],
        metavar="ENGINE[:PRESET[:COLUMNS]]",
        help="A configuration to score; repeat it to compare. Default: the worker's own.",
    )
    parser.add_argument(
        "--predictions",
        choices=("live", "stored"),
        default="live",
        help="live runs the engine; stored scores the links the last run wrote (free, whole collection).",
    )
    parser.add_argument("--limit", type=int, default=None, help="Cap the documents the live model sees, for a trial.")
    parser.add_argument("--min-positives", type=int, default=MIN_POSITIVES, help="Below this, a type is 'não medida'.")
    parser.add_argument("--allow-draft", action="store_true", help="Score a set whose 'status' is still draft.")
    parser.add_argument("--status", action="store_true", help="Print the set's status line before scoring.")
    parser.add_argument("--json", type=Path, default=None, help="Also write the raw report here.")
    args = parser.parse_args(argv)

    if args.pairs is None:
        args.pairs = args.out
    if args.propose:
        return run_propose(args.out, args.sheet_out, args.seed, args.per_type, args.empty_rows, args.force)
    if args.sheet:
        return run_sheet(args.out, args.sheet_out)
    if not args.config:
        args.config = [worker_default_config()]
    return run_score(args)


if __name__ == "__main__":
    raise SystemExit(main())
