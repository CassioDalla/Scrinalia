from unittest.mock import MagicMock, patch

import pytest

from memoria_curitibana.domains.archive.models.governance import ArchiveCleaningRule
from memoria_curitibana.domains.archive.schemas.cleaning_schema import CleanableDocumentDTO, CleaningUpdateCommand
from memoria_curitibana.domains.archive.workers.worker_cleaning_regex import execute

# ==========================================
# FIXTURES AND MOCKS
# ==========================================


@pytest.fixture
def mock_db():
    """Mock of the SQLAlchemy Session."""
    return MagicMock()


@pytest.fixture
def mock_repo():
    """Mock of the Repository injected into the Worker."""
    with patch("memoria_curitibana.domains.archive.workers.worker_cleaning_regex.CleaningRepository") as MockRepoClass:
        yield MockRepoClass.return_value


# ==========================================
# TESTS
# ==========================================
def test_worker_stops_when_no_rules(mock_db, mock_repo):
    """Guarantees that the Worker does not run useless queries if there are no active rules."""
    mock_repo.get_active_rules.return_value = []

    execute(mock_db)

    mock_repo.get_unprocessed_documents_for_rule.assert_not_called()
    mock_db.commit.assert_not_called()


def test_worker_applies_rule_successfully(mock_db, mock_repo):
    """Tests the perfect flow (Happy Path): cleans, builds the update commands and commits."""
    # 1. Prepare the active rule
    rule = ArchiveCleaningRule(
        rule_id=5,
        rule_name="Limpa Av",
        target_column="original_title",
        regex_pattern=r"\bav\b\.?",
        replacement_string="Avenida",
    )
    mock_repo.get_active_rules.return_value = [rule]

    # 2. Prepare the scanned documents (read DTOs, no ORM)
    dirty_doc = CleanableDocumentDTO(description_id="BR_01", text="av. Paulista")
    clean_doc = CleanableDocumentDTO(description_id="BR_02", text="Avenida Brasil")

    # 3. The side_effect simulates the while loop: first returns 2 docs, then returns empty to end the batch
    mock_repo.get_unprocessed_documents_for_rule.side_effect = [
        [dirty_doc, clean_doc],
        [],  # Ends the While True
    ]

    # Run the Worker
    execute(mock_db)

    # Both documents go through the repository as commands; the changed one is rewritten,
    # the clean one is kept as is, and both receive the rule stamp.
    mock_repo.apply_cleaning.assert_called_once()
    updates = mock_repo.apply_cleaning.call_args[0][0]
    assert updates == [
        CleaningUpdateCommand(
            description_id="BR_01",
            target_column="original_title",
            new_text="Avenida Paulista",
            stamp_key="cleaning_rule_5",
        ),
        CleaningUpdateCommand(
            description_id="BR_02",
            target_column="original_title",
            new_text="Avenida Brasil",
            stamp_key="cleaning_rule_5",
        ),
    ]

    # Check that the database was saved
    mock_db.commit.assert_called_once()


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


def test_worker_rolls_back_on_db_error(mock_db, mock_repo):
    """If there is a constraint/connection error in the middle of the batch, it must roll back and exit the infinite loop."""
    rule = ArchiveCleaningRule(
        rule_id=10, rule_name="Regra X", target_column="original_title", regex_pattern="x", replacement_string="y"
    )
    mock_repo.get_active_rules.return_value = [rule]

    doc = CleanableDocumentDTO(description_id="BR_01", text="x")
    mock_repo.get_unprocessed_documents_for_rule.return_value = [doc]

    # Force an error at commit time (e.g., Network drop, Deadlock)
    mock_db.commit.side_effect = Exception("Deadlock detectado")

    execute(mock_db)

    # It must have rolled back to avoid corrupting the database
    mock_db.rollback.assert_called_once()

    # And very important: it cannot have gotten stuck in an infinite `While True` loop
    mock_repo.get_unprocessed_documents_for_rule.assert_called_once()
