from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from domains.archive.models import ArchiveReviewStatus


class ArchiveDocumentDTO(BaseModel):
    """
    Contrato rigoroso de Inserção/Atualização para a Camada Archive.

    Atua como o guardião da integridade da tabela fato. Garante que scripts de
    migração e múltiplos workers de Inteligência Artificial trafeguem payloads
    completos e tipados ao atualizar o estado de enriquecimento do documento.
    """

    description_id: str = Field(description="ID herdado da Silver.")
    original_title: str = Field(description="Título original da Silver.")
    document_date: date | None = Field(default=None, description="Data do documento.")
    summary: str | None = Field(default=None, description="Resumo do documento.")
    staging_content_hash: str = Field(description="Hash de controle de linhagem e detecção de mudanças (CDC).")
    original_thumbnail_url: str | None = Field(
        default=None, description="Link de download público da thumbnail na fonte."
    )
    storage_thumbnail_uri: str | None = Field(
        default=None, description="URI ou Path interno do arquivo salvo no Object Storage"
    )

    # --- Metadados da Norma ISAD(G) ---
    reference_code: str | None = Field(default=None, description="Código de referência arquivística.")
    level: str | None = Field(default=None, description="Nível de descrição (ex: Dossiê, Item, Volume).")
    producers: str | None = Field(default=None, description="Entidades produtoras responsáveis pelo fundo/documento.")
    admin_bio_history: str | None = Field(default=None, description="História administrativa ou biografia do produtor.")
    admin_archival_history: str | None = Field(
        default=None, description="História arquivística (cadeia de custódia do documento)."
    )
    provenance: str | None = Field(default=None, description="Procedência / Proveniência do registro.")
    scope_content: str | None = Field(
        default=None, description="Âmbito e conteúdo (descrição detalhada do teor textual)."
    )
    language_name: str | None = Field(default=None, description="Idioma predominante no documento descritivo.")
    archivist_notes: str | None = Field(
        default=None, description="Notas e observações técnicas do arquivista que catalogou."
    )

    # --- Enriquecimento (Machine Learning) ---
    final_title: str | None = Field(default=None, description="Título gerado pela IA ou revisado.")
    semantic_search_vector: str | None = Field(default=None, description="Texto limpo para busca.")

    execution_log: dict[str, str] = Field(
        default_factory=dict,
        description="Rastreia quais workers (IA) já processaram o documento. Ex: {'ner_spacy': 'DONE'}",
    )

    # --- Governança (Human-In-The-Loop) ---
    review_status: ArchiveReviewStatus = Field(
        default=ArchiveReviewStatus.PENDING_AI, description="Status atual de auditoria."
    )
    is_anomaly: bool = Field(default=False, description="Flag de erro estrutural.")
    anomaly_reasons: list[str] | None = Field(default=None, description="Lista de erros encontrados.")

    model_config = ConfigDict(from_attributes=True)


class DocumentTagSummary(BaseModel):
    """Tag enxuta anexada a um documento na leitura do acervo."""

    tag_id: int
    name: str

    model_config = ConfigDict(from_attributes=True)


class DocumentEntitySummary(BaseModel):
    """Entidade nomeada (NER) enxuta anexada a um documento."""

    entity_id: int
    name: str
    entity_type: str

    model_config = ConfigDict(from_attributes=True)


class DocumentSummary(BaseModel):
    """Visão de leitura do acervo, consumida pela API e pelo front-end."""

    description_id: str
    original_title: str
    final_title: str | None = None
    document_date: date | None = None
    review_status: ArchiveReviewStatus
    is_anomaly: bool = False
    storage_thumbnail_uri: str | None = None
    scope_content: str | None = None
    admin_bio_history: str | None = None
    tags: list[DocumentTagSummary] = Field(default_factory=list)
    entities: list[DocumentEntitySummary] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class DocumentListResponse(BaseModel):
    """Página de resultados do acervo."""

    total: int
    limit: int
    offset: int
    items: list[DocumentSummary]
