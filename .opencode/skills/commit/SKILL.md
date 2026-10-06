---
name: Commit
description: Create Conventional Commits in English, splitting the working tree into one logical commit per context. Use when committing, staging, or writing commit messages in this repository.
---

# Commit

## Ground rules

- Write all commit messages in **English**, imperative mood, lowercase `type`/`scope`.
- One commit = one logical change. Split unrelated changes; never bundle them.
- Never commit secrets or generated artifacts: `.env`, `logs/`, `Data/`, `.pytest_cache/`, `__pycache__/`, `.coverage`, `htmlcov/`.
- Do **not** use `git add -A` / `git add .` blindly. Stage explicit paths. If you stage everything, unstage junk afterwards.
- Inspect reality before writing:
  - `git status --short`
  - `git diff` (unstaged) and `git diff --staged`
  - `git log --oneline -20` to match the existing style.

## Format

```text
<type>(<scope>): <subject>

<body>

<footer>
```

- `type` is required; `scope` is optional but recommended.
- `subject`: imperative, present tense, no trailing period, max ~72 chars.
- `body`: explain **what** and **why**, not how. Wrap at 72; leave a blank line before it.
- `footer`: `BREAKING CHANGE: ...`, `Refs: #123`, `Co-authored-by: ...`.

### Types

`feat`, `fix`, `refactor`, `perf`, `test`, `docs`, `build`, `ci`, `chore`, `style`, `revert`

### Scopes in this repo

`archive`, `ingestion`, `staging`, `api`, `web`, `core`, `db`, `tests`, `deps`, `ci`, `repo`

## Workflow

1. Read `git status --short` and `git diff` to understand each change.
2. Group changed files into commits **by context** (feature, fix, refactor, tests, docs, ...).
3. Order groups so each commit stays coherent; put foundations first:
   `deps/config` -> `core` -> `domains` -> `api` -> `web` -> `tests` -> `docs`.
4. For each group: `git add <explicit paths>`, review with `git diff --staged`, then commit.
5. Repeat until `git status` is clean (or only intentional leftovers remain).

## Examples

- `feat(archive): add regex cleaning worker`
- `fix(db): correct NETWORK_ERROR enum value in ingestion init`
- `refactor(ingestion): extract queue status updates into repository`
- `test(archive): cover cleaning service dry-run`
- `docs(repo): add AGENTS.md`
- `build(deps): add alembic and ruff to dev dependencies`

## Notes

- Breaking change: add `!` after the scope, e.g. `feat(api)!: rename taxonomy routes`.
- Prefer several small commits over one large one, even within a single feature.
- Only amend, force-push, or skip hooks when the user explicitly asks.
