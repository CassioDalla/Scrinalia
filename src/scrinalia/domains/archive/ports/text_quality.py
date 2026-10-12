from collections.abc import Iterator, Sequence
from typing import Protocol

from scrinalia.domains.archive.domain.text_quality import SuggestionCandidate
from scrinalia.domains.archive.repository.text_quality_repo import ExcerptRule
from scrinalia.domains.archive.schemas.text_quality_schema import (
    TemplateCreateCommand,
    TemplateDryRunResponse,
    TemplateUpdateCommand,
    TextTemplateDTO,
)


class TextQualityRepositoryPort(Protocol):
    """
    Output port for the repeated-excerpt catalog.

    The document scans are read-only by contract: the catalog never rewrites archival
    content, it only declares which excerpts the AI must not read.
    """

    def list_templates(self, status: str | None = None, only_active: bool = False) -> list[TextTemplateDTO]:
        raise NotImplementedError

    def get_template(self, template_id: int) -> TextTemplateDTO | None:
        raise NotImplementedError

    def get_active_templates(self) -> list[TextTemplateDTO]:
        raise NotImplementedError

    def get_active_rules(self, scope: str | None = None) -> list[ExcerptRule]:
        raise NotImplementedError

    def create_template(self, command: TemplateCreateCommand) -> TextTemplateDTO:
        raise NotImplementedError

    def upsert_suggestions(self, candidates: Sequence[SuggestionCandidate]) -> int:
        raise NotImplementedError

    def update_template(self, template_id: int, command: TemplateUpdateCommand) -> TextTemplateDTO | None:
        raise NotImplementedError

    def delete_template(self, template_id: int) -> TextTemplateDTO | None:
        raise NotImplementedError

    def refresh_occurrence_count(self, template_id: int, occurrence_count: int) -> TextTemplateDTO | None:
        raise NotImplementedError

    def iter_text_columns(self, columns: Sequence[str], batch_size: int = 500) -> Iterator[tuple[str, str, str | None]]:
        raise NotImplementedError

    def count_documents(self, columns: Sequence[str]) -> int:
        raise NotImplementedError

    def count_affected_documents(self, rules: Sequence[ExcerptRule], columns: Sequence[str]) -> int:
        raise NotImplementedError

    def dry_run(
        self, rules: Sequence[ExcerptRule], columns: Sequence[str], sample_limit: int = 5
    ) -> TemplateDryRunResponse:
        raise NotImplementedError

    def find_documents_with_excerpt(self, matchers: Sequence[str], columns: Sequence[str]) -> list[str]:
        raise NotImplementedError

    def requeue_documents(self, description_ids: Sequence[str], stamp_keys: Sequence[str]) -> int:
        raise NotImplementedError
