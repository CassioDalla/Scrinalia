from sqlalchemy import select, text

from domains.archive.models import ArchiveDocument, ArchiveEntity, DomainSynonyms
from domains.archive.repository.entity_repo import EntityRepository
from domains.archive.schemas.entity_schema import ArchiveEntityDTO


def test_get_or_create_entities_new_and_existing(use_test_db, db_session):
    """Garante a criação e a idempotência de Entidades (NER)."""
    repo = EntityRepository(db_session)
    entidades_dto = [ArchiveEntityDTO(name="David Carneiro", entity_type="PER")]

    ids_passo_1 = repo.get_or_create_entities(entidades_dto)
    db_session.commit()

    ids_passo_2 = repo.get_or_create_entities(entidades_dto)
    db_session.commit()

    assert len(ids_passo_1) == 1
    assert ids_passo_1[0] == ids_passo_2[0]


def test_get_ner_synonyms_rules(use_test_db, db_session):
    """Testa a junção SQL que gera os padrões do spaCy baseados na tabela oficial de Sinônimos."""
    repo = EntityRepository(db_session)

    # 1. Cria a Entidade Canônica
    ent_canonica = ArchiveEntity(name="Prefeitura de Curitiba", entity_type="ORG")
    db_session.add(ent_canonica)
    db_session.commit()

    # 2. Cria o Sinônimo apontando para a Entidade
    sinonimo = DomainSynonyms(
        synonym_name="prefeitura municipal", category="ORG", canonical_entity_id=ent_canonica.entity_id
    )
    db_session.add(sinonimo)
    db_session.commit()

    # 3. Executa a query
    regras = repo.get_ner_synonyms_rules()

    assert len(regras) == 1
    assert regras[0]["pattern"] == "prefeitura municipal"
    assert regras[0]["label"] == "ORG"
    assert regras[0]["canonical_name"] == "Prefeitura de Curitiba"


def test_purge_orphan_entities(use_test_db, db_session):
    """Garante que apenas entidades sem documentos vinculados são apagadas."""
    repo = EntityRepository(db_session)

    ent_orfam = ArchiveEntity(name="Fantasma", entity_type="PER")
    ent_utilizada = ArchiveEntity(name="Útil", entity_type="LOC")
    doc = ArchiveDocument(description_id="doc_1", staging_content_hash="hash", original_title="AAA")

    db_session.add_all([ent_orfam, ent_utilizada, doc])
    db_session.commit()

    # Vincula apenas a entidade útil
    repo.link_entities_to_document("doc_1", [ent_utilizada.entity_id])
    db_session.commit()

    # Limpa as orfãs
    qtd_apagadas = repo.purge_orphan_entities()
    db_session.commit()

    assert qtd_apagadas == 1

    # Verifica o estado do banco
    entidades_restantes = db_session.scalars(select(ArchiveEntity)).all()
    assert len(entidades_restantes) == 1
    assert entidades_restantes[0].name == "Útil"


def test_find_similar_trgm(use_test_db, db_session):
    """Testa a integração com a extensão pg_trgm do PostgreSQL."""

    db_session.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm;"))
    db_session.commit()

    repo = EntityRepository(db_session)

    db_session.add_all(
        [
            ArchiveEntity(name="Winston Churchill", entity_type="PER"),
            ArchiveEntity(name="Winstn Churchil", entity_type="PER"),
            ArchiveEntity(name="Winston Chuechill", entity_type="LOC"),  # Erro proposital de tipo
            ArchiveEntity(name="Getúlio Vargas", entity_type="PER"),
        ]
    )
    db_session.commit()

    # Busca por algo parecido (target deve ser minúsculo devido à regra de negócio do Service)
    resultados = repo.find_similar("winston churchill", entity_type=None, threshold=0.5)

    # Deve encontrar os dois erros de digitação, ignorando a si mesmo e ao Getúlio
    assert len(resultados) == 2
    nomes_encontrados = [r.name for r in resultados]
    assert "Winstn Churchil" in nomes_encontrados
    assert "Winston Chuechill" in nomes_encontrados
