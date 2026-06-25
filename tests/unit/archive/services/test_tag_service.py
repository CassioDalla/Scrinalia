from unittest.mock import Mock

import pytest
from pytest_mock import MockerFixture

from domains.archive.exceptions import InvalidMergeError, InvalidParam
from domains.archive.repository.document_repo import DocumentRepository
from domains.archive.repository.tag_repo import TagRepository
from domains.archive.schemas import ArchiveTagDTO
from domains.archive.schemas.tag_schema import MergeResponse
from domains.archive.services.tag_service import TagService

# ==========================================
# TESTES: extract_and_clean_tags
# ==========================================


def test_extract_and_clean_tags_sucesso(mocker: MockerFixture) -> None:
    """Caminho Feliz: Remove as stopwords usando o regex compilado e limpa a string corretamente."""
    mock_tag_repo = mocker.Mock(spec=TagRepository)
    mock_doc_repo = mocker.Mock(spec=DocumentRepository)

    # Ensinamos o repo falso a devolver um Set puro
    mock_tag_repo.get_stopwords.return_value = {"lixo", "ignorar"}

    service = TagService(mock_tag_repo, mock_doc_repo)
    texto_bruto = "Tag Válida, Lixo, Ignorar, Outra   Tag   Boa"

    resultado = service.extract_and_clean_tags(texto_bruto)

    assert len(resultado) == 2
    nomes_extraidos = {tag.name for tag in resultado}
    assert "tag válida" in nomes_extraidos
    assert "outra tag boa" in nomes_extraidos
    mock_tag_repo.get_stopwords.assert_called_once()


def test_extract_and_clean_tags_nulo_ou_vazio(mocker: MockerFixture) -> None:
    """Caminho Ruim: Garante o early return se a string for None ou vazia."""
    mock_tag_repo = mocker.Mock(spec=TagRepository)
    mock_doc_repo = mocker.Mock(spec=DocumentRepository)

    service = TagService(mock_tag_repo, mock_doc_repo)

    assert service.extract_and_clean_tags(None) == []
    assert service.extract_and_clean_tags("") == []
    # O repositório nem deve ser consultado
    mock_tag_repo.get_stopwords.assert_not_called()


def test_extract_and_clean_tags_apenas_stopwords(mocker: MockerFixture) -> None:
    """Caminho Ruim: A string continha apenas lixo e foi 100% limpa."""
    mock_tag_repo = mocker.Mock(spec=TagRepository)
    mock_doc_repo = mocker.Mock(spec=DocumentRepository)
    mock_tag_repo.get_stopwords.return_value = {"teste", "vazio"}

    service = TagService(mock_tag_repo, mock_doc_repo)
    resultado = service.extract_and_clean_tags("Teste, Vazio, Teste")

    assert resultado == []


def test_extract_and_clean_tags_data_quality(mocker: MockerFixture) -> None:
    """Limites de Borda: Garante que tags anômalas (1 a 2 letras ou >100) são descartadas."""
    mock_tag_repo = mocker.Mock(spec=TagRepository)
    mock_doc_repo = mocker.Mock(spec=DocumentRepository)
    mock_tag_repo.get_stopwords.return_value = set()  # Nenhuma stopword no banco

    service = TagService(mock_tag_repo, mock_doc_repo)
    texto_bruto = "A, Oi, Tag Normal, " + ("X" * 105)

    resultado = service.extract_and_clean_tags(texto_bruto)

    # 'A' e 'Oi' são menores ou iguais a 2 caracteres. 'X'*105 é maior que 100.
    assert len(resultado) == 1
    assert resultado[0].name == "tag normal"


# ==========================================
# TESTES: purge_stopwords
# ==========================================


def test_purge_stopwords_remove_tags_sucesso(mocker: MockerFixture) -> None:
    """Caminho Feliz: Coordena a busca de stopwords e a deleção em massa."""
    mock_tag_repo = mocker.Mock(spec=TagRepository)
    mock_doc_repo = mocker.Mock(spec=DocumentRepository)

    mock_tag_repo.get_stopwords.return_value = {"lixo"}
    mock_tag_repo.purge_tags_by_stopwords.return_value = 1  # Fingimos que apagou 1 tag

    service = TagService(mock_tag_repo, mock_doc_repo)
    qtd_apagada = service.purge_stopwords()

    assert qtd_apagada == 1
    mock_tag_repo.get_stopwords.assert_called_once()
    mock_tag_repo.purge_tags_by_stopwords.assert_called_once_with({"lixo"})


