"""
The typology bench (issue #69): the picker that builds its labelled set, and the scorer.

The typology classifier is the only AI worker with no measurement of its own. Nothing in the
repository said whether the model labels a description correctly, how much of the collection it
refuses to label, or whether it collapses the collection onto one typology. Measured in this
checkout on 2026-10-14, the collapse is not a hypothesis:

* On the reference collection (101 descriptions) 92 carried a typology and **78 of them were
  "Planta Arquitetônica"** — including all 21 records of the Fundação Cultural de Curitiba, whose
  titles are "Concerto na Pedreira do Pilarzinho" and "Vista interna das obras do Palácio 29 de
  Março". The catalogue has "Fotografia" and "Audiovisual" for exactly those.
* On the larger collection (4.831 descriptions) the same shape: of the 255 records whose title
  starts with "Registros Fotográficos", 189 were labelled "Fotografia" and **64 were labelled
  "Planta Arquitetônica"**.

A bench that prints accuracy alone would have called that a success. This one prints the label
distribution next to the score, on purpose, because the defect that opened this issue was a
collapse and not a low score.

**The labelled set is human.** ``--pick`` proposes rows by keyword stratum and writes the skeleton;
a curator confirms or corrects every ``expected``. The rows are collection data and are deliberately
not versioned (``testing/evaluation/README.md`` documents the shape); the scoring is what is
versioned.

Three modes, and the split is deliberate (principle VI — the decision, the write and the read are
separate):

``--pick``
    Reads the collection and writes the skeleton of the labelled set. Nothing reaches the database.

``--sheet``
    Regenerates the human sheet from the labelled set, reading the text from the database, so the
    sheet can never disagree with what the scorer will read.

``--collection``
    Samples the **pending queue** and measures what a configuration costs there and what it does to
    the label distribution. No gabarito and no score: the labelled set answers "is it right", and
    this answers "what does it cost on this collection's own mix", which is the half a sample that
    is balanced by construction cannot answer. Nothing reaches the database.

Run it from the repository root, against the real database::

    uv run python -m testing.evaluation.typology_quality --pick
    uv run python -m testing.evaluation.typology_quality --sheet
    uv run python -m testing.evaluation.typology_quality --collection --sample 100 \\
        --config deberta_typology:cpu_local:original_title:0.40 \\
        --config deberta_typology:cpu_local:original_title,admin_bio_history:0.40
"""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import math
import time
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, cast

from sqlalchemy import case, func, literal, select
from sqlalchemy.orm import Session

from scrinalia.core.config import settings
from scrinalia.core.database import get_db
from scrinalia.core.logger import logger
from scrinalia.domains.archive.domain.text_quality import AI_TEXT_COLUMNS
from scrinalia.domains.archive.engines.classification.registry import (
    EngineName,
    PresetName,
    get_engine,
)
from scrinalia.domains.archive.models import ArchiveDocument, ArchiveTypology
from scrinalia.domains.archive.repository import TypologyRepository
from scrinalia.domains.archive.repository.text_quality_repo import (
    TextQualityRepository,
    composed_text_sql,
)
from scrinalia.domains.archive.repository.typology_queue import count_refusals
from scrinalia.domains.archive.workers.worker_typology import (
    count_pending,
    execute,
    pending_conditions,
    producer_identity,
    resolved_parameters,
)
from testing.evaluation import MIN_POSITIVES
from testing.evaluation.dataset import DATA_DIR, load_dataset

PAIRS_FILENAME = "typology_pairs.json"
SHEET_FILENAME = "typology_pairs.sheet.md"

#: Ordering key of the sample. Recorded in ``sampling`` so the same run can be reproduced: the
#: picker sorts every stratum by ``md5(semente:description_id)``, never by insertion order, so a
#: re-run after the collection grew proposes the same rows for the rows that already existed.
DEFAULT_SEED = "scrinalia-typology-v1"

#: The class of "this description has no typology at all". It is not a typology and the catalogue
#: does not name it: it is the bucket that turns "the model abstained" into a measured false
#: positive instead of an invisible one.
NONE_CLASS = "NENHUMA"

#: How many rows one stratum contributes by default, and how many the NENHUMA bucket contributes.
DEFAULT_PER_FORM = 40
DEFAULT_NONE_ROWS = 25

#: How many documents ``--collection`` samples from the pending queue. Measured on 2026-10-14, one
#: document costs ~2 s on the title alone and ~6 s with the archival history, so 100 documents is
#: 3 to 11 minutes per configuration on CPU — enough to price a policy, short enough to re-run.
DEFAULT_SAMPLE = 100

#: The bucket of a sampled document no stratum pattern matches. Named instead of dropped: these
#: items are in the queue and the worker pays for them, and the picker's habit of discarding them
#: belongs to a gabarito that has to be decidable, not to a cost sample that has to be complete.
NO_STRATUM = "(sem estrato)"

#: ``confidence`` is the curator's own certainty, the same vocabulary the subject set uses.
CONFIDENCE_VALUES = ("alta", "media", "baixa")


# =============================================================================
# Label formats: the shape of the hypothesis, which is the bench's instrument
# =============================================================================


def label_bare(name: str) -> str:
    """The catalogue name, which is what the worker sends today and what #30 decided to keep."""
    return name


def label_sentence(name: str) -> str:
    """
    A short proposition around the name, with an article that agrees with ``documento``.

    Gender-invariant **by construction**, and that is not a stylistic choice: Portuguese forces the
    article to agree with the typology ("uma fotografia", "um relatório técnico", "uma planta
    arquitetônica"), the catalogue stores no gender, and no code template can be right for a mixed
    catalogue in any language that has one. The generic noun moves the agreement off the variable.
    """
    return f"um documento do tipo {name}"


def label_trata_de(name: str) -> str:
    """A second proposition phrasing, so a gain cannot be attributed to one wording (#112)."""
    return f"trata de {name.lower()}"


#: The shapes of the candidate label, one entry per format ``--formats`` accepts.
#:
#: **These are the bench's instrument and not a product string.** The product's home for "what
#: proposition does the model read?" is a field **per catalogue row** —
#: ``ArchiveMacroCategory.classifier_label``, composed by ``domain.vocabulary.classifier_labels``,
#: which falls back to the bare name — so the wording belongs to the institution and its language.
#: A proposition hand-written for this catalogue's ten typologies would be collection data inside
#: versioned code, which is why what is measured here is the *shape* and never the wording.
LABEL_FORMATS: dict[str, Callable[[str], str]] = {
    "bare": label_bare,
    "sentence": label_sentence,
    "trata_de": label_trata_de,
}


def formatted_labels(names: Sequence[str], label_format: str) -> dict[str, str]:
    """
    ``{label the model reads: catalogue name}`` for one format — the candidates and the way back.

    One dictionary for both directions, exactly like ``domain.vocabulary.classifier_labels`` returns
    ``{label: category_id}``, and for the same reason: a second structure is a second place where the
    two halves can disagree, and the failure is silent. ``DebertaEngine.classify`` echoes the label it
    was given, so a bench that read the answer without translating it back would compare
    "um documento do tipo Fotografia" against a gabarito written in catalogue names and score every
    row of every formatted run as a miss — a ``0.000`` that reads like a finding about the model and
    is a defect in the harness.

    Two names that format into the same label collapse into one entry, last one wins, which is the
    same rule ``classifier_labels`` documents: the label is what the model sees, so two identical
    labels are indistinguishable to it.
    """
    if label_format not in LABEL_FORMATS:
        raise SystemExit(f"'{label_format}' não é um formato de rótulo. Opções: {sorted(LABEL_FORMATS)}.")
    format_label = LABEL_FORMATS[label_format]
    return {format_label(name): name for name in names}


# =============================================================================
# Strata: the keyword rules that propose rows for a human to confirm
# =============================================================================


@dataclass(frozen=True)
class Stratum:
    """One keyword rule, and the reason it exists."""

    key: str
    pattern: str
    why: str


#: The photographic stratum is checked **before every other rule**, and that order is the whole
#: point: measured on 2026-10-14, every one of the 40 title matches for "ofício" in this collection
#: was a photograph ("Registros Fotográficos - Estofaria em Vila de Ofícios"), and so were the
#: matches for "ata" and "vistoria" ("... - Reunião com o Prefeito Erasto Gaertner"). Hunting the
#: rare forms without excluding the photographs first proposes a gabarito that measures Fotografia
#: forty times.
PHOTO_STRATUM = Stratum(
    key="Fotografia",
    pattern=r"^Registros Fotogr",
    why="The IPPUC fonds is a photographic record: the title prefix is the form, and the bio describes the image.",
)

