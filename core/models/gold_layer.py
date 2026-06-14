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
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base


# ==========================================
# ENUMS DE AUDITORIA E STATUS
# ==========================================
class GoldReviewStatus(enum.StrEnum):
    PENDING_AI = "PENDING_AI"  # Aguardando os pipelines de IA rodarem
    AI_APPROVED = "AI_APPROVED"  # A IA corrigiu/classificou com alta confiança
    NEEDS_REVIEW = "NEEDS_REVIEW"  # A IA achou anomalia ou teve baixa confiança
    HUMAN_APPROVED = "HUMAN_APPROVED"  # O humano validou ou corrigiu manualmente (Trava Edição de IA)
    REJECTED = "REJECTED"  # O humano definiu que o dado é lixo


class DomainStopwordsModel(Base):
    __tablename__ = "domain_stopwords"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    word: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)


class DomainSynonymsModel(Base):
    __tablename__ = "domain_synonyms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # O nome do sinônimo (Ex: "pmc", "prefeituta", "washington")
    synonym_name: Mapped[str] = mapped_column(String(100), index=True, nullable=False)

    # O Discriminador: Define de qual universo esse sinônimo faz parte
    # Valores aceitos: 'TAG', 'ORG', 'LOC', 'PER'
    category: Mapped[str] = mapped_column(String(10), nullable=False, index=True)

    # Arcos Exclusivos: Chaves estrangeiras opcionais (Nullable)
    canonical_tag_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("gold_tags.tag_id", ondelete="CASCADE"), nullable=True
    )

    canonical_entity_id: Mapped[int | None] = mapped_column(
        Integer,
        # Verifique se o nome da tabela e coluna da sua entidade é este mesmo
        ForeignKey("gold_entities.entity_id", ondelete="CASCADE"),
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
# 1. TABELAS DE DIMENSÃO
# ==========================================
class GoldEntityModel(Base):
    """
    Entidades Nomeadas (Pessoas, Organizações, Locais).
    Criadas por IA ou MANUALMENTE pelo painel administrativo.
    """

    __tablename__ = "gold_entities"

    entity_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    descriptions: Mapped[list["GoldDescriptionModel"]] = relationship(
        secondary="gold_description_entities", back_populates="entities"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GoldTagModel(Base):
    """
    Tags e Taxonomias de Agrupamento.
    """

    __tablename__ = "gold_tags"

    tag_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    macro_category: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    ai_confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    descriptions: Mapped[list["GoldDescriptionModel"]] = relationship(
        secondary="gold_description_tags", back_populates="tags"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ==========================================
# 2. TABELA FATO
# ==========================================


class GoldDescriptionModel(Base):
    """
    O documento final, limpo e enriquecido.
    """

    __tablename__ = "gold_descriptions"

    description_id: Mapped[str] = mapped_column(String(50), primary_key=True)

    # --- Dados Fundamentais (Herdados da Silver) ---
    original_title: Mapped[str] = mapped_column(Text, nullable=False)
    document_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    silver_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    original_thumbnail_url: Mapped[str | None] = mapped_column(String, nullable=True)
    storage_thumbnail_uri: Mapped[str | None] = mapped_column(String, nullable=True)

    # Metadados da Norma ISAD(G)
    reference_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    level: Mapped[str | None] = mapped_column(Text, nullable=True)
    producers: Mapped[str | None] = mapped_column(Text, nullable=True)
    admin_bio_history: Mapped[str | None] = mapped_column(Text, nullable=True)
    admin_archival_history: Mapped[str | None] = mapped_column(Text, nullable=True)
    provenance: Mapped[str | None] = mapped_column(Text, nullable=True)
    scope_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    language_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    archivist_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Enriquecimento e IA ---
    final_title: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Texto otimizado com spaCy (sem stopwords, lematizado) para Busca e BERTopic
    semantic_search_vector: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Rastreia quais pipelines já processaram este documento
    # Exemplo: {"ner_spacy_v1": "completed", "mdeberta_tags": "completed"}
    execution_log: Mapped[dict] = mapped_column(JSONB, default=dict)

    # --- Auditoria (Human-in-the-Loop) ---
    review_status: Mapped[GoldReviewStatus] = mapped_column(
        Enum(GoldReviewStatus, name="gold_review_status_enum", create_type=True),
        default=GoldReviewStatus.PENDING_AI,
        nullable=False,
        index=True,
    )
    is_anomaly: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    anomaly_reasons: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)

    # --- Relacionamentos ---
    entities: Mapped[list[GoldEntityModel]] = relationship(
        secondary="gold_description_entities", back_populates="descriptions"
    )
    tags: Mapped[list[GoldTagModel]] = relationship(secondary="gold_description_tags", back_populates="descriptions")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# ==========================================
# 3. TABELAS DE LIGAÇÃO (PONTES N:N)
# ==========================================


class GoldDescriptionEntityModel(Base):
    __tablename__ = "gold_description_entities"
    description_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("gold_descriptions.description_id", ondelete="CASCADE"), primary_key=True
    )
    entity_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("gold_entities.entity_id", ondelete="CASCADE"), primary_key=True
    )
    __table_args__ = (UniqueConstraint("description_id", "entity_id", name="uix_description_entity"),)


class GoldDescriptionTagModel(Base):
    __tablename__ = "gold_description_tags"
    description_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("gold_descriptions.description_id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[int] = mapped_column(Integer, ForeignKey("gold_tags.tag_id", ondelete="CASCADE"), primary_key=True)
    __table_args__ = (UniqueConstraint("description_id", "tag_id", name="uix_description_tag"),)
