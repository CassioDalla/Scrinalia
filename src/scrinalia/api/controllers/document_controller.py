from datetime import date

from litestar import Controller, Response, delete, get, patch, post
from litestar.di import NamedDependency, Provide
from litestar.exceptions import HTTPException
from litestar.openapi.datastructures import ResponseSpec
from litestar.params import FromPath, FromQuery

from scrinalia.api.dependencies import (
    ThumbnailReader,
    provide_current_user,
    provide_document_service,
    provide_thumbnail_reader,
)
from scrinalia.api.schemas.documents import (
    DocumentUpdateRequest,
    EntityLinkRequest,
    TagLinkRequest,
)
from scrinalia.api.security import Access, AuthenticatedUser
from scrinalia.core.config import storage_configured
from scrinalia.core.exceptions import DomainException
from scrinalia.core.logger import logger
from scrinalia.domains.archive.models import ArchiveReviewStatus
from scrinalia.domains.archive.schemas import RouteMessageCode
from scrinalia.domains.archive.schemas.command_schema import (
    DocumentReviewCommand,
    EntityLinkCommand,
    TagLinkCommand,
)
from scrinalia.domains.archive.schemas.document_schema import (
    DOCUMENTS_RESOURCE,
    THUMBNAIL_SEGMENT,
    DocumentDeletionListResponse,
    DocumentDeletionResponse,
    DocumentListResponse,
    DocumentRevisionDTO,
    DocumentSummary,
)
from scrinalia.domains.archive.schemas.query_schema import DocumentSearchQuery, SearchMode
from scrinalia.domains.archive.schemas.route_messages import route_message
from scrinalia.domains.archive.services.document_service import DocumentService


