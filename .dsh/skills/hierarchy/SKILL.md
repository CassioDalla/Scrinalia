---
name: hierarchy
description: "The arrangement plan catalogue and the tree: levels, suggest/apply, flags, diagnostics and the path invariant."
whenToUse: "When touching arrangement, a level, a plan or a node move."
---

# hierarchy

## The arrangement plan catalogue

- The arrangement plan catalogue separates the **decision** from the **run** exactly like the tag merges: `POST /hierarchy/plans/suggest` is idempotent by `code` and never rewrites a row that left `SUGGESTED`, so the same questions are not asked again. `GET /hierarchy/plans` carries `status_counts` for the **whole catalogue** (how much of the catalogue is already decided cannot be derived from a page), and preview and apply share one planner so the approved number is the written number. Two traps, both shipped and both caught by looking at the screen: (1) `GET /hierarchy/flags` publishes the **union of four vocabularies** — `ProposalFlag`, `HierarchyIssue.NEAR_DUPLICATE_NODE`, `HierarchyViolation.LEVEL_NOT_ALLOWED_AS_CHILD` and `CodeFlag` — because that is what a plan row's `flags` actually carries; publishing only the first leaves the UI rendering raw codes, and `plan_flag_vocabulary()` exists so there is one definition to update. (2) `GET /hierarchy/diagnostics/summary` counts each issue with `limit=0` through the same code that serves each page, and deliberately has **no grand total**: the issues overlap (a Dossiê at the root is both an `ORPHAN` and a `DOSSIER_WITHOUT_PARENT`), so a sum would inflate the collection. `PATH_DIVERGENCE` is the one diagnostic whose evidence is a comparison, so it carries both `path` and `expected_path` in `detail`.

## The path invariant

- **The `path` invariant is verified in CI through the shipped check, not a copy of it.** `find_path_divergences` is the query the `PATH_DIVERGENCE` diagnostic serves, and `testing/integration/archive/services/test_hierarchy_{service,materialisation_service}.py` call **it** after every writer (create, subtree move, materialise and undo). Do not reintroduce a second SQL string for the comparison in a test: it would keep passing while the shipped check drifted, and the panel would be the one place nobody looked. Both halves matter — a healthy tree must answer empty (including the `total == 0` early return) and the deliberately corrupted row must still be found.

