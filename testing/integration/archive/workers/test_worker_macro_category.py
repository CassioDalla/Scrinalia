import pytest

from memoria_curitibana.domains.archive.domain.vocabulary import label_set_fingerprint
from memoria_curitibana.domains.archive.engines.classification import registry as typology_registry
from memoria_curitibana.domains.archive.models import ArchiveMacroCategory, ArchiveTag
from memoria_curitibana.domains.archive.workers.worker_macro_category import execute


def _fingerprint(*categories) -> str:
    """
    The stamp value the worker writes for a given vocabulary.

    Keyed by the **resolved label** (``classifier_label`` when the curator wrote one, the
    bare name otherwise), because that is what the model reasons about — and therefore what
    the stamp has to identify. The names and ids are read eagerly: the worker calls
    ``expunge_all()``, so the ORM instances are detached by the time a test inspects them.
    """
    return label_set_fingerprint(
        {(category.classifier_label or category.name): category.category_id for category in categories}
    )


def _stamp_of(db_session, tag_id: int) -> str:
    """The fingerprint recorded on a tag, read back from the database."""
    tag = db_session.get(ArchiveTag, tag_id)
    return tag.execution_log["worker_macro_category_v1"]


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

    expected = _fingerprint(category)

    _fake_engine(mock_registry, "Urbanismo", 0.90)

    execute(db=db_session, engine_name="motor_fake", preset="preset_teste")  # type: ignore

    for tag_id in tag_ids:
        tag = db_session.get(ArchiveTag, tag_id)
        assert tag.macro_category_id == category_id
        assert tag.ai_confidence_score == pytest.approx(0.90)
        # The stamp is the identity of the vocabulary, not a status: this is what lets a
        # label rewrite re-queue the tag later.
        assert tag.execution_log["worker_macro_category_v1"] == expected


def test_worker_leaves_tag_orphan_on_low_confidence(use_test_db, db_session, mock_registry):
    """Below 40% the tag is not linked, but the score is kept and the tag stops being reprocessed."""
    category = ArchiveMacroCategory(name="Urbanismo")
    db_session.add(category)
    db_session.commit()

    tag = ArchiveTag(name="termo ambíguo")
    db_session.add(tag)
    db_session.commit()
    tag_id = tag.tag_id

    expected = _fingerprint(category)

    _fake_engine(mock_registry, "Urbanismo", 0.30)

    execute(db=db_session, engine_name="motor_fake", preset="preset_teste")  # type: ignore

    updated = db_session.get(ArchiveTag, tag_id)
    assert updated.macro_category_id is None
    assert updated.ai_confidence_score == pytest.approx(0.30)
    assert updated.execution_log["worker_macro_category_v1"] == expected


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

    # Stamped with the *current* vocabulary: this tag is settled.
    tag = ArchiveTag(name="ambíguo", execution_log={"worker_macro_category_v1": _fingerprint(category)})
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


def test_worker_sends_bare_category_names_to_the_engine(use_test_db, db_session, mock_registry):
    """
    Regression guard: the candidate labels reaching the engine must be bare names.

    A ``"Name: description"`` label makes mDeBERTa collapse every tag onto one category
    with high confidence, so this asserts the exact payload the engine receives.
    """
    db_session.add(ArchiveMacroCategory(name="Urbanismo", description="Obras, vias e mobilidade urbana"))
    db_session.add(ArchiveMacroCategory(name="Saúde", description="Epidemias, hospitais e saneamento"))
    db_session.add(ArchiveTag(name="pavimentação"))
    db_session.commit()

    MockClass = mock_registry(typology_registry)
    ai_instance = MockClass.return_value
    ai_instance.classify.return_value = [{"labels": ["Urbanismo"], "scores": [0.90]}]

    execute(db=db_session, engine_name="motor_fake", preset="preset_teste")  # type: ignore

    args, kwargs = ai_instance.classify.call_args
    _texts, candidate_labels = args
    assert candidate_labels == ["Urbanismo", "Saúde"]
    assert all(":" not in label for label in candidate_labels)
    assert all("Obras" not in label and "Epidemias" not in label for label in candidate_labels)
    assert kwargs["batch_size"] == 1


def test_worker_links_correct_category_when_description_is_filled(use_test_db, db_session, mock_registry):
    """A filled description must not change which label the engine is asked about."""
    db_session.add(ArchiveMacroCategory(name="Urbanismo", description="Obras e vias"))
    health = ArchiveMacroCategory(name="Saúde", description="Epidemias e hospitais")
    db_session.add(health)
    db_session.add(ArchiveTag(name="epidemia de dengue"))
    db_session.commit()
    health_id = health.category_id

    # The engine answers with the bare name, which is what it now receives.
    MockClass = mock_registry(typology_registry)
    ai_instance = MockClass.return_value
    ai_instance.classify.side_effect = lambda texts, candidate_labels, **kwargs: [
        {"labels": [candidate_labels[1]], "scores": [0.99]} for _ in texts
    ]

    execute(db=db_session, engine_name="motor_fake", preset="preset_teste")  # type: ignore

    tag = db_session.query(ArchiveTag).filter_by(name="epidemia de dengue").one()
    assert tag.macro_category_id == health_id


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


# ==========================================
# RE-QUEUE BY LABEL CHANGE (the defect the V3 migration exposed)
# ==========================================


