# ADR 0014: The workers leave the API — the ledger as the queue, a runner and its lease

- **Status:** Accepted
- **Date:** 2026-10-25

## Context

ADR 0004 put the AI workers inside the API process: a `ThreadPoolExecutor` with one worker at a
time, a `QUEUED` row written through its own committed session, the partial unique index
`uq_worker_run_active` as the concurrency guard, and a start-up routine that marks every
`QUEUED`/`RUNNING` row it finds as `INTERRUPTED`. It recorded its own limit in the same document:
that recovery is only correct with **one** API process, because with `uvicorn --workers > 1` it
would kill a sibling's live run. The revisit trigger was "the API is deployed with more than one
process".

The 1.6 milestone changes the topology instead: the API and the database live on a VPS, and the
models live on a machine with a GPU. The installation guide already tells the operator to run the
worker CLI on that GPU host, which means the host already reaches PostgreSQL. What is missing is a
process that drains a queue — not a new transport, and not a second source of truth.

The pieces the queue needs already exist, and that is the argument for reusing them:

- `archive_worker_runs` carries `QUEUED`, `RUNNING`, `SUCCESS`, `FAILED` and `INTERRUPTED`, with
  `queued_at`, `started_at`, `finished_at`, `duration_ms`, the resolved `config`, the effective
  `options` and the generated `error_fingerprint`. The `QUEUED` state exists on purpose: the ledger
  does not lie about the start time.
- `uq_worker_run_active` is a partial unique index on `(worker_name) WHERE status IN ('QUEUED',
  'RUNNING')` — a guarantee made by PostgreSQL, not by a process lock that `--reload` would drop.
- The ledger writes through its own committed session, so the row is durable before any executor
  sees it.
- The operations panel already reads the active and last run per worker, and the failure screen
  reads the fingerprint.

Reading the code also found four gaps that a queue makes visible and that the old in-memory hand-off
hid:

1. The row does **not** carry the request. `config` is the `describe_config` output; `db_batch_size`,
   the worker `options` and the raw `engine_options` lived only in the `ResolvedWorkerConfig` that
   the API passed to its thread. A runner that reads the row from the database cannot reproduce the
   run.
2. `mark_running` only updates `WHERE status = 'QUEUED'`. If a claim has already moved the row to
   `RUNNING`, the effective options are never recorded.
3. The CLI executes too (`create_running`) and has no lease. Today only the API's boot repairs a
   crashed CLI run; removing that recovery without giving the CLI a lease would leave a `RUNNING`
   row blocking its worker forever.
4. The panel has no concept of a live runner or of its capabilities, so it cannot answer "why did
   nothing happen?" after a run was accepted.

The milestone also defers two pieces deliberately: scheduling and retry are #43, and cancellation is
#72. This ADR fixes their vocabulary now so they do not invent a second one later.

## Decision

1. **The ledger is the queue.** A `QUEUED` row in `archive_worker_runs` *is* the work item. There is
   no broker and no HTTP claim endpoint. The row gains a `request` JSONB column carrying the
   validated request (`engine_name`, `preset`, `db_batch_size`, `options`, `engine_options`), so a
   runner can reproduce the execution from the database alone. The runner re-resolves at claim under
   the existing precedence (`explicit > persisted > signature default`) and `record_start` writes the
   **effective** engine, preset, config and options. The `QUEUED` configuration is the promise; the
   `RUNNING` configuration is the truth. The instruction is not frozen: the quality validator takes
   its engine from the *active* `LLM_CHECK` rule, and freezing it would execute a model that is no
   longer the rule's.

2. **The runner is a process, and the claim is one database statement.** A runner is started with
   `python -m scrinalia.domains.archive.workers.runner_daemon` (name, capabilities, concurrency and
   timings are flags). `claim_next` selects one `QUEUED` row whose worker the runner advertises,
   `ORDER BY queued_at, id`, `FOR UPDATE SKIP LOCKED`, and updates it to `RUNNING` with `runner_id`,
   `started_at`, `heartbeat_at` and `lease_expires_at` in the same statement. `uq_worker_run_active`
   remains the guard: the queue is **one slot per worker**, not a backlog, and a second request
   while the slot is occupied is a 409.

3. **The protocol vocabulary.** `queued` is `QUEUED` with no runner; `claimed` is `RUNNING` with a
   `runner_id` and a lease; `heartbeat` is `heartbeat_at`/`lease_expires_at` renewed by the runner;
   `done` is `SUCCESS`; `failed` is `FAILED`; a claim whose runner disappeared is `INTERRUPTED` when
   the lease expires. `cancelled` (and the `cancel_requested_at` request that precedes it) is
   reserved by decision 9 and implemented in #72.

