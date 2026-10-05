"""The tree the reference codes imply, proposed and never written (Fase 2.5, H3).

This is the decision point of the phase. The roadmap is explicit that H3 comes **before** any
screen, because the report says how regular the structure actually is — and the measurement
already contradicted the roadmap's own estimate: slicing the codes on every space turns
``BR PRADAP SMU ED AL`` into 1,123 parents of one document each, because the code interleaves the
arrangement vocabulary with the identifiers of the leaf. ``domain.hierarchy_code`` separates the
two, which is what brings ~3,600 codes down to a few dozen rungs a human can actually review.

Nothing in this service writes. It reads the codes and the catalogue and returns what the tree
would be, with every guess labelled: an ordinal no declared record anchors is ``ORDINAL_INFERRED``,
and a pair such as ``FOTOGRAFIA`` / ``FOTOGRAFIAS`` is surfaced as ``NEAR_DUPLICATE_NODE`` for the
archivist instead of being resolved by a similarity score.
"""

from dataclasses import dataclass, field

from memoria_curitibana.domains.archive.domain.hierarchy import (
    HierarchyIssue,
    HierarchyViolation,
    ProposalFlag,
    near_duplicate_codes,
)
from memoria_curitibana.domains.archive.domain.hierarchy_code import (
    CodeFlag,
    SlicedReferenceCode,
    normalize_reference_code,
    slice_reference_code,
)
from memoria_curitibana.domains.archive.models import ArchiveDescriptionLevel
from memoria_curitibana.domains.archive.repository.hierarchy_repo import CodeObservation, HierarchyRepository
from memoria_curitibana.domains.archive.repository.level_catalog_repo import LevelCatalogRepository
from memoria_curitibana.domains.archive.schemas.hierarchy_schema import (
    HierarchyProposalCommand,
    HierarchyProposalNode,
    HierarchyProposalResponse,
)

#: Reference codes whose shape is not a clean "arrangement + serial" are listed, not dropped.
UNPARSED_CODES_LIMIT = 100

#: The two depths the product decision already fixed: ``BR PRADAP`` is the single root and the
#: eight third-token nodes are the funds. Everything deeper is inferred relative to its children.
ROOT_DEPTH = 2
FUND_DEPTH = 3
ROOT_ORDINAL = 0
FUND_ORDINAL = 1
MAX_ORDINAL = 5

#: Names the proposal suggests per rung. Suggestions only: a proposal that renamed things would be
#: a write, and the whole surface exists because a human confirms the vocabulary.
VOCABULARY_BY_CODE: dict[str, str] = {
    "BR PRADAP": "Acervo da entidade custodiadora",
}
VOCABULARY_BY_TOKEN: dict[str, str] = {
    "IPPUC": "IPPUC - Instituto de Pesquisa e Planejamento Urbano de Curitiba",
    "SMU": "SMU - Secretaria Municipal de Urbanismo",
    "SMMA": "SMMA - Secretaria Municipal do Meio Ambiente",
    "SEPLAD": "SEPLAD - Secretaria Municipal do Planejamento",
    "CMC": "CMC - Câmara Municipal de Curitiba",
    "FAS": "FAS - Fundação de Ação Social",
    "SGM": "SGM - Secretaria Municipal de Governo",
    "SMCS": "SMCS - Secretaria Municipal da Comunicação Social",
    "SMDS": "SMDS - Secretaria Municipal da Defesa Social",
    "FOTOGRAFIA": "Registros Fotográficos",
    "FOTOGRAFIAS": "Registros Fotográficos",
    "ED": "Edificações",
    "AL": "Alvenaria",
    "CONSTR": "Construções",
    "CVCO": "Certificados de Vistoria e Conclusão de Obras",
    "OUVIDORIA": "Ouvidoria Municipal de Curitiba",
    "LEGISLAÇÃO": "Referência Legislativa",
    "MICROFILME": "Microfilme",
    "PROC": "Processos",
    "MATADOURO": "Matadouro Municipal",
    "DIAPOSITIVO": "Diapositivos",
    "JORN": "Jornais",
    "REQUERIMENTOS": "Requerimentos",
    "REQ": "Requerimentos",
    "OF": "Ofícios",
    "HIST": "Histórico",
    "PP": "Pareceres e Projetos",
    "DUP": "Duplicatas",
    "GAZ": "Gazeta",
    "MERC": "Mercado",
    "ATUBA": "Atuba",
    "INVENT": "Inventário",
    "MODELO": "Modelo",
    "BOMBAS": "Bombas",
    "INFLAMAVEIS": "Inflamáveis",
    "DEPOSITO": "Depósito",
    "PEQ": "Pequenos",
}


