"""
Dry-run of the subject classification over the real collection (Fase 1.5 — entregável X1).

Runs the **same** engine, the **same** vocabulary and the **same** guard the worker uses,
over every orphan tag, and prints the distribution that *would* be written. Then it stops.

The point is to decide with the number in hand instead of approving a promise: the defect
that started this phase was not "the worker is broken", it was "the worker classified 687 of
980 tags into one drawer and nothing in the output said so". A distribution is what denounces
that, so a distribution is what gets shown before anything is written.

Nothing here writes. The session is opened, read from and rolled back; the counters live in
memory. Applying it is ``worker_macro_category``, a separate command a human runs after
reading this report.

Run it from the repository root, against the real database and the real model::

    uv run python -m testing.evaluation.macro_category_dry_run --limit 400
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from sqlalchemy import func, select

from memoria_curitibana.core.database import get_db
from memoria_curitibana.core.logger import logger
from memoria_curitibana.core.runner_config import MacroCategoryRunnerConfig
from memoria_curitibana.domains.archive.domain.normalization import normalize_tag
from memoria_curitibana.domains.archive.domain.vocabulary import (
    is_place_term,
    is_subject_candidate,
    label_set_fingerprint,
)
from memoria_curitibana.domains.archive.models import ArchiveTag
from memoria_curitibana.domains.archive.repository import TagRepository

DEFAULT_OUTPUT = Path(".analysis") / "macro_category_dry_run.json"


def _bucket(name: str, excluded: set[str]) -> str:
    """Which final state a tag would end in, using the worker's own order of decisions."""
    if not is_subject_candidate(name):
        return "NENHUMA (regra de forma)"
    if normalize_tag(name) in excluded:
        return "NENHUMA (curadoria)"
    if is_place_term(name):
        return "FACETA PLACE"
    return "CLASSIFICAR"


def build_report(limit: int | None, device: str) -> dict:
    """Reads the collection and projects the outcome. Writes nothing, rollback at the end."""
    from memoria_curitibana.domains.archive.engines.classification.registry import get_engine

    config = MacroCategoryRunnerConfig()

    with get_db() as db:
        repository = TagRepository(db)
        categories_map = repository.get_active_macro_categories()
        excluded = repository.get_subject_exclusions()

        stmt = (
            select(ArchiveTag.tag_id, ArchiveTag.name)
            .where(ArchiveTag.macro_category_id.is_(None))
            .order_by(ArchiveTag.tag_id)
            .limit(limit or 100000)
        )
        pending = [(row.tag_id, row.name) for row in db.execute(stmt).all()]

        total_orphans = db.scalar(
            select(func.count()).select_from(ArchiveTag).where(ArchiveTag.macro_category_id.is_(None))
        )

        db.rollback()

    logger.info(f"📂 {len(categories_map)} drawers · {len(pending)} orphan tags read ({total_orphans} total)")

    plan = Counter()
    projected = Counter()
    confidences: list[float] = []
    would_link = 0
    would_review = 0
    samples: dict[str, list[str]] = {}

    classifiable = [(tag_id, name) for tag_id, name in pending if _bucket(name, excluded) == "CLASSIFICAR"]
    for _tag_id, name in pending:
        plan[_bucket(name, excluded)] += 1

    logger.info(f"🧠 {len(classifiable)} tags need the model; loading the engine...")
    engine = None
    if classifiable:
        engine = get_engine("deberta_typology", preset="cpu_local", device=device)

    labels = list(categories_map.keys())
    batch = 32
    for start in range(0, len(classifiable), batch):
        chunk = classifiable[start : start + batch]
        results = engine.classify([name for _tag_id, name in chunk], labels, batch_size=1) if engine else []
        for (_tag_id, name), result in zip(chunk, results, strict=True):
            best = result["labels"][0]
            score = float(result["scores"][0])
            confidences.append(score)
            if score > config.confidence_threshold:
                would_link += 1
                projected[best] += 1
                samples.setdefault(best, []).append(name)
            else:
                would_review += 1
                projected["(sem gaveta: revisão)"] += 1

    ranked = sorted(categories_map, key=lambda name: -projected.get(name, 0))
    distribution = [
        {
            "category": name,
            "tags": projected.get(name, 0),
            "share": projected.get(name, 0) / max(1, would_link),
            "samples": samples.get(name, [])[:8],
        }
        for name in ranked
    ]

    return {
        "drawers": list(categories_map),
        "label_fingerprint": label_set_fingerprint(categories_map),
        "confidence_threshold": config.confidence_threshold,
        "orphans_read": len(pending),
        "orphans_total": total_orphans,
        "plan": dict(plan),
        "classifiable": len(classifiable),
        "would_link": would_link,
        "would_review": would_review,
        "confidences": {
            "min": min(confidences) if confidences else 0.0,
            "max": max(confidences) if confidences else 0.0,
            "mean": sum(confidences) / len(confidences) if confidences else 0.0,
        },
        "distribution": distribution,
    }


def print_report(report: dict) -> None:
    plan = report["plan"]
    logger.info("--- plano (o que o worker faria) ---")
    for bucket, count in sorted(plan.items(), key=lambda kv: -kv[1]):
        logger.info(f"   {bucket:<26} {count:>5} tags")

    logger.info(
        f"--- resultado projetado ({report['would_link']} recebem gaveta · "
        f"{report['would_review']} vão para revisão) ---"
    )
    for row in report["distribution"]:
        bar = "█" * int(row["share"] * 40)
        logger.info(f"   {row['category']:<32} {row['tags']:>4}  {row['share']:>5.1%} {bar}")

    conf = report["confidences"]
    logger.info(f"--- confiança: min {conf['min']:.3f} · média {conf['mean']:.3f} · max {conf['max']:.3f} ---")
    for row in report["distribution"][:4]:
        if row["samples"]:
            logger.info(f"   {row['category']}: {', '.join(row['samples'])}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only projection of the subject classification.")
    parser.add_argument("--limit", type=int, default=None, help="Only the first N orphan tags by id.")
    parser.add_argument("--device", default="cpu", help="cpu or cuda:N.")
    parser.add_argument("--json", type=Path, default=DEFAULT_OUTPUT, help="Where to write the report.")
    args = parser.parse_args(argv)

    report = build_report(limit=args.limit, device=args.device)
    print_report(report)

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"💾 report written to {args.json} (nothing was written to the database)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