def test_purge_stopwords_tabela_stopwords_vazia(mocker: MockerFixture) -> None:
    """Caminho Ruim: O banco de stopwords está vazio. O serviço deve abortar rápido."""
    mock_tag_repo = mocker.Mock(spec=TagRepository)
    mock_doc_repo = mocker.Mock(spec=DocumentRepository)

    mock_tag_repo.get_stopwords.return_value = set()

    service = TagService(mock_tag_repo, mock_doc_repo)
    qtd_apagada = service.purge_stopwords()

    assert qtd_apagada == 0
    mock_tag_repo.purge_tags_by_stopwords.assert_not_called()


# ==========================================
# TESTES: merge_tags
# ==========================================


def test_merge_tags_transfere_e_apaga_sucesso(mocker: MockerFixture) -> None:
    """Caminho Feliz: Transfere os documentos, salva sinônimos e apaga as tags velhas."""
    mock_tag_repo = mocker.Mock(spec=TagRepository)
    mock_doc_repo = mocker.Mock(spec=DocumentRepository)

    # 1. Simula a validação da canônica e a busca das tags que serão mortas
    mock_tag_repo.get_by_id.return_value = Mock(tag_id=1, name="prefeitura")
    mock_tag_repo.get_by_ids.return_value = [Mock(tag_id=2, name="prefeituta")]

    # 2. Simula a busca de documentos que possuíam a tag velha
    mock_tag_repo.get_document_ids_by_tags.return_value = ["doc-1", "doc-2"]

    # 3. Simula o retorno do delete final
    mock_tag_repo.delete_tags.return_value = 1

    service = TagService(mock_tag_repo, mock_doc_repo)
    res: MergeResponse = service.merge(canonical_id=1, ids_to_merge=[2])

    assert res.documents_updated == 2
    assert res.tags_deleted == 1

    # Verifica a coordenação do Service
    mock_tag_repo.link_documents_to_tag.assert_called_once_with({"doc-1", "doc-2"}, 1)
    mock_tag_repo.create_synonyms.assert_called_once()
    mock_tag_repo.delete_tags.assert_called_once_with([2])


def test_merge_tags_lista_vazia(mocker: MockerFixture) -> None:
    """Caminho Ruim: O array de IDs a serem mesclados está vazio."""
    mock_tag_repo = mocker.Mock(spec=TagRepository)
    mock_doc_repo = mocker.Mock(spec=DocumentRepository)
    service = TagService(mock_tag_repo, mock_doc_repo)

    with pytest.raises(InvalidParam) as exc_info:
        service.merge(canonical_id=1, ids_to_merge=[])

    assert "A lista de tags para mesclar não pode estar vazia." in str(exc_info.value)
    mock_tag_repo.get_by_id.assert_not_called()


def test_merge_tags_id_canocical_in_id_to_merge(mocker: MockerFixture) -> None:
    """Caminho Ruim: O array de IDs a serem mesclados contem o id canonico."""
    mock_tag_repo = mocker.Mock(spec=TagRepository)
    mock_doc_repo = mocker.Mock(spec=DocumentRepository)
    service = TagService(mock_tag_repo, mock_doc_repo)

    with pytest.raises(InvalidMergeError) as exc_info:
        service.merge(canonical_id=1, ids_to_merge=[1])

    assert "O ID da tag canônica não pode estar na lista de exclusão." in str(exc_info.value)
    mock_tag_repo.get_by_id.assert_not_called()


def test_merge_tags_sem_documentos_afetados(mocker: MockerFixture) -> None:
    """
    Caminho Parcial: A tag existe, mas nenhum documento a usa.
    Deve pular a transferência de documentos, mas AINDA ASSIM criar o sinônimo e apagá-la.
    """
    mock_tag_repo = mocker.Mock(spec=TagRepository)
    mock_doc_repo = mocker.Mock(spec=DocumentRepository)

    mock_tag_repo.get_by_id.return_value = Mock(tag_id=1, name="oficial")
    mock_tag_repo.get_by_ids.return_value = [Mock(tag_id=2, name="tag_sem_uso")]

    # Nenhum documento usa a tag
    mock_tag_repo.get_document_ids_by_tags.return_value = []
    mock_tag_repo.delete_tags.return_value = 1

    service = TagService(mock_tag_repo, mock_doc_repo)
    res = service.merge(canonical_id=1, ids_to_merge=[2])

    assert res.documents_updated == 0
    assert res.tags_deleted == 1

    # Como não há documentos, o INSERT de transferência é pulado!
    mock_tag_repo.link_documents_to_tag.assert_not_called()
    mock_tag_repo.create_synonyms.assert_called_once()
    mock_tag_repo.delete_tags.assert_called_once_with([2])


