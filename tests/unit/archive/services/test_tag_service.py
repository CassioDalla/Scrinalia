from unittest.mock import MagicMock, Mock

import pytest
from pytest_mock import MockerFixture
from sqlalchemy.orm import Session

from domains.archive.exceptions import InvalidParam
from domains.archive.schemas.tag_schema import MergeResponse
from domains.archive.services.tag_service import TagService

# ==========================================
# TESTES: extract_and_clean_tags
# ==========================================


def test_extract_and_clean_tags_sucesso(mocker: MockerFixture) -> None:
    """Caminho Feliz: Remove as stopwords do banco e limpa a string corretamente."""
    mock_db = mocker.Mock(spec=Session)
    mock_db.scalars.return_value.all.return_value = ["lixo", "ignorar"]

    service = TagService(mock_db)
    # Inclui espaços extras bizarros para testar o regex r"\s+"
    texto_bruto = "Tag Válida, Lixo, Ignorar, Outra   Tag   Boa"

    resultado = service.extract_and_clean_tags(texto_bruto)

    assert len(resultado) == 2
    nomes_extraidos = {tag.name for tag in resultado}
    assert "tag válida" in nomes_extraidos
    assert "outra tag boa" in nomes_extraidos


def test_extract_and_clean_tags_nulo_ou_vazio(mocker: MockerFixture) -> None:
    """Caminho Ruim: Garante o early return se a string for None ou vazia."""
    mock_db = mocker.Mock(spec=Session)
    service = TagService(mock_db)

    assert service.extract_and_clean_tags(None) == []
    assert service.extract_and_clean_tags("") == []
    # O banco nem deve ser consultado se a string for nula
    mock_db.scalars.assert_not_called()


def test_extract_and_clean_tags_apenas_stopwords(mocker: MockerFixture) -> None:
    """Caminho Ruim: A string continha apenas lixo e foi 100% limpa."""
    mock_db = mocker.Mock(spec=Session)
    mock_db.scalars.return_value.all.return_value = ["teste", "vazio"]

    service = TagService(mock_db)
    resultado = service.extract_and_clean_tags("Teste, Vazio, Teste")

    assert resultado == []


def test_extract_and_clean_tags_data_quality(mocker: MockerFixture) -> None:
    """Limites de Borda: Garante que tags anômalas (1 a 2 letras ou >100) são descartadas."""
    mock_db = mocker.Mock(spec=Session)
    mock_db.scalars.return_value.all.return_value = []

    service = TagService(mock_db)
    texto_bruto = "A, Oi, Tag Normal, " + ("X" * 105)

    resultado = service.extract_and_clean_tags(texto_bruto)

    # 'A' e 'Oi' são menores ou iguais a 2 caracteres. 'X'*105 é maior que 100.
    assert len(resultado) == 1
    assert resultado[0].name == "tag normal"


# ==========================================
# TESTES: purge_stopwords
# ==========================================


def test_purge_stopwords_remove_tags_sucesso(mocker: MockerFixture) -> None:
    """Caminho Feliz: Deleta as tags que coincidem com stopwords."""
    mock_db = mocker.Mock(spec=Session)

    mock_db.scalars.return_value.all.side_effect = [
        ["lixo"],  # Primeira chamada: busca stopwords
        [Mock(tag_id=1, name="lixo")],  # Segunda chamada: busca tags que coincidem
    ]

    service = TagService(mock_db)
    qtd_apagada = service.purge_stopwords()

    assert qtd_apagada == 1
    mock_db.delete.assert_called_once()
    mock_db.commit.assert_called_once()


def test_purge_stopwords_tabela_stopwords_vazia(mocker: MockerFixture) -> None:
    """Caminho Ruim: O banco de stopwords está vazio. O serviço deve abortar rápido."""
    mock_db = mocker.Mock(spec=Session)
    mock_db.scalars.return_value.all.return_value = []  # Nenhuma stopword cadastrada

    service = TagService(mock_db)
    qtd_apagada = service.purge_stopwords()

    assert qtd_apagada == 0
    mock_db.delete.assert_not_called()
    mock_db.commit.assert_not_called()


def test_purge_stopwords_nenhuma_tag_lixo_encontrada(mocker: MockerFixture) -> None:
    """Caminho Ruim: Existem stopwords, mas o acervo está limpo (nenhuma tag bate)."""
    mock_db = mocker.Mock(spec=Session)
    mock_db.scalars.return_value.all.side_effect = [
        ["lixo"],  # Existem stopwords
        [],  # Mas nenhuma tag com esse nome foi encontrada
    ]

    service = TagService(mock_db)
    qtd_apagada = service.purge_stopwords()

    assert qtd_apagada == 0
    mock_db.delete.assert_not_called()
    mock_db.commit.assert_not_called()


# ==========================================
# TESTES: merge_tags
# ==========================================


