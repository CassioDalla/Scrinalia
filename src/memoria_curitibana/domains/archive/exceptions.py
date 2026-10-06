# domain/exceptions.py


class DomainException(Exception):
    pass


class TagNotFoundError(DomainException):
    """Raised when trying to fetch or merge a tag that does not exist."""

    # Ideal translation in Litestar: HTTP 404 (Not Found)
    pass


class EntityNotFoundError(DomainException):
    """Raised when linking or unlinking a named entity the collection does not have."""

    # Ideal translation in Litestar: HTTP 404 (Not Found)
    pass


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
