from unittest.mock import MagicMock, patch

import pytest

from domains.archive.models.governance import ArchiveCleaningRule
from domains.archive.workers.worker_cleaning_regex import execute

# ==========================================
# FIXTURES AND MOCKS
# ==========================================


class MockDocument:
    """Simulates a document returned by the database."""

    def __init__(self, description_id, text, execution_log=None):
        self.description_id = description_id
        self.original_title = text
        self.execution_log = execution_log


@pytest.fixture
def mock_db():
    """Mock of the SQLAlchemy Session."""
    return MagicMock()


@pytest.fixture
def mock_repo():
    """Mock of the Repository injected into the Worker."""
    with patch("domains.archive.workers.worker_cleaning_regex.CleaningRepository") as MockRepoClass:
        yield MockRepoClass.return_value


@pytest.fixture
def mock_flag_modified():
    """Mock of the SQLAlchemy flag_modified function to avoid errors without a real mapping."""
    with patch("domains.archive.workers.worker_cleaning_regex.flag_modified") as mock_flag:
        yield mock_flag


# ==========================================
# TESTS
# ==========================================
def test_worker_stops_when_no_rules(mock_db, mock_repo):
    """Guarantees that the Worker does not run useless queries if there are no active rules."""
    mock_repo.get_active_rules.return_value = []

    execute(mock_db)

    mock_repo.get_unprocessed_documents_for_rule.assert_not_called()
    mock_db.commit.assert_not_called()


def test_worker_applies_rule_successfully(mock_db, mock_repo, mock_flag_modified):
    """Tests the perfect flow (Happy Path): Cleans, stamps the JSONB and commits."""
    # 1. Prepare the active rule
    rule = ArchiveCleaningRule(
        rule_id=5,
        rule_name="Limpa Av",
        target_column="original_title",
        regex_pattern=r"\bav\b\.?",
        replacement_string="Avenida",
    )
    mock_repo.get_active_rules.return_value = [rule]

    # 2. Prepare the mocked documents
    dirty_doc = MockDocument("BR_01", "av. Paulista", execution_log=None)
    clean_doc = MockDocument("BR_02", "Avenida Brasil", execution_log={"outra_regra": "DONE"})

    # 3. The side_effect simulates the while loop: first returns 2 docs, then returns empty to end the batch
    mock_repo.get_unprocessed_documents_for_rule.side_effect = [
        [dirty_doc, clean_doc],
        [],  # Ends the While True
    ]

    # Run the Worker
    execute(mock_db)

    # Check Document 1 (should be modified and stamped)
    assert dirty_doc.original_title == "Avenida Paulista"
    assert dirty_doc.execution_log == {"cleaning_rule_5": "DONE"}

    # Check Document 2 (does not modify the text, preserves old logs and adds the new one)
    assert clean_doc.original_title == "Avenida Brasil"  # Intact
    assert clean_doc.execution_log == {"outra_regra": "DONE", "cleaning_rule_5": "DONE"}

    # Check that the database was saved
    mock_db.commit.assert_called_once()
    assert mock_flag_modified.call_count == 2


def test_worker_skips_rule_with_invalid_regex(mock_db, mock_repo):
    """Guarantees that if a rule has a broken Regex in the database, the Worker skips it without exploding."""
    broken_rule = ArchiveCleaningRule(
        rule_id=1, rule_name="Erro", target_column="original_title", regex_pattern=r"*[", replacement_string=""
    )
    good_rule = ArchiveCleaningRule(
        rule_id=2, rule_name="Boa", target_column="original_title", regex_pattern=r"teste", replacement_string=""
    )

    mock_repo.get_active_rules.return_value = [broken_rule, good_rule]

    # Simulates that there are no documents for the good rule, just to end quickly
    mock_repo.get_unprocessed_documents_for_rule.return_value = []

    execute(mock_db)

    # It must have tried to process rule 2 (good), which proves it did not get stuck on rule 1
    mock_repo.get_unprocessed_documents_for_rule.assert_called_once_with(
        rule_id=2, target_column="original_title", limit=500
    )


def test_worker_rolls_back_on_db_error(mock_db, mock_repo, mock_flag_modified):
    """If there is a constraint/connection error in the middle of the batch, it must roll back and exit the infinite loop."""
    rule = ArchiveCleaningRule(
        rule_id=10, rule_name="Regra X", target_column="original_title", regex_pattern="x", replacement_string="y"
    )
    mock_repo.get_active_rules.return_value = [rule]

    doc = MockDocument("BR_01", "x")
    mock_repo.get_unprocessed_documents_for_rule.return_value = [doc]

    # Force an error at commit time (e.g., Network drop, Deadlock)
    mock_db.commit.side_effect = Exception("Deadlock detectado")

    execute(mock_db)

    # It must have rolled back to avoid corrupting the database
    mock_db.rollback.assert_called_once()

    # And very important: it cannot have gotten stuck in an infinite `While True` loop
    mock_repo.get_unprocessed_documents_for_rule.assert_called_once()
