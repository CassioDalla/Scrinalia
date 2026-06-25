from pytest_mock import MockerFixture
from sqlalchemy.orm import Session

from domains.archive.repository.tag_repo import TagRepository


def test_save_stopwords_ignora_lista_vazia_ou_suja(mocker: MockerFixture) -> None:
    """Garante que espaços em branco ou listas vazias não geram queries inúteis."""
    mock_db = mocker.Mock(spec=Session)
    repo = TagRepository(mock_db)

    # Nenhuma das palavras é válida
    resultado = repo.save_stopwords(["   ", ""])

    assert resultado == 0
    mock_db.execute.assert_not_called()


def test_fetch_tags_for_clustering_ignora_numeros(mocker: MockerFixture) -> None:
    """Garante que o repositório filtra tags que são apenas números ou números com pontos."""
    mock_db = mocker.Mock(spec=Session)
    repo = TagRepository(mock_db)

    # Simula o retorno do banco com palavras úteis e ruídos numéricos
    mock_db.scalars.return_value.all.return_value = ["urbano", "123", "ruas", "1.500", None]

    resultado = repo.fetch_tags_for_clustering()

    # Deve ignorar "123", "1.500" e None
    assert resultado == ["urbano", "ruas"]


def test_get_synonyms_mapping_ignora_lista_vazia(mocker: MockerFixture) -> None:
    """Caminho Triste: Evita ida ao banco se não houver palavras para buscar."""
    mock_db = mocker.Mock(spec=Session)
    repo = TagRepository(mock_db)

    resultado = repo.get_synonyms_mapping([])

    assert resultado == {}
    mock_db.execute.assert_not_called()


def test_get_synonyms_mapping_retorna_dicionario(mocker: MockerFixture) -> None:
    """Garante que a resposta SQL é convertida para um dicionário perfeito de mapeamento."""
    mock_db = mocker.Mock(spec=Session)
    repo = TagRepository(mock_db)

    row1 = mocker.Mock(synonym_name="prefeitura", canonical_tag_id=10)
    row2 = mocker.Mock(synonym_name="governo", canonical_tag_id=15)

    mock_db.execute.return_value.all.return_value = [row1, row2]

    resultado = repo.get_synonyms_mapping(["prefeitura", "governo"])

    assert resultado == {"prefeitura": 10, "governo": 15}
