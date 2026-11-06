from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from scrinalia.domains.archive.models import ArchiveReviewStatus

#: How a free-text search is ranked. Declared once and read by the query object and by the two
#: routes that expose it (the curator's and the public one), so a new mode is one edit and not
#: three copies that can drift apart.
SearchMode = Literal["lexical", "semantic", "hybrid"]


class DocumentSearchQuery(BaseModel):
    """
    Read query of the collection search (showcase).

    Groups the free-text term and every facet in a single object, so the repository
    port does not grow one keyword argument per filter as the search evolves.
    Pagination travels with it because the page is part of the search itself.
    """

    term: str | None = Field(default=None, description="Free-text search term.")
    mode: SearchMode = Field(
        default="lexical",
        description="lexical: full-text ranking. semantic: cosine similarity over the embeddings. "
        "hybrid: the two fused by reciprocal rank fusion.",
    )
    typology_id: int | None = Field(default=None, description="Only documents classified with this typology.")
    macro_category_id: int | None = Field(
        default=None, description="Only documents having at least one tag of this macro category."
    )
    entity_type: str | None = Field(
        default=None, description="Only documents having at least one named entity of this type (LOC/PER/ORG)."
    )
    entity_id: int | None = Field(
        default=None,
        description="Only documents carrying this named entity, by id. It is what answers 'which descriptions "
        "carry this name', the list an entity card expands into.",
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
    #: public controller names the channel server-side, so a client cannot ask to see a record the
    #: channel does not carry by flipping a query string. It is a *filter*, not a facet, so it
    #: constrains every facet count as well. ``None`` is the curator's read, which is not gated.
    publication_channel: str | None = Field(
        default=None, description="Only descriptions the coverage view carries on this channel."
    )
    limit: int = Field(default=50, ge=1, le=200, description="Page size.")
    offset: int = Field(default=0, ge=0, description="Number of records to skip.")

    @property
    def term_to_embed(self) -> str | None:
        """
        The term a semantic or fused ranking has to embed; ``None`` when nothing is embedded.

        One definition for the decision, because two consumers depend on it and they must not
        disagree: the service embeds on it, the measurement bench reads it, and a lexical
        request never pays for loading the model. A blank term embeds nothing, which is what
        keeps ``mode=semantic`` over an empty term browsing the collection instead of failing.
        """
        if self.mode == "lexical" or not self.term or not self.term.strip():
            return None
        return self.term
