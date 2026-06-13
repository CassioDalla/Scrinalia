from sqlalchemy import select, text

from core.crud.gold_crud import (
    get_or_create_entities,
    get_or_create_tags,
    get_stopwords,
    link_description_relationships,
    load_nlp_rules,
    save_stopwords,
    stamp_ai_execution,
    upsert_gold_description,
)
from core.models.gold_layer import (
    GoldDescriptionEntityModel,
    GoldDescriptionModel,
    GoldDescriptionTagModel,
    GoldEntityModel,
    GoldReviewStatus,
    GoldTagModel,
)
from core.schemas.gold_schema import GoldEntityDTO, GoldTagDTO

# ==========================================
# 1. TESTES DE UPSERT (CARGA DA ETL)
# ==========================================


def test_upsert_gold_description_insert_new(use_test_db, db_session, generate_gold_description_dto):
    """Cenário 1: Inserção de documento inédito vindo da Silver."""
    dto_novo = generate_gold_description_dto(description_id="1", original_title="Inédito", silver_content_hash="hash_1")

    inseriu = upsert_gold_description(db_session, dto_novo)
    db_session.commit()

    assert inseriu is True
    doc_banco = db_session.execute(select(GoldDescriptionModel).filter_by(description_id="1")).scalar_one()
    assert doc_banco.original_title == "Inédito"


def test_upsert_gold_description_ignore_same_hash(use_test_db, db_session, generate_gold_description_dto):
    """Cenário 2: Carga Incremental. Documento com mesmo Hash deve ser ignorado."""
    dto_original = generate_gold_description_dto(
        description_id="2", original_title="Original", silver_content_hash="hash_2"
    )
    upsert_gold_description(db_session, dto_original)
    db_session.commit()

    # Tenta inserir de novo com o mesmo hash, mas título diferente
    dto_repetido = generate_gold_description_dto(
        description_id="2", original_title="Falso", silver_content_hash="hash_2"
    )
    inseriu_repetido = upsert_gold_description(db_session, dto_repetido)
    db_session.commit()

    assert inseriu_repetido is False
    doc_banco = db_session.execute(select(GoldDescriptionModel).filter_by(description_id="2")).scalar_one()
    assert doc_banco.original_title == "Original"  # O título NÃO deve ter mudado


def test_upsert_gold_description_update_different_hash(use_test_db, db_session, generate_gold_description_dto):
    """Cenário 3: Atualização de documento. Se o Hash mudou na Silver, a Gold deve atualizar."""
    dto_original = generate_gold_description_dto(
        description_id="3", original_title="Antigo", silver_content_hash="hash_3"
    )
    upsert_gold_description(db_session, dto_original)
    db_session.commit()

    # Nova carga com Hash atualizado
    dto_novo = generate_gold_description_dto(
        description_id="3", original_title="Novo Título", silver_content_hash="hash_3_NOVO"
    )
    inseriu_novo = upsert_gold_description(db_session, dto_novo)
    db_session.commit()

    assert inseriu_novo is True
    doc_banco = db_session.execute(select(GoldDescriptionModel).filter_by(description_id="3")).scalar_one()
    assert doc_banco.original_title == "Novo Título"


def test_upsert_gold_description_blocked_by_human_approved(use_test_db, db_session, generate_gold_description_dto):
    """Cenário 4: Governança. Documento com status HUMAN_APPROVED bloqueia sobrescrita da ETL."""
    # Simula documento que já foi aprovado por humano
    dto_original = generate_gold_description_dto(
        description_id="4",
        original_title="Revisado Perfeito",
        silver_content_hash="hash_4",
        review_status=GoldReviewStatus.HUMAN_APPROVED,
    )
    upsert_gold_description(db_session, dto_original)
    db_session.commit()

    # A ETL tenta sobrescrever com um hash novo (ex: extração nova do CSV)
    dto_ataque = generate_gold_description_dto(
        description_id="4", original_title="Lixo da Silver", silver_content_hash="hash_4_NOVO"
    )
    inseriu_ataque = upsert_gold_description(db_session, dto_ataque)
    db_session.commit()

    assert inseriu_ataque is False  # Bloqueado!
    doc_banco = db_session.execute(select(GoldDescriptionModel).filter_by(description_id="4")).scalar_one()
    assert doc_banco.original_title == "Revisado Perfeito"


