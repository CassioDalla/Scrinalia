from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class DocumentUpdateRequest(BaseModel):
    """
    Every ISAD(G) field the archivist may correct.

    The archivist fixes the whole record, not only the title. ``changed_by`` carries the
    authorship while authentication does not exist (phase 4); ``review_note`` explains the
    edit and stays in the audit trail.
    """

    original_title: str | None = Field(default=None, description="Título original corrigido.")
    final_title: str | None = Field(default=None, description="Título final revisado pelo arquivista.")
    document_date: date | None = Field(default=None, description="Data do documento corrigida.")

    reference_code: str | None = Field(default=None, description="Código de referência.")
    level: str | None = Field(default=None, description="Nível de descrição.")
    producers: str | None = Field(default=None, description="Produtor(es).")
    admin_bio_history: str | None = Field(default=None, description="História administrativa/biografia.")
    admin_archival_history: str | None = Field(default=None, description="História arquivística.")
    provenance: str | None = Field(default=None, description="Procedência.")
    scope_content: str | None = Field(default=None, description="Âmbito e conteúdo revisado.")
    language_name: str | None = Field(default=None, description="Idioma.")
    archivist_notes: str | None = Field(default=None, description="Notas do arquivista.")

    changed_by: str | None = Field(default=None, description="Quem revisou (autoria, enquanto não há autenticação).")
    review_note: str | None = Field(default=None, description="Motivo da edição; fica no histórico.")

    model_config = ConfigDict(extra="forbid")
