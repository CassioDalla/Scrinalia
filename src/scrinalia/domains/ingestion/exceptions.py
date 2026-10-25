"""Refusals of the ingestion domain, answered as business statuses by the API.

They live here, and not in ``archive.exceptions``, because the origin is an ingestion concept: the
archive's handler re-exports the shared ``DomainException`` base, but an origin that does not exist
is not an archive refusal. The API maps the subclasses it knows to 404/409/422.
"""

from scrinalia.core.exceptions import DomainException


class OriginNotFoundError(DomainException):
    """The registry or the table has no origin with this code."""

    pass


class OriginDisabledError(DomainException):
    """The origin exists but is paused; it cannot run and it cannot receive a manual record."""

    pass


class InvalidOriginConfigError(DomainException):
    """A configuration or run option the origin's own model refuses."""

    pass


class OriginPhaseNotImplementedError(DomainException):
    """The origin declares a kind whose phase the job asked for and the adapter does not have."""

    pass


class DuplicateManualRecordError(DomainException):
    """The manual form submitted a description_id the collection already has."""

    pass
