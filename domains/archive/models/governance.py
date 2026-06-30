from sqlalchemy import (
    CheckConstraint,
    Enum,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from core.base import Base

from .enums import StopwordsScope


class DomainStopwords(Base):
    """Lista de stopwords específicas do domínio
    arquivístico para limpeza de NLP."""

    __tablename__ = "domain_stopwords"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    word: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    word_scope: Mapped[StopwordsScope] = mapped_column(
        Enum(StopwordsScope, name="stopwords_scope", create_type=False),
        default=StopwordsScope.TAG,
        nullable=False,
        index=True,
    )


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
