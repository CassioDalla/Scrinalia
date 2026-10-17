"""
The conflict-judge bench (issue #114): the judge scored against the resolutions a human took.

The judge decides, for a spelling that arrived twice, whether the term belongs to the Subject axis
(``TAG``) or to Named Entities (``ENTITY``). #69's table named this measurement as the follow-up it
could not make: "agreement with the curator's resolution". What makes it possible here is that the
gabarito **already exists** — every resolution writes a row in ``archive_conflict_resolution_log``,
and a human verdict is durable intent (principle VII), so it is truth that no later suggestion run
overwrites.

Three things this bench does deliberately, each because the obvious version of them would lie:

**The gabarito is the human half of the ledger.** ``source`` is ``HUMAN`` for a curator on the
conflict screen and ``JUDGE`` for the worker auto-resolving. Scoring both together would measure the
model against itself, so the ``JUDGE`` rows are read, counted and printed as *outside the score*, and
never silently dropped: a ledger that is 90% judge decisions is a fact the reader has to see.

**The pairs come from the ledger's own snapshots.** ``tag_name``, ``entity_name`` and ``entity_type``
are the pair *as it was at decision time*. The resolution deletes the losing row, which is why
``context_payload`` carries no foreign key on purpose; joining the live catalogues would score the
judge against a pair that no longer exists, or against a spelling a later resolution changed.

**A failed call is not an opinion.** The decision schema has no "I could not answer" state, so a
transport failure comes back as ``winner="TAG"`` with ``confidence=0.0``
(``FAILURE_REASON_PREFIX``). Read as a verdict, an Ollama outage would look like a judge that answers
``TAG`` to everything. Those rows are counted as *motor failures*, excluded from the score, and
printed loudly.

And one thing it prints because a single number would flatter the judge: the **constant baseline**.
The columns below answer "does the judge beat always answering the most frequent verdict?", which is
the question the agreement alone does not answer when the ledger is lopsided — and the ledger of a
curator working through a backlog is lopsided.

Nothing is written to the database: no resolution, no ban, no ledger row.

Run it from the repository root, against the real database and the real model::

    uv run python -m testing.evaluation.conflict_judge_quality
    uv run python -m testing.evaluation.conflict_judge_quality \\
        --config ollama_judge:gemma_4b_local \\
        --config ollama_judge:granite_local

The default is the configuration the worker itself declares, read from its signature, so "the current
configuration" cannot drift from the code. A model is never named here: a new one is a preset in the
LLM engine registry (``engines/LLMs/registry.py``), which is the same registry the worker reads.
"""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import time
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from scrinalia.core.config import settings
from scrinalia.core.database import get_db
from scrinalia.core.logger import logger
from scrinalia.domains.archive.engines.LLMs.ollama_tag_entity_conflict import FAILURE_REASON_PREFIX
from scrinalia.domains.archive.engines.LLMs.registry import (
    AVAILABLE_ENGINES,
    PRESETS,
    EngineName,
    PresetName,
    describe_config,
    get_engine,
)
from scrinalia.domains.archive.models.governance import ArchiveConflictResolutionLog
from scrinalia.domains.archive.workers.worker_resolve_tag_entity_conflict import execute

#: The two verdicts the judge can return. Spelled out instead of read from the schema literal,
#: because the report needs a fixed column order and the schema's order is not a contract.
VERDICTS = ("TAG", "ENTITY")

#: ``source`` values of the ledger. ``HUMAN`` is the gabarito, ``JUDGE`` is the model measuring
#: itself; the constraint that keeps the column to these two lives in the model.
HUMAN = "HUMAN"
JUDGE = "JUDGE"

#: Ordering key of the subset ``--limit`` takes. Recorded so a trial can be reproduced: the ledger
#: is ordered by decision time, and "the first N" would sample one afternoon of a curator's work
#: instead of the ledger.
DEFAULT_SEED = "scrinalia-conflict-v1"


# =============================================================================
# Configurations: named by the registry, never by this script
# =============================================================================


