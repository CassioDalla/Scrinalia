import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from domains.archive.models import (
    ArchiveDocument,
    ArchiveDocumentEntity,
    ArchiveDocumentTag,
    ArchiveEntity,
    ArchiveMacroCategory,
    ArchiveReviewStatus,
    ArchiveTag,
    DomainSynonyms,
)
from domains.archive.repository import (
    get_ner_synonyms_rules,
    get_or_create_entities,
    get_or_create_tags,
    get_stopwords,
    link_description_relationships,
    save_stopwords,
    stamp_ai_execution,
    upsert_archive_document,
)
from domains.archive.schemas.schemas import ArchiveEntityDTO, ArchiveTagDTO


# TODO MUDAR OS TESTES PARA TESTAR INDIVIDUALMENTE CADA REPO


# ==========================================
# 1. TESTES DE UPSERT (CARGA DA ETL E RESET DE IA)
# ==========================================


def test_upsert_archive_document_insert_new(use_test_db, db_session, generate_archive_dto):
    """Cenário 1: Inserção de documento inédito vindo da Staging."""
    dto_novo = generate_archive_dto(description_id="1", original_title="Inédito", staging_content_hash="hash_1")

    inseriu = upsert_archive_document(db_session, dto_novo)
    db_session.commit()

    assert inseriu is True
    doc_banco = db_session.execute(select(ArchiveDocument).filter_by(description_id="1")).scalar_one()
    assert doc_banco.original_title == "Inédito"


def test_upsert_archive_document_ignore_same_hash(use_test_db, db_session, generate_archive_dto):
    """Cenário 2: Carga Incremental. Documento com mesmo Hash deve ser ignorado."""
    dto_original = generate_archive_dto(description_id="2", original_title="Original", staging_content_hash="hash_2")
    upsert_archive_document(db_session, dto_original)
    db_session.commit()

    dto_repetido = generate_archive_dto(description_id="2", original_title="Falso", staging_content_hash="hash_2")
    inseriu_repetido = upsert_archive_document(db_session, dto_repetido)
    db_session.commit()

    assert inseriu_repetido is False
    doc_banco = db_session.execute(select(ArchiveDocument).filter_by(description_id="2")).scalar_one()
    assert doc_banco.original_title == "Original"


def test_upsert_archive_document_update_resets_ai(use_test_db, db_session, generate_archive_dto):
    """Cenário 3: CDC (Change Data Capture). Se o Hash mudou na Staging, atualiza os dados E apaga rastros de IA."""
    dto_original = generate_archive_dto(
        description_id="3",
        original_title="Antigo",
        staging_content_hash="hash_3",
        execution_log={"ner_spacy_v1": "DONE"},  # Log sujo da IA
        review_status=ArchiveReviewStatus.NEEDS_REVIEW,
    )
    upsert_archive_document(db_session, dto_original)
    db_session.commit()

    # Nova carga com Hash atualizado da Staging envia o DTO limpo (Default)
    dto_novo = generate_archive_dto(
        description_id="3", original_title="Novo Título", staging_content_hash="hash_3_NOVO"
    )
    inseriu_novo = upsert_archive_document(db_session, dto_novo)
    db_session.commit()

    assert inseriu_novo is True
    doc_banco = db_session.execute(select(ArchiveDocument).filter_by(description_id="3")).scalar_one()
    assert doc_banco.original_title == "Novo Título"
    assert doc_banco.execution_log == {}  # O log foi resetado!
    assert doc_banco.review_status == ArchiveReviewStatus.PENDING_AI


def test_upsert_archive_document_blocked_by_human_approved(use_test_db, db_session, generate_archive_dto):
    """Cenário 4: Governança. Documento com status HUMAN_APPROVED bloqueia sobrescrita da ETL."""
    dto_original = generate_archive_dto(
        description_id="4",
        original_title="Revisado Perfeito",
        staging_content_hash="hash_4",
        review_status=ArchiveReviewStatus.HUMAN_APPROVED,
    )
    upsert_archive_document(db_session, dto_original)
    db_session.commit()

    dto_ataque = generate_archive_dto(
        description_id="4", original_title="Lixo da Staging", staging_content_hash="hash_4_NOVO"
    )
    inseriu_ataque = upsert_archive_document(db_session, dto_ataque)
    db_session.commit()

    assert inseriu_ataque is False
    doc_banco = db_session.execute(select(ArchiveDocument).filter_by(description_id="4")).scalar_one()
    assert doc_banco.original_title == "Revisado Perfeito"


