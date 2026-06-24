from unittest.mock import MagicMock, Mock

import pytest
from pytest_mock import MockerFixture
from sqlalchemy.orm import Session

from domains.archive.exceptions import InvalidParam
from domains.archive.schemas.schemas import ArchiveTagDTO
from domains.archive.schemas.tag_schema import MergeResponse
from domains.archive.services.tag_service import TagService


# TODO A SERVICE PASSOU A TER O REPO INJETADO, MUDAR OS TESTES


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
    res: MergeResponse = service.merge(canonical_id=1, ids_to_merge=[2])

    assert res.documents_updated == 2
    assert res.tags_deleted == 1
    assert mock_db.execute.call_count == 5


def test_merge_tags_lista_vazia(mocker: MockerFixture) -> None:
    """Caminho Ruim: O array de IDs a serem mesclados está vazio."""
    mock_db = mocker.Mock(spec=Session)
    service = TagService(mock_db)

    with pytest.raises(InvalidParam) as exc_info:
        service.merge(canonical_id=1, ids_to_merge=[])

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
    res = service.merge(canonical_id=1, ids_to_merge=[2])

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


# ==========================================
# TESTES: process_worker_tags
# ==========================================


def test_process_worker_tags_lista_vazia(mocker: MockerFixture) -> None:
    """Caminho Ruim: O worker enviou uma lista vazia, retorna rápido sem bater no banco."""
    mock_db = mocker.Mock(spec=Session)
    mock_repository = mocker.patch("domains.archive.services.tag_service.repo")

    service = TagService(mock_db)
    resultado = service.process_worker_tags([])

    assert resultado == []
    mock_repository.get_synonyms_mapping.assert_not_called()
    mock_repository.get_or_create_tags.assert_not_called()


def test_process_worker_tags_apenas_tags_novas_caminho_feliz(mocker: MockerFixture) -> None:
    """Caminho Feliz: Nenhuma tag é sinônimo, todas são enviadas para criação."""
    mock_db = mocker.Mock(spec=Session)
    mock_repository = mocker.patch("domains.archive.services.tag_service.repo")

    # Mocks: Banco retorna que não há sinônimos, e a criação gerou os IDs 10 e 11
    mock_repository.get_synonyms_mapping.return_value = {}
    mock_repository.get_or_create_tags.return_value = [10, 11]

    dtos = [
        ArchiveTagDTO(name="Urbanismo", macro_category_id=None, ai_confidence_score=None),
        ArchiveTagDTO(name="Asfalto", macro_category_id=None, ai_confidence_score=None),
    ]

    service = TagService(mock_db)
    resultado = service.process_worker_tags(dtos)

    assert set(resultado) == {10, 11}
    mock_repository.get_synonyms_mapping.assert_called_once()
    mock_repository.get_or_create_tags.assert_called_once_with(mock_db, dtos)


def test_process_worker_tags_apenas_sinonimos(mocker: MockerFixture) -> None:
    """Caminho de Substituição: O worker enviou APENAS sinônimos, pulando a criação no repositório."""
    mock_db = mocker.Mock(spec=Session)
    mock_repository = mocker.patch("domains.archive.services.tag_service.repo")

    # Mocks: Ambas as palavras já são sinônimos conhecidos mapeados para IDs 99 e 100
    mock_repository.get_synonyms_mapping.return_value = {"prefeiruta": 99, "parques": 100}

    dtos = [
        ArchiveTagDTO(name="Prefeiruta", macro_category_id=None, ai_confidence_score=None),
        ArchiveTagDTO(name="Parques", macro_category_id=None, ai_confidence_score=None),
    ]

    service = TagService(mock_db)
    resultado = service.process_worker_tags(dtos)

    assert set(resultado) == {99, 100}
    mock_repository.get_synonyms_mapping.assert_called_once()
    # Pula a criação, pois não sobrou nenhuma tag nova!
    mock_repository.get_or_create_tags.assert_not_called()


def test_process_worker_tags_misto_sinonimos_e_novas(mocker: MockerFixture) -> None:
    """Caminho Realista: A malha fina intercepta sinônimos e envia apenas as tags legítimas para o banco."""
    mock_db = mocker.Mock(spec=Session)
    mock_repository = mocker.patch("domains.archive.services.tag_service.repo")

    # Mocks: "leis" é sinônimo da tag canônica (ID 5). A tag "IPTU" não tem sinônimo e receberá o ID 88
    mock_repository.get_synonyms_mapping.return_value = {"leis": 5}
    mock_repository.get_or_create_tags.return_value = [88]

    dto_sinonimo = ArchiveTagDTO(name="Leis", macro_category_id=None, ai_confidence_score=None)
    dto_nova = ArchiveTagDTO(name="IPTU", macro_category_id=None, ai_confidence_score=None)

    service = TagService(mock_db)
    resultado = service.process_worker_tags([dto_sinonimo, dto_nova])

    assert set(resultado) == {5, 88}

    # Verifica se o service enviou APENAS a dto nova ("IPTU") para gravação
    args, _ = mock_repository.get_or_create_tags.call_args
    dtos_enviados_para_criacao = args[1]

    assert len(dtos_enviados_para_criacao) == 1
    assert dtos_enviados_para_criacao[0].name == "IPTU"


def test_process_worker_tags_deduplicacao_de_ids(mocker: MockerFixture) -> None:
    """Limites de Borda: Garante que múltiplas tags diferentes não gerem o mesmo ID duplicado no documento."""
    mock_db = mocker.Mock(spec=Session)
    mock_repository = mocker.patch("domains.archive.services.tag_service.repo")

    # Digamos que "parques" e "pracinhas" são ambos sinônimos para o ID 12 ("parque").
    # E "parque" também foi enviada (ela não é sinônimo, passará pela criação e retornará ID 12).
    mock_repository.get_synonyms_mapping.return_value = {"parques": 12, "pracinhas": 12}
    mock_repository.get_or_create_tags.return_value = [12]

    dtos = [
        ArchiveTagDTO(name="Parque", macro_category_id=None, ai_confidence_score=None),
        ArchiveTagDTO(name="Parques", macro_category_id=None, ai_confidence_score=None),
        ArchiveTagDTO(name="Pracinhas", macro_category_id=None, ai_confidence_score=None),
    ]

    service = TagService(mock_db)
    resultado = service.process_worker_tags(dtos)

    # O resultado deve ter apenas UM registro do ID 12. O uso do set() na service garante isso.
    assert len(resultado) == 1
    assert resultado == [12]
