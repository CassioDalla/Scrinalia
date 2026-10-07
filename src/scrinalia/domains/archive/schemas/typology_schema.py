"""Catalogue of documental typologies (the diplomatic form of a record)."""

from pydantic import BaseModel, ConfigDict, Field


class TypologyDTO(BaseModel):
    """One typology of the catalogue."""

    typology_id: int
    name: str
    #: Documentation *for the curator*, consumed by nothing: appending it to the zero-shot label
    #: makes the classifier lose the entailment and collapse the collection onto one typology.
    context_description: str | None = None
    is_active: bool
    #: How many descriptions carry this typology. Derived on read; the catalogue never deletes a
    #: typology precisely because this number is what makes "deactivate instead" a real choice.
    document_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class CreateTypologyCommand(BaseModel):
    """Registers a typology. The classifier reads the name as its candidate label."""

    name: str = Field(min_length=1, max_length=100, description="What the archivist sees and the classifier labels.")
    context_description: str | None = Field(
        default=None,
        description="Documentation for the curator; never sent to the model.",
    )


class UpdateTypologyCommand(BaseModel):
    """Partial update of a typology. Renaming it does not touch a single classified description."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    context_description: str | None = None
    is_active: bool | None = None