# ==========================================
# TESTES: get_text_to_suggest_macro_category
# ==========================================


def test_get_text_to_suggest_macro_category_tags(mocker: MockerFixture):
    """Garante que a service busca tags no repositório de Tags."""
    mock_tag_repo = mocker.Mock(spec=TagRepository)
    mock_doc_repo = mocker.Mock(spec=DocumentRepository)

    mock_tag_repo.fetch_tags_for_clustering.return_value = ["tag1", "tag2"]

    service = TagService(mock_tag_repo, mock_doc_repo)
    resultado = service.get_text_to_suggest_macro_category(source_type="tags")

    mock_tag_repo.fetch_tags_for_clustering.assert_called_once()
    assert resultado == ["tag1", "tag2"]


def test_get_text_to_suggest_macro_category_documents(mocker: MockerFixture):
    """Garante que a service delega corretamente a busca de documentos para o DocumentRepository."""
    mock_tag_repo = mocker.Mock(spec=TagRepository)
    mock_doc_repo = mocker.Mock(spec=DocumentRepository)

    mock_doc_repo.fetch_documents_for_clustering.return_value = ["doc1", "doc2"]

    service = TagService(mock_tag_repo, mock_doc_repo)
    colunas = ["scope_content"]

    resultado = service.get_text_to_suggest_macro_category(source_type="documents", columns_to_extract=colunas)

    mock_doc_repo.fetch_documents_for_clustering.assert_called_once_with(columns_to_extract=colunas)
    assert resultado == ["doc1", "doc2"]


def test_get_text_to_suggest_macro_category_invalid(mocker: MockerFixture):
    """Garante o bloqueio caso passem um source_type não suportado."""
    mock_tag_repo = mocker.Mock(spec=TagRepository)
    mock_doc_repo = mocker.Mock(spec=DocumentRepository)

    service = TagService(mock_tag_repo, mock_doc_repo)

    with pytest.raises(InvalidParam) as exc_info:
        service.get_text_to_suggest_macro_category(source_type="invalido")  # type: ignore

    assert "O parâmetro 'source_type' deve ser obrigatoriamente 'tags' ou 'documents'." in str(exc_info.value)


# ==========================================
# TESTES: process_worker_tags
# ==========================================


def test_process_worker_tags_lista_vazia(mocker: MockerFixture) -> None:
    """Caminho Ruim: O worker enviou uma lista vazia, retorna rápido sem bater no repositório."""
    mock_tag_repo = mocker.Mock(spec=TagRepository)
    mock_doc_repo = mocker.Mock(spec=DocumentRepository)

    service = TagService(mock_tag_repo, mock_doc_repo)
    resultado = service.process_worker_tags([])

    assert resultado == []
    mock_tag_repo.get_synonyms_mapping.assert_not_called()
    mock_tag_repo.get_or_create_tags.assert_not_called()


def test_process_worker_tags_apenas_tags_novas_caminho_feliz(mocker: MockerFixture) -> None:
    """Caminho Feliz: Nenhuma tag é sinônimo, todas são enviadas para criação."""
    mock_tag_repo = mocker.Mock(spec=TagRepository)
    mock_doc_repo = mocker.Mock(spec=DocumentRepository)

    # Mocks: Banco retorna que não há sinônimos, e a criação gerou os IDs 10 e 11
    mock_tag_repo.get_synonyms_mapping.return_value = {}
    mock_tag_repo.get_or_create_tags.return_value = [10, 11]

    dtos = [
        ArchiveTagDTO(name="Urbanismo", macro_category_id=None, ai_confidence_score=None),
        ArchiveTagDTO(name="Asfalto", macro_category_id=None, ai_confidence_score=None),
    ]

    service = TagService(mock_tag_repo, mock_doc_repo)
    resultado = service.process_worker_tags(dtos)

    assert set(resultado) == {10, 11}
    mock_tag_repo.get_synonyms_mapping.assert_called_once()
    mock_tag_repo.get_or_create_tags.assert_called_once_with(dtos)


