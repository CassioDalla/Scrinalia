---
name: documenter
description: "Keep the documentation in docs/ in step with the code: detect which pages the recent changes made stale, decide whether each page needs a new text, write the English page and its Portuguese translation, and record the decision in docs/log.md. Use after landing a change to a documented surface, before a release, or when asked to update the documentation."
whenToUse: "After code that touches a documented surface (a worker, a settings field, a screen, a table, an ADR), before a release, or when the user asks to update the docs."
---

# Documenter

The documentation of this repository is versioned with the code (ADR 0010). It has an English
canonical text and a Portuguese translation, a coverage gate that fails when a documented surface
is missing, and a freshness report that tells you which pages the recent code made stale. Nothing
here is enforced by a build failure: the judgement is yours, and the ledger is where it becomes
auditable.

Read [ADR 0010](../../../docs/adr/0010-documentation-coverage-and-freshness.md) before the first
run of a session. Everything below is the procedure it defines.

## Ground rules

- **Never state what you have not verified.** Every claim in a page is traceable to a file, a
  command or a route you read. This is the rule `AGENTS.md` already states for `README.md` and
  the guides, and it is the one that separates documentation from prose.
- **English is canonical, Portuguese is a translation of it.** Write the English page first and the
  translation after it; never let the translation be the only place a fact exists. A translation
  never adds structure the English page does not have.
- **A page is not "reviewed" because you opened it.** It is reviewed when you have read the diff of
  what changed on its `sources:` and decided, per change, whether the text still holds. The ledger
  entry is the record of that decision, not a checkbox.
- **Do not advance freshness to make the report quiet.** A stale page that is correct is closed
  with a `no-change` verdict and a reason, never by editing the page for the sake of an edit.
- **A page says what is not reversible.** The curation guide has to name, in bold, the writes that
  have no undo: the stopwords purge, `DELETE /documents/{id}`, unifying an entity (no ledger), and
  what the AI cannot silently rewrite after `HUMAN_APPROVED`.

## The two axes

**Coverage — mechanical, blocking, not yours to decide.** `testing/unit/docs/` walks the real
catalogues and fails when a worker, a settings field, a screen, a table or an ADR is missing from
its page. If the gate fails, the page is missing an item: add it. Never extend an allowlist to make
it pass.

**Freshness — a judgement, yours.** A page declares the code it documents:

```yaml
---
sources:
  - src/scrinalia/domains/archive/workers/catalogue.py
  - src/scrinalia/domains/archive/workers/**
---
```

and a translation declares the page it translates:

```yaml
---
translation_of: guides/operate.md
---
```

There is deliberately **no `reviewed:` field and no revision sha in the page**. The marker is
derived from git: an English page is a stale candidate when one of its `sources:` changed after the
last commit that touched the page, and a translation is a stale candidate when the page it
translates changed after the last commit that touched the translation.

## Workflow

1. **Read the ledger.** `docs/log.md` ends with the last triaged range. Everything after it is your
   input.
2. **Run the report.** `uv run python docs/_hooks/freshness.py` prints, per page, the sources that
   moved and — when `packages/api-contract/openapi.json` is inside the range — the routes added or
   removed. `uv run python docs/_hooks/freshness.py --all` ignores the ledger and reports every
   page, which is what a first visit to a page needs.
3. **Classify by surface, not by commit.** A commit is not the unit of documentation: "two settings
   fields and a new worker" is. For each page the report names, run the check that answers "did the
   text stop being true?":
   - `git log --oneline <range> -- <source>` and `git diff <range> -- <source>`;
   - the route delta for the install/operations pages, the worker catalogue for the operations
     page, `core/config.py` for the install page, the router for the curation page, and the models
     for the data model.
4. **Decide, per page**: `updated` (the text changed) or `no-change` (the text still holds, with
   one line saying why). Both are answers; a triage that only ever reports `updated` is a triage
   that is rewriting instead of maintaining.
5. **Write, English first.** Keep the page's existing voice, headings and examples style. Then
   write or update `page.pt.md` with the same structure — the Portuguese text is for the archivist
   and the operator, and it uses the vocabulary of the SPA (`Acervo`, `Arranjo`, `Assuntos`,
   `Geral`), not a literal word-for-word rendering of the English.
6. **Run the gates**: `uv run pytest testing/unit/docs -q` and `uv run mkdocs build --strict`. Both
   must pass; a broken link is a defect, not a warning.
7. **Append the ledger entry** to `docs/log.md`: the range, the date, and one line per page with
   the verdict and the reason. Then commit — `docs` and `docs(adr)` are the scopes the history
   already uses, and the [commit](../commit/SKILL.md) skill owns the commit itself.

## Fanning out

A triage over a large range does not belong in one context. When the report names more pages than
can be read carefully in one pass, give each page its own subagent: the page, its `sources:`, the
range and the report line for it, with the instruction to return `updated` (and the diff it wrote)
or `no-change` (and the reason) — never to write the ledger. Consolidate the answers, write the
pages that need writing, and make the ledger a single entry, because the ledger records an episode
of judgement, not one line per worker.

## Anti-patterns

- Bumping freshness by touching the page: it destroys the only signal the tracking has.
- Rewriting a page wholesale because a paragraph moved: it buries the actual change in a diff
  nobody will read.
- Translating mechanically: the Portuguese page is read by the person who operates the system, and
  a literal translation of an English term that the SPA already names in Portuguese is a defect.
- Documenting an intention. If a feature does not exist in the code, it belongs in an issue and
  nowhere else.
- Adding a page without `sources:`. An English page without `sources:` is a page that can never be
  reported stale; the front-matter test fails on it.