@dataclass(frozen=True)
class BenchConfig:
    """One scored configuration: an engine and a preset, both names the registry knows."""

    engine: str
    preset: str | None

    @property
    def label(self) -> str:
        return self.engine if self.preset is None else f"{self.engine}:{self.preset}"

    @property
    def typed_engine(self) -> EngineName:
        return cast("EngineName", self.engine)

    @property
    def typed_preset(self) -> PresetName | None:
        return cast("PresetName", self.preset) if self.preset else None


def parse_config(text: str) -> BenchConfig:
    """
    ``ENGINE[:PRESET]``, validated against the registry.

    A name the registry does not have is refused here rather than at load time: the judge registry
    holds one engine today, and "the bench measured a model the worker cannot be told to run" is the
    failure this refusal exists to prevent.
    """
    engine, _, preset = text.partition(":")
    if engine not in AVAILABLE_ENGINES:
        raise SystemExit(
            f"'{engine}' não é um motor do juiz de conflito. Opções: {sorted(AVAILABLE_ENGINES)}. "
            "Um motor novo é uma entrada em engines/LLMs/registry.py, não um argumento daqui."
        )
    if preset and preset not in PRESETS:
        raise SystemExit(f"'{preset}' não é um preset do juiz. Opções: {sorted(PRESETS)}.")
    return BenchConfig(engine=engine, preset=preset or None)


def worker_default_config() -> str:
    """
    The configuration the worker runs with when nobody says otherwise, read from its own signature.

    Retyping ``"ollama_judge:gemma_4b_local"`` here would be a second definition of the worker's
    default, and the day it changes the bench would keep scoring the old one while calling it "the
    current configuration".
    """
    parameters = inspect.signature(execute).parameters
    return f"{parameters['engine_name'].default}:{parameters['preset'].default}"


def worker_auto_resolve_threshold() -> float:
    """
    The floor above which the worker settles a conflict without a human, read from its signature.

    It is what turns agreement into a decision: the judge's verdicts below it reach a person, so the
    rate that matters operationally is not "how often is it right" but "how often is it right **and**
    sure enough to act alone".
    """
    return float(inspect.signature(execute).parameters["auto_resolve_threshold"].default)


# =============================================================================
# The gabarito: the human resolutions, read from the ledger
# =============================================================================


@dataclass(frozen=True)
class Resolution:
    """One ledger row, as the snapshots recorded it."""

    resolution_id: int
    tag_name: str
    entity_name: str
    entity_type: str
    winner: str
    source: str


def read_ledger(db: Session, source: str) -> list[Resolution]:
    """
    The ledger rows of one ``source``, oldest first.

    Two exclusions, both deliberate. ``source`` separates the human verdicts from the judge's own.
    ``undone_at IS NOT NULL`` is a decision a human reversed: it is not truth any more, and leaving
    it in would score the judge against an answer the institution already withdrew.

    Only the snapshot columns are read. ``tag_name``/``entity_name``/``entity_type`` are the pair at
    decision time; ``tag_id``/``entity_id`` are deliberately **not** selected, because resolving them
    against the live catalogues is exactly the read the ledger was built to make unnecessary.
    """
    stmt = (
        select(
            ArchiveConflictResolutionLog.resolution_id,
            ArchiveConflictResolutionLog.tag_name,
            ArchiveConflictResolutionLog.entity_name,
            ArchiveConflictResolutionLog.entity_type,
            ArchiveConflictResolutionLog.winner,
            ArchiveConflictResolutionLog.source,
        )
        .where(
            ArchiveConflictResolutionLog.source == source,
            ArchiveConflictResolutionLog.undone_at.is_(None),
        )
        .order_by(ArchiveConflictResolutionLog.resolution_id)
    )
    return [Resolution(*row) for row in db.execute(stmt).all()]


