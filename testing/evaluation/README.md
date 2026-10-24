# Evaluation sets

The benches under this directory measure the AI against **labelled collection data**:

| Script | Reads | What it answers |
| --- | --- | --- |
| `retrieval_quality.py` | `retrieval_pairs.json` | does subtracting the curated excerpts improve the ranking? |
| `retrieval_modes.py` | `retrieval_pairs.json` | which ranking — lexical, semantic or the fusion — answers the labelled queries better, per query stratum? |
| `macro_category_quality.py` | `macro_category_pairs.json` | which label format classifies the subjects without collapsing them? |
| `typology_quality.py` | `typology_pairs.json` | does the typology classifier label the form correctly, or collapse onto one typology? |
| `quality_validator_quality.py` | `validator_pairs.json` | do the active `VALIDATE`/`LLM_CHECK` rules flag what a curator flags, rule by rule? |
| `conflict_judge_quality.py` | `archive_conflict_resolution_log` | does the judge agree with the resolutions a human took? |
| `ner_quality.py` | `ner_pairs.json` | does the extractor find names, places and institutions — and where does it get the boundary wrong? |

Two benches read `retrieval_pairs.json` and they are not the same measurement: `retrieval_quality.py`
embeds the text itself and compares the embedded text before and after the curated excerpts (there the
text *is* the variable), while `retrieval_modes.py` runs the three rankings **through the product
path** — `DocumentService` and the repository, the same objects the route uses — because a bench that
ranked on its own would score a second definition of the search.

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

`--formats` is a **separate** dimension, and deliberately not a fifth field of `--config`: the label
shape is not part of the producer identity today, so folding it into the configuration string would
make the bench name a producer the worker cannot be told to run. The default is all three:

```sh
uv run python -m testing.evaluation.typology_quality \
    --config deberta_typology:cpu_local:original_title:0.40 \
    --formats bare sentence trata_de
```

| format | the label the model reads |
| --- | --- |
| `bare` | `Fotografia` — what the worker sends today, and the baseline |
| `sentence` | `um documento do tipo Fotografia` |
| `trata_de` | `trata de fotografia` |

The templates are the bench's **instrument**, not a product string: a wording hand-written for one
catalogue's typologies would be collection data inside versioned code, and the shape is what this
measures. The `sentence` format is gender-invariant by construction (`um documento do tipo …`) because
Portuguese forces the article to agree with the typology — "uma fotografia" against "um relatório
técnico" — the catalogue stores no gender, and no code template can be right for a mixed catalogue.
The product's home for a proposition with the right article is a field **per catalogue row**, the way
`archive_macro_categories.classifier_label` already works for the subject axis; the typology catalogue
has no such column today.

Two rules keep a formatted run honest, and both exist because the engine **echoes the label it was
given**: the candidate list and the way back are one dictionary (`{label: catalogue name}`), and the
placar is written in catalogue names. Without the translation every row of every formatted run scores
as a miss, and the report prints `0.000` — a number that reads like a finding about the model and is a
defect in the harness. `formatted_labels` and `link_decision` are pinned by unit tests on each side of
that pair.

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

## `validator_pairs.json`

The quality validator's output is not one label but a **set of flags per document**, so this set
grades *rules* and not documents: each entry names the rules that should have flagged the row.

```json
{
  "description": "why this set exists",
  "collection": "which database produced it, how many items, and the date — measured",
  "sampling": "the strata rule, the seed and the candidate counts; the selection rule is part of the method",
  "active_rules": ["the rule_name of every scorable rule at the day of the pick"],
  "rules_at_labelling": [
    {"rule_name": "rua abreviada", "rule_kind": "VALIDATE", "target_column": "original_title"}
  ],
  "pairs": [
    {
      "description_id": "33850",
      "candidate": "the stratum that proposed this row",
      "title": "the title, as an aid for the person labelling",
      "stored_reasons": ["RULE_MATCH:grafia viária abreviada", "NO_TAGS"],
      "expected": ["rua abreviada"],
      "confidence": "alta | media | baixa — the curator's own certainty",
      "needs_decision": false,
      "note": "the reasoning, which is the part a later reader needs"
    }
  ],
  "status": "who approved the set and when"
}
```

- `expected` is a **list of `rule_name`s**, and an **empty list is a verdict**: "no rule should have
  flagged this document". It is the verdict that measures precision, so leaving it blank is not the
  same answer and the loader distinguishes them (`null` and `[]` both mean none, a missing key means
  the curator has not answered).
- A name the active catalogue does not have is **refused** rather than warned about. Here it is a typo
  in the gabarito far more often than a retired rule, and it would be a guaranteed miss the rule
  cannot avoid.
- `stored_reasons` is a labelling aid, not what the bench scores. The scorer recomputes the flags
  through the worker's own functions — `matched_rule_labels` for `VALIDATE` and `llm_check_reason` for
  `LLM_CHECK` — so the graded flags cannot drift from the ones the worker writes.
