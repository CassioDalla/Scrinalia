# ADR 0007: The project is named Scrinalia

- **Status:** Accepted
- **Date:** 2026-10-07
- **Applies to:** the commit `refactor(pkg)!: rename memoria_curitibana to scrinalia`, which
  landed immediately before this record.

## Context

Phase 5 of `TODO.md` listed the name among the 1.0 blockers, and the reasoning was the same as
for the license: the name is the identity of the release, and renaming *after* 1.0 means 1.0 ships
with a name that is about to be discarded, breaking every link, bookmark and document twice.

The name in use, `memoria_curitibana` (plus an `-etl` suffix in `[project].name`), had three
separate defects:

1. **It named one city.** The stated goal is an institution-agnostic system that another archive
   can install; a name with *Curitibana* in it contradicts the product it is trying to be.
2. **`-etl` named a piece of infrastructure.** It describes a mechanism, not the thing itself, and
   it dates.
3. **"Memory" does not say "archive".** The domain is archival description, and the word that
   carries that meaning was available to be used.

The requirements for the replacement were: international and pronounceable in Portuguese and
English; rooted in the domain, not in a technological fashion (no `AI`, `GPT` or `ETL`); not tied
to an institution or to a standard (`ISAD(G)` may not be the last one); spellable from hearing;
short enough for an import identifier; and free in the namespaces that matter.

**The method matters as much as the outcome, because the first pass was wrong.** An initial
availability check looked only at PyPI and npm and concluded that `Tabularium` had "two hobby
projects" against it. A deeper pass — package registries, container registries, DNS, and then
registered trademarks and live commercial products — disqualified it outright. The lesson is
recorded here so the next naming exercise does not repeat it: **a name is not available just
because it is free in the package index you happened to check, and the collision that matters is
usually not in a package index at all.**

## Decision

The project is **Scrinalia**.

- Python distribution and import: `scrinalia`. Repository: `scrinalia`. Display name: `Scrinalia`.
- **No alias is kept** for the old import path. A compatibility shim would keep the discarded name
  alive in every traceback, and the project is installed rather than depended upon, so the cost
  falls on forks rather than on library consumers.
- **The rename does not touch data identity.** The database name `memoriacuritibana`, the legacy
  database `memoriacuritibana_legacy`, the MinIO bucket `memoria-curitibana-bronze` and every
  `archive_*` / `domain_*` schema object keep their names. Those are what a running installation's
  data is found by; renaming them would point a working deployment at empty data for a purely
  cosmetic gain. This is the same distinction the license decision drew between the project and
  what it holds.

## The name

**`scrinium`** is Latin, and it meant the round case that held scrolls and papers. By extension it
named the **record offices of the later Roman and Byzantine administration** — `scrinium memoriae`,
`scrinium epistularum`, `scrinium libellorum`, `scrinium dispositionum` — a usage the papal curia
also kept, and one documented in reference works (the Italian encyclopaedias carry an entry for
the *scriniari*, the officials who served in one). A **`scriniarius`** was therefore an archivist
or registrar: the person responsible for the contents of the archive, not merely its building.

The ending is **`-alia`**, the Latin neuter plural of adjectives in `-alis`, which survives in
exactly this sense in the languages this project is written for: *marginalia* (the things in the
margin), *memorabilia* (the things worth remembering), *naturalia*, *mirabilia*, *curiosa*. It is
the pattern a collection of things is named with — and memory institutions already use it *as*
institutional vocabulary.

So the name reads structurally as **"the things of the archive"**, which is a description of what
the system holds: a body of descriptions, kept together and made findable in a plural collective
rather than a singular building.

Two honest notes about the word:

- **`scrinalia` is coined, not attested Latin.** The root and the ending are both real and the
  formation is regular, but no dictionary contains the compound. This is deliberate and it is the
  entire point: the meaning comes from the root and the grammar, while the collision surface comes
  from the form — and the form is empty.
- **Portuguese keeps the root.** *escrínio*, a cabinet for papers, descends from `scrinium`. So the
  name is not alien to the Brazilian archivist even though it is not part of the language. (Its
  neighbour *escrivão* comes from a sibling root, *scribanus*, off *scribere* — not this one.)

## Rationale

- **Every real archival word tested was already claimed.** Measured (2026-10-07) across PyPI, npm,
  crates.io, Docker Hub, the six relevant TLDs, the GitHub namespace and a trademark search:

  | Candidate | What was found |
  | --- | --- |
  | `Tabularium` | **A records-management system of the MPDFT, in production since 2016**, formalised by *portarias* and reported on at five years; also an active crates.io crate, six Docker Hub repositories including an org with `tabularium-api` + `tabularium-web`, a GitHub user since 2014, and **every** domain taken including `.com.br` |
  | `Cimelia` | **A live registered trademark** (EUIPO 017967984, plus its UK equivalent) held by an insurer; also a recycling company; `.com` and `.app` taken |
  | `Repertorium` | A live AI company at `repertorium.com/.org/.eu` |
  | `Arkheion` | A Brazilian `arkheion_backend` + `arkheion_frontend` pair on Docker Hub; and the `kh`/`ch` spelling is ambiguous |
  | `Arkheum` | Four plausible spellings (`arkeum`, `arkheum`, `archeum`, `arqueum` — and Portuguese actively pushes toward the `qu` one, as in *arquivo*), `.com` and `.org` taken, on a root that also carries a software company and a geological eon |
  | `Chartularius` | Free everywhere, but the twin spelling **Cartularius** is a live document-management product that has already claimed the same "document guardianship" framing |
  | `Chartalia` | A US limited liability company |
  | `Pinakora`, `Tabuleum` | Free, but without `.com` |

  The outcome is not that a better real word was found — it is that **for this project the class of
  available real words is empty**, and coining is what removes the constraint rather than working
  around it.
