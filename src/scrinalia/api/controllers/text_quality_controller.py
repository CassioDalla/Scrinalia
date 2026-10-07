from litestar import Controller, delete, get, patch, post
from litestar.di import NamedDependency, Provide
from litestar.params import FromPath, FromQuery

from scrinalia.api.dependencies import provide_text_quality_service
from scrinalia.api.schemas.text_quality_requests import (
    CreateTextTemplateRequest,
    DryRunTextTemplateRequest,
    SuggestTextTemplatesRequest,
    UpdateTextTemplateRequest,
)
from scrinalia.api.security import Access
from scrinalia.domains.archive.schemas import RouteMessageCode
from scrinalia.domains.archive.schemas.text_quality_schema import (
    TemplateCreateCommand,
    TemplateDryRunRequest,
    TemplateDryRunResponse,
    TemplateSuggestionResponse,
    TemplateUpdateCommand,
    TextTemplateDTO,
    TextTemplateMutationResponse,
)
from scrinalia.domains.archive.services.text_quality_service import TextQualityService


class TextQualityController(Controller):
    """Curation of the repeated excerpts the AI must not read (Fase 3.5)."""

    path = "/api/v1/quality/text-templates"
    tags = ["Data Quality"]  # noqa: RUF012

    dependencies = {  # noqa: RUF012
        "text_quality_service": Provide(provide_text_quality_service, sync_to_thread=False),
    }

    @get("/", opt={"access": Access.AUTHENTICATED}, sync_to_thread=True)
    def list_templates(
        self,
        text_quality_service: NamedDependency[TextQualityService],
        status: FromQuery[str | None] = None,
        only_active: FromQuery[bool] = False,
    ) -> list[TextTemplateDTO]:
        """Lists the catalog: pending suggestions, approved excerpts and rejected ones."""
        return text_quality_service.list_templates(status=status, only_active=only_active)

    @post("/suggest", opt={"access": Access.CATALOGUE}, sync_to_thread=True)
    def suggest_templates(
        self,
        text_quality_service: NamedDependency[TextQualityService],
        data: SuggestTextTemplatesRequest,
    ) -> TemplateSuggestionResponse:
        """
        Scans the collection for repeated excerpts and registers them as inactive
        suggestions. Nothing is applied to the AI text before a human approves it.
        """
        return text_quality_service.suggest_templates(
            min_ratio=data.min_ratio,
            min_documents=data.min_documents,
        )

    @post("/preview", opt={"access": Access.AUTHENTICATED}, sync_to_thread=True)
    def preview_template(
        self,
        text_quality_service: NamedDependency[TextQualityService],
        data: DryRunTextTemplateRequest,
    ) -> TemplateDryRunResponse:
        """Dry-run: how many documents the excerpt would change, with before/after samples."""
        return text_quality_service.dry_run(
            TemplateDryRunRequest(
                text=data.text,
                action=data.action,
                replacement=data.replacement,
                scope=data.scope,
                variants=data.variants,
                sample_limit=data.sample_limit,
            )
        )

    @post("/", opt={"access": Access.CATALOGUE}, status_code=201, sync_to_thread=True)
    def create_template(
        self,
        text_quality_service: NamedDependency[TextQualityService],
        data: CreateTextTemplateRequest,
    ) -> TextTemplateMutationResponse:
        """Registers an excerpt by hand; it starts approved and applied."""
        template, requeued = text_quality_service.create_template(
            TemplateCreateCommand(
                text=data.text,
                action=data.action,
                replacement=data.replacement,
                scope=data.scope,
                reason=data.reason,
                variants=data.variants,
                created_by=data.changed_by,
            )
        )
        return TextTemplateMutationResponse(
            code=RouteMessageCode.TEXT_TEMPLATE_CREATED,
            message="Trecho cadastrado e aplicado. Os documentos afetados voltaram para a fila da IA.",
            documents_requeued=requeued,
            data=template,
        )

    @patch("/{template_id:int}", opt={"access": Access.CATALOGUE}, sync_to_thread=True)
    def update_template(
        self,
        text_quality_service: NamedDependency[TextQualityService],
        template_id: FromPath[int],
        data: UpdateTextTemplateRequest,
    ) -> TextTemplateMutationResponse:
        """Approves, edits, deactivates or rejects an excerpt."""
        template, requeued = text_quality_service.update_template(
            template_id,
            TemplateUpdateCommand(**data.model_dump(exclude_unset=True)),
        )
        return TextTemplateMutationResponse(
            code=RouteMessageCode.TEXT_TEMPLATE_UPDATED,
            message="Trecho atualizado. Os documentos afetados voltaram para a fila da IA.",
            documents_requeued=requeued,
            data=template,
        )

    @delete("/{template_id:int}", opt={"access": Access.CATALOGUE}, status_code=200, sync_to_thread=True)
    def delete_template(
        self,
        text_quality_service: NamedDependency[TextQualityService],
        template_id: FromPath[int],
    ) -> TextTemplateMutationResponse:
        """Undoes the decision and re-queues every document the excerpt affected."""
        removed, requeued = text_quality_service.delete_template(template_id)
        return TextTemplateMutationResponse(
            code=RouteMessageCode.TEXT_TEMPLATE_DELETED,
            message="Trecho removido do catálogo e efeito desfeito nos documentos afetados.",
            documents_requeued=requeued,
            data=removed,
        )
