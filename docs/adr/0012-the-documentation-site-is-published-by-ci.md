# ADR 0012: The documentation site is published by CI, from `main`, into the Pages artifact

- **Status:** Accepted
- **Date:** 2026-10-10
- **Amends:** [ADR 0010](0010-documentation-coverage-and-freshness.md) §1 ("there is no hosted
  deployment yet") and its revisit trigger, which asked for `mike` "when there is a first release to
  serve and a host to serve it from".
- **Applies to:** `.github/workflows/ci.yml` (the `docs` job and the `docs-publish` job that follows
  it), `mkdocs.yml`, and the repository's Pages configuration.

## Context

The site is live at `https://cassiodalla.github.io/Scrinalia/` — English at the root, Portuguese
under `/pt/` — and it was published **by hand**. Measured on 2026-10-10, before this change:

- `gh-pages` held a single commit, `8c4d27a Deployed e96473f with MkDocs version: 1.6.1`;
- `gh api repos/:owner/:repo/pages` answered `build_type: legacy`, `source: {branch: gh-pages}`,
  `status: built`;
- the CI `docs` job built the site with `--strict` on a full-history checkout and **published
  nothing**.

So the published site was one manual command away from being stale, and nothing in the repository
said so — the failure mode ADR 0010 exists to prevent, one level up: the page said what the code
does, and the site served an older page.

The two facts that shaped the decision came from the API, not from a plan:

| measured | value |
| --- | --- |
| the `github-pages` environment's deployment branch policies | `main` and `gh-pages` only |
| the site's bytes before switching the publishing source | HTTP 200, 27,792 bytes |
| the site's bytes after switching `build_type` to `workflow` | HTTP 200, **27,792 bytes** — the last deployment keeps being served, so the switch is not an outage |
| `mkdocs build --strict` with `theme.logo`, `theme.favicon` and `extra_css` all pointing at files that do not exist | **exit 0** — the strict build gates links, never assets |

ADR 0010 deferred this on purpose — "publishing is a later decision" — and left a trigger: reconsider
`mike` "when there is a first release to serve and a host to serve it from". 1.0.0 exists and Pages
serves it, so the trigger has fired and this is the answer, not a deferral.

## Decision

### 1. The artifact path, not a deploy branch

`docs` builds the site **once** — `--strict`, full-history checkout, the pinned `uvx` toolchain it
already used — and uploads `site/` with `actions/upload-pages-artifact`. A second job,
`docs-publish`, deploys exactly that artifact with `actions/deploy-pages` and holds the only write
permission in the workflow:

```yaml
permissions:
  pages: write   # deploy the artifact to Pages
  id-token: write # prove to Pages that this run is the one that built it
```

The repository's Pages publishing source becomes **GitHub Actions** (`build_type: workflow`), a
one-time setting; the `gh-pages` branch stops being the site.

### 2. Only `main` publishes

`docs` builds on every push and every pull request; `docs-publish` and the upload are conditioned on
`github.event_name == 'push' && github.ref == 'refs/heads/main'`.

The public site documents the **release**, and `main` is the branch that moves at a release
(`CONTRIBUTING.md`): the merge that publishes is the release merge, so the site cannot describe the
integration branch. The environment's own branch policy says the same thing — it trusts `main` and
`gh-pages` and nothing else — and publishing from `dev` would need that policy loosened first, which
is a deliberate act and not a side effect of merging a typo fix.

### 3. Latest only; `mike` is still not adopted

One URL, no `versions.json`, no version switcher. The site describes the installation of the current
release, and the project supports one line at a time.

The reconsideration ADR 0010 asked for happened, and it produced a **sharper trigger** than "there is
a release": adopt `mike` when a second line has to be *supported in parallel* — a maintenance branch
serving an older release to an institution that installed it — because that is the first moment two
versions of these pages are both true at the same address. Until then a version switcher would offer
a choice between one option and an older set of install instructions.

### 4. Re-running the workflow run is the recovery

There is no dispatch input and no separate publish workflow: the artifact the deploy job takes is the
one the `docs` job built and verified in the same run, and GitHub's own "re-run jobs" re-publishes
after a transient failure. A second, hand-rolled deploy path is a second definition of "the site",
which is what this decision removes.

## Rationale

**Why not `mkdocs gh-deploy`.** It is the alternative the issue named, and it works today with no
setting changed — the environment already trusts `gh-pages`. It was rejected because it buys that
convenience with three things the artifact path does not need: the built site *in the repository's
history* (a force-pushed commit of generated HTML per publish, a second copy of every page, and one
more branch to keep honest), `contents: write` on a job whose work is otherwise read-only, and a
deploy that is a **push** — indistinguishable, in the audit log and in the branch list, from a person
pushing to the repository.

**Why not keep deploying by hand.** The deployment existed and was correct; what did not exist was
any signal that it had fallen behind. A gate that only builds is a gate that certifies a page nobody
can read: the site is what an installer opens, and it can be a release older than the tag.

**Why not publish every push to `dev`.** Two costs, and only one of them is technical. The
`github-pages` environment would have to trust `dev`; and the front page states what the system *is*
("Scrinalia is at 1.0"), which is a claim about a release, not about the integration branch. A site
that describes unreleased work is a site whose version paragraph is wrong.

**Why the theme change ships with this.** The site was already dark-navy-free: Material's default
palette (indigo) is not the identity, and `mkdocs.yml` had no `site_url`, so no canonical link and no
cross-language alternate was emitted. Both are one-line facts about the same site, and the second one
only matters once the site is published by a machine: a search engine reading a page with no
canonical URL is what turns a versioned site into duplicate content later.

## Consequences

**What changes.** A push to `main` publishes the site, and it is the only thing that does. The
`docs` job gains two conditional steps, and a new job appears in the workflow. `gh-pages` is no
longer the site's source and can be deleted once the first artifact deploy has succeeded — a
separate, visible step, deliberately **not** part of this change, because deleting it before that
deploy would be the only way this decision can take the site down.

**What the documentation gains.** `guides/operate.md` names the deploy path and the recovery, so the
next person does not have to read the workflow to find out how the site is published.

**The accepted cost.** The first publish after this change waits for `main` to move — a release — and
until then the live site is the hand-made build of `e96473f`. That is the same age it already had,
so nothing is lost, but it does mean this change is not observable on the public site until the
release merge.

**Operational.** The deploy job takes about as long as the upload of a `site/` of a few megabytes; the
build itself does not run twice. Two pushes to `main` in quick succession serialise on a `pages`
concurrency group instead of cancelling a deploy mid-flight.

## Alternatives considered

- **`mkdocs gh-deploy` into `gh-pages`.** Rejected above: build output in history, `contents: write`,
  and a deploy that looks like a push. It also keeps alive the branch whose single hand-made commit
  is the symptom this issue was filed about.
- **`mike`, versioned per release.** Rejected for now (§3). It is also incompatible with §1 as
  written: `mike` works by committing the built site into `gh-pages`, so adopting it would put the
  site back in a branch and retire the artifact path — a decision to take when the trigger fires,
  not one to leave half-taken.
- **Publishing from `dev` as a preview.** Rejected: the site's own front page makes a claim about the
  release, and the environment would have to be loosened to allow it.
- **Read the Docs or Netlify.** Rejected: a second account and a second build definition for the one
  artifact the repository already produces, and ADR 0010's own argument against a documentation site
  that depends on somebody else's account applies to the operator who installs the system and reads
  this site offline.

## Revisit trigger

Adopt `mike` when a second line is supported in parallel (a maintenance branch serving an older
release), because that is when two versions of these pages are both true. Publish from `dev` only if
the site stops being the release's documentation and becomes the project's — that is a change of what
the site *is*, and it belongs in a new ADR rather than in a condition on this one.
