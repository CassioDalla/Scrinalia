"""Normalisation of the free-text description level into the level catalogue.

The source declares the level as text (``"Item Documental"``, ``"Dossiê/Processo"``) and the
archive stores it as a foreign key. The bridge between the two is this fold: accent- and
case-insensitive and punctuation-tolerant, so the 3,608 declared values map without a
hand-written de-para per spelling. It is pure, which is what lets the migration, the transfer
worker and the human review share exactly one definition of "the same level".
"""

import re
import unicodedata
from collections.abc import Iterable, Sequence

# ``/`` and ``-`` separate the words of a level in the source spellings ("Dossiê/Processo",
# "Dossiê - Processo", "Fundo/Coleção"), so they collapse to a single space before the
# comparison: the punctuation may differ without the level becoming a different level.
_SEPARATORS = re.compile(r"[/\\\-\u2013\u2014]+")
_WHITESPACE = re.compile(r"\s+")

#: The rungs the catalogue starts with, in the order of the norm.
#:
#: ``name`` is the spelling the **source** declares wherever the source declares one, so the
#: migration's backfill is a literal fold instead of a translation table. ``description``
#: carries the NOBRADE wording, and ``aliases`` the variants seen or expected in the wild —
#: including the norm's own wording, which is what a curator typing by hand is likely to use.
NOBRADE_LEVELS: tuple[tuple[int, str, str, str, tuple[str, ...], bool, bool], ...] = (
    (
        0,
        "acervo",
        "Acervo da entidade custodiadora",
        "Conjunto documental sob a guarda de uma mesma entidade custodiadora. É a raiz da árvore.",
        ("Acervo", "Acervo da entidade"),
        False,
        True,
    ),
    (
        1,
        "fundo",
        "Fundo",
        "Fundo ou coleção: o conjunto produzido por uma mesma instituição ou pessoa.",
        ("Fundo ou coleção", "Coleção", "Fundo ou colecao"),
        False,
        True,
    ),
    (
        2,
        "secao",
        "Seção",
        "Divisão administrativa ou funcional do fundo.",
        ("Secao", "Seccao"),
        False,
        True,
    ),
    (
        3,
        "serie",
        "Série",
        "Agrupamento de descrições por afinidade de função, atividade ou tipo documental.",
        ("Serie", "Subsérie", "Subserie"),
        False,
        True,
    ),
    (
        4,
        "dossie",
        "Dossiê/Processo",
        "Nível obrigatório da norma: o conjunto de documentos reunidos por um mesmo assunto ou processo.",
        ("Dossiê ou processo", "Dossiê", "Dossie", "Processo"),
        True,
        True,
    ),
    (
        5,
        "item",
        "Item Documental",
        "Unidade documental indivisível. Não admite filhos.",
        ("Item documental", "Item"),
        True,
        False,
    ),
)


def normalize_level_name(value: str) -> str:
    """
    Folds a level spelling to the form the catalogue matches on.

    ``"Dossiê/Processo"``, ``"dossie - processo"`` and ``"DOSSIE PROCESSO"`` all fold to
    ``"dossie processo"``: the comparison must survive the punctuation, the accents and the
    case the source happens to use, because all three vary in real payloads.
    """
    decomposed = unicodedata.normalize("NFKD", value)
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    without_separators = _SEPARATORS.sub(" ", without_accents)
    return _WHITESPACE.sub(" ", without_separators).strip().lower()


def build_level_index(levels: Iterable[tuple[int, str, Sequence[str]]]) -> dict[str, int]:
    """
    Builds the ``folded spelling -> level_id`` index the resolution reads.

    The canonical ``name`` wins over an alias when both fold to the same key, so a curator who
    registers a colliding alias cannot silently steal another level's matches.
    """
    index: dict[str, int] = {}
    for level_id, name, aliases in levels:
        for spelling in (name, *aliases):
            key = normalize_level_name(spelling)
            if key:
                index.setdefault(key, level_id)
    return index


def resolve_level_id(index: dict[str, int], value: str | None) -> int | None:
    """Returns the level a declared spelling belongs to, or ``None`` when nothing folds to it."""
    if not value:
        return None
    return index.get(normalize_level_name(value))