#: The narrow forms come before the broad one, because the first match wins. "Projeto de Croqui de
#: Terreno" is proposed as Mapa/Croqui and not as Planta; a row the curator disagrees with is
#: corrected, and a row the *catalogue* cannot decide is marked ``needs_decision``.
FORM_STRATA: tuple[Stratum, ...] = (
    Stratum(
        key="Mapa / Croqui Urbanístico",
        pattern=r"croqui|loteamento|zoneamento|arruamento|\mmapa\M|cartograf",
        why="Loteamento, zoneamento and croqui are the urbanistic reading of a plan.",
    ),
    Stratum(
        key="Processo Administrativo",
        pattern=r"\mprocesso\M|licita|autos de infra",
        why="A building-approval process is an administrative file, not the drawing inside it.",
    ),
    Stratum(
        key="Decreto / Lei / Portaria",
        pattern=r"decreto|portaria|\mlei\M|legisla",
        why="Normative acts.",
    ),
    Stratum(
        key="Relatório Técnico",
        pattern=r"relat[óo]rio|laudo|vistoria|diagn[óo]stico",
        why="Studies, inspections and technical opinions.",
    ),
    Stratum(
        key="Ofício / Memorando",
        pattern=r"of[íi]cio|memorando|correspond",
        why="Official correspondence.",
    ),
    Stratum(
        key="Ata de Reunião",
        pattern=r"\mata\M|reuni[ãa]o|delibera",
        why="Records of a meeting; a photograph *of* a meeting is a Fotografia, which is why the photo stratum runs first.",
    ),
    Stratum(
        key="Dossiê Funcional",
        pattern=r"dossi[êe]|funcion[áa]rio|servidor|prontu[áa]rio",
        why="Personnel files.",
    ),
    Stratum(
        key="Audiovisual",
        pattern=r"v[íi]deo|\mfita\M|filme|audiovisual|grava[çc]|microfilme",
        why="Moving image and sound recordings.",
    ),
    Stratum(
        key="Planta Arquitetônica",
        pattern=r"^Projeto|^Planta|fachada",
        why="The dominant form of the SMU fonds: architectural projects and elevations.",
    ),
)

#: The control bucket: descriptions the ten typologies do not cover. Without these rows the bench
#: cannot measure a false positive — a model that labels everything would look perfect.
NONE_STRATUM = Stratum(
    key=NONE_CLASS,
    pattern=r"requerimento|alvar[áa]|certid[ãa]o|escritura|invent[áa]rio|livro|boletim|registro de",
    why="Forms the catalogue has no entry for; the curator confirms that no typology applies.",
)

#: Every stratum in decision order. The first one whose pattern matches owns the row.
STRATA: tuple[Stratum, ...] = (PHOTO_STRATUM, *FORM_STRATA, NONE_STRATUM)


# =============================================================================
# Reading the collection
# =============================================================================


@dataclass
class Row:
    """One item of the collection, the text the worker reads, and the stratum its title proposes."""

    description_id: str
    title: str
    evidence: str
    provenance: str
    input_text: str
    stratum: str | None


#: How much of the description reaches the sheet and the skeleton. The first clause carries the form
#: ("Fachada do Matadouro Municipal do Guabirotuba em reforma"); the rest of a long paragraph is
#: research prose that does not change the label, and it is still in the database for whoever wants it.
EVIDENCE_LIMIT = 400


def _evidence(scope: str | None, bio: str | None, title: str) -> str:
    """
    The text that lets a person decide the form.

    The archival history comes first and ``scope_content`` second, and that order is measured: in this
    collection ``scope_content`` carries the same "Acervo de 35.327 fotografias…" paragraph for the
    3.163 items of the IPPUC fonds, so preferring it made every photographic row look identical — and
    the first run of this picker proposed 3 rows for a stratum with 3.163 candidates. The history is
    the field that describes each item.
    """
    for value in (bio, scope):
        text = " ".join((value or "").split())
        if text and text.lower() != title.strip().lower():
            return text[:EVIDENCE_LIMIT] + ("…" if len(text) > EVIDENCE_LIMIT else "")
    return title


def _stratum_expression() -> Any:
    """
    The stratum of a title, as SQL: the first pattern that matches owns the row.

    One CASE, stated once, because the priority between the strata is what keeps "Fotografia" from
    losing a photograph of a meeting to "Ata de Reunião" — and both the picker and the collection
    sample read it.
    """
    return case(
        *[(ArchiveDocument.original_title.op("~*")(s.pattern), literal(s.key)) for s in STRATA],
        else_=literal(None),
    ).label("stratum")


def read_collection(db: Session) -> list[Row]:
    """
    Every item of the collection, the text the worker reads, and the stratum its title proposes.

    The hierarchy nodes (``node_*``) are out: they are fundos and séries, not items, and the
    classifier never sees them. The text is composed by ``composed_text_sql`` — the very expression
    ``worker_typology.execute`` builds — and not by a Python re-implementation of the columns and the
    approved excerpts: a bench that composed the text itself would measure a text the worker never
    sees (principle IV).
    """
    columns, _threshold = resolved_parameters(None, None, None)
    rules = TextQualityRepository(db).get_active_rules("NER")
    text_expression = composed_text_sql(columns, rules, separator=". ")

    stmt = (
        select(
            ArchiveDocument.description_id,
            ArchiveDocument.original_title,
            ArchiveDocument.scope_content,
            ArchiveDocument.admin_bio_history,
            ArchiveDocument.provenance,
            text_expression.label("input_text"),
            _stratum_expression(),
        )
        .where(ArchiveDocument.description_id.op("!~")("^node_"))
        .order_by(ArchiveDocument.description_id)
    )

    rows: list[Row] = []
    for description_id, title, scope, bio, provenance, input_text, stratum in db.execute(stmt).all():
        clean_title = " ".join((title or "").split())
        rows.append(
            Row(
                description_id=description_id,
                title=clean_title,
                evidence=_evidence(scope, bio, clean_title),
                provenance=" ".join((provenance or "").split()),
                input_text=" ".join((input_text or "").split()),
                stratum=stratum,
            )
        )
    return rows


# =============================================================================
# The picker
# =============================================================================


def _order_key(seed: str, description_id: str) -> str:
    """Deterministic ordering key of the sample: the same seed proposes the same rows."""
    return hashlib.md5(f"{seed}:{description_id}".encode()).hexdigest()


def _one_per_input(rows: list[Row]) -> list[Row]:
    """
    Keeps one row per distinct text the worker reads.

    Measured: the photographic fonds has 3.164 items over **1.240 distinct titles**, and two titles in
    the reference collection repeat ten times each. Two documents with the same input cannot disagree,
    so a second copy adds no measurement and only weights whatever the collection happens to repeat.
    The cap is applied after this, so the sample spreads across events instead of across duplicates.
    """
    seen: set[str] = set()
    kept: list[Row] = []
    for row in rows:
        key = row.input_text.lower()
        if key in seen:
            continue
        seen.add(key)
        kept.append(row)
    return kept


def pick(rows: list[Row], seed: str, per_form: int, none_rows: int) -> dict[str, list[Row]]:
    """
    One sample per stratum, deterministic under ``seed``.

    Every stratum is deduplicated by the text the worker reads, for the reason ``_one_per_input``
    gives; the rare forms are small enough that the cap only bites on Planta and Fotografia.
    """
    pools: dict[str, list[Row]] = {stratum.key: [] for stratum in STRATA}
    unbucketed = 0
    for row in rows:
        if row.stratum is None:
            unbucketed += 1
            continue
        pools[row.stratum].append(row)

    picked: dict[str, list[Row]] = {}
    for stratum in STRATA:
        pool = sorted(pools[stratum.key], key=lambda r: _order_key(seed, r.description_id))
        pool = _one_per_input(pool)
        cap = none_rows if stratum.key == NONE_CLASS else per_form
        picked[stratum.key] = pool[:cap]

    logger.info(f"🔎 {len(rows)} items read · {unbucketed} matched no stratum (outside the sample)")
    return picked


