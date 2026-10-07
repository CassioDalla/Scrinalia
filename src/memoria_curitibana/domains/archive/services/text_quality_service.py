"""
Use cases of the repeated-excerpt catalog (Fase 3.5-A).

The service never rewrites archival content: it proposes excerpts, records the human
decision and invalidates the derived work that the decision changes. The documents that
must be redone are found by the excerpt they contain — the same SQL normalization the
composition uses, so "affected" means affected for real.
"""

import math

from memoria_curitibana.core.logger import logger
from memoria_curitibana.domains.archive.domain.text_quality import (
    AI_TEXT_COLUMNS,
    ExcerptSuggestionAggregator,
    normalize_excerpt,
)
from memoria_curitibana.domains.archive.exceptions import InvalidParam, TextTemplateNotFoundError
from memoria_curitibana.domains.archive.ports.text_quality import TextQualityRepositoryPort
from memoria_curitibana.domains.archive.repository.text_quality_repo import ExcerptRule
from memoria_curitibana.domains.archive.schemas.responses import RouteMessageCode
from memoria_curitibana.domains.archive.schemas.text_quality_schema import (
    TemplateCreateCommand,
    TemplateDryRunRequest,
    TemplateDryRunResponse,
    TemplateSuggestion,
    TemplateSuggestionResponse,
    TemplateUpdateCommand,
    TextTemplateDTO,
)
from memoria_curitibana.domains.archive.worker_stamp import TEXT_DEPENDENT_STAMPS


