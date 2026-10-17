# Evaluation sets

The benches under this directory measure the AI against **labelled collection data**:

| Script | Reads | What it answers |
| --- | --- | --- |
| `retrieval_quality.py` | `retrieval_pairs.json` | does subtracting the curated excerpts improve the ranking? |
| `macro_category_quality.py` | `macro_category_pairs.json` | which label format classifies the subjects without collapsing them? |
| `typology_quality.py` | `typology_pairs.json` | does the typology classifier label the form correctly, or collapse onto one typology? |
| `conflict_judge_quality.py` | `archive_conflict_resolution_log` | does the judge agree with the resolutions a human took? |

The last one is the exception to everything below: the conflict judge reads no file at all, because
its gabarito is already in the database. Its section is at the end.

## The data is not versioned, on purpose

These files name **real descriptions, real titles and real tags** of the collection. They are the
collection, not the method, so they do not live in this repository: a clone carries the code and the
format, never the acervo. `dataset.py` reads them from `Data/evaluation/` — the gitignored drawer the
repository already keeps for unpublished data — or from `SCRINALIA_EVALUATION_DATA`, when a checkout
holds them somewhere else. Running a bench without them fails with that instruction instead of a bare
`FileNotFoundError`, because the reflex fix for a missing fixture is to recreate it from the code,
which is the one thing that must not happen.

What *is* versioned is the shape below. It is the part worth reviewing and diffing; the rows are not.

## `retrieval_pairs.json`

Relevance is **derived from the title**: for each query, the expected documents are the ones whose
title carries `title_term`. It is a labelled proxy, not a human truth, and it exists to compare two
rankings of the same model — never to crown one.

```json
{
  "description": "why this set exists and what its labels mean",
  "collection": "a free-text note about which collection produced it",
  "pairs": [
    {
      "query": "the sentence a person would type",
      "expected_document_ids": ["28780", "28781"],
      "title_term": "the term whose presence in the title makes a document relevant"
    }
  ]
}
```

## `macro_category_pairs.json`

This one **is** human-labelled: a curator read each tag and said which subject drawer it belongs to,
with the reasoning next to it. That is what separates it from the retrieval set.

```json
{
  "description": "why this set exists",
  "collection": "a free-text note about which collection produced it",
  "sampling": "how the tags were chosen — the selection rule is part of the method",
  "vocabulary": ["Urbanismo e Arquitetura", "Mobilidade e Transporte"],
  "instructions_for_the_curator": ["how the labels were to be written"],
  "pairs": [
    {
      "name": "the tag",
      "documents": 2467,
      "expected": "the drawer, or null when the tag is not a subject at all",
      "confidence": "alta | media | baixa — the curator's own certainty",
      "needs_decision": true,
      "already_covered": false,
      "note": "the reasoning, which is the part a later reader needs"
    }
  ],
  "status": "who approved the set and when",
  "approved_note": "what changed when the verdicts became a gabarito"
}
```

`vocabulary` is the candidate list the model is scored against. `already_covered` is optional and
marks a tag the deterministic guard or a facet already claims — the bench measures the model, not the
guard, so those are counted separately.

## `typology_pairs.json`

This one is **human-labelled too**, but a tool proposes the rows: `--pick` writes the skeleton and a
curator confirms or corrects every `expected`. It is the only set whose rows are proposed by rule,
which is why the rule is recorded in the file.

```json
{
  "description": "why this set exists",
  "collection": "which database produced it, how many items, and the date — measured",
  "sampling": "the strata rule, the seed and the candidate counts; the selection rule is part of the method",
  "catalogue_at_labelling": ["Fotografia", "Planta Arquitetônica"],
  "instructions_for_the_curator": ["how the labels were to be written"],
  "pairs": [
    {
      "description_id": "33850",
      "candidate": "the stratum that proposed this row",
      "title": "the title, as an aid for the person labelling",
      "evidence": "the description text, as an aid",
      "expected": "the typology name, a list of acceptable names, or null",
      "confidence": "alta | media | baixa — the curator's own certainty",
      "needs_decision": false,
      "note": "the reasoning, which is the part a later reader needs"
    }
  ],
  "status": "who approved the set and when",
  "approved_note": "what changed when the verdicts became a gabarito"
}
```