class DocumentController(Controller):
    path = DOCUMENTS_RESOURCE
    tags = ["Documents"]  # noqa: RUF012

    dependencies = {  # noqa: RUF012
        "current_user": Provide(provide_current_user, sync_to_thread=False),
        "document_service": Provide(provide_document_service, sync_to_thread=False),
    }

    @get("/", opt={"access": Access.AUTHENTICATED}, sync_to_thread=True)
    def list_documents(
        self,
        document_service: NamedDependency[DocumentService],
        term: FromQuery[str | None] = None,
        mode: FromQuery[SearchMode] = "lexical",
        typology_id: FromQuery[int | None] = None,
        macro_category_id: FromQuery[int | None] = None,
        level_id: FromQuery[int | None] = None,
        ancestor_id: FromQuery[str | None] = None,
        entity_type: FromQuery[str | None] = None,
        entity_id: FromQuery[int | None] = None,
        date_from: FromQuery[date | None] = None,
        date_to: FromQuery[date | None] = None,
        status: FromQuery[ArchiveReviewStatus | None] = None,
        is_anomaly: FromQuery[bool | None] = None,
        anomaly_reason: FromQuery[str | None] = None,
        limit: FromQuery[int] = 50,
        offset: FromQuery[int] = 0,
    ) -> DocumentListResponse:
        """
        Lists/paginates the collection with full-text or semantic ranking and facet filters.

        ``ancestor_id`` is "search inside this fonds/série": the branch is resolved to its
        materialised path and matched with one indexed prefix, so it costs the same at any depth.
        """
        return document_service.search(
            DocumentSearchQuery(
                term=term,
                mode=mode,
                typology_id=typology_id,
                macro_category_id=macro_category_id,
                level_id=level_id,
                ancestor_id=ancestor_id,
                entity_type=entity_type,
                entity_id=entity_id,
                date_from=date_from,
                date_to=date_to,
                status=status,
                is_anomaly=is_anomaly,
                anomaly_reason=anomaly_reason,
                limit=limit,
                offset=offset,
            )
        )

    @get("/deletions", opt={"access": Access.AUTHENTICATED}, sync_to_thread=True)
    def list_deletions(
        self,
        document_service: NamedDependency[DocumentService],
        term: FromQuery[str | None] = None,
        limit: FromQuery[int] = 50,
        offset: FromQuery[int] = 0,
    ) -> DocumentDeletionListResponse:
        """
        The deletion ledger: what was removed, when, by whom and the snapshot of it.

        It is a ledger and not a revision because the revision table cascades with the document — an
        audit trail of a deletion has to outlive the thing it describes.
        """
        return document_service.list_deletions(term=term, limit=limit, offset=offset)

    @get("/{description_id:str}", opt={"access": Access.AUTHENTICATED}, sync_to_thread=True)
    def get_document(
        self, document_service: NamedDependency[DocumentService], description_id: FromPath[str]
    ) -> DocumentSummary:
        """Returns a specific document with its tags and entities."""
        return document_service.get(description_id)

    @get(
        THUMBNAIL_SEGMENT,
        opt={"access": Access.AUTHENTICATED},
        sync_to_thread=True,
        dependencies={"thumbnail_reader": Provide(provide_thumbnail_reader, sync_to_thread=False)},
        responses={
            200: ResponseSpec(
                data_container=bytes,
                media_type="image/jpeg",
                description="The stored miniature, read from the object storage on demand.",
                generate_examples=False,
            )
        },
    )
    def get_thumbnail(
        self,
        document_service: NamedDependency[DocumentService],
        thumbnail_reader: NamedDependency[ThumbnailReader],
        description_id: FromPath[str],
    ) -> Response[bytes]:
        """
        Serves the miniature's bytes, from the same origin and under the session cookie.

        The browser gets no ``s3://`` URI and no presigned link: the bucket's endpoint is the API's
        private one, and a link handed to the browser would both expose it and outlive the session
        that may read it. ``DocumentSummary.thumbnail_url`` advertises this route, so the SPA never
        assembles the path itself.

        **404** is also the answer when this installation has no object storage configured: the
        contract then advertises no thumbnail at all (``thumbnail_url`` is ``None``), so a request
        that arrives is a stale link and there is nothing for the browser to show. It is deliberately
        **not** a 503 and not a log line per image — the health probe is where "the storage is not
        configured" is reported once, and an unconfigured installation does not get one stack trace
        per card. The other answers are the states the screen draws: **200** the image, **404** when
        the source had no image or the object is no longer in the bucket (the URI is a reference, not
        a guarantee), and **503** when the storage **is** configured but unreachable — an operator
        problem, logged, and not a defect of the request. The body is private for five minutes so a
        page of miniatures is paid once; a forced worker run can take that long to show.
        """
        # Before the URI lookup: an installation without storage has no URL to advertise and no
        # image to serve, and the check keeps ``S3Storage`` from even building its client.
        if not storage_configured():
            raise HTTPException(
                status_code=404,
                detail="This installation has no object storage, so it has no stored thumbnail.",
            )

        uri = document_service.get_thumbnail_uri(description_id)
        if uri is None:
            raise HTTPException(status_code=404, detail="This description has no stored thumbnail.")

        try:
            stored = thumbnail_reader.read_object(uri)
        except DomainException:
            # ``ObjectStorageError``: credentials, endpoint or bucket, not this description. The
            # handler is the operator's log line; the browser only needs the placeholder.
            logger.exception(f"🖼️ The object storage could not read the thumbnail of {description_id}.")
            raise HTTPException(status_code=503, detail="The object storage is unavailable.") from None

        if stored is None:
            raise HTTPException(status_code=404, detail="The thumbnail object is not in the bucket.")

        body, media_type = stored
        return Response(
            content=body,
            media_type=media_type,
            headers={
                "Cache-Control": "private, max-age=300",
                # The worker writes JPEG, and a bucket whose metadata says otherwise must not make
                # this origin serve a type the browser would interpret as markup.
                "X-Content-Type-Options": "nosniff",
            },
        )

    @get("/{description_id:str}/revisions", opt={"access": Access.AUTHENTICATED}, sync_to_thread=True)
    def list_revisions(
        self, document_service: NamedDependency[DocumentService], description_id: FromPath[str]
    ) -> list[DocumentRevisionDTO]:
        """Human review audit trail: who changed what, and from which value to which."""
        return document_service.list_revisions(description_id)

    @patch("/{description_id:str}", opt={"access": Access.CURATE}, sync_to_thread=True)
    def update_document(
        self,
        document_service: NamedDependency[DocumentService],
        description_id: FromPath[str],
        data: DocumentUpdateRequest,
        current_user: NamedDependency[AuthenticatedUser],
    ) -> DocumentSummary:
        """Applies the human review, records the changes and marks the document HUMAN_APPROVED."""
        return document_service.update_review(
            DocumentReviewCommand(
                description_id=description_id,
                **data.model_dump(exclude_unset=True),
                changed_by=current_user.author,
            )
        )

    # --- Local subject curation ---------------------------------------------------------------
    #
    # Until now "this document is about this too" could only be decided by merging terms globally or
    # by re-running a worker. These four routes close that gap, and they follow the same rule as the
    # field edit: a human decision is recorded in the revision ledger and takes the record out of
    # the AI's reach.
    @post("/{description_id:str}/tags", opt={"access": Access.CURATE}, status_code=201, sync_to_thread=True)
    def link_tag(
        self,
        document_service: NamedDependency[DocumentService],
        description_id: FromPath[str],
        data: TagLinkRequest,
        current_user: NamedDependency[AuthenticatedUser],
    ) -> DocumentSummary:
        """Attaches one tag to this description, records the revision and marks it HUMAN_APPROVED."""
        return document_service.link_tag(
            TagLinkCommand(description_id=description_id, tag_id=data.tag_id), current_user.author, data.review_note
        )

    @delete(
        "/{description_id:str}/tags/{tag_id:int}", opt={"access": Access.CURATE}, status_code=200, sync_to_thread=True
    )
    def unlink_tag(
        self,
        document_service: NamedDependency[DocumentService],
        description_id: FromPath[str],
        tag_id: FromPath[int],
        current_user: NamedDependency[AuthenticatedUser],
        review_note: FromQuery[str | None] = None,
    ) -> DocumentSummary:
        """Detaches one tag from this description, records the revision and marks it HUMAN_APPROVED."""
        return document_service.unlink_tag(
            TagLinkCommand(description_id=description_id, tag_id=tag_id), current_user.author, review_note
        )

    @post("/{description_id:str}/entities", opt={"access": Access.CURATE}, status_code=201, sync_to_thread=True)
    def link_entity(
        self,
        document_service: NamedDependency[DocumentService],
        description_id: FromPath[str],
        data: EntityLinkRequest,
        current_user: NamedDependency[AuthenticatedUser],
    ) -> DocumentSummary:
        """Attaches one named entity to this description, records the revision and marks it HUMAN_APPROVED."""
        return document_service.link_entity(
            EntityLinkCommand(description_id=description_id, entity_id=data.entity_id),
            current_user.author,
            data.review_note,
        )

    @delete(
        "/{description_id:str}/entities/{entity_id:int}",
        opt={"access": Access.CURATE},
        status_code=200,
        sync_to_thread=True,
    )
    def unlink_entity(
        self,
        document_service: NamedDependency[DocumentService],
        description_id: FromPath[str],
        entity_id: FromPath[int],
        current_user: NamedDependency[AuthenticatedUser],
        review_note: FromQuery[str | None] = None,
    ) -> DocumentSummary:
        """Detaches one named entity from this description, records the revision and marks it HUMAN_APPROVED."""
        return document_service.unlink_entity(
            EntityLinkCommand(description_id=description_id, entity_id=entity_id), current_user.author, review_note
        )

    # --- Deletion ------------------------------------------------------------------------------
    #
    # The one write on this controller that removes a record. It refuses a node with children (the
    # arrangement's FK is RESTRICT on purpose) and records the snapshot before deleting, so the
    # decision can be explained afterwards.
    @delete("/{description_id:str}", opt={"access": Access.CURATE}, status_code=200, sync_to_thread=True)
    def delete_document(
        self,
        document_service: NamedDependency[DocumentService],
        description_id: FromPath[str],
        current_user: NamedDependency[AuthenticatedUser],
        note: FromQuery[str | None] = None,
    ) -> DocumentDeletionResponse:
        """Deletes one description, refusing a node that still has children below it."""
        entry = document_service.delete(description_id, changed_by=current_user.author, note=note)
        return DocumentDeletionResponse(
            code=RouteMessageCode.DOCUMENT_DELETED,
            message=route_message(
                RouteMessageCode.DOCUMENT_DELETED, "Descrição '{title}' excluída do acervo.", title=entry.title
            ),
            data=entry,
        )
