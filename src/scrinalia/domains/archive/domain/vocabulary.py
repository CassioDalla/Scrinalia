"""
The subject vocabulary of the archive and what is deliberately *not* a subject.

Two measured facts made this module necessary (Fase 1.5, defeito 2/2):

1. **The five drawers registered for the IPPUC/SMU records do not cover the collection.**
   ``igrejas`` reaches 2.467 documents — the largest tag of the archive — and there was no
   "Religião" for it, so the model had no choice but ``Instituição``. No label format fixes
   a missing drawer.
2. **Two of those five were never subjects.** ``Instituição`` (``ippuc`` 2.376 docs, ``pmc``
   269) and ``Localidade`` (``curitiba`` 1.865, ``centro`` 464) describe provenance and
   geography. Sharing a slot with ``alvenaria`` is what produced "``alvenaria`` is
   Mobilidade".

So the vocabulary is split in three: subject drawers, facets, and terms that are not a
subject at all. The evidence for every family lives in
``testing/evaluation/macro_category_vocabulary.py``, which produced the proposal the curator
approved; this module is the approved result, and the classifier reads it instead of the
raw tag list.

**Nothing here classifies anything.** It states which drawers exist and which tags are
statements about something other than a subject. Deciding is still the archivist's.
"""

import hashlib
import re

#: The subject drawers, in the order the tree of the archive reads. Populated by the
#: ``subjects`` migration; the names are the curation decision, not an engineering one.
SUBJECT_CATEGORIES: tuple[str, ...] = (
    "Urbanismo e Arquitetura",
    "Mobilidade e Transporte",
    "Religião",
    "Meio Ambiente e Áreas Verdes",
    "Economia e Comércio",
    "Educação e Cultura",
    "Patrimônio e Preservação",
    "Assistência e Questões Sociais",
)

#: Drawers that existed before this vocabulary and **leave** the subject axis. Deactivated
#: rather than deleted: the FK is ``ON DELETE SET NULL``, so deleting would silently orphan
#: the tags while erasing the record that the drawer existed, and deactivating already hides
#: it from the worker (which reads ``is_active`` only).
RETIRED_CATEGORIES: tuple[str, ...] = (
    "Pessoa",
    "Localidade",
    "Instituição",
)

#: A placeholder the origin wrote where no value existed (``local não identificado``).
_PLACEHOLDER = re.compile(
    r"^(não identificad[oa]|local não identificad[oa]|localização não identificad[oa]|"
    r"sem identificação|ilegível|não possui|não informado)$",
    re.IGNORECASE,
)

#: A bare year. ``1924`` reached 260 documents and was classified as "Mobilidade e
#: Transporte" with **0.73** confidence — a threshold cannot catch that, because the model
#: is confidently wrong.
_YEAR = re.compile(r"^(1[89]\d{2}|20\d{2})$")

#: A bare number, optionally followed by a unit (``303 anos``).
_MEASURE = re.compile(r"^\d+(\s*(anos?|meses?|metros?|m|km|nº\.?\s*\d*))?$", re.IGNORECASE)

#: Street and address prefixes. These are **places**, not non-subjects: the curator decided
#: (2026-10-04) that a street with a number goes to the ``PLACE`` facet rather than being
#: discarded, because the search already reaches the term and the facet says more than
#: silence would. ``is_subject_candidate`` returns ``False`` for them — they must not be
#: *classified* — while ``is_place_term`` returns ``True``, which is where they go.
_STREET = re.compile(
    r"^(rua|r\.|avenida|av\.|alameda|travessa|tv\.|rodovia|estrada|largo|praça|pça\.?|"
    r"br[-\s]?\d+|km\s*\d+)",
    re.IGNORECASE,
)

#: A person name. Deliberately *not* a subject drawer: a name is the author or the person
#: depicted, the same reasoning that moved ``Instituição`` out of the axis. Kept explicit
#: because the old vocabulary had a ``Pessoa`` drawer and its removal must be visible.
_PERSON_SUFFIX = re.compile(
    r"^(jaime lerner|oscar niemeyer|lúcio costa|mário de miranda|joel rocha|poty lazzarotto|"
    r"tadeusz kościuszko|ernesto guaita|lina faria|michelangelo cuniberti|marilia kranz|"
    r"paulo spzak|eduardo fernando chaves|aristeu dias|joão zaco paraná|abrão assad)$",
    re.IGNORECASE,
)


def is_placeholder(term: str) -> bool:
    """True for the spellings the origin wrote where there was no value at all."""
    return bool(_PLACEHOLDER.match(term.strip()))


def is_year(term: str) -> bool:
    """True for a bare year, which is a date the ingestion failed to place in a date column."""
    return bool(_YEAR.match(term.strip()))


def is_measure(term: str) -> bool:
    """True for a bare number or a number with a unit."""
    return bool(_MEASURE.match(term.strip()))


def is_street(term: str) -> bool:
    """True for a street/address spelling. A place, never a subject."""
    return bool(_STREET.match(term.strip()))


def is_person_name(term: str) -> bool:
    """True for a term the old ``Pessoa`` drawer held; a producer, not a subject."""
    return bool(_PERSON_SUFFIX.match(term.strip()))


