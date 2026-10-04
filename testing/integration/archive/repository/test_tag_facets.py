"""
The non-subject axis against a real database (Fase 1.5, defeito 2/2 — entregável I4).

Two things are pinned here that unit tests cannot reach: the facet row really survives the
tag it belongs to (the ``ON DELETE CASCADE`` is a database property, not a Python one), and
the repository resolves the classifier labels from the column rather than from the name.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from memoria_curitibana.domains.archive.domain.vocabulary import label_set_fingerprint
from memoria_curitibana.domains.archive.models import (
    ArchiveMacroCategory,
    ArchiveTag,
    ArchiveTagFacet,
    TagFacetType,
)
from memoria_curitibana.domains.archive.repository.tag_repo import TagRepository


class TestFacetPersistence:
    """The facet is the third axis: not a subject, not noise."""

    def test_a_tag_can_carry_a_facet_without_a_subject(self, use_test_db, db_session):
        """``ippuc`` reaches 2.376 documents and is a producer, not a subject."""
        tag = ArchiveTag(name="ippuc")
        db_session.add(tag)
        db_session.flush()

        db_session.add(ArchiveTagFacet(tag_id=tag.tag_id, facet_type=TagFacetType.INSTITUTION.value, value="IPPUC"))
        db_session.commit()

        stored = db_session.execute(select(ArchiveTagFacet).where(ArchiveTagFacet.tag_id == tag.tag_id)).scalar_one()
        assert stored.value == "IPPUC"
        # The subject axis stays empty: that is the whole point of the separate table.
        assert db_session.get(ArchiveTag, tag.tag_id).macro_category_id is None

    def test_a_tag_can_be_a_place_and_an_institution_at_once(self, use_test_db, db_session):
        """
        The composite key exists for this: one drawer per subject, but two facets per tag.

        ``jardim botânico`` is a park *and* a bairro — the same term is a subject and a place,
        and a single ``facet_type`` column could not express both.
        """
        tag = ArchiveTag(name="jardim botânico")
        db_session.add(tag)
        db_session.flush()

        db_session.add_all(
            [
                ArchiveTagFacet(tag_id=tag.tag_id, facet_type=TagFacetType.PLACE.value, value="Jardim Botânico"),
                ArchiveTagFacet(
                    tag_id=tag.tag_id, facet_type=TagFacetType.INSTITUTION.value, value="Fundação Jardim Botânico"
                ),
            ]
        )
        db_session.commit()

        facets = db_session.execute(select(ArchiveTagFacet).where(ArchiveTagFacet.tag_id == tag.tag_id)).scalars().all()
        assert {facet.facet_type for facet in facets} == {"PLACE", "INSTITUTION"}

    def test_the_same_facet_type_cannot_repeat(self, use_test_db, db_session):
        """The composite primary key is the guard, not application code."""
        tag = ArchiveTag(name="curitiba")
        db_session.add(tag)
        db_session.flush()

        db_session.add(ArchiveTagFacet(tag_id=tag.tag_id, facet_type=TagFacetType.PLACE.value, value="Curitiba"))
        db_session.commit()

        db_session.add(ArchiveTagFacet(tag_id=tag.tag_id, facet_type=TagFacetType.PLACE.value, value="Curitiba antiga"))
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()

    def test_an_unknown_facet_type_is_rejected_by_the_database(self, use_test_db, db_session):
        """The CHECK constraint keeps a typo from creating a fourth axis silently."""
        tag = ArchiveTag(name="alvenaria")
        db_session.add(tag)
        db_session.flush()

        db_session.add(ArchiveTagFacet(tag_id=tag.tag_id, facet_type="SUBJECT", value="x"))
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()

    def test_deleting_the_tag_takes_its_facets_with_it(self, use_test_db, db_session):
        """``ON DELETE CASCADE``: the cascade is a database property, so it is tested here."""
        tag = ArchiveTag(name="pmc")
        db_session.add(tag)
        db_session.flush()
        tag_id = tag.tag_id
        db_session.add(ArchiveTagFacet(tag_id=tag_id, facet_type=TagFacetType.INSTITUTION.value, value="PMC"))
        db_session.commit()

        db_session.delete(db_session.get(ArchiveTag, tag_id))
        db_session.commit()

        remaining = db_session.execute(select(ArchiveTagFacet).where(ArchiveTagFacet.tag_id == tag_id)).scalars().all()
        assert remaining == []


class TestClassifierLabelsFromTheRepository:
    """The repository is where the label the model reads is resolved."""

    def test_a_written_label_is_what_the_engine_receives(self, use_test_db, db_session):
        """``classifier_label`` is the proposition; the description is never the label."""
        db_session.add(
            ArchiveMacroCategory(
                name="Urbanismo e Arquitetura",
                description="Documentação para o curador, nunca enviada ao modelo.",
                classifier_label="um assunto sobre obras, construção e desenho urbano",
            )
        )
        db_session.commit()

        mapping = TagRepository(db_session).get_active_macro_categories()

        assert list(mapping) == ["um assunto sobre obras, construção e desenho urbano"]
        assert "Documentação" not in str(mapping)

    def test_without_a_label_the_bare_name_is_used(self, use_test_db, db_session):
        """``NULL`` falls back to the name, so the column changes nothing until written."""
        db_session.add(ArchiveMacroCategory(name="Religião", classifier_label=None))
        db_session.commit()

        assert list(TagRepository(db_session).get_active_macro_categories()) == ["Religião"]

    def test_the_fingerprint_matches_what_the_worker_will_stamp(self, use_test_db, db_session):
        """
        The repository and the worker must agree on the identity of the vocabulary.

        If they disagreed, every run would consider the collection pending — a re-queue loop
        instead of a one-off correction, and the kind of defect that only shows up in
        production.
        """
        category = ArchiveMacroCategory(
            name="Religião", classifier_label="um assunto sobre igrejas e prática religiosa"
        )
        db_session.add(category)
        db_session.commit()

        mapping = TagRepository(db_session).get_active_macro_categories()
        assert label_set_fingerprint(mapping) == label_set_fingerprint(
            {"um assunto sobre igrejas e prática religiosa": category.category_id}
        )

    def test_a_retired_drawer_leaves_the_map(self, use_test_db, db_session):
        """``is_active`` is the switch the V3 migration used to retire ``Instituição``."""
        db_session.add(ArchiveMacroCategory(name="Religião", is_active=True))
        db_session.add(ArchiveMacroCategory(name="Instituição", is_active=False))
        db_session.commit()

        assert list(TagRepository(db_session).get_active_macro_categories()) == ["Religião"]

    def test_the_service_clears_a_blank_label_back_to_null(self, use_test_db, db_session):
        """
        A blank label must become ``NULL`` instead of ``""``.

        An empty string would be sent to the model as an empty hypothesis, which is worse than
        the drawer name it replaced — the entailment would have nothing to reason about.
        """
        from memoria_curitibana.domains.archive.schemas.command_schema import UpdateMacroCategoryCommand
        from memoria_curitibana.domains.archive.services.tag_service import TagService

        category = ArchiveMacroCategory(name="Religião", classifier_label="um assunto sobre religião")
        db_session.add(category)
        db_session.commit()
        category_id = category.category_id

        service = TagService(TagRepository(db_session), None)  # type: ignore[arg-type]
        service.update_macro_category(category_id, UpdateMacroCategoryCommand(classifier_label="   "))
        db_session.commit()

        stored = db_session.get(ArchiveMacroCategory, category_id)
        assert stored.classifier_label is None
        # And the model goes back to reading the name.
        assert list(TagRepository(db_session).get_active_macro_categories()) == ["Religião"]