def build_payload(
    picked: dict[str, list[Row]], catalogue: list[str], seed: str, per_form: int, none_rows: int
) -> dict[str, Any]:
    """The skeleton of the labelled set, with the proposal pre-filled for the curator to correct."""
    pairs: list[dict[str, Any]] = []
    for stratum in STRATA:
        for row in picked[stratum.key]:
            pairs.append(
                {
                    "description_id": row.description_id,
                    "candidate": stratum.key,
                    "title": row.title,
                    "evidence": row.evidence,
                    "expected": None if stratum.key == NONE_CLASS else stratum.key,
                    "confidence": None,
                    "needs_decision": False,
                    "note": "",
                }
            )

    counts = {stratum.key: len(picked[stratum.key]) for stratum in STRATA}
    missing = [stratum.key for stratum in STRATA if not picked[stratum.key]]
    sampling = (
        f"Estrato por expressão regular no título, na ordem de STRATA, com o prefixo fotográfico "
        f"({PHOTO_STRATUM.pattern!r}) avaliado ANTES das outras formas: medido em 2026-10-14, os 40 "
        f"casamentos de 'ofício' nesta coleção eram todos fotografias ('Vila de Ofícios'). A semente "
        f"{seed!r} ordena cada estrato por md5(semente:description_id), então o recorte é "
        f"reproduzível. Dentro de cada estrato fica 1 linha por TEXTO DISTINTO que o worker lê "
        f"(título já sem os trechos aprovados): dois documentos com a mesma entrada não podem "
        f"discordar, e o acervo tem 3.164 fotografias sobre 1.240 títulos. "
        f"Teto por estrato: {per_form}; o balde {NONE_CLASS}: {none_rows}. Linhas propostas: {counts}. "
        f"Sem candidato nenhum: {missing or 'nenhuma'} — as formas ausentes não podem ser medidas "
        f"nesta coleção e o relatório tem de imprimir 'não medida' em vez de um F1 de dois exemplos."
    )

    return {
        "description": (
            "Conjunto rotulado do eixo de tipologia documental (issue #69). Cada linha traz o "
            "estrato que a propôs em 'candidate' e o texto que permite decidir; 'expected' é a "
            "verdade do curador, e é ela que a bancada pontua. O rótulo é humano: é isto que separa "
            "este conjunto do que o modelo já escreveu no banco."
        ),
        "collection": "",  # filled by the caller
        "sampling": sampling,
        "catalogue_at_labelling": catalogue,
        "instructions_for_the_curator": [
            "Cada linha vem com o estrato que a propôs em 'candidate'. Se ele estiver certo, não "
            + "mexa em 'expected'; se estiver errado, corrija.",
            "'expected' aceita o nome de uma tipologia, uma LISTA de nomes aceitáveis (quando o "
            + "documento é duas coisas ao mesmo tempo) ou null quando nenhuma tipologia se aplica.",
            "'confidence' é a SUA certeza: alta, media ou baixa.",
            "Marque 'needs_decision': true quando a ambiguidade for do catálogo e não sua — um "
            + "'Projeto de Croqui de Terreno' é Planta ou Mapa? O relatório exclui essas linhas do "
            "placar e as conta em separado, para não punir o modelo por uma pergunta mal feita.",
            "Escreva o motivo em 'note': é a parte que um leitor posterior precisa.",
            "As linhas com 'candidate': 'NENHUMA' são o controle: confirme que nenhuma tipologia se "
            + "aplica, ou dê a elas a tipologia que o catálogo não tem.",
            "Quando terminar, troque 'status' por 'aprovado por <quem> em <data>' e registre em "
            + "'approved_note' o que mudou. A bancada se recusa a pontuar um conjunto 'draft'.",
        ],
        "pairs": pairs,
        "status": "draft — nenhum curador revisou este conjunto ainda",
        "approved_note": "",
    }


def _labelled(payload: dict[str, Any]) -> int:
    """How many rows a human already touched, so a re-run can say what it would discard."""
    return sum(1 for pair in payload.get("pairs", []) if pair.get("confidence") or pair.get("note"))


def write_skeleton(out: Path, payload: dict[str, Any], force: bool) -> None:
    """
    Writes the skeleton, refusing to overwrite a curator's work.

    A re-run of the picker would destroy labels that have no undo, so the default is to refuse. The
    preview of what would die is printed before ``--force`` does it (principle VI).
    """
    if out.exists() and not force:
        existing = json.loads(out.read_text(encoding="utf-8"))
        raise SystemExit(
            f"{out} already exists with {_labelled(existing)} labelled row(s). The labelled set is a "
            "curator's work and re-running the picker would overwrite it. Pass --force only if you "
            "mean to discard it, or point --out at another file."
        )
    if out.exists():
        existing = json.loads(out.read_text(encoding="utf-8"))
        logger.warning(f"⚠️ --force discards {_labelled(existing)} labelled row(s) in {out}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    logger.success(f"💾 skeleton written to {out} ({len(payload['pairs'])} rows, nothing written to the database)")


# =============================================================================
# The sheet
# =============================================================================


def sheet_lines(payload: dict[str, Any], effective_text: dict[str, str]) -> list[str]:
    """The human sheet: what the curator reads to decide each row, in the file's own order."""
    lines = [
        "# Conjunto rotulado de tipologia — folha de revisão",
        "",
        f"Coleção: {payload.get('collection', '')}",
        "",
        f"Status: {payload.get('status', '')}",
        "",
        "`expected` já vem com o estrato que propôs a linha. Corrija o que estiver errado.",
        "",
    ]
    for index, pair in enumerate(payload["pairs"], start=1):
        lines.append(f"## {index}. `{pair['description_id']}` — {pair.get('candidate', '')}")
        lines.append("")
        lines.append(f"- **Título:** {pair.get('title', '')}")
        if pair.get("evidence"):
            lines.append(f"- **Evidência:** {pair['evidence']}")
        text = effective_text.get(pair["description_id"], "")
        if text and text != pair.get("title"):
            lines.append(f"- **Texto que o modelo lê:** {text}")
        expected = pair.get("expected")
        shown = "nenhuma" if expected is None else expected
        lines.append(f"- **esperado:** {shown}   _(confiança: {pair.get('confidence') or '—'})_")
        if pair.get("needs_decision"):
            lines.append("- **decisão de catálogo pendente**")
        if pair.get("note"):
            lines.append(f"- **nota:** {pair['note']}")
        lines.append("")
    return lines


def load_payload(path: Path) -> dict[str, Any]:
    """
    Reads the labelled set, through the shared drawer loader when it lives in the standard place.

    Going through ``dataset.load_dataset`` is what makes a missing file say where it belongs and why
    it is not versioned, instead of a bare ``FileNotFoundError`` whose reflex fix is to re-create the
    set from the code — the one thing that must not happen. An explicit path elsewhere still fails
    with the same instruction.
    """
    if path.parent.resolve() == DATA_DIR.resolve():
        return load_dataset(path.name)
    if not path.exists():
        raise SystemExit(
            f"{path} does not exist. Build it with `--pick`, label it by hand, then score it. The "
            "expected shape is documented in testing/evaluation/README.md."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def print_sheet(payload: dict[str, Any], out: Path) -> None:
    """Writes the sheet next to the labelled set; the text comes from the database, never from the file."""
    ids = [pair["description_id"] for pair in payload["pairs"]]
    columns, _threshold = resolved_parameters(None, None, None)
    with get_db() as db:
        effective = read_input_text(db, ids, columns)
        db.rollback()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(sheet_lines(payload, effective)) + "\n", encoding="utf-8")
    logger.success(f"📄 sheet written to {out} ({len(ids)} rows)")


# =============================================================================
# Metrics — pure functions, no session and no model
# =============================================================================
#
# This is the part a unit test can hold: the arithmetic that turns a list of (truth, prediction)
# into a number. The model and the database are exercised elsewhere, so a defect in the metrics
# cannot hide behind "it needs a GPU".

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
        because the catalogue mixes support and species; without them the bench would score a
        legitimate answer as an error.
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
    return sum(1 for row in rows if row.prediction.label is None) / len(rows) if rows else 0.0


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


# =============================================================================
# Configurations
# =============================================================================


@dataclass(frozen=True)
class BenchConfig:
    """One scored configuration: the same four things ``worker_typology.producer_identity`` signs."""

    engine: str
    preset: str | None
    columns: tuple[str, ...]
    threshold: float

    @property
    def label(self) -> str:
        return f"{self.engine}:{self.preset or '-'}:{','.join(self.columns)}:{self.threshold:.2f}"


def parse_config(text: str, default_columns: tuple[str, ...], default_threshold: float) -> BenchConfig:
    """
    Reads ``engine[:preset[:columns[:threshold]]]``, filling the empty fields from the worker.

    The four fields are exactly what the worker stamps as the producer identity, and that is the
    point: the bench can only measure a configuration the worker can be told to run. The model is
    never named here — a new model is a preset in the engine registry, not an edit to this script.
    """
    parts = text.split(":")
    if len(parts) > 4:
        raise SystemExit(f"--config {text!r} has {len(parts)} fields; expected engine[:preset[:columns[:threshold]]].")
    engine = parts[0].strip()
    if not engine:
        raise SystemExit(f"--config {text!r} names no engine.")
    preset = parts[1].strip() if len(parts) > 1 and parts[1].strip() else None
    columns = (
        tuple(part.strip() for part in parts[2].split(",") if part.strip())
        if len(parts) > 2 and parts[2].strip()
        else default_columns
    )
    try:
        threshold = float(parts[3]) if len(parts) > 3 and parts[3].strip() else default_threshold
    except ValueError as error:
        raise SystemExit(f"--config {text!r} has a threshold that is not a number: {parts[3]!r}") from error

    unknown = [column for column in columns if column not in AI_TEXT_COLUMNS]
    if unknown:
        raise SystemExit(
            f"--config {text!r} names columns the AI text does not have: {unknown}. Known: {AI_TEXT_COLUMNS}"
        )

    return BenchConfig(engine=engine, preset=preset, columns=columns, threshold=threshold)


# =============================================================================
# Simulating a catalogue edit, before it is written
# =============================================================================


def simulated_catalogue(catalogue: Sequence[str], drop: Sequence[str] = (), add: Sequence[str] = ()) -> list[str]:
    """
    The candidate set an experiment reads against, with forms retired or added **by name**.

    A catalogue edit is the identity's business: the label set is part of
    ``worker_typology.producer_identity``, so retiring or adding a form re-reads the whole collection
    (~2.9 h of CPU at the measured 2.2 s per document). That is a lot to pay for a guess, and until
    now the bench could only measure the catalogue that was already live — the decision, the write
    and the read in one act, which principle VI exists to prevent.

    Names are all this needs. The worker maps an answer back to a ``typology_id`` to write it, but the
    bench compares against the gabarito, which is written in names, and the engine only ever echoes
    the label it was handed. So the simulation can be honest without inventing ids for rows the
    database does not have yet — and a name the *active* catalogue does not have is refused rather
    than added, because a typo there would silently measure a catalogue nobody proposed.
    """
    unknown = [name for name in drop if name not in catalogue]
    if unknown:
        raise SystemExit(
            f"--drop-typology nomeia {unknown}, que o catálogo ativo não tem. Ativas: {sorted(catalogue)}."
        )
    kept = [name for name in catalogue if name not in set(drop)]
    for name in add:
        if name in catalogue:
            raise SystemExit(f"--add-typology '{name}' já está no catálogo ativo.")
        if name not in kept:
            kept.append(name)
    return kept


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


def _truth(value: Any, index: int, description_id: str) -> Truth:
    """Validates one ``expected`` field: a name, a list of acceptable names, or null."""
    if value is None:
        return Truth(labels=None)
    if isinstance(value, str):
        if not value.strip():
            raise SystemExit(f"row {index} ({description_id}) has an empty 'expected'.")
        return Truth(labels=frozenset({value.strip()}))
    if isinstance(value, list) and value and all(isinstance(item, str) and item.strip() for item in value):
        return Truth(labels=frozenset(item.strip() for item in value))
    raise SystemExit(
        f"row {index} ({description_id}) has 'expected': {value!r}, which is not a typology name, a "
        "list of acceptable names, or null. The shape is in testing/evaluation/README.md."
    )


def load_labelled(path: Path, catalogue: Sequence[str], allow_draft: bool) -> tuple[list[LabelledRow], dict[str, Any]]:
    """
    Reads the labelled set, refusing a draft unless ``--allow-draft`` says otherwise.

    The human signature is what makes the number quotable: a set nobody reviewed produces a figure
    that reads exactly like a reviewed one, and that is the failure ``status`` exists to prevent.
    """
    payload = load_payload(path)
    status = str(payload.get("status", ""))
    if status.strip().lower().startswith("draft") and not allow_draft:
        raise SystemExit(
            f"{path} still says {status!r}. The bench refuses to score a set no curator signed, "
            "because the number would be quoted as if someone had. Review the rows, write the "
            "signature into 'status', or pass --allow-draft to explore."
        )

    rows: list[LabelledRow] = []
    for index, pair in enumerate(payload.get("pairs", []), start=1):
        if "expected" not in pair:
            raise SystemExit(f"row {index} ({pair.get('description_id')}) has no 'expected' field at all.")
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
                truth=_truth(pair["expected"], index, description_id),
                needs_decision=bool(pair.get("needs_decision", False)),
                note=str(pair.get("note", "")),
            )
        )
    return rows, payload


