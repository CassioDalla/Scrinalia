"""Writes the OpenAPI document of the application to stdout.

Exists so the contract is an artifact the CI can regenerate and compare, instead of something only
a running server produces. The front-end client is generated from this file, so a route or schema
change that is not accompanied by a regenerated contract fails the build rather than surfacing as a
runtime type error in the browser.

Usage::

    uv run python -m scrinalia.api.dump_openapi > packages/api-contract/openapi.json

It imports the app factory, which builds the Litestar application without touching the database:
the composition root only wires dependencies lazily, so this runs without Postgres.
"""

import json
import sys

from scrinalia.asgi import create_app


def openapi_document() -> dict:
    """
    The OpenAPI schema of the application, as a plain dict.

    ``sort_keys`` is applied by the caller, not here: the point of the committed file is that two
    runs on the same commit produce byte-identical output, and dict ordering would otherwise depend
    on import order.
    """
    return create_app().openapi_schema.to_schema()  # type: ignore[union-attr]


def main() -> None:
    """Dumps the schema as deterministic JSON."""
    json.dump(openapi_document(), sys.stdout, indent=2, sort_keys=True, ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
