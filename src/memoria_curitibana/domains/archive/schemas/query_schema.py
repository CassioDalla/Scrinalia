from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from memoria_curitibana.domains.archive.models import ArchiveReviewStatus


class DocumentSearchQuery(BaseModel):
    """
    Read query of the collection search (showcase).

    Groups the free-text term and every facet in a single object, so the repository
    port does not grow one keyword argument per filter as the search evolves.
    Pagination travels with it because the page is part of the search itself.
    """

    term: str | None = Field(default=None, description="Free-text search term.")
    mode: Literal["lexical", "semantic"] = Field(
        default="lexical",
        description="lexical: full-text ranking. semantic: cosine similarity over the embeddings.",
    )
    typology_id: int | None = Field(default=None, description="Only documents classified with this typology.")
    macro_category_id: int | None = Field(
        default=None, description="Only documents having at least one tag of this macro category."
    )
    entity_type: str | None = Field(
        default=None, description="Only documents having at least one named entity of this type (LOC/PER/ORG)."
    )
    level_id: int | None = Field(
        default=None, description="Only descriptions at this level of the catalogue (Dossiê, Item...)."
    )
    ancestor_id: str | None = Field(
        default=None,
        description="Only descriptions inside this branch of the arrangement: 'search within this fonds'. "
        "It is the materialised path that answers it, in one indexed prefix match.",
    )
    date_from: date | None = Field(default=None, description="Inclusive lower bound on the document date.")
    date_to: date | None = Field(default=None, description="Inclusive upper bound on the document date.")
    #: Governance filters. They exist because the work list links straight into a filtered list
    #: ("the descriptions nobody reviewed", "the ones the validator flagged"), and a card promising
    #: a screen the search cannot produce would be a dead end.
    status: ArchiveReviewStatus | None = Field(default=None, description="Only descriptions in this review state.")
    is_anomaly: bool | None = Field(default=None, description="Only flagged, or only clean, descriptions.")
    anomaly_reason: str | None = Field(
        default=None,
        description="Only descriptions flagged for this reason, as the facet key names it: a bare code "
        "('NO_TAGS', 'LLM_SUSPECT') or a code with its payload when the payload is a catalogue entry "
        "('RULE_MATCH:nome da regra'). The free text of an LLM check is never a key.",
    )
    #: Diffusion gate, applied by the public surface and never exposed to it as a parameter: the
    #: public controller sets it to ``True`` server-side, so a client cannot ask to see unpublished
    #: records by flipping a query string. It is a *filter*, not a facet, so it constrains every
    #: facet count as well.
    published_only: bool = Field(default=False, description="Only descriptions cleared for diffusion.")
    limit: int = Field(default=50, ge=1, le=200, description="Page size.")
    offset: int = Field(default=0, ge=0, description="Number of records to skip.")
