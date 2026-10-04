"""
Review report for the tag-merge proposals (Buraco 4, Fase 1).

Computes the clusters the suggester proposes on the **real** collection and, for each one,
the impact the merge would have and the warnings a curator must read before approving.
Nothing is written and nothing is merged: this is the evidence the human decides on, and
the reason the suggestions stopped being a list nobody could act on safely.

The distinction that matters (measured, see ``.analysis/buraco-4-plano.md``): the clusters
are not all equal. In the real collection, 60 of them carry a member with a number and some
of those are wrong (``rua 24 de maio`` <- ``rua 13 de maio``, ``303 anos`` <- ``anos 30``).
Approving the list wholesale would corrupt the taxonomy, exactly like approving every
excerpt made the semantic ranking worse in Fase 3.5-B.

Run it from the repository root, against the real database:

    uv run python -m testing.evaluation.tag_merge_review --threshold 0.65 --limit 1000

It prints a summary and writes the full JSON report to ``.analysis/`` (non-versioned).
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from sqlalchemy import func, select

from memoria_curitibana.core.database import get_db
from memoria_curitibana.core.logger import logger
from memoria_curitibana.domains.archive.models import ArchiveTag
from memoria_curitibana.domains.archive.repository.tag_repo import TagRepository

DEFAULT_OUTPUT = Path(".analysis") / "tag_merge_report.json"


def _review_cluster(repo: TagRepository, suggestion) -> dict:
    """Impact and warnings of one proposed cluster, computed without applying it."""
    ids_to_merge = [member.tag_id for member in suggestion.members[1:]]
    plan = repo.plan_merge(suggestion.canonical_id, ids_to_merge)

    return {
        "canonical_name": suggestion.canonical_name,
        "reason": suggestion.reason,
        "total_documents": suggestion.total_documents,
        "documents_updated": plan.documents_updated,
        "links_rewritten": plan.links_rewritten,
        "review_flags": plan.review_flags,
        "category_would_be_lost": plan.category_would_be_lost,
        "members": [
            {
                "tag_id": member.tag_id,
                "name": member.name,
                "document_count": member.document_count,
                "macro_category_id": next(
                    (impact.macro_category_id for impact in plan.impacted if impact.tag_id == member.tag_id), None
                ),
            }
            for member in suggestion.members
        ],
    }


def build_report(threshold: float, limit: int) -> dict:
    """Reads the collection and returns the full report. Read-only by construction."""
    with get_db() as db:
        repo = TagRepository(db)
        suggestions = repo.find_merge_suggestions(threshold=threshold, limit=limit)
        clusters = [_review_cluster(repo, suggestion) for suggestion in suggestions]
        tags_total = db.scalar(select(func.count()).select_from(ArchiveTag))
        db.rollback()

    absorbed = sum(len(cluster["members"]) - 1 for cluster in clusters)
    documents_touched = sum(cluster["documents_updated"] for cluster in clusters)
    links_rewritten = sum(cluster["links_rewritten"] for cluster in clusters)

    return {
        "threshold": threshold,
        "tags_in_catalog": tags_total,
        "clusters_found": len(clusters),
        "tags_absorbed": absorbed,
        "documents_touched": documents_touched,
        "links_rewritten": links_rewritten,
        "by_reason": dict(Counter(cluster["reason"] for cluster in clusters)),
        "by_flag": dict(Counter(flag for cluster in clusters for flag in cluster["review_flags"])),
        "clusters_without_flags": sum(1 for cluster in clusters if not cluster["review_flags"]),
        "clusters": clusters,
    }


def _tag_count():
    from sqlalchemy import func, select

    from memoria_curitibana.domains.archive.models import ArchiveTag

    return select(func.count()).select_from(ArchiveTag)


def print_summary(report: dict, examples: int) -> None:
    logger.info(f"📊 {report['clusters_found']} clusters over {report['tags_in_catalog']} tags")
    logger.info(f"   {report['tags_absorbed']} tags absorbed · {report['documents_touched']} documents touched")
    logger.info(f"   reasons: {report['by_reason']}")
    logger.info(f"   flags: {report['by_flag']}")
    logger.info(f"   clusters without flags: {report['clusters_without_flags']}")

    flagged = [cluster for cluster in report["clusters"] if cluster["review_flags"]]
    flagged.sort(key=lambda cluster: -cluster["total_documents"])
    if examples:
        logger.info(f"--- {examples} flagged clusters with the most documents (read before approving) ---")
        for cluster in flagged[:examples]:
            members = ", ".join(f"{member['name']}({member['document_count']})" for member in cluster["members"])
            logger.info(
                f"   [{cluster['reason']}] {cluster['canonical_name']} <- {members} :: {cluster['review_flags']}"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only review report of the tag-merge proposals.")
    parser.add_argument("--threshold", type=float, default=0.65, help="pg_trgm similarity floor.")
    parser.add_argument("--limit", type=int, default=1000, help="How many clusters to report.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Where to write the JSON report.")
    parser.add_argument("--examples", type=int, default=10, help="Flagged clusters to print.")
    args = parser.parse_args()

    report = build_report(threshold=args.threshold, limit=args.limit)
    print_summary(report, examples=args.examples)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"💾 report written to {args.output}")


if __name__ == "__main__":
    main()
