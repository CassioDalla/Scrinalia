import pandas as pd
from sqlalchemy import select, text

from domains.archive import repository
from domains.archive.engines.clustering import registry as clustering_registry
from domains.archive.models import ArchiveDocument, ArchiveDocumentTag, ArchiveMacroCategory, ArchiveTag, DomainSynonyms
from domains.archive.services.tag_service import TagService

# ==========================================
# 1. TESTES DE PURGE (STOPWORDS)
# ==========================================


def test_purge_stopwords_success(use_test_db, db_session):
    """Garante que as stopwords são lidas do banco e apagadas."""
    service = TagService(db_session)

    # 1. Prepara o banco com tags
    db_session.add_all([ArchiveTag(name="ofício"), ArchiveTag(name="valiosa"), ArchiveTag(name="curitiba")])

    # 2. Insere as stopwords no dicionário (simulando o frontend)
    repository.save_stopwords(db_session, [" OFÍCIO ", "Curitiba"])
    db_session.commit()

    # 3. O método deve ler do banco e apagar
    apagadas = service.purge_stopwords()

    assert apagadas == 2
    restantes = db_session.scalars(select(ArchiveTag.name)).all()
    assert restantes == ["valiosa"]


def test_purge_stopwords_cascade(use_test_db, db_session, generate_archive_doc):
    """Garante que apagar uma tag também destrói os vínculos N:N (Cascade)."""
    service = TagService(db_session)

    tag_lixo = ArchiveTag(name="lixo")
    doc = generate_archive_doc(description_id="doc_1")
    db_session.add(tag_lixo)
    db_session.commit()

    db_session.add(ArchiveDocumentTag(description_id=doc.description_id, tag_id=tag_lixo.tag_id))
    repository.save_stopwords(db_session, ["lixo"])
    db_session.commit()

    service.purge_stopwords()

    # A tabela de vínculos também deve estar vazia agora
    vinculos = db_session.scalars(select(ArchiveDocumentTag)).all()
    assert len(vinculos) == 0


def test_purge_stopwords_empty_db(use_test_db, db_session):
    """Garante que a função retorna 0 se não encontrar nada."""
    service = TagService(db_session)
    apagadas = service.purge_stopwords()
    assert apagadas == 0


# ==========================================
# 2. TESTES DE CONTAGEM E ESTATÍSTICA (RELEVANCE)
# ==========================================


def test_get_tag_relevance_count(use_test_db, db_session, generate_archive_doc):
    """Garante que a contagem agrupa e ordena da mais usada para a menos usada."""
    service = TagService(db_session)

    tag_comum = ArchiveTag(name="comum")
    tag_rara = ArchiveTag(name="rara")
    doc1 = generate_archive_doc(description_id="doc_1")
    doc2 = generate_archive_doc(description_id="doc_2")

    db_session.add_all([tag_comum, tag_rara])
    db_session.commit()

    db_session.add_all(
        [
            ArchiveDocumentTag(description_id=doc1.description_id, tag_id=tag_comum.tag_id),
            ArchiveDocumentTag(description_id=doc2.description_id, tag_id=tag_comum.tag_id),
            ArchiveDocumentTag(description_id=doc1.description_id, tag_id=tag_rara.tag_id),
        ]
    )
    db_session.commit()

    resultados = service.get_tag_relevance_count(limit=5)

    assert len(resultados) == 2
    assert resultados[0] == ("comum", 2)
    assert resultados[1] == ("rara", 1)


def test_get_tag_relevance_tfidf(use_test_db, db_session, generate_archive_doc):
    """
    Testa o motor matemático de TF-IDF.
    Tags que aparecem em TODOS os documentos devem ter o IDF zerado.
    """
    service = TagService(db_session)

    tag_onipresente = ArchiveTag(name="onipresente")
    tag_especifica = ArchiveTag(name="especifica")
    db_session.add_all([tag_onipresente, tag_especifica])
    db_session.commit()

    # Criamos 4 documentos no total
    docs = [generate_archive_doc(description_id=f"doc_{i}") for i in range(4)]

    # A Onipresente está nos 4 documentos
    for d in docs:
        db_session.add(ArchiveDocumentTag(description_id=d.description_id, tag_id=tag_onipresente.tag_id))

    # A Específica está em apenas 1 documento
    db_session.add(ArchiveDocumentTag(description_id=docs[0].description_id, tag_id=tag_especifica.tag_id))
    db_session.commit()

    resultados = service.get_tag_relevance_tfidf()

    nome_primeiro_lugar = resultados[0][0]
    score_primeiro_lugar = resultados[0][3]
    nome_segundo_lugar = resultados[1][0]
    score_segundo_lugar = resultados[1][3]

    assert nome_primeiro_lugar == "especifica"
    assert score_primeiro_lugar > 0
    assert nome_segundo_lugar == "onipresente"
    assert score_segundo_lugar == 0.0  # ln(4/4) = 0


