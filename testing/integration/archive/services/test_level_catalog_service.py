"""The level catalogue's use cases against the real database."""

import pytest

from memoria_curitibana.domains.archive.exceptions import (
    DescriptionLevelNotFoundError,
    DuplicateDescriptionLevelError,
    InvalidDescriptionLevelError,
)
from memoria_curitibana.domains.archive.repository.level_catalog_repo import LevelCatalogRepository
from memoria_curitibana.domains.archive.schemas.hierarchy_schema import (
    CreateDescriptionLevelCommand,
    UpdateDescriptionLevelCommand,
)
from memoria_curitibana.domains.archive.services.level_catalog_service import LevelCatalogService


def _service(db_session) -> LevelCatalogService:
    return LevelCatalogService(LevelCatalogRepository(db_session))


def test_the_ladder_lists_in_ordinal_order_with_the_document_count(
    db_session, generate_archive_doc, generate_description_level
):
    item = generate_description_level(ordinal=5, code="item", name="Item Documental")
    generate_description_level(ordinal=1, code="fundo", name="Fundo", requires_parent=False, allows_children=True)
    generate_archive_doc(description_id="d1", level_id=item.level_id)
    generate_archive_doc(description_id="d2", level_id=item.level_id)

    levels = _service(db_session).list_levels()

    assert [level.ordinal for level in levels] == [1, 5]
    assert [level.document_count for level in levels] == [0, 2]


def test_only_active_filters_deactivated_rungs(db_session, generate_description_level):
    generate_description_level(ordinal=3, code="serie", name="Série", is_active=False)
    generate_description_level(ordinal=5, code="item", name="Item Documental")

    assert [level.code for level in _service(db_session).list_levels(only_active=True)] == ["item"]


def test_a_taken_ordinal_is_a_named_conflict(db_session, generate_description_level):
    generate_description_level(ordinal=3, code="serie", name="Série")
    with pytest.raises(DuplicateDescriptionLevelError):
        _service(db_session).create_level(CreateDescriptionLevelCommand(ordinal=3, code="subserie", name="Subsérie"))


def test_a_taken_code_is_a_named_conflict(db_session, generate_description_level):
    generate_description_level(ordinal=3, code="serie", name="Série")
    with pytest.raises(DuplicateDescriptionLevelError):
        _service(db_session).create_level(CreateDescriptionLevelCommand(ordinal=4, code="serie", name="Outra Série"))


def test_a_taken_name_is_a_named_conflict_and_the_case_does_not_matter(db_session, generate_description_level):
    generate_description_level(ordinal=3, code="serie", name="Série")
    with pytest.raises(DuplicateDescriptionLevelError):
        _service(db_session).create_level(CreateDescriptionLevelCommand(ordinal=4, code="subserie", name="  SÉRIE "))


def test_creating_a_rung_returns_it_with_its_id(db_session):
    created = _service(db_session).create_level(CreateDescriptionLevelCommand(ordinal=2, code="secao", name="Seção"))
    assert created.level_id is not None
    assert created.code == "secao"
    assert created.document_count == 0


def test_updating_a_rung_keeps_the_ordinal_out_of_reach(db_session, generate_description_level):
    level = generate_description_level(ordinal=3, code="serie", name="Série")
    updated = _service(db_session).update_level(
        level.level_id, UpdateDescriptionLevelCommand(name="Série Fotográfica", aliases=["Serie"])
    )
    assert updated.name == "Série Fotográfica"
    assert updated.ordinal == 3
    assert updated.aliases == ["Serie"]


def test_renaming_onto_another_rung_is_refused(db_session, generate_description_level):
    generate_description_level(ordinal=3, code="serie", name="Série")
    other = generate_description_level(ordinal=4, code="dossie", name="Dossiê/Processo")
    with pytest.raises(DuplicateDescriptionLevelError):
        _service(db_session).update_level(other.level_id, UpdateDescriptionLevelCommand(name="Série"))


def test_deactivating_is_not_deleting(db_session, generate_description_level):
    """
    The FK is ``SET NULL``, so deleting a rung would unclassify descriptions while destroying the
    record that the rung existed. Deactivating is the operation the catalogue offers.
    """
    level = generate_description_level(ordinal=3, code="serie", name="Série")
    updated = _service(db_session).update_level(level.level_id, UpdateDescriptionLevelCommand(is_active=False))
    assert updated.is_active is False
    assert _service(db_session).get_level(level.level_id).code == "serie"


def test_an_unknown_rung_is_a_not_found(db_session):
    with pytest.raises(DescriptionLevelNotFoundError):
        _service(db_session).get_level(99999)


class TestTheAsymmetryBetweenTheLoadAndTheArchivist:
    """
    ``resolve`` returns ``None`` for an unknown spelling; ``require`` raises.

    The difference is the whole governance rule: a source typo must not stop a transfer, but an
    archivist choosing a rung is making a claim the catalogue has to be able to answer.
    """

    def test_resolve_answers_none_instead_of_guessing(self, db_session, seed_nobrade_levels):
        seed_nobrade_levels()
        service = _service(db_session)
        assert service.resolve("Nível Inventado") is None
        # The alias of the norm and the spelling of the source fold onto the same rung.
        assert service.resolve("Dossiê ou processo") == service.resolve("Dossiê/Processo")
        assert service.resolve("Dossiê/Processo") is not None

    def test_require_refuses_the_unknown_spelling(self, db_session, seed_nobrade_levels):
        seed_nobrade_levels()
        with pytest.raises(InvalidDescriptionLevelError):
            _service(db_session).require("Nível Inventado")
