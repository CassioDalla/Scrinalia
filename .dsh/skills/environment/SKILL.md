---
name: environment
description: "The agent sandbox and the toolchain caches: $HOME read-only, /tmp private per command, the workspace writable, and where uv's and pre-commit's caches must point."
whenToUse: "Before running anything through uv, pre-commit or a tool that caches under $HOME, and whenever a command dies with 'Read-only file system'."
---

# environment

## The sandbox mounts `$HOME` read-only

Measured in this environment:

| Path | State |
| --- | --- |
| `$HOME`, and therefore `~/.cache` | **read-only** |
| `/tmp` | writable, but a **private tmpfs per command** — anything written there is gone before the next command |
| the checkout (`$PWD`) | writable |

Reading under `$HOME` still works; only writing fails. So `ls ~/.cache/ms-playwright/` answers, and a
browser found there is usable — the `render` rule file depends on that.

## The consequence: every cache under `$HOME` dies

`uv` and `pre-commit` default their caches to `$HOME/.cache/...`, and the sandbox refuses the write:

```
error: Could not acquire lock
  Caused by: Could not create temporary file
  Caused by: Read-only file system (os error 30) at path "/home/<user>/.cache/uv/.tmpXXXXXX"
```

This is **not** the commit hook's problem and not a broken checkout: `uv run <anything>` fails the same
way — `pytest`, `alembic`, `mkdocs`, `docs/_hooks/freshness.py` — because `uv` takes its cache lock on
every invocation. A command that "works" without the flags is one whose cache already exists and is
warm, which is not a state to rely on.

## The fix: point the caches into the checkout

```sh
UV_CACHE_DIR="$PWD/.cache-uv" PRE_COMMIT_HOME="$PWD/.cache-pre-commit" uv run <command>
```

Both directories are gitignored (`.gitignore`), so they never reach a commit. For a single command that
does not need the cache again, `/tmp/uv-cache` also works — but see below.

## A scratch file used by a later command belongs in the workspace

The per-command `/tmp` is the second half of the same trap. A token or a payload written to
`/tmp/<name>` in one command is **absent** in the next one, and the failure reads as "the file was
never written". Write scratch state under the checkout (a directory that is gitignored, or one removed
before the commit), not under `/tmp`.