def unknown_truth_labels(rows: Sequence[LabelledRow], catalogue: Sequence[str]) -> list[str]:
    """
    Typologies the gabarito names that the active catalogue no longer has.

    Reported instead of ignored: the classifier can only answer with an active label, so such a row
    is a guaranteed miss, and the curator has to decide whether the label was retired or mistyped.
    """
    known = set(catalogue)
    named = {label for row in rows for label in (row.truth.labels or ())}
    return sorted(named - known)


# =============================================================================
# Scoring
# =============================================================================


def read_input_text(db: Session, description_ids: Sequence[str], columns: Sequence[str]) -> dict[str, str]:
    """
    The text the worker reads, for these ids and columns.

    Composed by ``composed_text_sql`` — the expression ``worker_typology.execute`` builds — with the
    worker's own scope (``NER``) and separator (``". "``). The pinning test runs the worker with a
    fake engine and compares what it handed to the model with what this function returns for the same
    document: a bench that composed the text itself would measure a text the worker never sees.
    """
    if not description_ids:
        return {}
    rules = TextQualityRepository(db).get_active_rules("NER")
    text_expression = composed_text_sql(columns, rules, separator=". ")
    stmt = select(ArchiveDocument.description_id, text_expression).where(
        ArchiveDocument.description_id.in_(list(description_ids))
    )
    return {description_id: " ".join((text or "").split()) for description_id, text in db.execute(stmt).all()}


def score_stored(db: Session, rows: Sequence[LabelledRow]) -> list[Scored]:
    """
    Scores the typology the last run already wrote, without loading a model.

    This is the "how did the run that shipped do?" question, and it is also the only view that
    covers the whole collection for free. The confidence is not stored, so the floor is not applied
    here: the stored answer *is* the post-threshold outcome.
    """
    ids = [row.description_id for row in rows]
    stmt = (
        select(ArchiveDocument.description_id, ArchiveTypology.name)
        .outerjoin(ArchiveTypology, ArchiveTypology.typology_id == ArchiveDocument.typology_id)
        .where(ArchiveDocument.description_id.in_(ids))
    )
    stored = dict(db.execute(stmt).all())
    return [
        Scored(
            description_id=row.description_id,
            truth=row.truth,
            prediction=Prediction(label=stored.get(row.description_id)),
        )
        for row in rows
    ]


def link_decision(result: dict, threshold: float, lookup: Mapping[str, str] | None = None) -> Prediction:
    """
    The worker's decision about one answer, in one place.

    ``worker_typology.execute`` links a typology only when ``score > confidence_threshold`` —
    strictly — and leaves ``typology_id`` NULL otherwise. Both the scorer and the collection sample
    read the rule from here, because a second copy of the comparison is a second abstention rate, and
    the one the report prints would stop being the one the worker produces (principle IV).

    ``lookup`` translates the label the model echoed back into the catalogue name, which is what a
    label format requires: the engine answers with the label it was handed, and the gabarito is
    written in catalogue names. Without it every row of a formatted run scores as a miss. The worker
    makes the same translation with the same shape of dictionary (``{label: id}``).
    """
    echoed = result["labels"][0]
    label = lookup.get(echoed, echoed) if lookup is not None else echoed
    score = float(result["scores"][0])
    return Prediction(label=label if score > threshold else None, score=score)


