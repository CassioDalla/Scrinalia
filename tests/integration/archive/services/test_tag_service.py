from sqlalchemy import select, text

from domains.archive.models import ArchiveDocumentTag, ArchiveMacroCategory, ArchiveTag, DomainSynonyms
from domains.archive.repository.document_repo import DocumentRepository
from domains.archive.repository.tag_repo import TagRepository
from domains.archive.schemas.tag_schema import TagRelevanceCount
from domains.archive.services.tag_service import TagService

# ==========================================
# 1. TESTES DE PURGE (STOPWORDS)
# ==========================================


def test_purge_stopwords_success(use_test_db, db_session):
    """Garante que as stopwords são lidas do banco e apagadas."""
    tag_repo = TagRepository(db_session)
    doc_repo = DocumentRepository(db_session)
    service = TagService(tag_repo, doc_repo)

    # 1. Prepara o banco com tags
    db_session.add_all([ArchiveTag(name="ofício"), ArchiveTag(name="valiosa"), ArchiveTag(name="curitiba")])

    # 2. Insere as stopwords no dicionário (simulando o frontend)
    tag_repo.save_stopwords([" OFÍCIO ", "Curitiba"])
    db_session.commit()

    # 3. O método deve ler do banco e apagar
    apagadas = service.purge_stopwords()

    # 4. Como o Service não faz mais commit, precisamos comitar a transação de teste
    db_session.commit()

    assert apagadas == 2
    restantes = db_session.scalars(select(ArchiveTag.name)).all()
    assert restantes == ["valiosa"]


def test_purge_stopwords_cascade(use_test_db, db_session, generate_archive_doc):
    """Garante que apagar uma tag também destrói os vínculos N:N (Cascade)."""
    tag_repo = TagRepository(db_session)
    doc_repo = DocumentRepository(db_session)
    service = TagService(tag_repo, doc_repo)

    tag_lixo = ArchiveTag(name="lixo")
    doc = generate_archive_doc(description_id="doc_1", original_title="Título Teste")
    db_session.add(tag_lixo)
    db_session.commit()

    db_session.add(ArchiveDocumentTag(description_id=doc.description_id, tag_id=tag_lixo.tag_id))
    tag_repo.save_stopwords(["lixo"])
    db_session.commit()

    service.purge_stopwords()
    db_session.commit()  # Persiste a deleção

    # A tabela de vínculos também deve estar vazia agora
    vinculos = db_session.scalars(select(ArchiveDocumentTag)).all()
    assert len(vinculos) == 0


def test_purge_stopwords_empty_db(use_test_db, db_session):
    """Garante que a função retorna 0 se não encontrar nada."""
    tag_repo = TagRepository(db_session)
    doc_repo = DocumentRepository(db_session)
    service = TagService(tag_repo, doc_repo)

    apagadas = service.purge_stopwords()

    assert apagadas == 0


# ==========================================
# 2. TESTES DE CONTAGEM E ESTATÍSTICA (RELEVANCE)
# ==========================================


def test_get_tag_relevance_count(use_test_db, db_session, generate_archive_doc):
    """Garante que a contagem agrupa e ordena da mais usada para a menos usada."""
    tag_repo = TagRepository(db_session)
    doc_repo = DocumentRepository(db_session)
    service = TagService(tag_repo, doc_repo)

    tag_comum = ArchiveTag(name="comum")
    tag_rara = ArchiveTag(name="rara")
    doc1 = generate_archive_doc(description_id="doc_1", original_title="Doc 1")
    doc2 = generate_archive_doc(description_id="doc_2", original_title="Doc 2")

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


