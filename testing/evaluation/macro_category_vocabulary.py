"""
Vocabulary report for the subject axis (Fase 1.5, defeito 2/2 — decision "V1").

The macro-category classification is systematically wrong on the real collection, and the
measurement isolated two causes that are tangled together: the NLI label format and the
**vocabulary itself**. ``igrejas`` — the single largest tag of the collection (2.467
documents) — has nowhere to go, because "Religião" does not exist among the five categories
registered for the IPPUC/SMU records. No label format fixes a missing drawer.

This module produces the evidence a curator decides the new vocabulary on: it ranks the tags
by how many documents they actually reach, groups them by the regex families that show up in
the real spellings, and reports which terms are not subjects at all but provenance
(``ippuc``, ``pmc``) or toponyms (``curitiba``, ``centro``, ``rua xv de novembro``).

**It reads and proposes; it never writes.** Deciding the vocabulary is a curation act, not an
engineering one — the same principle the whole Phase 3.5 was built on.

Run it from the repository root, against the real database:

    uv run python -m testing.evaluation.macro_category_vocabulary --top 250

It writes the full JSON report to ``.analysis/`` (non-versioned) and prints the summary the
curator reads.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import func, select

from memoria_curitibana.core.database import get_db
from memoria_curitibana.core.logger import logger
from memoria_curitibana.domains.archive.models import ArchiveDocumentTag, ArchiveTag

DEFAULT_OUTPUT = Path(".analysis") / "macro_category_vocabulary.json"

#: How many of the collection's document<->tag links the report accounts for. The point of
#: ranking by ``document_count`` is that the head of the list is what a reader actually
#: navigates: measured on the real collection, the top 50 tags already carry 40% of the
#: links and the top 150 carry 83%.
DEFAULT_TOP = 250


@dataclass
class TermClassification:
    """What a tag is, according to the families measured on the real spellings."""

    name: str
    document_count: int
    kind: str
    evidence: str


@dataclass
class Family:
    """A subject family: the drawer the vocabulary proposes, plus the tags that justify it."""

    key: str
    name: str
    rationale: str
    pattern: str
    members: list[TermClassification] = field(default_factory=list)

    @property
    def documents(self) -> int:
        return sum(member.document_count for member in self.members)


#: Terms that are *not* a subject. Kept here, next to the report, because the vocabulary
#: decision needs the boundary explicit: a curator looking at the list has to see that
#: ``ippuc`` is not "a subject that lost" but "a producer", and that ``1924`` is a date.
_NON_SUBJECT = {
    "PLACEHOLDER": re.compile(
        r"^(não identificad[oa]|local não identificad[oa]|localização não identificad[oa]|"
        r"sem identificação|ilegível|não possui)$"
    ),
    "DATE": re.compile(r"^(1[89]\d{2}|20\d{2})$"),
    "MEASURE": re.compile(r"^\d+\s*(anos?|metros?|m|km|nº.*)?$"),
    "STREET": re.compile(r"^(rua|r\.|avenida|av\.|alameda|travessa|tv\.|rodovia|br[-\s]?\d+|praça|pça)\b"),
    "INSTITUTION": re.compile(
        r"^(ippuc|pmc|smma|smcs|smf|smma|urbs|cmtc|cohab|fcc|ibram|ufpr|ifpr|iphan|alep|"
        r"prefeitura|câmara municipal|câmara dos vereadores|tribunal de justiça|"
        r"assembleia legislativa|comissão|companhia|fundação cultural|cmpb|rvpsc)\b"
    ),
    "PERSON": re.compile(
        r"^(jaime lerner|oscar niemeyer|lúcio costa|mário de miranda|joel rocha|poty lazzarotto|"
        r"tadeusz|ernesto guaita|lina faria|michelangelo cuniberti|marilia kranz|"
        r"paulo spzak|eduardo fernando chaves|aristeu dias|moacir|sidney|joão zaco)\b"
    ),
}

#: The proposed subject drawers. Each one carries the regex that selects its evidence, so the
#: report is reproducible and the curator can see *why* a tag landed there instead of trusting
#: the grouping. The names are proposals: renaming one is a curation decision, not a bug.
_FAMILIES: tuple[Family, ...] = (
    Family(
        key="URBANISM",
        name="Urbanismo e Arquitetura",
        rationale="Construção, materiais, tipologia construtiva e desenho urbano. É hoje o "
        "destino correto de `alvenaria`, `residencial` e `eclético`, que a classificação atual "
        "manda para Mobilidade.",
        pattern=r"\b(?:alvenaria|madeira|tijolo|concreto|ferro|pedra|telhas?|telhados?|parede|fachada|muro|gradil|lambrequim|escada|portão|janela|garagem|residencial|residência|sobrado|chalé|chalet|bangalô|bungalow|casa|prédios?|edifícios?|apartamentos?|construção|obras?|reformas?|aumento|terreno|lote|pavimentação|calçamento|calçada|asfaltamento|urbanização|paisagismo|eclético|ecletismo|art[- ]?noveau|art déco|neoclássico|brutalismo|arquitetura|plantas?|maquete|projeto|fundação|estrutura)\b",
    ),
    Family(
        key="HERITAGE",
        name="Patrimônio e Preservação",
        rationale="Tombamento, unidades de interesse de preservação e o patrimônio construído "
        "como objeto de política pública. Distinto de Urbanismo: aqui o assunto é a *preservação*.",
        pattern=r"\b(?:patrimônio|uip|unidade de interesse|tombad|setor histórico|centro histórico|prédio histórico|casa histórica|casa antiga|casas antigas|solar|palácio|memorial|monumento|estátua|escultura|chafariz|arco|pirâmide|mural|painel|relíquia)\b",
    ),
    Family(
        key="ENVIRONMENT",
        name="Meio Ambiente e Áreas Verdes",
        rationale="Parques, rios, vegetação e ecologia. Hoje `parque` (203 docs), `jardim botânico` "
        "(201) e `parque iguaçu` (144) caem em Mobilidade — o modelo não tem gaveta melhor.",
        pattern=r"\b(?:parque|jardim botânico|jardinete|jardim|praças?|bosques?|horto|horta|pomar|árvores?|vegetação|floreira|flores|grama|gramado|área verde|meio ambiente|ecolog|natureza|rio|riacho|riacho|lago|lagoa|represa|bacia|água|piscicultura|pesca|zoológico|animais|enchente|alagamento|chuvas|lama)\b",
    ),
    Family(
        key="MOBILITY",
        name="Mobilidade e Transporte",
        rationale="Circulação, ferrovia, veículos e transporte público. É a gaveta que hoje "
        "concentra 687 de 980 tags por ser a única que 'parece próxima' de tudo.",
        pattern=r"\b(?:ferrovi\w*|linha férrea|linha ferroviária|trilho|trem|bonde|trolleybus|metrô|monotrilho|estação|rodoferroviária|rodoviária|terminal|ônibus|veículos?|carros?|automóveis?|caminhão|kombi|fusca|táxi|bicicleta|ciclovia|ciclista|pedestres?|trânsito|sistema viário|viaduto|passarela|ponte|calçadão|circulação|estacionamento|semáforo|lombada|pista|corredor|transporte|linha verde)\b",
    ),
    Family(
        key="COMMERCE",
        name="Economia e Comércio",
        rationale="Comércio, serviços, indústria e abastecimento. Hoje `comércio` (193) e "
        "`comércios` (163) não têm gaveta e o modelo os espalha.",
        pattern=r"\b(?:comércio|comércios|comercial|estabelecimento|lojas?|mercados?|armazém|mercearia|açougue|panificadora|confeitaria|restaurante|lanchonete|bar|hotel|banco|farmácia|papelaria|supermercado|shopping|galeria|vitrine|feira|feirante|ambulante|indústria|industrial|fábrica|oficina|depósito|galpão|barracão|abastecimento|produtos|mercadoria|qualificação profissional|linhão do emprego|aluguel|venda|renda)\b",
    ),
    Family(
        key="RELIGION",
        name="Religião",
        rationale="**A gaveta que falta e o motivo desta sessão existir.** `igrejas` sozinha "
        "alcança 2.467 documentos — a maior tag do acervo — e o melhor que o modelo consegue hoje "
        "é classificá-la como 'Instituição', porque 'Religião' não existe.",
        pattern=r"\b(?:igrejas?|paróquias?|catedrais?|capelas?|seminários?|basílica|diocese|arcebispado|presbiteriana|católic|religios|santa|culto|missa)\b",
    ),
    Family(
        key="CULTURE",
        name="Educação e Cultura",
        rationale="Escolas, museus, eventos, esporte e produção cultural.",
        pattern=r"\b(?:escola|colégio|universidade|liceu|educação|curso|cursos|museu|galeria de arte|teatro|cinema|cine |biblioteca|conservatório|música|banda|coral|arte|artista|exposição|evento|festa|comemoração|aniversário|natal|decoração|show|apresentação|esporte|canoagem|remo|caiaque|canoa|atletas?|campeonato|competição|torcidas?|futebol|estádio|quadra|pista de rodeios|rodeio|lazer|turismo|pontos turísticos)\b",
    ),
    Family(
        key="SOCIAL",
        name="Assistência e Questões Sociais",
        rationale="População, vulnerabilidade, trabalho e ação social.",
        pattern=r"\b(?:população|pessoas|pessoa|homem|mulheres?|crianças?|jovens|idoso|família|trabalhador\w*|trabalho|funcionário|vulnerabilidade|social|assistência|comunidade|favelas|imigração|imigrante|polonesa|alemão|italiana|árabe|ação social|projeto social)\b",
    ),
    Family(
        key="ADMIN",
        name="Administração e Política Pública",
        rationale="A ação do Estado como assunto: planejamento, legislação e programa público. "
        "Distinto da faceta INSTITUTION, que diz *quem produziu*, não *sobre o que é*.",
        pattern=r"\b(?:planejamento|legislação|lei|decreto|portaria|política|programa|projeto|administração|gestão|diretriz|plano|orçamento|obra pública|concessão|regularização|licitação)\b",
    ),
)

#: Facet families: not a subject drawer, but the classification the tag itself carries. Kept
#: apart in the report because the whole point of decision D5 is that they must not compete
#: with the subject axis for the same slot.
_FACETS: tuple[Family, ...] = (
    Family(
        key="INSTITUTION",
        name="Instituição (faceta)",
        rationale="Quem produziu ou de quem se fala. `ippuc` (2.376 docs) e `pmc` (269) são "
        "proveniência, não assunto — e disputam hoje a mesma gaveta que `alvenaria`.",
        pattern=r"\b(?:ippuc|pmc|smma|smcs|urbs|cmtc|cohab|fcc|ibram|ufpr|ifpr|iphan|alep|prefeitura|câmara|tribunal|assembleia|companhia|fundação|secretaria|ministério|sociedade|associação|clube|sindicato|instituto)\b",
    ),
    Family(
        key="PLACE",
        name="Lugar (faceta)",
        rationale="Topônimos e logradouros. `curitiba` (1.865) e `centro` (464) são lugar, não "
        "assunto. Logradouro com número entra aqui por decisão do dono do produto (2026-10-04), "
        "não em NENHUMA: a busca já alcança o termo e a faceta informa mais que o silêncio.",
        pattern=r"\b(?:curitiba|centro|bairro|região|batel|boqueirão|campinas|cajuru|uberaba|pinheirinho|portão|pilarzinho|mossunguê|bigorrilho|bacacheri|rebouças|guabirotuba|tatuquara|barreirinha|juvevê|capão|santa felicidade|alto da|são francisco|sítio cercado|cristo rei|campo comprido|prado velho|vila|paraná|são paulo|joinville|santa catarina|australia|austrália|suíça|frança|alemanha|paris|zurique|zurich|washington|nova york|bahia|rua|avenida|alameda|travessa|rodovia|br[-\s]?\d|praça|largo|estrada|região metropolitana|rmc)\b",
    ),
)


def _classify(name: str, document_count: int, families: list[Family], facets: list[Family]) -> TermClassification:
    """Assigns one tag to the first family that claims it, or reports it as non-subject."""
    # Facets first: a place or an institution never becomes a subject drawer, even when the
    # subject regex would also match (``praça`` is in ENVIRONMENT and in PLACE — the curator
    # decides which axis wins, and the report surfaces the collision instead of hiding it).
    for family in facets:
        if re.search(family.pattern, name):
            return TermClassification(name, document_count, family.key, family.name)

    for kind, pattern in _NON_SUBJECT.items():
        if pattern.search(name):
            return TermClassification(name, document_count, kind, "não é assunto")

    for family in families:
        if re.search(family.pattern, name):
            return TermClassification(name, document_count, family.key, family.name)

    return TermClassification(name, document_count, "UNCLASSIFIED", "sem família proposta")


def build_report(top: int) -> dict:
    """Reads the collection and returns the report. Read-only by construction."""
    with get_db() as db:
        stmt = (
            select(ArchiveTag.name, func.count(ArchiveDocumentTag.description_id).label("documents"))
            .join(ArchiveDocumentTag, ArchiveTag.tag_id == ArchiveDocumentTag.tag_id)
            .group_by(ArchiveTag.name)
            .order_by(func.count(ArchiveDocumentTag.description_id).desc(), ArchiveTag.name)
            .limit(top)
        )
        rows = [(row.name, row.documents) for row in db.execute(stmt).all()]

        links_total = db.scalar(select(func.count()).select_from(ArchiveDocumentTag)) or 0
        tags_total = db.scalar(select(func.count()).select_from(ArchiveTag)) or 0
        db.rollback()

    families = [Family(**{k: v for k, v in family.__dict__.items() if k != "members"}) for family in _FAMILIES]
    facets = [Family(**{k: v for k, v in facet.__dict__.items() if k != "members"}) for facet in _FACETS]

    by_family: dict[str, list[TermClassification]] = defaultdict(list)
    for name, document_count in rows:
        classification = _classify(name, document_count, families, facets)
        by_family[classification.kind].append(classification)

    covered = sum(document_count for _, document_count in rows)
    return {
        "top": top,
        "tags_in_catalog": tags_total,
        "links_in_catalog": links_total,
        "tags_in_report": len(rows),
        "links_covered": covered,
        "share_of_links": covered / links_total if links_total else 0.0,
        "families": [
            {
                "key": family.key,
                "name": family.name,
                "rationale": family.rationale,
                "documents": sum(c.document_count for c in by_family.get(family.key, [])),
                "tags": len(by_family.get(family.key, [])),
                "members": [
                    {"name": c.name, "documents": c.document_count}
                    for c in sorted(by_family.get(family.key, []), key=lambda c: -c.document_count)
                ],
            }
            for family in [*_FAMILIES, *_FACETS]
        ],
        "non_subject": {
            kind: [
                {"name": c.name, "documents": c.document_count}
                for c in sorted(by_family.get(kind, []), key=lambda c: -c.document_count)
            ]
            for kind in _NON_SUBJECT
        },
        "unclassified": [
            {"name": c.name, "documents": c.document_count}
            for c in sorted(by_family.get("UNCLASSIFIED", []), key=lambda c: -c.document_count)
        ],
    }


def print_summary(report: dict, examples: int) -> None:
    logger.info(
        f"📊 {report['tags_in_report']} tags analysed over {report['tags_in_catalog']} in the catalog "
        f"({report['share_of_links']:.0%} of the {report['links_in_catalog']} links)"
    )
    logger.info("--- subject drawers proposed ---")
    for family in report["families"]:
        if family["key"] in {f.key for f in _FACETS}:
            continue
        head = ", ".join(f"{m['name']}({m['documents']})" for m in family["members"][:examples])
        logger.info(
            f"   [{family['key']:12}] {family['name']:34} {family['tags']:>3} tags · "
            f"{family['documents']:>5} docs :: {head}"
        )

    logger.info("--- facets (not subjects) ---")
    for family in report["families"]:
        if family["key"] not in {f.key for f in _FACETS}:
            continue
        head = ", ".join(f"{m['name']}({m['documents']})" for m in family["members"][:examples])
        logger.info(f"   [{family['key']:12}] {family['name']:34} {family['tags']:>3} tags :: {head}")

    logger.info("--- terms that are not subjects ---")
    for kind, members in report["non_subject"].items():
        head = ", ".join(f"{m['name']}({m['documents']})" for m in members[:examples])
        logger.info(f"   [{kind:12}] {len(members):>3} tags :: {head}")

    logger.info(f"--- unclassified: {len(report['unclassified'])} tags (the curator reads these) ---")
    head = ", ".join(f"{m['name']}({m['documents']})" for m in report["unclassified"][: examples * 3])
    logger.info(f"   {head}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only vocabulary report for the subject axis.")
    parser.add_argument("--top", type=int, default=DEFAULT_TOP, help="How many tags, by document count.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Where to write the JSON report.")
    parser.add_argument("--examples", type=int, default=6, help="Members printed per family.")
    args = parser.parse_args(argv)

    report = build_report(top=args.top)
    print_summary(report, examples=args.examples)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"💾 report written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