def score_live(
    db: Session,
    config: BenchConfig,
    rows: Sequence[LabelledRow],
    limit: int | None = None,
    label_format: str = "bare",
    engine: Any | None = None,
    catalogue: Sequence[str] | None = None,
) -> tuple[list[Scored], float]:
    """
    Runs the engine over the labelled rows and mirrors the worker's decision exactly.

    The mirror matters: the worker links a typology only when ``score > confidence_threshold``
    (strictly), and skips a document whose composed text is empty, stamping it without asking the
    model. A bench that used ``>=`` would report an abstention rate the worker never produces.

    ``label_format`` changes only the candidate labels. ``engine`` lets a caller sweeping several
    formats over one configuration build the model once: the load is a cost of the run, not of an
    answer, and charging it three times would distort the seconds per document the report prints.
    ``catalogue`` is the candidate set to read against; it defaults to the active one, and a caller
    that simulates a catalogue edit passes the simulated set (see :func:`simulated_catalogue`).

    Returns the scored rows and the seconds spent inside the model, so the report can print seconds
    per document instead of an estimate.
    """
    if engine is None:
        engine = get_engine(cast("EngineName", config.engine), cast("PresetName", config.preset))
    candidates = list(catalogue) if catalogue is not None else list(TypologyRepository(db).get_active_typologies())
    if not candidates:
        raise SystemExit("The candidate typology catalogue is empty; there is nothing to classify against.")
    labels = formatted_labels(candidates, label_format)

    selected = list(rows[:limit] if limit else rows)
    texts = read_input_text(db, [row.description_id for row in selected], config.columns)

    scored: list[Scored] = []
    seconds = 0.0
    classified = 0
    batch_size = 8
    for start in range(0, len(selected), batch_size):
        chunk = selected[start : start + batch_size]
        pending = [row for row in chunk if texts.get(row.description_id, "")]
        if pending:
            started = time.perf_counter()
            results = engine.classify([texts[row.description_id] for row in pending], list(labels), batch_size=1)
            seconds += time.perf_counter() - started
            classified += len(pending)
            by_id = {row.description_id: result for row, result in zip(pending, results, strict=True)}
        else:
            by_id = {}
        for row in chunk:
            result = by_id.get(row.description_id)
            if result is None:
                # The worker never asks the model about an empty text; it stamps the document and
                # moves on. Abstaining is the same outcome for the measurement.
                scored.append(
                    Scored(description_id=row.description_id, truth=row.truth, prediction=Prediction(label=None))
                )
                continue
            scored.append(
                Scored(
                    description_id=row.description_id,
                    truth=row.truth,
                    prediction=link_decision(result, config.threshold, labels),
                )
            )
    return scored, (seconds / classified if classified else 0.0)


def stored_collection_distribution(db: Session) -> Counter[str]:
    """
    The distribution of what the last run wrote, over the **whole** collection.

    The sample answers "is it right"; this answers "does it collapse", and the collapse is a property
    of the collection and not of the sample. It is free in the stored mode because it is one query.
    """
    stmt = (
        select(ArchiveTypology.name, func.count())
        .select_from(ArchiveDocument)
        .outerjoin(ArchiveTypology, ArchiveTypology.typology_id == ArchiveDocument.typology_id)
        .where(ArchiveDocument.description_id.op("!~")("^node_"))
        .group_by(ArchiveTypology.name)
    )
    counts: Counter[str] = Counter()
    for name, count in db.execute(stmt).all():
        counts[name or ABSTAINED] += int(count)
    return counts


def stored_mode_note(collection: Counter[str], refused: int) -> str:
    """
    What the stored mode can and cannot say, with the numbers that make it concrete.

    ``typology_id`` is NULL both when the run abstained and when it never reached the document, and
    the column does not say which — so "agreement 0.259" reads as the model's quality when most of it
    is the run's coverage. Since #110 the abstentions the classifier actually looked at are recorded
    in the review queue with the score, so the blanket caveat becomes a measured **split**: the
    abstentions the queue accounts for, against the descriptions no run has reached. The rest of the
    limitation stands and is not dressed up: this mode still serves the collapse, and the ``live``
    mode is what measures the model.
    """
    total = sum(collection.values())
    abstained = collection.get(ABSTAINED, 0)
    answered = total - abstained
    seen = min(refused, abstained)
    return (
        "O modo `stored` lê a coluna `typology_id`, e ela é NULL tanto quando a execução absteve "
        f"quanto quando ela nunca chegou ao documento. Medido agora, {answered} de {total} itens "
        f"carregam tipologia ({answered / max(1, total):.1%}) e, das {abstained} abstenções, {seen} "
        "estão registradas na fila de revisão — o classificador olhou e recusou, com o score que viu "
        "— contra "
        f"{max(0, abstained - seen)} que nenhuma execução alcançou. Este modo serve para o colapso — a "
        "distribuição da coleção inteira, impressa acima — e o modo `live` é o que mede o modelo."
    )


# =============================================================================
# The collection sample: cost and shape, never accuracy
# =============================================================================
#
# The modes above answer "is it right" on rows a human labelled. Neither answers the other half of
# the decision #109 takes: **what does a configuration cost on this collection, and what does it do
# to the label distribution** — measured on the collection's own mix, not on a sample that is
# balanced by construction. This is that measurement, and it is deliberately blind to the gabarito:
# it scores nothing, because these rows have no truth.
#
# Three traps it exists to avoid:
#
# * It does **not** deduplicate by text (``_one_per_input``), unlike the picker. The photographic
#   fonds repeats 3.164 items over 1.240 distinct titles and the worker pays for every item, so a
#   sample of distinct texts would price the collection as if the repeats were free.
# * It samples through the worker's **own** pending predicate (``pending_conditions``) and not
#   through a filter retyped here, and the caller compares the result with ``count_pending`` — the
#   number the panel shows. A sample drawn from a queue the worker does not have measures a run that
#   will not happen.
# * It allocates **proportionally** across the picker's strata, with no floor. A floor of one row per
#   stratum would give 6 rows of a 100-row sample (6%) to the forms that are 41 of the 4.813 items
#   (0.85%), and those are the forms with the longest texts (measured on 2026-10-14: mean 917
#   characters against 472 overall), so a floor would inflate the projected hours.

#: What this mode does not do, said where the numbers are printed and not only in the docstring.
COLLECTION_CAVEAT = (
    "Este modo **não mede acurácia**: as linhas da fila não têm gabarito, e um rótulo errado aqui não "
    "aparece. Ele mede custo e forma — quanto tempo a configuração leva nesta coleção e para onde ela "
    'empurra os rótulos. Quem responde "está certo" é o modo `live`, sobre o conjunto rotulado.'
)


@dataclass(frozen=True)
class SampledRow:
    """One item of the pending queue: the id the text is read for, and the stratum of its title."""

    description_id: str
    stratum: str | None


def collection_identity(config: BenchConfig, typologies: dict[str, int]) -> str:
    """
    The producer identity of one configuration, through the worker's own function.

    The label set comes in because the identity signs it: a bench that composed an identity without
    the catalogue would price a queue the worker does not have (issue #117).
    """
    return producer_identity(
        engine_name=cast("EngineName", config.engine),
        preset=cast("PresetName", config.preset),
        columns_to_classify=list(config.columns),
        confidence_threshold=config.threshold,
        typologies=typologies,
        engine_kwargs={},
    )


def pending_ids(db: Session, config: BenchConfig) -> set[str]:
    """
    The documents this configuration would read, through the worker's own predicate.

    ``pending_conditions`` **is** the queue: it carries the governance guard, the "at least one column
    is not null" clause and the identity stamp — and since #117 the stamp is the only gate on the
    answer side, so a document already classified is pending again under another identity.
    Re-deriving any of those clauses here is how a bench starts measuring a queue the panel does not
    show.
    """
    typologies = TypologyRepository(db).get_active_typologies()
    stmt = select(ArchiveDocument.description_id).where(
        *pending_conditions(list(config.columns), collection_identity(config, typologies))
    )
    return {row[0] for row in db.execute(stmt).all()}


def allocate(counts: dict[str, int], total: int) -> dict[str, int]:
    """
    Largest-remainder allocation of ``total`` samples across the strata, without a floor.

    Pinned by a unit test: an allocation that did not add up to ``total``, or that gave a stratum
    more weight than the collection gives it, would make the projected hours a number about the
    sample instead of about the collection.
    """
    size = sum(counts.values())
    if size == 0 or total <= 0:
        return {}
    exact = {key: total * count / size for key, count in counts.items()}
    allocated = {key: int(value) for key, value in exact.items()}
    remaining = total - sum(allocated.values())
    # The fractional part decides, and the stratum key breaks the tie: the sample stays deterministic
    # under the seed alone, with no dependence on the order the database returned the rows in.
    ranked = sorted(exact, key=lambda key: (-(exact[key] - allocated[key]), key))
    for key in ranked[:remaining]:
        allocated[key] += 1
    return {key: quota for key, quota in allocated.items() if quota > 0}


