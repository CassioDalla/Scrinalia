# ADR 0015: Schedules and retries — one cron per worker, one scheduler, one row per attempt

- **Status:** Accepted
- **Date:** 2026-10-25
- **Amends:** ADR 0014

## Context

ADR 0014 moved the workers out of the API and defined the queue: the ledger is the queue, a runner
claims a `QUEUED` row with a lease, and the API only enqueues. It also fixed the vocabulary for the
two pieces it deferred — scheduling and retry — and left the model to #43:

- a retry is a **new row per attempt**, created after the previous row is terminal, carrying
  `attempt`, `retry_of` and `not_before`;
- only a **scheduled** run is retried; a manual or CLI run is one execution the operator asked for;
- a scheduled run that ends `FAILED`/`INTERRUPTED` is retried up to three attempts with
  `60 s × 2^(attempt-1)`, ±20% jitter, cap 30 min; `CANCELLED` is never retried;
- the scheduler is **exactly one process**, decided in the database, and a tick that fires while a
  run is active is skipped, not queued;
- a missed tick is **one catch-up**, not a replay;
- the runner does not retry; it reports.

What the ADR did not settle is the schedule itself: what a schedule is, how the period is expressed,
where the scheduler runs, how one instance is guaranteed, and what "scheduled" means in the panel.
Those are the questions this ADR answers, and they change the data model (one table and three
columns), the claim, the panel and the deploy.

Two constraints shape the answer:

- **The queue is one slot per worker.** `uq_worker_run_active` is a partial unique index on
  `(worker_name) WHERE status IN ('QUEUED','RUNNING')`; a schedule cannot create a backlog, and a
  tick while a run is active has nowhere to go. A retry that sits `QUEUED` with a future
  `not_before` therefore *does* occupy the slot.
- **The database is the clock and the record.** The lease already uses PostgreSQL's `now()`, and the
  schedule has to survive a restart: the period, the last run and the next run belong in the
  database, not in the scheduler's memory.

The issue also asks for the panel to show a scheduled worker **as scheduled** and for the
pending/processed counters to stay truthful. They are two different numbers: the counters are the
worker's queue (the units), and "scheduled" is a property of the worker's agenda. The panel must not
turn one into the other.

## Decision

1. **A schedule is one row per worker.** `archive_worker_schedules` has `worker_name` as its primary
   key, plus `enabled`, `cron` (a five-field expression), `timezone` (an IANA name), `request` (the
   validated `WorkerRunRequest`), `next_run_at`, `last_enqueued_at`, `last_skipped_at`,
   `updated_by`/`updated_by_user_id`, `created_at`/`updated_at`. One worker, one agenda: the queue
   is one slot, so two schedules for the same worker would only collide with each other. An
   institution that wants two rhythms for one worker has two workers' worth of configuration and
   two runs it will have to merge anyway; that is a new decision, not a column.

2. **The request is pinned in the schedule.** The schedule stores the same body the panel's
   "Enfileirar execução" sends, validated against the worker's catalogue at save time (the engine,
   the preset, the options and the engine options). The enqueue resolves the **configuration** from
   that request under the existing precedence (`explicit > persisted settings > signature default`),
   so the parts the schedule did not name still follow the persisted settings — the same promise the
   manual trigger makes. Changing the settings does **not** change a schedule until the schedule is
   edited; a schedule that silently followed every settings change would be a second source of
   truth for "what runs next".

3. **The period is a five-field cron, evaluated in an explicit timezone.** A `croniter` expression
   (`minute hour day-of-month month day-of-week`) over a `zoneinfo` zone; the stored `next_run_at`
   is a `timestamptz` (UTC in the database), so the calculation happens in the schedule's zone and
   the storage stays unambiguous. The DST rules are the zone's: a nightly job at 02:00 does not run
   twice on the fall-back day and does not silently run at 02:00 on a spring-forward day that has no
   02:00 (the next valid instant is used). `DEFAULT_TIMEZONE` is a new setting, the panel's default
   and the API's fallback; the schedule always stores the zone the operator saw.

4. **The scheduler is a dedicated process, and exactly one holds the lock.** A new
   `python -m scrinalia.domains.archive.workers.scheduler` command (its own compose service, its own
   `Procfile` type, its own `scheduler:dev`). At start it takes `pg_try_advisory_lock(<fixed key>)`
   on a dedicated connection and keeps it for its lifetime; a second instance does **not** exit — it
   stays in standby, retrying the lock every few seconds, so a compose `restart: always` does not
   spin and a crashed scheduler is replaced without an operator. The lock is released by the
   connection's death, which is the only release path that matters. The per-tick work uses row locks
   (`FOR UPDATE SKIP LOCKED`) on top of the advisory lock: the lock says "one scheduler", the row
   locks say "one enqueue per schedule".

