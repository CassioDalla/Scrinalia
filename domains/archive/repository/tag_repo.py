from typing import cast

from sqlalchemy import CursorResult, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from domains.archive.models import ArchiveMacroCategory, ArchiveTag, DomainStopwords, DomainSynonyms
from domains.archive.schemas import ArchiveMacroCategoryEntityDTO
from domains.archive.schemas.schemas import ArchiveTagDTO


def fetch_tags_for_clustering(db: Session) -> list[str]:
    """Busca apenas tags únicas que ainda não têm Macro Categoria."""
    stmt = select(ArchiveTag.name).where(ArchiveTag.macro_category_id.is_(None)).distinct()
    results = db.scalars(stmt).all()

    texts = [t for t in results if t and not t.replace(".", "").isdigit()]
    return texts


def get_synonyms_mapping(db: Session, words: list[str]) -> dict[str, int]:
    """
    Busca no banco se alguma das palavras fornecidas é um sinônimo conhecido.
    Retorna um dicionário mapeando: { 'nome_do_sinonimo': ID_da_Tag_Canonica }
    """
    if not words:
        return {}

    words_clean = [w.strip().lower() for w in words]

    stmt = select(DomainSynonyms.synonym_name, DomainSynonyms.canonical_tag_id).where(
        DomainSynonyms.category == "TAG", DomainSynonyms.synonym_name.in_(words_clean)
    )

    resultados = db.execute(stmt).all()
    return {row.synonym_name: row.canonical_tag_id for row in resultados}


def get_or_create_tags(db: Session, tags_list: list[ArchiveTagDTO]) -> list[int]:
    """
    Gerencia a dimensão de tags e taxonomias do mDeBERTa.
    Garante que termos idênticos (em minúsculas) partilhem o mesmo ID no banco.
    """

    if not tags_list:
        return []

    insert_data = []
    names_to_search = []

    for t in tags_list:
        name_clean = t.name.strip().lower()
        names_to_search.append(name_clean)
        insert_data.append(
            {
                "name": name_clean,
                "macro_category_id": t.macro_category_id,
                "ai_confidence_score": t.ai_confidence_score,
            }
        )

    # 2. Faz o INSERT massivo ignorando as tags que já existem (graças ao índice único na coluna 'name')
    stmt_insert = insert(ArchiveTag).values(insert_data).on_conflict_do_nothing(index_elements=["name"])
    db.execute(stmt_insert)

    # 3. Num ÚNICO select, busca todos os IDs (dos que acabaram de ser criados e dos que já existiam)
    stmt_select = select(ArchiveTag.tag_id).where(ArchiveTag.name.in_(names_to_search))

    return list(db.scalars(stmt_select).all())


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


def get_macro_categories(db: Session) -> list[ArchiveMacroCategoryEntityDTO]:

    stmt = select(
        ArchiveMacroCategory.category_id,
        ArchiveMacroCategory.name,
        ArchiveMacroCategory.description,
        ArchiveMacroCategory.is_active,
    )

    results = db.execute(stmt).mappings().all()
    return [ArchiveMacroCategoryEntityDTO.model_validate(r) for r in results]


# TODO
def create_macro_category(db: Session, m_category: ArchiveMacroCategoryEntityDTO): ...


# TODO pensar na melhor forma de fazer isso e nos args. Receber a model do banco, DTOS ou listas simples de ids
def link_to_macro_category(db: Session, tags_ids: list[int], m_category_id: int): ...
