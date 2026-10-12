import pytest
from sqlalchemy.exc import IntegrityError

from scrinalia.domains.archive.models import ArchiveEntity


def test_a_case_twin_entity_is_rejected(use_test_db, db_session):
    """
    The name's identity is the shape ``normalize_entity`` declares, and the schema enforces it.

    ``archive_entities.name`` was unique case-sensitively, so ``Batel`` and ``batel`` were two rows
    and ``get_or_create_entities`` — which inserts the lowercase spelling and looks the ids up with
    ``name IN (…lowercase…)`` — could never see the Title Case one. That is what put 3 523 twin
    groups in the reference collection. The unique index on ``lower(btrim(name))`` is what makes the
    second row impossible instead of merely unlikely.
    """
    db_session.add(ArchiveEntity(name="batel", entity_type="LOC"))
    db_session.commit()

    db_session.add(ArchiveEntity(name="Batel", entity_type="LOC"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
