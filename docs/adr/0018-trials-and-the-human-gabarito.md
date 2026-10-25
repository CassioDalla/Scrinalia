# ADR 0018: A trial is a ledger row, and the gabarito is the human decision already recorded

- **Status:** Accepted
- **Date:** 2026-10-25
- **Applies to:** the trial run, its result in the run ledger, the shared typology metric, and the
  gabarito read that the panel shows (#71).

## Context

#70 made a classified description re-classifiable: the stamp names the producer, so changing the
engine, the preset, the columns or the confidence floor puts the affected units back in the queue.
That solved the "cannot run it again" half and exposed the other one: **the run that stamps the
collection is unbounded and irreversible in practice.** Choosing a preset, running the typology over
4,844 descriptions and discovering afterwards that the collection was labelled with the wrong
configuration is the decision #71 exists to prevent.

The panel already answers *what a configuration would cost*: `POST
/api/v1/system/workers/{worker_name}/queue/preview` returns the pending count under a proposed
configuration without writing (the "declared options" work of #120 is what made that possible). It
does not answer *whether the configuration is any good*, and the two questions are different: the
preview prices the queue, and a measured answer needs the model to run over a set the institution
can judge.

The repository already had the measurement, in two halves:

- `testing/evaluation/typology_quality.py` scores a configuration against a human-labelled set
  (`agreement`, `macro_f1`, `abstention_rate`, the label distribution, entropy and the largest
  bucket) and has a `--collection` mode that prices a configuration on the collection's own mix.
- The bench is a **script outside the package**: the API and the runner cannot import it, so its
  arithmetic could not be the number the panel shows. #69's definition of done says the metric has
  to exist once; #71 is the occasion to make that true.

Two constraints the design has to respect:

1. **The queue is one slot per worker.** `uq_worker_run_active` is a partial unique index on
   `(worker_name, COALESCE(origin_code, '')) WHERE status IN ('QUEUED','RUNNING')`, and the runner
   executes one run at a time. A comparison of two configurations can therefore not be two
   simultaneous executions of the same worker.
2. **A trial must not be mistaken for the real thing.** The run ledger is the operations screen; a
   row that wrote archival content under a configuration nobody chose would be the defect, not the
   feature.

The issue also asks a question the code did not answer: *what is the gabarito inside the product?*
The benches read JSON files of labelled collection data, which are intentionally not versioned and
not available to the archivist at the panel. The only ground truth an installation really has is the
decision its people already took while curating.

## Decision

### 1. A trial is a kind of execution, not a worker run

`archive_worker_runs` gains `trial` (boolean, default false) and `trial_result` (JSONB, nullable).
`trigger` keeps its meaning — **who** asked (`CLI`, `API`, `SCHEDULE`) — and `trial` says **what
kind** of execution it is; a new `WorkerRunTrigger` value would conflate the two.

A trial run:

- is enqueued by the panel (`POST /api/v1/system/workers/{worker_name}/trial`) and claimed by the
  same runner, with the same lease, the same heartbeat and the same cancellation as any other run;
- **holds the worker's slot**, because it loads the model and reads the collection, and because the
  panel should never show two executions of one worker at once;
- **writes no archival content**: it does not touch `typology_id`, `execution_log` or the review
  queue. The only write is the ledger row's `trial_result`;
- **is distinguishable** in `/sistema/execucoes` by the `trial` flag, and the production `last_run`
  shown by the panel is a real run, not a trial.

The trial's per-configuration execution happens **inside the one row**, sequentially. The row is the
comparison: one sample, two or more configurations, each with its own measured seconds. The
alternative — one row per configuration — was rejected because the one-slot index would force the
API to chain the rows (enqueue the next only when the previous is terminal), and a comparison that
can be half-finished is a state the archivist would have to reason about. The row's `duration_ms` is
the whole trial; each configuration carries its own `seconds_per_document`, measured around the
model calls only, so the model load is charged once to the run and not to the first configuration.

### 2. The metric exists once, in the package

The scoring primitives (`Truth`, `Prediction`, `Scored`, `agreement`, `per_class`, `macro_f1`,
`confusion`, `distribution`, `entropy_bits`, `largest_share`, `abstention_rate`) and the worker's
decision rule (`link_decision`: an answer is linked only when `score > confidence_threshold`) move
from `testing/evaluation/typology_quality.py` into `src/scrinalia/domains/archive/evaluation/`.
The bench imports them from there, and the worker imports `link_decision` from there, so the panel,
the bench and the worker cannot disagree about what "agreement" or "the floor" means. A test pins
that the bench's names are the package's functions, not a copy.

A trial executor, not the worker's `execute`, runs the model. It shares the text composition
(`composed_text_sql`), the engine registry and the decision rule; it deliberately does not call
`execute`, because `execute`'s job is to write and a trial's job is to measure. The two are pinned
together by a test that runs both over the same input with a fake engine and compares the decision.

### 3. The gabarito is the human decision already recorded

There is **no new verdict table and no new labelling screen**. Each axis's existing ledger already
records the decisions a person took, and the gabarito is a read over it:

| Axis | The human decision | The label |
| --- | --- | --- |
| Typology | the latest `archive_document_revisions` row whose `changes` carries `typology_id` | the `typology_id` the revision wrote (`NULL` = the `NENHUMA` class) |
| Subject | the tag carries `curated_macro_category` | the current `macro_category_id` (`NULL` = not a subject) |
| Entity | `archive_document_entities.origin = HUMAN` | the linked entity |
| Conflict judge | the human resolution in `archive_conflict_resolution_log` | `TAG` or `ENTITY` |

Two rules make the read honest:

- **The mark is the decision; `HUMAN_APPROVED` is not.** Approving a dossier says the record is
  publishable, not that every label in it is right. A description a person approved without touching
  the typology is not a verdict, and measuring the model against its own output would be circular.
- **The current catalogue value is the label; the ledger is the fact that a person chose it.** A
  typology renamed later still means the same concept, and the trial records the names it scored
  against so a past result stays readable.

The screen that owns the verdict is the screen that owns the decision — the dossier and the typology
refusal queue, the tags screen, the conflicts screen. The comparison card reads the count and links
there; it never asks the archivist to state a verdict a second time. This is the same principle that
made `curated_macro_category` the tag's mark and not a second tag category.

The consequence is accepted and stated: the gabarito is **the cases a person touched**, not a random
sample of the collection. It is a hard set (the refusals and the corrections), and the agreement
measured on it is quoted as "concordância no gabarito", never as "accuracy on the collection". A
representative labelled sample would need a new screen and a new ledger of verdicts; that is a
different issue, and the trial's contract can read a second source without changing.

### 4. The sample has two populations

The trial draws one sample and runs every configuration over it, so the configurations are not
confounded with the collection:

- **The verdict set** — every unit with a human decision, up to a cap, ordered by a recorded seed.
  This is the population the **agreement** and the **coverage** (answered share) are measured on.
  These units are usually `HUMAN_APPROVED` and therefore outside the production queue; the trial
  reads them anyway, because that is what a test set is.
- **The production scope** — a seeded random sample of the units the configurations would really
  process: the intersection of each configuration's candidate predicate (`ai_writable_documents()`
  plus at least one of the columns it reads is not null). This is the population the **distribution**,
  the **abstention rate**, the **entropy** and the **seconds per document** are measured on.

The random sample is drawn from the candidate predicates, **not** from the pending queue. The bench's
`--collection` mode samples the intersection of the pending queues, which is right for comparing two
candidates and useless for comparing the configuration that is already applied (its queue is empty).
The trial must be able to re-measure the current configuration, so the stamp is not part of the
sample's predicate.

The result records the seed, the sampled ids, the verdict ids and the counts, so the run can be
audited and the same sample can be reasoned about after the collection grew. The engine is built once
per `(engine, preset)` and shared by the configurations that use it.

### 5. The comparison produces the choice; it does not become the choice

The result is a table, not a verdict: agreement (with its denominator), coverage, abstention, the
label distribution, the largest bucket, entropy, seconds per document, the queue under that
configuration and the projected hours. The archivist reads it and takes the decision.

**"Use this configuration"** writes the existing `archive_worker_settings` row through `PUT
/api/v1/system/workers/{worker_name}/settings` — the trial result carries the settings body it
measured, so the screen sends exactly that. There is no `trial_config` column and no second place
where the choice lives.

**"Run over the whole collection"** then triggers the real run with an empty request, so the
precedence resolves the settings row that was just written. The pending count is read **after** the
save, with the same configuration the trigger will use, and that is the number shown next to the
button. The trial's own `pending` per configuration is the projection base, never the number the
production button promises.

### 6. Typology first, the contract generic

This ADR and its change implement the trial for `typology` only. The subject, entity and judge
verdicts have different shapes (a tag, a link set, a pair verdict), and each one needs its own read;
the contract (`trial` in the catalogue, `trial_result` in the ledger) does not name typology. A
worker without a trial read refuses the route, so the screen cannot offer a comparison the runner
cannot execute. The `WORKER_CATALOGUE` flag is the single list of trial-capable workers, and a test
keeps it equal to the trial registry.

## Alternatives considered

- **Thread a `trial` flag through each worker's `execute`.** The smallest diff for one worker, and
  the wrong shape: the flag reaches every write site, and the guarantee "writes nothing" becomes the
  worker's discipline instead of the executor's construction. A new worker would have to remember it.
- **Run the real worker inside a transaction and roll it back.** The workers commit per batch and a
  run can last hours; a database transaction is not the tool, and the per-unit answers (which the
  comparison needs) would still be lost.
- **A dedicated verdict table plus an evaluation screen.** The scientifically stronger option: a
  sampled, representative gabarito with an explicit `NENHUMA` and a confirmation action. It is a new
  table, a new screen and a second place where the same human decision is recorded; the current
  decision read can be swapped for it later without changing the trial's contract.
- **One ledger row per configuration, grouped.** Honest `duration_ms` per configuration, at the cost
  of a chaining state machine and a half-finished comparison. The one-row trial keeps the atomicity
  and stores per-configuration seconds.
- **A `TRIAL` value in `WorkerRunTrigger`.** The trigger answers who asked, not what the execution
  does; a trial can be asked by the panel or by a future CLI, and the audit needs both facts.

## Consequences

- The panel gains a "compare" card on the settings screen, a trial row with a badge in the run
  history, and a detail read of the result; no new screen and no new table for the comparison.
- A trial occupies the worker's slot for its duration; a production run enqueued behind it waits.
- The gabarito grows only as the archivists curate. A fresh installation has no agreement to show,
  and the card says so instead of printing a number on an empty set.
- A typology retired from the active catalogue is a guaranteed miss in the gabarito (the engine can
  only answer active labels); the result reports the count instead of hiding it.
- The model load is a cost of the run, not of a configuration; the per-configuration seconds exclude
  it, and the projection says so.
- A trial never retries: it is a manual execution, and a failed trial is a failed execution with its
  error fingerprint like any other.