def ledger_census(db: Session) -> dict[str, int]:
    """
    The composition of the ledger: how many resolutions each side took, and how many were reversed.

    Printed and scored against, because it is what tells a reader whether the agreement below it
    means anything — a ledger that is 90% judge decisions has almost no gabarito in it.
    """
    rows = db.execute(select(ArchiveConflictResolutionLog.source, ArchiveConflictResolutionLog.undone_at)).all()
    counts: Counter[str] = Counter(row[0] for row in rows)
    return {
        "human": counts.get(HUMAN, 0),
        "judge": counts.get(JUDGE, 0),
        "undone": sum(1 for row in rows if row[1] is not None),
        "total": len(rows),
    }


def sample(rows: Sequence[Resolution], seed: str, limit: int | None) -> list[Resolution]:
    """
    The rows a trial run sees, in the ledger's own order.

    ``--limit`` exists to price a run before paying for it. The subset is drawn by
    ``md5(seed:resolution_id)`` rather than by position: the ledger is ordered by decision time, so
    "the first 10" is one curator's afternoon and not a sample of the ledger.
    """
    if limit is None or limit >= len(rows):
        return list(rows)
    if limit <= 0:
        raise SystemExit("--limit precisa ser um número positivo de pares.")
    shuffled = sorted(rows, key=lambda row: hashlib.md5(f"{seed}:{row.resolution_id}".encode()).hexdigest())
    return sorted(shuffled[:limit], key=lambda row: row.resolution_id)


# =============================================================================
# Scoring
# =============================================================================


@dataclass(frozen=True)
class Verdict:
    """What the judge answered, and why."""

    winner: str
    confidence: float
    reason: str = ""

    @property
    def failed(self) -> bool:
        """
        Whether this is a transport failure rather than an opinion.

        The engine answers ``winner="TAG"`` with a reason carrying ``FAILURE_REASON_PREFIX`` when the
        call fails. Scoring that as a verdict would turn an Ollama outage into a judge that answers
        ``TAG`` to everything, which is the most flattering possible reading of a broken run.
        """
        return self.reason.startswith(FAILURE_REASON_PREFIX)


@dataclass(frozen=True)
class Judged:
    """One human resolution the judge answered."""

    resolution: Resolution
    verdict: Verdict

    @property
    def measured(self) -> bool:
        return not self.verdict.failed

    @property
    def correct(self) -> bool:
        return self.verdict.winner == self.resolution.winner

    def would_resolve(self, threshold: float) -> bool:
        """Whether the worker, on this confidence, would have settled it without a human."""
        return self.verdict.confidence >= threshold


def agreement(rows: Sequence[Judged]) -> float:
    """Share of the scored rows the judge got right. Empty input is 0.0, never a division error."""
    return sum(1 for row in rows if row.correct) / len(rows) if rows else 0.0


def confusion(rows: Sequence[Judged]) -> Counter[tuple[str, str]]:
    """``(gabarito, juiz)`` counts: which way the mistake went, not only how many there were."""
    return Counter((row.resolution.winner, row.verdict.winner) for row in rows)


def constant_baseline(rows: Sequence[Judged]) -> tuple[str, float]:
    """
    The verdict that is right most often, and the agreement a judge answering only that would get.

    The number that keeps a lopsided ledger honest. A curator working through a backlog decides a
    run of street names in a row, so the ledger skews; against a 90%-ENTITY gabarito a judge that
    answers ``ENTITY`` to everything scores 0.900 and has measured nothing.
    """
    counts = Counter(row.resolution.winner for row in rows)
    if not counts:
        return ("", 0.0)
    label, count = counts.most_common(1)[0]
    return (label, count / len(rows))


def by_entity_type(rows: Sequence[Judged]) -> list[tuple[str, int, float]]:
    """
    Agreement per ``entity_type``, most frequent first.

    The judge's prompt answers by rule — geography, institutions, people, subjects — so where it
    fails is a question about a rule, and the type is the ledger's own column for it.
    """
    grouped: dict[str, list[Judged]] = {}
    for row in rows:
        grouped.setdefault(row.resolution.entity_type, []).append(row)
    return [
        (name, len(group), agreement(group))
        for name, group in sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0]))
    ]