def test_get_tag_relevance_tfidf_empty_db(use_test_db, db_session):
    service = TagService(db_session)
    assert service.get_tag_relevance_tfidf() == []


# ==========================================
# 3. TESTES DE ALGORITMO APROXIMADO (PG_TRGM)
# ==========================================


def test_find_similar_tags(use_test_db, db_session):
    """Garante que a busca trigramática acha erros de digitação e obedece ao threshold."""
    # Instala a extensão no banco de testes do Docker
    db_session.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm;"))
    db_session.commit()

    service = TagService(db_session)

    db_session.add_all([ArchiveTag(name="prefeitura"), ArchiveTag(name="prefeituta"), ArchiveTag(name="abacate")])
    db_session.commit()

    similares = service.find_similar_tags("prefeitura", threshold=0.3)

    assert len(similares) == 1
    assert similares[0][1] == "prefeituta"
    assert similares[0][2] > 0.4


# ==========================================
# 4. TESTES DE MESCLAGEM (MERGE)
# ==========================================


def test_merge_tags_success(use_test_db, db_session, generate_archive_doc):
    """Testa o fluxo feliz: move docs, cria sinônimos e apaga a tag antiga."""
    service = TagService(db_session)

    tag_oficial = ArchiveTag(name="foto")
    tag_erro = ArchiveTag(name="fotu")
    doc = generate_archive_doc(description_id="doc_1")

    db_session.add_all([tag_oficial, tag_erro])
    db_session.commit()

    db_session.add(ArchiveDocumentTag(description_id=doc.description_id, tag_id=tag_erro.tag_id))
    db_session.commit()

    docs_afetados, tags_apagadas = service.merge_tags(tag_oficial.tag_id, [tag_erro.tag_id])

    assert docs_afetados == 1
    assert tags_apagadas == 1

    sinonimo = db_session.scalars(select(DomainSynonyms)).first()
    assert sinonimo.synonym_name == "fotu"
    assert sinonimo.canonical_tag_id == tag_oficial.tag_id
    assert sinonimo.category == "TAG"


def test_merge_tags_idempotency_conflict(use_test_db, db_session, generate_archive_doc):
    """Testa a blindagem UniqueConstraint. Se o doc já tiver as duas tags, não deve explodir."""
    service = TagService(db_session)

    tag_oficial = ArchiveTag(name="foto")
    tag_erro = ArchiveTag(name="fotu")
    doc = generate_archive_doc(description_id="doc_1")

    db_session.add_all([tag_oficial, tag_erro])
    db_session.commit()

    db_session.add_all(
        [
            ArchiveDocumentTag(description_id=doc.description_id, tag_id=tag_oficial.tag_id),
            ArchiveDocumentTag(description_id=doc.description_id, tag_id=tag_erro.tag_id),
        ]
    )
    db_session.commit()

    _docs_afetados, tags_apagadas = service.merge_tags(tag_oficial.tag_id, [tag_erro.tag_id])

    assert tags_apagadas == 1
    qtd_vinculos = db_session.query(ArchiveDocumentTag).count()
    assert qtd_vinculos == 1  # Apenas o oficial restou


# ==========================================
# TESTES DE INTEGRAÇÃO (DB REAL + IA MOCKADA)
# ==========================================


