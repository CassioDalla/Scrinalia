from memoria_curitibana.domains.archive.models import ArchiveTypology
from memoria_curitibana.domains.archive.repository.typology_repo import TypologyRepository


def test_get_active_typologies_from_db(use_test_db, db_session):
    """Tests the real integration of the typology repository with the database."""
    repo = TypologyRepository(db_session)

    # Insertion of simulated data into PostgreSQL/SQLite
    db_session.add_all(
        [
            ArchiveTypology(name="Carta", context_description="Correspondência oficial e pessoal."),
            ArchiveTypology(name="Memorando", context_description=None),
        ]
    )
    db_session.commit()

    # Run the method
    results = repo.get_active_typologies()

    # Guarantees that the data came formatted directly from the database
    assert isinstance(results, dict)
    assert "Carta: Correspondência oficial e pessoal." in results
    assert "Memorando" in results

    # Checks the IDs (assuming auto-increment 1 and 2 in the clean database)
    assert results["Memorando"] > 0
