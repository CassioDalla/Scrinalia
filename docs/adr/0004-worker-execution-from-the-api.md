# ADR 0004: Running AI workers from the API, and the ledger that makes it observable

- **Status:** Accepted
- **Date:** 2026-10-06

## Context

The nine AI workers were only reachable from the command line
(`python -m memoria_curitibana.domains.archive.workers.runner <name>`). Nothing in the
system could answer, without reading the code:

- which workers exist, in which order they run, and which engine/preset each one uses;
- which model a preset resolves to, and where it will be called;
- what is pending in each queue, and what already ran;
- whether the model server, the database and the object storage are reachable at all.

The curator SPA had no operational surface, and `TODO.md` listed health, error tracking
and scheduling as open items. The owner asked for a panel that shows the workers, their
effective configuration and their state, and that can also **configure** and **run**
them.

Two facts shaped the decision:

1. **The configuration already existed, but only in code.** Each `execute()` declares
   `engine_name`/`preset` in its signature, and each registry declares `PRESETS` with
   the model. Reading it back required nothing new; exposing it required a catalogue
   that could not drift from the signatures.
2. **Nothing recorded a run.** The per-unit stamps in `execution_log` say *that* a unit
   was processed, never *when* or *with what*, and they carry no duration or outcome. A
   ledger was the only way to answer "how is it running?".

## Decision

1. **A declarative worker catalogue** (`workers/catalogue.py`) is the single definition
   of what a worker is: order, axis, governance, stamp, and the dotted path of its queue
   counter. It imports no worker — resolving a function goes through `import_module`
   with a cache — because importing all nine modules at API start-up pulls spaCy, pandas
   and scikit-learn into a process that runs no worker (measured: ~1.7 s for spaCy
   alone).
2. **Each worker owns its queue predicate**, exposed as `count_pending(db, **options)`
   and shared with `execute()`. The panel never re-derives a predicate.
3. **A persisted override per worker**, with an audit trail, applied with the precedence
   `explicit argument > persisted override > signature default`. The override is partial:
   a field left `NULL` keeps following the code.
4. **An execution ledger** (`archive_worker_runs`) written by the runner for **both** the
   CLI and the panel, carrying the resolved configuration, the duration and the outcome.
5. **An in-process executor** in the API (`ThreadPoolExecutor`, one worker at a time by
   default), guarded by a **partial unique index** on `(worker_name)` for the rows in
   flight, and repaired at start-up: a row left `QUEUED`/`RUNNING` by a dead process
   becomes `INTERRUPTED`.
6. **The panel may trigger, not schedule.** No retry, no cron, no priority.

## Rationale

- **The concurrency guard belongs in the database.** A process-local lock does not
  survive `--reload`, and the only thing that knows a run is in flight is the row. The
  partial unique index makes a second run impossible across processes, and the API
  translates the violation into a 409 with a sentence a person can read.
- **The ledger writes through its own session.** The worker commits and rolls back per
  batch; an entry that vanished with a rollback would be worse than no ledger. It is also
  what makes the trigger race-free: the `QUEUED` row is committed *before* the executor
  thread receives the id, so the thread always finds it. Committing through the request's
  transaction was not an option — the row must be durable before the thread starts, and
  `UnitOfWork` owns the request transaction.
- **Configuration is resolved without instantiating an engine.** `describe_config` is the
  read-only twin of `get_engine`; a test captures the kwargs the factory forwards and
  asserts the two agree, so the panel cannot describe a configuration the run would not
  use.
- **The quality validator's engine is not configurable in the panel.** It comes from the
  active `LLM_CHECK` cleaning rule. A second place to choose the same engine would be a
  second source of truth; the panel reads the rule and links to the rules screen.
- **The unmeasurable queue says so.** `conflict-judge`'s pending set is the trigram
  product of tags and entities, measured at 53 s on the real collection. The panel shows
  what was already judged and the reason it does not count the rest, instead of inventing
  a number.

## Consequences

Positive: the workers are visible and configurable without reading code; every execution
leaves a durable record with the configuration it used; a missing Ollama model, an
unreachable bucket or a database that is down is visible before a run discovers it.

Negative, and accepted:

- **One API process.** The start-up recovery assumes the rows it finds are orphans. With
  `uvicorn --workers > 1`, it would kill a sibling's live run. Scaling out requires moving
  the executor (and the recovery) out of the API; the partial unique index stays valid.
- **A run in flight is not cancelled on shutdown.** The thread is not killed; the next
  boot marks the row `INTERRUPTED`. Waiting for a long inference during shutdown would
  make deploys hang.
- **The panel's queue counts are not free.** The transfer's counter validates the whole
  staging table, so `/system/workers` costs about two seconds on the real collection and
  the screen only polls while something is running.
- **The ledger records the invocation, not the work.** Processed counts per run are not
  stored: the workers return `None`. The per-unit stamps answer "how much is done"; the
  ledger answers "what ran, with what, and how it ended".

## Alternatives considered

- **A separate daemon consuming a run-request queue.** More moving parts and a new
  process to operate, for the same result while the deployment is a single API process.
  Revisit when scaling out, which is exactly when the in-process executor stops being
  valid.
- **Locking in process memory.** Rejected: does not survive a reload and does not cover a
  second process.
- **Deriving the run history from `execution_log`.** Rejected: the stamps have no
  timestamp, no duration and no outcome, and adding them per unit would write operational
  bookkeeping into every document.
- **Letting the panel write the environment (`LOG_LEVEL`, hosts).** Rejected: those are
  process configuration, and changing them at runtime either lies until a restart or
  needs a configuration subsystem the project does not have. The panel shows them.

## Revisit trigger

Reconsider if any of these becomes true: the API is deployed with more than one process;
a worker needs to run on a schedule or with retries; or the ledger has to record
per-run work counts, which would require the workers to return a result.
