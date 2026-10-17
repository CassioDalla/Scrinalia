"""
The ranking arithmetic the retrieval benches score with.

Hit@k, recall@k and the reciprocal rank are defined **once**, here, because two benches report
them — the excerpt bench and the mode bench — and two spellings of "the metric" would let the same
run be reported with two different numbers, which is the one thing a measurement must not do.

Nothing here touches a database or a model: it takes the ids a ranking produced and the ids the
labelled set expects, so it is unit-testable without either.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class QueryMetrics:
    """What one labelled query scored, for one ranking."""

    #: 1.0 when any expected id is inside the first ``k`` positions, else 0.0.
    hit: float
    #: Fraction of the expected ids found inside the first ``k`` positions.
    recall: float
    #: ``1 / position`` of the first expected id anywhere in the ranking handed in, else 0.0.
    reciprocal_rank: float
    #: 1.0 when any expected id is anywhere in the ranking handed in, else 0.0.
    covered: float


def query_metrics(expected: set[str], ranking: list[str], k: int) -> QueryMetrics:
    """
    Scores one ranking against the ids the labelled set expects.

    ``hit`` is the metric that answers "did the search find it at all"; ``recall`` says how much
    of the expected set it found, which matters when a query expects several descriptions;
    ``reciprocal_rank`` is the position of the first expected id **anywhere in the ranking the
    caller handed in**, so the caller decides how deep the ranking was cut and the metric cannot
    silently disagree with it. ``covered`` is the same question as ``hit`` without the cut, which
    is what separates "ranked low" from "not reachable at all" — the difference between a ranking
    problem and a coverage problem.

    An empty expected set scores zero instead of dividing by it: the callers are labelled sets,
    and a row without a verdict is a row the bench counts apart rather than scores.
    """
    top = ranking[:k]
    found = expected.intersection(top)
    return QueryMetrics(
        hit=1.0 if found else 0.0,
        recall=len(found) / len(expected) if expected else 0.0,
        reciprocal_rank=next(
            (1.0 / (position + 1) for position, description_id in enumerate(ranking) if description_id in expected),
            0.0,
        ),
        covered=1.0 if expected.intersection(ranking) else 0.0,
    )


@dataclass
class RankingScore:
    """
    Accumulates one method's queries and summarises them.

    The average is over the queries that were asked, so a method that answers nothing still gets a
    zero instead of a shorter list that flatters it.
    """

    hits: list[float] = field(default_factory=list)
    recalls: list[float] = field(default_factory=list)
    reciprocal_ranks: list[float] = field(default_factory=list)
    coverages: list[float] = field(default_factory=list)
    seconds: float = 0.0

    def add(self, expected: set[str], ranking: list[str], k: int) -> None:
        measured = query_metrics(expected, ranking, k)
        self.hits.append(measured.hit)
        self.recalls.append(measured.recall)
        self.reciprocal_ranks.append(measured.reciprocal_rank)
        self.coverages.append(measured.covered)

    def summary(self, k: int) -> dict[str, float]:
        total = max(1, len(self.hits))
        return {
            f"hit_rate@{k}": sum(self.hits) / total,
            f"recall@{k}": sum(self.recalls) / total,
            "mrr": sum(self.reciprocal_ranks) / total,
            "coverage": sum(self.coverages) / total,
            "seconds": self.seconds,
            "queries": float(len(self.hits)),
        }
