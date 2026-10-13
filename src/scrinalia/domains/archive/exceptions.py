# domain/exceptions.py

from typing import Any

# The base class lives in ``core`` (see ``core/exceptions.py``): the API registers one handler for
# every domain's refusals, and a per-domain base class would escape it. Re-exported here with the
# redundant alias so the imports across the codebase keep resolving and ruff sees the intent.
from scrinalia.core.exceptions import DomainException as DomainException


class TagNotFoundError(DomainException):
    """Raised when trying to fetch or merge a tag that does not exist."""

    # Ideal translation in Litestar: HTTP 404 (Not Found)
    pass


class EntityNotFoundError(DomainException):
    """Raised when linking, renaming or unlinking a named entity the collection does not have."""

    # Ideal translation in Litestar: HTTP 404 (Not Found)
    pass


class DuplicateEntityNameError(DomainException):
    """
    A rename asked for a spelling another entity already carries.

    ``uix_archive_entities_name_normalized`` would raise an ``IntegrityError`` a moment later, and the
    generic handler answers *"Conflito estrutural no banco de dados"* — a 409 that names neither the
    twin nor the fact that the twin **is** the merge case. So the check happens before the write and
    the refusal says which one.

    The pair travels in ``details`` as well as in the sentence, and that is the point of the two: the
    sentence is Portuguese and the interface is going to be translated (#45), so the SPA reads the
    facts from ``details`` and wraps them in its own copy.
    """

    def __init__(self, entity_id: int, name: str, conflicting_entity_id: int, conflicting_name: str) -> None:
        super().__init__(
            f"Já existe uma entidade com a grafia '{conflicting_name}' (ID {conflicting_entity_id}). "
            f"Mescle as duas em vez de renomear."
        )
        self.entity_id = entity_id
        self.name = name
        self.conflicting_entity_id = conflicting_entity_id
        self.conflicting_name = conflicting_name
        self.details: dict[str, Any] = {
            "entity": {"entity_id": entity_id, "name": name},
            "conflicting_entity": {"entity_id": conflicting_entity_id, "name": conflicting_name},
        }


class DocumentNotFoundError(DomainException):
    """Raised when a document does not exist in the Archive layer."""

    # Ideal translation in Litestar: HTTP 404 (Not Found)
    pass


class CleaningRuleNotFoundError(DomainException):
    """Raised when a cleaning rule does not exist."""

    # Ideal translation in Litestar: HTTP 404 (Not Found)
    pass


class MacroCategoryNotFoundError(DomainException):
    """Raised when a macro category does not exist in the Archive layer."""

    # Ideal translation in Litestar: HTTP 404 (Not Found)
    pass


class TextTemplateNotFoundError(DomainException):
    """Raised when a repeated-excerpt catalog row does not exist."""

    # Ideal translation in Litestar: HTTP 404 (Not Found)
    pass


class TagMergeProposalNotFoundError(DomainException):
    """Raised when a tag-merge proposal does not exist in the curation catalog."""

    # Ideal translation in Litestar: HTTP 404 (Not Found)
    pass


class MergeLogNotFoundError(DomainException):
    """Raised when a merge ledger entry does not exist."""

    # Ideal translation in Litestar: HTTP 404 (Not Found)
    pass


class MergeAlreadyUndoneError(DomainException):
    """Raised when the same merge is undone twice; the ledger keeps one reversal per merge."""

    # Ideal translation in Litestar: HTTP 409 (Conflict)
    pass


class StopwordPurgeLogNotFoundError(DomainException):
    """Raised when a stopword-purge ledger entry does not exist."""

    # Ideal translation in Litestar: HTTP 404 (Not Found)
    pass


class StopwordPurgeAlreadyUndoneError(DomainException):
    """Raised when the same purge is undone twice; the ledger keeps one reversal per tag."""

    # Ideal translation in Litestar: HTTP 409 (Conflict)
    pass


class NerPurgeLogNotFoundError(DomainException):
    """Raised when a NER-purge ledger entry does not exist."""

    # Ideal translation in Litestar: HTTP 404 (Not Found)
    pass


class NerPurgeAlreadyUndoneError(DomainException):
    """Raised when the same NER purge is undone twice; the ledger keeps one reversal per entity."""

    # Ideal translation in Litestar: HTTP 409 (Conflict)
    pass


class InvalidMergeError(DomainException):
    """Raised when trying to merge a tag into itself or breaking synonym rules."""

    # Ideal translation in Litestar: HTTP 400 (Bad Request) or 422
    pass


class InvalidParam(DomainException):
    """Raised when a function parameter is passed incorrectly."""

    # Ideal translation in Litestar: HTTP 400 (Bad Request) or 422
    pass


class EngineExecutionError(DomainException):
    """Raised when an error occurs in the AI engines."""

    pass


class DescriptionLevelNotFoundError(DomainException):
    """Raised when a level of the description catalogue does not exist."""

    # Ideal translation in Litestar: HTTP 404 (Not Found)
    pass


class DuplicateDescriptionLevelError(DomainException):
    """Raised when the ordinal, the code or the name of a level is already taken."""

    # Ideal translation in Litestar: HTTP 409 (Conflict)
    pass


