from pydantic import BaseModel, ConfigDict, Field


class DocumentUpdateRequest(BaseModel):
    """Campos que um arquivista pode revisar manualmente em um documento."""

    final_title: str | None = Field(default=None, description="Título definitivo revisado pelo arquivista.")
    scope_content: str | None = Field(default=None, description="Âmbito e conteúdo revisado.")
    archivist_notes: str | None = Field(default=None, description="Notas técnicas do arquivista.")

    model_config = ConfigDict(extra="forbid")