# ==========================================
# 2. TESTES DE ENTIDADES
# ==========================================


def test_get_or_create_entities_new(use_test_db, db_session):
    """Garante a criação de entidades inéditas, limpando os espaços do nome."""
    entidades_dto = [
        GoldEntityDTO(name="  David Carneiro  ", entity_type="PER"),
        GoldEntityDTO(name="Curitiba", entity_type="LOC"),
    ]
    ids_gerados = get_or_create_entities(db_session, entidades_dto)
    db_session.commit()

    assert len(ids_gerados) == 2
    entidade_db = db_session.execute(select(GoldEntityModel).filter_by(name="David Carneiro")).scalar_one()
    assert entidade_db.entity_type == "PER"


def test_get_or_create_entities_existing(use_test_db, db_session):
    """Garante a idempotência (ON CONFLICT DO NOTHING) para entidades que já existem."""
    entidades_dto = [GoldEntityDTO(name="Prefeitura", entity_type="ORG")]

    # Primeira chamada: Cria a entidade
    ids_passo_1 = get_or_create_entities(db_session, entidades_dto)
    db_session.commit()

    # Segunda chamada: Deve devolver o mesmo ID sem estourar UniqueConstraint error
    ids_passo_2 = get_or_create_entities(db_session, entidades_dto)
    db_session.commit()

    assert ids_passo_1[0] == ids_passo_2[0]


# ==========================================
# 3. TESTES DE TAGS
# ==========================================


def test_get_or_create_tags_new_and_lowercased(use_test_db, db_session):
    """Garante a criação de tags inéditas e que todas fiquem em letras minúsculas."""
    tags_dto = [GoldTagDTO(name=" ARQUIVAMENTO ", macro_category="Administrativo")]
    ids_gerados = get_or_create_tags(db_session, tags_dto)
    db_session.commit()

    assert len(ids_gerados) == 1
    tag_db = db_session.execute(select(GoldTagModel).filter_by(tag_id=ids_gerados[0])).scalar_one()
    assert tag_db.name == "arquivamento"  # Teste estrito de lowercase


def test_get_or_create_tags_existing(use_test_db, db_session):
    """Garante a idempotência para Tags que já existem."""
    tags_dto = [GoldTagDTO(name="fotografia")]
    ids_1 = get_or_create_tags(db_session, tags_dto)
    ids_2 = get_or_create_tags(db_session, tags_dto)

    assert ids_1 == ids_2


# ==========================================
# 4. TESTES DE RELACIONAMENTOS (N:N)
# ==========================================


def test_link_description_relationships_new(use_test_db, db_session, generate_gold_description_dto):
    """Testa a criação das pontes N:N entre Documento, Entidade e Tag."""
    # Prepara o banco com 1 doc, 1 entidade e 1 tag
    upsert_gold_description(db_session, generate_gold_description_dto(description_id="25"))
    ent_id = get_or_create_entities(db_session, [GoldEntityDTO(name="Ent", entity_type="ORG")])[0]
    tag_id = get_or_create_tags(db_session, [GoldTagDTO(name="Tag")])[0]
    db_session.commit()

    # Executa a vinculação
    link_description_relationships(db_session, "25", [ent_id], [tag_id])
    db_session.commit()

    # Verifica se os vínculos nasceram
    qtd_ent = db_session.query(GoldDescriptionEntityModel).count()
    qtd_tag = db_session.query(GoldDescriptionTagModel).count()
    assert qtd_ent == 1
    assert qtd_tag == 1


