# domain/exceptions.py


class DomainException(Exception):
    pass


class TagNotFoundError(DomainException):
    """Raised when trying to fetch or merge a tag that does not exist."""

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