5. **A tick enqueues one run per due schedule and advances the next run.** The scheduler computes
   which schedules have `next_run_at <= now()` (the database's clock), and for each one, in **one
   transaction**:
   - if the worker already has a `QUEUED`/`RUNNING` row, the period is **skipped**: it writes
     `last_skipped_at` and advances `next_run_at` to the next future occurrence, creating no row;
   - otherwise it creates the run (`trigger=SCHEDULE`, `attempt=1`, the schedule's `request`, the
     resolved `config`), writes `last_enqueued_at`, and advances `next_run_at`;
   - a schedule whose `next_run_at` is several periods in the past gets **one** run (the catch-up)
     and the next future occurrence; it does not replay every period it missed.
   `enabled=false` means no due schedule at all: the toggle pauses, it does not delete, and turning
   it back on recomputes `next_run_at` from the cron.

6. **A retry is a new row, created immediately, by the scheduler — never by the runner.** After a
   `SCHEDULE` run reaches `FAILED` or `INTERRUPTED`, the scheduler's next tick creates the retry row
   with the previous `request`, `attempt = previous + 1`, `retry_of = previous.run_id` and
   `not_before = the database's now() + the delayed backoff`. The delay after attempt *n* is
   `min(60 × 2^(n-1), 1800)` seconds, with ±20% jitter, and the jittered value is capped again at
   30 minutes; the total is **three attempts**, so the retry is created only while the previous
   attempt is 1 or 2. A manual or CLI run is never retried, whatever its state; `CANCELLED` (#72)
   will never be retried either. The runner does not know about retries: it claims, runs, and
   reports.

7. **The claim honours `not_before`.** `claim_next` gains `AND (not_before IS NULL OR not_before <=
   now())`; the row is created immediately after the failure, so the slot is reserved for the retry
   during the backoff. That is the accepted cost of the new-row model: a manual run of the same
   worker answers 409 until the retry's moment, and the panel shows the retry and its `not_before`.
   The alternative — creating the row only when it is due — needs a second place to keep "a retry
   is pending", which is exactly the duplication the ledger avoids.

8. **The schedule is configured on `/configuracoes/workers`; the state is shown on
   `/sistema/workers`.** The write (cron, timezone, request, enabled/disabled) is configuration and
   lives beside the persisted settings; the operations card shows the agenda (the expression, the
   next run, the paused state, the last skipped) and the run history shows `SCHEDULE`, the attempt
   (`tentativa 2/3`) and `retry de #N`. The API gains `GET/PUT/DELETE
   /api/v1/system/workers/{worker_name}/schedule` (read authenticated, write `OPERATE`) and the
   run DTO gains `attempt`, `retry_of` and `not_before`; `WorkerRunTrigger` gains `SCHEDULE`. The
   pending/processed counters keep their meaning — the queue of units — and the test pins that a
   schedule does not move them.

9. **The migration is additive.** The new table, the three nullable/defaulted columns and the enum
   value; the rows that already exist read `attempt=1`, `not_before=null`, `retry_of=null`. The
   scheduler and the runner check the schema head at start-up, like the runner (ADR 0014): the
   scheduler against the columns and the enum, the runner against the claim's new predicate.

10. **The scheduler is another process to operate.** It has no port, no model and no archive write:
    it reads the schedules and writes the ledger. It shares the API's database credential (the
    least-privilege runner role can also run it, because it only needs the ledger and the schedule
    table; the default is the API's `DB_*`). It is on the `bun run dev`, the compose `scheduler`
    service and the `Procfile`, and the install guide documents the one-instance lock.

## Rationale

- **The schedule is state, not a loop in memory.** A restart must not forget the period, the last
  run or the next run; a table is the smallest thing that survives it, and the same table is what
  the panel reads.
- **One process is a database decision because the database is the shared thing.** An advisory lock
  is one row of shared state and the connection death releases it; a "please run one" in the docs is
  not a guarantee. The standby is the difference between a lock and an outage.
- **Retry as a new row is the ledger's own shape.** The failed row keeps its error, its fingerprint
  and its duration; the attempt is a fact, not a counter that overwrites history. The partial unique
  index is never violated because the retry is created after the previous row is terminal.
- **A pinned request is reproducible.** The schedule and the retry both carry the body that was
  asked for; the config is resolved at enqueue and recorded at start, so the row still explains
  itself after a preset or a rule changes.
- **The skip and the one catch-up are the queue's consequences, not extra policy.** A one-slot
  queue cannot absorb a period that arrives during a run; pretending otherwise would need a backlog.
  A restart is not special: the scheduler creates the period it missed once, because a replay would
  be a backlog by another name.
- **The panel's two numbers are kept apart.** The queue counter answers "how much work is left for
  this worker"; the agenda answers "when does it run next". Merging them would make one of the two
  lie.

## Consequences

Positive:

- A worker has a durable agenda: the cron, the timezone, the request and the next run survive the
  restart of the API, the scheduler and the runner.
- Every attempt is a ledger row with its own error, duration and timestamp; "why did it run three
  times?" has a query, not a guess.
- The scheduler cannot double-enqueue a period: the advisory lock and the row lock, plus the
  enqueue+advance transaction.
- The panel can answer "is this worker scheduled, and when does it run next?" without inventing a
  number for the queue.
- The retry is bounded and visible: three attempts, at most 30 minutes apart, and the row that will
  run says `not_before`.

Negative, accepted:

- **The retry holds the slot during the backoff.** A manual run of the same worker is refused until
  the retry's `not_before`; the panel shows the time. A schedule that fires in the window is
  skipped, like any tick during an active run.
- **A deterministic failure spends three attempts.** The policy is for transient failures (a
  database restart, an Ollama restart, a network blip) and is deliberately not classified: three
  bounded attempts are cheaper than a classifier that is wrong in the other direction. If the cost
  becomes real, a per-error classification is the next decision, not a knob today.
- **One scheduler instance is a single point of failure.** The advisory lock releases on death and
  a standby takes over within its retry interval; there is still a window of one tick length with
  no scheduler. The alternative — several schedulers — is safe for this table but contradicts the
  explicit "one process" the issue asks for.
- **A cron expression and its timezone are a small language.** A typo is a validation error at save
  time, but "the last Sunday of the month" is not expressible; the operator who needs it uses an
  external cron and the CLI, which remains a supported path.
- **`croniter` is a new dependency.** It is small, pure Python and the alternative is a parser with
  the same DST edge cases.
- **The scheduler is another process to operate** — logs and a service, but no port, no model and no
  archive authority.
- **A schedule with no runner online waits.** The run it creates is a `QUEUED` row; the panel's
  `runner_available` says why it is not moving, and the next tick sees the active row and skips the
  period instead of piling up.

## Alternatives considered

- **The runner owns the schedule.** Rejected: the runner is the process that runs models; a schedule
  would die with the GPU process, a runner without the model cache would still have to schedule,
  and "who ticked?" would be a property of a particular runner. The scheduler is cheap and separate.
- **A period (every N minutes) instead of a cron.** Rejected for this issue: the issue's title and
  the first real use ("every night at 02:00", "weekdays at 06:00") need the time of day and the day
  of the week; a period-only form would force the operator to an external cron for the normal case.
  A period is a strict subset of the cron (a `*/N` expression).
- **Several schedules per worker.** Rejected for now: the queue is one slot per worker, so two
  schedules would collide and be skipped; the second rhythm is a new worker-level configuration or a
  backlog decision, not a row.
- **The retry row created only when it is due.** Rejected: it is the `not_before` model with an
  extra pending table; the ledger already has the place for the scheduled time, and the slot is the
  cost of a queue without a backlog. Revisit if the manual-run refusal becomes a real workflow
  problem.
- **Classifying failures as transient or permanent.** Rejected for this issue: the exception types
  do not yet say "transient" reliably (a missing model and a stopped Ollama can raise the same
  library error), and a wrong classification either wastes the GPU or hides a real failure. The
  bounded three attempts are the honest default; the ADR records the classification as the next
  decision if the cost is measured.
- **The scheduler inside the API.** Rejected: the API is stateless and can run several processes;
  a scheduler inside it would need a leader election among API replicas, and the API is exactly what
  the runner architecture took the background work out of.
- **An external cron calling the API.** Rejected as the built-in answer: it needs the session cookie
  or a token, it has no state for the catch-up and the skip, and the panel could not show the next
  run. It remains a supported way to run a one-off, like the CLI.
- **A single `schedules` row with an advisory lock but no row lock.** Rejected: the lock is
  connection-scoped and a transaction can outlive a tick; the row lock makes the enqueue+advance
  atomic even if the lock's owner is being replaced.
- **Storing the resolved `config` on the schedule.** Rejected: it would freeze the active
  `LLM_CHECK` rule and the persisted settings at the schedule's save, which is the opposite of the
  precedence the manual trigger documents. The request is pinned; the config is resolved per run.

## Revisit trigger

Reconsider if any of these becomes true:

- a backlog or a priority is needed, or two schedules for the same worker are wanted (the one-slot
  queue is the constraint, not the schedule table);
- the retry of a deterministic failure is measured to cost real GPU time (the classification or a
  per-schedule toggle becomes worth it);
- the manual-run refusal during a retry's backoff becomes a normal workflow;
- the scheduler's single instance is not enough (a second site, a hot standby with a shared lock);
- a cron expression cannot express the institution's real calendar and an external cron is the
  norm.

## Related

- ADR 0014 — the runner protocol, the lease and the retry vocabulary this ADR implements.
- ADR 0009 — the sessions and the `OPERATE` permission the schedule write uses.
- ADR 0010 — the documentation coverage/freshness rules the operate guide follows.
