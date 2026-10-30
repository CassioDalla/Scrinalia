"""The HTTP envelope of the diffusion surface.

The projection itself — the allowlist of fields a channel may show — is a domain object, in
``domains/archive/schemas/public_projection.py``. It lives there so the open dataset (#214) exports
the same records without the domain importing the API layer. This module keeps only the page
envelope the public list route returns.
"""

from pydantic import BaseModel, Field

from scrinalia.domains.archive.schemas.public_projection import PublicDocumentFacets, PublicDocumentSummary


class PublicDocumentListResponse(BaseModel):
    """Page of the diffusion surface, with the facet envelope the diffusion is allowed to show."""

    total: int
    limit: int
    offset: int
    items: list[PublicDocumentSummary]
    facets: PublicDocumentFacets = Field(default_factory=PublicDocumentFacets)