Three fields exist so the set can be argued with, and none of them is what the bench scores:

- `expected` accepts a **list** because the catalogue mixes support and species: a "Projeto de Croqui
  de Terreno" is a Planta Arquitetônica or a Mapa/Croqui Urbanístico, and a photograph of a
  construction site is a Fotografia or, to another reader, the obra. `needs_decision: true` marks the
  rows where the ambiguity belongs to the **catalogue** and not to the curator; the report counts them
  apart and leaves them out of the score instead of punishing the model for a badly posed question.
- `candidate`, `title` and `evidence` are **labelling aids**. The scorer never reads the text from this
  file: it composes it from the database through `composed_text_sql`, the same expression
  `worker_typology.execute` builds, so the scored text and the worker's text cannot drift.
- `catalogue_at_labelling` is a snapshot of the active typologies on the day of the pick, and only
  that: the scorer labels against the live `get_active_typologies()`, so a typology retired after the
  labelling shows up as a row the catalogue no longer has rather than as a silent mismatch.

`status` is the human signature. While it still starts with `draft`, the scorer refuses to produce a
number unless `--allow-draft` says otherwise — a draft set quoted in a changelog is the failure mode
this field exists to prevent.

## Producing them

The retrieval and macro-category sets are built by hand against a real database, and neither is
regenerable from the code: the retrieval set needs the collection's titles, and the macro-category set
needs a curator's judgement.

The typology set is the one a tool proposes, and the proposal is only a starting point:

```sh
uv run python -m testing.evaluation.typology_quality --pick   # writes the skeleton + the sheet
uv run python -m testing.evaluation.typology_quality --sheet  # regenerates the sheet from the file
```

`--pick` reads the collection without writing to it, and refuses to overwrite an existing set unless
`--force` — the labels have no undo. The sheet carries the text; the file carries the ids and the
labels. The sheet reads the text from the **database**, never from the file, so it cannot disagree
with what the scorer will read.

## Running the typology bench

Label `expected` on every row, set `confidence`, mark `needs_decision` where the ambiguity belongs to
the catalogue, write the reason in `note`, and replace `status` with who approved the set and when.
While `status` still starts with `draft` the scorer refuses to produce a number; `--allow-draft`
exists to explore a set nobody has signed yet, and a figure produced that way is not a measurement of
the model.

```sh
# The run that shipped, and the collapse over the whole collection. One query, no model.
uv run python -m testing.evaluation.typology_quality --predictions stored

# The model, on the labelled rows. One line per configuration; repeat --config to compare.
uv run python -m testing.evaluation.typology_quality \
    --config deberta_typology:cpu_local:original_title:0.40 \
    --config deberta_typology:cpu_local:original_title:0.55

# A trial before the full run: the cap only limits how many rows the model sees.
uv run python -m testing.evaluation.typology_quality --limit 20

# The same numbers as JSON, for the changelog.
uv run python -m testing.evaluation.typology_quality --json .analysis/typology_bench.json
```

`--config` is `engine[:preset[:columns[:threshold]]]`, and the four fields are exactly what
`worker_typology.producer_identity` signs — a configuration the bench scores is one the worker can be
told to run. The default is the worker's own, read from its signature. The model is never named in
the script: a new model is a preset in the engine registry.

The report prints agreement, per-typology precision/recall/F1, the confusion matrix, the label
distribution (largest share, entropy, abstentions) and seconds per document. A typology with fewer
than `--min-positives` labelled examples (5 by default) is printed as **não medida** instead of
scored: an F1 built on two rows reads like a measurement and is not one.

## Running the macro-category bench

The subject bench compares label formats and arrangements on the macro-category set. Its models come
from the engine registry — the same registry both workers of the axis read — so the bench names no
model:

```sh
uv run python -m testing.evaluation.macro_category_quality \
    --config deberta_typology:cpu_local \
    --config deberta_typology:xlm_roberta_local
```

With no `--config` it runs the configuration the macro-category worker declares in its own signature,
so "the current configuration" cannot drift from the code. `--device` overrides the preset's device
for every configuration. A model that is not a registry preset is not reachable from here: adding one
is a registry entry, which is what makes a configuration the bench measures one the worker can also
be told to run.

## Measuring the collection, not the sample (issue #109)

