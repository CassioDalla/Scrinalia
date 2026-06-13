from sqlalchemy import select, text

from core.models.gold_layer import DomainSynonymsModel, GoldDescriptionModel, GoldDescriptionTagModel, GoldTagModel
from scripts.gold.tag_service import TagManager

# ==========================================
# 1. TESTES DE PURGE (STOPWORDS)
# ==========================================


def test_purge_stopwords_success(use_test_db, db_session):
    """Garante que as stopwords são apagadas e ignoram case/espaços."""
    manager = TagManager(db_session)

    db_session.add_all([GoldTagModel(name="ofício"), GoldTagModel(name="valiosa"), GoldTagModel(name="curitiba")])
    db_session.commit()

    # O método deve limpar os espaços e ignorar maiúsculas/minúsculas
    apagadas = manager.purge_stopwords([" OFÍCIO ", "Curitiba"])

    assert apagadas == 2
    restantes = db_session.scalars(select(GoldTagModel.name)).all()
    assert restantes == ["valiosa"]


def test_purge_stopwords_cascade(use_test_db, db_session):
    """Garante que apagar uma tag também destrói os vínculos N:N (Comportamento ORM Cascade)."""
    manager = TagManager(db_session)

    tag_lixo = GoldTagModel(name="lixo")
    doc = GoldDescriptionModel(description_id="doc_1", original_title="T", silver_content_hash="H")
    db_session.add_all([tag_lixo, doc])
    db_session.commit()

    db_session.add(GoldDescriptionTagModel(description_id="doc_1", tag_id=tag_lixo.tag_id))
    db_session.commit()

    manager.purge_stopwords(["lixo"])

    # A tabela de vínculos também deve estar vazia agora
    vinculos = db_session.scalars(select(GoldDescriptionTagModel)).all()
    assert len(vinculos) == 0


def test_purge_stopwords_empty_list(use_test_db, db_session):
    """Garante que a função retorna 0 se não encontrar nada, sem dar erro de SQL."""
    manager = TagManager(db_session)
    apagadas = manager.purge_stopwords(["inexistente"])
    assert apagadas == 0


# ==========================================
# 2. TESTES DE CONTAGEM E ESTATÍSTICA (RELEVANCE)
# ==========================================


def test_get_tag_relevance_count(use_test_db, db_session):
    """Garante que a contagem agrupa e ordena da mais usada para a menos usada."""
    manager = TagManager(db_session)

    tag_comum = GoldTagModel(name="comum")
    tag_rara = GoldTagModel(name="rara")
    doc1 = GoldDescriptionModel(description_id="doc_1", original_title="T1", silver_content_hash="H1")
    doc2 = GoldDescriptionModel(description_id="doc_2", original_title="T2", silver_content_hash="H2")

    db_session.add_all([tag_comum, tag_rara, doc1, doc2])
    db_session.commit()

    # Tag comum vai em 2 docs. Tag rara em 1 doc.
    db_session.add_all(
        [
            GoldDescriptionTagModel(description_id="doc_1", tag_id=tag_comum.tag_id),
            GoldDescriptionTagModel(description_id="doc_2", tag_id=tag_comum.tag_id),
            GoldDescriptionTagModel(description_id="doc_1", tag_id=tag_rara.tag_id),
        ]
    )
    db_session.commit()

    resultados = manager.get_tag_relevance_count(limit=5)

    assert len(resultados) == 2
    # A tupla devolve (nome_da_tag, total_usos)
    assert resultados[0] == ("comum", 2)
    assert resultados[1] == ("rara", 1)


def test_get_tag_relevance_tfidf(use_test_db, db_session):
    """
    Testa o motor matemático de TF-IDF.
    Tags que aparecem em TODOS os documentos devem ter o IDF zerado.
    Tags raras devem ter um score mais alto.
    """
    manager = TagManager(db_session)

    tag_onipresente = GoldTagModel(name="onipresente")
    tag_especifica = GoldTagModel(name="especifica")

    # Criamos 4 documentos no total
    docs = [
        GoldDescriptionModel(description_id=f"doc_{i}", original_title="T", silver_content_hash="H") for i in range(4)
    ]
    db_session.add_all([tag_onipresente, tag_especifica] + docs)
    db_session.commit()

    # A Onipresente está nos 4 documentos
    for d in docs:
        db_session.add(GoldDescriptionTagModel(description_id=d.description_id, tag_id=tag_onipresente.tag_id))

    # A Específica está em apenas 1 documento
    db_session.add(GoldDescriptionTagModel(description_id="doc_0", tag_id=tag_especifica.tag_id))
    db_session.commit()

    resultados = manager.get_tag_relevance_tfidf()

    # O resultado traz: (name, frequencia, peso_idf, score_tfidf)
    nome_primeiro_lugar = resultados[0][0]
    score_primeiro_lugar = resultados[0][3]

    nome_segundo_lugar = resultados[1][0]
    score_segundo_lugar = resultados[1][3]

    # A Específica tem de vencer a Onipresente porque o seu IDF é alto
    assert nome_primeiro_lugar == "especifica"
    assert score_primeiro_lugar > 0

    assert nome_segundo_lugar == "onipresente"
    assert score_segundo_lugar == 0.0  # ln(4/4) = ln(1) = 0


