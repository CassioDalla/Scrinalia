from sqlalchemy import select, text

from domains.archive.models import ArchiveEntity, ArchiveTag
from domains.archive.repository import EntityRepository

# ==========================================
# TESTES DE CHOQUE DE DOMÍNIOS (Cross-Domain)
# ==========================================


def test_get_cross_domain_conflicts(use_test_db, db_session):
    """Testa se o pg_trgm localiza conflitos reais entre as tabelas independentes."""

    db_session.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm;"))
    db_session.commit()

    repo = EntityRepository(db_session)

    # Criamos um cenário de conflito: "Batel" existe como Tag e como Entidade(LOC)
    db_session.add_all(
        [
            ArchiveTag(name="batel"),
            ArchiveEntity(name="Batel", entity_type="LOC"),
            ArchiveTag(name="ofício"),  # Não tem conflito
            ArchiveEntity(name="David Carneiro", entity_type="PER"),  # Não tem conflito
        ]
    )
    db_session.commit()

    conflitos = repo.get_cross_domain_conflicts(threshold=0.85)

    assert len(conflitos) == 1
    assert conflitos[0].tag_name == "batel"
    assert conflitos[0].entity_name == "Batel"
    assert conflitos[0].similarity >= 0.99  # São a mesma palavra


def test_resolve_cross_domain_conflict_tag_wins(use_test_db, db_session, generate_archive_doc):
    """Garante que a Tag absorve os documentos da Entidade e a Entidade é destruída."""
    from domains.archive.models import ArchiveDocumentEntity, ArchiveDocumentTag, ArchiveEntity

    repo = EntityRepository(db_session)

    tag = ArchiveTag(name="urbanismo")
    ent = ArchiveEntity(name="Urbanismo", entity_type="ORG")
    doc_da_entidade = generate_archive_doc(description_id="doc_1", original_title="Teste")

    db_session.add_all([tag, ent, doc_da_entidade])
    db_session.commit()

    # Vincula o documento SOMENTE à Entidade
    db_session.add(ArchiveDocumentEntity(description_id="doc_1", entity_id=ent.entity_id))
    db_session.commit()

    # A MÁGICA: A Tag vence o conflito
    docs_movidos = repo.resolve_cross_domain_conflict(winner="TAG", tag_id=tag.tag_id, entity_id=ent.entity_id)
    db_session.commit()

    assert docs_movidos == 1

    # A entidade deve ter deixado de existir
    ent_banco = db_session.get(ArchiveEntity, ent.entity_id)
    assert ent_banco is None

    # O documento agora deve estar na tabela ArchiveDocumentTag!
    vinculo_novo = db_session.scalars(select(ArchiveDocumentTag)).all()
    assert len(vinculo_novo) == 1
    assert vinculo_novo[0].tag_id == tag.tag_id
