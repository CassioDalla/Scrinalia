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


class DiffusionAdapterMissingError(DomainException):
    """
    The channel has no adapter in this version, so an export run cannot be queued.

    The registry ships a definition and, for an export channel, the module that writes it. Until the
    first adapter lands (#214) an export channel that is only a definition must answer with a
    sentence instead of queueing a run that would fail for a reason the operator cannot fix. The
    worker raises the same refusal defensively, for a row that was queued before a deploy.
    """

    pass


class PublicationPreviewStaleError(DomainException):
    """
    The selection a preview resolved is not the one the apply would resolve.

    The token is a **consistency** check and not a capability: it exists so the confirmation cannot
    run over a different set (a record approved meanwhile, a scope revoked by another curator), and
    never to authorize the write — that is the session's ``CURATE``. It expires, and an expired or
    tampered token is the same refusal: preview again.
    """

    pass


class PublicationNodeNotFoundError(DomainException):
    """The branch or record a publication names does not exist in the archive."""

    pass


class PublicationBatchNotFoundError(DomainException):
    """The history has no batch with this id."""

    pass


class PublicationBatchAlreadyUndoneError(DomainException):
    """The batch was already undone; a second undo would revert decisions taken after it."""

    pass


class PublicationRefusedError(DomainException):
    """
    The gesture is well formed and there is nothing it can do.

    A scope the channel already has, an exclusion and an inclusion on the same node, every selected
    record already covered: the answer is a sentence about what to do next, not a silent no-op that
    would leave the curator believing the click wrote.
    """

    pass
