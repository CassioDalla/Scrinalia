from __future__ import annotations

import argparse
import inspect
from collections.abc import Callable
from typing import Any

from scrinalia.core.author import Author
from scrinalia.core.cli import positive_int
from scrinalia.core.database import get_db
from scrinalia.core.logger import logger
from scrinalia.domains.archive.exceptions import InvalidWorkerSettingsError
from scrinalia.domains.archive.models.enums import WorkerRunStatus, WorkerRunTrigger
from scrinalia.domains.archive.repository.worker_settings_repo import WorkerSettingsRepository
from scrinalia.domains.archive.workers import (
    worker_archive_transfer,
    worker_cleaning_regex,
    worker_embedding,
    worker_macro_category,
    worker_ner,
    worker_quality_validator,
    worker_resolve_tag_entity_conflict,
    worker_thumbnail,
    worker_typology,
)
from scrinalia.domains.archive.workers.catalogue import WORKER_CATALOGUE
from scrinalia.domains.archive.workers.configuration import resolve_configuration
from scrinalia.domains.archive.workers.ledger import WorkerRunLedger

WorkerFn = Callable[..., None]

# Registry of executable workers. The key is the CLI name.
WORKERS: dict[str, WorkerFn] = {
    "transfer": worker_archive_transfer.execute,
    "cleaning": worker_cleaning_regex.execute,
    "ner": worker_ner.execute,
    "typology": worker_typology.execute,
    "thumbnail": worker_thumbnail.execute,
    "conflict-judge": worker_resolve_tag_entity_conflict.execute,
    "macro-category": worker_macro_category.execute,
    "quality-validator": worker_quality_validator.execute,
    "embedding": worker_embedding.execute,
}

# Recommended execution order for the enrichment pipeline. The macro-category step runs
# after the workers that produce tags: it depends on the tags already existing and on the
# curators having registered the categories (usually from a cluster suggestion) it
# classifies against. The quality validator comes next, because it reads the tags, the
# typology and the entities the earlier workers produced. The embedding step runs last,
# after every worker that can change the document text, because it embeds that text and
# keys its stamp on a hash of it.
PIPELINE_ORDER = [
    "transfer",
    "cleaning",
    "ner",
    "typology",
    "thumbnail",
    "conflict-judge",
    "macro-category",
    "quality-validator",
    "embedding",
]


def _workers_declaring(key: str) -> list[str]:
    """The registered workers whose ``execute`` declares ``key``; used to keep a refusal honest."""
    return sorted(name for name, fn in WORKERS.items() if key in inspect.signature(fn).parameters)


def _coerce_option(key: str, value: Any, declared: Any) -> Any:
    """
    Coerces a CLI string to the type the worker declared for that option.

    ``--option force=false`` used to arrive as the truthy string ``"false"``, so a boolean flag
    could not be switched off from the command line. Numbers had the worse failure: they arrived as
    strings, and ``confidence_score > "0.6"`` is a ``TypeError`` at the bottom of a run instead of a
    refusal at the top — which is why a declared business threshold was unreachable in practice even
    for a worker that declared it. The declared default is what tells the types apart: it is the
    type the worker already wrote in its signature, so nothing new has to be declared twice.

    Values that are not strings (a programmatic caller passing a real bool or number) are left
    untouched, and an option whose declaration is a list or an object is refused rather than
    forwarded as a string the worker would iterate character by character.
    """
    if not isinstance(value, str):
        return value

    if isinstance(declared, bool):
        lowered = value.strip().lower()
        if lowered not in {"true", "false"}:
            raise InvalidWorkerSettingsError(f"A opção '{key}' é booleana: use true ou false, não {value!r}.")
        return lowered == "true"

    if isinstance(declared, int):
        try:
            return int(value)
        except ValueError as error:
            raise InvalidWorkerSettingsError(f"A opção '{key}' espera um inteiro, não {value!r}.") from error

    if isinstance(declared, float):
        try:
            return float(value)
        except ValueError as error:
            raise InvalidWorkerSettingsError(f"A opção '{key}' espera um número, não {value!r}.") from error

    if isinstance(declared, (list, tuple, dict)):
        raise InvalidWorkerSettingsError(
            f"A opção '{key}' espera uma lista ou um objeto: ela não é configurável pela linha de comando."
        )

    lowered = value.strip().lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    return value


def _forward_kwargs(
    fn: WorkerFn,
    *,
    engine_name: str | None,
    preset: str | None,
    db_batch_size: int | None,
    limit: int | None,
    extra: dict[str, Any],
) -> dict[str, Any]:
    """
    Forwards only what the target function declares.

    The same CLI has to work for workers with different signatures (and the session parameter may be
    named either ``db`` or ``db_session``); a value the worker does not declare is dropped, except
    through ``**engine_kwargs``, which is the documented way to override ``device`` or ``host``.

    A dropped value is logged: ``--batch`` was accepted by every name and silently ignored by the
    workers without ``db_batch_size``, so a run that asked for a small batch swept the whole backlog
    and looked like it had honoured the flag. A flag nobody reads is worse than a refused one.
    """
    params = inspect.signature(fn).parameters
    accepts_var_kwargs = any(param.kind == inspect.Parameter.VAR_KEYWORD for param in params.values())

    kwargs: dict[str, Any] = {}
    for key, value in (
        ("engine_name", engine_name),
        ("preset", preset),
        ("db_batch_size", db_batch_size),
        ("limit", limit),
    ):
        if value is None:
            continue
        if key in params or accepts_var_kwargs:
            kwargs[key] = value
        else:
            logger.warning(f"⚠️ The worker does not declare '{key}': the value {value!r} was ignored.")

    for key, value in extra.items():
        if key in params or accepts_var_kwargs:
            kwargs[key] = _coerce_option(key, value, params[key].default if key in params else None)
    return kwargs


