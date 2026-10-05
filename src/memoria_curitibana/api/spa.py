"""Serving the built curator SPA from the API process."""

from pathlib import Path

from litestar import Request, Response
from litestar.exceptions import HTTPException
from litestar.router import Router
from litestar.static_files import create_static_files_router
from litestar.status_codes import HTTP_200_OK, HTTP_404_NOT_FOUND
from litestar.types import ExceptionHandlersMap

#: Where ``bun run --cwd apps/curator build`` leaves the bundle. ``asgi.py`` lives two levels under
#: the repository root, so ``parents[2]`` is that root.
DIST_DIRECTORY = Path(__file__).resolve().parents[3] / "apps" / "curator" / "dist"


def spa_directory() -> Path | None:
    """The build directory, or ``None`` when the front-end was never built."""
    return DIST_DIRECTORY if DIST_DIRECTORY.is_dir() else None


def _serve_index(request: Request, exc: Exception) -> Response:
    """
    Hands the client router its entry point for a path it owns.

    Static file serving answers 404 for anything that is not a file on disk, but the SPA's routes
    (``/acervo/lista``, ``/acervo/123``) are not files: they only exist in the browser. Without this
    fallback every deep link and every refresh on a route answers 404 — the classic way to ship a
    single-page app that works only if you start from the home page.

    Genuine API 404s never reach here: the static router is registered last, so a request under
    ``/api`` is resolved by its controller long before this handler is a candidate.
    """
    if getattr(exc, "status_code", None) != HTTP_404_NOT_FOUND:
        raise exc

    index = spa_directory()
    if index is None:
        raise exc

    return Response(
        content=(index / "index.html").read_text(encoding="utf-8"),
        media_type="text/html",
        status_code=HTTP_200_OK,
    )


def curator_spa_router() -> Router | None:
    """
    The SPA mounted at the root, or ``None`` when there is no build to serve.

    Optional on purpose: the Python test suite, a fresh clone and the CI job that only runs pytest
    all work without ever building the front-end, and an absent directory means "no UI mounted"
    rather than a startup failure.
    """
    directory = spa_directory()
    if directory is None:
        return None

    handlers: ExceptionHandlersMap = {
        # The fallback is what makes client-side routing survive a page load. It only ever sees the
        # 404 the static router produces, because it is installed on that router alone.
        HTTPException: _serve_index,
    }

    return create_static_files_router(
        path="/",
        directories=[directory],
        html_mode=True,
        exception_handlers=handlers,
    )