class InvalidDescriptionLevelError(DomainException):
    """Raised when a declared level spelling is not in the catalogue.

    Only the *human* path raises: the staging load deliberately records the unknown value as
    unclassified and carries on, because a source typo must not stop a transfer.
    """

    # Ideal translation in Litestar: HTTP 422 (Unprocessable Entity)
    pass


class TypologyNotFoundError(DomainException):
    """Raised when a documental typology does not exist in the catalogue."""

    # Ideal translation in Litestar: HTTP 404 (Not Found)
    pass


class ConflictResolutionNotFoundError(DomainException):
    """Raised when a tag x entity resolution does not exist in the ledger."""

    # Ideal translation in Litestar: HTTP 404 (Not Found)
    pass


class UnresolvableConflictError(DomainException):
    """Raised when a tag x entity pair cannot be resolved because a side no longer exists.

    Not an ``InvalidParam``: the parameters are well formed, the *state* is what makes the write
    impossible — the losing row was already deleted by an earlier resolution. A 400 would blame the
    client for a business condition.
    """

    # Ideal translation in Litestar: HTTP 422 (Unprocessable Entity)
    pass


class ConflictResolutionAlreadyUndoneError(DomainException):
    """Raised when the same resolution is reversed twice.

    The undo is single-shot, like the merge's: the ledger row is never deleted, so "this was
    resolved, then reversed" survives the reversal and the second attempt is a conflict, not a
    silent no-op that would look like it worked.
    """

    # Ideal translation in Litestar: HTTP 409 (Conflict)
    pass


class DuplicateTypologyError(DomainException):
    """Raised when the name of a typology is already taken (case-insensitively)."""

    # Ideal translation in Litestar: HTTP 409 (Conflict)
    pass


class InvalidTypologyError(DomainException):
    """Raised when a typology a human chose is not in the catalogue.

    Only the *human* path raises: the classifier only ever writes a name the catalogue gave it, so
    an unknown id can only come from a client, and storing ``NULL`` would turn a wrong id into
    missing data.
    """

    # Ideal translation in Litestar: HTTP 422 (Unprocessable Entity)
    pass


class ArrangementTermNotFoundError(DomainException):
    """Raised when an arrangement vocabulary row does not exist."""

    # Ideal translation in Litestar: HTTP 404 (Not Found)
    pass


class DuplicateArrangementTermError(DomainException):
    """Raised when two rows would carry the same arrangement token."""

    # Ideal translation in Litestar: HTTP 409 (Conflict)
    pass


class CollectionTermNotFoundError(DomainException):
    """Raised when a collection term row does not exist."""

    # Ideal translation in Litestar: HTTP 404 (Not Found)
    pass


class DuplicateCollectionTermError(DomainException):
    """Raised when the same term would be registered twice under the same kind."""

    # Ideal translation in Litestar: HTTP 409 (Conflict)
    pass


class HierarchyNodeNotFoundError(DomainException):
    """Raised when a description referenced by the tree does not exist."""

    # Ideal translation in Litestar: HTTP 404 (Not Found)
    pass


class InvalidHierarchyMoveError(DomainException):
    """Raised when a parent/level assignment breaks a rule of the arrangement."""

    # Ideal translation in Litestar: HTTP 422 (Unprocessable Entity)
    pass


class HierarchyPlanNotFoundError(DomainException):
    """Raised when an arrangement plan of the hierarchy catalogue does not exist."""

    # Ideal translation in Litestar: HTTP 404 (Not Found)
    pass


class InvalidHierarchyPlanError(DomainException):
    """Raised when a decision about a rung cannot be materialised as written."""

    # Ideal translation in Litestar: HTTP 422 (Unprocessable Entity)
    pass


class MaterialisationNotFoundError(DomainException):
    """Raised when a materialisation run does not exist in the ledger."""

    # Ideal translation in Litestar: HTTP 404 (Not Found)
    pass


class MaterialisationAlreadyUndoneError(DomainException):
    """Raised when the same materialisation is undone twice; the ledger keeps one reversal per run."""

    # Ideal translation in Litestar: HTTP 409 (Conflict)
    pass


class DocumentHasChildrenError(DomainException):
    """Raised when a description that still has children is asked to be deleted."""

    # Ideal translation in Litestar: HTTP 409 (Conflict)
    pass


class WorkerNotFoundError(DomainException):
    """Raised when the operations panel names a worker the catalogue does not have."""

    # Ideal translation in Litestar: HTTP 404 (Not Found)
    pass


class WorkerRunNotFoundError(DomainException):
    """Raised when a run of the execution ledger does not exist."""

    # Ideal translation in Litestar: HTTP 404 (Not Found)
    pass


class WorkerRunAlreadyActiveError(DomainException):
    """Raised when a worker already has a run in flight; the database refuses a second one."""

    # Ideal translation in Litestar: HTTP 409 (Conflict)
    pass


class InvalidWorkerSettingsError(DomainException):
    """Raised when an override names an engine/preset/option the worker cannot accept."""

    # Ideal translation in Litestar: HTTP 422 (Unprocessable Entity)
    pass
