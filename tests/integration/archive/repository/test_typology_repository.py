from domains.archive.models import ArchiveTypology
from domains.archive.repository.typology_repo import TypologyRepository


def test_get_active_typologies_from_db(use_test_db, db_session):
    """Testa a integração real do repositório de tipologias com o banco de dados."""
    repo = TypologyRepository(db_session)

    # Inserção de dados simulados no PostgreSQL/SQLite
    db_session.add_all(
        [
            ArchiveTypology(name="Carta", context_description="Correspondência oficial e pessoal."),
            ArchiveTypology(name="Memorando", context_description=None),
        ]
    )
    db_session.commit()

    # Executa o método
    resultados = repo.get_active_typologies()

    # Garante que os dados vieram formatados diretamente do banco
    assert isinstance(resultados, dict)
    assert "Carta: Correspondência oficial e pessoal." in resultados
    assert "Memorando" in resultados

    # Verifica os IDs (assumindo auto-incremento 1 e 2 no banco limpo)
    assert resultados["Memorando"] > 0
