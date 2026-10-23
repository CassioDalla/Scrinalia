"""
The quality-validator bench (issue #115): the cleaning rules scored one by one.

The validator's output is not one label but a **set of flags per document**. A ``REWRITE`` rule
rewrites text, a ``VALIDATE`` rule only flags a match and never touches the text, and an ``LLM_CHECK``
rule asks a model for an opinion about the title. So the unit of the measurement is the **rule** and
not the document: a validator that flags the right document for the wrong reason is not doing the
job, and a document-level agreement cannot see the difference.

Two questions the report answers per rule, and neither is derivable from the other:

**precision**
    Of the documents this rule flagged, how many a curator agrees were anomalous.

**recall**
    Of the documents the curator says this rule should have caught, how many it caught. This is why
    the bench needs a labelled set: the curator only ever sees what was flagged, so a review queue
    can measure precision and can never measure a miss — the documents nobody flagged are precisely
    the ones absent from it.

The gabarito is therefore a **human-labelled set** of documents, the same shape the typology bench
uses. ``--pick`` proposes rows by the stored flag strata and writes the skeleton; a curator writes,
per document, which rules should have fired; ``--score`` measures. The rows are collection data and
are deliberately not versioned (``testing/evaluation/README.md`` documents the format); the scoring
is what is versioned.

The rules come from the catalogue, never from a list here, so the bench follows the installation's
own rules — including the fact that it currently has none. Whether a rule fires is decided by the
worker's own functions, so the bench cannot score a rule the worker does not have:

* :func:`~scrinalia.domains.archive.workers.worker_quality_validator.matched_rule_labels` for a
  ``VALIDATE`` rule;
* :func:`~scrinalia.domains.archive.workers.worker_quality_validator.llm_check_reason` for the
  ``LLM_CHECK`` rule, with the worker's own confidence floor.

Nothing is written: the session is opened, read and rolled back.

Run it from the repository root, against the real database::

    uv run python -m testing.evaluation.quality_validator_quality --pick
    uv run python -m testing.evaluation.quality_validator_quality --sheet
    uv run python -m testing.evaluation.quality_validator_quality
    uv run python -m testing.evaluation.quality_validator_quality --predictions stored
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from scrinalia.core.config import settings
from scrinalia.core.database import get_db
from scrinalia.core.logger import logger
from scrinalia.domains.archive.models import AnomalyReason, ArchiveDocument
from scrinalia.domains.archive.repository.cleaning_repo import CleaningRepository
from scrinalia.domains.archive.schemas.cleaning_schema import CleaningRuleDTO
from scrinalia.domains.archive.workers.worker_quality_validator import (
    DEFAULT_LLM_CONFIDENCE,
    compile_rules,
    llm_check_reason,
    matched_rule_labels,
    rule_flag_label,
)
from testing.evaluation import MIN_POSITIVES
from testing.evaluation.dataset import DATA_DIR

PAIRS_FILENAME = "validator_pairs.json"
SHEET_FILENAME = "validator_pairs.sheet.md"

#: The kinds whose output is a flag rather than a rewrite. ``REWRITE`` is out of scope by
#: definition: it changes the text and marks nothing, so there is no flag to agree with.
SCORED_KINDS = ("VALIDATE", "LLM_CHECK")

#: Ordering key of the sample, recorded in ``sampling`` for the same reason the other benches record
#: it: a re-run after the collection grew proposes the same rows for the rows that already existed.
DEFAULT_SEED = "scrinalia-validator-v1"

#: How many rows one stratum contributes by default, and how many the two "nothing was flagged"
#: buckets contribute. The second is not optional padding: without documents no scorable rule
#: flagged, recall has no denominator and the bench would only ever measure precision.
DEFAULT_PER_RULE = 40
DEFAULT_CLEAN_ROWS = 25

#: The bucket of a document some **unscorable** rule touched, or of one whose stored flag names a
#: rule the catalogue no longer has. It is where a rule that should have fired is looked for.
NO_RULE = "(nenhuma regra)"

#: The bucket of a document with no anomaly recorded at all: where a false positive would live.
CLEAN = "(sem anomalia)"

#: ``confidence`` is the curator's own certainty, the same vocabulary the other sets use.
CONFIDENCE_VALUES = ("alta", "media", "baixa")


# =============================================================================
# The rules under measurement
# =============================================================================


def all_rules(db: Session) -> list[CleaningRuleDTO]:
    """The whole catalogue, retired rules included, the way the rules screen reads it."""
    return list(CleaningRepository(db).list_rules(include_inactive=True))


def scorable_rules(rules: Sequence[CleaningRuleDTO]) -> list[CleaningRuleDTO]:
    """The active rules whose output is a flag, in catalogue order — the unit of this bench."""
    return [rule for rule in rules if rule.is_active and rule.rule_kind in SCORED_KINDS]


def ambiguous_rules(rules: Sequence[CleaningRuleDTO]) -> list[str]:
    """
    The names that cannot identify a rule, as sentences for the person who has to fix them.

    The gabarito names rules by ``rule_name``, and a ``VALIDATE`` flag carries the label
    ``rule.anomaly_reason or rule.rule_name``. Two active rules sharing either one would make the read
    ambiguous — a flag that could belong to two rules, or a name two rows answer to — and the report
    would silently charge one rule with the other's documents. Refused instead of guessed, because
    the fix is in the catalogue and takes a minute.
    """
    problems: list[str] = []
    for name, count in Counter(rule.rule_name for rule in rules).items():
        if count > 1:
            problems.append(f"{count} regras ativas chamadas '{name}' — o gabarito não pode dizer qual delas")
    for label, count in Counter(rule_flag_label(rule) for rule in rules if rule.rule_kind == "VALIDATE").items():
        if count > 1:
            problems.append(
                f"{count} regras VALIDATE gravam o mesmo rótulo '{label}' — um flag não diz qual delas o levantou"
            )
    return problems


def engine_overrides(args: argparse.Namespace) -> dict[str, Any]:
    """The engine overrides the run carries, forwarded to the reviewer exactly like ``--option``."""
    overrides: dict[str, Any] = {}
    for text in args.option:
        key, separator, value = text.partition("=")
        if not key or not separator:
            raise SystemExit(f"--option espera CHAVE=VALOR, recebeu '{text}'.")
        overrides[key] = value
    return overrides


def build_llm_engine(db: Session, args: argparse.Namespace) -> Any | None:
    """
    The reviewer of the first active ``LLM_CHECK`` rule, or ``None`` when there is no such rule.

    A rule whose engine or preset the registry does not have is refused here, naming the rule, rather
    than surfacing as a ``ValueError`` from inside the worker (issue #124). ``execute`` calls
    ``get_engine`` with no guard, so that mistake is not a warning — it fails the whole run.
    """
    from scrinalia.domains.archive.engines.title_quality.registry import get_engine

    rules = [rule for rule in all_rules(db) if rule.is_active and rule.rule_kind == "LLM_CHECK"]
    if not rules:
        return None
    rule = rules[0]
    try:
        return get_engine(
            rule.engine_name or "ollama_title_check",  # type: ignore[arg-type]
            rule.preset,  # type: ignore[arg-type]
            **engine_overrides(args),
        )
    except ValueError as error:
        raise SystemExit(
            f"A regra LLM_CHECK '{rule.rule_name}' nomeia engine/preset que o registro não tem: {error} "
            "As regras VALIDATE não precisam de modelo; corrija ou desative a regra na tela de regras. "
            "Ver a issue #124."
        ) from error


# =============================================================================
# The labelled set
# =============================================================================


@dataclass(frozen=True)
class LabelledRow:
    """One document a curator graded: which rules should have flagged it."""

    description_id: str
    expected: frozenset[str]
    needs_decision: bool = False
    note: str = ""


def load_payload(path: Path) -> dict[str, Any]:
    """
    The labelled set as it was written, with a sentence instead of a traceback when it is not one.

    The reflex fix for a missing fixture is to recreate it from the code, which is the one thing that
    must not happen here — the rows are the collection. The message says so out loud.
    """
    if not path.exists():
        raise SystemExit(
            f"'{path}' não existe: proponha o conjunto com --pick e rotule-o antes de pontuar. As linhas "
            "são dados do acervo e não são versionadas (testing/evaluation/README.md explica o formato)."
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise SystemExit(f"'{path}' não é um JSON válido: {error}") from error
    if not isinstance(payload, dict):
        raise SystemExit(f"'{path}' tem de conter um objeto JSON, veio {type(payload).__name__}.")
    return payload


def load_labelled(path: Path, known: Sequence[str], allow_draft: bool) -> tuple[list[LabelledRow], dict[str, Any]]:
    """
    Reads the labelled set, refusing a draft and a rule the catalogue does not have.

    ``status`` is the human signature. While it still starts with ``draft``, the scorer refuses to
    produce a number unless ``--allow-draft`` says otherwise — a draft set quoted in a changelog is
    the failure mode this field exists to prevent.

    An ``expected`` that names a rule the active catalogue does not have is refused for the same
    reason the typology scorer warns: it is a guaranteed miss the model cannot avoid, and it is a
    typo in the gabarito far more often than a retired rule.
    """
    payload = load_payload(path)
    status = str(payload.get("status", ""))
    if status.lower().startswith("draft") and not allow_draft:
        raise SystemExit(
            f"'{path}' ainda é rascunho ('{status}'): nenhum curador assinou este gabarito, e um número "
            "tirado dele lê exatamente como um revisado. Use --allow-draft para explorar, sabendo que "
            "não é uma medição."
        )
    known_set = set(known)
    rows: list[LabelledRow] = []
    for index, entry in enumerate(payload.get("pairs", [])):
        expected = entry.get("expected") or []
        if not isinstance(expected, list) or not all(isinstance(item, str) for item in expected):
            raise SystemExit(f"linha {index}: 'expected' tem de ser uma lista de nomes de regra, veio {expected!r}.")
        unknown = sorted(set(expected) - known_set)
        if unknown:
            raise SystemExit(
                f"linha {index} ({entry.get('description_id')}): o gabarito nomeia {unknown}, que o catálogo "
                f"ativo não tem. Regras ativas: {sorted(known_set)}."
            )
        confidence = entry.get("confidence")
        if confidence is not None and confidence not in CONFIDENCE_VALUES:
            raise SystemExit(f"linha {index}: 'confidence' tem de estar em {CONFIDENCE_VALUES}, veio {confidence!r}.")
        rows.append(
            LabelledRow(
                description_id=str(entry["description_id"]),
                expected=frozenset(expected),
                needs_decision=bool(entry.get("needs_decision", False)),
                note=str(entry.get("note", "")),
            )
        )
    return rows, payload


# =============================================================================
# Scoring
# =============================================================================


@dataclass(frozen=True)
class RuleScore:
    """One rule's four counts over the scored documents."""

    label: str
    kind: str
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0

    @property
    def support(self) -> int:
        """How many documents the gabarito says this rule should have flagged."""
        return self.true_positives + self.false_negatives

    @property
    def fired(self) -> int:
        """How many documents this rule flagged, rightly or not."""
        return self.true_positives + self.false_positives

    @property
    def measured(self) -> bool:
        """
        Whether the rule has enough labelled positives to be worth a number.

        The same floor the typology bench uses, applied to the same quantity: the support the curator
        gave the rule. A rule with one or two documents behind it produces an F1 that reads like a
        measurement and is not one, and the report says "não medida" instead.
        """
        return self.support >= MIN_POSITIVES

    @property
    def precision(self) -> float:
        return self.true_positives / self.fired if self.fired else 0.0

    @property
    def recall(self) -> float:
        return self.true_positives / self.support if self.support else 0.0

    @property
    def f1(self) -> float:
        precision, recall = self.precision, self.recall
        return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


@dataclass(frozen=True)
class Scored:
    """One graded document with the rules that actually fired on it."""

    description_id: str
    expected: frozenset[str]
    predicted: frozenset[str]
    needs_decision: bool = False

    @property
    def missing(self) -> frozenset[str]:
        """Rules the curator wanted and the validator did not fire — the anomalies it missed."""
        return self.expected - self.predicted

    @property
    def spurious(self) -> frozenset[str]:
        """Rules the validator fired and the curator did not want — the flags it should not have raised."""
        return self.predicted - self.expected


def score_rules(rows: Sequence[Scored], rules: Sequence[CleaningRuleDTO]) -> list[RuleScore]:
    """
    Precision, recall and F1 per rule, over the rows the curator did not mark ambiguous.

    A rule the curator never mentions and that never fires still gets a line: on a set of forty
    documents, "this rule agrees with nobody" is the finding, and a rule silently absent from the
    table reads as a rule that works.
    """
    counts: dict[str, list[int]] = {rule.rule_name: [0, 0, 0] for rule in rules}
    for row in rows:
        for name in row.expected:
            if name not in counts:
                continue
            counts[name][0 if name in row.predicted else 2] += 1
        for name in row.predicted - row.expected:
            if name in counts:
                counts[name][1] += 1
    scores = [
        RuleScore(
            label=rule.rule_name,
            kind=rule.rule_kind,
            true_positives=counts[rule.rule_name][0],
            false_positives=counts[rule.rule_name][1],
            false_negatives=counts[rule.rule_name][2],
        )
        for rule in rules
    ]
    return sorted(scores, key=lambda score: (-score.support, -score.fired, score.label))


def flag_agreement(rows: Sequence[Scored]) -> float:
    """Share of the graded documents whose whole flag set the validator got right."""
    return sum(1 for row in rows if row.expected == row.predicted) / len(rows) if rows else 0.0


# =============================================================================
# Reading the collection
# =============================================================================


@dataclass(frozen=True)
class Candidate:
    """A document the picker proposes, with the flags the last run stored on it."""

    description_id: str
    title: str
    stored_reasons: tuple[str, ...]
    key: str


def stored_key(reasons: Sequence[str], validate_labels: dict[str, str], llm_names: Sequence[str]) -> str:
    """
    Which stratum a document belongs to, from the flags the last run wrote.

    The stored flags are enough to stratify on, and they are free. The alternative — running the
    active rules over the whole collection to build the strata — re-reads 4,831 documents and, with an
    ``LLM_CHECK`` rule active, makes a model call for each, to order a sample of a hundred.
    """
    for reason in reasons:
        code, _, payload = reason.partition(":")
        if code == AnomalyReason.RULE_MATCH and payload in validate_labels:
            return validate_labels[payload]
        if code == AnomalyReason.LLM_SUSPECT and llm_names:
            return llm_names[0]
    return NO_RULE if reasons else CLEAN


def read_candidates(db: Session, validate_labels: dict[str, str], llm_names: Sequence[str]) -> list[Candidate]:
    """Every document with its stored flags, as the picker sees it."""
    stmt = select(
        ArchiveDocument.description_id,
        ArchiveDocument.original_title,
        ArchiveDocument.anomaly_reasons,
    ).order_by(ArchiveDocument.description_id)
    out: list[Candidate] = []
    for description_id, title, reasons in db.execute(stmt).all():
        stored = tuple(reasons or ())
        out.append(
            Candidate(
                description_id=description_id,
                title=(title or "").strip(),
                stored_reasons=stored,
                key=stored_key(stored, validate_labels, llm_names),
            )
        )
    return out


def order_key(seed: str, description_id: str) -> str:
    """Deterministic ordering key of the sample: the same seed proposes the same rows."""
    return hashlib.md5(f"{seed}:{description_id}".encode()).hexdigest()


def pick(
    candidates: Sequence[Candidate], strata: Sequence[str], seed: str, per_rule: int, clean_rows: int
) -> dict[str, list[Candidate]]:
    """
    One sample per stratum, deterministic under ``seed``.

    A stratum is a rule, plus the two buckets that make the mistakes visible: documents no scorable
    rule flagged (where a *miss* lives) and documents with no anomaly at all (where a false positive
    would be). Each stratum is deduplicated by the title, because two documents with the same title
    cannot disagree and a second copy would only weight whatever the collection repeats.
    """
    picked: dict[str, list[Candidate]] = {}
    for key in [*strata, NO_RULE, CLEAN]:
        limit = clean_rows if key == CLEAN else per_rule
        bucket = [row for row in candidates if row.key == key]
        seen: set[str] = set()
        unique: list[Candidate] = []
        for row in sorted(bucket, key=lambda item: order_key(seed, item.description_id)):
            text = row.title.lower()
            if text in seen:
                continue
            seen.add(text)
            unique.append(row)
        picked[key] = unique[:limit]
    return picked


def build_payload(picked: dict[str, list[Candidate]], status: str, sampling: str) -> dict[str, Any]:
    """The skeleton the curator fills: one entry per proposed document, ``expected`` empty."""
    pairs: list[dict[str, Any]] = []
    for key, rows in picked.items():
        for row in rows:
            pairs.append(
                {
                    "description_id": row.description_id,
                    "candidate": key,
                    "title": row.title,
                    "stored_reasons": list(row.stored_reasons),
                    "expected": [],
                    "confidence": None,
                    "needs_decision": False,
                    "note": "",
                }
            )
    return {
        "description": "As regras VALIDATE/LLM_CHECK ativas, medidas uma por uma contra um curador.",
        "collection": "",
        "sampling": sampling,
        "active_rules": [],
        "pairs": pairs,
        "status": status,
    }


def sheet_lines(payload: dict[str, Any]) -> list[str]:
    """The human sheet: what was stored, and nothing that would give the answer away."""
    rules = sorted(payload.get("active_rules", []))
    lines = [
        "# Gabarito do validador de qualidade",
        "",
        f"Regras no catálogo quando o conjunto foi proposto: {', '.join(rules) or '(nenhuma)'}",
        "",
        "Para cada documento, escreva em `expected` **o nome de cada regra que deveria tê-lo marcado**.",
        "Uma lista vazia é a resposta 'nenhuma regra deveria marcar este documento' — e é a resposta que",
        "mede a precisão das outras.",
        "",
    ]
    for pair in payload["pairs"]:
        stored = ", ".join(pair["stored_reasons"]) or "nada"
        lines += [
            f"## `{pair['description_id']}` — estrato: {pair['candidate']}",
            "",
            f"- título: {pair['title'] or '(vazio)'}",
            f"- flags gravadas na última execução: {stored}",
            "",
        ]
    return lines


def print_sheet(payload: dict[str, Any], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(sheet_lines(payload)) + "\n", encoding="utf-8")
    logger.success(f"📝 folha escrita em {out}")


# =============================================================================
# The prediction
# =============================================================================


def _label_maps(rules: Sequence[CleaningRuleDTO]) -> tuple[dict[str, str], list[str]]:
    """``{flag label: rule name}`` for the ``VALIDATE`` rules and the ``LLM_CHECK`` rule names."""
    labels = {rule_flag_label(rule): rule.rule_name for rule in rules if rule.rule_kind == "VALIDATE"}
    return labels, [rule.rule_name for rule in rules if rule.rule_kind == "LLM_CHECK"]


def predict_stored(
    db: Session, description_ids: Sequence[str], rules: Sequence[CleaningRuleDTO]
) -> dict[str, set[str]]:
    """
    The rules whose flags the last run already wrote, read from ``anomaly_reasons``.

    Free and over the whole collection, which is what makes it the honest first look: it measures the
    flags the installation already acted on, at the exact threshold the worker used, without asking
    a model anything.
    """
    labels, llm_names = _label_maps(rules)
    stmt = select(ArchiveDocument.description_id, ArchiveDocument.anomaly_reasons).where(
        ArchiveDocument.description_id.in_(list(description_ids))
    )
    out: dict[str, set[str]] = {}
    for description_id, reasons in db.execute(stmt).all():
        fired: set[str] = set()
        for reason in reasons or ():
            code, _, payload = reason.partition(":")
            if code == AnomalyReason.RULE_MATCH and payload in labels:
                fired.add(labels[payload])
            elif code == AnomalyReason.LLM_SUSPECT and llm_names:
                fired.add(llm_names[0])
        out[description_id] = fired
    return out


def predict_live(
    db: Session,
    description_ids: Sequence[str],
    rules: Sequence[CleaningRuleDTO],
    llm_engine: Any | None,
    llm_confidence: float,
) -> dict[str, set[str]]:
    """
    Which rules fire on each document now, through the worker's own two questions.

    The regex is always live: it costs nothing and it is the thing a curator edits. The language model
    is asked only while an ``LLM_CHECK`` rule is active, and the floor is the worker's own.
    """
    compiled = compile_rules([rule for rule in rules if rule.rule_kind == "VALIDATE"])
    labels, llm_names = _label_maps(rules)
    documents = db.scalars(
        select(ArchiveDocument).where(ArchiveDocument.description_id.in_(list(description_ids)))
    ).all()
    out: dict[str, set[str]] = {}
    for doc in documents:
        fired = {labels[label] for label in matched_rule_labels(doc, compiled) if label in labels}
        if llm_names and llm_check_reason(doc, llm_engine, llm_confidence) is not None:
            fired.add(llm_names[0])
        out[doc.description_id] = fired
    return out


# =============================================================================
# The report
# =============================================================================


def report_for(
    predictions: str,
    rows: Sequence[Scored],
    rules: Sequence[CleaningRuleDTO],
    labelled: int,
    missing_from_collection: int,
) -> dict[str, Any]:
    """Everything the run measured, as plain data, so ``--json`` and the print cannot disagree."""
    scored = [row for row in rows if not row.needs_decision]
    scores = score_rules(scored, rules)
    notes: list[str] = []
    ambiguous = len(rows) - len(scored)
    if not scored:
        notes.append("Nada foi pontuado: todas as linhas estão marcadas `needs_decision`, ou o conjunto está vazio.")
    if ambiguous:
        notes.append(
            f"{ambiguous} linha(s) com `needs_decision` ficaram fora do placar: a ambiguidade pertence ao "
            "catálogo de regras e não ao documento."
        )
    if missing_from_collection:
        notes.append(f"{missing_from_collection} linha(s) do gabarito não existem mais na coleção e saíram do placar.")
    if rules and not [score for score in scores if score.measured]:
        notes.append(
            f"Nenhuma regra atingiu o piso de {MIN_POSITIVES} exemplos rotulados: os números abaixo são ruído "
            "com cara de medida, e o relatório se recusa a imprimi-los."
        )
    if predictions == "live" and any(score.kind == "LLM_CHECK" for score in scores):
        notes.append(
            "O `LLM_CHECK` foi perguntado de novo nesta execução; o validador é determinístico só em parte, "
            "então duas execuções podem discordar nos documentos em que o modelo hesita."
        )
    return {
        "predictions": predictions,
        "labelled": labelled,
        "scored": len(scored),
        "needs_decision": ambiguous,
        "missing_from_collection": missing_from_collection,
        "flag_agreement": flag_agreement(scored),
        "rules": [
            {
                "label": score.label,
                "kind": score.kind,
                "support": score.support,
                "fired": score.fired,
                "true_positives": score.true_positives,
                "false_positives": score.false_positives,
                "false_negatives": score.false_negatives,
                "precision": score.precision,
                "recall": score.recall,
                "f1": score.f1,
                "measured": score.measured,
            }
            for score in scores
        ],
        "unmeasured": [score.label for score in scores if not score.measured],
        "misses": [
            {
                "description_id": row.description_id,
                "missing": sorted(row.missing),
                "spurious": sorted(row.spurious),
            }
            for row in scored
            if row.missing or row.spurious
        ],
        "notes": notes,
    }


def summary_table(report: dict[str, Any]) -> str:
    """One line per rule, the measured ones first: the answer is a table, not a paragraph."""
    lines = [
        "| Regra | tipo | suporte | marcou | precisão | recall | F1 |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for entry in report["rules"]:
        if entry["measured"]:
            lines.append(
                f"| `{entry['label']}` | {entry['kind']} | {entry['support']} | {entry['fired']} "
                f"| {entry['precision']:.3f} | {entry['recall']:.3f} | {entry['f1']:.3f} |"
            )
        else:
            lines.append(
                f"| `{entry['label']}` | {entry['kind']} | {entry['support']} | {entry['fired']} "
                "| — | — | — *(não medida)* |"
            )
    return "\n".join(lines)


def print_report(report: dict[str, Any], rule_count: int) -> None:
    """Prints the agreement, the per-rule table and then what the two disagreement kinds are."""
    print()
    print(
        f"Regras ativas com flag: {rule_count} · linhas: {report['labelled']} no conjunto, "
        f"{report['scored']} pontuadas, {report['needs_decision']} com `needs_decision`, "
        f"{report['missing_from_collection']} ausentes do banco · predições: {report['predictions']}"
    )
    print()
    print(f"Concordância do conjunto inteiro de flags: **{report['flag_agreement']:.3f}**")
    print()
    print(summary_table(report))
    print()
    if report["unmeasured"]:
        print(
            f"**Não medidas** (menos de {MIN_POSITIVES} exemplos rotulados): {', '.join(report['unmeasured'])}. "
            "O relatório se recusa a imprimir um F1 de dois documentos."
        )
        print()
    for note in report["notes"]:
        print(f"> {note}")
    if report["misses"]:
        print()
        print(f"**{len(report['misses'])} documento(s) com discordância**, os primeiros 20:")
        print()
        for miss in report["misses"][:20]:
            parts = []
            if miss["missing"]:
                parts.append(f"perdeu {', '.join(miss['missing'])}")
            if miss["spurious"]:
                parts.append(f"marcou a mais {', '.join(miss['spurious'])}")
            print(f"- `{miss['description_id']}`: {'; '.join(parts)}")
    print()


# =============================================================================
# CLI
# =============================================================================


def _today() -> str:
    return date.today().isoformat()


def run_pick(args: argparse.Namespace) -> int:
    """Reads the catalogue and the stored flags, proposes the sample and writes the skeleton."""
    with get_db() as db:
        catalogue = all_rules(db)
        problems = ambiguous_rules([rule for rule in catalogue if rule.is_active])
        if problems:
            raise SystemExit(
                "O catálogo de regras não permite um gabarito sem ambiguidade: "
                + "; ".join(problems)
                + ". Renomeie ou desambigue antes de rotular."
            )
        rules = scorable_rules(catalogue)
        if not rules:
            raise SystemExit(
                "Não há nenhuma regra VALIDATE ou LLM_CHECK **ativa** no catálogo: não há flag para medir. "
                "Este bench mede regras, e a tela de regras é onde elas vivem. Uma regra VALIDATE só "
                "sinaliza; ela não reescreve nada."
            )
        labels, llm_names = _label_maps(rules)
        candidates = read_candidates(db, labels, llm_names)
        db.rollback()

    if args.out.exists() and not args.force:
        raise SystemExit(
            f"'{args.out}' já existe: as etiquetas não têm desfazer. Use --force para sobrescrever, sabendo "
            "que o gabarito anterior se perde."
        )

    sampling = (
        "estratos pelos flags gravados em `anomaly_reasons`; semente "
        f"'{args.seed}'; até {args.per_rule} documento(s) por regra e {args.clean_rows} sem anomalia; "
        "deduplicado pelo título"
    )
    picked = pick(candidates, [rule.rule_name for rule in rules], args.seed, args.per_rule, args.clean_rows)
    payload = build_payload(picked, status="draft — nenhum curador revisou", sampling=sampling)
    payload["collection"] = (
        f"{settings.DB_NAME} — {len(candidates)} descrições lidas, "
        f"{sum(1 for row in candidates if row.stored_reasons)} com alguma anomalia gravada; medido em {_today()}."
    )
    payload["active_rules"] = sorted(rule.rule_name for rule in rules)
    payload["rules_at_labelling"] = [
        {"rule_name": rule.rule_name, "rule_kind": rule.rule_kind, "target_column": rule.target_column}
        for rule in rules
    ]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    logger.success(f"💾 esqueleto escrito em {args.out}")

    for rule in rules:
        pool = sum(1 for row in candidates if row.key == rule.rule_name)
        flag = "⚠️ SEM CANDIDATO" if pool == 0 else ""
        logger.info(f"   {rule.rule_name:<32} {len(picked.get(rule.rule_name, [])):>3} propostos de {pool:>5} {flag}")
    for key in (NO_RULE, CLEAN):
        pool = sum(1 for row in candidates if row.key == key)
        logger.info(f"   {key:<32} {len(picked.get(key, [])):>3} propostos de {pool:>5}")

    print_sheet(payload, args.sheet_out)
    return 0


def run_score(args: argparse.Namespace) -> int:
    """Scores every active scorable rule against the labelled set and prints the comparison."""
    with get_db() as db:
        rules = scorable_rules(all_rules(db))
        if not rules:
            raise SystemExit(
                "Não há nenhuma regra VALIDATE ou LLM_CHECK **ativa** no catálogo: não há flag para medir."
            )
        rows, payload = load_labelled(args.pairs, [rule.rule_name for rule in rules], args.allow_draft)
        if args.status:
            logger.info(f"📄 {args.pairs} · {payload.get('status', '')}")

        present = {
            description_id
            for (description_id,) in db.execute(
                select(ArchiveDocument.description_id).where(
                    ArchiveDocument.description_id.in_([row.description_id for row in rows])
                )
            ).all()
        }
        absent = [row for row in rows if row.description_id not in present]
        if absent:
            logger.warning(f"⚠️ {len(absent)} linha(s) do gabarito não existem mais na coleção e saem do placar.")
        rows = [row for row in rows if row.description_id in present]

        if args.predictions == "stored":
            predicted = predict_stored(db, [row.description_id for row in rows], rules)
        else:
            predicted = predict_live(
                db,
                [row.description_id for row in rows],
                rules,
                build_llm_engine(db, args),
                args.llm_confidence,
            )
        db.rollback()

    scored = [
        Scored(
            description_id=row.description_id,
            expected=row.expected,
            predicted=frozenset(predicted.get(row.description_id, set())),
            needs_decision=row.needs_decision,
        )
        for row in rows
    ]
    report = report_for(args.predictions, scored, rules, labelled=len(rows), missing_from_collection=len(absent))
    print_report(report, rule_count=len(rules))

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(
                {"mode": "quality_validator", "measured_at": _today(), "database": settings.DB_NAME, **report},
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
        description="The quality-validator bench: the active VALIDATE/LLM_CHECK rules, scored one by one."
    )
    parser.add_argument("--pick", action="store_true", help="Propose the sample and write the skeleton.")
    parser.add_argument("--sheet", action="store_true", help="Regenerate the human sheet from the set.")
    parser.add_argument("--out", type=Path, default=DATA_DIR / PAIRS_FILENAME, help="Where the labelled set lives.")
    parser.add_argument("--sheet-out", type=Path, default=DATA_DIR / SHEET_FILENAME, help="Where the sheet goes.")
    parser.add_argument("--pairs", type=Path, default=None, help="The labelled set to score (default: --out).")
    parser.add_argument("--seed", default=DEFAULT_SEED, help="Ordering seed of the sample; recorded in the file.")
    parser.add_argument("--per-rule", type=int, default=DEFAULT_PER_RULE, help="Rows per rule stratum.")
    parser.add_argument("--clean-rows", type=int, default=DEFAULT_CLEAN_ROWS, help=f"Rows for the {CLEAN} bucket.")
    parser.add_argument("--force", action="store_true", help="Overwrite an existing labelled set (discards labels).")
    parser.add_argument(
        "--predictions",
        choices=("live", "stored"),
        default="live",
        help="live runs the regex and the model; stored scores the flags the last run already wrote (free).",
    )
    parser.add_argument(
        "--llm-confidence",
        type=float,
        default=DEFAULT_LLM_CONFIDENCE,
        help="Floor below which the language-model opinion is ignored; the worker's own default.",
    )
    parser.add_argument(
        "--option",
        action="append",
        default=[],
        metavar="CHAVE=VALOR",
        help="Engine override forwarded to the reviewer, like the worker's own --option.",
    )
    parser.add_argument("--allow-draft", action="store_true", help="Score a set whose 'status' is still draft.")
    parser.add_argument("--status", action="store_true", help="Print the set's status line before scoring.")
    parser.add_argument("--json", type=Path, default=None, help="Also write the raw report here.")
    args = parser.parse_args(argv)

    if args.pairs is None:
        args.pairs = args.out
    if args.pick:
        return run_pick(args)
    if args.sheet:
        print_sheet(load_payload(args.pairs), args.sheet_out)
        return 0
    return run_score(args)


if __name__ == "__main__":
    raise SystemExit(main())
