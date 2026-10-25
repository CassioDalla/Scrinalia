"""The trial: compare configurations over one sample, writing only the ledger (ADR 0018, #71).

A trial answers the question the queue preview cannot: *is this configuration any good on this
collection, and what does it cost?* It reads a fixed sample with the same text composition, engine
registry and decision rule the worker uses, and it writes **nothing** to the archive — no
``typology_id``, no stamp, no review-queue row. The only write is the ``trial_result`` the ledger
stores when the run closes.

Two populations are measured on purpose:

* the **gabarito** — every description whose typology a person changed, read from
  ``archive_document_revisions`` (the human decision, never ``HUMAN_APPROVED`` alone). Agreement
  and coverage are measured here;
* the **production scope** — a seeded sample of the ai-writable descriptions the configurations
  would really read (the intersection of their non-stamp predicates). Distribution, abstention and
  seconds per document are measured here, because the gabarito is a hard set and not the mix the
  next run will pay for.

The engine is built once per ``(engine, preset, engine kwargs)`` and shared, so a configuration that
only changes the floor does not pay the model load twice. Cancellation is honoured at every chunk
boundary through the same ``RunControl`` the workers use.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections import Counter
from collections.abc import Callable, Sequence
from typing import Any, cast

from sqlalchemy import func, literal, select
from sqlalchemy.orm import Session

from scrinalia.core.logger import logger
from scrinalia.domains.archive.engines.classification.registry import (
    EngineName,
    PresetName,
    get_engine,
)
from scrinalia.domains.archive.exceptions import InvalidWorkerSettingsError
from scrinalia.domains.archive.models import ArchiveDocument, ArchiveDocumentRevision, ArchiveTypology
from scrinalia.domains.archive.models.enums import WorkerRunStatus
from scrinalia.domains.archive.repository import TypologyRepository
from scrinalia.domains.archive.repository.governance import ai_writable_documents
from scrinalia.domains.archive.repository.worker_settings_repo import WorkerSettingsRepository
from scrinalia.domains.archive.schemas.system_schema import (
    WorkerSettingsRequest,
    WorkerTrialConfigDTO,
    WorkerTrialMissDTO,
    WorkerTrialRequest,
    WorkerTrialResultDTO,
    WorkerTrialSampleDTO,
)
from scrinalia.domains.archive.workers import worker_typology
from scrinalia.domains.archive.workers.cancellation import RunControl, WorkerRunCancelled, checkpoint
from scrinalia.domains.archive.workers.catalogue import WORKER_CATALOGUE, WorkerSpec, count_pending
from scrinalia.domains.archive.workers.configuration import (
    RUN_ONLY_OPTIONS,
    ResolvedWorkerConfig,
    counter_options,
    effective_worker_options,
    resolve_configuration,
    validate_engine_choice,
    validate_options,
)
from scrinalia.domains.archive.workers.lease import RunLeaseMonitor
from scrinalia.domains.archive.workers.ledger import WorkerRunLedger

from .metrics import (
    ABSTAINED,
    Prediction,
    Scored,
    Truth,
    abstention_rate_of,
    agreement,
    entropy_bits,
    largest_share,
    link_decision,
)
from .text import read_composed_text

#: The default seed, recorded with the sample. Changing it changes which descriptions a trial reads;
#: the point of recording it is that the same run can be reasoned about after the collection grew.
DEFAULT_TRIAL_SEED = "scrinalia-trial-v1"

#: How many texts one ``classify`` call receives. The engine is asked for ``batch_size=1`` inside it,
#: exactly like the worker, so a document's neighbours cannot change its cost.
ENGINE_BATCH = 8

#: How many disagreements the result carries. Enough to act on, not a second copy of the sample.
MAX_MISSES = 20

TrialFn = Callable[[Session, WorkerSpec, WorkerTrialRequest, RunControl], WorkerTrialResultDTO]

#: The workers whose trial this module knows how to run. The catalogue's ``trial`` flag is the
#: list the panel offers, and a test keeps the two equal; a worker absent here is refused even if
#: the catalogue says it supports trials.
TRIALS: dict[str, TrialFn] = {}


def register(worker_name: str) -> Callable[[TrialFn], TrialFn]:
    """Registers a trial implementation under the worker's catalogue name."""

    def decorator(fn: TrialFn) -> TrialFn:
        TRIALS[worker_name] = fn
        return fn

    return decorator


