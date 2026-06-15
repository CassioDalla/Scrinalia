import enum
from datetime import date, datetime

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.base import Base


# ==========================================
# ENUMS DE AUDITORIA E STATUS
# ==========================================
class ArchiveReviewStatus(enum.StrEnum):
    """
    Controla o ciclo de vida da validação humana
    sobre o trabalho da IA.
    """

    PENDING_AI = "PENDING_AI"  # Aguardando os pipelines de IA rodarem
    AI_APPROVED = "AI_APPROVED"  # A IA corrigiu/classificou com alta confiança
    NEEDS_REVIEW = "NEEDS_REVIEW"  # A IA achou anomalia ou teve baixa confiança
    HUMAN_APPROVED = "HUMAN_APPROVED"  # O humano validou ou corrigiu manualmente (Trava Edição de IA)
    REJECTED = "REJECTED"  # O humano definiu que o dado é lixo


class DomainStopwords(Base):
    """Lista de stopwords específicas do domínio
    arquivístico para limpeza de NLP."""

    __tablename__ = "domain_stopwords"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    word: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)


class DomainSynonyms(Base):
    """
    Dicionário de sinônimos para normalização de Entidades e Tags.
    Mapeia termos variáveis ("pmc", "prefeituta") para uma entidade ou tag canônica.
    """

    __tablename__ = "domain_synonyms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # O nome do sinônimo (Ex: "pmc", "prefeituta", "washington")
    synonym_name: Mapped[str] = mapped_column(String(100), index=True, nullable=False)

    # O Discriminador: Define de qual universo esse sinônimo faz parte
    # Valores aceitos: 'TAG', 'ORG', 'LOC', 'PER'
    category: Mapped[str] = mapped_column(String(10), nullable=False, index=True)

    # Arcos Exclusivos: Chaves estrangeiras opcionais (Nullable)
    canonical_tag_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("archive_tags.tag_id", ondelete="CASCADE"), nullable=True
    )
    canonical_entity_id: Mapped[int | None] = mapped_column(
        Integer,
        # Verifique se o nome da tabela e coluna da sua entidade é este mesmo
        ForeignKey("archive_entities.entity_id", ondelete="CASCADE"),
        nullable=True,
    )

    __table_args__ = (
        # 1. Garante que a mesma palavra pode existir, DESDE QUE em categorias diferentes.
        # Ex: "Amazon" (LOC) e "Amazon" (ORG) podem conviver em paz.
        UniqueConstraint("synonym_name", "category", name="uix_synonym_category"),
        # 2. Integridade de Dados: Garante no motor do PostgreSQL que NUNCA
        # teremos uma linha sem destino, ou uma linha apontando para os dois lugares ao mesmo tempo.
        CheckConstraint(
            """
            (category = 'TAG' AND canonical_tag_id IS NOT NULL AND canonical_entity_id IS NULL) OR
            (category IN ('ORG', 'LOC', 'PER') AND canonical_entity_id IS NOT NULL AND canonical_tag_id IS NULL)
            """,
            name="chk_exclusive_synonym_target",
        ),
    )


# ==========================================
# 1. TABELAS DE DIMENSÃO (TAXONOMIA E NER)
# ==========================================
class ArchiveEntity(Base):
    """
    Entidades Nomeadas (Pessoas, Organizações, Locais).
    Descobertas dinamicamente pelo spaCy ou inseridas manualmente.
    """

    __tablename__ = "archive_entities"

    entity_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    descriptions: Mapped[list["ArchiveDocument"]] = relationship(
        secondary="archive_document_entities", back_populates="entities"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ArchiveTag(Base):
    """
    Tags e Taxonomias de Agrupamento.
    """

    __tablename__ = "archive_tags"

    tag_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    macro_category: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    ai_confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    descriptions: Mapped[list["ArchiveDocument"]] = relationship(
        secondary="archive_document_tags", back_populates="tags"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ==========================================
# 2. TABELA FATO (O ACERVO ENRIQUECIDO)
# ==========================================


class ArchiveDocument(Base):
    """
    O documento final, limpo e enriquecido.

    Esta é a base de dados central servida para os utilizadores finais,
    alimentada por múltiplos workers de Inteligência Artificial assíncronos.
    """

    __tablename__ = "archive_documents"

    description_id: Mapped[str] = mapped_column(String(50), primary_key=True)

    # --- Linhagem e Origem ---
    original_title: Mapped[str] = mapped_column(Text, nullable=False)
    document_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    staging_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    original_thumbnail_url: Mapped[str | None] = mapped_column(String, nullable=True)
    storage_thumbnail_uri: Mapped[str | None] = mapped_column(String, nullable=True)

    # --- Metadados Arquivísticos (ISAD-G) ---
    reference_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    level: Mapped[str | None] = mapped_column(Text, nullable=True)
    producers: Mapped[str | None] = mapped_column(Text, nullable=True)
    admin_bio_history: Mapped[str | None] = mapped_column(Text, nullable=True)
    admin_archival_history: Mapped[str | None] = mapped_column(Text, nullable=True)
    provenance: Mapped[str | None] = mapped_column(Text, nullable=True)
    scope_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    language_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    archivist_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Enriquecimento NLP/IA ---
    final_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    semantic_search_vector: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Estado dos Workers Descentralizados
    # Exemplo: {"ner_spacy_v1": "DONE", "mdeberta_tags": "PENDING"}
    execution_log: Mapped[dict] = mapped_column(JSONB, default=dict)

    # --- Auditoria (Human-in-the-Loop) ---
    review_status: Mapped[ArchiveReviewStatus] = mapped_column(
        Enum(ArchiveReviewStatus, name="archive_review_status_enum", create_type=True),
        default=ArchiveReviewStatus.PENDING_AI,
        nullable=False,
        index=True,
    )
    is_anomaly: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    anomaly_reasons: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)

    # --- Relacionamentos de IA ---
    entities: Mapped[list[ArchiveEntity]] = relationship(
        secondary="archive_document_entities", back_populates="descriptions"
    )
    tags: Mapped[list[ArchiveTag]] = relationship(secondary="archive_document_tags", back_populates="descriptions")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        # O Índice GIN é vital para a performance do polling dos Workers de IA
        Index("ix_archive_exec_log", execution_log, postgresql_using="gin"),
    )


# ==========================================
# 3. TABELAS DE LIGAÇÃO (PONTES N:N)
# ==========================================


class ArchiveDocumentEntity(Base):
    __tablename__ = "archive_document_entities"
    description_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("archive_documents.description_id", ondelete="CASCADE"), primary_key=True
    )
    entity_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("archive_entities.entity_id", ondelete="CASCADE"), primary_key=True
    )
    __table_args__ = (UniqueConstraint("description_id", "entity_id", name="uix_description_entity"),)


class ArchiveDocumentTag(Base):
    __tablename__ = "archive_document_tags"
    description_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("archive_documents.description_id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("archive_tags.tag_id", ondelete="CASCADE"), primary_key=True
    )
    __table_args__ = (UniqueConstraint("description_id", "tag_id", name="uix_description_tag"),)