def sample_queue(
    db: Session, configs: Sequence[BenchConfig], sample: int, seed: str
) -> tuple[list[SampledRow], dict[str, int]]:
    """
    The sampled units, and the size of each configuration's queue.

    The sample is read from the documents pending under **every** requested configuration, so the
    before/after reads the same rows: comparing two configurations on two different sets of documents
    would confound the configuration with the collection. An empty list means the intersection is
    empty, and the queue of each configuration is returned either way so the caller can say which one
    has documents.
    """
    queues = {config.label: pending_ids(db, config) for config in configs}
    common = set.intersection(*queues.values()) if queues else set()
    if not common:
        return [], {label: len(ids) for label, ids in queues.items()}

    stmt = select(ArchiveDocument.description_id, _stratum_expression()).where(
        ArchiveDocument.description_id.in_(list(common))
    )
    by_stratum: dict[str, list[SampledRow]] = {}
    for description_id, stratum in db.execute(stmt).all():
        by_stratum.setdefault(stratum or NO_STRATUM, []).append(
            SampledRow(description_id=description_id, stratum=stratum)
        )

    allocation = allocate({key: len(rows) for key, rows in by_stratum.items()}, sample)
    picked: list[SampledRow] = []
    for key, quota in allocation.items():
        ordered = sorted(by_stratum[key], key=lambda row: _order_key(seed, row.description_id))
        picked.extend(ordered[:quota])
    picked.sort(key=lambda row: row.description_id)
    return picked, {label: len(ids) for label, ids in queues.items()}


def measure_collection(db: Session, configs: Sequence[BenchConfig], rows: Sequence[SampledRow]) -> list[dict[str, Any]]:
    """
    Runs the engine over the sampled rows under every configuration and returns the numbers.

    The engine is built **once per (engine, preset)**: two configurations that differ only in the
    columns or the floor share one model, and loading mDeBERTa again would charge the model load to
    the seconds per document. The rows are processed **grouped by stratum**, which is what makes the
    per-stratum seconds exact: the worker calls the engine with ``batch_size=1``, so no text is
    padded against another and a document's neighbours cannot change its cost.
    """
    catalogue = list(TypologyRepository(db).get_active_typologies())
    if not catalogue:
        raise SystemExit("The active typology catalogue is empty; there is nothing to classify against.")
    engines: dict[tuple[str, str | None], Any] = {}

    def engine_for(config: BenchConfig) -> Any:
        """One engine per (engine, preset): a second configuration of the same model reuses it."""
        key = (config.engine, config.preset)
        if key not in engines:
            engines[key] = get_engine(cast("EngineName", config.engine), cast("PresetName", config.preset))
        return engines[key]

    grouped: dict[str, list[SampledRow]] = {}
    for row in rows:
        grouped.setdefault(row.stratum or NO_STRATUM, []).append(row)

    reports: list[dict[str, Any]] = []
    for config in configs:
        engine = engine_for(config)
        texts = read_input_text(db, [row.description_id for row in rows], config.columns)
        counts: Counter[str] = Counter()
        strata: dict[str, dict[str, Any]] = {}
        seconds = 0.0
        classified = 0
        characters = 0
        batch_size = 8
        for stratum, group in grouped.items():
            entry: dict[str, Any] = {"n": len(group), "classified": 0, "seconds": 0.0, "abstained": 0, "characters": 0}
            for start in range(0, len(group), batch_size):
                chunk = group[start : start + batch_size]
                asked = [row for row in chunk if texts.get(row.description_id, "")]
                if asked:
                    started = time.perf_counter()
                    results = engine.classify([texts[row.description_id] for row in asked], catalogue, batch_size=1)
                    elapsed = time.perf_counter() - started
                    chunk_characters = sum(len(texts[row.description_id]) for row in asked)
                    seconds += elapsed
                    characters += chunk_characters
                    classified += len(asked)
                    entry["seconds"] += elapsed
                    entry["characters"] += chunk_characters
                    entry["classified"] += len(asked)
                    for result in results:
                        counts[link_decision(result, config.threshold).label or ABSTAINED] += 1
                for row in chunk:
                    if not texts.get(row.description_id, ""):
                        # The worker never asks the model about an empty text; it stamps the
                        # document and moves on. Abstaining is the same outcome for the measurement.
                        counts[ABSTAINED] += 1
                        entry["abstained"] += 1
            entry["seconds_per_document"] = entry["seconds"] / entry["classified"] if entry["classified"] else 0.0
            entry["mean_characters"] = entry["characters"] / entry["classified"] if entry["classified"] else 0.0
            strata[stratum] = entry
        reports.append(
            {
                "config": config.label,
                "engine": config.engine,
                "preset": config.preset,
                "columns": list(config.columns),
                "threshold": config.threshold,
                "sampled": len(rows),
                "classified": classified,
                "seconds_per_document": seconds / classified if classified else 0.0,
                "mean_characters": characters / classified if classified else 0.0,
                "abstention_rate": counts[ABSTAINED] / len(rows) if rows else 0.0,
                "distribution": dict(counts),
                "largest_share": list(largest_share(counts)),
                "entropy_bits": entropy_bits(counts),
                "by_stratum": dict(sorted(strata.items())),
            }
        )
    return reports