def run_trial(
    worker_name: str,
    *,
    db: Session,
    request: WorkerTrialRequest,
    run_id: int,
    runner_id: str,
    ledger: WorkerRunLedger,
    lease_monitor: RunLeaseMonitor | None = None,
) -> None:
    """
    Executes one claimed trial and closes its ledger row with the result.

    The trial owns its finish, like ``run_worker`` does for a production run: a cancellation closes
    ``CANCELLED`` (a stop is not a failure), any other exception closes ``FAILED`` with the class in
    front of the message, and success writes the result in the same closing statement. The runner's
    outer handler covers what happens before this function takes over.
    """
    spec = WORKER_CATALOGUE.get(worker_name)
    fn = TRIALS.get(worker_name)
    if spec is None or fn is None:
        raise ValueError(f"O worker '{worker_name}' não tem ensaio registrado. Hoje: {sorted(TRIALS)}.")
    if not ledger.owns(run_id, runner_id):
        raise RuntimeError(f"a execução {run_id} não pertence mais ao runner '{runner_id}'")

    control = RunControl(ledger=ledger, run_id=run_id)
    if lease_monitor is not None:
        lease_monitor.track(run_id)
    try:
        # A cancellation requested while the row was queued is honoured before the model is built.
        control.checkpoint()
        result = fn(db, spec, request, control)
    except WorkerRunCancelled:
        ledger.finish(run_id, status=WorkerRunStatus.CANCELLED, runner_id=runner_id)
        return
    except BaseException as exc:
        ledger.finish(
            run_id,
            status=WorkerRunStatus.FAILED,
            error=str(exc),
            error_kind=type(exc).__name__,
            runner_id=runner_id,
        )
        raise
    else:
        ledger.finish(
            run_id,
            status=WorkerRunStatus.SUCCESS,
            runner_id=runner_id,
            trial_result=result.model_dump(mode="json"),
        )
    finally:
        if lease_monitor is not None:
            lease_monitor.release(run_id)


@register("typology")
def _typology_trial(
    db: Session, spec: WorkerSpec, request: WorkerTrialRequest, control: RunControl
) -> WorkerTrialResultDTO:
    """The typology comparison: one sample, every configuration, agreement on the human gabarito."""
    seed = request.seed or DEFAULT_TRIAL_SEED
    catalogue = list(TypologyRepository(db).get_active_typologies())
    if not catalogue:
        raise InvalidWorkerSettingsError(
            "O catálogo de tipologias ativo está vazio: o ensaio não tem contra o que classificar."
        )

    setting = WorkerSettingsRepository(db).get(spec.name)
    resolved_configs = [_resolve(db, spec, setting, config) for config in request.configs]
    options = [effective_worker_options(spec, resolved) for resolved in resolved_configs]
    columns = [list(option["columns_to_classify"]) for option in options]

    random_ids = _sample_production_scope(db, columns, request.sample, seed)
    verdicts = _read_verdicts(db)
    verdict_ids = _sample_verdicts(verdicts, request.sample, seed)
    unknown = sorted({expected for expected in verdicts.values() if expected is not None and expected not in catalogue})

    all_ids = list(dict.fromkeys([*random_ids, *verdict_ids]))
    engines: dict[str, tuple[Any, float]] = {}
    configs: list[WorkerTrialConfigDTO] = []
    for resolved, option in zip(resolved_configs, options, strict=True):
        configs.append(
            _measure(
                db=db,
                spec=spec,
                resolved=resolved,
                option=option,
                catalogue=catalogue,
                ids=all_ids,
                random_ids=random_ids,
                verdict_ids=verdict_ids,
                verdicts=verdicts,
                engines=engines,
                control=control,
            )
        )

    return WorkerTrialResultDTO(
        worker_name=spec.name,
        sample=WorkerTrialSampleDTO(
            seed=seed,
            size=request.sample,
            description_ids=random_ids,
            verdict_ids=verdict_ids,
            verdicts_available=len(verdicts),
        ),
        unknown_verdicts=unknown,
        configs=configs,
    )


def _resolve(db: Session, spec: WorkerSpec, setting: Any, config: Any) -> ResolvedWorkerConfig:
    """The configuration a run would use, with the same precedence and the same refusals."""
    validate_engine_choice(spec, config.engine_name, config.preset)
    validate_options(spec, config.options)
    if config.engine_options:
        raise InvalidWorkerSettingsError(
            "Um ensaio compara o que a tela pode salvar: 'engine_options' é um repasse de uma "
            "execução e não vira padrão, então não entra na comparação."
        )
    refused = sorted(set(config.options) & RUN_ONLY_OPTIONS)
    if refused:
        raise InvalidWorkerSettingsError(
            f"O ensaio não aceita {refused}: o tamanho da amostra é o 'sample'. Um limite por "
            "configuração mediria uma configuração diferente da que a tela pode salvar."
        )
    return resolve_configuration(
        db,
        spec,
        setting,
        engine_name=config.engine_name,
        preset=config.preset,
        db_batch_size=config.db_batch_size,
        options=config.options,
        engine_options={},
    )