# ==========================================
# 2. TESTES DE ENTIDADES E TAGS (DIMENSÕES)
# ==========================================


def test_get_or_create_entities_new_and_existing(use_test_db, db_session):
    """Garante a criação e a idempotência de Entidades (NER)."""
    entidades_dto = [ArchiveEntityDTO(name="David Carneiro", entity_type="PER")]

    ids_passo_1 = get_or_create_entities(db_session, entidades_dto)
    db_session.commit()

    ids_passo_2 = get_or_create_entities(db_session, entidades_dto)
    db_session.commit()

    assert len(ids_passo_1) == 1
    assert ids_passo_1[0] == ids_passo_2[0]


def test_get_or_create_tags_new_and_lowercased(use_test_db, db_session):
    """Garante a criação de tags inéditas convertendo sempre para minúsculo."""
    tags_dto = [ArchiveTagDTO(name=" ARQUIVAMENTO ", macro_category_id=None)]
    ids_gerados = get_or_create_tags(db_session, tags_dto)
    db_session.commit()

    assert len(ids_gerados) == 1
    tag_db = db_session.execute(select(ArchiveTag).filter_by(tag_id=ids_gerados[0])).scalar_one()
    assert tag_db.name == "arquivamento"


def test_create_tag_com_macro_category_valida(use_test_db, db_session):
    """Garante que uma tag é criada e vinculada corretamente a uma categoria macro existente."""
    # 1. Setup: Criamos a Categoria Macro primeiro
    macro = ArchiveMacroCategory(name="Administrativo", description="Documentos de RH e Gestão")
    db_session.add(macro)
    db_session.commit()

    # 2. Ação: Passamos o ID gerado para a DTO
    tags_dto = [ArchiveTagDTO(name="ofício", macro_category_id=macro.category_id)]
    ids_gerados = get_or_create_tags(db_session, tags_dto)
    db_session.commit()

    # 3. Verificações
    tag_db = db_session.get(ArchiveTag, ids_gerados[0])
    assert tag_db.name == "ofício"
    assert tag_db.macro_category_id == macro.category_id

    # Testa o relationship do SQLAlchemy
    assert tag_db.macro_category.name == "Administrativo"


def test_falha_ao_criar_tag_com_macro_category_inexistente(use_test_db, db_session):
    """Garante que o banco de dados bloqueia a criação de tag com um ID de categoria fantasma."""
    # ID 9999 não existe na tabela archive_macro_categories
    tags_dto = [ArchiveTagDTO(name="financeiro", macro_category_id=9999)]

    # O SQLAlchemy deve levantar um IntegrityError por violação de Foreign Key
    with pytest.raises(IntegrityError):
        get_or_create_tags(db_session, tags_dto)
        db_session.commit()


def test_recupera_tag_existente_mantendo_macro_category(use_test_db, db_session):
    """Se a tag já existe, deve apenas retornar o ID mantendo a categoria intacta."""
    macro = ArchiveMacroCategory(name="Financeiro")
    db_session.add(macro)
    db_session.commit()

    # Simulamos uma execução anterior que criou a tag
    get_or_create_tags(db_session, [ArchiveTagDTO(name="recibo", macro_category_id=macro.category_id)])
    db_session.commit()

    # Ação: Rodamos a função de novo com a mesma tag
    ids_gerados = get_or_create_tags(db_session, [ArchiveTagDTO(name="RECIBO", macro_category_id=macro.category_id)])

    assert len(ids_gerados) == 1
    tag_db = db_session.get(ArchiveTag, ids_gerados[0])

    # Garante que a relação não se perdeu no "Get"
    assert tag_db.macro_category_id == macro.category_id


