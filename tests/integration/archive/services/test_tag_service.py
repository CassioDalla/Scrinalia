from sqlalchemy import select, text

from domains.archive import repository
from domains.archive.models import ArchiveDocumentTag, ArchiveMacroCategory, ArchiveTag, DomainSynonyms
from domains.archive.schemas.tag_schema import TagRelevanceCount
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

    resExpected = [TagRelevanceCount(name="comum", total_usage=2), TagRelevanceCount(name="rara", total_usage=1)]

    assert list(resultados) == resExpected

    # assert resultados[0] == {"name": "comum", "total_usage": 2}
    # assert resultados[1] == {"name": "rara", "total_usage": 1}


def test_get_tag_relevance_tfidf(use_test_db, db_session, generate_archive_doc):
    """
    Testa o motor matemático de TF-IDF.
    Tags que aparecem em TODOS os documentos devem ter o IDF zerado.
    """
    service = TagService(db_session)

    tag_oni = ArchiveTag(name="onipresente")
    tag_esp = ArchiveTag(name="especifica")
    docs = [generate_archive_doc(description_id=f"doc_{i}") for i in range(4)]

    # Salva tags e docs de uma vez
    db_session.add_all([tag_oni, tag_esp, *docs])
    db_session.commit()

    # Cria todos os vínculos de uma vez com list comprehension
    vinculos = [ArchiveDocumentTag(description_id=d.description_id, tag_id=tag_oni.tag_id) for d in docs]
    vinculos.append(ArchiveDocumentTag(description_id=docs[0].description_id, tag_id=tag_esp.tag_id))
    db_session.add_all(vinculos)
    db_session.commit()

    # 2. EXECUÇÃO
    resultados = service.get_tag_relevance_tfidf()

    # 3. VERIFICAÇÃO (ASSERTS) MAIS EXPRESSIVA:
    assert len(resultados) == 2, "Deveria ter avaliado exatamente 2 tags"

    # Desempacota os objetos do Pydantic (assumindo que a service já ordena DESC)
    primeiro_lugar, segundo_lugar = resultados[0], resultados[1]

    # Verifica o topo do ranking
    assert primeiro_lugar.name == "especifica"
    assert primeiro_lugar.score_tfidf > 0.0

    # Verifica a base do ranking (penalização do IDF)
    assert segundo_lugar.name == "onipresente"
    assert segundo_lugar.score_tfidf == 0.0


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

    tag = similares[0]
    assert len(similares) == 1
    assert tag.name == "prefeituta"
    assert tag.similarity > 0.4


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

    res = service.merge_tags(tag_oficial.tag_id, [tag_erro.tag_id])

    assert res.documents_updated == 1
    assert res.tags_deleted == 1

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

    res = service.merge_tags(tag_oficial.tag_id, [tag_erro.tag_id])

    assert res.tags_deleted == 1
    qtd_vinculos = db_session.query(ArchiveDocumentTag).count()
    assert qtd_vinculos == 1  # Apenas o oficial restou


# ==========================================
# TESTES DE INTEGRAÇÃO (SERVICE + POSTGRESQL REAL)
# ==========================================


def test_integration_get_texts_happy_path_tags(db_session):
    """
    Testa a integração real via Tags.
    Garante que puxa apenas tags órfãs (sem categoria) para análise.
    """
    # 1. Criamos a Macro Categoria primeiro para respeitar a Foreign Key
    macro = ArchiveMacroCategory(name="Categoria Ignorada", description="Teste")
    db_session.add(macro)
    db_session.flush()

    # 2. Inserimos 12 tags orfãs reais
    tags_orfas = [ArchiveTag(name=f"Tag Real {i}", macro_category_id=None) for i in range(12)]
    db_session.add_all(tags_orfas)

    # 3. Inserimos 1 tag que já tem categoria (NÃO deve ser puxada)
    db_session.add(ArchiveTag(name="Tag Ignorada", macro_category_id=macro.category_id))
    db_session.commit()

    # 4. Execução da Service (sem envolver IA)
    service = TagService(db=db_session)
    textos = service.get_text_to_suggest_macro_category(source_type="tags")

    # 5. Asserts
    assert len(textos) == 12, "Deveria ter puxado apenas as 12 tags órfãs."
    assert "Tag Real 0" in textos
    assert "Tag Ignorada" not in textos


def test_integration_get_texts_happy_path_docs(db_session, generate_archive_doc):
    """
    Testa a integração real via Documentos.
    Verifica se o repositório concatena as colunas corretamente no banco.
    """
    # Criamos os documentos reais no banco
    _ = [
        generate_archive_doc(
            description_id=f"doc_{i}",
            original_title=f"Título {i}",
            scope_content="Descrição válida com texto",
            staging_content_hash=f"hash_{i}",
        )
        for i in range(12)
    ]

    service = TagService(db=db_session)
    textos = service.get_text_to_suggest_macro_category(
        source_type="documents", columns_to_extract=["original_title", "scope_content"]
    )

    assert len(textos) == 12
    # Valida exatamente o formato da string que vai ser enviada para a IA depois
    assert textos[0] == "Título 0. Descrição válida com texto."


def test_integration_get_texts_sad_path_insufficient_tags(db_session):
    """
    Caminho Triste: Existem tags, mas são menos que 10.
    A Service devolve a lista curta (O Controller é quem deve bloquear).
    """
    tags = [ArchiveTag(name=f"Tag {i}", macro_category_id=None) for i in range(5)]
    db_session.add_all(tags)
    db_session.commit()

    service = TagService(db=db_session)
    textos = service.get_text_to_suggest_macro_category(source_type="tags")

    assert len(textos) == 5
    # A responsabilidade do retorno de "Textos insuficientes" ficou no Controller.
    # Aqui atestamos que a Service fez a parte dela.


def test_integration_get_texts_sad_path_already_categorized(db_session):
    """
    Caminho Triste: Existem muitas tags, mas todas já têm Macro Categoria.
    O banco não deve retornar nada.
    """
    macro = ArchiveMacroCategory(name="Categoria Existente", description="Teste")
    db_session.add(macro)
    db_session.flush()

    # Vinculamos todas as 20 tags à categoria
    tags = [ArchiveTag(name=f"Tag {i}", macro_category_id=macro.category_id) for i in range(20)]
    db_session.add_all(tags)
    db_session.commit()

    service = TagService(db=db_session)
    textos = service.get_text_to_suggest_macro_category(source_type="tags")

    assert len(textos) == 0, "Nenhuma tag deveria ter sido retornada, pois todas já estão categorizadas."
    assert textos == []
