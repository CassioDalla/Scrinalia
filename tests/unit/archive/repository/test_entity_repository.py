from pytest_mock import MockerFixture
from sqlalchemy.orm import Session

from domains.archive.repository import EntityRepository


def test_get_or_create_entities_ignora_lista_vazia(mocker: MockerFixture) -> None:
    """Garante que o repositório não bate no banco à toa se não houver entidades."""
    mock_db = mocker.Mock(spec=Session)
    repo = EntityRepository(mock_db)

    resultado = repo.get_or_create_entities([])

    assert resultado == []
    mock_db.execute.assert_not_called()


def test_get_or_create_entities_happy_path(mocker: MockerFixture) -> None:
    """Garante que a função processa DTOs, tira espaços e chama INSERT/SELECT em massa."""
    mock_db = mocker.Mock(spec=Session)
    repo = EntityRepository(mock_db)

    # Criando DTOs fakes
    ent1 = mocker.Mock(name=" Winston Churchill  ", entity_type="PER")
    ent2 = mocker.Mock(name="Curitiba", entity_type="LOC")

    # Simulando que o banco retornou os IDs 1 e 2
    mock_db.scalars.return_value.all.return_value = [1, 2]

    resultado = repo.get_or_create_entities([ent1, ent2])

    assert resultado == [1, 2]
    # Garante que houve um execute (para o insert) e um scalars (para o select)
    assert mock_db.execute.call_count == 1
    assert mock_db.scalars.call_count == 1


def test_purge_orphan_entities_ignora_se_nenhuma_orfam(mocker: MockerFixture) -> None:
    """Garante que não há execute de DELETE se não forem encontrados órfãos."""
    mock_db = mocker.Mock(spec=Session)
    repo = EntityRepository(mock_db)

    # Simula que a busca de órfãos retornou vazio
    mock_db.scalars.return_value.all.return_value = []

    qtd_apagada = repo.purge_orphan_entities()

    assert qtd_apagada == 0
    # O mock_db.execute só seria chamado no DELETE. Como foi evitado, call_count == 0
    assert mock_db.execute.call_count == 0


def test_purge_orphan_entities_deleta_orfans_encontradas(mocker: MockerFixture) -> None:
    """Garante que o DELETE é chamado se existirem órfãos."""
    mock_db = mocker.Mock(spec=Session)
    repo = EntityRepository(mock_db)

    # Simula ids órfãos
    mock_db.scalars.return_value.all.return_value = [10, 20]
    # Simula o retorno do rowcount do delete
    mock_db.execute.return_value.rowcount = 2

    qtd_apagada = repo.purge_orphan_entities()

    assert qtd_apagada == 2
    assert mock_db.execute.call_count == 1  # Chamou o delete
