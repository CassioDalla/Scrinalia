"""HTTP surface of the documental typology catalogue."""

from litestar import Controller, get, patch, post
from litestar.di import NamedDependency, Provide
from litestar.params import FromPath, FromQuery

from memoria_curitibana.api.dependencies import provide_typology_service
from memoria_curitibana.api.schemas.typologies import TypologyCreateRequest, TypologyUpdateRequest
from memoria_curitibana.domains.archive.schemas.typology_schema import (
    CreateTypologyCommand,
    TypologyDTO,
    UpdateTypologyCommand,
)
from memoria_curitibana.domains.archive.services.typology_service import TypologyService


class TypologyController(Controller):
    """
    The catalogue of diplomatic forms: ata, ofício, planta, fotografia.

    A controller of its own, and not a corner of ``HierarchyController`` or ``TaxonomyController``:
    the hierarchy is *provenance and arrangement* (objective, one place per description) and the
    taxonomy is *subject* (interpretative, several per description, written by the AI), while the
    typology is the *form of the record* — a closed catalogue the archivist maintains and the
    classifier reads as its candidate labels. Filing it under either would invite exactly the
    confusion the two were separated to avoid.

    There is no ``DELETE``. ``archive_documents.typology_id`` is ``SET NULL``, so removing a row
    would unclassify every description carrying it while erasing the record that the type ever
    existed; ``PATCH {"is_active": false}`` is the way out and it is reversible.
    """

    path = "/api/v1/typologies"
    tags = ["Typologies"]  # noqa: RUF012

    dependencies = {  # noqa: RUF012
        "typology_service": Provide(provide_typology_service, sync_to_thread=False),
    }

    @get("/", sync_to_thread=True)
    def list_typologies(
        self,
        typology_service: NamedDependency[TypologyService],
        only_active: FromQuery[bool] = False,
    ) -> list[TypologyDTO]:
        """
        Every typology, retired ones included, with how many descriptions carry each.

        The dossier's select reads only the active ones; the catalogue screen needs the retired ones
        too, because the FK is ``SET NULL`` and a deactivated typology still holds the descriptions
        classified with it. Hiding them would make the catalogue look lighter than it is.
        """
        return typology_service.list_typologies(only_active=only_active)

    @post("/", status_code=201, sync_to_thread=True)
    def create_typology(
        self,
        typology_service: NamedDependency[TypologyService],
        data: TypologyCreateRequest,
    ) -> TypologyDTO:
        """Registers a typology. A name already taken — even by a retired one — is rejected with 409."""
        return typology_service.create_typology(CreateTypologyCommand(**data.model_dump()))

    @patch("/{typology_id:int}", sync_to_thread=True)
    def update_typology(
        self,
        typology_service: NamedDependency[TypologyService],
        typology_id: FromPath[int],
        data: TypologyUpdateRequest,
    ) -> TypologyDTO:
        """
        Renames, re-documents or (de)activates a typology. Typologies are never deleted.

        Retiring one is what stops the classifier from proposing it; the descriptions already
        classified with it keep it, and the catalogue keeps showing their weight.
        """
        return typology_service.update_typology(
            typology_id, UpdateTypologyCommand(**data.model_dump(exclude_unset=True))
        )
