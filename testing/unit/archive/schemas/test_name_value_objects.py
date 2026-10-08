from scrinalia.domains.archive.schemas.command_schema import SynonymCommand
from scrinalia.domains.archive.schemas.entity_schema import ArchiveEntityDTO
from scrinalia.domains.archive.schemas.tag_schema import ArchiveTagDTO


def test_tag_name_is_normalized_on_construction() -> None:
    tag = ArchiveTagDTO(name="  Urbanismo ", macro_category_id=None, ai_confidence_score=None)
    assert tag.name == "urbanismo"


def test_entity_name_is_normalized_on_construction() -> None:
    entity = ArchiveEntityDTO(name="  Prefeitura de Curitiba ", entity_type="ORG")
    assert entity.name == "prefeitura de curitiba"


def test_synonym_name_is_normalized_on_construction() -> None:
    command = SynonymCommand(synonym_name="  PMC ", category="ORG", canonical_entity_id=1)
    assert command.synonym_name == "pmc"
