import pytest

from memoria_curitibana.domains.archive.engines.classification import registry as typology_registry
from memoria_curitibana.domains.archive.models import ArchiveMacroCategory, ArchiveTag
from memoria_curitibana.domains.archive.workers.worker_macro_category import execute


def _fake_engine(mock_registry, label: str, score: float):
    """Registers the fake engine and answers with the same verdict for every tag in the batch."""
    MockClass = mock_registry(typology_registry)
    ai_instance = MockClass.return_value
    ai_instance.classify.side_effect = lambda texts, candidate_labels, **kwargs: [
        {"labels": [label], "scores": [score]} for _ in texts
    ]
    return ai_instance


def test_worker_links_orphan_tags_and_persists_score(use_test_db, db_session, mock_registry):
    category = ArchiveMacroCategory(name="Urbanismo")
    db_session.add(category)
    db_session.commit()
    category_id = category.category_id

    tags = [ArchiveTag(name="pavimentação"), ArchiveTag(name="calçamento")]
    db_session.add_all(tags)
    db_session.commit()
    tag_ids = [tag.tag_id for tag in tags]

    _fake_engine(mock_registry, "Urbanismo", 0.90)

    execute(db=db_session, engine_name="motor_fake", preset="preset_teste")  # type: ignore

    for tag_id in tag_ids:
        tag = db_session.get(ArchiveTag, tag_id)
        assert tag.macro_category_id == category_id
        assert tag.ai_confidence_score == pytest.approx(0.90)
        assert tag.execution_log["worker_macro_category_v1"] == "DONE"


def test_worker_leaves_tag_orphan_on_low_confidence(use_test_db, db_session, mock_registry):
    """Below 40% the tag is not linked, but the score is kept and the tag stops being reprocessed."""
    category = ArchiveMacroCategory(name="Urbanismo")
    db_session.add(category)
    db_session.commit()

    tag = ArchiveTag(name="termo ambíguo")
    db_session.add(tag)
    db_session.commit()
    tag_id = tag.tag_id

    _fake_engine(mock_registry, "Urbanismo", 0.30)

    execute(db=db_session, engine_name="motor_fake", preset="preset_teste")  # type: ignore

    updated = db_session.get(ArchiveTag, tag_id)
    assert updated.macro_category_id is None
    assert updated.ai_confidence_score == pytest.approx(0.30)
    assert updated.execution_log["worker_macro_category_v1"] == "DONE"


def test_worker_exits_gracefully_without_categories(db_session, mock_registry):
    db_session.add(ArchiveTag(name="órfã"))
    db_session.commit()

    ai_instance = _fake_engine(mock_registry, "Urbanismo", 0.90)

    execute(db=db_session, engine_name="motor_fake", preset="preset_teste")  # type: ignore

    ai_instance.classify.assert_not_called()


def test_worker_skips_stamped_orphan_until_forced(use_test_db, db_session, mock_registry):
    """The idempotency stamp keeps low-confidence orphans out, and ``force`` brings them back."""
    category = ArchiveMacroCategory(name="Urbanismo")
    db_session.add(category)
    db_session.commit()
    category_id = category.category_id

    tag = ArchiveTag(name="ambíguo", execution_log={"worker_macro_category_v1": "DONE"})
    db_session.add(tag)
    db_session.commit()
    tag_id = tag.tag_id

    ai_instance = _fake_engine(mock_registry, "Urbanismo", 0.90)

    execute(db=db_session, engine_name="motor_fake", preset="preset_teste")  # type: ignore
    ai_instance.classify.assert_not_called()

    execute(db=db_session, engine_name="motor_fake", preset="preset_teste", force=True)  # type: ignore
    ai_instance.classify.assert_called_once()

    assert db_session.get(ArchiveTag, tag_id).macro_category_id == category_id


def test_worker_never_touches_already_categorized_tags(use_test_db, db_session, mock_registry):
    category = ArchiveMacroCategory(name="Urbanismo")
    db_session.add(category)
    db_session.commit()

    tag = ArchiveTag(name="pavimentação", macro_category_id=category.category_id)
    db_session.add(tag)
    db_session.commit()

    ai_instance = _fake_engine(mock_registry, "Urbanismo", 0.90)

    execute(db=db_session, engine_name="motor_fake", preset="preset_teste", force=True)  # type: ignore

    ai_instance.classify.assert_not_called()


def test_worker_respects_the_batch_size(use_test_db, db_session, mock_registry):
    category = ArchiveMacroCategory(name="Urbanismo")
    db_session.add(category)
    db_session.commit()

    db_session.add_all([ArchiveTag(name=f"tag {i}") for i in range(3)])
    db_session.commit()

    ai_instance = _fake_engine(mock_registry, "Urbanismo", 0.90)

    execute(db=db_session, engine_name="motor_fake", preset="preset_teste", db_batch_size=2)  # type: ignore

    # 3 tags with a batch of 2 mean two round trips to the AI, and the cursor keeps them distinct.
    assert ai_instance.classify.call_count == 2
