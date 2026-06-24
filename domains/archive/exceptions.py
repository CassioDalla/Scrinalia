# domain/exceptions.py


class DomainException(Exception):
    pass


class TagNotFoundError(DomainException):
    """Lançado quando se tenta buscar ou mesclar uma tag que não existe."""

    # Tradução ideal no Litestar: HTTP 404 (Not Found)
    pass


class InvalidMergeError(DomainException):
    """Lançado quando tenta mesclar uma tag nela mesma ou quebra regras de sinônimos."""

    # Tradução ideal no Litestar: HTTP 400 (Bad Request) ou 422
    pass


class InvalidParam(DomainException):
    "Lançado quando algum parametro de função é passo errado"

    # Tradução ideal no Litestar: HTTP 400 (Bad Request) ou 422
    pass


class EngineExecutionError(DomainException):
    "Lançado quando algum erro nos motores de Ia acontecem"

    pass