def collection_summary_table(reports: Sequence[dict[str, Any]], queues: dict[str, int]) -> str:
    """The comparison: one line per configuration, with the queue projected from the sample."""
    lines = [
        "| Configuração | fila | amostra | s/doc | projeção (1 worker) | abstenção | maior gaveta |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for report in reports:
        label, share = report["largest_share"]
        queue = queues.get(report["config"], 0)
        hours = queue * report["seconds_per_document"] / 3600
        lines.append(
            f"| `{report['config']}` | {queue} | {report['sampled']} | {report['seconds_per_document']:.2f} "
            f"| {hours:.1f} h | {report['abstention_rate']:.1%} | {label} ({share:.0%}) |"
        )
    return "\n".join(lines)


def collection_detail_lines(report: dict[str, Any], queue: int) -> list[str]:
    """Per-configuration detail: the strata it pays for and where the labels land."""
    projected = queue * report["seconds_per_document"] / 3600
    empty = report["sampled"] - report["classified"]
    lines = [
        f"### `{report['config']}`",
        "",
        f"- colunas: {', '.join(report['columns'])} · limiar: {report['threshold']:.2f} · fila: {queue}",
        f"- amostra: {report['sampled']} documento(s), {report['classified']} classificado(s) "
        f"({empty} sem texto) · texto lido: {report['mean_characters']:.0f} caracteres em média",
        f"- segundos por documento: **{report['seconds_per_document']:.2f}** · projeção para a fila: "
        f"**{projected:.1f} h**",
        f"- abstenção: {report['abstention_rate']:.1%} · entropia: {report['entropy_bits']:.2f} bits",
        "",
        "| estrato | n | s/doc | caracteres | abstenção |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for key, entry in report["by_stratum"].items():
        lines.append(
            f"| {key} | {entry['n']} | {entry['seconds_per_document']:.2f} | {entry['mean_characters']:.0f} "
            f"| {entry['abstained'] / max(1, entry['n']):.0%} |"
        )
    lines += ["", "| rótulo | n | % da amostra | projeção na fila |", "| --- | ---: | ---: | ---: |"]
    for bucket, count in sorted(report["distribution"].items(), key=lambda item: (-item[1], item[0])):
        share = count / max(1, report["sampled"])
        lines.append(f"| {bucket} | {count} | {share:.1%} | {round(queue * share)} |")
    lines.append("")
    return lines


def print_collection_report(reports: Sequence[dict[str, Any]], queues: dict[str, int], sample: int, seed: str) -> None:
    """Prints the comparison first, then the strata and the labels, then what was not measured."""
    print()
    print(
        f"Fila pendente medida em {date.today().isoformat()} · amostra de {sample} documento(s) por "
        f"estrato proporcional · semente `{seed}`"
    )
    print()
    print(collection_summary_table(reports, queues))
    print()
    for label, size in queues.items():
        print(f"   fila de `{label}`: {size} pendente(s)")
    print()
    for report in reports:
        print("\n".join(collection_detail_lines(report, queues.get(report["config"], 0))))
    print(f"> {COLLECTION_CAVEAT}")
    print()


# =============================================================================
# Report
# =============================================================================


def report_for(
    config: BenchConfig,
    scored: Sequence[Scored],
    catalogue: Sequence[str],
    labelled: int,
    needs_decision: int,
    missing: int,
    seconds_per_document: float,
    min_positives: int,
    predictions: str,
    label_format: str = "bare",
) -> dict[str, Any]:
    """Everything the decision needs about one configuration, as data the JSON can carry."""
    metrics = per_class(scored, catalogue, min_positives)
    counts = distribution(scored)
    label, share = largest_share(counts)
    return {
        "config": config.label,
        "label_format": label_format,
        "catalogue": sorted(catalogue),
        "engine": config.engine,
        "preset": config.preset,
        "columns": list(config.columns),
        "threshold": config.threshold,
        "predictions": predictions,
        "rows": {
            "labelled": labelled,
            "scored": len(scored),
            "needs_decision": needs_decision,
            "missing_from_collection": missing,
        },
        "agreement": agreement(scored),
        "macro_f1": macro_f1(metrics),
        "measured_classes": sum(1 for metric in metrics.values() if metric.measured),
        "abstention_rate": abstention_rate(scored),
        "largest_share": [label, share],
        "entropy_bits": entropy_bits(counts),
        "seconds_per_document": seconds_per_document,
        "distribution": dict(counts),
        "confusion": {
            f"{truth} → {predicted}": count for (truth, predicted), count in sorted(confusion(scored).items())
        },
        "classes": [
            {
                "label": metric.label,
                "support": metric.support,
                "precision": metric.precision,
                "recall": metric.recall,
                "f1": metric.f1,
                "measured": metric.measured,
            }
            for metric in sorted(metrics.values(), key=lambda m: (-m.support, m.label))
        ],
        "unmeasured": [metric.label for metric in metrics.values() if not metric.measured],
        "notes": [],
        "misses": [
            {
                "description_id": row.description_id,
                "expected": row.truth_key,
                "predicted": row.key,
                "score": row.prediction.score,
            }
            for row in scored
            if not row.correct
        ],
    }


def _f1(report: dict[str, Any]) -> str:
    """
    Macro-F1, or an em dash when no class was measured.

    "0.000" next to "no class was measured" reads like a bad model, when the truth is that this
    collection does not have the examples. The dash says which of the two it is.
    """
    return f"{report['macro_f1']:.3f}" if report.get("measured_classes") else "—"


def summary_table(reports: Sequence[dict[str, Any]]) -> str:
    """The comparison: one line per configuration, ordered by agreement."""
    lines = [
        "| Configuração | Formato | Concordância | Macro-F1 | Abstenção | Maior gaveta | Entropia (bits) | s/doc |",
        "| --- | --- | ---: | ---: | ---: | --- | ---: | ---: |",
    ]
    for report in sorted(reports, key=lambda r: -r["agreement"]):
        label, share = report["largest_share"]
        lines.append(
            f"| `{report['config']}` | `{report['label_format']}` | {report['agreement']:.3f} | {_f1(report)} "
            f"| {report['abstention_rate']:.3f} | {label} ({share:.0%}) | {report['entropy_bits']:.2f} "
            f"| {report['seconds_per_document']:.2f} |"
        )
    return "\n".join(lines)


def detail_lines(report: dict[str, Any]) -> list[str]:
    """Per-configuration detail: the per-typology table, the confusion matrix and the misses."""
    rows = report["rows"]
    lines = [
        f"### `{report['config']}` · `{report['label_format']}`",
        "",
        f"- predições: **{report['predictions']}** · limiar: {report['threshold']:.2f} · colunas: {', '.join(report['columns'])}",
        f"- candidatos ({len(report['catalogue'])}): {', '.join(report['catalogue'])}",
        f"- linhas: {rows['labelled']} no conjunto, {rows['scored']} pontuadas, "
        f"{rows['needs_decision']} com `needs_decision` (fora do placar), {rows['missing_from_collection']} ausentes do banco",
        f"- concordância: **{report['agreement']:.3f}** · macro-F1 (classes medidas): {_f1(report)}",
        f"- abstenção: {report['abstention_rate']:.3f} · maior gaveta: {report['largest_share'][0]} "
        f"({report['largest_share'][1]:.0%}) · entropia: {report['entropy_bits']:.2f} bits",
        f"- segundos por documento: {report['seconds_per_document']:.2f}",
        "",
    ]
    lines += [f"> {note}" for note in report.get("notes", [])]
    if report.get("notes"):
        lines.append("")
    lines += [
        "| Tipologia | suporte | precisão | recall | F1 |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for entry in report["classes"]:
        if entry["measured"]:
            lines.append(
                f"| {entry['label']} | {entry['support']} | {entry['precision']:.3f} "
                f"| {entry['recall']:.3f} | {entry['f1']:.3f} |"
            )
        else:
            lines.append(f"| {entry['label']} | {entry['support']} | — | — | — *(não medida)* |")
    if report["unmeasured"]:
        lines += [
            "",
            f"**Não medidas** (menos de {MIN_POSITIVES} exemplos rotulados): {', '.join(report['unmeasured'])}. "
            "Estas formas não existem nesta coleção em quantidade suficiente e o relatório se recusa a "
            "imprimir um F1 de dois exemplos.",
        ]

    lines += ["", "| gabarito \\ predito |", "| --- |"] if report["confusion"] else []
    for cell, count in report["confusion"].items():
        lines.append(f"| {cell} | {count} |")

    if report["misses"]:
        lines += ["", f"**{len(report['misses'])} discordância(s)**, as primeiras 20:", ""]
        lines += [
            f"- `{miss['description_id']}`: gabarito **{miss['expected']}**, resposta **{miss['predicted']}**"
            + (f" (confiança {miss['score']:.3f})" if miss["score"] is not None else "")
            for miss in report["misses"][:20]
        ]
    lines.append("")
    return lines


def print_report(reports: Sequence[dict[str, Any]], collection: Counter[str] | None) -> None:
    """Prints the comparison first and the detail after, so the table is the answer and not a preface."""
    print()
    print(summary_table(reports))
    print()
    if collection:
        label, share = largest_share(collection)
        print(
            f"Coleção inteira, o que a última execução gravou: {sum(collection.values())} itens · "
            f"maior gaveta {label} ({share:.0%}) · entropia {entropy_bits(collection):.2f} bits"
        )
        for bucket, count in collection.most_common():
            print(f"   {bucket:<28} {count:>5}  {count / max(1, sum(collection.values())):>5.1%}")
        print()
    for report in reports:
        print("\n".join(detail_lines(report)))


# =============================================================================
# CLI
# =============================================================================


def _today() -> str:
    return date.today().isoformat()


def run_pick(out: Path, sheet_out: Path, seed: str, per_form: int, none_rows: int, force: bool) -> int:
    """Reads the collection, proposes the sample and writes the skeleton and its sheet."""
    with get_db() as db:
        rows = read_collection(db)
        catalogue = list(TypologyRepository(db).get_active_typologies())
        db.rollback()

    known = {stratum.key for stratum in STRATA if stratum.key != NONE_CLASS}
    unknown = sorted(known - set(catalogue))
    if unknown:
        raise SystemExit(
            f"The strata name {unknown}, which the active typology catalogue does not have "
            f"({catalogue}). The picker proposes by the catalogue's own names on purpose: rename a "
            "typology and this is the sentence that tells you, instead of a sample of rows that "
            "quietly mean nothing."
        )

    picked = pick(rows, seed, per_form, none_rows)
    payload = build_payload(picked, catalogue, seed, per_form, none_rows)
    payload["collection"] = (
        f"{settings.DB_NAME} — {len(rows)} itens de archive_documents (nós de hierarquia excluídos), "
        f"catálogo ativo com {len(catalogue)} tipologias; medido em {_today()}."
    )
    payload["catalogue_at_labelling"] = catalogue
    write_skeleton(out, payload, force)

    for stratum in STRATA:
        count = len(picked[stratum.key])
        candidates = sum(1 for row in rows if row.stratum == stratum.key)
        flag = "⚠️ SEM CANDIDATO" if candidates == 0 else ""
        logger.info(f"   {stratum.key:<26} {count:>3} propostos de {candidates:>5} candidatos {flag}")

    print_sheet(payload, sheet_out)
    return 0


def run_sheet(pairs: Path, sheet_out: Path) -> int:
    """Regenerates the sheet from the labelled set already on disk."""
    print_sheet(load_payload(pairs), sheet_out)
    return 0


def worker_default_config() -> str:
    """
    The configuration the worker runs with when nobody says otherwise, read from its own signature.

    Retyping ``"deberta_typology:cpu_local"`` here would be a second definition of the worker's
    default, and the day it changes the bench would keep scoring the old one while calling it "the
    current configuration".
    """
    parameters = inspect.signature(execute).parameters
    return f"{parameters['engine_name'].default}:{parameters['preset'].default}"


def run_score(args: argparse.Namespace) -> int:
    """Scores every requested configuration against the labelled set and prints the comparison."""
    default_columns, default_threshold = resolved_parameters(None, None, None)
    configs = [parse_config(text, tuple(default_columns), default_threshold) for text in args.config]

    with get_db() as db:
        catalogue = list(TypologyRepository(db).get_active_typologies())
        rows, payload = load_labelled(args.pairs, catalogue, args.allow_draft)
        missing = unknown_truth_labels(rows, catalogue)
        # The gabarito is written against the catalogue that exists, so it is validated against that
        # one; the scoring runs against the simulated set, which is the point of the experiment.
        candidates = simulated_catalogue(catalogue, args.drop_typology, args.add_typology)
        if candidates != catalogue:
            logger.warning(
                f"⚠️ catálogo SIMULADO: -{args.drop_typology or '[]'} +{args.add_typology or '[]'} → "
                f"{len(candidates)} forma(s). Nada foi escrito no banco."
            )
        if missing:
            logger.warning(
                f"⚠️ o gabarito nomeia {missing}, que o catálogo ativo não tem: estas linhas são erro "
                "garantido do modelo. Decida se a tipologia foi aposentada ou se o nome saiu errado."
            )
        if args.status:
            logger.info(f"📄 {args.pairs} · {payload.get('status', '')}")

        scored_rows = [row for row in rows if not row.needs_decision]
        needs_decision = len(rows) - len(scored_rows)
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
        scored_rows = [row for row in scored_rows if row.description_id in present]

        reports: list[dict[str, Any]] = []
        engines: dict[tuple[str, str | None], Any] = {}
        for config in configs:
            for label_format in args.formats:
                if args.predictions == "stored":
                    scored = score_stored(db, scored_rows)
                    seconds = 0.0
                else:
                    to_score = min(len(scored_rows), args.limit) if args.limit else len(scored_rows)
                    logger.info(
                        f"🧠 {config.label} · formato `{label_format}`: carregando o motor e classificando "
                        f"{to_score} linha(s)..."
                    )
                    # One model per configuration, not per format: the load is the run's cost and
                    # charging it to every format would inflate the seconds per document the report
                    # prints, which is the number the decision about cost rests on.
                    key = (config.engine, config.preset)
                    if key not in engines:
                        engines[key] = get_engine(cast("EngineName", config.engine), cast("PresetName", config.preset))
                    scored, seconds = score_live(
                        db,
                        config,
                        scored_rows,
                        limit=args.limit,
                        label_format=label_format,
                        engine=engines[key],
                        catalogue=candidates,
                    )
                reports.append(
                    report_for(
                        config,
                        scored,
                        candidates,
                        labelled=len(rows),
                        needs_decision=needs_decision,
                        missing=len(absent),
                        seconds_per_document=seconds,
                        min_positives=args.min_positives,
                        predictions=args.predictions,
                        label_format=label_format,
                    )
                )
        collection = stored_collection_distribution(db) if args.predictions == "stored" else None
        if collection is not None:
            for report in reports:
                report["notes"].append(stored_mode_note(collection, count_refusals(db)))
        db.rollback()

    print_report(reports, collection)

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps({"reports": reports, "collection": dict(collection or {})}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        logger.success(f"💾 relatório escrito em {args.json}")
    return 0


def run_collection(args: argparse.Namespace) -> int:
    """
    Measures cost and shape of every requested configuration on the pending queue.

    Nothing is written and nothing is scored. The two things it checks while it measures are worth
    printing: the size of each configuration's queue against ``count_pending`` (the worker's own
    counter, and the number the panel shows), and how many documents the two configurations share —
    a before/after that reads the same rows is the only one that isolates the columns.
    """
    default_columns, default_threshold = resolved_parameters(None, None, None)
    configs = [parse_config(text, tuple(default_columns), default_threshold) for text in args.config]

    with get_db() as db:
        rows, queues = sample_queue(db, configs, args.sample, args.seed)
        if not rows:
            raise SystemExit(
                "Nada pendente sob **todas** as configurações pedidas: não há acervo para medir. "
                f"Filas: {queues}. O modo `stored` mede o que já foi gravado, sem modelo."
            )
        counters = {
            config.label: count_pending(
                db,
                columns_to_classify=list(config.columns),
                confidence_threshold=config.threshold,
                engine_name=cast("EngineName", config.engine),
                preset=cast("PresetName", config.preset),
            )
            for config in configs
        }
        db.rollback()
        for label, size in counters.items():
            if size != queues[label]:
                logger.warning(
                    f"⚠️ `{label}`: a interseção amostrável tem {queues[label]} documento(s) e "
                    f"`count_pending` responde {size}. A projeção usa {size}; a amostra é a interseção."
                )
        logger.info(f"🧠 classificando {len(rows)} documento(s) sob {len(configs)} configuração(ões)...")
        reports = measure_collection(db, configs, rows)
        db.rollback()

    print_collection_report(reports, counters, args.sample, args.seed)

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(
                {
                    "mode": "collection",
                    "measured_at": _today(),
                    "seed": args.seed,
                    "sample": args.sample,
                    "queues": counters,
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
    parser = argparse.ArgumentParser(description="The typology bench: pick the labelled set, then score it.")
    parser.add_argument("--pick", action="store_true", help="Propose the sample and write the skeleton.")
    parser.add_argument("--sheet", action="store_true", help="Regenerate the human sheet from the labelled set.")
    parser.add_argument(
        "--collection",
        action="store_true",
        help="Sample the pending queue, measure cost and label shape; no gabarito, nothing written.",
    )
    parser.add_argument("--out", type=Path, default=DATA_DIR / PAIRS_FILENAME, help="Where the labelled set lives.")
    parser.add_argument("--sheet-out", type=Path, default=DATA_DIR / SHEET_FILENAME, help="Where the sheet goes.")
    parser.add_argument("--seed", default=DEFAULT_SEED, help="Ordering seed of the sample; recorded in the file.")
    parser.add_argument("--per-form", type=int, default=DEFAULT_PER_FORM, help="Rows per stratum.")
    parser.add_argument("--none-rows", type=int, default=DEFAULT_NONE_ROWS, help=f"Rows for the {NONE_CLASS} bucket.")
    parser.add_argument("--force", action="store_true", help="Overwrite an existing labelled set (discards labels).")
    parser.add_argument(
        "--sample", type=int, default=DEFAULT_SAMPLE, help="Documents --collection samples from the pending queue."
    )
    parser.add_argument("--pairs", type=Path, default=None, help="The labelled set to score (default: --out).")
    parser.add_argument(
        "--config",
        action="append",
        default=[],
        metavar="ENGINE[:PRESET[:COLUMNS[:THRESHOLD]]]",
        help="A configuration to score; repeat it to compare. Default: the worker's own.",
    )
    parser.add_argument(
        "--predictions",
        choices=("live", "stored"),
        default="live",
        help="live runs the engine; stored scores the typology the last run already wrote (free, whole collection).",
    )
    parser.add_argument(
        "--drop-typology",
        nargs="+",
        default=[],
        metavar="NOME",
        help=(
            "Simulate retiring a form: it leaves the candidate set and nothing is written to the "
            "database. A catalogue edit is part of the producer identity, so the real one re-reads the "
            "whole collection; this measures the effect first."
        ),
    )
    parser.add_argument(
        "--add-typology",
        nargs="+",
        default=[],
        metavar="NOME",
        help="Simulate registering a form, by name, so a proposed drawer can be measured before it exists.",
    )
    parser.add_argument(
        "--formats",
        nargs="+",
        default=list(LABEL_FORMATS),
        choices=list(LABEL_FORMATS),
        help=(
            "Label shapes to compare, all in one invocation; the default is every one of them. "
            "The format is a dimension of the experiment and NOT a field of --config, because "
            "producer_identity does not sign it today: a format the bench could not hand the worker "
            "would be a number about a configuration that does not exist."
        ),
    )
    parser.add_argument("--limit", type=int, default=None, help="Cap the rows the live model sees, for a trial.")
    parser.add_argument("--min-positives", type=int, default=MIN_POSITIVES, help="Below this, a class is 'não medida'.")
    parser.add_argument("--allow-draft", action="store_true", help="Score a set whose 'status' is still draft.")
    parser.add_argument("--status", action="store_true", help="Print the set's status line before scoring.")
    parser.add_argument("--json", type=Path, default=None, help="Also write the raw report here.")
    args = parser.parse_args(argv)

    if args.pairs is None:
        args.pairs = args.out
    if args.pick:
        return run_pick(args.out, args.sheet_out, args.seed, args.per_form, args.none_rows, args.force)
    if args.sheet:
        return run_sheet(args.out, args.sheet_out)
    if not args.config:
        args.config = [worker_default_config()]
    if args.collection:
        return run_collection(args)
    return run_score(args)


if __name__ == "__main__":
    raise SystemExit(main())
