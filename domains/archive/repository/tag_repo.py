from typing import cast

from sqlalchemy import CursorResult, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from domains.archive.models import (
    ArchiveTag,
    DomainStopwords,
)
from domains.archive.schemas.schemas import ArchiveTagDTO

def fetch_tags_for_clustering(db: Session) -> list[str]:
    """Busca apenas tags únicas que ainda não têm Macro Categoria."""
    stmt = select(ArchiveTag.name).where(ArchiveTag.macro_category_id.is_(None)).distinct()
    results = db.scalars(stmt).all()

    texts = [t for t in results if t and not t.replace(".", "").isdigit()]
    return texts

# TODO Buscar os sinonomios de tags no banco, se alguma tag for sinonimo, usar a canonica
def get_or_create_tags(db: Session, tags_list: list[ArchiveTagDTO]) -> list[int]:
    """
    Gerencia a dimensão de tags e taxonomias do mDeBERTa.
    Garante que termos idênticos (em minúsculas) partilhem o mesmo ID no banco.
    """

    if not tags_list:
        return []

    tag_ids = []
    for t in tags_list:
        # Tags oficiais sempre minúsculas para agrupamento perfeito (ex: alvenaria)
        name_clean = t.name.strip().lower()

        stmt = (
            insert(ArchiveTag)
            .values(
                name=name_clean,
                macro_category_id=t.macro_category_id,
                ai_confidence_score=t.ai_confidence_score,
            )
            .on_conflict_do_nothing(index_elements=["name"])
        )

        db.execute(stmt)

        id_query = select(ArchiveTag.tag_id).where(ArchiveTag.name == name_clean)
        tag_id = db.execute(id_query).scalar_one()
        tag_ids.append(tag_id)

    return tag_ids


def save_stopwords(db: Session, words_list: list[str]) -> int:
    """
    Insere uma lista de palavras na tabela de stopwords em lote.
    Retorna a quantidade exata de novas stopwords inseridas.
    """
    if not words_list:
        return 0

    clean_words = [{"word": w.strip().lower()} for w in words_list if w.strip()]

    if not clean_words:
        return 0

    stmt = insert(DomainStopwords).values(clean_words).on_conflict_do_nothing()

    result = cast(CursorResult, db.execute(stmt))
    return result.rowcount


def get_stopwords(db: Session) -> set[str]:
    """
    Recupera todas as stopwords de domínio cadastradas no banco de dados.
    Retorna um conjunto (Set) de stopwords

    Args:
        db (Session): Sessão ativa do SQLAlchemy.

    Returns:
        set[str]: Conjunto contendo todas as stopwords em letras minúsculas.
    """
    stmt = select(DomainStopwords.word)
    results = db.scalars(stmt).all()
    return set(results)