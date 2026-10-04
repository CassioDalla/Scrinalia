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
