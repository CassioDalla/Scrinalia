"""SQLAlchemy types that the framework does not ship, but the schema needs."""

from typing import Any

from sqlalchemy.types import UserDefinedType


class Vector(UserDefinedType):
    """
    PostgreSQL ``vector(N)`` from the pgvector extension, mapped to ``list[float]``.

    A local type instead of the ``pgvector`` package: the project only needs to store a
    vector and order by the cosine distance operator, and SQLAlchemy renders both from
    the column type alone. Alembic cannot introspect ``vector`` (it warns "Did not
    recognize type" and skips the column), exactly like a computed column, so the column
    is created by a hand-written migration and ``alembic check`` stays green.
    """

    cache_ok = True

    def __init__(self, dimensions: int) -> None:
        self.dimensions = dimensions

    def get_col_spec(self, **kw: Any) -> str:
        return f"vector({self.dimensions})"

    def bind_processor(self, dialect: Any) -> Any:
        """Renders the Python list as the ``[1.0,2.0,...]`` literal pgvector expects."""

        def process(value: list[float] | None) -> str | None:
            if value is None:
                return None
            return "[" + ",".join(str(float(component)) for component in value) + "]"

        return process

    def result_processor(self, dialect: Any, coltype: Any) -> Any:
        """Parses the pgvector text form back into a list of floats."""

        def process(value: str | None) -> list[float] | None:
            if value is None:
                return None
            return [float(component) for component in value.strip("[]").split(",")]

        return process
