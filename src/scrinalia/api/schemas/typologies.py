from pydantic import BaseModel, ConfigDict, Field


class TypologyCreateRequest(BaseModel):
    """Registers a documental typology: a name the classifier will propose and the curator will read."""

    name: str = Field(
        min_length=1, max_length=100, description="O que o arquivista lê e o classificador usa como rótulo."
    )
    context_description: str | None = Field(
        default=None,
        description="Documentação para o curador: exemplos do que cai nesta tipologia. "
        "Nunca vai para o modelo — concatená-lo ao rótulo faz o classificador colapsar o acervo.",
    )

    model_config = ConfigDict(extra="forbid")


class TypologyUpdateRequest(BaseModel):
    """
    Partial update of a typology.

    There is no delete and no ``typology_id`` to move: the foreign key is ``SET NULL``, so a
    removal would silently unclassify every description carrying it. ``is_active=false`` retires the
    typology — and that is also what takes it out of the classifier's candidate labels.
    """

    name: str | None = Field(default=None, min_length=1, max_length=100)
    context_description: str | None = None
    is_active: bool | None = None

    model_config = ConfigDict(extra="forbid")
