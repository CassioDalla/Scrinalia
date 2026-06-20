from unittest.mock import MagicMock, Mock

import pandas as pd
import pytest
from pytest_mock import MockerFixture
from sqlalchemy.orm import Session

from domains.archive.engines.clustering import registry
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
    docs_afetados, tags_apagadas = service.merge_tags(canonical_id=1, ids_to_merge=[2])

    assert docs_afetados == 2
    assert tags_apagadas == 1
    assert mock_db.execute.call_count == 5


def test_merge_tags_lista_vazia(mocker: MockerFixture) -> None:
    """Caminho Ruim: O array de IDs a serem mesclados está vazio."""
    mock_db = mocker.Mock(spec=Session)
    service = TagService(mock_db)

    docs, tags = service.merge_tags(canonical_id=1, ids_to_merge=[])

    assert docs == 0
    assert tags == 0
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
    docs_afetados, tags_apagadas = service.merge_tags(canonical_id=1, ids_to_merge=[2])

    assert docs_afetados == 0
    assert tags_apagadas == 1

    # Como não há documentos, o INSERT de transferência na ArchiveDocumentTag é pulado!
    # Restam apenas: 1 SELECT (docs) + 1 INSERT (synonyms) + 2 DELETEs (tags associativas e tag final)
    assert mock_db.execute.call_count == 4


# ==========================================
# TESTES: sugest_macro_categories
# ==========================================


def test_suggest_macro_categories_happy_path_tags(mock_registry, mocker):
    """Garante que a função formata corretamente as categorias sugeridas pela IA usando Tags."""
    # 1. Prepara os dados falsos do banco
    tags_falsas = [f"tag_{i}" for i in range(15)]  # Precisamos de > 10 para não cair no IF de escape
    mock_tag_repo = mocker.patch("domains.archive.services.tag_service.repo")
    mock_tag_repo.fetch_tags_for_clustering.return_value = tags_falsas

    # 2. Prepara o retorno falso do BERTopic (Pandas DataFrame)
    mock_df = pd.DataFrame(
        [
            {"Topic": 0, "Count": 10, "Representation": ["urbano", "rua", "obras"]},
            {"Topic": 1, "Count": 5, "Representation": ["lei", "decreto", "oficio"]},
        ]
    )
    # Tópico 0 para as 10 primeiras tags, Tópico 1 para as 5 últimas
    mock_topics = [0] * 10 + [1] * 5

    MockClass = mock_registry(registry)
    instancia_da_ia = MockClass.return_value

    instancia_da_ia.discover_topics.return_value = (mock_topics, mock_df)

    # 3. Execução
    service = TagService(db=MagicMock())
    resultado = service.suggest_macro_categories(source_type="tags", engine_name="motor_fake")  # type: ignore

    # 4. Verificações (Asserts)
    mock_tag_repo.fetch_tags_for_clustering.assert_called_once()
    instancia_da_ia.discover_topics.assert_called_once_with(tags_falsas)

    # Valida a formatação de negócios
    assert len(resultado) == 2
    assert resultado[0]["nome_sugerido"] == "Urbano - Rua - Obras"
    assert resultado[0]["volume_estimado"] == 10
    assert len(resultado[0]["amostras_reais"]) == 10  # Respeita o limite de fatiamento


def test_suggest_macro_categories_happy_path_documents(mock_registry, mocker):
    """Garante que a função repassa as colunas corretas quando busca por Documentos."""
    textos_docs = [f"Doc texto longo {i}" for i in range(12)]
    mock_tag_repo = mocker.patch("domains.archive.services.tag_service.repo")
    mock_tag_repo.fetch_documents_for_clustering.return_value = textos_docs

    MockClass = mock_registry(registry)
    instancia_da_ia = MockClass.return_value

    mock_df = pd.DataFrame([{"Topic": 0, "Count": 12, "Representation": ["teste", "doc", "ok"]}])
    instancia_da_ia.discover_topics.return_value = ([0] * 12, mock_df)

    service = TagService(db=MagicMock())
    colunas_teste = ["scope_content"]
    resultado = service.suggest_macro_categories(
        source_type="documents",
        columns_to_extract=colunas_teste,
        engine_name="motor_fake",  # type: ignore
    )

    # Verifica se as colunas foram passadas para o repositório
    mock_tag_repo.fetch_documents_for_clustering.assert_called_once_with(
        db=service.db, columns_to_extract=colunas_teste
    )
    assert 0 in resultado


def test_suggest_macro_categories_insufficient_texts(mock_registry, mocker):
    """Garante que a execução é abortada graciosamente se houver menos de 10 textos no banco."""
    # Apenas 5 tags no banco
    mock_tag_repo = mocker.patch("domains.archive.services.tag_service.repo")
    mock_tag_repo.fetch_tags_for_clustering.return_value = ["tag1", "tag2", "tag3", "tag4", "tag5"]

    service = TagService(db=MagicMock())
    resultado = service.suggest_macro_categories(engine_name="motor_fake")  # type: ignore

    MockClass = mock_registry(registry)
    instancia_da_ia = MockClass.return_value

    # Como não há dados suficientes, a IA não deve ser incomodada
    instancia_da_ia.discover_topics.assert_not_called()
    assert resultado == {}


def test_suggest_macro_categories_invalid_source_type():
    """Garante que um ValueError é lançado se o programador passar um 'source_type' inválido."""
    service = TagService(db=MagicMock())

    with pytest.raises(ValueError, match="O parâmetro 'source_type' deve ser 'tags' ou 'documents'"):
        service.suggest_macro_categories(source_type="invalido", engine_name="motor_fake")  # type: ignore


def test_suggest_macro_categories_ignores_noise_topic(mock_registry, mocker):
    """Garante que o tópico '-1' (ruído do BERTopic) é sumariamente ignorado e não aparece no JSON final."""
    tags_falsas = [f"tag_{i}" for i in range(12)]
    mock_tag_repo = mocker.patch("domains.archive.services.tag_service.repo")
    mock_tag_repo.fetch_tags_for_clustering.return_value = tags_falsas

    # O DataFrame contém o tópico -1 (que deve ser ignorado) e o 0 (que deve passar)
    mock_df = pd.DataFrame(
        [
            {"Topic": -1, "Count": 4, "Representation": ["lixo", "ruido", "aleatorio"]},
            {"Topic": 0, "Count": 8, "Representation": ["bom", "certo", "ok"]},
        ]
    )
    mock_topics = [-1] * 4 + [0] * 8

    MockClass = mock_registry(registry)
    instancia_da_ia = MockClass.return_value

    instancia_da_ia.discover_topics.return_value = (mock_topics, mock_df)

    service = TagService(db=MagicMock())
    resultado = service.suggest_macro_categories(engine_name="motor_fake")  # type: ignore

    # O tópico -1 NÃO deve estar nas chaves do dicionário de retorno
    assert -1 not in resultado
    assert 0 in resultado
    assert len(resultado) == 1