- **`scrinalia` is free on everything measured.** PyPI, npm, crates.io, NuGet, RubyGems, Packagist,
  the Go module proxy, Docker Hub (zero hits), the GitHub username, and **all six domains** —
  `.com`, `.org`, `.io`, `.dev`, `.app` and `.com.br`. A web search returns nothing at all.
- **One spelling.** This was the deciding argument in the final comparison, and it is a practical
  one rather than an aesthetic one: a name must be *typed*. It appears in `pip install`, in a
  repository URL, in a domain, and — under the additional term of ADR 0006 — in the footer
  attribution that every fork is obliged to preserve. A name that cannot be spelled from hearing
  gets misspelled in the one place the license forces it to be copied. `scrinalia` has exactly one
  spelling; the rejected `arkheum` had four.
- **The root is about archives, not about origins in general.** `arkhē` is a fine root, but it
  reaches archives through *origin*, and it carries geology, philosophy and a software company
  along with it. `scrinium` reaches them directly: it is the word for the container and the office
  that held the records.

## Consequences

Positive: the name no longer ties the system to a city, to a standard or to a technology; it is
free in every namespace that matters, so a release can claim the distribution name, the domain and
the username without negotiation; the etymology is checkable and specific; and because the
database, the bucket and the schema were deliberately left alone, **an existing installation
migrates by pulling and re-syncing, with no data migration at all**.

Negative, and accepted:

- **The import path changes with no alias**, so anything importing `memoria_curitibana` stops
  working. Nothing outside this repository does, which is why the alias was not worth its
  lifetime cost.
- **The GitHub repository and the checkout directory still carry the old name.** The footer's
  `sourceUrl` points at `https://github.com/CassioDalla/Scrinalia`, which is the §13 offer of
  Corresponding Source and must resolve — so renaming the repository is not optional politeness,
  it is part of the same operation, and until it happens that link is a 404. **Resolved:** the
  repository is now `Scrinalia`, the canonical capitalisation, matching the display name; GitHub
  redirects the old lowercase URL, so nothing that already cited it broke. The local directory
  additionally feeds the editable install's `.pth`, so `uv sync` is needed after renaming it.
- **The container and image names changed** (`scrinalia_db`, `scrinalia-postgres:15`), which
  requires recreating the containers. The volume is untouched: `docker compose down` then up, and
  **never** `down -v`, which would delete the collection.
- **`scrinalia` is a coined word, so it has to be taught.** There is no prior meaning to borrow for
  recognition, which is exactly why this ADR carries the etymology: the name's meaning now lives in
  the documentation because it lives nowhere else.
- **Git's rename detection missed one file** in the rename commit (a small `__init__.py` whose
  content changed past the similarity threshold), so `git show --stat` reports one deletion rather
  than 173 renames. File counts and a symmetric diff of the package were used to verify that
  nothing was lost.

## Alternatives considered

- **Keeping `memoria_curitibana`.** Free, and zero work. Rejected: it fails the stated goal
  outright, and the cost of fixing it only grows.
- **`Tabularium`** — the initial recommendation, and the one that shows why the method in Context
  matters. Rejected: a Brazilian public-sector records system of the same sector has used the name
  since 2016. Adopting it would make this project look like a copy of a government system, or the
  reverse.
- **`Cimelia`** — short, and instantly legible to a Portuguese speaker through *cimélio*. Rejected
  on the one class of collision that can actually stop a project later: a third party holds live
  registered trademark rights in the name.
- **`Repertorium`** — conceptually the tightest of the real words, since a *Repertorium* is the
  finding aid that archival work produces. Rejected for a live company of the same name.
- **`Arkheion`** and **`Arkheum`** — the most evocative roots, and the closest calls. Rejected on
  the spelling argument above, and because the root is crowded.
- **`Chartularius`** — free everywhere and etymologically perfect (it means *archivist*). Rejected
  because its twin spelling is a live commercial document-management product that already occupies
  the same "guardian of documents" meaning, which would make search and identity permanently
  ambiguous.
- **A coined compound on a different root**, such as `pinakora` (from the *Pinakes*, Callimachus's
  catalogue at Alexandria — arguably the best story of any candidate). Rejected only because
  `.com` was taken while `scrinalia` took everything.

## Revisit trigger

The name is the identity of the 1.0 release, so the trigger for changing it is not a technical
event but a strategic one: **if the project is ever to be presented as Software Público Brasileiro,
or adopted under a public programme that requires a name with an owner, revisit this.** A coined
name is deliberately unowned, which is a virtue for adoption and a problem for any process that
expects a trademark holder. Also revisit if a *Scrinalia* appears in the archival sector: the name
being free is a fact about 2026-10-07, and the measurements above are dated for that reason.