def _sample_production_scope(
    db: Session, columns_per_config: Sequence[Sequence[str]], size: int, seed: str
) -> list[str]:
    """
    The seeded sample of the units every configuration would read.

    The predicate is the intersection of the configurations' **candidate** conditions — ai-writable
    and at least one of the columns it reads is not null — and deliberately not the pending queue:
    the configuration that is already applied has an empty queue, and a trial has to be able to
    re-measure it (ADR 0018). The md5 of ``seed:description_id`` is the order, so the same seed and
    a collection that only grew propose the same rows for the rows that already existed.
    """
    conditions = [ai_writable_documents()]
    conditions += [worker_typology.column_conditions(list(columns)) for columns in columns_per_config]
    stmt = (
        select(ArchiveDocument.description_id)
        .where(*conditions)
        .order_by(
            func.md5(func.concat(literal(f"{seed}:"), ArchiveDocument.description_id)),
            ArchiveDocument.description_id,
        )
        .limit(size)
    )
    return [row[0] for row in db.execute(stmt).all()]


def _read_verdicts(db: Session) -> dict[str, str | None]:
    """
    The human gabarito, read from the document's own audit ledger.

    A description's verdict is the **latest revision that changed ``typology_id``**: the dossier
    writes that revision when an archivist overrules or files the classifier, and ``update_review``
    skips a value that did not change, so a revision is a decision. ``HUMAN_APPROVED`` alone is not
    one — approving a record is not certifying every label in it (ADR 0018).

    The label is resolved from the revision's ``new`` id to the current catalogue name, so a typology
    renamed later still means the same concept; ``NULL`` is the ``NENHUMA`` class, not a missing
    verdict. A retired typology keeps its name and is reported by the caller as unknown.
    """
    changes = ArchiveDocumentRevision.changes
    latest = (
        select(
            ArchiveDocumentRevision.description_id.label("description_id"),
            changes["typology_id"]["new"].as_integer().label("typology_id"),
            func.row_number()
            .over(
                partition_by=ArchiveDocumentRevision.description_id,
                order_by=(ArchiveDocumentRevision.created_at.desc(), ArchiveDocumentRevision.revision_id.desc()),
            )
            .label("position"),
        )
        .where(changes.has_key("typology_id"))
        .subquery()
    )
    stmt = (
        select(ArchiveDocument.description_id, ArchiveTypology.name)
        .join(latest, latest.c.description_id == ArchiveDocument.description_id)
        .outerjoin(ArchiveTypology, ArchiveTypology.typology_id == latest.c.typology_id)
        .where(latest.c.position == 1)
    )
    return dict(db.execute(stmt).all())


def _sample_verdicts(verdicts: dict[str, str | None], size: int, seed: str) -> list[str]:
    """The verdict units the trial scores, capped and ordered by the same seed as the random sample."""
    ordered = sorted(verdicts, key=lambda description_id: hashlib.md5(f"{seed}:{description_id}".encode()).hexdigest())
    return ordered[:size]