4. **The lease is the liveness proof, and it uses the database clock.** The runner renews its
   runs — and its own row — every 15 s with a 60 s lease by default (both configurable; the lease
   must exceed the heartbeat). Every timestamp is produced by `now()` in SQL, never by the runner's
   clock: the VPS and the GPU host are different machines. A runner that dies stops renewing; the
   lease expires; the next runner (at start and on each poll) marks only expired `RUNNING` rows as
   `INTERRUPTED`. The API no longer recovers anything at boot. `record_start`, `heartbeat` and
   `finish` are fenced by `runner_id`: a runner that lost its lease updates nothing and logs it. The
   fence covers the **ledger**, not the archive writes; the per-unit stamps make a re-run idempotent,
   and a hard fence on every write is recorded below as an accepted residual.

5. **A runner registry backs the panel.** `archive_worker_runners` records `runner_id`, name,
   hostname, package version, `capabilities` (the worker names it accepts), concurrency, heartbeat
   interval, `started_at`, `last_heartbeat_at` and `stopped_at`. The panel reads it and answers
   "which runners are online?", "can any of them run this worker?" and "who claimed this row?". The
   API never talks to a runner.

6. **A runner is authenticated as a PostgreSQL client, not as an HTTP client.** Every worker is a
   database client by construction: it reads the composed text, writes stamps, tags, entities and
   review rows. A runner that could not reach the database could not run a worker, so an HTTP token
   would protect a second door to the same room without removing the database credential. The runner
   connects with TLS (`DB_SSLMODE`, default `prefer`; `verify-full` with a CA for a remote database)
   over a private network, a WireGuard/Tailscale mesh or an SSH tunnel, and may use its own
   `RUNNER_DATABASE_URL` so it can hold a **least-privilege role** (`scrinalia_runner`: no
   `auth_users`/`auth_sessions`, no DDL, `SELECT` on `alembic_version`, DML on the archive, the
   ledger and the registry). The role is hardening: the worker still has archival write authority,
   which is its nature.

7. **The API only enqueues; the CLI stays a one-shot runner.** `POST /system/workers/{name}/runs`
   validates the request, resolves the configuration for the panel, writes the `QUEUED` row through
   the ledger's own committed session and returns 201. The API has no thread pool, no start-up
   recovery and no executor dependency; it becomes stateless across processes, so
   `uvicorn --workers > 1` is allowed. The login rate limiter remains a per-process brake (ADR 0009);
   the durable lockout is the database column. The CLI (`runner <name>`) keeps running in the
   foreground: it creates a `RUNNING` row with its own `runner_id`, lease and heartbeat, and a crash
   is repaired by the next CLI or runner. `WORKER_RUNTIME_MAX_WORKERS` is removed; the runner's
   `--concurrency` replaces it.

8. **Retry is the scheduler's, and this ADR defines the policy that #43 implements.** A retry is a
   **new row per attempt**, created only after the previous row is terminal, so the partial unique
   index is never violated. It copies `request`, sets `attempt = previous + 1`,
   `retry_of = previous.run_id` and `not_before = now() + backoff`. A manual or CLI run is a single
   execution the operator asked for and is never retried automatically. A **scheduled** run that ends
   `FAILED` or `INTERRUPTED` is retried up to three attempts with exponential backoff
   (`60 s × 2^(attempt-1)`, ±20% jitter, cap 30 min). `CANCELLED` is never retried. The claim query
   gains `AND (not_before IS NULL OR not_before <= now())` when #43 adds the column. The scheduler is
   exactly one process, decided in the database (a schedules table claimed with `FOR UPDATE SKIP
   LOCKED`, or an advisory lock), and a tick that fires while a run is active is **skipped**, not
   queued: the queue is a slot. A missed tick is one catch-up, not a replay. `WorkerRunTrigger` gains
   `SCHEDULE` (additive). The runner does not retry; it reports.

9. **Cancellation is a request, not a status that frees the slot, and #72 implements it.** The row
   gains `cancel_requested_at`; it stays `QUEUED`/`RUNNING` and keeps `uq_worker_run_active` until the
   request is honoured. A `QUEUED` row that no runner has claimed is closed `CANCELLED` immediately
   by the API. A running row is cooperative: the worker checks the flag once per batch (one function,
   gated by a test that walks the catalogue), commits the current batch and finishes `CANCELLED` with
   what it did; a torch forward pass is not interruptible, so the granularity is one batch. `CANCELLED`
   is an additive status and is never retried. A process death is `INTERRUPTED`, not `CANCELLED`.

10. **Two machines, one release.** The runner compares `alembic_version` with the head of the
    `migrations/` directory at start-up and refuses to run against a schema that is behind its code;
    it records its package version in the registry so the panel can show a mismatch. The deploy order
    is migrate → API → runner. The schema change is additive; the migration also closes the active
    rows left by the old executor once, with a sentence that explains the transition.

11. **Local development uses the same topology.** `bun run dev` starts the database, the API, the
    runner and the SPA. There is deliberately no in-process fallback: a second execution path would
    be the one nobody exercises in production.

## Rationale

- **The database already has the guarantee and the record.** A broker would be a second source of
  truth for "in flight", with a reconciliation between the broker and the ledger. ADR 0005 chose
  local observability for the same reason: an institution installs the system on the database it
  already requires.
- **The GPU host already needs the database.** The install guide's CLI workflow has always required
  it. The change adds a process and a credential, not a new data path.
