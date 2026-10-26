---
name: release
description: "Cut a release: bump the single version, prepare the changelog and the citation on a release branch, merge `dev` into `main`, and leave the tag to the Release workflow. Use when the version changes, when `dev` is merged into `main`, or when the user asks to cut or publish a release."
whenToUse: "When asked to bump the version, cut a release, or merge `dev` into `main`."
---

# Release

`main` moves only at a release, through a `dev` → `main` pull request; the tag is created by the
`Release` workflow, never by hand (`.github/workflows/release.yml`, `CONTRIBUTING.md`). A merge into
`main` without the release preparation leaves the changelog and the citation claiming the previous
version, and the next release inherits the debt. After the tag, `dev` is fast-forwarded to the release
commit (step 7), so the next cut starts from the tag and not behind it.

Read `commit` for the message format and the DCO sign-off; every commit here uses both.

## 1 — Choose the version

The next semantic version is a human decision; the Release workflow prints what Conventional Commits
imply but never infers it. Read the range with
`git log --oneline "$(git describe --tags --abbrev=0)"..dev`.

## 2 — Bump the version on `dev`

`pyproject.toml` is the single declaration; these follow it:

| File | What changes |
| --- | --- |
| `pyproject.toml` | `[project] version` |
| `apps/curator/package.json` | `version` |
| `CITATION.cff` | `version` (the date waits for step 3) |
| `README.md` | the `Status:` line |
| `docs/index.md`, `docs/index.pt.md` | the `1.x` phrase |
| `.github/workflows/release.yml` | the input description and default |
| `.github/ISSUE_TEMPLATE/bug_report.yml` | the placeholder |

Then let the generated and locked files follow, rather than editing them by hand:

```sh
UV_CACHE_DIR="$PWD/.cache-uv" uv sync   # installed metadata -> the API version
bun run contract                        # openapi.json + schema.d.ts
UV_CACHE_DIR="$PWD/.cache-uv" uv lock   # uv.lock
bun install                             # bun.lock
```

`uv lock --check` must pass, and `git diff` after `bun run contract` must be empty. Commit
`chore(release): bump the version to X.Y.Z` with `-s`.

## 3 — Prepare the release on a branch from `dev`

```sh
git checkout -b "release/X.Y.Z" dev
```

**Cut this branch from the `dev` tip that already contains the version-bump pull request.** The 1.4.0
cut branched before the bump PR merged: the merge into `main` recorded the content but not the `dev`
merge commit, so `git log dev ^main` still showed one commit after the release and the two branches
diverged. The clean order is bump → pull request into `dev` → merge → update `dev` → cut this branch.
If the branch was already cut, the repair is a **history-only sync**: merge `dev` into a branch off
`main`, keep `main`'s changelog and citation, and the tree does not change — only the merge commit is
recorded. Do it **before** the Release workflow tags.

- **CHANGELOG.md.** Add `## [X.Y.Z] - YYYY-MM-DD` with only the entries since the previous release.
  The previous release's section stays exactly as it shipped. The `[Unreleased]` link moves to
  `compare/vX.Y.Z...HEAD`, and an `[X.Y.Z]` tag link joins the footer.
- **CITATION.cff.** Set `date-released`.
- Commit `build(repo): the release is X.Y.Z` with `-s`.

**Do not build the changelog from `main`'s copy.** `dev` accumulates the next release's entries in
`[Unreleased]` and may carry a fix that `main` does not — the 1.4.0 cut found `main`'s copy missing
the `[1.2.0]` section that `dev` had restored. Start from `dev`'s `CHANGELOG.md`, remove the entry
blocks that belong to the new release, and turn the remainder into the previous release's section.
`testing/unit/repo/test_changelog.py` checks the result: one section per link, versions and dates
descending, and `[Unreleased]` comparing from the newest release.

## 4 — Merge into `main`

```sh
git checkout main
git merge --no-ff --no-commit "release/X.Y.Z"
# CHANGELOG.md and CITATION.cff conflict: keep the release branch's versions
git checkout --theirs -- CHANGELOG.md CITATION.cff
git add CHANGELOG.md CITATION.cff
git commit -s
```

The merge commit is the release commit; the Release workflow tags it. Do not `git tag` by hand, and
never re-point a published tag — a released version moves forward only through a patch.

## 5 — Verify

```sh
UV_CACHE_DIR="$PWD/.cache-uv" uv run pytest testing/unit/repo testing/unit/docs -q
git log --oneline dev ^main   # must be empty: main contains every dev commit
git diff --stat main..dev     # only the release-preparation files
```

If `git log dev ^main` is not empty, stop before tagging: the release branch was cut before the
version-bump PR merged, and the history-only sync in step 3 is what repairs it.

Check the version in each declaration (`pyproject.toml`, `package.json`, `openapi.json`,
`CITATION.cff`, `README.md`) and confirm the committed contract matches
`uv run python -m scrinalia.api.dump_openapi`.

## 6 — Publish

Actions → Release → *Run workflow* with the version: `dry_run: true` first, then `false`. The workflow
validates the version, builds the SPA and the SBOM, attests provenance, and creates the tag and the
GitHub Release. It does not update the changelog.

`main` is pushed as a release pull request, not with a direct push. `dev` keeps moving after the
release; do not reset it to `main` — step 7 moves it forward to the release commit, and the work that
lands on it afterwards stays.

## 7 — Bring the release commit back into `dev`

The release commit — the one the tag points at — exists only on `main`, and the next release branch is
cut from `dev`. If `dev` does not contain it, that branch starts behind the tag: `git describe` names
the previous release, the changelog has the released entries back in `[Unreleased]`, and the release
has to rebuild the released sections from `main` — the debt 1.5.0 inherited and 1.6.0 paid.

Right after the merge, `dev` is an ancestor of `main`, so the sync is a fast-forward and the two
branches end at the **same commit**:

```sh
git checkout dev
git fetch origin
git merge --ff-only origin/main   # fails if dev moved; see below
git push origin dev
```

No pull request: the tree does not change, only the branch pointer moves. Do **not** sync it through
a PR merged with a merge commit — `dev` would end one empty merge commit ahead of `main`, the same
tree at a different commit, and the next release would carry that commit into `main`. The 1.6.0
release did exactly that (#218) and left `dev ^main` at one commit.

If `dev` already moved past the merge, the fast-forward fails — that is the guard, not an error. Then
the sync is a real merge: merge `main` into a branch off `dev`, open a pull request, and keep `main`'s
changelog and citation; the tree does not change, only the merge commit is recorded. Do it before
cutting the next release, not necessarily on the day of this one.
