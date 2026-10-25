"""The typology metric: one definition for the bench and for the panel's trial (ADR 0018, #71).

The arithmetic that turns a list of ``(truth, prediction)`` into a number used to live only in the
bench under ``testing/evaluation``. The panel now shows the same numbers for an institution's own
collection, and a second copy of ``agreement`` or of the ``score > threshold`` rule would let the
screen and the bench drift into two answers to the same question (principle IV). So the primitives
live here, the bench imports them, and the trial executor writes its result with them.

The model and the database are exercised elsewhere on purpose: this module is pure and a unit test
can pin its arithmetic without a GPU.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

#: Below this many labelled positives a class's F1 is noise wearing a number's clothes, and a report
#: says "não medida" instead. Measured on the reference collection: five typologies have two examples
#: or none at all, and a "F1 = 1.000" built on two rows would be quoted as if it meant something.
MIN_POSITIVES = 5

#: The class of "this description has no typology at all". It is not a typology and the catalogue
#: does not name it: it is the bucket that turns "the model abstained" into a measured false
#: positive instead of an invisible one.
NONE_CLASS = "NENHUMA"

#: The bucket a prediction falls into when the classifier refuses to answer. It is not a typology:
#: it is the outcome the confidence floor produces, and it belongs in the distribution because a
#: model that abstains on everything must not look like a model with a clean spread.
ABSTAINED = "(abstained)"


@dataclass(frozen=True)
class Truth:
    """What the curator said about one row: one label, several acceptable ones, or none at all."""

    labels: frozenset[str] | None

    @property
    def is_none(self) -> bool:
        """``None`` is the NENHUMA class: no typology applies, so abstaining is the right answer."""
        return self.labels is None


@dataclass(frozen=True)
class Prediction:
    """What the classifier answered, and with how much confidence."""

    label: str | None
    score: float | None = None


@dataclass(frozen=True)
class Scored:
    """One labelled row after the classifier answered it."""

    description_id: str
    truth: Truth
    prediction: Prediction

    @property
    def key(self) -> str:
        """The predicted bucket, with the abstention named instead of dropped."""
        return self.prediction.label or ABSTAINED

    @property
    def truth_key(self) -> str:
        """The gabarito as one cell of the confusion matrix; a list of acceptable names is joined."""
        if self.truth.is_none:
            return NONE_CLASS
        return " | ".join(sorted(self.truth.labels or ()))

    @property
    def correct(self) -> bool:
        """
        Agreement with the gabarito.

        A row the curator marked NENHUMA is right exactly when the classifier abstained, and a row
        with a list of acceptable names is right when the answer is any of them. Both rules exist
        because the catalogue mixes support and species; without them a legitimate answer would be
        scored as an error.
        """
        if self.truth.is_none:
            return self.prediction.label is None
        return self.prediction.label in (self.truth.labels or frozenset())


@dataclass
class ClassMetrics:
    """Precision, recall and F1 of one typology, over the rows the curator labelled."""

    label: str
    support: int = 0
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    min_positives: int = MIN_POSITIVES

    @property
    def measured(self) -> bool:
        return self.support >= self.min_positives

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


def agreement(rows: Sequence[Scored]) -> float:
    """Share of the scored rows the classifier got right."""
    return sum(1 for row in rows if row.correct) / len(rows) if rows else 0.0


def distribution(rows: Sequence[Scored]) -> Counter[str]:
    """How many rows each predicted bucket took — the collapse, as a number."""
    return Counter(row.key for row in rows)


def confusion(rows: Sequence[Scored]) -> Counter[tuple[str, str]]:
    """``(gabarito, predito)`` counts, so a systematic confusion is visible and not only its total."""
    return Counter((row.truth_key, row.key) for row in rows)


def entropy_bits(counts: Counter[str]) -> float:
    """
    Shannon entropy of the predicted buckets, in bits.

    Over the buckets **including** the abstention, because abstaining is an outcome and a model that
    abstains on everything should not look concentrated. ``largest_share`` is the same symptom
    without the logarithm.
    """
    total = sum(counts.values())
    if total <= 0:
        return 0.0
    # ``max(0.0, ...)`` is not decoration: one bucket gives ``-0.0``, and "-0.00 bits" in a report
    # reads like a bug in the metric rather than a perfectly concentrated answer.
    return max(0.0, -sum((count / total) * math.log2(count / total) for count in counts.values() if count > 0))


def largest_share(counts: Counter[str]) -> tuple[str, float]:
    """The biggest predicted bucket and its share: the one number that denounces a collapse."""
    total = sum(counts.values())
    if not counts or total <= 0:
        return ("", 0.0)
    label, count = counts.most_common(1)[0]
    return (label, count / total)


def abstention_rate(rows: Sequence[Scored]) -> float:
    """Share of the scored rows the classifier refused to label."""
    return abstention_rate_of([row.prediction for row in rows])


def abstention_rate_of(predictions: Sequence[Prediction]) -> float:
    """
    Share of the answers that were abstentions.

    The trial measures a random sample that has no truth to score, so it has predictions and not
    ``Scored`` rows; the arithmetic is the same one :func:`abstention_rate` uses, not a second rule.
    """
    return sum(1 for prediction in predictions if prediction.label is None) / len(predictions) if predictions else 0.0


def per_class(
    rows: Sequence[Scored], labels: Sequence[str], min_positives: int = MIN_POSITIVES
) -> dict[str, ClassMetrics]:
    """
    Precision, recall and F1 per typology, with the any-of truth treated as multi-label.

    A row whose gabarito is ``["Mapa / Croqui Urbanístico", "Planta Arquitetônica"]`` and whose answer
    is Planta gives Planta a true positive and Mapa a false negative: both readings are true at once,
    and collapsing them into one column would hide which of the two the model can find.
    """
    metrics = {label: ClassMetrics(label=label, min_positives=min_positives) for label in labels}
    for row in rows:
        truth = row.truth.labels or frozenset()
        predicted = row.prediction.label
        for label in truth:
            if label not in metrics:
                continue  # the curator named a typology the active catalogue no longer has
            metrics[label].support += 1
            if predicted == label:
                metrics[label].true_positives += 1
            else:
                metrics[label].false_negatives += 1
        if predicted is not None and predicted in metrics and predicted not in truth:
            metrics[predicted].false_positives += 1
    return metrics


def macro_f1(metrics: dict[str, ClassMetrics]) -> float:
    """Mean F1 over the **measured** classes only: an unmeasured class is absent, not zero."""
    measured = [metric.f1 for metric in metrics.values() if metric.measured]
    return sum(measured) / len(measured) if measured else 0.0


def link_decision(result: dict, threshold: float, lookup: Mapping[str, str] | None = None) -> Prediction:
    """
    The worker's decision about one answer, in one place.

    ``worker_typology.execute`` links a typology only when ``score > confidence_threshold`` —
    strictly — and leaves ``typology_id`` NULL otherwise. The scorer, the collection sample and the
    panel's trial read the rule from here, because a second copy of the comparison is a second
    abstention rate, and the one the report prints would stop being the one the worker produces
    (principle IV).

    ``lookup`` translates the label the model echoed back into the catalogue name, which is what a
    label format requires: the engine answers with the label it was handed, and the gabarito is
    written in catalogue names. Without it every row of a formatted run scores as a miss. The worker
    makes the same translation with the same shape of dictionary (``{label: id}``).
    """
    echoed = result["labels"][0]
    label = lookup.get(echoed, echoed) if lookup is not None else echoed
    score = float(result["scores"][0])
    return Prediction(label=label if score > threshold else None, score=score)