# =============================================================================
# Running the judge
# =============================================================================


def score_live(
    config: BenchConfig,
    rows: Sequence[Resolution],
) -> tuple[list[Judged], float]:
    """Asks the engine about every row, in order, and returns the verdicts and the seconds per pair."""
    engine = get_engine(engine_name=config.typed_engine, preset=config.typed_preset)
    judged: list[Judged] = []
    started = time.perf_counter()
    for index, resolution in enumerate(rows, start=1):
        if index == 1 or index % 10 == 0 or index == len(rows):
            logger.info(f"⚖️  {config.label}: {index}/{len(rows)} — '{resolution.tag_name}'")
        try:
            decision = engine.decide_conflict(
                tag_name=resolution.tag_name,
                entity_name=resolution.entity_name,
                entity_type=resolution.entity_type,
            )
        except Exception as error:  # the engine is supposed to absorb this; a new engine may not
            logger.error(f"❌ o motor levantou em '{resolution.tag_name}': {error}")
            failure = str(error)[:50]
            judged.append(
                Judged(
                    resolution,
                    Verdict(winner="TAG", confidence=0.0, reason=f"{FAILURE_REASON_PREFIX}{failure}"),
                )
            )
            continue
        judged.append(
            Judged(
                resolution,
                Verdict(winner=decision.winner, confidence=decision.confidence, reason=decision.reason),
            )
        )
    seconds = (time.perf_counter() - started) / len(rows) if rows else 0.0
    return judged, seconds


# =============================================================================
# The report
# =============================================================================


def report_for(
    config: BenchConfig,
    judged: Sequence[Judged],
    census: dict[str, int],
    threshold: float,
    seconds_per_pair: float,
) -> dict[str, Any]:
    """Everything one configuration measured, as plain data, so ``--json`` and the print agree."""
    measured = [row for row in judged if row.measured]
    failed = [row for row in judged if not row.measured]
    baseline_label, baseline = constant_baseline(measured)
    resolved = [row for row in measured if row.would_resolve(threshold)]
    deferred = [row for row in measured if not row.would_resolve(threshold)]
    notes: list[str] = []

    classes = {row.resolution.winner for row in measured}
    if len(classes) == 1 and measured:
        only = next(iter(classes))
        notes.append(
            f"O gabarito desta coleção é de **classe única** ({only} {len(measured)}/{len(measured)}): "
            "uma resposta constante acerta tanto quanto o juiz, e a concordância sozinha não mede nada. "
            f"Leia a coluna `Δ` (concordância menos {baseline:.3f}) e a matriz."
        )
    if not measured:
        notes.append(
            "Nada foi pontuado: o motor não respondeu a nenhum par. O número da concordância abaixo é "
            "vazio, não zero — uma execução sem respostas não é uma medição."
        )
    if failed:
        notes.append(
            f"**{len(failed)} par(es) fora do placar por falha do motor** (prefixo `{FAILURE_REASON_PREFIX}`): "
            "o schema de decisão não tem estado de erro, então o motor devolve `TAG` com confiança 0.0 "
            "quando a chamada falha. Contado como falha, não como opinião."
        )
    if census.get("judge", 0) and not census.get("human", 0):
        notes.append(
            "O ledger tem decisões do juiz e nenhuma humana: não há gabarito para comparar. "
            "A concordância do juiz consigo mesmo é 1.000 por construção."
        )

    return {
        "config": config.label,
        "engine": config.engine,
        "preset": config.preset,
        "engine_config": dict(describe_config(config.typed_engine, config.typed_preset)),
        "threshold": threshold,
        "ledger": census,
        "scored": len(measured),
        "failed": len(failed),
        "agreement": agreement(measured),
        "constant": {"label": baseline_label, "agreement": baseline, "delta": agreement(measured) - baseline},
        "confusion": {f"{truth} → {predicted}": count for (truth, predicted), count in confusion(measured).items()},
        "entity_types": [
            {"entity_type": name, "rows": rows, "agreement": rate} for name, rows, rate in by_entity_type(measured)
        ],
        "auto_resolve": {
            "resolved": len(resolved),
            "resolved_agreement": agreement(resolved),
            "deferred": len(deferred),
            "deferred_agreement": agreement(deferred),
        },
        "seconds_per_pair": seconds_per_pair,
        "misses": [
            {
                "resolution_id": row.resolution.resolution_id,
                "tag_name": row.resolution.tag_name,
                "entity_name": row.resolution.entity_name,
                "entity_type": row.resolution.entity_type,
                "expected": row.resolution.winner,
                "predicted": row.verdict.winner,
                "confidence": row.verdict.confidence,
                "reason": row.verdict.reason,
            }
            for row in measured
            if not row.correct
        ],
        "failures": [
            {
                "resolution_id": row.resolution.resolution_id,
                "tag_name": row.resolution.tag_name,
                "reason": row.verdict.reason,
            }
            for row in failed
        ],
        "notes": notes,
    }