def is_subject_candidate(term: str) -> bool:
    """
    Whether the term may be sent to the subject classifier at all.

    The deterministic guard that makes the ``NENHUMA`` class real without asking the model
    to abstain. Measured on the collection, this removes roughly 1.600 documents from the
    subject axis that today receive a confident wrong answer: every bare year (``1924`` with
    0.73), every placeholder (``local não identificado``, 166 documents) and every street.

    Being a pure function of the spelling is the point: it cannot hallucinate, it costs no
    inference, and its verdict is pinned by tests instead of by a threshold.

    Note that a street is *excluded here* and then claimed by ``is_place_term``: "not a
    subject" and "goes nowhere" are different statements, and the facet is where the street
    goes.
    """
    return not (is_placeholder(term) or is_year(term) or is_measure(term) or is_street(term) or is_person_name(term))


#: The guard's verdicts, as codes. Declared once because the suggestion route publishes them and
#: the screen translates them: a bare string in two places would drift.
SUBJECT_EXCLUSION_SIGNALS: tuple[str, ...] = ("PLACEHOLDER", "YEAR", "MEASURE", "STREET", "PERSON")


def subject_exclusion_signal(term: str) -> str | None:
    """
    Which shape of non-subject the guard recognised, or ``None`` when it recognises nothing.

    ``is_subject_candidate`` answers yes/no and is what the classifier obeys; this answers *why*,
    and it is what the suggestion route publishes. The two share this one function so the reason a
    term is skipped in the worker is the reason the catalogue shows — the guard's verdicts were
    applied silently for months, and 1.489 of the 8.155 real tags are refused by it without the
    archivist being able to see it anywhere.

    Order matters and mirrors ``is_subject_candidate``: a term that is both a year and a street is
    reported as the first shape that matched, so the two functions can never disagree.
    """
    stripped = term.strip()
    if is_placeholder(stripped):
        return "PLACEHOLDER"
    if is_year(stripped):
        return "YEAR"
    if is_measure(stripped):
        return "MEASURE"
    if is_street(stripped):
        return "STREET"
    if is_person_name(stripped):
        return "PERSON"
    return None


def is_place_term(term: str) -> bool:
    """
    Whether the term is a place, and therefore belongs to the ``PLACE`` facet.

    Returns ``True`` for a bare street spelling and for a toponym the collection actually
    carries. Kept next to :func:`is_subject_candidate` on purpose: the two answer different
    questions about the same word, and a curator reading only one of them would conclude
    that ``rua xv de novembro`` (118 documents) is discarded.
    """
    return is_street(term) or bool(_PLACE_NAME.match(term.strip()))


#: Toponyms measured in the collection, so the facet can be populated without a gazetteer.
#: The bairro names of Curitiba are the bulk of it, plus the municipalities and countries
#: that appear as subjects of the photographed records.
_PLACE_NAME = re.compile(
    r"^(curitiba|curitiba antiga|centro|centro cívico|centro histórico|batel|boqueirão|"
    r"alto boqueirão|campinas|cajuru|uberaba|pinheirinho|portão|pilarzinho|mossunguê|"
    r"bigorrilho|bacacheri|rebouças|guabirotuba|tatuquara|barreirinha|juvevê|capão|"
    r"capão da imbuia|capão raso|santa felicidade|alto da glória|alto da xv|"
    r"são francisco|sítio cercado|cristo rei|campo comprido|prado velho|vila|"
    r"paraná|são paulo|joinville|santa catarina|australia|austrália|suíça|frança|"
    r"alemanha|paris|zurique|zurich|washington|bahia|campina grande do sul|araucária|"
    r"pinhais|mandirituba|balsa nova|região metropolitana de curitiba|rmc)$",
    re.IGNORECASE,
)


def classifier_labels(categories: dict[str, int], labels: dict[str, str | None] | None = None) -> dict[str, int]:
    """
    Builds the label set the NLI model reads, from the drawers the curator registered.

    The label is ``classifier_label`` when the curator wrote one, and the bare ``name``
    otherwise. The description is **never** used, in either case: concatenating it makes the
    model progressively lose the entailment as the label grows, until it collapses every
    input onto a single drawer — measured, and guarded by tests that fail if it comes back.

    Args:
        categories: ``{name: category_id}`` of the active drawers.
        labels: ``{name: classifier_label | None}``. A missing key falls back to the name,
            so a repository that has not been taught about the column still works.

    Returns:
        ``{label: category_id}``. Two drawers that write the same label collapse into one
        entry, and the last one wins — the label is what the model sees, so two identical
        labels are indistinguishable to it and the classifier could never separate them.
    """
    resolved: dict[str, int] = {}
    for name, category_id in categories.items():
        raw_label = (labels or {}).get(name)
        label = (raw_label or name).strip() or name
        resolved[label] = category_id
    return resolved


def label_set_fingerprint(labels: dict[str, int]) -> str:
    """
    Stable identity of the label set a tag was classified against.

    This is what makes the macro-category worker re-queue by itself when a curator rewrites a
    label: the stamp stores this hash instead of ``"DONE"``, so a changed label set makes
    every stamped tag pending again. Without it the correction would never reach the
    collection — the exact failure the V3 migration exposed, where a tag kept
    ``worker_macro_category_v1: DONE`` while its drawer had been retired.

    Sorted and joined before hashing, so the order the rows came back in cannot produce two
    different hashes for the same vocabulary (which would re-queue the collection forever).
    The category ids are part of the payload because a drawer that is *replaced* under the
    same label must also invalidate the stamp.
    """
    payload = "\x1f".join(f"{label}\x1e{category_id}" for label, category_id in sorted(labels.items()))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
