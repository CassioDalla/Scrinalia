import pytest
from pytest_mock import MockerFixture
from sqlalchemy.orm import Session

from scrinalia.domains.archive.domain.vocabulary import label_set_fingerprint
from scrinalia.domains.archive.workers import worker_macro_category

#: The stamp value a tag gets after being classified against a given label set. The worker
#: stores the *identity of the vocabulary*, not a status, so this changes whenever a drawer
#: is added, retired or relabelled — which is what re-queues the collection.
FINGERPRINT = label_set_fingerprint({"Urbanismo": 7})


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
    mock_repo_class = mocker.patch("scrinalia.domains.archive.workers.worker_macro_category.TagRepository")
    mock_get_engine = mocker.patch("scrinalia.domains.archive.workers.worker_macro_category.get_engine")
    mocker.patch("scrinalia.domains.archive.workers.worker_macro_category.flag_modified")

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
    assert tag.execution_log == {"worker_macro_category_v1": FINGERPRINT}


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
    assert tag.execution_log == {"worker_macro_category_v1": FINGERPRINT}


def test_worker_survives_hallucinated_label(mocker: MockerFixture) -> None:
    """The engine cannot force a KeyError by returning a label that is not in the map."""
    mock_db, engine = _prepare(mocker, {"Urbanismo": 7})
    engine.classify.return_value = [{"labels": ["Categoria Inexistente"], "scores": [0.99]}]

    tag = MockArchiveTag(1, "algo")
    mock_db.scalars.return_value.all.side_effect = [[tag], []]

    worker_macro_category.execute(db=mock_db, engine_name="motor_fake", preset="preset_teste")  # type: ignore

    assert tag.macro_category_id is None
    assert tag.execution_log == {"worker_macro_category_v1": FINGERPRINT}


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


# ==========================================
# NENHUMA: THE DETERMINISTIC GUARD
# ==========================================


def test_worker_never_sends_a_bare_year_to_the_model(mocker: MockerFixture) -> None:
    """
    ``1924`` reaches 260 documents, is a date, and was classified as "Mobilidade e
    Transporte" with 0.73 confidence — no threshold can catch a confident wrong answer.
    """
    mock_db, engine = _prepare(mocker, {"Urbanismo": 7})
    year = MockArchiveTag(1, "1924")
    real = MockArchiveTag(2, "alvenaria")
    engine.classify.return_value = [{"labels": ["Urbanismo"], "scores": [0.93]}]
    mock_db.scalars.return_value.all.side_effect = [[year, real], []]

    worker_macro_category.execute(db=mock_db, engine_name="motor_fake", preset="preset_teste")  # type: ignore

    # Only the real subject reached the engine, and the results line up with it — not with
    # the batch, which would have shifted every label by one.
    engine.classify.assert_called_once_with(["alvenaria"], ["Urbanismo"], batch_size=1)
    assert real.macro_category_id == 7
    assert year.macro_category_id is None
    assert year.ai_confidence_score is None
    assert year.execution_log == {"worker_macro_category_v1": FINGERPRINT}


def test_worker_skips_a_placeholder_and_a_street(mocker: MockerFixture) -> None:
    """``local não identificado`` (166 docs) and ``rua xv de novembro`` (118) are not subjects."""
    mock_db, engine = _prepare(mocker, {"Urbanismo": 7})
    tags = [
        MockArchiveTag(1, "local não identificado"),
        MockArchiveTag(2, "rua xv de novembro"),
        MockArchiveTag(3, "parque"),
    ]
    engine.classify.return_value = [{"labels": ["Urbanismo"], "scores": [0.93]}]
    mock_db.scalars.return_value.all.side_effect = [tags, []]

    worker_macro_category.execute(db=mock_db, engine_name="motor_fake", preset="preset_teste")  # type: ignore

    engine.classify.assert_called_once_with(["parque"], ["Urbanismo"], batch_size=1)
    assert tags[0].macro_category_id is None
    assert tags[1].macro_category_id is None
    assert tags[2].macro_category_id == 7


def test_worker_does_not_instantiate_the_engine_for_an_all_guarded_batch(mocker: MockerFixture) -> None:
    """A batch of only dates must not pay for inference at all."""
    mock_db, engine = _prepare(mocker, {"Urbanismo": 7})
    tags = [MockArchiveTag(1, "1924"), MockArchiveTag(2, "1915")]
    mock_db.scalars.return_value.all.side_effect = [tags, []]

    worker_macro_category.execute(db=mock_db, engine_name="motor_fake", preset="preset_teste")  # type: ignore

    engine.classify.assert_not_called()
    for tag in tags:
        assert tag.macro_category_id is None
        assert tag.execution_log == {"worker_macro_category_v1": FINGERPRINT}


def test_guarded_tags_are_still_stamped_so_the_queue_advances(mocker: MockerFixture) -> None:
    """The guard is a verdict, not a failure: without a stamp the batch would loop forever."""
    mock_db, _engine = _prepare(mocker, {"Urbanismo": 7})
    mock_db.scalars.return_value.all.side_effect = [[MockArchiveTag(1, "1924")], []]

    worker_macro_category.execute(db=mock_db, engine_name="motor_fake", preset="preset_teste")  # type: ignore

    mock_db.rollback.assert_not_called()


# ==========================================
# THE STAMP IS THE IDENTITY OF THE VOCABULARY
# ==========================================


def test_a_different_vocabulary_produces_a_different_stamp() -> None:
    """Rewriting a label must re-queue the tags classified against the old one."""
    assert label_set_fingerprint({"Urbanismo": 7}) != label_set_fingerprint({"um assunto sobre obras e construção": 7})


def test_registering_a_drawer_invalidates_the_stamp() -> None:
    """A new drawer changes the decision the model makes, so nothing stays settled."""
    assert label_set_fingerprint({"Urbanismo": 7}) != label_set_fingerprint({"Urbanismo": 7, "Religião": 8})


def test_retiring_a_drawer_invalidates_the_stamp() -> None:
    """The V3 migration exposed exactly this: a retired drawer left its tags stamped DONE."""
    assert label_set_fingerprint({"Urbanismo": 7, "Instituição": 9}) != label_set_fingerprint({"Urbanismo": 7})


def test_the_fingerprint_does_not_depend_on_row_order() -> None:
    """Two orderings of the same vocabulary are the same vocabulary, not two."""
    assert label_set_fingerprint({"Urbanismo": 7, "Religião": 8}) == label_set_fingerprint(
        {"Religião": 8, "Urbanismo": 7}
    )


def test_replacing_a_drawer_under_the_same_label_invalidates_the_stamp() -> None:
    """Two drawers can share a name across time; the id is what keeps them apart."""
    assert label_set_fingerprint({"Urbanismo": 7}) != label_set_fingerprint({"Urbanismo": 99})