@dataclass
class _NodeAccumulator:
    """What the codes say about one proposed rung, before it becomes a response node."""

    code: str
    depth: int
    parent_code: str | None
    own: list[CodeObservation] = field(default_factory=list)
    subtree_ids: set[str] = field(default_factory=set)
    flags: set[str] = field(default_factory=set)
    ordinal: int | None = None
    inferred: bool = True


class HierarchyProposalService:
    def __init__(self, repo: HierarchyRepository, catalog: LevelCatalogRepository) -> None:
        self.repo = repo
        self.catalog = catalog

    def propose(self, command: HierarchyProposalCommand) -> HierarchyProposalResponse:
        observations = self.repo.stream_code_observations()
        levels = self.catalog.list_levels()
        ordinal_to_level = {level.ordinal: level for level in levels}

        sliced = [(obs, slice_reference_code(obs.reference_code)) for obs in observations]
        records_by_code = self._records_by_code(observations)
        documents_by_rung = self._documents_by_rung(sliced)

        nodes = self._collect_nodes(sliced, records_by_code, documents_by_rung)
        near_duplicates = {code for pair in near_duplicate_codes(nodes) for code in pair}

        self._assign_ordinals(nodes, records_by_code, ordinal_to_level)
        self._add_flags(nodes, sliced, records_by_code, near_duplicates)

        proposal_nodes = [
            self._to_proposal_node(
                node=node,
                records_by_code=records_by_code,
                ordinal_to_level=ordinal_to_level,
                near_duplicates=near_duplicates,
            )
            for node in sorted(nodes.values(), key=lambda item: item.code)
        ]

        visible = [node for node in proposal_nodes if command.include_existing or node.status != "EXISTS"][
            : command.limit
        ]

        flag_counts: dict[str, int] = {}
        for node in proposal_nodes:
            for flag in node.flags:
                flag_counts[flag] = flag_counts.get(flag, 0) + 1

        return HierarchyProposalResponse(
            total_codes=len(observations),
            structural_codes=len(documents_by_rung),
            total_nodes=len(proposal_nodes),
            existing_nodes=sum(1 for node in proposal_nodes if node.status == "EXISTS"),
            nodes_to_create=sum(1 for node in proposal_nodes if node.status == "TO_CREATE"),
            ambiguous_nodes=sum(1 for node in proposal_nodes if node.status == "AMBIGUOUS"),
            flagged_nodes=sum(1 for node in proposal_nodes if node.flags),
            flags=flag_counts,
            unparsed_codes=self._unparsed_codes(sliced),
            nodes=visible,
        )

    # =========================================================================
    # Reading the codes
    # =========================================================================
    @staticmethod
    def _records_by_code(observations: list[CodeObservation]) -> dict[str, list[CodeObservation]]:
        by_code: dict[str, list[CodeObservation]] = {}
        for obs in observations:
            by_code.setdefault(normalize_reference_code(obs.reference_code), []).append(obs)
        return by_code

    @staticmethod
    def _documents_by_rung(
        sliced: list[tuple[CodeObservation, SlicedReferenceCode]],
    ) -> dict[str, list[CodeObservation]]:
        """
        Groups documents by the rung their code hangs from.

        The trailing identifiers of a code are the document's own identity inside its rung, so a
        document's *rung* is its structural code — ``BR PRADAP IPPUC FOTOGRAFIA`` for the 2,391
        items, not ``... 00680``. Without that distinction every document would be its own parent.

        The key is folded with ``normalize_reference_code`` so it meets the keys of
        ``records_by_code``: the source is not consistent about the case of a code, and two
        spellings of the same rung must not become two nodes.
        """
        by_rung: dict[str, list[CodeObservation]] = {}
        for obs, sliced_code in sliced:
            if not sliced_code.structural:
                continue
            by_rung.setdefault(normalize_reference_code(sliced_code.structural_code), []).append(obs)
        return by_rung

    @staticmethod
    def _collect_nodes(
        sliced: list[tuple[CodeObservation, SlicedReferenceCode]],
        records_by_code: dict[str, list[CodeObservation]],
        documents_by_rung: dict[str, list[CodeObservation]],
    ) -> dict[str, _NodeAccumulator]:
        """Every rung the codes imply, plus the pure-arrangement records they do not imply."""
        nodes: dict[str, _NodeAccumulator] = {}

        def touch(code: str) -> _NodeAccumulator:
            if code not in nodes:
                tokens = code.split(" ")
                nodes[code] = _NodeAccumulator(
                    code=code,
                    depth=len(tokens),
                    parent_code=" ".join(tokens[:-1]) if len(tokens) > ROOT_DEPTH else None,
                )
            return nodes[code]

        for code, docs in documents_by_rung.items():
            # ``rungs()`` is the contract the slicer owns and tests: every container the code
            # implies, root first, the code's own rung last. A pure-arrangement record is its own
            # rung, so this loop is also what creates the nodes no document hangs from.
            for rung in slice_reference_code(code).rungs():
                touch(rung)
            touch(code).own.extend(docs)

        # Subtree membership: a document belongs to its rung and to every ancestor of that rung.
        for code, node in nodes.items():
            for candidate, docs in documents_by_rung.items():
                if candidate == code or candidate.startswith(f"{code} "):
                    node.subtree_ids.update(doc.description_id for doc in docs)

        # A rung that is itself a description (``BR PRADAP IPPUC FOTOGRAFIAS`` is the Série record)
        # is the node, not a descendant of itself: counting it would inflate every materialised
        # rung by one. It stays in the ancestor's count, which is why the discard is per node.
        for code, node in nodes.items():
            for record in records_by_code.get(code, []):
                node.subtree_ids.discard(record.description_id)

        return nodes

    # =========================================================================
    # Ordinals
    # =========================================================================
    def _assign_ordinals(
        self,
        nodes: dict[str, _NodeAccumulator],
        records_by_code: dict[str, list[CodeObservation]],
        ordinal_to_level: dict[int, ArchiveDescriptionLevel],
    ) -> None:
        """
        Anchors the rungs the collection already declares, and infers the rest.

        An existing record with a level is the only anchor: it is the archivist's own statement.
        Everything else is derived — the two top depths from the product decision (root and funds),
        the rest one rung above whatever hangs directly below. The measurement is why depth alone
        cannot decide: five tokens hold Items, a Série and a Seção at the same time.

        Deepest first, because a container's proposal is read from its children's.
        """
        ordinal_by_level_id = {level.level_id: level.ordinal for level in ordinal_to_level.values()}

        for node in sorted(nodes.values(), key=lambda item: -item.depth):
            anchored: int | None = None
            for record in records_by_code.get(node.code, []):
                ordinal = ordinal_by_level_id.get(record.level_id) if record.level_id is not None else None
                if ordinal is not None:
                    anchored = ordinal
                    break

            if anchored is not None:
                node.ordinal = anchored
                node.inferred = False
                continue

            node.inferred = True
            node.flags.add(str(ProposalFlag.ORDINAL_INFERRED))

            if node.depth <= ROOT_DEPTH:
                node.ordinal = ROOT_ORDINAL
            elif node.depth == FUND_DEPTH:
                node.ordinal = FUND_ORDINAL
            else:
                child_ordinals = self._direct_child_ordinals(node, nodes, ordinal_by_level_id)
                if child_ordinals:
                    node.ordinal = max(ROOT_ORDINAL, min(child_ordinals) - 1)
                else:
                    node.ordinal = min(MAX_ORDINAL, max(ROOT_ORDINAL, node.depth - 2))

    @staticmethod
    def _direct_child_ordinals(
        node: _NodeAccumulator,
        nodes: dict[str, _NodeAccumulator],
        ordinal_by_level_id: dict[int, int],
    ) -> list[int]:
        """
        The ordinals of everything hanging directly under a rung.

        Both kinds of child count: the documents whose rung this is, and the child rungs, whose
        proposals are already computed because the walk goes deepest first. A container sits one
        rung above what it holds — the only NOBRADE-consistent statement available before a human
        looks at it.
        """
        ordinals: list[int] = []
        for obs in node.own:
            if obs.level_id is None:
                continue
            ordinal = ordinal_by_level_id.get(obs.level_id)
            if ordinal is not None:
                ordinals.append(ordinal)
        for child in nodes.values():
            if child.parent_code == node.code and child.ordinal is not None:
                ordinals.append(child.ordinal)
        return ordinals

    # =========================================================================
    # Flags
    # =========================================================================
    @staticmethod
    def _add_flags(
        nodes: dict[str, _NodeAccumulator],
        sliced: list[tuple[CodeObservation, SlicedReferenceCode]],
        records_by_code: dict[str, list[CodeObservation]],
        near_duplicates: set[str],
    ) -> None:
        """Adds everything that must be visible before the archivist approves a rung."""
        for code, node in nodes.items():
            if code not in records_by_code:
                continue
            if not node.subtree_ids:
                node.flags.add(str(ProposalFlag.RECORD_WITHOUT_DOCUMENTS))
            if len(records_by_code[code]) > 1:
                node.flags.add(str(ProposalFlag.DUPLICATE_REFERENCE_CODE))

        for code in near_duplicates:
            if code in nodes:
                nodes[code].flags.add(str(HierarchyIssue.NEAR_DUPLICATE_NODE))

        # A rung whose ordinal is not strictly above its parent's cannot be materialised: the tree
        # rule refuses it. Surfacing it is the honest outcome — the SMU branch really carries more
        # levels than the ladder has rungs, and only a human can decide what to collapse.
        for node in nodes.values():
            parent = nodes.get(node.parent_code) if node.parent_code else None
            if parent is None or parent.ordinal is None or node.ordinal is None:
                continue
            if node.ordinal <= parent.ordinal:
                node.flags.add(str(HierarchyViolation.LEVEL_NOT_ALLOWED_AS_CHILD))

        for _obs, sliced_code in sliced:
            rung = nodes.get(sliced_code.structural_code)
            if rung is None:
                continue
            for flag in sliced_code.flags:
                rung.flags.add(str(flag))

    # =========================================================================
    # Output
    # =========================================================================
    @staticmethod
    def _to_proposal_node(
        node: _NodeAccumulator,
        records_by_code: dict[str, list[CodeObservation]],
        ordinal_to_level: dict[int, ArchiveDescriptionLevel],
        near_duplicates: set[str],
    ) -> HierarchyProposalNode:
        records = records_by_code.get(node.code, [])
        level = ordinal_to_level.get(node.ordinal) if node.ordinal is not None else None

        if len(records) > 1:
            status = "AMBIGUOUS"
        elif records:
            status = "EXISTS"
        elif node.code in near_duplicates:
            # No record of its own, but a sibling differs by one letter: creating it silently is
            # exactly the mistake the roadmap warns about, so a human decides.
            status = "AMBIGUOUS"
        else:
            status = "TO_CREATE"

        return HierarchyProposalNode(
            code=node.code,
            depth=node.depth,
            parent_code=node.parent_code,
            status=status,
            proposed_level_id=level.level_id if level else None,
            proposed_level_code=level.code if level else None,
            ordinal_inferred=node.inferred,
            document_count=len(node.subtree_ids),
            declared_levels=sorted({obs.level_name for obs in node.own if obs.level_name}),
            flags=sorted(node.flags),
            suggested_name=HierarchyProposalService._suggest_name(node.code),
            existing_description_id=records[0].description_id if records else None,
            sample_description_ids=sorted(node.subtree_ids)[:5],
        )

    @staticmethod
    def _suggest_name(code: str) -> str | None:
        if code in VOCABULARY_BY_CODE:
            return VOCABULARY_BY_CODE[code]
        return VOCABULARY_BY_TOKEN.get(code.split(" ")[-1])

    @staticmethod
    def _unparsed_codes(sliced: list[tuple[CodeObservation, SlicedReferenceCode]]) -> list[str]:
        interesting = {
            str(CodeFlag.UNPARSED_TAIL),
            str(CodeFlag.MID_CODE_IDENTIFIER),
            str(CodeFlag.NO_STRUCTURAL_TOKEN),
        }
        codes = [
            obs.reference_code
            for obs, sliced_code in sliced
            if any(str(flag) in interesting for flag in sliced_code.flags)
        ]
        return sorted(codes)[:UNPARSED_CODES_LIMIT]