- `needs_decision: true` marks a row where the ambiguity belongs to the **catalogue** and not to the
  curator (two rules that overlap by construction). Those rows leave the score instead of becoming a
  false negative for a rule that was never allowed to satisfy them.

## The quality validator's set is proposed, not hand-picked

`--pick` reads the catalogue and the flags the **last run** stored, and proposes rows by stratum:

```sh
uv run python -m testing.evaluation.quality_validator_quality --pick
uv run python -m testing.evaluation.quality_validator_quality --sheet
```

One stratum per active scorable rule, capped at `--per-rule` (40), plus two buckets that are not
padding: the documents some *unscorable* rule touched — where a rule that should have fired is looked
for — and the documents with no anomaly at all, at `--clean-rows` (25). Without those two, recall has
no denominator: **a review queue can only ever measure precision**, because the documents nobody
flagged are exactly the ones absent from it.

Stratifying on the stored flags is what keeps the pick free. The alternative — running the active
rules over the whole collection to build the strata — re-reads every description and, with an
`LLM_CHECK` rule active, makes a model call for each, to order a sample of a hundred.

## Running the validator bench

```sh
# The rules the worker would run now: the regex is live, the model is asked again.
uv run python -m testing.evaluation.quality_validator_quality

# The flags the last run already wrote. Free, whole collection, no model.
uv run python -m testing.evaluation.quality_validator_quality --predictions stored

# The same numbers as JSON, for the changelog.
uv run python -m testing.evaluation.quality_validator_quality --json .analysis/validator_bench.json
```

The rules are read from the catalogue through the same repository the worker uses, so the bench
follows the installation's own rules instead of a list kept in the code — including the case where
there are none, which is the state of this installation today: `--pick` and the scorer both refuse
with that sentence rather than printing an empty table.

The report is one line per rule with its **support** (how many documents the gabarito says it should
have flagged), how many it **fired** on, precision, recall and F1. A rule below five labelled
positives — the same floor the typology bench uses — is printed as **não medida**: a rule with two
examples behind it produces an F1 that reads like a measurement and is not one. The two disagreement
kinds are listed separately and by document, because they are not the same defect: **perdeu** is an
anomaly nobody will look at, **marcou a mais** is a person's time spent on nothing.

