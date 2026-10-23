"""
Retrieval-quality benchmark of the three ranking modes (issue #38).

It answers one question: which ranking finds the labelled descriptions — the full-text one, the
semantic one, or the fusion of the two? It runs through **the product path** (``DocumentService``
and the repository, the same objects the route uses) and not against a re-implementation in numpy:
a bench that embedded and ranked on its own would score a second definition of the search and could
disagree with the route it claims to measure. ``retrieval_quality.py`` answers a different question
— whether subtracting the curated excerpts improves the embedded text — and there embedding on its
own is the point, because the text is the variable.

The labelled set is sixteen queries whose gold is derived from the title term, asked twice: as the
sentence a person types and as the term alone. Both are reported apart because they disagree — one
is the semantic arm's case and the other the full-text arm's — and an average over the two would
describe neither.

**Its size is the limit of the evidence.** One query is worth 0.0625 of Hit@10, so the set separates
the modes only when they differ by more than a query or two, and the gold being derived from the
title is a proxy for relevance, not a human verdict about it. The report prints the number of
queries next to every number it prints, on purpose.

    uv run python -m testing.evaluation.retrieval_modes --k 10 --depth 50 --json <destino>
"""

from __future__ import annotations

import argparse
import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from scrinalia.core.database import create_session
from scrinalia.core.logger import logger
from scrinalia.domains.archive.engines.base import EmbeddingEngine
from scrinalia.domains.archive.repository.document_repo import DocumentRepository
from scrinalia.domains.archive.schemas.query_schema import DocumentSearchQuery, SearchMode
from scrinalia.domains.archive.services.document_service import DocumentService
from testing.evaluation.dataset import load_dataset
from testing.evaluation.ranking_metrics import RankingScore

#: The rankings the route exposes, in the order the report prints them. ``lexical`` first because it
#: is the default, so a reader compares everything against the mode an archivist gets without asking.
MODES: tuple[SearchMode, ...] = ("lexical", "semantic", "hybrid")

#: The two formulations of the same labelled query. ``sentence`` is what a person types when they do
#: not know the vocabulary of the fonds; ``term`` is what they type when they do, and it is the case
#: the full-text ranking was built for. Reading one without the other is how a mode gets called
#: better than it is.
STRATA: tuple[tuple[str, Callable[[dict[str, Any]], str]], ...] = (
    ("sentence", lambda pair: pair["query"]),
    ("term", lambda pair: pair["title_term"]),
)


def _embedder() -> EmbeddingEngine:
    """
    The engine the API injects, imported the way ``provide_embedding_engine`` imports it.

    Inside the function on purpose: importing the embedding registry pulls the model libraries, and
    a bench that measured only the full-text mode must not pay for them.
    """
    from scrinalia.domains.archive.engines.embeddings.registry import get_engine

    return get_engine("sentence_transformer", preset="multilingual_minilm")


def _warm_up(service: DocumentService) -> None:
    """
    Pays the model load once, before anything is timed.

    Without it the first semantic query of the run carries the load and the mode that happens to be
    measured first looks slower than the others — a measurement artefact, not a property of the
    ranking. One throwaway query is the price of comparing the modes instead of the import order.
    """
    logger.info("Loading the real embedding model...")
    service.search(DocumentSearchQuery(term="aquecimento", mode="semantic", limit=1))


def run(k: int, depth: int) -> dict[str, Any]:
    """Scores every mode over every stratum, through the service the route uses."""
    document = load_dataset("retrieval_pairs.json")
    pairs = document["pairs"]

    with create_session() as db:
        service = DocumentService(DocumentRepository(db), embedder=_embedder)
        _warm_up(service)

        strata: dict[str, Any] = {}
        per_query: dict[str, list[dict[str, Any]]] = {}
        for stratum, term_of in STRATA:
            scores = {mode: RankingScore() for mode in MODES}
            queries: list[dict[str, Any]] = []
            for pair in pairs:
                term = term_of(pair)
                expected = set(pair["expected_document_ids"])
                positions: dict[str, int | None] = {}
                for mode in MODES:
                    started = time.perf_counter()
                    page = service.search(DocumentSearchQuery(term=term, mode=mode, limit=depth))
                    scores[mode].seconds += time.perf_counter() - started
                    ranking = [item.description_id for item in page.items]
                    scores[mode].add(expected, ranking, k)
                    positions[mode] = next(
                        (
                            position
                            for position, description_id in enumerate(ranking, start=1)
                            if description_id in expected
                        ),
                        None,
                    )
                queries.append({"term": term, "positions": positions})
            strata[stratum] = {mode: scores[mode].summary(k) for mode in MODES}
            per_query[stratum] = queries

    return {
        "k": k,
        "depth": depth,
        "queries": len(pairs),
        "modes": list(MODES),
        "strata": list(strata),
        # The set's own note about where it was built, quoted and not measured: it is collection
        # data and it goes stale, which is exactly why it is not used as the name of this run.
        "set_declares": document.get("collection"),
        "scores": strata,
        "per_query": per_query,
    }


def to_markdown(report: dict[str, Any]) -> str:
    """The report as the table that goes into the issue and the log."""
    k, depth = report["k"], report["depth"]
    lines = [
        f"{report['queries']} labelled queries · cut-off {k} · ranking depth {depth} · "
        f"the set declares: {report['set_declares']}",
        "",
    ]
    for stratum in report["strata"]:
        lines.append(f"**{stratum}**")
        lines.append("")
        lines.append(f"| mode | Hit@{k} | Recall@{k} | MRR | found in top-{depth} | s/query |")
        lines.append("| --- | ---: | ---: | ---: | ---: | ---: |")
        for mode in report["modes"]:
            score = report["scores"][stratum][mode]
            lines.append(
                f"| {mode} | {score[f'hit_rate@{k}']:.3f} | {score[f'recall@{k}']:.3f} | {score['mrr']:.3f} | "
                f"{score['coverage']:.3f} | {score['seconds'] / max(1.0, score['queries']):.2f} |"
            )
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Which ranking mode answers the labelled queries better.")
    parser.add_argument("--k", type=int, default=10, help="Cut-off used by hit@k and recall@k.")
    parser.add_argument("--depth", type=int, default=50, help="How many documents each mode returns per query.")
    parser.add_argument("--json", type=str, default=None, help="Also write the raw report to this path.")
    args = parser.parse_args(argv)

    report = run(k=args.k, depth=args.depth)
    print()
    print(to_markdown(report))
    for stratum in report["strata"]:
        print(f"--- {stratum}: position of the first expected description")
        for query in report["per_query"][stratum]:
            positions = " ".join(
                f"{mode}={query['positions'][mode] if query['positions'][mode] is not None else '-'}"
                for mode in report["modes"]
            )
            print(f"  {query['term'][:44]:46s} {positions}")
    print()

    if args.json:
        Path(args.json).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