def test_get_tag_relevance_tfidf_empty_db(use_test_db, db_session):
    """Garante que a fórmula matemática não tenta fazer divisão por zero se o acervo estiver vazio."""
    manager = TagManager(db_session)
    assert manager.get_tag_relevance_tfidf() == []


# ==========================================
# 3. TESTES DE ALGORITMO APROXIMADO (PG_TRGM)
# ==========================================


def test_find_similar_tags(use_test_db, db_session):
    """Garante que a busca trigramática acha erros de digitação e obedece ao threshold."""
    # PREPARAÇÃO CRÍTICA: Instala a extensão no banco de testes do Docker
    db_session.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm;"))
    db_session.commit()

    manager = TagManager(db_session)

    # Inserimos a oficial, um erro clássico, e uma palavra totalmente nada a ver
    db_session.add_all([GoldTagModel(name="prefeitura"), GoldTagModel(name="prefeituta"), GoldTagModel(name="abacate")])
    db_session.commit()

    # Busca termos parecidos com "prefeitura" (limite 0.3 para garantir captura)
    similares = manager.find_similar_tags("prefeitura", threshold=0.3)

    assert len(similares) == 1
    # O formato da tupla é (id, name, score)
    assert similares[0][1] == "prefeituta"
    assert similares[0][2] > 0.4  # O score de 'prefeituta' costuma ser perto de 0.8


# ==========================================
# 4. TESTES DE MESCLAGEM (MERGE)
# ==========================================


def test_merge_tags_success(use_test_db, db_session):
    """Testa o fluxo feliz: move docs, cria sinônimos e apaga a tag antiga."""
    manager = TagManager(db_session)

    tag_oficial = GoldTagModel(name="foto")
    tag_erro = GoldTagModel(name="fotu")
    doc = GoldDescriptionModel(description_id="doc_1", original_title="T", silver_content_hash="H")

    db_session.add_all([tag_oficial, tag_erro, doc])
    db_session.commit()

    db_session.add(GoldDescriptionTagModel(description_id="doc_1", tag_id=tag_erro.tag_id))
    db_session.commit()

    docs_afetados, tags_apagadas = manager.merge_tags(tag_oficial.tag_id, [tag_erro.tag_id])

    assert docs_afetados == 1
    assert tags_apagadas == 1

    # Confirma o sinônimo criado com o CheckConstraint correto (category='TAG')
    sinonimo = db_session.scalars(select(DomainSynonymsModel)).first()
    assert sinonimo.synonym_name == "fotu"
    assert sinonimo.canonical_tag_id == tag_oficial.tag_id
    assert sinonimo.category == "TAG"


def test_merge_tags_idempotency_conflict(use_test_db, db_session):
    """Testa a blindagem UniqueConstraint. Se o doc já tiver as duas tags, não deve explodir erro."""
    manager = TagManager(db_session)

    tag_oficial = GoldTagModel(name="foto")
    tag_erro = GoldTagModel(name="fotu")
    doc = GoldDescriptionModel(description_id="doc_1", original_title="T", silver_content_hash="H")

    db_session.add_all([tag_oficial, tag_erro, doc])
    db_session.commit()

    # O documento já possui a tag certa E a errada
    db_session.add_all(
        [
            GoldDescriptionTagModel(description_id="doc_1", tag_id=tag_oficial.tag_id),
            GoldDescriptionTagModel(description_id="doc_1", tag_id=tag_erro.tag_id),
        ]
    )
    db_session.commit()

    _docs_afetados, tags_apagadas = manager.merge_tags(tag_oficial.tag_id, [tag_erro.tag_id])

    # Sobreviveu ao ON CONFLICT DO NOTHING!
    assert tags_apagadas == 1
    qtd_vinculos = db_session.query(GoldDescriptionTagModel).count()
    assert qtd_vinculos == 1  # Apenas o oficial restou


def test_merge_tags_empty_lists(use_test_db, db_session):
    """Garante que passar listas vazias não causa erros de SQL (IN clause empty)."""
    manager = TagManager(db_session)
    docs, tags = manager.merge_tags(99, [])
    assert docs == 0
    assert tags == 0