A rule whose `rule_name`, or whose `VALIDATE` flag label (`anomaly_reason or rule_name`), collides with
another active rule is **refused** at `--pick` time: the gabarito names rules, so an ambiguous
catalogue cannot produce one.

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
- **A failed call is not an opinion.** `EntityTagDecisionSchema` has no error state, so the engine
  raises `EngineExecutionError` when the call cannot be made (#122). A pair it could not answer is a
  `Failed`, not a `Judged`: counted as an *engine failure*, excluded from the score and printed.

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
uv run python -m testing.evaluation.conflict_judge_quality --config ollama_judge:gemma_4b_local --limit 10
```

`--config` is `ENGINE[:PRESET]`, validated against `engines/LLMs/registry.py` — the same registry the
worker reads — and the default is the worker's own configuration read from its signature. `--limit`
draws a reproducible subset by `md5(seed:resolution_id)` rather than taking the first N, because the
ledger is ordered by decision time and "the first ten" is one curator's afternoon. Nothing is written:
no resolution, no ban, no ledger row.
## `ner_pairs.json` — the gold is a correction of the stored run (issue #113)

There is no human NER gabarito for this collection, and there is no second source to build one from:
`archive_document_entities` holds 64.504 links over 4.811 documents, and the ones that exist today
were all written by the worker itself (`bulk_link_entities`), while `domain_ner_exclusions` has three
rows and `archive_entity_merge_log` has none. The link records its **origin** now (#135), so
`--propose` ignores a link a person made: the curator's decision is gold, and scoring it as the
extractor's own answer would credit the model for a correction.

So the set is built the other way round, and the way round is the design: **the gold comes from
correcting the stored output.** `--propose` reads the links the last run wrote and writes a skeleton
where the model's own extraction is `proposed` and `expected` is empty, plus a sheet where a curator
marks what is wrong and what is missing.

```json
{
  "description": "why this set exists and what its labels mean",
  "collection": "which database produced it, how many documents, and the date — measured",
  "sampling": "the seed, how many rows per entity type, and how the empty documents entered",
  "instructions_for_the_curator": ["how the labels were to be written"],
  "pairs": [
    {
      "description_id": "33850",
      "proposed_by": "the entity type that put this row in the sample, or '(sem tipo)' for a document with no stored entity",
      "title": "the title, as an aid for the person labelling",
      "proposed": [{"term": "Curitiba", "type": "LOC"}],
      "expected": [{"term": "Curitiba - Paraná", "type": "LOC"}],
      "confidence": "alta | media | baixa — the curator's own certainty",
      "needs_decision": false,
      "note": "the reasoning, which is the part a later reader needs"
    }
  ],
  "status": "who approved the set and when",
  "approved_note": "what changed when the corrections became a gabarito"
}
```

**The anchoring bias is declared here, in the file's own `instructions_for_the_curator`, and at the
top of every sheet.** A pre-annotated gold drags the annotator toward the model's answer: deleting
what is wrong is easy, noticing what is *absent* is not, and the absence is the half of the measure
that has no other source. This is the reason the field is called `proposed` and never `expected`, and
the reason the loader **refuses a row that still has no `expected` key** — a set left as the proposal
was written would score the model against itself and print a perfect number.

- `input_text` is deliberately **not** in the file. The sheet carries the text and reads it from the
  **database** through the worker's own composition, so it cannot disagree with what the scorer will
  read. Storing it would be a second copy of the collection.
- `expected` is a list of `{term, type}` rather than a list of strings, because a term of the wrong
  type is a different defect from a term that was not found, and the two must be countable apart. A
  term whose type the curator cannot settle is written `"(sem tipo)"` and is reported separately.
- `expected: null` (or `[]`) means **no entity should have been found**, which is an answer and not a
  gap: it is the only thing that turns an invented entity into a measured false positive. A document
  with one is proposed on purpose (`--empty-rows`), because a sample drawn only from the model's own
  output can never see what the model missed.
- `needs_decision: true` marks a row where the question belongs to **policy** and not to the curator
  (is this term an entity or a subject?). Those rows leave the score and are counted apart.
- **A row is "read" when it carries `confidence` or `note`, and a row that carries neither leaves the
  score.** `expected: null` means both "no entity should have been found" and, on an untouched row, the
  proposal's own placeholder — the two are indistinguishable in that field, so the curator's certainty
  (or the reason they cleared everything) is what separates a correction from a line nobody opened.
  Without the rule a forgotten row would silently score the model against the answer the model itself
  wrote, which is the whole failure the pre-annotation risks. It is **counted and printed**, never
  dropped in silence: a report that quietly shrank its own denominator would hide how much of the set
  a curator worked through.

**The boundary breakdown is a token measure, not a character one.** `ArchiveEntityDTO` carries `name`
and `entity_type` and no offsets, and `archive_document_entities` is `(description_id, entity_id)` and
no offsets either. What the bench measures is whether one token sequence contains the other
("Curitiba" against "Curitiba - Paraná"), which is what the token-boundary blocking of #69 produces. It
is a count of the defect and not of where it happened, and the report says so.

## Running the NER bench

```sh
# Propose the set from the run that shipped, and its correction sheet. Nothing reaches the database.
uv run python -m testing.evaluation.ner_quality --propose
uv run python -m testing.evaluation.ner_quality --sheet

# What the last run already wrote. Free, whole collection, no model.
uv run python -m testing.evaluation.ner_quality --predictions stored

# The extractor the worker would run now. One line per configuration; repeat --config to compare.
uv run python -m testing.evaluation.ner_quality --config spacy_ner:gpu \
    --config spacy_ner:gpu:original_title,scope_content

# A trial before the full run: the cap only limits how many documents the model sees.
uv run python -m testing.evaluation.ner_quality --limit 10 --json .analysis/ner_bench.json
```

Correct `expected` on every row, set `confidence`, mark `needs_decision` where the question belongs to
policy, write the reason in `note`, and replace `status` with who approved the set and when. While
`status` still starts with `draft` the scorer refuses to produce a number; `--allow-draft` exists to
explore a set nobody has signed yet, and a figure produced that way is not a measurement of the model.

`--config` is `ENGINE[:PRESET[:COLUMNS]]`, validated against `engines/NER/registry.py` — the same
registry the worker reads — and the default is the worker's own configuration read from its signature.
The text is composed by the worker's own expression (same columns, same `NER` rules, same `". "`
separator, same URL stripping), and an integration test pins the pair by running the real worker with a
fake engine and comparing the two strings. Nothing is written: the session is opened, read and rolled
back, and a test asserts the collection is untouched.

**The two modes do not answer the same question, and `stored` must not look like it measured this
configuration's boundary.** Both compare the term string, because neither the link nor
`ArchiveEntityDTO` carries an offset — but `stored` reads what an **earlier** run wrote, so its
boundary counts describe the recorded output and belong to whatever producer stamped those documents.
The report therefore prints the **producer identities the documents carry** next to the breakdown, and
a `stored` figure must never be quoted as the boundary error of the configuration under test. `live`
runs the engine over the composed text and is the only mode whose boundary counts belong to the
configuration being measured. (Measured on this collection: of 122 sampled documents, 75 carry no NER
stamp at all and 47 carry the legacy `"DONE"` — the recorded output is not attributable to a single
producer, which is precisely why the report names it instead of assuming it.)

The report prints the configuration, the mode, the producer identity, the per-type table with the
support floor (a type below five labelled mentions is **não medida**), the type distribution next to
the score — so a collapse onto one type is visible and not only its total — the boundary breakdown as
counts, and the disagreeing documents listed by what happened. **A confidence is not printed, because
there is none to print**: `ArchiveEntityDTO` has no score, so a disagreement is listed by its terms and
not by a number the engine never returns.
