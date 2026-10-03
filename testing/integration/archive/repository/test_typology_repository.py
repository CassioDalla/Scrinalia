from memoria_curitibana.domains.archive.models import ArchiveTypology
from memoria_curitibana.domains.archive.repository.typology_repo import TypologyRepository


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
