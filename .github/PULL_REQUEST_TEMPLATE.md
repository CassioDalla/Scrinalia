## What this changes

<!-- One paragraph: the problem, and why this is the shape of the fix. The "why" is the part a
     reviewer cannot recover from the diff. -->

## How it was verified

<!-- What you ran, and what you looked at. "Tests pass" is not verification of a screen: the project
     has shipped a CSS bug that a green `vite build` did not catch. -->

## Checklist

- [ ] I read [`AGENTS.md`](../AGENTS.md), and this change does not contradict a rule it states (or the
      contradiction is explained above).
- [ ] The commits are **signed off** (`git commit -s`) and follow Conventional Commits.
- [ ] `uv run ruff check . && uv run ruff format --check .` and `uv run basedpyright` are clean.
- [ ] `uv run pytest` passes.
- [ ] If a route or a schema changed: I ran `bun run contract` and committed both
      `packages/api-contract/openapi.json` and `apps/curator/src/api/schema.d.ts`.
- [ ] If a model changed: `uv run alembic check` reports no drift, and the migration was **read**, not
      only generated.
- [ ] If the SPA changed: `bun run --cwd apps/curator typecheck && lint && build` are clean, **and** I
      rendered the screen.
- [ ] If documentation became untrue, I updated it — `README.md`, a guide under `docs/`, an ADR, or
      `AGENTS.md`.
- [ ] I removed every secret and every real personal datum from the diff and from the tests.

## Breaking change?

<!-- Delete what does not apply. A breaking change is a conversation, not a checkbox. -->

- **No.**
- **Yes** — what an existing client or installation has to change:
