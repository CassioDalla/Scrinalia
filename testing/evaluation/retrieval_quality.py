"""
Retrieval-quality benchmark for the embedded text (Fase 3.5-B).

Measures the same labelled queries against the same collection **before** and **after**
subtracting the excerpts the curation catalogue would remove, so the claim "removing the
boilerplate improves retrieval" is a number instead of an intuition.

Nothing is written: the excerpts are recomputed in memory from the collection and the
after-text comes from a SQL expression that is never persisted. The before-text is the
composition that ``worker_embedding`` used before this phase (human title or original,
then scope, administrative history and provenance), reproduced here on purpose so the
baseline does not move with the production code.

Run it from the repository root, against a real database and the real model:

    uv run python -m testing.evaluation.retrieval_quality --min-ratio 0.05 --k 10

Relevance is **derived from the title** (see ``retrieval_pairs.json``): the metric is a
proxy, honest about being one. It exists to compare two rankings, not to crown a model.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from sqlalchemy import ColumnElement, func, select

from memoria_curitibana.core.database import get_db
from memoria_curitibana.core.logger import logger
from memoria_curitibana.domains.archive.domain.text_quality import (
    AI_TEXT_COLUMNS,
    ExcerptSuggestionAggregator,
)
from memoria_curitibana.domains.archive.models import ArchiveDocument
from memoria_curitibana.domains.archive.repository.text_quality_repo import (
    ExcerptRule,
    TextQualityRepository,
    embedding_text_sql,
)

PAIRS_PATH = Path(__file__).parent / "retrieval_pairs.json"
EMBED_BATCH_SIZE = 128


@dataclass
class RankingMetrics:
    """Ranking quality of one method over the labelled set."""

    name: str
    hits: int = 0
    recalls: list[float] = field(default_factory=list)
    reciprocal_ranks: list[float] = field(default_factory=list)
    term_precisions: list[float] = field(default_factory=list)

    def add(self, expected: set[str], ranking: list[str], k: int, term_matches: dict[str, bool]) -> None:
        top = ranking[:k]
        self.hits += 1 if expected.intersection(top) else 0
        self.recalls.append(len(expected.intersection(top)) / len(expected))
        # Precision by title term is label-free: it does not depend on how many matching
        # documents the labelled set happened to keep, so it cannot punish a ranking for
        # surfacing an equally relevant document that the cut-off left out.
        self.term_precisions.append(sum(term_matches.get(description_id, False) for description_id in top) / max(1, k))
        for position, description_id in enumerate(ranking, start=1):
            if description_id in expected:
                self.reciprocal_ranks.append(1.0 / position)
                break
        else:
            self.reciprocal_ranks.append(0.0)

    def summary(self) -> dict[str, float]:
        total = max(1, len(self.recalls))
        return {
            "hit_rate": self.hits / total,
            "recall": sum(self.recalls) / total,
            "mrr": sum(self.reciprocal_ranks) / total,
            "term_precision": sum(self.term_precisions) / total,
        }


def baseline_text_sql() -> ColumnElement[str]:
    """The embedded text as it was produced before the excerpt catalogue existed."""
    title = func.coalesce(
        func.nullif(func.btrim(ArchiveDocument.final_title), ""),
        func.btrim(ArchiveDocument.original_title),
    )
    columns = ("scope_content", "admin_bio_history", "provenance")
    parts: list[ColumnElement[str]] = [func.nullif(title, "")]
    parts.extend(func.nullif(func.btrim(getattr(ArchiveDocument, column)), "") for column in columns)
    return func.concat_ws("\n", *parts)


def suggest_rules(db, min_ratio: float, min_documents: int = 5, scope: str = "EMBEDDING") -> list[ExcerptRule]:
    """Recomputes the catalogue candidates in memory; nothing is approved or stored."""
    repository = TextQualityRepository(db)
    documents = repository.count_documents(list(AI_TEXT_COLUMNS))
    min_count = max(min_documents, math.ceil(min_ratio * documents))

    aggregator = ExcerptSuggestionAggregator()
    for description_id, column, value in repository.iter_text_columns(list(AI_TEXT_COLUMNS)):
        if value:
            aggregator.observe(description_id, column, value)

    rules = []
    for candidate in aggregator.candidates(min_count=min_count):
        # Only the excerpts whose scope includes the consumer being measured. A title
        # template is proposed for TITLE, so it never reaches the embedded vector.
        if scope not in candidate.scope:
            continue
        matchers = tuple(dict.fromkeys([candidate.text, *candidate.variants]))
        rules.append(ExcerptRule(matchers=matchers, replacement=""))
    return rules


def collect_texts(db, rules: list[ExcerptRule]) -> tuple[list[str], list[str], list[str], dict[str, str]]:
    """Streams ids plus the before/after text of every document, straight from PostgreSQL."""
    ids: list[str] = []
    before: list[str] = []
    after: list[str] = []
    titles: dict[str, str] = {}

    stmt = (
        select(
            ArchiveDocument.description_id,
            ArchiveDocument.original_title,
            baseline_text_sql().label("before_text"),
            embedding_text_sql(rules).label("after_text"),
        )
        .where(ArchiveDocument.review_status != "REJECTED")
        .order_by(ArchiveDocument.description_id)
    )
    for row in db.execute(stmt).yield_per(500):
        mapping = row._mapping
        ids.append(mapping["description_id"])
        titles[mapping["description_id"]] = mapping["original_title"] or ""
        before.append(mapping["before_text"] or "")
        after.append(mapping["after_text"] or "")

    return ids, before, after, titles


def embed_all(engine, texts: list[str]) -> np.ndarray:
    vectors: list[list[float]] = []
    for start in range(0, len(texts), EMBED_BATCH_SIZE):
        vectors.extend(engine.embed(texts[start : start + EMBED_BATCH_SIZE]))
    matrix = np.asarray(vectors, dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    return matrix / np.clip(norms, 1e-12, None)


def rank(matrix: np.ndarray, ids: list[str], query_vector: np.ndarray, top: int) -> list[str]:
    similarities = matrix @ query_vector
    order = np.argsort(-similarities)[:top]
    return [ids[index] for index in order]


def mean_pairwise_cosine(matrix: np.ndarray, samples: int = 20000) -> float:
    """
    Average similarity of random document pairs: the "separation" the roadmap measured.

    A shared block pushes every vector together, so this number falls when the boilerplate
    is removed. It is reported next to the ranking metrics on purpose, because the two can
    move in opposite directions and only the second one is what a user feels.
    """
    generator = np.random.default_rng(0)
    index = generator.integers(0, len(matrix), size=(samples, 2))
    return float(np.mean(np.sum(matrix[index[:, 0]] * matrix[index[:, 1]], axis=1)))


def run(
    min_ratio: float,
    k: int,
    top: int,
    sample: int,
    only: str | None = None,
    exclude: list[str] | None = None,
    scope: str = "EMBEDDING",
) -> dict:
    pairs = json.loads(PAIRS_PATH.read_text(encoding="utf-8"))["pairs"]

    from memoria_curitibana.domains.archive.engines.embeddings.registry import get_engine

    logger.info("Loading the real embedding model...")
    engine = get_engine("sentence_transformer", preset="multilingual_minilm")

    with get_db() as db:
        rules = suggest_rules(db, min_ratio=min_ratio, scope=scope)
        if only:
            # Ablation: keep a single excerpt family, to attribute the effect instead of
            # assuming the whole set behaves like one.
            rules = [rule for rule in rules if any(only.lower() in matcher.lower() for matcher in rule.matchers)]
            logger.info(f"Ablation active: {len(rules)} excerpt family(ies) match {only!r}.")
        for pattern in exclude or []:
            rules = [rule for rule in rules if not any(pattern.lower() in matcher.lower() for matcher in rule.matchers)]
        logger.info(f"{len(rules)} excerpt(s) would be applied; {sum(len(rule.matchers) for rule in rules)} spellings.")
        ids, before_texts, after_texts, titles = collect_texts(db, rules)

    logger.info(f"Embedding {len(ids)} documents twice (before/after)...")
    before_matrix = embed_all(engine, before_texts)
    after_matrix = embed_all(engine, after_texts)

    before_metrics = RankingMetrics(name="before (raw text)")
    after_metrics = RankingMetrics(name="after (excerpts removed)")
    examples: list[dict] = []

    for pair in pairs:
        expected = set(pair["expected_document_ids"])
        term = pair["title_term"].lower()
        term_matches = {description_id: term in title.lower() for description_id, title in titles.items()}
        query_vector = np.asarray(engine.embed([pair["query"]])[0], dtype=np.float32)
        query_vector = query_vector / max(float(np.linalg.norm(query_vector)), 1e-12)

        before_ranking = rank(before_matrix, ids, query_vector, top)
        after_ranking = rank(after_matrix, ids, query_vector, top)
        before_metrics.add(expected, before_ranking, k, term_matches)
        after_metrics.add(expected, after_ranking, k, term_matches)
        examples.append(
            {
                "query": pair["query"],
                "title_term": pair["title_term"],
                "expected": sorted(expected),
                "before_top": before_ranking[:sample],
                "after_top": after_ranking[:sample],
                "before_term_precision": sum(term_matches[i] for i in before_ranking[:k]) / k,
                "after_term_precision": sum(term_matches[i] for i in after_ranking[:k]) / k,
            }
        )

    return {
        "documents": len(ids),
        "k": k,
        "min_ratio": min_ratio,
        "scope": scope,
        "excerpts": [list(rule.matchers) for rule in rules],
        "mean_pairwise_cosine": {
            "before": mean_pairwise_cosine(before_matrix),
            "after": mean_pairwise_cosine(after_matrix),
        },
        "before": before_metrics.summary(),
        "after": after_metrics.summary(),
        "queries": len(pairs),
        "examples": examples,
    }


def to_markdown(report: dict) -> str:
    before, after = report["before"], report["after"]
    cosine = report["mean_pairwise_cosine"]
    lines = [
        "| Métrica | Antes | Depois | Δ |",
        "| --- | --- | --- | --- |",
        f"| Similaridade média entre pares (separação — menor é melhor) | {cosine['before']:.3f} | {cosine['after']:.3f} | {cosine['after'] - cosine['before']:+.3f} |",
        f"| Hit@{report['k']} | {before['hit_rate']:.3f} | {after['hit_rate']:.3f} | {after['hit_rate'] - before['hit_rate']:+.3f} |",
        f"| Recall@{report['k']} | {before['recall']:.3f} | {after['recall']:.3f} | {after['recall'] - before['recall']:+.3f} |",
        f"| MRR | {before['mrr']:.3f} | {after['mrr']:.3f} | {after['mrr'] - before['mrr']:+.3f} |",
        f"| Precisão@{report['k']} por termo do título | {before['term_precision']:.3f} | {after['term_precision']:.3f} | {after['term_precision'] - before['term_precision']:+.3f} |",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Before/after retrieval quality of the embedded text.")
    parser.add_argument("--min-ratio", type=float, default=0.05, help="Frequency floor of the suggestion run.")
    parser.add_argument("--k", type=int, default=10, help="Cut-off used by hit@k and recall@k.")
    parser.add_argument("--top", type=int, default=50, help="How many documents are ranked per query.")
    parser.add_argument("--sample", type=int, default=5, help="Top ids printed per query.")
    parser.add_argument("--json", type=str, default=None, help="Also write the raw report to this path.")
    parser.add_argument(
        "--only", type=str, default=None, help="Ablation: keep only excerpts whose spelling contains this text."
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=None,
        help="Ablation: drop excerpts whose spelling contains this text (can be repeated).",
    )
    parser.add_argument(
        "--scope",
        type=str,
        default="EMBEDDING",
        choices=["EMBEDDING", "NER", "TITLE"],
        help="Which consumer the after-text is composed for.",
    )
    args = parser.parse_args(argv)

    report = run(
        min_ratio=args.min_ratio,
        k=args.k,
        top=args.top,
        sample=args.sample,
        only=args.only,
        exclude=args.exclude,
        scope=args.scope,
    )

    print(
        f"\nDocuments: {report['documents']} · queries: {report['queries']} · excerpts applied: {len(report['excerpts'])}"
    )
    for matchers in report["excerpts"]:
        print(f"  · {matchers[0][:70]!r}" + (f" (+{len(matchers) - 1} variantes)" if len(matchers) > 1 else ""))
    print()
    print(to_markdown(report))
    print()
    for example in report["examples"]:
        print(
            f"«{example['query']}» termo={example['title_term']!r} "
            f"precisão@k antes={example['before_term_precision']:.2f} depois={example['after_term_precision']:.2f}"
        )
        print(f"   esperados={example['expected']}")
        print(f"   antes : {example['before_top']}")
        print(f"   depois: {example['after_top']}")

    if args.json:
        Path(args.json).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