The labelled set is balanced by construction — 40 rows per form by default — and a decision about
cost is not: what a whole collection pays depends on its own mix. `--collection` samples the
**pending queue** and prints seconds per document, the projection for that queue, the abstention rate
and the label distribution, per configuration and per stratum:

```sh
uv run python -m testing.evaluation.typology_quality --collection --sample 100 \
    --config deberta_typology:cpu_local:original_title:0.40 \
    --config deberta_typology:cpu_local:original_title,admin_bio_history:0.40
```

It writes nothing (no typology, no stamp) and scores nothing: these rows have no gabarito, and a
wrong label here is invisible. Three rules make its number mean the collection:

- The sample comes from the worker's **own** pending predicate (`pending_conditions`), and the mode
  prints `count_pending` beside it — the number the panel shows. A sample drawn from a queue the
  worker does not have prices a run that will not happen.
- The rows are allocated **proportionally** across the picker's strata, with no floor, and are *not*
  deduplicated by text: the worker pays for a repeated title every time it appears.
- Two configurations are measured on the rows pending under **both**, so the comparison isolates the
  columns instead of the collection.

The model is loaded **once per engine and preset**: configurations that differ only in the columns or
the floor share one model in memory, because building mDeBERTa again would charge the model load to
the seconds per document. Comparing two engines in one run is allowed and loads both.

Keep a copy of all three wherever the collection is backed up. If one is lost, the bench cannot be
re-run — it can only be rebuilt by reading the collection again.

## The conflict judge's set is derived, not stored (issue #114)

`conflict_judge_quality.py` scores the tag x entity judge against the resolutions a **human** took, and
it needs no file of its own: `archive_conflict_resolution_log` already holds the verdict, the pair and
who decided, and a human verdict is durable intent that no later suggestion run overwrites
(principle VII). The set is derived at run time, which is why there is no shape to version here — the
rules below are the method, and they are what a reader has to check instead.

- **`source='HUMAN'` is the gabarito; `'JUDGE'` is not.** Every resolution records whether a curator
  on the conflict screen decided it or the worker auto-resolved it. Scoring both together measures the
  model against itself, so the judge's rows are read, counted and printed as *outside the score* —
  never silently dropped, because a ledger that is 90% judge decisions is a fact the reader needs.
- **`undone_at IS NOT NULL` is out.** A decision a human reversed is not truth any more, and leaving
  it in would score the judge against an answer the institution withdrew.
- **The pairs come from the ledger's own snapshots.** The resolution deletes the losing row, which is
  why `context_payload` carries no foreign key on purpose. `tag_name`, `entity_name` and `entity_type`
  are the pair at decision time; the bench never joins the live catalogues, because the row it would
  join is the one the resolution removed.
- **A failed call is not an opinion.** `EntityTagDecisionSchema` has no error state, so a transport
  failure returns `winner="TAG"` with `confidence=0.0` and a reason carrying `FAILURE_REASON_PREFIX`.
  Those rows are counted as *engine failures*, excluded from the score and printed.

Two numbers are printed next to the agreement, and neither is decoration. The **constant baseline** is
the verdict a judge answering only the most frequent one would get: on a ledger where a curator worked
through a run of street names the gabarito skews, and against a 90%-ENTITY ledger a judge that always
says ENTITY scores 0.900 having measured nothing — the table's `Δ` column is agreement minus that
baseline, and it is the number that answers "is this better than a constant?". The **auto-resolve
split** puts the worker's own `auto_resolve_threshold` (read from its signature) on the verdicts, and
reports agreement separately for the pairs it would have settled without a person and for the ones it
would have sent to review: the operationally interesting figure is right *and* sure enough to act
alone.

```sh
uv run python -m testing.evaluation.conflict_judge_quality
uv run python -m testing.evaluation.conflict_judge_quality --config ollama_judge:granite_local --limit 10
```

`--config` is `ENGINE[:PRESET]`, validated against `engines/LLMs/registry.py` — the same registry the
worker reads — and the default is the worker's own configuration read from its signature. `--limit`
draws a reproducible subset by `md5(seed:resolution_id)` rather than taking the first N, because the
ledger is ordered by decision time and "the first ten" is one curator's afternoon. Nothing is written:
no resolution, no ban, no ledger row.
