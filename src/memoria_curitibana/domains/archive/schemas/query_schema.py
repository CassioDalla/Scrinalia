from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


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
    date_from: date | None = Field(default=None, description="Inclusive lower bound on the document date.")
    date_to: date | None = Field(default=None, description="Inclusive upper bound on the document date.")
    limit: int = Field(default=50, ge=1, le=200, description="Page size.")
    offset: int = Field(default=0, ge=0, description="Number of records to skip.")
