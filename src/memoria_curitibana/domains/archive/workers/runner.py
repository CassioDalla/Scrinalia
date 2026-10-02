from __future__ import annotations

import argparse
import inspect
from collections.abc import Callable
from typing import Any

from memoria_curitibana.core.database import get_db
from memoria_curitibana.core.logger import logger
from memoria_curitibana.domains.archive.workers import (
    worker_archive_transfer,
    worker_cleaning_regex,
    worker_ner,
    worker_resolve_tag_entity_conflict,
    worker_thumbnail,
    worker_typology,
)

WorkerFn = Callable[..., None]

# Registry of executable workers. The key is the CLI name.
WORKERS: dict[str, WorkerFn] = {
    "transfer": worker_archive_transfer.execute,
    "cleaning": worker_cleaning_regex.execute,
    "ner": worker_ner.execute,
    "typology": worker_typology.execute,
    "thumbnail": worker_thumbnail.execute,
    "conflict-judge": worker_resolve_tag_entity_conflict.execute,
}

# Recommended execution order for the enrichment pipeline.
PIPELINE_ORDER = ["transfer", "cleaning", "ner", "typology", "thumbnail", "conflict-judge"]


def run_worker(
    name: str,
    *,
    engine_name: str | None = None,
    preset: str | None = None,
    db_batch_size: int | None = None,
    extra: dict[str, Any] | None = None,
    db_factory: Callable[[], Any] = get_db,
) -> None:
    """
    Opens a database session and dispatches to the requested worker.

    Options are forwarded only when the target function declares them, so the
    same CLI works for workers with different signatures (and the session
    parameter may be named either ``db`` or ``db_session``).
    """
    if name not in WORKERS:
        raise ValueError(f"Unknown worker '{name}'. Options: {sorted(WORKERS)}")

    fn = WORKERS[name]
    params = inspect.signature(fn).parameters
    accepts_var_kwargs = any(param.kind == inspect.Parameter.VAR_KEYWORD for param in params.values())

    session_arg = "db_session" if "db_session" in params else "db"

    kwargs: dict[str, Any] = {}
    for key, value in (("engine_name", engine_name), ("preset", preset), ("db_batch_size", db_batch_size)):
        if value is not None and (key in params or accepts_var_kwargs):
            kwargs[key] = value

    for key, value in (extra or {}).items():
        if key in params or accepts_var_kwargs:
            kwargs[key] = value

    logger.info(f"🚀 Runner executing the worker '{name}'...")
    with db_factory() as db:
        kwargs[session_arg] = db
        fn(**kwargs)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Unified runner for the Archive layer workers.")
    parser.add_argument("worker", choices=sorted(WORKERS), help="Name of the worker to run.")
    parser.add_argument("--engine", dest="engine_name", help="Registered AI engine (e.g. spacy_ner).")
    parser.add_argument("--preset", dest="preset", help="Engine preset (e.g. gpu, cpu_local).")
    parser.add_argument("--batch", dest="db_batch_size", type=int, help="Batch size per transaction.")
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
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
