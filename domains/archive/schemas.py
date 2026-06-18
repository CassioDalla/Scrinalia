from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from domains.archive.models import ArchiveReviewStatus


# ==========================================
# DTOs para Entidades (Pessoas, Locais, Orgs)
# ==========================================
class ArchiveEntityDTO(BaseModel):
    """
    Contrato de dados para Entidades Nomeadas (NER).

    Garante que os extratores (como o spaCy) retornem entidades
    padronizadas e validadas contra os tipos permitidos no domínio
    antes da persistência.
    """

    name: str = Field(description="Nome limpo e formatado da entidade.")
    entity_type: Literal["PER", "ORG", "LOC"] = Field(
        description="Tipo da entidade. Restrito a Pessoa, Organização ou Local."
    )

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# DTOs para Tags e Taxonomias
# ==========================================
class ArchiveTagDTO(BaseModel):
    """
    Contrato rigoroso para a criação de Tags (Taxonomia).

    Assegura que os modelos de classificação (ex: mDeBERTa) entreguem
    categorias consistentes acompanhadas de sua métrica de confiança
    para métricas de observabilidade.
    """

    name: str = Field(description="A palavra-chave ou conceito associado, preferencialmente em minúsculo.")
    macro_category_id: int | None = Field(
        default=None, description="Id linkando para a gaveta semântica principal (ex: Urbanismo, Saúde)"
    )
    ai_confidence_score: float | None = Field(
        default=None, description="Grau de certeza do modelo de IA (0.0 a 1.0 ou 0 a 100)."
    )

    model_config = ConfigDict(from_attributes=True)


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
