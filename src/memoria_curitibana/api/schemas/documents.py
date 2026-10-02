from pydantic import BaseModel, ConfigDict, Field


class DocumentUpdateRequest(BaseModel):
    """Fields an archivist can review manually in a document."""

    final_title: str | None = Field(default=None, description="Final title reviewed by the archivist.")
    scope_content: str | None = Field(default=None, description="Reviewed scope and content.")
    archivist_notes: str | None = Field(default=None, description="Technical notes from the archivist.")

    model_config = ConfigDict(extra="forbid")