def run_worker(
    name: str,
    *,
    engine_name: str | None = None,
    preset: str | None = None,
    db_batch_size: int | None = None,
    limit: int | None = None,
    extra: dict[str, Any] | None = None,
    db_factory: Callable[[], Any] = get_db,
    ledger: WorkerRunLedger | None = None,
    run_id: int | None = None,
    trigger: WorkerRunTrigger = WorkerRunTrigger.CLI,
    requested_by: Author | None = None,
) -> None:
    """
    Resolves the configuration, opens a database session and dispatches to the requested worker.

    The configuration follows ``explicit argument > persisted override > signature default``; the
    override is read through the worker's own session, because that is the session the run already
    opens. When a worker is registered in ``WORKERS`` but not in the catalogue (the tests inject
    doubles that way), the resolution is skipped and the explicit arguments are forwarded as before.

    ``limit`` caps the units of this one run and is **not** a persisted setting: it exists so a local
    test does not sweep the backlog, and a cap that outlived the command would be a trap. It is
    refused for a worker whose ``execute`` does not declare it, instead of being dropped.

    ``ledger``/``run_id`` are how the execution becomes visible in the panel: the CLI passes a
    ledger and no id (the runner opens the row), the API passes the id of the row it queued. A
    programmatic caller that passes neither runs without a ledger line — explicit, not silent.
    """
    if name not in WORKERS:
        raise ValueError(f"Unknown worker '{name}'. Options: {sorted(WORKERS)}")

    fn = WORKERS[name]
    params = inspect.signature(fn).parameters
    session_arg = "db_session" if "db_session" in params else "db"

    if limit is not None and "limit" not in params:
        # ``**engine_kwargs`` does not count: it is the documented door for engine-constructor
        # overrides (``device``, ``host``), and a run cap that fell into it would be handed to the
        # engine and ignored — exactly the silent drop this refusal exists to prevent.
        raise InvalidWorkerSettingsError(
            f"O worker '{name}' não aceita --limit: ele não declara 'limit' no execute. "
            f"Quem declara hoje: {_workers_declaring('limit')}."
        )

    spec = WORKER_CATALOGUE.get(name)
    explicit_extra = extra or {}

    logger.info(f"🚀 Runner executing the worker '{name}'...")
    with db_factory() as db:
        if spec is None:
            resolved_engine, resolved_preset, resolved_batch = engine_name, preset, db_batch_size
            forwarded = explicit_extra
            run_config: dict[str, Any] = {}
        else:
            setting = WorkerSettingsRepository(db).get(name)
            resolved = resolve_configuration(
                db,
                spec,
                setting,
                engine_name=engine_name,
                preset=preset,
                db_batch_size=db_batch_size,
                options=explicit_extra,
            )
            resolved_engine, resolved_preset, resolved_batch = (
                resolved.engine_name,
                resolved.preset,
                resolved.db_batch_size,
            )
            forwarded = resolved.forwarded_options
            run_config = resolved.config

        if ledger is not None:
            if run_id is None:
                run_id = ledger.start(
                    name,
                    trigger=trigger,
                    requested_by=requested_by,
                    engine_name=resolved_engine,
                    preset=resolved_preset,
                    config=run_config,
                )
            else:
                ledger.mark_running(run_id)

        kwargs = _forward_kwargs(
            fn,
            engine_name=resolved_engine,
            preset=resolved_preset,
            db_batch_size=resolved_batch,
            limit=limit,
            extra=forwarded,
        )
        kwargs[session_arg] = db

        try:
            fn(**kwargs)
        except BaseException as exc:
            if ledger is not None and run_id is not None:
                ledger.finish(run_id, status=WorkerRunStatus.FAILED, error=str(exc), error_kind=type(exc).__name__)
            raise
        else:
            if ledger is not None and run_id is not None:
                ledger.finish(run_id, status=WorkerRunStatus.SUCCESS)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Unified runner for the Archive layer workers.")
    parser.add_argument("worker", choices=sorted(WORKERS), help="Name of the worker to run.")
    parser.add_argument("--engine", dest="engine_name", help="Registered AI engine (e.g. spacy_ner).")
    parser.add_argument("--preset", dest="preset", help="Engine preset (e.g. gpu, cpu_local).")
    parser.add_argument("--batch", dest="db_batch_size", type=int, help="Batch size per transaction.")
    parser.add_argument(
        "--limit",
        dest="limit",
        type=positive_int,
        help="Cap on the units this run touches; accepted by the workers that declare 'limit'.",
    )
    parser.add_argument(
        "--by",
        dest="requested_by",
        help="Quem está executando: texto livre, porque a CLI roda no host e não tem sessão.",
    )
    parser.add_argument(
        "--option",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Extra parameter forwarded to the worker (can be repeated).",
    )
    args = parser.parse_args(argv)

    extra: dict[str, str] = {}
    for item in args.option:
        key, separator, value = item.partition("=")
        if not separator:
            parser.error(f"Invalid option '{item}'. Use KEY=VALUE.")
        extra[key] = value

    run_worker(
        args.worker,
        engine_name=args.engine_name,
        preset=args.preset,
        db_batch_size=args.db_batch_size,
        limit=args.limit,
        extra=extra,
        ledger=WorkerRunLedger(),
        trigger=WorkerRunTrigger.CLI,
        requested_by=Author(name=args.requested_by) if args.requested_by else None,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
