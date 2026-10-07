from __future__ import annotations

import argparse
import inspect
from collections.abc import Callable
from typing import Any

from memoria_curitibana.core.database import get_db
from memoria_curitibana.core.logger import logger
from memoria_curitibana.domains.archive.models.enums import WorkerRunStatus, WorkerRunTrigger
from memoria_curitibana.domains.archive.repository.worker_settings_repo import WorkerSettingsRepository
from memoria_curitibana.domains.archive.workers import (
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
from memoria_curitibana.domains.archive.workers.catalogue import WORKER_CATALOGUE
from memoria_curitibana.domains.archive.workers.configuration import resolve_configuration
from memoria_curitibana.domains.archive.workers.ledger import WorkerRunLedger

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
# last: it depends on the tags already existing and on the curators having registered the
# categories (usually from a cluster suggestion) it classifies against. The embedding
# step runs after every worker that can change the document text, because it embeds that
# text and keys its stamp on a hash of it. The quality validator runs before it: it
# reads the tags, the typology and the entities the earlier workers produced.
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


def _coerce_option(value: Any) -> Any:
    """Turns the CLI ``true``/``false`` strings into booleans.

    ``--option force=false`` used to arrive as the truthy string ``"false"``, so a
    boolean flag could not be switched off from the command line. Values that are not
    strings (a programmatic caller passing a real bool or number) are left untouched.
    """
    if not isinstance(value, str):
        return value

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
    extra: dict[str, Any],
) -> dict[str, Any]:
    """
    Forwards only what the target function declares.

    The same CLI has to work for workers with different signatures (and the session parameter may be
    named either ``db`` or ``db_session``); a value the worker does not declare is dropped, except
    through ``**engine_kwargs``, which is the documented way to override ``device`` or ``host``.
    """
    params = inspect.signature(fn).parameters
    accepts_var_kwargs = any(param.kind == inspect.Parameter.VAR_KEYWORD for param in params.values())

    kwargs: dict[str, Any] = {}
    for key, value in (("engine_name", engine_name), ("preset", preset), ("db_batch_size", db_batch_size)):
        if value is not None and (key in params or accepts_var_kwargs):
            kwargs[key] = value

    for key, value in extra.items():
        if key in params or accepts_var_kwargs:
            kwargs[key] = _coerce_option(value)
    return kwargs


def run_worker(
    name: str,
    *,
    engine_name: str | None = None,
    preset: str | None = None,
    db_batch_size: int | None = None,
    extra: dict[str, Any] | None = None,
    db_factory: Callable[[], Any] = get_db,
    ledger: WorkerRunLedger | None = None,
    run_id: int | None = None,
    trigger: WorkerRunTrigger = WorkerRunTrigger.CLI,
    requested_by: str | None = None,
) -> None:
    """
    Resolves the configuration, opens a database session and dispatches to the requested worker.

    The configuration follows ``explicit argument > persisted override > signature default``; the
    override is read through the worker's own session, because that is the session the run already
    opens. When a worker is registered in ``WORKERS`` but not in the catalogue (the tests inject
    doubles that way), the resolution is skipped and the explicit arguments are forwarded as before.

    ``ledger``/``run_id`` are how the execution becomes visible in the panel: the CLI passes a
    ledger and no id (the runner opens the row), the API passes the id of the row it queued. A
    programmatic caller that passes neither runs without a ledger line — explicit, not silent.
    """
    if name not in WORKERS:
        raise ValueError(f"Unknown worker '{name}'. Options: {sorted(WORKERS)}")

    fn = WORKERS[name]
    params = inspect.signature(fn).parameters
    session_arg = "db_session" if "db_session" in params else "db"

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
    parser.add_argument("--by", dest="requested_by", help="Quem está executando (texto livre, sem auth).")
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
        extra=extra,
        ledger=WorkerRunLedger(),
        trigger=WorkerRunTrigger.CLI,
        requested_by=args.requested_by,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
