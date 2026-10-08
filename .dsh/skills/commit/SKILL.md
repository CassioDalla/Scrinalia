---
name: commit
description: "Create Conventional Commits in English, splitting the working tree into one logical commit per context, with the DCO sign-off every commit must carry. Use when committing, staging, or writing commit messages in this repository."
---

# Commit

## Ground rules

- Write all commit messages in **English**, imperative mood, lowercase `type`/`scope`.
- One commit = one logical change. Split unrelated changes; never bundle them.
- **Every commit is signed off**: `git commit -s`. See [DCO](#dco).
- Never commit secrets or generated artifacts: `.env`, `logs/`, `Data/`, `.pytest_cache/`, `__pycache__/`, `.coverage`, `htmlcov/`.
- Do **not** use `git add -A` / `git add .` blindly, and never stage a whole file just because one hunk of it is yours: `git add <file>` stages **every** change in that file, including work somebody else left uncommitted in the same checkout. Stage explicit paths, or `git add -p` when the file is shared.
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
- `footer`: `BREAKING CHANGE: ...`, `Refs: #123`, `Signed-off-by: ...`, `Co-authored-by: ...`.

### Types

`feat`, `fix`, `refactor`, `perf`, `test`, `docs`, `build`, `ci`, `chore`, `style`, `revert`

### Scopes in this repo

`archive`, `repo`, `api`, `web`, `taxonomy`, `db`, `staging`, `ingestion`, `core`, `identity`,
`curator`, `deploy`, `deps`, `ci`, `adr`, `todo`

Any short lowercase word naming the area is fine; these are the ones the history already uses.

## DCO

Every commit must carry a `Signed-off-by:` trailer certifying the
[Developer Certificate of Origin](https://developercertificate.org/). `git commit -s` appends it
from `user.name` and `user.email`:

```text
Signed-off-by: CassioDalla <cassiodalla@hotmail.com>
```

- It certifies that you wrote the change, or have the right to submit it, and that it may be
  distributed under this project's license. It is **not** a copyright assignment — you keep the
  copyright of your contribution. There is no CLA.
- `git commit -s` on every commit is the whole workflow. The flag also works with `--amend`, and
  `git rebase --signoff <base>` retro-fits a branch that was committed without it.
- CI checks the trailer on every commit of a pull request (the `dco` job in
  `.github/workflows/ci.yml`) and fails without it.
- Never sign off on somebody else's behalf, and never hand-write somebody else's name and address
  into the trailer: the sign-off is a statement by the person who wrote the commit.

## Workflow

1. Read `git status --short` and `git diff` to understand each change.
2. Group changed files into commits **by context** (feature, fix, refactor, tests, docs, ...).
3. Order groups so each commit stays coherent; put foundations first:
   `deps/config` -> `core` -> `domains` -> `api` -> `web` -> `tests` -> `docs`.
4. For each group: `git add <explicit paths>`, review with `git diff --staged`, then
   `git commit -s` with the message.
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
- **The pre-commit hook stashes what is not staged**, so it type-checks the **staged** tree: a commit
  that stages half of a Python change can fail `basedpyright` on code that is fine in the working
  tree. Commit the Python of one change together, or order the commits so each one is self-consistent.
- If the hook dies writing its cache with `Read-only file system`, point the cache into the checkout
  and retry: `PRE_COMMIT_HOME="$PWD/.cache-pre-commit" UV_CACHE_DIR="$PWD/.cache-uv" git commit -s`.
