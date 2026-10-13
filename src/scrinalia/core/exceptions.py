"""The base class of a business refusal, shared by every domain.

It lives in ``core`` and not inside a domain because the HTTP layer has to catch **all** of them with
one handler. ``DomainException`` is the API's contract with the domains — it means "this is an answer
the API owes the client, not a defect" — and a second base class per domain would silently escape the
handler and turn a business refusal into a recorded 500.

``domains/archive/exceptions.py`` re-exports it, so the imports that already exist keep working and
there is still exactly one class to register.
"""

from typing import Any


class DomainException(Exception):
    """A business refusal: the request was well formed and the *state* says no."""

    #: Optional payload the refusal carries as **data** rather than as a sentence, or ``None``.
    #:
    #: The sentence in ``str(exc)`` is Portuguese, and it stays because the API owes one to whoever
    #: reads the response. It is not, however, a channel a translated interface can use: the interface
    #: is translated (#45), and a client that read the prose would freeze the server's language into
    #: its copy. So a refusal that has *facts* to report — which twin a rename collided with — puts
    #: them here, where they are language-neutral, and the copy that wraps them lives in the SPA's
    #: catalogue (`apps/curator/src/lib/messages.ts`).
    #:
    #: ``None`` for the refusals that are only a sentence, and the response then keeps exactly the
    #: shape it always had. The field is not in the committed contract: the error body is produced by
    #: the exception handlers and declared by no route, so this is additive without regenerating
    #: anything.
    details: dict[str, Any] | None = None
