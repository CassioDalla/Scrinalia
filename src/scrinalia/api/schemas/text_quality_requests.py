from pydantic import BaseModel, ConfigDict, Field

from scrinalia.domains.archive.schemas.text_quality_schema import (
    TemplateAction,
    TemplateScope,
    TemplateStatus,
)


class CreateTextTemplateRequest(BaseModel):
    """An excerpt the archivist writes by hand."""

    text: str = Field(min_length=1, description="Trecho repetido que a IA não deve mais ler.")
    action: TemplateAction = "IGNORE"
    replacement: str = Field(default="", description="Texto que substitui o trecho quando action=REPLACE.")
    scope: list[TemplateScope] = Field(
        default_factory=lambda: ["EMBEDDING", "NER"],
        description="Quem deixa de ler o trecho: EMBEDDING (vetor), NER (extração/classificação) e TITLE (título sugerido).",
    )
    reason: str | None = None
    variants: list[str] = Field(default_factory=list, description="Outras grafias do mesmo trecho.")
    changed_by: str | None = Field(default=None, description="Quem decidiu (autoria, enquanto não há autenticação).")

    model_config = ConfigDict(extra="forbid")


class UpdateTextTemplateRequest(BaseModel):
    """Partial edit: approve, correct, deactivate or reject a catalog row."""

    text: str | None = None
    action: TemplateAction | None = None
    replacement: str | None = None
    scope: list[TemplateScope] | None = None
    reason: str | None = None
    variants: list[str] | None = None
    status: TemplateStatus | None = None
    is_active: bool | None = None
    changed_by: str | None = None

    model_config = ConfigDict(extra="forbid")


class SuggestTextTemplatesRequest(BaseModel):
    """Parameters of the frequency scan; all optional."""

    min_ratio: float = Field(default=0.05, gt=0, le=1, description="Fração mínima do acervo para virar candidato.")
    min_documents: int = Field(default=5, ge=2, description="Piso absoluto de documentos repetidos.")


class DryRunTextTemplateRequest(BaseModel):
    """Simulates an excerpt before approving it."""

    text: str = Field(min_length=1)
    action: TemplateAction = "IGNORE"
    replacement: str = ""
    scope: list[TemplateScope] = Field(default_factory=lambda: ["EMBEDDING", "NER"])
    variants: list[str] = Field(default_factory=list)
    sample_limit: int = Field(default=5, ge=1, le=50)

    model_config = ConfigDict(extra="forbid")