def test_integration_suggest_categories_happy_path_tags(db_session, mock_registry):
    """
    Testa a integração real entre o Service, o Repository e o PostgreSQL via Tags.
    """

    # 1. Criamos a Macro Categoria primeiro para respeitar a Foreign Key
    macro = ArchiveMacroCategory(name="Categoria Ignorada", description="Teste")
    db_session.add(macro)
    db_session.flush()  # O flush envia para o banco e gera o ID, mas mantém na transação

    # 2. Inserimos 12 tags orfãs reais
    for i in range(12):
        db_session.add(ArchiveTag(name=f"Tag Real {i}", macro_category_id=None))

    # 3. Inserimos 1 tag que já tem categoria usando o ID gerado (não deve ser puxada pela query)
    db_session.add(ArchiveTag(name="Tag Ignorada", macro_category_id=macro.category_id))
    db_session.commit()

    MockClass = mock_registry(clustering_registry)
    instancia_da_ia = MockClass.return_value
    mock_df = pd.DataFrame([{"Topic": 0, "Count": 12, "Representation": ["teste", "banco", "real"]}])
    instancia_da_ia.discover_topics.return_value = ([0] * 12, mock_df)

    service = TagService(db=db_session)
    resultado = service.suggest_macro_categories(source_type="tags")

    # Garante que a IA recebeu as 12 tags e ignorou a que já tinha categoria
    argumentos_passados_pra_ia = instancia_da_ia.discover_topics.call_args[0][0]
    assert len(argumentos_passados_pra_ia) == 12
    assert "Tag Ignorada" not in argumentos_passados_pra_ia

    assert 0 in resultado
    assert resultado[0]["nome_sugerido"] == "Teste - Banco - Real"


def test_integration_suggest_categories_happy_path_docs(db_session, mock_registry, generate_archive_doc):
    """
    Testa a integração real entre o Service, o Repository e o PostgreSQL via Documentos.
    Verifica se a concatenação de Título e Descrição funciona na prática.
    """

    for i in range(12):
        doc = generate_archive_doc(
            description_id=f"doc_{i}",
            original_title=f"Título {i}",
            scope_content="Descrição válida com texto.",
            staging_content_hash=f"hash_{i}",
        )

    MockClass = mock_registry(clustering_registry)
    instancia_da_ia = MockClass.return_value
    mock_df = pd.DataFrame([{"Topic": 0, "Count": 12, "Representation": ["teste", "docs", "integra"]}])
    instancia_da_ia.discover_topics.return_value = ([0] * 12, mock_df)

    service = TagService(db=db_session)
    resultado = service.suggest_macro_categories(
        source_type="documents", columns_to_extract=["original_title", "scope_content"]
    )

    argumentos_passados_pra_ia = instancia_da_ia.discover_topics.call_args[0][0]

    texto_esperado = "Título 0. Descrição válida com texto."
    assert texto_esperado in argumentos_passados_pra_ia[0]

    assert len(resultado) == 1
    assert resultado[0]["nome_sugerido"] == "Teste - Docs - Integra"


def test_integration_suggest_categories_sad_path_insufficient_tags(db_session, mock_registry):
    """
    Caminho Triste: Existem tags no banco real, mas são menos que 10.
    """

    for i in range(5):
        db_session.add(ArchiveTag(name=f"Tag {i}", macro_category_id=None))
    db_session.commit()

    MockClass = mock_registry(clustering_registry)
    instancia_da_ia = MockClass.return_value

    service = TagService(db=db_session)
    resultado = service.suggest_macro_categories(source_type="tags")

    instancia_da_ia.discover_topics.assert_not_called()
    assert resultado == {}


def test_integration_suggest_categories_sad_path_already_categorized(db_session, mock_registry):
    """
    Caminho Triste: Existem 20 tags, mas todas elas já têm Macro Categoria atribuída.
    """

    # 1. Criamos a Macro Categoria real
    macro = ArchiveMacroCategory(name="Categoria Existente", description="Teste")
    db_session.add(macro)
    db_session.flush()

    # 2. Vinculamos as 20 tags a essa categoria
    for i in range(20):
        db_session.add(ArchiveTag(name=f"Tag {i}", macro_category_id=macro.category_id))
    db_session.commit()

    MockClass = mock_registry(clustering_registry)
    instancia_da_ia = MockClass.return_value

    service = TagService(db=db_session)
    resultado = service.suggest_macro_categories(source_type="tags")

    instancia_da_ia.discover_topics.assert_not_called()
    assert resultado == {}
