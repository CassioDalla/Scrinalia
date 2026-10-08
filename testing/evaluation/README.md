# Evaluation sets

The two benches under this directory measure the AI against **labelled collection data**:

| Script | Reads | What it answers |
| --- | --- | --- |
| `retrieval_quality.py` | `retrieval_pairs.json` | does subtracting the curated excerpts improve the ranking? |
| `macro_category_quality.py` | `macro_category_pairs.json` | which label format classifies the subjects without collapsing them? |

## The data is not versioned, on purpose

Both files name **real descriptions, real titles and real tags** of the collection. They are the
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

## Producing them

Both are built by hand against a real database, and neither is regenerable from the code: the
retrieval set needs the collection's titles, and the macro-category set needs a curator's judgement.
Keep a copy wherever the collection is backed up. If one is lost, the bench cannot be re-run — it can
only be rebuilt by reading the collection again.
