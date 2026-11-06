"""Every model package, imported in one place so ``Base.metadata`` is complete.

The archive tables carry foreign keys into ``auth_users`` — the account behind a worker run and
behind a settings revision. SQLAlchemy resolves a foreign key when it flushes the write, not when it
reads, so a process that imported only the archive models could **read** the ledger and could not
**write** it: ``NoReferencedTableError`` on the insert. The CLI did exactly that, and the ledger
swallowed the failure by design, so a CLI run left no line in ``archive_worker_runs`` while the
panel's runs did — the run history quietly depended on which button was pressed.

Alembic's autogenerate and the run ledger both call :func:`load_all_models`, which is the one
definition of "the model packages" — the migration environment used to carry its own copy of the
list.
"""

from importlib import import_module

#: Imported through ``import_module`` and not as four bare imports: the bound name is never read, and
#: CodeQL's ``py/unused-import`` does not model the side effect the import is for.
MODEL_PACKAGES: tuple[str, ...] = (
    "scrinalia.domains.archive.models",
    "scrinalia.domains.diffusion.models",
    "scrinalia.domains.identity.models",
    "scrinalia.domains.ingestion.models",
    "scrinalia.domains.staging.models",
)


def load_all_models() -> None:
    """Populates ``Base.metadata`` with every table the migrations know about. Idempotent."""
    for package in MODEL_PACKAGES:
        import_module(package)