def summary_table(reports: Sequence[dict[str, Any]]) -> str:
    """The comparison: one line per configuration, best first by the margin over the constant."""
    lines = [
        "| Configuração | Concordância | Constante | Δ | Auto-resolvidos | Falhas | s/par |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for report in sorted(reports, key=lambda r: (-r["constant"]["delta"], -r["scored"])):
        constant = report["constant"]
        auto = report["auto_resolve"]
        lines.append(
            f"| `{report['config']}` | {report['agreement']:.3f} "
            f"| {constant['label'] or '—'} ({constant['agreement']:.3f}) | {constant['delta']:+.3f} "
            f"| {auto['resolved']} ({auto['resolved_agreement']:.3f}) | {report['failed']} "
            f"| {report['seconds_per_pair']:.2f} |"
        )
    return "\n".join(lines)


def matrix_lines(report: dict[str, Any]) -> list[str]:
    """The 2x2 of gabarito against verdict, with the totals, because the direction is the finding."""
    cells = report["confusion"]
    lines = [
        "| gabarito \\ juiz | TAG | ENTITY | total |",
        "| --- | ---: | ---: | ---: |",
    ]
    for truth in VERDICTS:
        counts = [cells.get(f"{truth} → {predicted}", 0) for predicted in VERDICTS]
        lines.append(f"| **{truth}** | {counts[0]} | {counts[1]} | {sum(counts)} |")
    totals = [sum(cells.get(f"{truth} → {predicted}", 0) for truth in VERDICTS) for predicted in VERDICTS]
    lines.append(f"| **total** | {totals[0]} | {totals[1]} | {sum(totals)} |")
    return lines


def detail_lines(report: dict[str, Any]) -> list[str]:
    """Per-configuration detail: the ledger split, the score, the matrix and the disagreements."""
    ledger = report["ledger"]
    auto = report["auto_resolve"]
    engine_config = report["engine_config"]
    lines = [
        f"### `{report['config']}`",
        "",
        f"- ledger: {ledger.get('total', 0)} resolução(ões) — **{ledger.get('human', 0)} humana(s)** "
        f"(o gabarito), {ledger.get('judge', 0)} do juiz (fora do placar), "
        f"{ledger.get('undone', 0)} desfeita(s) (fora do placar)",
        f"- pontuadas: {report['scored']} · falhas do motor: {report['failed']}",
        f"- concordância: **{report['agreement']:.3f}** · constante `{report['constant']['label'] or '—'}` "
        f"({report['constant']['agreement']:.3f}) → Δ **{report['constant']['delta']:+.3f}**",
        f"- motor: `{report['engine']}` · preset `{report['preset']}` · "
        + " · ".join(f"{key}={value}" for key, value in engine_config.items()),
        f"- limiar de auto-resolução do worker: {report['threshold']:.2f} — teria resolvido "
        f"{auto['resolved']} sem humano (concordância {auto['resolved_agreement']:.3f}) e mandado "
        f"{auto['deferred']} para revisão (concordância {auto['deferred_agreement']:.3f})",
        f"- segundos por par: {report['seconds_per_pair']:.2f}",
        "",
    ]
    lines += [f"> {note}" for note in report["notes"]]
    if report["notes"]:
        lines.append("")
    lines += matrix_lines(report)
    if report["entity_types"]:
        rendered = " · ".join(
            f"{entry['entity_type']} {entry['agreement']:.3f} ({entry['rows']})" for entry in report["entity_types"]
        )
        lines += ["", f"Concordância por tipo de entidade: {rendered}"]
    if report["failures"]:
        lines += ["", f"**{len(report['failures'])} falha(s) do motor**, as primeiras 10:", ""]
        lines += [
            f"- `{failure['resolution_id']}` '{failure['tag_name']}': {failure['reason']}"
            for failure in report["failures"][:10]
        ]
    if report["misses"]:
        lines += ["", f"**{len(report['misses'])} discordância(s)**, as primeiras 20:", ""]
        lines += [
            f"- `{miss['resolution_id']}` '{miss['tag_name']}' vs '{miss['entity_name']}' "
            f"({miss['entity_type']}): o curador decidiu **{miss['expected']}**, o juiz respondeu "
            f"**{miss['predicted']}** (confiança {miss['confidence']:.3f}) — {miss['reason']}"
            for miss in report["misses"][:20]
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


def run_score(args: argparse.Namespace) -> int:
    """Asks every requested configuration about the human resolutions and prints the comparison."""
    configs = [parse_config(text) for text in args.config]
    threshold = worker_auto_resolve_threshold()

    with get_db() as db:
        census = ledger_census(db)
        rows = read_ledger(db, HUMAN)
        db.rollback()

    logger.info(
        f"📒 ledger: {census.get('total', 0)} resolução(ões) · {census.get('human', 0)} humana(s) · "
        f"{census.get('judge', 0)} do juiz · {census.get('undone', 0)} desfeita(s)"
    )
    if not rows:
        raise SystemExit(
            "O ledger não tem nenhuma resolução humana: não há gabarito. Este banco nunca teve um "
            "curador decidindo um conflito de grafia, então o juiz não pode ser medido contra ele — "
            "e medir contra as decisões do próprio juiz não é uma medição."
        )

    chosen = sample(rows, args.seed, args.limit)
    if len(chosen) < len(rows):
        logger.info(f"🎲 {len(chosen)} de {len(rows)} par(es) sorteados com a semente '{args.seed}'")

    reports: list[dict[str, Any]] = []
    for config in configs:
        logger.info(f"🧠 {config.label}: consultando o juiz sobre {len(chosen)} par(es)...")
        judged, seconds = score_live(config, chosen)
        reports.append(report_for(config, judged, census, threshold, seconds))

    print_report(reports)

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(
                {
                    "mode": "conflict_judge",
                    "measured_at": _today(),
                    "database": settings.DB_NAME,
                    "seed": args.seed,
                    "scored_pairs": len(chosen),
                    "reports": reports,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        logger.success(f"💾 relatório escrito em {args.json}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="The conflict-judge bench: the judge scored against the resolutions a human took."
    )
    parser.add_argument(
        "--config",
        action="append",
        default=[],
        metavar="ENGINE[:PRESET]",
        help="A configuration to score; repeat it to compare. Default: the worker's own.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Cap the pairs the judge sees, for a trial before the full run.",
    )
    parser.add_argument(
        "--seed",
        default=DEFAULT_SEED,
        help="Ordering seed of the subset --limit takes; recorded so a trial is reproducible.",
    )
    parser.add_argument("--json", type=Path, default=None, help="Also write the raw report here.")
    args = parser.parse_args(argv)

    if not args.config:
        args.config = [worker_default_config()]
    return run_score(args)


if __name__ == "__main__":
    raise SystemExit(main())