def test_get_tag_relevance_tfidf(use_test_db, db_session, generate_archive_doc):
    """
    Testa o motor matemático de TF-IDF.
    Tags que aparecem em TODOS os documentos devem ter o IDF zerado.
    """
    tag_repo = TagRepository(db_session)
    doc_repo = DocumentRepository(db_session)
    service = TagService(tag_repo, doc_repo)

    tag_oni = ArchiveTag(name="onipresente")
    tag_esp = ArchiveTag(name="especifica")
    docs = [generate_archive_doc(description_id=f"doc_{i}", original_title=f"Doc {i}") for i in range(4)]

    db_session.add_all([tag_oni, tag_esp, *docs])
    db_session.commit()

    vinculos = [ArchiveDocumentTag(description_id=d.description_id, tag_id=tag_oni.tag_id) for d in docs]
    vinculos.append(ArchiveDocumentTag(description_id=docs[0].description_id, tag_id=tag_esp.tag_id))
    db_session.add_all(vinculos)
    db_session.commit()

    resultados = service.get_tag_relevance_tfidf()

    assert len(resultados) == 2, "Deveria ter avaliado exatamente 2 tags"
    primeiro_lugar, segundo_lugar = resultados[0], resultados[1]

    assert primeiro_lugar.name == "especifica"
    assert primeiro_lugar.score_tfidf > 0.0

    assert segundo_lugar.name == "onipresente"
    assert segundo_lugar.score_tfidf == 0.0


def test_get_tag_relevance_tfidf_empty_db(use_test_db, db_session):
    tag_repo = TagRepository(db_session)
    doc_repo = DocumentRepository(db_session)
    service = TagService(tag_repo, doc_repo)

    assert service.get_tag_relevance_tfidf() == []


# ==========================================
# 3. TESTES DE ALGORITMO APROXIMADO (PG_TRGM)
# ==========================================


def test_find_similar_tags(use_test_db, db_session):
    """Garante que a busca trigramática acha erros de digitação e obedece ao threshold."""
    db_session.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm;"))
    db_session.commit()

    tag_repo = TagRepository(db_session)
    doc_repo = DocumentRepository(db_session)
    service = TagService(tag_repo, doc_repo)

    db_session.add_all([ArchiveTag(name="prefeitura"), ArchiveTag(name="prefeituta"), ArchiveTag(name="abacate")])
    db_session.commit()

    similares = service.find_similar_tags("prefeitura", threshold=0.3)

    assert len(similares) == 1
    tag = similares[0]
    assert tag.name == "prefeituta"
    assert tag.similarity > 0.4


# ==========================================
# 4. TESTES DE MESCLAGEM (MERGE)
# ==========================================


def test_merge_tags_success(use_test_db, db_session, generate_archive_doc):
    """Testa o fluxo feliz: move docs, cria sinônimos e apaga a tag antiga."""
    tag_repo = TagRepository(db_session)
    doc_repo = DocumentRepository(db_session)
    service = TagService(tag_repo, doc_repo)

    tag_oficial = ArchiveTag(name="foto")
    tag_erro = ArchiveTag(name="fotu")
    doc = generate_archive_doc(description_id="doc_1", original_title="Doc Teste")

    db_session.add_all([tag_oficial, tag_erro])
    db_session.commit()

    db_session.add(ArchiveDocumentTag(description_id=doc.description_id, tag_id=tag_erro.tag_id))
    db_session.commit()

    res = service.merge(tag_oficial.tag_id, [tag_erro.tag_id])
    db_session.commit()  # Commit no teste

    assert res.documents_updated == 1
    assert res.tags_deleted == 1

    sinonimo = db_session.scalars(select(DomainSynonyms)).first()
    assert sinonimo.synonym_name == "fotu"
    assert sinonimo.canonical_tag_id == tag_oficial.tag_id
    assert sinonimo.category == "TAG"


def test_merge_tags_idempotency_conflict(use_test_db, db_session, generate_archive_doc):
    """Testa a blindagem UniqueConstraint. Se o doc já tiver as duas tags, não deve explodir."""
    tag_repo = TagRepository(db_session)
    doc_repo = DocumentRepository(db_session)
    service = TagService(tag_repo, doc_repo)

    tag_oficial = ArchiveTag(name="foto")
    tag_erro = ArchiveTag(name="fotu")
    doc = generate_archive_doc(description_id="doc_1", original_title="Doc Teste")

    db_session.add_all([tag_oficial, tag_erro])
    db_session.commit()

    db_session.add_all(
        [
            ArchiveDocumentTag(description_id=doc.description_id, tag_id=tag_oficial.tag_id),
            ArchiveDocumentTag(description_id=doc.description_id, tag_id=tag_erro.tag_id),
        ]
    )
    db_session.commit()

    res = service.merge(tag_oficial.tag_id, [tag_erro.tag_id])
    db_session.commit()  # Commit no teste

    assert res.tags_deleted == 1
    qtd_vinculos = db_session.query(ArchiveDocumentTag).count()
    assert qtd_vinculos == 1  # Apenas o oficial restou