- **`FOR UPDATE SKIP LOCKED` is a work queue with no application lock.** The claim is one statement;
  the partial index prevents two active rows per worker; multiple runners are safe without
  coordination.
- **The database clock is the only shared clock.** A lease that used the runner's clock would expire
  early or late by whatever the two hosts disagree on.
- **A heartbeat replaces a boot-time guess.** The old recovery had to assume one process; a lease
  says "alive" without counting processes, and expires only what stopped renewing.
- **The fence belongs on the ledger.** It is what prevents a zombie from closing another runner's
  row. Fencing every archive write would touch every repository and every worker; the stamps already
  make a re-run idempotent.
- **The request on the row is what makes the row a work item.** Without it the queue would depend on
  the process that accepted the request — the very dependency this change removes.
- **The no-token decision is about capability, not ceremony.** A token for an HTTP claim channel
  grants nothing the database credential does not, and it would add a second contract, a second
  credential and a long-poll.
- **The CLI as a one-shot runner keeps `run now` honest** and gives the CLI the same orphan recovery
  as the daemon. A CLI that only enqueued would turn a synchronous operator command into "wait for a
  runner".
- **One execution path in development** is what keeps the panel's "no runner" state exercised by the
  people writing the code.

## Consequences

Positive:

- The executor and its single-process assumption leave the API. The API can run with several
  processes; the queue and the ledger are the only shared state.
- The workers run on the machine with the GPU, and an API restart no longer kills a run.
- Every execution, from the CLI or the panel, has a durable row and a lease; an orphan is repaired
  by a heartbeat, not by the next boot.
- The panel can answer "is a runner online?", "which worker can it run?" and "who claimed this row?".
- A run survives the restart of the process that requested it: the queue is durable.

Negative, accepted:

- **The database is reachable from the GPU host.** TLS, a private network/tunnel and the
  least-privilege role reduce the exposure; they do not remove the runner's archival write authority.
- **The lease is not a fencing token.** A run continues to write after its lease expired; the next
  runner may re-run it. The stamps make the second run idempotent and the ledger fence keeps the row
  honest, but a concurrent duplicate is possible after the lease. A hard fence is future work.
- **The queue is one slot per worker.** No backlog, no priority; a scheduler must coalesce. A backlog
  would be a different decision.
- **No retry and no cancellation in this change.** A failed run stays failed; a queued run waits; a
  running one cannot be stopped. #43 and #72 own them, and this ADR fixes the vocabulary they use.
- **A queued run with no runner online waits indefinitely.** The panel shows the runner list and the
  `QUEUED` row; #72 adds the way out.
- **The operations panel is still not free.** `/system/workers` costs about two seconds on the real
  collection because of the transfer's queue counter; the screen polls only while a run is active
  (5 s), at a slower pace while a run is queued (15 s), and not at all when idle.
- **Two machines, one release.** The schema check and the recorded version make a mismatch visible;
  the deploy order has to be followed.
- **A runner is another process to operate** — a service, its logs, its model cache and its database
  credential. The install guide gains the process and the network path.

## Alternatives considered

- **An HTTP claim protocol with a runner token.** Rejected: the runner still needs the database to
  execute the workers as they are; the token would protect a claim channel that grants nothing the
  database credential does not, and would add a second credential, a second contract and a long-poll.
  Revisit if a runner must run without database credentials — which would require the workers to
  receive their data over HTTP, a different design.
- **A Redis/RQ/Celery broker.** Rejected: a second source of truth for "in flight", a second thing to
  install, and a reconciliation with the ledger. The project's value is installability on the
  database it already requires.
- **A remote inference service on the GPU host.** Rejected: it does not move the executor; it
  refactors every engine; a long embedding sweep would still run inside the API. That is a decision
  about the engines, not about the workers.
- **An in-process executor behind a development flag.** Rejected: two execution paths, and the one
  that ships would be the one not exercised daily.
- **Freezing the fully resolved instruction at enqueue.** Rejected: the quality validator's engine is
  the active `LLM_CHECK` rule; freezing it would execute a model that is no longer the rule's.
- **A fencing token checked by every write.** Rejected for this change: it would touch every
  repository and every worker. The stamps already make a re-run idempotent and the ledger is fenced.
  Revisit if a duplicate execution is observed.
- **`LISTEN/NOTIFY` instead of polling.** Rejected for now: a persistent connection, reconnect
  logic and a second wake-up path, for a queue that is one indexed query every couple of seconds.
- **Recovering orphans at API boot.** Rejected: it is exactly the single-process assumption this
  change removes.

## Revisit trigger

Reconsider if any of these becomes true:

- the database cannot be exposed to the runner's host, or an institution requires a runner without
  database credentials;
- a backlog or a priority is needed (more than one active run per worker), or a schedule must queue
  behind a running one;
- a duplicate execution is observed after a lease expiry, making a hard fence necessary;
- the poll's query load or the panel's queue counts become measurable;
- a runner must run several models at once (concurrency and GPU memory), or the scheduler and the
  runner become one process.