def test_link_description_relationships_duplicate_safe(use_test_db, db_session, generate_gold_description_dto):
    """Garante que rodar o Worker de IA duas vezes não duplica vínculos no banco."""
    upsert_gold_description(db_session, generate_gold_description_dto(description_id="26"))
    tag_id = get_or_create_tags(db_session, [GoldTagDTO(name="Tag2")])[0]
    db_session.commit()

    # Roda a vinculação duas vezes seguidas
    link_description_relationships(db_session, "26", [], [tag_id])
    link_description_relationships(db_session, "26", [], [tag_id])
    db_session.commit()

    # O banco de dados deve ter ignorado o segundo vínculo silenciosamente
    qtd_tag = db_session.query(GoldDescriptionTagModel).count()
    assert qtd_tag == 1


# ==========================================
# 5. TESTES DE IA (STAMP E NLP)
# ==========================================


def test_stamp_ai_execution(use_test_db, db_session, generate_gold_description_dto):
    """Testa se a coluna JSONB execution_log é atualizada corretamente sem perder chaves antigas."""
    # Cria doc com um log existente
    dto = generate_gold_description_dto(description_id="27", execution_log={"migracao_base": "completed"})
    upsert_gold_description(db_session, dto)
    db_session.commit()

    # Roda o carimbo de um novo worker
    stamp_ai_execution(db_session, "27", "ner_spacy")
    db_session.commit()

    doc_banco = db_session.execute(select(GoldDescriptionModel).filter_by(description_id="27")).scalar_one()

    # Valida se preservou a migração E adicionou o novo
    assert "migracao_base" in doc_banco.execution_log
    assert doc_banco.execution_log["ner_spacy"] == "completed"


def test_load_nlp_rules(use_test_db, db_session):
    """Testa a extração de regras customizadas para o motor do spaCy."""
    # Como não temos um model DDL formal mapeado para a nlp_dictionary no SQLAlchemy,
    # vamos criar a tabela em tempo de execução via comando cru no banco de teste:
    db_session.execute(
        text("""
        CREATE TABLE IF NOT EXISTS nlp_dictionary (
            id SERIAL PRIMARY KEY,
            pattern TEXT,
            label TEXT,
            canonical_name TEXT
        )
    """)
    )
    db_session.execute(
        text(
            "INSERT INTO nlp_dictionary (pattern, label, canonical_name) VALUES ('prefeitura municipal', 'ORG', 'Prefeitura de Curitiba')"
        )
    )
    db_session.commit()

    regras = load_nlp_rules(db_session)

    assert len(regras) >= 1
    assert regras[0]["pattern"] == "prefeitura municipal"
    assert regras[0]["label"] == "ORG"
    assert regras[0]["id"] == "Prefeitura de Curitiba"


# ==========================================
# 6. TESTES DE STOPWORDS DO DOMÍNIO
# ==========================================


def test_save_and_get_stopwords(use_test_db, db_session):
    """Testa tanto a gravação em massa (bulk insert) quanto a busca de stopwords."""
    palavras_sujas = [" Curitiba ", "ofício", "", "  ", "Prefeitura"]

    # Salva
    save_stopwords(db_session, palavras_sujas)
    db_session.commit()

    # Tenta salvar itens repetidos (deve ser ignorado)
    save_stopwords(db_session, ["ofício", "colombo"])
    db_session.commit()

    # Recupera
    stopwords_db = get_stopwords(db_session)

    # Asserts
    assert "curitiba" in stopwords_db  # Deve ter feito strip e lower
    assert "ofício" in stopwords_db
    assert "prefeitura" in stopwords_db
    assert "colombo" in stopwords_db
    assert "" not in stopwords_db  # Palavras vazias devem ter sido limpas

    # 4 palavras válidas únicas ("curitiba", "ofício", "prefeitura", "colombo")
    assert len(stopwords_db) == 4
