"""Contracts of the text-quality catalog (repeated excerpts the curation decided on)."""

from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator

from scrinalia.domains.archive.domain.text_quality import (
    AI_TEXT_COLUMNS,
    DEFAULT_TEMPLATE_SCOPE,
    normalize_excerpt,
)
from scrinalia.domains.archive.schemas.responses import RouteResponse

TemplateAction = Literal["IGNORE", "REPLACE"]
TemplateScope = Literal["EMBEDDING", "NER", "TITLE"]
TemplateSource = Literal["SUGGESTED", "HUMAN"]
TemplateStatus = Literal["SUGGESTED", "APPROVED", "REJECTED"]


class TextTemplateDTO(BaseModel):
    """One catalog row: an excerpt and what the AI text must do with it."""

    template_id: int
    text: str
    fingerprint: str
    variants: list[str] = Field(default_factory=list)
    action: TemplateAction = "IGNORE"
    replacement: str = ""
    scope: list[TemplateScope] = Field(
        default_factory=lambda: cast("list[TemplateScope]", list(DEFAULT_TEMPLATE_SCOPE))
    )
    reason: str | None = None
    source: TemplateSource = "HUMAN"
    status: TemplateStatus = "SUGGESTED"
    is_active: bool = True
    occurrence_count: int = 0
    sample_document_ids: list[str] = Field(default_factory=list)
    created_by: str | None = None

    model_config = ConfigDict(from_attributes=True)

    @property
    def matchers(self) -> list[str]:
        """Every spelling this row matches, canonical first and without duplicates."""
        seen: dict[str, None] = {}
        for candidate in (self.text, *self.variants):
            normalized = normalize_excerpt(candidate)
            if normalized:
                seen.setdefault(normalized, None)
        return list(seen)

    @property
    def applies(self) -> bool:
        """True when the excerpt must be applied to the AI text right now."""
        return self.status == "APPROVED" and self.is_active


class TemplateCreateCommand(BaseModel):
    """A curator writing an excerpt by hand (no suggestion involved)."""

    text: str
    action: TemplateAction = "IGNORE"
    replacement: str = ""
    scope: list[TemplateScope] = Field(
        default_factory=lambda: cast("list[TemplateScope]", list(DEFAULT_TEMPLATE_SCOPE))
    )
    reason: str | None = None
    variants: list[str] = Field(default_factory=list)
    created_by: str | None = None

    @field_validator("text")
    @classmethod
    def _text_not_blank(cls, value: str) -> str:
        if not normalize_excerpt(value):
            raise ValueError("text must not be blank")
        return value


class TemplateUpdateCommand(BaseModel):
    """Partial edit: approve, correct the replacement, deactivate or reject."""

    text: str | None = None
    action: TemplateAction | None = None
    replacement: str | None = None
    scope: list[TemplateScope] | None = None
    reason: str | None = None
    variants: list[str] | None = None
    status: TemplateStatus | None = None
    is_active: bool | None = None
    changed_by: str | None = None


class TemplateSuggestion(BaseModel):
    """A repeated excerpt found in the collection. Evidence only; nothing was written."""

    text: str
    variants: list[str] = Field(default_factory=list)
    scope: list[TemplateScope] = Field(
        default_factory=lambda: cast("list[TemplateScope]", list(DEFAULT_TEMPLATE_SCOPE))
    )
    occurrence_count: int
    sample_document_ids: list[str] = Field(default_factory=list)
    columns: list[str] = Field(default_factory=list)


class TemplateSuggestionResponse(RouteResponse):
    """Result of a suggestion run over the collection."""

    documents_scanned: int
    candidates: list[TemplateSuggestion]
    persisted: int


class TemplateDryRunRequest(BaseModel):
    """Simulates the impact of an excerpt before it is approved."""

    text: str
    action: TemplateAction = "IGNORE"
    replacement: str = ""
    scope: list[TemplateScope] = Field(
        default_factory=lambda: cast("list[TemplateScope]", list(DEFAULT_TEMPLATE_SCOPE))
    )
    variants: list[str] = Field(default_factory=list)
    sample_limit: int = 5


class TemplateDryRunMatch(BaseModel):
    """Before/after of one affected document, so the archivist sees what changes."""

    description_id: str
    column: str
    original_text: str
    modified_text: str


class TemplateDryRunResponse(BaseModel):
    """Impact report: how many documents change and a few examples."""

    documents_affected: int
    documents_scanned: int
    samples: list[TemplateDryRunMatch] = Field(default_factory=list)


class TextTemplateMutationResponse(RouteResponse):
    """
    Result of a write on the excerpt catalog.

    ``documents_requeued`` is the number the archivist needs to see: touching an excerpt puts the
    documents it affected back in the AI queue, because the composed text — and the MD5 stamped on
    the embedding — changed.
    """

    documents_requeued: int
    data: TextTemplateDTO


class TextTemplateApplicationConfig(BaseModel):
    """Immutable snapshot of the excerpts applied to the AI text during one run."""

    templates: list[TextTemplateDTO] = Field(default_factory=list)

    @property
    def active(self) -> list[TextTemplateDTO]:
        return [template for template in self.templates if template.applies]

    @property
    def columns(self) -> tuple[str, ...]:
        return AI_TEXT_COLUMNS
