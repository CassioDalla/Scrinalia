"""HTTP surface of the collection vocabulary catalogue."""

from litestar import Controller, get, patch, post
from litestar.di import NamedDependency, Provide
from litestar.params import FromPath

from scrinalia.api.dependencies import provide_collection_vocabulary_service
from scrinalia.api.schemas.collection_vocabulary import (
    ArrangementTermCreateRequest,
    ArrangementTermUpdateRequest,
    CollectionTermCreateRequest,
    CollectionTermUpdateRequest,
)
from scrinalia.api.security import Access
from scrinalia.domains.archive.schemas.collection_vocabulary_schema import (
    ArrangementTermDTO,
    CollectionTermDTO,
    CollectionVocabularyResponse,
    CreateArrangementTermCommand,
    CreateCollectionTermCommand,
    UpdateArrangementTermCommand,
    UpdateCollectionTermCommand,
)
from scrinalia.domains.archive.services.collection_vocabulary_service import CollectionVocabularyService


class CollectionVocabularyController(Controller):
    """
    What *this* collection declares, as opposed to what the software or the language fixes.

    Two catalogues, one screen: the arrangement names the hierarchy proposal suggests for a rung,
    and the terms the subject guard reads for the families the collection owns — a toponym that is a
    place and a person name that is not a subject. Everything else the guard refuses (a bare year, a
    placeholder, an address prefix) is a property of the Portuguese language and lives in the
    language profile, deliberately out of the curator's reach: it is not a curation decision.

    There is no ``DELETE``. Removing an arrangement name would make the next proposal suggest nothing
    again, and removing a collection term would make a term the archivist explicitly refused come
    back into the subject axis — both are silent behaviour changes. ``PATCH {"is_active": false}``
    retires the row and keeps the record that it existed.
    """

    path = "/api/v1/vocabulary"
    tags = ["Vocabulary"]  # noqa: RUF012

    dependencies = {  # noqa: RUF012
        "vocabulary_service": Provide(provide_collection_vocabulary_service, sync_to_thread=False),
    }

    @get("/", opt={"access": Access.AUTHENTICATED}, sync_to_thread=True)
    def read_vocabulary(
        self,
        vocabulary_service: NamedDependency[CollectionVocabularyService],
    ) -> CollectionVocabularyResponse:
        """Both catalogues, retired rows included, with the weight of each collection term."""
        return vocabulary_service.read()

    @post("/arrangement-terms", opt={"access": Access.CATALOGUE}, status_code=201, sync_to_thread=True)
    def create_arrangement_term(
        self,
        vocabulary_service: NamedDependency[CollectionVocabularyService],
        data: ArrangementTermCreateRequest,
    ) -> ArrangementTermDTO:
        """Registers a rung name. A token already taken — even by a retired row — is a 409."""
        return vocabulary_service.create_arrangement_term(CreateArrangementTermCommand(**data.model_dump()))

    @patch("/arrangement-terms/{term_id:int}", opt={"access": Access.CATALOGUE}, sync_to_thread=True)
    def update_arrangement_term(
        self,
        vocabulary_service: NamedDependency[CollectionVocabularyService],
        term_id: FromPath[int],
        data: ArrangementTermUpdateRequest,
    ) -> ArrangementTermDTO:
        """Renames or (de)activates a suggestion. Arrangement terms are never deleted."""
        return vocabulary_service.update_arrangement_term(
            term_id, UpdateArrangementTermCommand(**data.model_dump(exclude_unset=True))
        )

    @post("/collection-terms", opt={"access": Access.CATALOGUE}, status_code=201, sync_to_thread=True)
    def create_collection_term(
        self,
        vocabulary_service: NamedDependency[CollectionVocabularyService],
        data: CollectionTermCreateRequest,
    ) -> CollectionTermDTO:
        """Registers a non-subject term. The same spelling under the same kind is a 409."""
        return vocabulary_service.create_collection_term(CreateCollectionTermCommand(**data.model_dump()))

    @patch("/collection-terms/{term_id:int}", opt={"access": Access.CATALOGUE}, sync_to_thread=True)
    def update_collection_term(
        self,
        vocabulary_service: NamedDependency[CollectionVocabularyService],
        term_id: FromPath[int],
        data: CollectionTermUpdateRequest,
    ) -> CollectionTermDTO:
        """Renames, re-kinds or (de)activates a term. Collection terms are never deleted."""
        return vocabulary_service.update_collection_term(
            term_id, UpdateCollectionTermCommand(**data.model_dump(exclude_unset=True))
        )
