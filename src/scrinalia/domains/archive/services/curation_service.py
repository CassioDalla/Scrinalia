from datetime import UTC, datetime

from scrinalia.domains.archive.repository.curation_repo import CurationRepository
from scrinalia.domains.archive.schemas.curation_schema import CurationInbox, CurationQueue

#: The catalogue of queues. Order matters: it is the order the cards appear on the home screen, and
#: it goes from "the collection cannot be navigated" to "the record has a defect", because that is
#: the order in which the queues unblock each other.
#: ``route`` is a front-end path, carried by the API so the mapping lives in one place instead of
#: being duplicated in the UI. The Portuguese text is end-user-visible, which is the only place the
#: project keeps it (see AGENTS.md).
QUEUE_CATALOGUE: tuple[tuple[str, str, str, str], ...] = (
    (
        "hierarchy_orphans",
        "Arranjo não materializado",
        "/arranjo/plano",
        "Descrições que o arranjo ainda não consegue colocar numa cadeia.",
    ),
    (
        "hierarchy_plans",
        "Níveis aguardando decisão",
        "/arranjo/plano",
        "Níveis que o fatiador propôs a partir dos códigos de referência.",
    ),
    (
        "tag_merge_proposals",
        "Propostas de merge de tags",
        "/assuntos/tags",
        "Conjuntos de grafias que a rotina propôs unificar; nenhum foi unificado.",
    ),
    (
        "cross_domain_conflicts",
        "Conflitos entre assunto e entidade",
        "/entidades/conflitos",
        "Termos que colidem: o mesmo nome é assunto e nome próprio.",
    ),
    (
        "subject_low_confidence",
        "Assunto com confiança baixa",
        "/assuntos/tags",
        "Tags que o classificador não teve confiança para arquivar numa gaveta.",
    ),
    (
        "orphan_subject_tags",
        "Tags sem gaveta de assunto",
        "/assuntos/tags",
        "Tags sem categoria: nenhum selo de assunto pode ser mostrado para elas.",
    ),
    (
        "anomalies",
        "Anomalias detectadas",
        "/qualidade/anomalias",
        "Documentos que o validador de qualidade marcou.",
    ),
    (
        "unreviewed_documents",
        "Documentos não revisados",
        "/acervo/lista?status=PENDING_AI",
        "O acervo que nenhum arquivista olhou ainda.",
    ),
)


class CurationService:
    """
    The curator's work list.

    A read-only view of the domain: it counts what is pending and says which screen resolves it.
    It owns the *presentation* of the queues (labels, order, routes) and the repository owns the
    counting, so a new queue is a line in the catalogue plus a count in the repository — never a
    new route, and never seven requests from the browser.
    """

    def __init__(self, repo: CurationRepository) -> None:
        self.repo = repo

    def inbox(self) -> CurationInbox:
        counts = self.repo.count_pending()
        return CurationInbox(
            queues=[
                CurationQueue(key=key, label=label, count=counts[key], route=route, description=description)
                for key, label, route, description in QUEUE_CATALOGUE
            ],
            generated_at=datetime.now(UTC),
        )
