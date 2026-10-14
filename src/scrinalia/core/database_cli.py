"""Create and recreate the database the settings name — the two things a DSN alone cannot do.

Run with ``uv run python -m scrinalia.core.database_cli create|recreate``, or through the
``bun run db:init`` and ``bun run db:recreate`` scripts, which also bring the container up and apply
the migrations afterwards.

It exists for the gap ``docker compose up -d`` cannot close: ``POSTGRES_DB`` is honoured when the
volume is **initialised**, so a database dropped from an existing volume stays dropped, and
``alembic upgrade head`` then fails on a database that is not there. It is also the database-scoped
alternative to ``docker compose down -v``, which destroys every database in the volume — the sibling
catalogues included.

Host, port, credentials and the name itself come from ``core.config.settings``, the same source the
API and Alembic read, so this command cannot disagree with the application about which database it is
talking about. Dropping has no undo: ``recreate`` prints what would die and refuses to act unless the
name is typed back at the prompt or ``--yes`` is given.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager

from sqlalchemy import Connection, create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import SQLAlchemyError

from scrinalia.core.config import settings

#: The maintenance database every PostgreSQL cluster ships. ``CREATE DATABASE`` and ``DROP DATABASE``
#: cannot be issued from inside the database they act on, so they go through here and never through
#: the application's own connection.
MAINTENANCE_DATABASE = "postgres"

#: Reads one line from the terminal. Injected so a test can answer without a TTY.
Prompt = Callable[[str], str]


def maintenance_url(url: URL) -> URL:
    """The same cluster and credentials, pointed at the maintenance database."""
    return url.set(database=MAINTENANCE_DATABASE)


def database_name(url: URL) -> str:
    """The database the URL names; an empty ``DB_NAME`` is a configuration error, not a default."""
    if not url.database:
        raise ValueError("The connection URL names no database (is DB_NAME empty?)")
    return url.database


@contextmanager
def _maintenance(url: URL) -> Iterator[Connection]:
    """
    An autocommit connection to the maintenance database.

    Autocommit because PostgreSQL refuses ``CREATE DATABASE``/``DROP DATABASE`` inside a transaction
    block, which is what SQLAlchemy would otherwise open around the statement.
    """
    engine = create_engine(maintenance_url(url), isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as connection:
            yield connection
    finally:
        engine.dispose()


def _exists(connection: Connection, name: str) -> bool:
    found = connection.execute(text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": name}).scalar()
    return found is not None


def _quoted(connection: Connection, name: str) -> str:
    """``name`` as PostgreSQL itself quotes an identifier, so nothing here is quoted by hand."""
    return connection.execute(text("SELECT quote_ident(:name)"), {"name": name}).scalar_one()


def _create(connection: Connection, name: str) -> None:
    connection.exec_driver_sql(f"CREATE DATABASE {_quoted(connection, name)}")


def _drop(connection: Connection, name: str) -> None:
    """Drops the database, closing whatever is connected to it (PostgreSQL's own ``FORCE``)."""
    connection.exec_driver_sql(f"DROP DATABASE {_quoted(connection, name)} WITH (FORCE)")


def _revision(url: URL) -> str | None:
    """
    The Alembic revision in the target database, or ``None`` when it carries no version table.

    A second connection, to the database itself: ``alembic_version`` lives in it, and no query from
    the maintenance database reads another database's tables. Any failure reads as "unknown" — the
    preview describes what would die, it never blocks the command.
    """
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            if connection.execute(text("SELECT to_regclass('public.alembic_version')")).scalar() is None:
                return None
            return connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
    except SQLAlchemyError:
        return None
    finally:
        engine.dispose()


def _inspect(connection: Connection, url: URL) -> str:
    """One line naming what the recreation would destroy beside its size and whoever is using it."""
    name = database_name(url)
    size = connection.execute(text("SELECT pg_size_pretty(pg_database_size(:name))"), {"name": name}).scalar_one()
    sessions = connection.execute(
        text("SELECT count(*) FROM pg_stat_activity WHERE datname = :name"), {"name": name}
    ).scalar_one()
    revision = _revision(url) or "sem migração aplicada"
    return f"a base {name} em {url.host}:{url.port} — {size}, revisão {revision}, {sessions} conexões abertas"


def _confirmed(name: str, *, assume_yes: bool, ask: Prompt | None) -> bool:
    """Whether the drop may happen: an explicit ``--yes``, or the name typed back at the prompt."""
    if assume_yes:
        return True
    if ask is None:
        return False
    return ask(f"Digite o nome da base ({name}) para confirmar, ou nada para abortar: ").strip() == name


def create(url: URL) -> int:
    """Creates the database if it is not there. Idempotent on purpose: ``db:init`` always runs it."""
    name = database_name(url)
    with _maintenance(url) as connection:
        if _exists(connection, name):
            print(f"✅ Base {name} já existe em {url.host}:{url.port}; nada a criar.")
            return 0
        _create(connection, name)
    print(f"✅ Base {name} criada em {url.host}:{url.port}.")
    return 0


def recreate(url: URL, *, assume_yes: bool, ask: Prompt | None) -> int:
    """Drops the database and creates it empty, or creates it when it is not there at all."""
    name = database_name(url)
    with _maintenance(url) as connection:
        if not _exists(connection, name):
            # Nothing to lose, so nothing to confirm.
            _create(connection, name)
            print(f"✅ Base {name} não existia em {url.host}:{url.port}; criada vazia, nada a apagar.")
            return 0
        print(f"⚠️  Isto apaga {_inspect(connection, url)}.")
        print("    Não há desfazer: a base renasce vazia, sem contas e sem catálogo — a primeira conta")
        print("    vem da tela de primeiro acesso ou de `python -m scrinalia.domains.identity.cli`.")
        if not _confirmed(name, assume_yes=assume_yes, ask=ask):
            print("Nada foi apagado.", file=sys.stderr)
            return 1
        _drop(connection, name)
        _create(connection, name)
    print(f"✅ Base {name} recriada vazia em {url.host}:{url.port}.")
    return 0


def _run_create(args: argparse.Namespace, url: URL) -> int:
    return create(url)


def _run_recreate(args: argparse.Namespace, url: URL) -> int:
    # ``input`` only when a person is at the terminal: without a TTY nobody can answer the question,
    # and ``_confirmed`` refuses instead of assuming the yes that was never given.
    return recreate(url, assume_yes=args.yes, ask=input if sys.stdin.isatty() else None)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Cria ou recria a base de dados nomeada pela configuração.")
    commands = parser.add_subparsers(dest="command", required=True)

    create_command = commands.add_parser("create", help="Cria a base se ela não existir. Não apaga nada.")
    create_command.set_defaults(handler=_run_create)

    recreate_command = commands.add_parser("recreate", help="Apaga a base e cria uma vazia. Não há desfazer.")
    recreate_command.add_argument("--yes", action="store_true", help="Não pergunta nada.")
    recreate_command.set_defaults(handler=_run_recreate)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        return args.handler(args, make_url(settings.DATABASE_URL))
    except ValueError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 1
    except SQLAlchemyError as exc:
        print(f"❌ Não foi possível falar com o banco: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
