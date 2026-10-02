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

# Dynamically discover the absolute path of the 'tests' folder
TESTS_FOLDER = Path(__file__).parent

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "postgresql://test_user:test_password@localhost:5433/test_db")


@pytest.fixture
def mock_registry(monkeypatch):
    """
    Fixture Factory: Dynamically prepares any registry module for tests,
    ensuring the real AI is never called by accident.
    """

    def _patch_registry(registry_module):
        # 1. We create our Fake Class
        MockEngineClass = MagicMock()

        for engine_name in registry_module.AVAILABLE_ENGINES:
            monkeypatch.setitem(registry_module.AVAILABLE_ENGINES, engine_name, MockEngineClass)

        # 3. We also shield the presets to avoid annoying validation of real keys
        for preset_name in registry_module.PRESETS:
            monkeypatch.setitem(registry_module.PRESETS, preset_name, {"model": "falso", "device": "cpu"})

        monkeypatch.setitem(registry_module.AVAILABLE_ENGINES, "motor_fake", MockEngineClass)
        monkeypatch.setitem(registry_module.PRESETS, "preset_teste", {"model": "falso", "device": "cpu"})

        # Return the class for the asserts
        return MockEngineClass

    return _patch_registry


@pytest.fixture
def html_mock_valid():
    """Simulates a perfect page from the Archive Site."""

    file_path = TESTS_FOLDER / "data" / "valid_scrape_request.html"

    return file_path.read_text(encoding="utf-8")


@pytest.fixture
def html_mock_empty():
    """Simulates a page with no useful data."""
    return "<html><body><h1>Sem dados</h1></body></html>"


@pytest.fixture
def queue_mock():
    """Creates a fake Queue record to inject into the Orchestrator."""
    return ingest_model.ScrapingQueue(
        description_id="doc-123",
        scrape_status=ingest_model.ScrapeStatus.PENDING,
        retry_count=0,
        discovered_at=datetime.now(UTC),
    )


@pytest.fixture(scope="session")
def engine():
    """Creates the connection to the test database and builds the table structure only once."""
    engine = create_engine(TEST_DATABASE_URL)

    # pg_trgm must exist before create_all builds the fuzzy-search GIN indexes.
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))

    # Creates all tables based on your Models
    Base.metadata.create_all(bind=engine)

    yield engine

    # At the end of all tests, drop the tables
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture(scope="function")
def db_session(engine) -> Generator[Session, None, None]:
    """
    Provides an isolated session for each test.
    Uses SAVEPOINTs to guarantee that even if the tested code calls db.commit(),
    everything is rolled back at the end of the test, keeping the database empty for the next one.
    """
    connection = engine.connect()
    transaction = connection.begin()

    # join_transaction_mode="create_savepoint" is the secret of SQLAlchemy 2.0
    # It wraps your real commits in temporary sub-transactions
    session = Session(bind=connection, join_transaction_mode="create_savepoint")

    yield session

    # End the test by destroying the session and rolling back absolutely everything
    session.close()
    transaction.rollback()
    connection.close()


# We removed autouse=True!
@pytest.fixture()
def use_test_db(db_session):
    """
    On-demand fixture. Only the tests that request 'use_test_db'
    will have 'get_db' intercepted and pointed at Docker.
    """

    @contextmanager
    def _mock_get_db():
        yield db_session

    with patch("core.database.get_db", _mock_get_db):
        yield


@pytest.fixture
def generate_archive_doc(db_session):
    """
    A smart document factory.
    Automatically fills in all the boring mandatory fields,
    but lets the test override only what matters.
    """

    def _create(**kwargs):
        default_data = {
            # Generates a unique string and trims it to fit the String(50) limit
            "description_id": f"doc_teste_{uuid.uuid4().hex[:30]}",
            "original_title": "Título Genérico de Teste",
            "staging_content_hash": "hash_falso_1234567890abcdef",
        }

        default_data.update(kwargs)
        doc = ArchiveDocument(**default_data)
        db_session.add(doc)
        db_session.commit()

        return doc

    return _create


@pytest.fixture
def generate_archive_dto():
    """
    Factory to generate valid DTOs for the CRUD and ETL tests.
    Automatically fills in the fields that Pylance requires.
    """

    def _create(**kwargs):
        # The skeleton with everything Pylance requires
        default_data: dict[str, Any] = {
            "description_id": f"doc_teste_{uuid.uuid4().hex[:30]}",
            "original_title": "Titulo Teste",
            "staging_content_hash": "hash_falso_1234567890abcdef",
        }

        default_data.update(kwargs)
        return ArchiveDocumentDTO(**default_data)

    return _create


@pytest.fixture
def mock_staging_doc():
    """
    Generates a perfect Mock object simulating a StagingDocument coming from the database.
    Prevents Pydantic from raising type-validation errors during the Worker tests.
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
    """Factory to populate the typology table before the tests."""

    def _create(id=99, name="Dossiê"):
        typology = ArchiveTypology(typology_id=id, name=name)
        db_session.add(typology)
        db_session.commit()
        return typology

    return _create


@pytest.fixture
def mock_ner_engine():
    """Simulates the spaCy engine returning entity DTOs."""
    mock_engine = MagicMock()
    entity_mock = ArchiveEntityDTO(name="Prefeitura de Curitiba", entity_type="ORG")

    # Dynamic function: returns a copy of the result for EACH text that comes in
    def extraction_simulator(texts):
        return [[entity_mock] for _ in texts]

    mock_engine.extract.side_effect = extraction_simulator
    return mock_engine


def pytest_collection_modifyitems(config, items):
    """Tag every collected test with ``unit`` or ``integration`` based on its path.

    This keeps the suite runnable without a database via ``pytest -m unit`` and lets
    CI/developers select the integration layer explicitly, without annotating each file.
    """
    for item in items:
        path = str(item.fspath)
        if "/tests/integration/" in path:
            item.add_marker(pytest.mark.integration)
        elif "/tests/unit/" in path:
            item.add_marker(pytest.mark.unit)