def _measure(
    *,
    db: Session,
    spec: WorkerSpec,
    resolved: ResolvedWorkerConfig,
    option: dict[str, Any],
    catalogue: Sequence[str],
    ids: Sequence[str],
    random_ids: Sequence[str],
    verdict_ids: Sequence[str],
    verdicts: dict[str, str | None],
    engines: dict[str, tuple[Any, float]],
    control: RunControl,
) -> WorkerTrialConfigDTO:
    """Runs one configuration over the fixed sample and turns the answers into the contract shape."""
    checkpoint(control)
    columns = list(option["columns_to_classify"])
    threshold = float(option["confidence_threshold"])
    texts = read_composed_text(db, ids, columns)

    engine_key = _engine_key(resolved)
    load_seconds = 0.0
    if engine_key not in engines:
        started = time.perf_counter()
        engine = _build_engine(resolved)
        load_seconds = time.perf_counter() - started
        engines[engine_key] = (engine, load_seconds)
    else:
        engine = engines[engine_key][0]

    predictions: dict[str, Prediction] = {}
    seconds = 0.0
    classified = 0
    asked = [description_id for description_id in ids if texts.get(description_id)]
    for start in range(0, len(asked), ENGINE_BATCH):
        checkpoint(control)
        chunk = asked[start : start + ENGINE_BATCH]
        started = time.perf_counter()
        results = engine.classify([texts[description_id] for description_id in chunk], list(catalogue), batch_size=1)
        seconds += time.perf_counter() - started
        classified += len(chunk)
        for description_id, result in zip(chunk, results, strict=True):
            predictions[description_id] = link_decision(result, threshold)
    for description_id in ids:
        predictions.setdefault(description_id, Prediction(label=None))

    counts = Counter(predictions[description_id].label or ABSTAINED for description_id in random_ids)
    label, share = largest_share(counts)
    scored = [
        Scored(
            description_id=description_id,
            truth=_truth(verdicts[description_id]),
            prediction=predictions[description_id],
        )
        for description_id in verdict_ids
    ]
    answered = sum(1 for row in scored if row.prediction.label is not None)
    pending, pending_reason = _pending(db, spec, resolved)
    seconds_per_document = seconds / classified if classified else 0.0
    projected_hours = (
        pending * seconds_per_document / 3600 if pending is not None and seconds_per_document > 0 else None
    )

    return WorkerTrialConfigDTO(
        engine_name=resolved.engine_name,
        preset=resolved.preset,
        db_batch_size=resolved.db_batch_size,
        options=option,
        config=resolved.config,
        settings=WorkerSettingsRequest(
            engine_name=resolved.engine_name,
            preset=resolved.preset,
            db_batch_size=resolved.db_batch_size,
            options={key: value for key, value in option.items() if key not in RUN_ONLY_OPTIONS},
        ),
        pending=pending,
        pending_reason=pending_reason,
        processed=classified,
        verdicts_scored=len(scored),
        answered=answered,
        agreement=agreement(scored) if scored else None,
        coverage=answered / len(scored) if scored else 0.0,
        abstention_rate=abstention_rate_of([predictions[description_id] for description_id in random_ids]),
        distribution=dict(counts),
        largest_share=label,
        largest_share_value=share,
        entropy_bits=entropy_bits(counts),
        seconds_per_document=seconds_per_document,
        load_seconds=load_seconds,
        projected_hours=projected_hours,
        misses=[
            WorkerTrialMissDTO(
                description_id=row.description_id,
                expected=row.truth_key,
                predicted=row.key,
                score=row.prediction.score,
            )
            for row in scored
            if not row.correct
        ][:MAX_MISSES],
    )


def _pending(db: Session, spec: WorkerSpec, resolved: ResolvedWorkerConfig) -> tuple[int | None, str | None]:
    """The queue under this configuration, with the panel's own reason when it cannot be counted."""
    if spec.counter is None:
        return None, spec.unmeasurable_reason
    try:
        return int(count_pending(spec, db, **counter_options(spec, resolved))), None
    except Exception as exc:
        logger.error(f"⚠️ Não foi possível contar a fila de '{spec.name}' no ensaio: {exc}")
        return None, "A contagem falhou; veja o log do servidor."


def _truth(expected: str | None) -> Truth:
    """
    The gabarito of one verdict unit, as the metric expects it.

    ``None`` is the ``NENHUMA`` class (the person decided no typology applies), and a name is one
    acceptable answer. The database read already collapses the latest revision to one value; this
    only turns it into the metric's frozen shape.
    """
    return Truth(labels=None if expected is None else frozenset({expected}))


def _engine_key(resolved: ResolvedWorkerConfig) -> str:
    """Identity of the engine instance: two configurations that differ only in response share it."""
    return f"{resolved.engine_name}:{resolved.preset}:{json.dumps(resolved.engine_kwargs, sort_keys=True, default=str)}"


def _build_engine(resolved: ResolvedWorkerConfig) -> Any:
    """
    Builds the engine through the registry; kept in one function so the test can replace it.

    The casts are the registry's own contract: ``resolve_configuration`` has already resolved a
    signature worker's engine/preset to a registered pair, and ``get_engine`` takes the literal
    names the registry declares.
    """
    return get_engine(
        cast(EngineName, resolved.engine_name),
        cast(PresetName, resolved.preset),
        **resolved.engine_kwargs,
    )


__all__ = ["DEFAULT_TRIAL_SEED", "TRIALS", "register", "run_trial"]