def test_process_worker_tags_apenas_sinonimos(mocker: MockerFixture) -> None:
    """Caminho de Substituição: O worker enviou APENAS sinônimos, pulando a criação no repositório."""
    mock_tag_repo = mocker.Mock(spec=TagRepository)
    mock_doc_repo = mocker.Mock(spec=DocumentRepository)

    # Mocks: Ambas as palavras já são sinônimos conhecidos mapeados para IDs 99 e 100
    mock_tag_repo.get_synonyms_mapping.return_value = {"prefeiruta": 99, "parques": 100}

    dtos = [
        ArchiveTagDTO(name="Prefeiruta", macro_category_id=None, ai_confidence_score=None),
        ArchiveTagDTO(name="Parques", macro_category_id=None, ai_confidence_score=None),
    ]

    service = TagService(mock_tag_repo, mock_doc_repo)
    resultado = service.process_worker_tags(dtos)

    assert set(resultado) == {99, 100}
    mock_tag_repo.get_synonyms_mapping.assert_called_once()
    # Pula a criação, pois não sobrou nenhuma tag nova!
    mock_tag_repo.get_or_create_tags.assert_not_called()


def test_process_worker_tags_misto_sinonimos_e_novas(mocker: MockerFixture) -> None:
    """Caminho Realista: A malha fina intercepta sinônimos e envia apenas as tags legítimas para o banco."""
    mock_tag_repo = mocker.Mock(spec=TagRepository)
    mock_doc_repo = mocker.Mock(spec=DocumentRepository)

    # Mocks: "leis" é sinônimo da tag canônica (ID 5). A tag "IPTU" não tem sinônimo e receberá o ID 88
    mock_tag_repo.get_synonyms_mapping.return_value = {"leis": 5}
    mock_tag_repo.get_or_create_tags.return_value = [88]

    dto_sinonimo = ArchiveTagDTO(name="Leis", macro_category_id=None, ai_confidence_score=None)
    dto_nova = ArchiveTagDTO(name="IPTU", macro_category_id=None, ai_confidence_score=None)

    service = TagService(mock_tag_repo, mock_doc_repo)
    resultado = service.process_worker_tags([dto_sinonimo, dto_nova])

    assert set(resultado) == {5, 88}

    # Verifica se o service enviou APENAS a dto nova ("IPTU") para gravação
    mock_tag_repo.get_or_create_tags.assert_called_once()
    dtos_enviados_para_criacao = mock_tag_repo.get_or_create_tags.call_args[0][0]

    assert len(dtos_enviados_para_criacao) == 1
    assert dtos_enviados_para_criacao[0].name == "IPTU"


def test_process_worker_tags_deduplicacao_de_ids(mocker: MockerFixture) -> None:
    """Limites de Borda: Garante que múltiplas tags diferentes não gerem o mesmo ID duplicado no documento."""
    mock_tag_repo = mocker.Mock(spec=TagRepository)
    mock_doc_repo = mocker.Mock(spec=DocumentRepository)

    # Digamos que "parques" e "pracinhas" são ambos sinônimos para o ID 12 ("parque").
    # E "parque" também foi enviada (ela não é sinônimo, passará pela criação e retornará ID 12).
    mock_tag_repo.get_synonyms_mapping.return_value = {"parques": 12, "pracinhas": 12}
    mock_tag_repo.get_or_create_tags.return_value = [12]

    dtos = [
        ArchiveTagDTO(name="Parque", macro_category_id=None, ai_confidence_score=None),
        ArchiveTagDTO(name="Parques", macro_category_id=None, ai_confidence_score=None),
        ArchiveTagDTO(name="Pracinhas", macro_category_id=None, ai_confidence_score=None),
    ]

    service = TagService(mock_tag_repo, mock_doc_repo)
    resultado = service.process_worker_tags(dtos)

    # O resultado deve ter apenas UM registro do ID 12. O uso do set() na service garante isso.
    assert len(resultado) == 1
    assert resultado == [12]
