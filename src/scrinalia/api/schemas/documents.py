from datetime import date

from pydantic import Field

from scrinalia.core.schemas import RequestModel


class DocumentUpdateRequest(RequestModel):
    """
    Every ISAD(G) field the archivist may correct.

    The archivist fixes the whole record, not only the title. ``changed_by`` carries the
    authorship while authentication does not exist (phase 4); ``review_note`` explains the
    edit and stays in the audit trail.
    """

    original_title: str | None = Field(default=None, description="Título original corrigido.")
    final_title: str | None = Field(default=None, description="Título final revisado pelo arquivista.")
    document_date: date | None = Field(default=None, description="Data do documento corrigida.")

    reference_code: str | None = Field(default=None, description="Código de referência.")
    level_id: int | None = Field(
        default=None,
        description="Nível de descrição: id no catálogo (GET /api/v1/hierarchy/levels). A grafia livre "
        "saiu do contrato quando a coluna de texto virou chave estrangeira.",
    )
    typology_id: int | None = Field(
        default=None,
        description="Tipologia documental: id no catálogo (GET /api/v1/typologies). É a forma "
        "diplomática do registro — ata, ofício, planta — que o classificador propõe e o arquivista "
        "pode corrigir. Um id fora do catálogo é recusado com 422.",
    )
    producers: str | None = Field(default=None, description="Produtor(es).")
    admin_bio_history: str | None = Field(default=None, description="História administrativa/biografia.")
    admin_archival_history: str | None = Field(default=None, description="História arquivística.")
    provenance: str | None = Field(default=None, description="Procedência.")
    scope_content: str | None = Field(default=None, description="Âmbito e conteúdo revisado.")
    language_name: str | None = Field(default=None, description="Idioma.")
    archivist_notes: str | None = Field(default=None, description="Notas do arquivista.")
    access_conditions: str | None = Field(
        default=None,
        description="ISAD(G) 4.1 — condições de acesso. Sem ele o acervo não tem como declarar "
        "que uma descrição é restrita, e a difusão não tem como respeitar a restrição.",
    )

    # O resto do registro ISAD(G). O acervo passou a guardar estas colunas e o arquivista é quem
    # completa ou corrige o que a origem não declarou; o corpo é o espelho de
    # ``DocumentReviewCommand`` sem os dois campos que a rota possui (o id vem do caminho, o autor
    # da sessão), e um teste pina a igualdade entre os dois.
    dimension_support: str | None = Field(default=None, description="ISAD(G) 3.1.5 — dimensão e suporte.")
    appraisal_destruction: str | None = Field(
        default=None, description="ISAD(G) 3.3.2 — avaliação, eliminação e temporalidade."
    )
    accruals: str | None = Field(default=None, description="ISAD(G) 3.3.3 — incorporações.")
    arrangement: str | None = Field(default=None, description="ISAD(G) 3.3.4 — sistema de arranjo.")
    reproduction_conditions: str | None = Field(default=None, description="ISAD(G) 3.4.2 — condições de reprodução.")
    physical_characteristics: str | None = Field(
        default=None, description="ISAD(G) 3.4.4 — características físicas e requisitos técnicos."
    )
    finding_aids: str | None = Field(default=None, description="ISAD(G) 3.4.5 — instrumentos de pesquisa.")
    originals_location: str | None = Field(
        default=None, description="ISAD(G) 3.5.1 — existência e localização dos originais."
    )
    copies_location: str | None = Field(
        default=None, description="ISAD(G) 3.5.2 — existência e localização das cópias."
    )
    related_units: str | None = Field(default=None, description="ISAD(G) 3.5.3 — unidades de descrição relacionadas.")
    publication_notes: str | None = Field(default=None, description="ISAD(G) 3.5.4 — notas de publicação.")
    conservation_notes: str | None = Field(default=None, description="Nota da instituição sobre o estado físico.")
    general_notes: str | None = Field(default=None, description="ISAD(G) 3.6.1 — notas gerais.")
    rules_conventions: str | None = Field(default=None, description="ISAD(G) 3.7.2 — regras ou convenções.")
    description_dates: str | None = Field(default=None, description="ISAD(G) 3.7.3 — datas da descrição.")

    is_published: bool | None = Field(
        default=None,
        description="Decisão de difusão, ortogonal ao status de revisão. Publicar não bloqueia a IA "
        "de continuar melhorando o registro; aprovar, sim.",
    )

    review_note: str | None = Field(default=None, description="Motivo da edição; fica no histórico.")


class TagLinkRequest(RequestModel):
    """Attaches or detaches one tag on one description, as a human decision."""

    tag_id: int = Field(description="Id da tag no vocabulário (GET /api/v1/taxonomy/tags).")
    review_note: str | None = Field(default=None, description="Por que decidiu; fica no histórico do documento.")


class EntityLinkRequest(RequestModel):
    """Attaches or detaches one named entity on one description, as a human decision."""

    entity_id: int = Field(description="Id da entidade nomeada.")
    review_note: str | None = Field(default=None, description="Por que decidiu; fica no histórico do documento.")
