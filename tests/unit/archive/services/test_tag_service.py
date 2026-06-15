from unittest.mock import Mock

from pytest_mock import MockerFixture
from sqlalchemy.orm import Session

from domains.archive.services.tag_service import TagService


def test_extract_and_clean_tags_sucesso(mocker: MockerFixture) -> None:
    """Testa se o serviço remove as stopwords do banco e limpa a string."""
    mock_db = mocker.Mock(spec=Session)

    # Simula o banco de dados retornando a lista de stopwords
    mock_db.scalars.return_value.all.return_value = ["lixo", "ignorar"]

    service = TagService(mock_db)
    texto_bruto = "Tag Válida, Lixo, Ignorar, Outra Tag Boa"

    resultado = service.extract_and_clean_tags(texto_bruto)

    assert len(resultado) == 2
    # Valida se normalizou para minúsculo e removeu as stopwords
    nomes_extraidos = {tag.name for tag in resultado}
    assert "tag válida" in nomes_extraidos
    assert "outra tag boa" in nomes_extraidos


def test_extract_and_clean_tags_data_quality(mocker: MockerFixture) -> None:
    """Garante que tags anômalas (1 letra ou gigantes) são descartadas."""
    mock_db = mocker.Mock(spec=Session)
    mock_db.scalars.return_value.all.return_value = []

    service = TagService(mock_db)
    texto_bruto = "A, Tag Normal, " + ("X" * 105)

    resultado = service.extract_and_clean_tags(texto_bruto)

    assert len(resultado) == 1
    assert resultado[0].name == "tag normal"


def test_purge_stopwords_remove_tags_sucesso(mocker: MockerFixture) -> None:
    """Testa se o serviço deleta as tags que coincidem com stopwords."""
    mock_db = mocker.Mock(spec=Session)

    # 1. Simula as stopwords do banco
    mock_db.scalars.return_value.all.side_effect = [
        ["lixo"],  # Primeira chamada: busca stopwords
        [Mock(tag_id=1, name="lixo")],  # Segunda chamada: busca tags que coincidem
    ]

    service = TagService(mock_db)
    qtd_apagada = service.purge_stopwords()

    assert qtd_apagada == 1
    mock_db.delete.assert_called_once()
    mock_db.commit.assert_called_once()


def test_merge_tags_transfere_e_apaga(mocker: MockerFixture) -> None:
    """Testa a fusão de tags, criação de sinônimos e deleção das antigas."""
    mock_db = mocker.Mock(spec=Session)

    # 1. Simula a primeira query: self.db.scalars(...).all()
    tag_morta = Mock(tag_id=2, name="prefeituta")
    mock_db.scalars.return_value.all.return_value = [tag_morta]

    # 2. Simula a segunda query: self.db.execute(...).scalars().all()
    mock_db.execute.return_value.scalars.return_value.all.return_value = ["doc-1", "doc-2"]

    service = TagService(mock_db)
    docs_afetados, _tags_apagadas = service.merge_tags(canonical_id=1, ids_to_merge=[2])

    assert docs_afetados == 2

    # Verifica se o execute foi chamado corretamente para todas as operações
    # São 5 chamadas no total:
    # 1 SELECT (dos docs afetados) + 2 INSERTs (Transferência e Sinônimo) + 2 DELETEs (Vínculos e Tags)
    assert mock_db.execute.call_count == 5
