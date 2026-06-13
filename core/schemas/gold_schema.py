from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from core.models.gold_layer import GoldReviewStatus


# ==========================================
# DTOs para Entidades (Pessoas, Locais, Orgs)
# ==========================================
class GoldEntityDTO(BaseModel):
    name: str = Field(..., description="Nome limpo e formatado da entidade.")
    entity_type: Literal["PER", "ORG", "LOC"] = Field(..., description="Tipo da entidade.")

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# DTOs para Tags e Taxonomias
# ==========================================
class GoldTagDTO(BaseModel):
    """Contrato rigoroso para a criação de Tags via mDeBERTa."""

    name: str = Field(description="A palavra-chave, sempre em minúsculo.")
    macro_category: str | None = Field(default=None, description="A gaveta principal (ex: Urbanismo).")
    ai_confidence_score: float | None = Field(default=None, description="Certeza do modelo de IA (0 a 100).")

    model_config = ConfigDict(from_attributes=True)


class GoldDescriptionDTO(BaseModel):
    """
    Contrato rigoroso para a inserção/atualização de um Documento na Camada Ouro.
    Garante que a IA ou o script de migração enviem todos os dados necessários.
    """

    description_id: str = Field(description="ID herdado da Silver.")
    original_title: str = Field(description="Título original da Silver.")
    document_date: date | None = Field(default=None, description="Data do documento.")
    summary: str | None = Field(default=None, description="Resumo do documento.")
    silver_content_hash: str = Field(description="Hash de controle da Silver.")
    original_thumbnail_url: str | None = Field(default=None, description="Link de Dowload da Thumbnail")
    storage_thumbnail_uri: str | None = Field(default=None, description="URI ")

    # --- Metadados da Norma ISAD(G) (Herdados para leitura rápida no Front-end) ---
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

    # Enriquecimento
    final_title: str | None = Field(default=None, description="Título gerado pela IA ou revisado.")
    semantic_search_vector: str | None = Field(default=None, description="Texto limpo para busca.")

    execution_log: dict[str, str] = Field(
        default_factory=dict,
        description="Rastreia quais workers (IA) já processaram o documento. Ex: {'ner_spacy': 'completed'}",
    )

    # Governança
    review_status: GoldReviewStatus = Field(
        default=GoldReviewStatus.PENDING_AI, description="Status atual de auditoria."
    )
    is_anomaly: bool = Field(default=False, description="Flag de erro estrutural.")
    anomaly_reasons: list[str] | None = Field(default=None, description="Lista de erros encontrados.")

    model_config = ConfigDict(from_attributes=True)
