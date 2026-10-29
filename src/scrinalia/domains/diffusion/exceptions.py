"""Refusals of the diffusion domain, answered as business statuses by the API.

They live here and not in ``archive.exceptions`` because a channel is a distribution concept: the
archive's handler re-exports the shared ``DomainException`` base, but a channel that does not exist
is not an archive refusal. The API maps the subclasses it knows to 404/422 in ``api/handlers.py``.
"""

from scrinalia.core.exceptions import DomainException


class DiffusionChannelNotFoundError(DomainException):
    """The registry or the table has no channel with this code, or the channel is not configured."""

    pass


class InvalidDiffusionConfigError(DomainException):
    """A configuration, a schedule or an option the channel's own model refuses."""

    pass


class PublicSiteNotConfiguredError(DomainException):
    """The public site was not added, or it is paused; the public identity read answers 404."""

    pass
