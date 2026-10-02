"""Deployable ASGI entrypoint.

Kept at the repository root so ``uvicorn main:app`` and the ``Procfile`` stay
unchanged. The application itself lives in the installed package; this module only
re-exports it, and exists so a deploy does not need to know the package layout.
"""

from memoria_curitibana.asgi import app, create_app

__all__ = ["app", "create_app"]
