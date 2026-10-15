# Evaluation sets

The benches under this directory measure the AI against **labelled collection data**:

| Script | Reads | What it answers |
| --- | --- | --- |
| `retrieval_quality.py` | `retrieval_pairs.json` | does subtracting the curated excerpts improve the ranking? |
| `macro_category_quality.py` | `macro_category_pairs.json` | which label format classifies the subjects without collapsing them? |
| `typology_quality.py` | `typology_pairs.json` | does the typology classifier label the form correctly, or collapse onto one typology? |

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

Keep a copy of all three wherever the collection is backed up. If one is lost, the bench cannot be
re-run — it can only be rebuilt by reading the collection again.
