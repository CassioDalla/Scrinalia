from scrinalia.domains.archive.models import ArchiveDocument, ArchiveTypology
from scrinalia.domains.archive.repository.typology_repo import TypologyRepository


def test_get_active_typologies_from_db(use_test_db, db_session):
    """Tests the real integration of the typology repository with the database."""
    repo = TypologyRepository(db_session)

    db_session.add_all(
        [
            ArchiveTypology(name="Carta", context_description="Correspondência oficial e pessoal."),
            ArchiveTypology(name="Memorando", context_description=None),
        ]
    )
    db_session.commit()

    results = repo.get_active_typologies()

    assert isinstance(results, dict)
    # Regression: the bare name is the candidate label. Appending the context made
    # mDeBERTa collapse every document onto a single typology.
    assert "Carta" in results
    assert "Memorando" in results
    assert results["Memorando"] > 0


def test_get_active_typologies_keeps_context_out_of_the_label(use_test_db, db_session):
    """
    The classifier reads bare names, never ``"Name: description"``.

    With the concatenated label the model progressively loses the entailment as the label
    grows, ending on a confident wrong answer — so a curator who fills the context would
    silently degrade classification. The context stays as documentation.
    """
    repo = TypologyRepository(db_session)
    db_session.add(
        ArchiveTypology(
            name="Planta",
            context_description="Projetos de expansão, construção e reforma de edificações.",
        )
    )
    db_session.commit()

    labels = list(repo.get_active_typologies().keys())

    assert labels == ["Planta"]
    assert all(":" not in label for label in labels)
    assert all("Projetos de expansão" not in label for label in labels)


def test_retiring_a_typology_takes_it_out_of_the_labels_and_keeps_the_description(use_test_db, db_session):
    """
    ``is_active`` is the only lever that reaches the classifier without touching a description.

    A retired typology stops being a candidate label — the model would otherwise keep proposing a
    spelling the curator decided against — while every description already classified with it keeps
    it, and the catalogue keeps showing its weight. That is why there is no delete.
    """
    repo = TypologyRepository(db_session)
    retired = ArchiveTypology(name="Dossiê Funcional", is_active=False)
    kept = ArchiveTypology(name="Fotografia")
    db_session.add_all([retired, kept])
    db_session.commit()

    db_session.add(
        ArchiveDocument(
            description_id="retired-1",
            original_title="Prontuário",
            staging_content_hash="h",
            typology_id=retired.typology_id,
        )
    )
    db_session.commit()

    assert repo.get_active_typologies() == {"Fotografia": kept.typology_id}
    assert [row.name for row in repo.list_typologies(only_active=True)] == ["Fotografia"]
    assert [row.name for row in repo.list_typologies()] == ["Dossiê Funcional", "Fotografia"]

    # The weight of the retired one is still visible, which is what makes retiring a trade.
    assert repo.document_counts() == {retired.typology_id: 1}
    retired_typology = repo.get(retired.typology_id)
    assert retired_typology is not None
    assert retired_typology.name == "Dossiê Funcional"