def test_rewriting_a_label_requeues_the_stamped_tags(use_test_db, db_session, mock_registry):
    """
    The correction has to reach the collection, which a status stamp could never do.

    Measured failure this pins: the V3 migration retired a drawer while its tags kept
    ``worker_macro_category_v1: DONE``, so the worker considered them settled and the fix
    would never have been applied.
    """
    category = ArchiveMacroCategory(name="Urbanismo")
    db_session.add(category)
    db_session.commit()
    tag = ArchiveTag(name="alvenaria", execution_log={"worker_macro_category_v1": _fingerprint(category)})
    db_session.add(tag)
    db_session.commit()
    tag_id = tag.tag_id

    # The engine answers with whatever label it was asked about, like the real model does.
    MockClass = mock_registry(typology_registry)
    ai_instance = MockClass.return_value
    ai_instance.classify.side_effect = lambda texts, candidate_labels, **kwargs: [
        {"labels": [candidate_labels[0]], "scores": [0.90]} for _ in texts
    ]

    # Settled under the current vocabulary: nothing to do.
    execute(db=db_session, engine_name="motor_fake", preset="preset_teste")  # type: ignore
    ai_instance.classify.assert_not_called()

    # The curator writes the proposition the model should read.
    category_id = category.category_id
    category.classifier_label = "um assunto sobre obras, construção e desenho urbano"
    db_session.commit()

    execute(db=db_session, engine_name="motor_fake", preset="preset_teste")  # type: ignore

    # The engine is asked about the *proposition*, not the drawer name...
    args, _kwargs = ai_instance.classify.call_args
    assert args[1] == ["um assunto sobre obras, construção e desenho urbano"]
    # ...and the proposition still resolves back to the drawer it belongs to.
    assert db_session.get(ArchiveTag, tag_id).macro_category_id == category_id


def test_rewriting_a_label_back_to_the_same_value_does_not_requeue(use_test_db, db_session, mock_registry):
    """Idempotence: a no-op edit must not send the whole collection through the model again."""
    category = ArchiveMacroCategory(name="Urbanismo", classifier_label="um assunto sobre urbanismo")
    db_session.add(category)
    db_session.commit()
    db_session.add(ArchiveTag(name="alvenaria", execution_log={"worker_macro_category_v1": _fingerprint(category)}))
    db_session.commit()

    ai_instance = _fake_engine(mock_registry, "Urbanismo", 0.90)

    execute(db=db_session, engine_name="motor_fake", preset="preset_teste")  # type: ignore
    ai_instance.classify.assert_not_called()


def test_registering_a_new_drawer_requeues_the_orphans_only(use_test_db, db_session, mock_registry):
    """
    A new drawer can change the winner for a tag that scored below the threshold, so the
    stamped orphans come back while the already-linked tags stay out of the queue.
    """
    urbanism = ArchiveMacroCategory(name="Urbanismo")
    db_session.add(urbanism)
    db_session.commit()

    orphan = ArchiveTag(name="igrejas", execution_log={"worker_macro_category_v1": _fingerprint(urbanism)})
    linked = ArchiveTag(name="alvenaria", macro_category_id=urbanism.category_id)
    db_session.add_all([orphan, linked])
    db_session.commit()
    orphan_id = orphan.tag_id

    religion = ArchiveMacroCategory(name="Religião")
    db_session.add(religion)
    db_session.commit()
    religion_id = religion.category_id

    MockClass = mock_registry(typology_registry)
    ai_instance = MockClass.return_value
    ai_instance.classify.side_effect = lambda texts, candidate_labels, **kwargs: [
        {"labels": ["Religião"], "scores": [0.95]} for _ in texts
    ]

    execute(db=db_session, engine_name="motor_fake", preset="preset_teste")  # type: ignore

    ai_instance.classify.assert_called_once()
    assert db_session.get(ArchiveTag, orphan_id).macro_category_id == religion_id


# ==========================================
# NENHUMA AGAINST A REAL DATABASE
# ==========================================


def test_the_guard_keeps_non_subjects_out_on_a_real_database(use_test_db, db_session, mock_registry):
    """``1924``, a placeholder and a street are never sent to the model and never linked."""
    category = ArchiveMacroCategory(name="Urbanismo")
    db_session.add(category)
    db_session.commit()

    non_subjects = ["1924", "local não identificado", "rua xv de novembro", "303 anos"]
    db_session.add_all([ArchiveTag(name=name) for name in non_subjects])
    db_session.add(ArchiveTag(name="parque"))
    db_session.commit()
    non_subject_ids = [tag.tag_id for tag in db_session.query(ArchiveTag).filter(ArchiveTag.name.in_(non_subjects))]

    ai_instance = _fake_engine(mock_registry, "Urbanismo", 0.90)

    execute(db=db_session, engine_name="motor_fake", preset="preset_teste")  # type: ignore

    # Exactly one tag reached the engine — the real subject.
    args, _kwargs = ai_instance.classify.call_args
    assert args[0] == ["parque"]

    for tag_id in non_subject_ids:
        tag = db_session.get(ArchiveTag, tag_id)
        assert tag.macro_category_id is None
        assert tag.ai_confidence_score is None
        # Stamped, otherwise the batch would revisit them on every run.
        assert "worker_macro_category_v1" in tag.execution_log