class TextQualityService:
    """Curation of the text the AI reads, with the archivist as the only decision maker."""

    def __init__(self, repo: TextQualityRepositoryPort) -> None:
        self.repo = repo

    # ==========================================
    # CATALOG
    # ==========================================

    def list_templates(self, status: str | None = None, only_active: bool = False) -> list[TextTemplateDTO]:
        return self.repo.list_templates(status=status, only_active=only_active)

    def create_template(self, command: TemplateCreateCommand) -> tuple[TextTemplateDTO, int]:
        """
        Registers an excerpt written by hand.

        A human-authored excerpt is applied immediately, so the documents it touches are
        re-queued for the workers that read the text.
        """
        template = self.repo.create_template(command)
        refreshed = self._refresh_evidence(template)
        requeued = self._requeue_documents(refreshed)
        logger.info(f"🏷️ Text template {refreshed.template_id} created; {requeued} document(s) re-queued.")
        return refreshed, requeued

    def update_template(self, template_id: int, command: TemplateUpdateCommand) -> tuple[TextTemplateDTO, int]:
        """Applies a partial edit and re-queues what the new decision changes."""
        previous = self.repo.get_template(template_id)
        if previous is None:
            raise TextTemplateNotFoundError(f"Trecho {template_id} não encontrado no catálogo.")

        updated = self.repo.update_template(template_id, command)
        if updated is None:
            raise TextTemplateNotFoundError(f"Trecho {template_id} não encontrado no catálogo.")

        refreshed = self._refresh_evidence(updated)
        if not self._changes_effect(previous, refreshed):
            return refreshed, 0

        # Documents that no longer match must lose the effect, and documents that now match
        # must gain it: both are found by the union of the old and the new spellings.
        requeued = self.repo.requeue_documents(
            self.repo.find_documents_with_excerpt(
                list(dict.fromkeys([*previous.matchers, *refreshed.matchers])), list(AI_TEXT_COLUMNS)
            ),
            [stamp.key for stamp in TEXT_DEPENDENT_STAMPS],
        )
        logger.info(f"🏷️ Text template {refreshed.template_id} updated; {requeued} document(s) re-queued.")
        return refreshed, requeued

    def delete_template(self, template_id: int) -> tuple[TextTemplateDTO, int]:
        """
        Undoes the decision and purges its retroactive effect.

        Removing the excerpt from the AI text is not enough: the workers already ran with
        it, so their stamps are cleared on every document that matched. The embedding is
        not touched here — its stamp is the hash of the effective text and it re-queues on
        its own.
        """
        removed = self.repo.delete_template(template_id)
        if removed is None:
            raise TextTemplateNotFoundError(f"Trecho {template_id} não encontrado no catálogo.")

        requeued = self.repo.requeue_documents(
            self.repo.find_documents_with_excerpt(removed.matchers, list(AI_TEXT_COLUMNS)),
            [stamp.key for stamp in TEXT_DEPENDENT_STAMPS],
        )
        logger.info(f"🏷️ Text template {template_id} removed; {requeued} document(s) re-queued.")
        return removed, requeued

    # ==========================================
    # SUGGESTION AND DRY-RUN
    # ==========================================

    def suggest_templates(
        self,
        min_ratio: float = 0.05,
        min_documents: int = 5,
        columns: tuple[str, ...] = AI_TEXT_COLUMNS,
        batch_size: int = 500,
    ) -> TemplateSuggestionResponse:
        """
        Points at repeated excerpts without applying anything.

        The floor is relative to the collection: a 5% default finds the boilerplate that
        matters without proposing every coincidence of two documents. Whatever comes out
        is written as an **inactive suggestion**, so nothing reaches the AI before a human
        approves it.
        """
        if not 0 < min_ratio <= 1:
            raise InvalidParam("O parâmetro 'min_ratio' deve estar entre 0 e 1.")

        documents = self.repo.count_documents(list(columns))
        min_count = max(min_documents, math.ceil(min_ratio * documents))

        aggregator = ExcerptSuggestionAggregator()
        for description_id, column, value in self.repo.iter_text_columns(list(columns), batch_size=batch_size):
            if value:
                aggregator.observe(description_id, column, value)

        candidates = aggregator.candidates(min_count=min_count)
        persisted = self.repo.upsert_suggestions(candidates)

        logger.info(f"🔎 Suggestion run: {documents} documents scanned, {len(candidates)} candidates.")

        return TemplateSuggestionResponse(
            documents_scanned=documents,
            candidates=[
                TemplateSuggestion(
                    text=candidate.text,
                    variants=candidate.variants,
                    scope=candidate.scope,  # type: ignore[arg-type]
                    occurrence_count=candidate.occurrence_count,
                    sample_document_ids=candidate.sample_document_ids,
                    columns=candidate.columns,
                )
                for candidate in candidates
            ],
            persisted=persisted,
            code=RouteMessageCode.TEXT_TEMPLATE_SUGGESTED,
            message=(
                f"{len(candidates)} trecho(s) repetido(s) encontrado(s) em {documents} documento(s). "
                "Nada foi aplicado: aprove, edite ou rejeite cada candidato."
            ),
        )

    def dry_run(self, request: TemplateDryRunRequest) -> TemplateDryRunResponse:
        """Shows the impact of an excerpt on the text the chosen consumers read."""
        rule = self._rule_from(request.text, request.variants, request.action, request.replacement)
        if not rule.matchers:
            raise InvalidParam("O trecho não pode ser vazio.")

        return self.repo.dry_run(
            [rule], self._columns_for_scope(list(request.scope)), sample_limit=request.sample_limit
        )

    # ==========================================
    # INTERNALS
    # ==========================================

    @staticmethod
    def _columns_for_scope(scope: list[str]) -> list[str]:
        """
        Which columns the requested consumers read.

        A title-scoped excerpt is about the title field alone (the derived suggestion); a
        general one is about the whole AI text. Keeping them apart is what the measurement
        asked for: the title prefix helps the suggestion and hurts the vector.
        """
        if scope == ["TITLE"]:
            return ["original_title"]
        return list(AI_TEXT_COLUMNS)

    @staticmethod
    def _rule_from(text: str, variants: list[str], action: str, replacement: str) -> ExcerptRule:
        matchers = tuple(
            normalized for normalized in (normalize_excerpt(candidate) for candidate in (text, *variants)) if normalized
        )
        return ExcerptRule(
            matchers=tuple(dict.fromkeys(matchers)), replacement=replacement if action == "REPLACE" else ""
        )

    @staticmethod
    def _changes_effect(previous: TextTemplateDTO, updated: TextTemplateDTO) -> bool:
        """True when the update changes which text the AI reads."""
        return (
            previous.matchers != updated.matchers
            or previous.replacement != updated.replacement
            or previous.scope != updated.scope
            or previous.applies != updated.applies
        )

    def _refresh_evidence(self, template: TextTemplateDTO) -> TextTemplateDTO:
        """Recomputes how many documents the excerpt affects, now that it is a decision."""
        if not template.applies:
            return template

        rule = self._rule_from(template.text, template.variants, template.action, template.replacement)
        affected = self.repo.count_affected_documents([rule], self._columns_for_scope(list(template.scope)))

        # ``occurrence_count`` is evidence, not a decision, so it is not part of the
        # editable command surface; it is written through this dedicated path.
        return self.repo.refresh_occurrence_count(template.template_id, affected) or template

    def _requeue_documents(self, template: TextTemplateDTO) -> int:
        if not template.applies:
            return 0

        # A title-only excerpt changes nothing the workers produced: the suggested title is
        # derived on read. The embedding re-queues by itself (its stamp is the hash of the
        # effective text); only the status-stamped readers have to be told.
        if "NER" not in template.scope:
            return 0

        return self.repo.requeue_documents(
            self.repo.find_documents_with_excerpt(template.matchers, list(AI_TEXT_COLUMNS)),
            [stamp.key for stamp in TEXT_DEPENDENT_STAMPS],
        )
