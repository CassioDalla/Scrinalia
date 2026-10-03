import pytest
from pytest_mock import MockerFixture
from sqlalchemy.orm import Session

from memoria_curitibana.domains.archive.workers import worker_macro_category


class MockArchiveTag:
    """Ultralean double simulating an SQLAlchemy tag for the Unit Tests."""

    def __init__(
        self,
        tag_id: int,
        name: str,
        macro_category_id: int | None = None,
        ai_confidence_score: float | None = None,
        execution_log: dict[str, str] | None = None,
    ):
        self.tag_id = tag_id
        self.name = name
        self.macro_category_id = macro_category_id
        self.ai_confidence_score = ai_confidence_score
        self.execution_log = execution_log


def _prepare(mocker: MockerFixture, categories: dict[str, int]):
    """Patches the repository and the engine, returning (db, engine, repo)."""
    mock_db = mocker.Mock(spec=Session)
    mock_repo_class = mocker.patch("memoria_curitibana.domains.archive.workers.worker_macro_category.TagRepository")
    mock_get_engine = mocker.patch("memoria_curitibana.domains.archive.workers.worker_macro_category.get_engine")
    mocker.patch("memoria_curitibana.domains.archive.workers.worker_macro_category.flag_modified")

    mock_repo_class.return_value.get_active_macro_categories.return_value = categories

    return mock_db, mock_get_engine.return_value


# ==========================================
# MACRO CATEGORY WORKER ORCHESTRATION TESTS
# ==========================================


def test_worker_links_category_and_persists_score(mocker: MockerFixture) -> None:
    """Good Scenario: the AI wins the tag, the category is linked and the score persisted."""
    mock_db, engine = _prepare(mocker, {"Urbanismo": 7})
    engine.classify.return_value = [{"labels": ["Urbanismo"], "scores": [0.93]}]

    tag = MockArchiveTag(1, "pavimentação")
    mock_db.scalars.return_value.all.side_effect = [[tag], []]

    worker_macro_category.execute(db=mock_db, engine_name="motor_fake", preset="preset_teste")  # type: ignore

    assert tag.macro_category_id == 7
    assert tag.ai_confidence_score == pytest.approx(0.93)
    assert tag.execution_log == {"worker_macro_category_v1": "DONE"}


def test_worker_keeps_score_but_does_not_link_below_threshold(mocker: MockerFixture) -> None:
    """Sad Path: below the threshold the tag stays orphan, but the score is observable."""
    mock_db, engine = _prepare(mocker, {"Urbanismo": 7})
    engine.classify.return_value = [{"labels": ["Urbanismo"], "scores": [0.20]}]

    tag = MockArchiveTag(1, "termo ambíguo")
    mock_db.scalars.return_value.all.side_effect = [[tag], []]

    worker_macro_category.execute(db=mock_db, engine_name="motor_fake", preset="preset_teste")  # type: ignore

    assert tag.macro_category_id is None
    assert tag.ai_confidence_score == pytest.approx(0.20)
    # Still stamped: the tag leaves the queue instead of looping forever.
    assert tag.execution_log == {"worker_macro_category_v1": "DONE"}


def test_worker_survives_hallucinated_label(mocker: MockerFixture) -> None:
    """The engine cannot force a KeyError by returning a label that is not in the map."""
    mock_db, engine = _prepare(mocker, {"Urbanismo": 7})
    engine.classify.return_value = [{"labels": ["Categoria Inexistente"], "scores": [0.99]}]

    tag = MockArchiveTag(1, "algo")
    mock_db.scalars.return_value.all.side_effect = [[tag], []]

    worker_macro_category.execute(db=mock_db, engine_name="motor_fake", preset="preset_teste")  # type: ignore

    assert tag.macro_category_id is None
    assert tag.execution_log == {"worker_macro_category_v1": "DONE"}


def test_worker_aborts_without_registered_categories(mocker: MockerFixture) -> None:
    """Without an active macro category there is nothing to classify against."""
    mock_db, engine = _prepare(mocker, {})

    worker_macro_category.execute(db=mock_db, engine_name="motor_fake", preset="preset_teste")  # type: ignore

    engine.classify.assert_not_called()
    mock_db.scalars.assert_not_called()


def test_worker_aborts_without_pending_tags(mocker: MockerFixture) -> None:
    """When the count query says zero, the AI must not even be instantiated."""
    mock_db, engine = _prepare(mocker, {"Urbanismo": 7})
    mock_db.scalar.return_value = 0

    worker_macro_category.execute(db=mock_db, engine_name="motor_fake", preset="preset_teste")  # type: ignore

    engine.classify.assert_not_called()


def test_worker_rolls_back_on_ai_failure(mocker: MockerFixture) -> None:
    """OOM/engine failure must roll back the batch and leave the tags unstamped for a retry."""
    mock_db, engine = _prepare(mocker, {"Urbanismo": 7})
    engine.classify.side_effect = Exception("CUDA Out of Memory")

    tag = MockArchiveTag(1, "texto")
    mock_db.scalars.return_value.all.side_effect = [[tag], []]

    worker_macro_category.execute(db=mock_db, engine_name="motor_fake", preset="preset_teste")  # type: ignore

    assert tag.macro_category_id is None
    assert tag.execution_log is None
    mock_db.rollback.assert_called_once()