def test_merge_tags_transfere_e_apaga_sucesso(mocker: MockerFixture) -> None:
    """Caminho Feliz: Transfere os documentos, salva sinônimos e apaga as tags velhas."""
    mock_db = mocker.Mock(spec=Session)

    # 1. Simula a busca das tags que serão mortas
    tag_morta = Mock(tag_id=2, name="prefeituta")
    mock_db.scalars.return_value.all.return_value = [tag_morta]

    # 2. Simula a busca de documentos que possuíam a tag velha
    mock_db.execute.return_value.scalars.return_value.all.return_value = ["doc-1", "doc-2"]

    # 3. Simula o retorno do rowcount para o delete final
    mock_result = mocker.Mock()
    mock_result.rowcount = 1
    # Configura o execute() para retornar o mock_result na última chamada (o delete da tag)
    mock_db.execute.side_effect = [mocker.DEFAULT, mocker.DEFAULT, mocker.DEFAULT, mocker.DEFAULT, mock_result]

    service = TagService(mock_db)
    res: MergeResponse = service.merge_tags(canonical_id=1, ids_to_merge=[2])

    assert res.documents_updated == 2
    assert res.tags_deleted == 1
    assert mock_db.execute.call_count == 5


def test_merge_tags_lista_vazia(mocker: MockerFixture) -> None:
    """Caminho Ruim: O array de IDs a serem mesclados está vazio."""
    mock_db = mocker.Mock(spec=Session)
    service = TagService(mock_db)

    with pytest.raises(InvalidParam) as exc_info:
        service.merge_tags(canonical_id=1, ids_to_merge=[])

    # (Opcional, mas recomendado) Valida se a mensagem do erro está correta
    assert "A lista de tags para mesclar não pode estar vazia." in str(exc_info.value)

    mock_db.execute.assert_not_called()


def test_merge_tags_sem_documentos_afetados(mocker: MockerFixture) -> None:
    """
    Caminho Ruim/Parcial: A tag existe, mas nenhum documento a usa.
    Deve pular a transferência de documentos, mas AINDA ASSIM criar o sinônimo e apagá-la.
    """
    mock_db = mocker.Mock(spec=Session)

    tag_morta = Mock(tag_id=2, name="tag_sem_uso")
    mock_db.scalars.return_value.all.return_value = [tag_morta]

    # Nenhum documento usa a tag
    mock_db.execute.return_value.scalars.return_value.all.return_value = []

    # Configura o rowcount para o delete
    mock_result = mocker.Mock()
    mock_result.rowcount = 1
    mock_db.execute.side_effect = [mocker.DEFAULT, mocker.DEFAULT, mocker.DEFAULT, mock_result]

    service = TagService(mock_db)
    res = service.merge_tags(canonical_id=1, ids_to_merge=[2])

    assert res.documents_updated == 0
    assert res.tags_deleted == 1

    # Como não há documentos, o INSERT de transferência na ArchiveDocumentTag é pulado!
    # Restam apenas: 1 SELECT (docs) + 1 INSERT (synonyms) + 2 DELETEs (tags associativas e tag final)
    assert mock_db.execute.call_count == 4


# ==========================================
# TESTES: get_text_to_suggest_macro_category_tags
# ==========================================


def test_get_text_to_suggest_macro_category_tags(mocker):
    """Garante que a service busca tags no repositório correto."""
    mock_tag_repo = mocker.patch("domains.archive.services.tag_service.repo")
    mock_tag_repo.fetch_tags_for_clustering.return_value = ["tag1", "tag2"]

    service = TagService(db=MagicMock())
    resultado = service.get_text_to_suggest_macro_category(source_type="tags")

    mock_tag_repo.fetch_tags_for_clustering.assert_called_once_with(db=service.db)
    assert resultado == ["tag1", "tag2"]


def test_get_text_to_suggest_macro_category_documents(mocker):
    """Garante que a service busca documentos repassando as colunas."""
    mock_tag_repo = mocker.patch("domains.archive.services.tag_service.repo")
    mock_tag_repo.fetch_documents_for_clustering.return_value = ["doc1", "doc2"]

    service = TagService(db=MagicMock())
    colunas = ["scope_content"]

    resultado = service.get_text_to_suggest_macro_category(source_type="documents", columns_to_extract=colunas)

    mock_tag_repo.fetch_documents_for_clustering.assert_called_once_with(db=service.db, columns_to_extract=colunas)
    assert resultado == ["doc1", "doc2"]


def test_get_text_to_suggest_macro_category_invalid():
    """Garante o bloqueio caso passem um source_type não suportado."""
    service = TagService(db=MagicMock())

    with pytest.raises(InvalidParam) as exc_info:
        service.get_text_to_suggest_macro_category(source_type="invalido")  # type: ignore

    assert "O parâmetro 'source_type' deve ser obrigatoriamente 'tags' ou 'documents'." in str(exc_info.value)
