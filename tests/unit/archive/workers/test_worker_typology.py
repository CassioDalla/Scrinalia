from pytest_mock import MockerFixture
from sqlalchemy.orm import Session

from domains.archive.workers import worker_typology


class MockArchiveDocument:
    """Ultralean double simulating an SQLAlchemy document for the Unit Tests."""

    def __init__(self, description_id: str, title: str, content: str | None = None):
        self.description_id = description_id
        self.original_title = title
        self.scope_content = content
        self.typology_id = None
        self.execution_log = None


# ==========================================
# TYPOLOGY WORKER ORCHESTRATION TESTS
# ==========================================


def test_worker_typology_unit_ideal_flow(mocker: MockerFixture) -> None:
    """Good Scenario: Texts are concatenated ignoring nulls, the AI classifies and the doc is updated."""
    mock_db = mocker.Mock(spec=Session)

    # 1. Mocks of the External Classes/Functions in the Worker scope
    mock_repo_class = mocker.patch("domains.archive.workers.worker_typology.TypologyRepository")
    mock_get_engine = mocker.patch("domains.archive.workers.worker_typology.get_engine")
    mock_flag_modified = mocker.patch("domains.archive.workers.worker_typology.flag_modified")

    # 2. Return Configurations (Faking the DB and the AI)
    mock_repo = mock_repo_class.return_value
    mock_repo.get_active_typologies.return_value = {"Contrato": 1}

    mock_classifier_engine = mock_get_engine.return_value
    # The HuggingFace/ZeroShot AI returns a list with the format: [{"labels": [...], "scores": [...]}]
    mock_classifier_engine.classify.return_value = [{"labels": ["Contrato"], "scores": [0.95]}]

    # 3. Simulates the database queue (1 document on the 1st round, breaks the loop on the 2nd)
    # We send the content as None to test whether it ignores the Null and does not concatenate junk
    test_doc = MockArchiveDocument("doc-1", "Contrato de Prestação de Serviços", None)
    mock_db.scalars.return_value.all.side_effect = [[test_doc], []]

    # 4. Execution
    worker_typology.execute(
        db=mock_db,
        engine_name="motor_fake",  # type: ignore
        preset="preset_teste",  # type: ignore
        columns_to_classify=["original_title", "scope_content"],
    )

    # 5. AI verifications
    mock_classifier_engine.classify.assert_called_once()
    args, _ = mock_classifier_engine.classify.call_args
    # Confirms whether the columns were cleaned, joined with a period and the "scope_content" field (None) ignored
    assert args[0] == ["Contrato de Prestação de Serviços"]

    # 6. Persistence verifications
    assert test_doc.typology_id == 1
    assert test_doc.execution_log["worker_typology_classifier_v1"] == "DONE"  # type: ignore

    mock_flag_modified.assert_called_once_with(test_doc, "execution_log")
    mock_db.commit.assert_called_once()


def test_worker_typology_ignores_empty_texts(mocker: MockerFixture) -> None:
    """Edge Scenario: Documents with no useful text must be skipped by the AI, but stamped in the DB."""
    mock_db = mocker.Mock(spec=Session)

    mocker.patch("domains.archive.workers.worker_typology.TypologyRepository")
    mock_get_engine = mocker.patch("domains.archive.workers.worker_typology.get_engine")
    mock_flag_modified = mocker.patch("domains.archive.workers.worker_typology.flag_modified")

    # Document where everything is empty
    empty_doc = MockArchiveDocument("doc-2", "   ", None)
    mock_db.scalars.return_value.all.side_effect = [[empty_doc], []]

    worker_typology.execute(db=mock_db)

    # The AI must not have been called (saves processing)
    mock_get_engine.return_value.classify.assert_not_called()

    # The stamp must have been applied so the Worker does not loop again tomorrow
    assert empty_doc.execution_log["worker_typology_classifier_v1"] == "DONE"  # type: ignore
    mock_flag_modified.assert_called_once()


def test_worker_typology_ai_failure_rolls_back(mocker: MockerFixture) -> None:
    """Bad Scenario: If the Zero-Shot engine throws a memory error, the transaction aborts and rolls back."""
    mock_db = mocker.Mock(spec=Session)

    mocker.patch("domains.archive.workers.worker_typology.TypologyRepository")
    mock_get_engine = mocker.patch("domains.archive.workers.worker_typology.get_engine")

    test_doc = MockArchiveDocument("doc-3", "Texto super complexo", "Muitas palavras")
    mock_db.scalars.return_value.all.side_effect = [[test_doc], []]

    # Force the NLP engine to explode
    mock_get_engine.return_value.classify.side_effect = Exception("Out of Memory na GPU")

    worker_typology.execute(db=mock_db)

    # The rollback must have been called to protect the database transaction
    mock_db.rollback.assert_called()

    # The stamp must not have been applied, allowing a future retry
    assert test_doc.execution_log is None
