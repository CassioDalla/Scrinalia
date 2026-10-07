"""
The collection's own vocabulary: the value object the guard reads, and the seed mirror.

Two things live here, and the distinction matters.

``CollectionVocabulary`` is the **runtime** input: a frozen pair of sets that the subject guard
consults for the two families the *collection* owns — a toponym it carries as a place and a
person name. The guard stays a pure function of the term plus this object, which is what keeps
it deterministic and testable; the repository loads the object from ``archive_collection_terms``
once per run.

``ARRANGEMENT_TERMS`` and ``COLLECTION_TERMS`` are the **seed mirror** of the reference
collection: the rows the migration registers. They are duplicated in the migration on purpose
(replaying history must reproduce the state it produced) and a test pins the two together, the
same pattern ``NOBRADE_LEVELS`` and ``SUBJECT_CATEGORIES`` already follow. Nothing at runtime
reads them — an installation that empties the catalogue must not silently inherit Curitiba's
names, which is exactly what a fallback would do.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field

from scrinalia.domains.archive.models.enums import PLACE_TERM_KINDS, CollectionTermKind


def normalize_term(term: str) -> str:
    """
    Canonical form of a collection term: whitespace collapsed, lowercase.

    The collapsed whitespace is not cosmetic: a term copied from a page arrives with a double space
    often enough that ``local  não identificado`` and ``local não identificado`` were two rows the
    curator could not tell apart, and only one of them matched.
    """
    return " ".join(term.split()).lower()


@dataclass(frozen=True)
class CollectionVocabulary:
    """
    The terms the collection declares, split by where the guard sends them.

    ``place_terms`` claim the PLACE facet; ``person_terms`` go nowhere (the name is the producer,
    the same reasoning that retired the ``Pessoa`` drawer). Both are stored normalised, and the
    default is empty: an installation with no catalogue refuses nothing it has not declared,
    which is the honest behaviour for a collection nobody has described yet.
    """

    place_terms: frozenset[str] = field(default_factory=frozenset)
    person_terms: frozenset[str] = field(default_factory=frozenset)

    def is_place(self, term: str) -> bool:
        return normalize_term(term) in self.place_terms

    def is_person(self, term: str) -> bool:
        return normalize_term(term) in self.person_terms


#: The vocabulary of a deployment whose catalogue is still empty. Never a fallback to the
#: reference collection: that would make another institution's installation silently Curitiba.
EMPTY_VOCABULARY = CollectionVocabulary()

#: The kinds that claim the PLACE facet, as stored values. Derived from the enum so the catalogue
#: and the guard cannot disagree about which kind is a place.
PLACE_KINDS: frozenset[str] = frozenset(kind.value for kind in PLACE_TERM_KINDS)


# =============================================================================
# The seed mirror of the reference collection
# =============================================================================

#: Arrangement token (or full code) to the name the proposal suggests, in the order the seed
#: registers it. The root is the whole-code entry; the rest are single tokens.
ARRANGEMENT_TERMS: tuple[tuple[str, str], ...] = (
    ("BR PRADAP", "Acervo da entidade custodiadora"),
    ("IPPUC", "IPPUC - Instituto de Pesquisa e Planejamento Urbano de Curitiba"),
    ("SMU", "SMU - Secretaria Municipal de Urbanismo"),
    ("SMMA", "SMMA - Secretaria Municipal do Meio Ambiente"),
    ("SEPLAD", "SEPLAD - Secretaria Municipal do Planejamento"),
    ("CMC", "CMC - Câmara Municipal de Curitiba"),
    ("FAS", "FAS - Fundação de Ação Social"),
    ("SGM", "SGM - Secretaria Municipal de Governo"),
    ("SMCS", "SMCS - Secretaria Municipal da Comunicação Social"),
    ("SMDS", "SMDS - Secretaria Municipal da Defesa Social"),
    ("FOTOGRAFIA", "Registros Fotográficos"),
    ("FOTOGRAFIAS", "Registros Fotográficos"),
    ("ED", "Edificações"),
    ("AL", "Alvenaria"),
    ("CONSTR", "Construções"),
    ("CVCO", "Certificados de Vistoria e Conclusão de Obras"),
    ("OUVIDORIA", "Ouvidoria Municipal de Curitiba"),
    ("LEGISLAÇÃO", "Referência Legislativa"),
    ("MICROFILME", "Microfilme"),
    ("PROC", "Processos"),
    ("MATADOURO", "Matadouro Municipal"),
    ("DIAPOSITIVO", "Diapositivos"),
    ("JORN", "Jornais"),
    ("REQUERIMENTOS", "Requerimentos"),
    ("REQ", "Requerimentos"),
    ("OF", "Ofícios"),
    ("HIST", "Histórico"),
    ("PP", "Pareceres e Projetos"),
    ("DUP", "Duplicatas"),
    ("GAZ", "Gazeta"),
    ("MERC", "Mercado"),
    ("ATUBA", "Atuba"),
    ("INVENT", "Inventário"),
    ("MODELO", "Modelo"),
    ("BOMBAS", "Bombas"),
    ("INFLAMAVEIS", "Inflamáveis"),
    ("DEPOSITO", "Depósito"),
    ("PEQ", "Pequenos"),
)

#: The non-subject terms the reference collection carries, as ``(term, kind)``. The kind is the
#: enum **value** and not the member, so the mirror stays plain data and a migration can carry it
#: without importing application code.
COLLECTION_TERMS: tuple[tuple[str, str], ...] = (
    # Bairros and the areas the collection names as places.
    ("curitiba antiga", "DISTRICT"),
    ("centro", "DISTRICT"),
    ("centro cívico", "DISTRICT"),
    ("centro histórico", "DISTRICT"),
    ("batel", "DISTRICT"),
    ("boqueirão", "DISTRICT"),
    ("alto boqueirão", "DISTRICT"),
    ("campinas", "DISTRICT"),
    ("cajuru", "DISTRICT"),
    ("uberaba", "DISTRICT"),
    ("pinheirinho", "DISTRICT"),
    ("portão", "DISTRICT"),
    ("pilarzinho", "DISTRICT"),
    ("mossunguê", "DISTRICT"),
    ("bigorrilho", "DISTRICT"),
    ("bacacheri", "DISTRICT"),
    ("rebouças", "DISTRICT"),
    ("guabirotuba", "DISTRICT"),
    ("tatuquara", "DISTRICT"),
    ("barreirinha", "DISTRICT"),
    ("juvevê", "DISTRICT"),
    ("capão", "DISTRICT"),
    ("capão da imbuia", "DISTRICT"),
    ("capão raso", "DISTRICT"),
    ("santa felicidade", "DISTRICT"),
    ("alto da glória", "DISTRICT"),
    ("alto da xv", "DISTRICT"),
    ("são francisco", "DISTRICT"),
    ("sítio cercado", "DISTRICT"),
    ("cristo rei", "DISTRICT"),
    ("campo comprido", "DISTRICT"),
    ("prado velho", "DISTRICT"),
    ("vila", "DISTRICT"),
    # Municipalities, including the ones abroad (the collection's records reach them).
    ("curitiba", "MUNICIPALITY"),
    ("são paulo", "MUNICIPALITY"),
    ("joinville", "MUNICIPALITY"),
    ("paris", "MUNICIPALITY"),
    ("zurique", "MUNICIPALITY"),
    ("zurich", "MUNICIPALITY"),
    ("washington", "MUNICIPALITY"),
    ("campina grande do sul", "MUNICIPALITY"),
    ("araucária", "MUNICIPALITY"),
    ("pinhais", "MUNICIPALITY"),
    ("mandirituba", "MUNICIPALITY"),
    ("balsa nova", "MUNICIPALITY"),
    # States and the metropolitan region.
    ("paraná", "STATE"),
    ("santa catarina", "STATE"),
    ("bahia", "STATE"),
    ("região metropolitana de curitiba", "REGION"),
    ("rmc", "REGION"),
    # Countries.
    ("australia", "COUNTRY"),
    ("austrália", "COUNTRY"),
    ("suíça", "COUNTRY"),
    ("frança", "COUNTRY"),
    ("alemanha", "COUNTRY"),
    # Person names: the producer or the person depicted, never a subject.
    ("jaime lerner", "PERSON"),
    ("oscar niemeyer", "PERSON"),
    ("lúcio costa", "PERSON"),
    ("mário de miranda", "PERSON"),
    ("joel rocha", "PERSON"),
    ("poty lazzarotto", "PERSON"),
    ("tadeusz kościuszko", "PERSON"),
    ("ernesto guaita", "PERSON"),
    ("lina faria", "PERSON"),
    ("michelangelo cuniberti", "PERSON"),
    ("marilia kranz", "PERSON"),
    ("paulo spzak", "PERSON"),
    ("eduardo fernando chaves", "PERSON"),
    ("aristeu dias", "PERSON"),
    ("joão zaco paraná", "PERSON"),
    ("abrão assad", "PERSON"),
)


def vocabulary_from_rows(rows: list[tuple[str, str]]) -> CollectionVocabulary:
    """Builds the guard's value object from ``(term, kind)`` pairs, active rows only."""
    places: set[str] = set()
    persons: set[str] = set()
    for term, kind in rows:
        if kind in PLACE_KINDS:
            places.add(normalize_term(term))
        elif kind == CollectionTermKind.PERSON.value:
            persons.add(normalize_term(term))
    return CollectionVocabulary(place_terms=frozenset(places), person_terms=frozenset(persons))


def suggest_name(code: str, names: Mapping[str, str]) -> str | None:
    """
    The suggestion for a rung's code: the whole code first, then its last token.

    ``BR PRADAP`` is the collection's root and has a name of its own; ``IPPUC`` is a token that
    names the fund. Looking the whole code up first is what lets the two coexist in one
    catalogue, and it is the rule the old two-dict constant implemented by hand.
    """
    if code in names:
        return names[code]
    return names.get(code.split(" ")[-1])


#: The guard's five verdicts, as codes. Declared once because the suggestion route publishes
#: them and the screen translates them: a bare string in two places would drift.
SUBJECT_EXCLUSION_SIGNALS: tuple[str, ...] = ("PLACEHOLDER", "YEAR", "MEASURE", "STREET", "PERSON")
