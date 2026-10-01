import os
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from core.base import Base
from domains.archive.models import ArchiveDocument, ArchiveTypology
from domains.archive.schemas import ArchiveEntityDTO
from domains.archive.schemas.document_schema import ArchiveDocumentDTO
from domains.ingestion import models as ingest_model

# Descobre o caminho absoluto da pasta 'tests' de forma dinâmica
TESTS_FOLDER = Path(__file__).parent

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "postgresql://test_user:test_password@localhost:5433/test_db")


@pytest.fixture
def mock_registry(monkeypatch):
    """
    Fixture Factory: Prepara dinamicamente qualquer módulo registry para testes,
    garantindo que a IA real nunca seja chamada por acidente
    """

    def _patch_registry(registry_module):
        # 1. Criamos a nossa Classe Falsa
        MockEngineClass = MagicMock()

        for engine_name in registry_module.AVAILABLE_ENGINES:
            monkeypatch.setitem(registry_module.AVAILABLE_ENGINES, engine_name, MockEngineClass)

        # 3. Blindamos os presets também para evitar validações chatas de chaves reais
        for preset_name in registry_module.PRESETS:
            monkeypatch.setitem(registry_module.PRESETS, preset_name, {"model": "falso", "device": "cpu"})

        monkeypatch.setitem(registry_module.AVAILABLE_ENGINES, "motor_fake", MockEngineClass)
        monkeypatch.setitem(registry_module.PRESETS, "preset_teste", {"model": "falso", "device": "cpu"})

        # Retornamos a classe para os asserts
        return MockEngineClass

    return _patch_registry


@pytest.fixture
def html_mock_valido():
    """Simula uma página perfeita do Site do Arquivo."""

    file_path = TESTS_FOLDER / "data" / "valid_scrape_request.html"

    return file_path.read_text(encoding="utf-8")


@pytest.fixture
def html_mock_vazio():
    """Simula uma página sem dados úteis."""
    return "<html><body><h1>Sem dados</h1></body></html>"


@pytest.fixture
def fila_mock():
    """Cria um registro falso da Fila para injetar no Orquestrador."""
    return ingest_model.ScrapingQueue(
        description_id="doc-123",
        scrape_status=ingest_model.ScrapeStatus.PENDING,
        retry_count=0,
        discovered_at=datetime.now(UTC),
    )


@pytest.fixture(scope="session")
def engine():
    """Cria a conexão com o banco de testes e monta a estrutura de tabelas uma única vez."""
    engine = create_engine(TEST_DATABASE_URL)

    # pg_trgm must exist before create_all builds the fuzzy-search GIN indexes.
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))

    # Cria todas as tabelas baseadas nos seus Models
    Base.metadata.create_all(bind=engine)

    yield engine

    # Ao final de todos os testes, destrói as tabelas
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture(scope="function")
def db_session(engine) -> Generator[Session, None, None]:
    """
    Fornece uma sessão isolada para cada teste.
    Usa SAVEPOINTs para garantir que mesmo que o código teste chame db.commit(),
    tudo seja revertido no final do teste, mantendo o banco vazio para o próximo.
    """
    connection = engine.connect()
    transaction = connection.begin()

    # join_transaction_mode="create_savepoint" é o segredo do SQLAlchemy 2.0
    # Ele empacota os seus commits reais em sub-transações temporárias
    session = Session(bind=connection, join_transaction_mode="create_savepoint")

    yield session

    # Encerra o teste destruindo a sessão e dando um rollback em absolutamente tudo
    session.close()
    transaction.rollback()
    connection.close()


# Tiramos o autouse=True!
@pytest.fixture()
def use_test_db(db_session):
    """
    Fixture sob demanda. Apenas os testes que pedirem por 'use_test_db'
    terão o 'get_db' interceptado e apontado para o Docker.
    """

    @contextmanager
    def _mock_get_db():
        yield db_session

    with patch("core.database.get_db", _mock_get_db):
        yield


@pytest.fixture
def generate_archive_doc(db_session):
    """
    Uma fábrica inteligente de documentos.
    Preenche automaticamente todos os campos chatos e obrigatórios,
    mas permite que o teste sobrescreva apenas o que importa.
    """

    def _create(**kwargs):
        dados_padrao = {
            # Gera uma string única e corta para caber no limite de String(50)
            "description_id": f"doc_teste_{uuid.uuid4().hex[:30]}",
            "original_title": "Título Genérico de Teste",
            "staging_content_hash": "hash_falso_1234567890abcdef",
        }

        dados_padrao.update(kwargs)
        doc = ArchiveDocument(**dados_padrao)
        db_session.add(doc)
        db_session.commit()

        return doc

    return _create


@pytest.fixture
def generate_archive_dto():
    """
    Fábrica para gerar DTOs válidos para os testes de CRUD e ETL.
    Preenche automaticamente os campos que o Pylance exige.
    """

    def _create(**kwargs):
        # O esqueleto com tudo o que o Pylance exige
        dados_padrao: dict[str, Any] = {
            "description_id": f"doc_teste_{uuid.uuid4().hex[:30]}",
            "original_title": "Titulo Teste",
            "staging_content_hash": "hash_falso_1234567890abcdef",
        }

        dados_padrao.update(kwargs)
        return ArchiveDocumentDTO(**dados_padrao)

    return _create


@pytest.fixture
def mock_staging_doc():
    """
    Gera um objeto Mock perfeito simulando um StagingDocument vindo do banco.
    Evita que o Pydantic dê erro de validação de tipos durante os testes dos Workers.
    """

    def _create(description_id="doc-100", raw_content_hash="hash_123"):
        from unittest.mock import Mock

        doc = Mock()
        doc.description_id = description_id
        doc.title = "Dossiê Teste"
        doc.document_date = None
        doc.scope_content = "Resumo do documento"
        doc.raw_content_hash = raw_content_hash
        doc.reference_code = "BR PR"
        doc.level = "Dossiê"
        doc.producers = "Prefeitura"
        doc.admin_bio_history = None
        doc.admin_archival_history = None
        doc.provenance = None
        doc.language_name = "pt-BR"
        doc.archivist_notes = None
        doc.indexing_points = "Tag Teste"
        doc.thumb_down_link = ""
        return doc

    return _create


@pytest.fixture
def generate_typology(db_session):
    """Fábrica para popular a tabela de tipologias antes dos testes."""

    def _create(id=99, name="Dossiê"):
        tipo = ArchiveTypology(typology_id=id, name=name)
        db_session.add(tipo)
        db_session.commit()
        return tipo

    return _create


@pytest.fixture
def mock_ner_engine():
    """Simula o motor spaCy devolvendo DTOs de entidades."""
    mock_engine = MagicMock()
    entidade_mock = ArchiveEntityDTO(name="Prefeitura de Curitiba", entity_type="ORG")

    # Função dinâmica: devolve uma cópia do resultado para CADA texto que entrar
    def simulador_de_extracao(texts):
        return [[entidade_mock] for _ in texts]

    mock_engine.extract.side_effect = simulador_de_extracao
    return mock_engine
