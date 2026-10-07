from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class DocumentUpdateRequest(BaseModel):
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
    is_published: bool | None = Field(
        default=None,
        description="Decisão de difusão, ortogonal ao status de revisão. Publicar não bloqueia a IA "
        "de continuar melhorando o registro; aprovar, sim.",
    )

    changed_by: str | None = Field(default=None, description="Quem revisou (autoria, enquanto não há autenticação).")
    review_note: str | None = Field(default=None, description="Motivo da edição; fica no histórico.")

    model_config = ConfigDict(extra="forbid")


class TagLinkRequest(BaseModel):
    """Attaches or detaches one tag on one description, as a human decision."""

    tag_id: int = Field(description="Id da tag no vocabulário (GET /api/v1/taxonomy/tags).")
    changed_by: str | None = Field(default=None, description="Quem decidiu; texto livre até haver autenticação.")
    review_note: str | None = Field(default=None, description="Por que decidiu; fica no histórico do documento.")

    model_config = ConfigDict(extra="forbid")


class EntityLinkRequest(BaseModel):
    """Attaches or detaches one named entity on one description, as a human decision."""

    entity_id: int = Field(description="Id da entidade nomeada.")
    changed_by: str | None = Field(default=None, description="Quem decidiu; texto livre até haver autenticação.")
    review_note: str | None = Field(default=None, description="Por que decidiu; fica no histórico do documento.")

    model_config = ConfigDict(extra="forbid")
