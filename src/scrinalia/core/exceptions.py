"""The base class of a business refusal, shared by every domain.

It lives in ``core`` and not inside a domain because the HTTP layer has to catch **all** of them with
one handler. ``DomainException`` is the API's contract with the domains — it means "this is an answer
the API owes the client, not a defect" — and a second base class per domain would silently escape the
handler and turn a business refusal into a recorded 500.

``domains/archive/exceptions.py`` re-exports it, so the imports that already exist keep working and
there is still exactly one class to register.
"""


class DomainException(Exception):
    """A business refusal: the request was well formed and the *state* says no."""