def test_exclusao_de_macro_category_seta_fk_como_nulo(use_test_db, db_session):
    """Garante o comportamento 'SET NULL' quando a categoria pai é deletada."""
    # 1. Setup
    macro = ArchiveMacroCategory(name="Projetos Especiais")
    db_session.add(macro)
    db_session.commit()

    tag = ArchiveTag(name="planta_baixa", macro_category_id=macro.category_id)
    db_session.add(tag)
    db_session.commit()

    # 2. Ação: Deletamos a categoria macro (o pai)
    db_session.delete(macro)
    db_session.commit()

    # 3. Verificação: Atualizamos a tag na memória e verificamos
    db_session.refresh(tag)
    assert tag.macro_category_id is None
    assert tag.name == "planta_baixa"  # A tag deve continuar existindo!


# ==========================================
# 3. TESTES DE RELACIONAMENTOS (N:N)
# ==========================================


def test_link_description_relationships_bulk(use_test_db, db_session, generate_archive_dto):
    """Testa a inserção em lote (Bulk Insert) otimizada nas tabelas associativas."""
    upsert_archive_document(db_session, generate_archive_dto(description_id="25"))
    ent_id = get_or_create_entities(db_session, [ArchiveEntityDTO(name="Ent", entity_type="ORG")])[0]
    tag_id = get_or_create_tags(db_session, [ArchiveTagDTO(name="Tag")])[0]
    db_session.commit()

    link_description_relationships(db_session, "25", [ent_id], [tag_id])
    # Testa a idempotência (ON CONFLICT DO NOTHING) no Bulk Insert
    link_description_relationships(db_session, "25", [ent_id], [tag_id])
    db_session.commit()

    qtd_ent = db_session.query(ArchiveDocumentEntity).count()
    qtd_tag = db_session.query(ArchiveDocumentTag).count()
    assert qtd_ent == 1
    assert qtd_tag == 1


# ==========================================
# 4. TESTES DE IA (STAMP E NLP)
# ==========================================


def test_stamp_ai_execution(use_test_db, db_session, generate_archive_dto):
    """Testa se a coluna JSONB mutável salva o novo log garantindo o estado da ORM."""
    dto = generate_archive_dto(description_id="27", execution_log={"migracao_base": "DONE"})
    upsert_archive_document(db_session, dto)
    db_session.commit()

    stamp_ai_execution(db_session, "27", "ner_spacy_v1")
    db_session.commit()

    doc_banco = db_session.execute(select(ArchiveDocument).filter_by(description_id="27")).scalar_one()

    assert "migracao_base" in doc_banco.execution_log
    assert doc_banco.execution_log["ner_spacy_v1"] == "DONE"


def test_get_ner_synonyms_rules(use_test_db, db_session):
    """Testa a junção SQL que gera os padrões do spaCy baseados na tabela oficial de Sinônimos."""
    # 1. Cria a Entidade Canônica
    ent_canonica = ArchiveEntity(name="Prefeitura de Curitiba", entity_type="ORG")
    db_session.add(ent_canonica)
    db_session.commit()

    # 2. Cria o Sinônimo apontando para a Entidade
    sinonimo = DomainSynonyms(
        synonym_name="prefeitura municipal", category="ORG", canonical_entity_id=ent_canonica.entity_id
    )
    db_session.add(sinonimo)
    db_session.commit()

    # 3. Executa a query
    regras = get_ner_synonyms_rules(db_session)

    assert len(regras) == 1
    assert regras[0]["pattern"] == "prefeitura municipal"
    assert regras[0]["label"] == "ORG"
    assert regras[0]["canonical_name"] == "Prefeitura de Curitiba"


# ==========================================
# 5. TESTES DE STOPWORDS DO DOMÍNIO
# ==========================================


def test_save_and_get_stopwords(use_test_db, db_session):
    """Testa o bulk insert com ON CONFLICT e a extração limpa."""
    palavras_sujas = [" Curitiba ", "ofício", "", "  ", "Prefeitura"]

    save_stopwords(db_session, palavras_sujas)
    db_session.commit()

    save_stopwords(db_session, ["ofício", "colombo"])
    db_session.commit()

    stopwords_db = get_stopwords(db_session)

    assert "curitiba" in stopwords_db
    assert "prefeitura" in stopwords_db
    assert "" not in stopwords_db
    assert len(stopwords_db) == 4