# ==========================================
# TESTES: get_text_to_suggest_macro_category
# ==========================================


def test_integration_get_texts_happy_path_tags(use_test_db, db_session):
    """
    Testa a integração real via Tags.
    Garante que puxa apenas tags órfãs (sem categoria) para análise.
    """
    macro = ArchiveMacroCategory(name="Categoria Ignorada", description="Teste")
    db_session.add(macro)
    db_session.flush()

    tags_orfas = [ArchiveTag(name=f"Tag Real {i}", macro_category_id=None) for i in range(12)]
    db_session.add_all(tags_orfas)

    db_session.add(ArchiveTag(name="Tag Ignorada", macro_category_id=macro.category_id))
    db_session.commit()

    tag_repo = TagRepository(db_session)
    doc_repo = DocumentRepository(db_session)
    service = TagService(tag_repo, doc_repo)

    textos = service.get_text_to_suggest_macro_category(source_type="tags")

    assert len(textos) == 12, "Deveria ter puxado apenas as 12 tags órfãs."
    assert "Tag Real 0" in textos
    assert "Tag Ignorada" not in textos


def test_integration_get_texts_happy_path_docs(use_test_db, db_session, generate_archive_doc):
    """
    Testa a integração real via Documentos.
    Verifica se o repositório concatena as colunas corretamente no banco.
    """
    _ = [
        generate_archive_doc(
            description_id=f"doc_{i}",
            original_title=f"Título {i}",
            scope_content="Descrição válida com texto",
            staging_content_hash=f"hash_{i}",
        )
        for i in range(12)
    ]
    # O generate_archive_doc normalmente já comita ou acopla à sessão. Se precisar:
    db_session.commit()

    tag_repo = TagRepository(db_session)
    doc_repo = DocumentRepository(db_session)
    service = TagService(tag_repo, doc_repo)

    textos = service.get_text_to_suggest_macro_category(
        source_type="documents", columns_to_extract=["original_title", "scope_content"]
    )

    assert len(textos) == 12
    assert textos[0] == "Título 0. Descrição válida com texto."


def test_integration_get_texts_sad_path_insufficient_tags(use_test_db, db_session):
    """
    Caminho Triste: Existem tags, mas são menos que 10.
    A Service devolve a lista curta (O Controller é quem deve bloquear).
    """
    tags = [ArchiveTag(name=f"Tag {i}", macro_category_id=None) for i in range(5)]
    db_session.add_all(tags)
    db_session.commit()

    tag_repo = TagRepository(db_session)
    doc_repo = DocumentRepository(db_session)
    service = TagService(tag_repo, doc_repo)

    textos = service.get_text_to_suggest_macro_category(source_type="tags")

    assert len(textos) == 5


def test_integration_get_texts_sad_path_already_categorized(use_test_db, db_session):
    """
    Caminho Triste: Existem muitas tags, mas todas já têm Macro Categoria.
    O banco não deve retornar nada.
    """
    macro = ArchiveMacroCategory(name="Categoria Existente", description="Teste")
    db_session.add(macro)
    db_session.flush()

    tags = [ArchiveTag(name=f"Tag {i}", macro_category_id=macro.category_id) for i in range(20)]
    db_session.add_all(tags)
    db_session.commit()

    tag_repo = TagRepository(db_session)
    doc_repo = DocumentRepository(db_session)
    service = TagService(tag_repo, doc_repo)

    textos = service.get_text_to_suggest_macro_category(source_type="tags")

    assert len(textos) == 0, "Nenhuma tag deveria ter sido retornada, pois todas já estão categorizadas."
    assert textos == []
