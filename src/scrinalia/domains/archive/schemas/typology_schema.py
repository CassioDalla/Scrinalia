"""Catalogue of documental typologies (the diplomatic form of a record)."""

from datetime import date

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


class TypologyRefusalRow(BaseModel):
    """
    One description the classifier refused, with the evidence that explains the decision.

    Deliberately not ``DocumentSummary``: the queue read needs the label the run guessed and the
    score it saw, and a summary would carry every ISAD(G) field of the record for a list whose only
    question is "which typology does this one get?". The title comes from the document, not from the
    queue's ``context_payload`` snapshot, so a rename is what the archivist reads.
    """

    description_id: str
    original_title: str
    final_title: str | None = None
    document_date: date | None = None
    reference_code: str | None = None
    #: The candidate label the run scored highest before refusing; ``None`` for a legacy row that
    #: did not carry one.
    guessed_label: str | None = None
    #: The score the run saw, kept in the queue because ``typology_id`` cannot say whether a run
    #: declined or never reached the description.
    ai_confidence_score: float | None = None


class TypologyRefusalListResponse(BaseModel):
    """One page of the refusal queue, with the total for the same predicate."""

    total: int = 0
    limit: int = 20
    offset: int = 0
    items: list[TypologyRefusalRow] = Field(default_factory=list)


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
