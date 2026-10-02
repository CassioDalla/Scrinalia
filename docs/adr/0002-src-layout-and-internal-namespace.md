# ADR 0002: `src/` layout and internal package namespace

- **Status:** Accepted
- **Date:** 2026-10-02
- **Supersedes:** the open questions in `.analysis/analise-layout-src-e-divida-tecnica.md` §6

## Context

The project has four top-level import roots (`core`, `api`, `domains`, `dashboard`) that are
not a package: there is no `[build-system]`, so nothing is installed into the virtualenv and
every tool has to be told where the source lives independently — pytest through
`pythonpath = ["."]`, Alembic through `prepend_sys_path = .`, uvicorn by being run from the
root, basedpyright through `include = [...]`. Streamlit additionally creates a second root
(`dashboard/`), which is why `dashboard/views/*` import `services.*` while `taxonomy_view.py`
imports `dashboard.services.*`.

This ADR also settles what the project *is*, because that determines how much packaging it
needs: Memória Curitibana is **a system to be deployed and used**, in the spirit of AtoM, not a
library to be `pip install`ed by third parties. The code must be internally well-packaged, but
there is no public distribution to design for.

The name `memoria` is taken on PyPI by an unrelated memory-management package
(`memoria` 2025.4.27.4), so no public name is claimed at this stage.

## Decision

1. **Adopt a `src/` layout with one internal namespace package:**

   ```
   src/memoria_curitibana/
     api/  core/  domains/  dashboard/
   ```

   `main.py` stays at the repository root as the deployable entrypoint, so the
   `uvicorn main:app` command, the `Procfile` and the CI are unaffected.

2. **Do not publish to PyPI.** The distribution is built and installed locally as an editable
   internal package; `memoria_curitibana` is an import namespace, not a public artifact. This
   avoids the `memoria` collision entirely and sidesteps the naming question until the project
   actually has an institutional identity to publish under.

3. **`testing/` and `scripts/` stay outside the package** (as `testing/`, `scripts/`), together
   with `migrations/`. Tests import `memoria_curitibana.*` like any other consumer; that is what
   makes the packaging boundary real rather than cosmetic.

4. **`dashboard/` stays inside the namespace for now.** It is scheduled for replacement by a
   backend + React frontend; when that happens it becomes a separate deployable and can leave
   the package, rather than being extracted now only to be deleted later.

## Consequences

Positive: imports work from any working directory, the four `sys.path` workarounds disappear,
the Streamlit second-root hack goes away, and the packaging boundary stops `testing/` from
being importable as if it were application code.

Costs, measured before committing to it:

- **335 import lines across 111 files** to rewrite, plus `migrations/env.py` (3 imports), the
  test suite, `AGENTS.md` and `TODO.md`.
- **50 `mock.patch("domains....")` strings.** These are module paths as strings: neither ruff
  nor basedpyright can see them, so only running the suite catches a mistake. This is the main
  risk of the rename and the reason it must not be hand-edited file by file without verification.
- **17 directories lack `__init__.py`** and rely on implicit namespace packages today; the
  packaged layout requires them.
- The rename is mechanical and must land as **one commit**, so `git blame` does not dissolve
  into noise.

## Alternatives considered

- **`src/` keeping the current names** (packaging first, rename later). Rejected as a separate
  step: it moves files twice and leaves the four colliding top-level names in place, for a
  smaller first step that still has to be repeated.
- **Publishing as `memoria-curitibana` with import `memoria`.** Rejected: the project is a
  system, not a library, so claiming a public name now buys nothing and commits us to the
  name before the project has an institutional identity.
- **Monorepo (`apps/` + `packages/`) now.** Rejected: there is exactly one deployable Python
  application today; the structure would be ceremony. Revisit when the React front arrives.

## Revisit trigger

Reconsider the public packaging (and the name) if the system is distributed for other
institutions to run, or if a library boundary emerges that is worth publishing on its own.
Reconsider the monorepo when the React frontend becomes a second deployable.
