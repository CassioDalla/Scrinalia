# ADR 0008: The language lives in code, the collection vocabulary lives in the database

- **Status:** Accepted
- **Date:** 2026-10-07
- **Applies to:** the commits that removed the dead ArqDoc settings, moved the Portuguese data
  into `core/language`, added the two vocabulary catalogues and made the scraper adapter receive
  its origin.

## Context

Phase 5 listed "decouple what is specific to one institution" among the 1.0 blockers, with three
measured items: the dead `ARQDOC_*` settings, the `VOCABULARY_BY_TOKEN` map of IPPUC/SMU
secretariats, and the `_PLACE_NAME` regex holding the bairros of Curitiba. The post-1.0 backlog
extended the same question to the whole Portuguese language: a 573-line stopword list inside the
clustering engine, the date grammar inside the staging parser, the street and measure patterns
inside the subject guard, and the plural rules inside the normaliser.

Every one of those was a constant read at runtime. For another institution to install the system,
each had to be replaced without editing the software.

`TODO.md` left the design question open: **database (table + routes + screen) or a versioned
configuration file?** The note observed that the three catalogues already in the system — the
NOBRADE ladder, the subject drawers and the documental typologies — are tables, so consistency
pulled toward the database.

**The question as posed was the wrong shape, because it treated one class of data as two.**
Looking at what each artefact actually decides, the artefacts fall into three families with
different owners and different lifecycles:

1. **The language.** `STOPWORDS_BR` (573 lines, zero test coverage), the date expressions
   (`década de`, `anos`, `a`/`até`), the street prefixes (`rua`, `avenida`, `praça`), the
   placeholder spellings (`não identificado`), the measure units (`anos`, `meses`, `metros`) and
   the plural endings (`ões`→`ão`). These are properties of Portuguese, not of the archive.
2. **The collection.** The arrangement token map (`SMU`, `ED`, `AL`) and the non-subject terms the
   guard recognises: the bairros of Curitiba and the person names. These are statements about
   *this* archive; another institution's collection has other names.
3. **The origin.** The scraped site's URLs, which are already configuration — but the adapter read
   them from the global `settings` singleton instead of receiving them.

Two facts forced the split rather than a preference:

- **The full-text dictionary reaches a generated column.** `search_vector` is built with
  `to_tsvector('portuguese', …)`. A language cannot be switched by an environment variable alone,
  because the column is stored. Putting the language in the database would have made a language a
  row that the schema still would not follow.
- **A person's name and a street are answered differently.** `is_subject_candidate` refuses a
  street *and* `is_place_term` claims it for the PLACE facet, while a person's name goes nowhere.
  The collection's two families have destinations; the language's three are refusals with no
  destination. Mixing them in one table would erase that distinction.

## Decision

**Three families, three homes.**

### 1. The language is code: one profile per language

`src/scrinalia/core/language/` holds a frozen `LanguageProfile` stating everything a language
contributes — stopwords, date grammar, term shapes, plural rules, the full-text dictionary and the
spaCy model — and `pt_BR` is the profile the deployment ships. `ACERVO_LANGUAGE` selects it.

The **rules did not move**: `staging/dates.py` still parses dates, `domain/vocabulary.py` still
guards terms, `domain/normalization.py` still singularises. They now read the profile instead of
carrying a copy of its data, so a second language adds a profile rather than a second parser.

### 2. The collection vocabulary is data: two catalogues, one screen

- `archive_arrangement_vocabulary` — token (or whole code) to the name the hierarchy proposal
  suggests. The whole code wins over its last token, which is what lets `BR PRADAP` have a name of
  its own next to `SMU`.
- `archive_collection_terms` — the non-subject terms, typed by `CollectionTermKind`
  (`DISTRICT`, `MUNICIPALITY`, `STATE`, `REGION`, `COUNTRY`, `PERSON`). A place kind claims the
  PLACE facet; `PERSON` goes nowhere.

`GET/POST/PATCH /api/v1/vocabulary` exposes both and `apps/curator` renders them at
`/vocabulario`. Like the other three catalogues, **neither deletes**: `is_active=false` retires a
row, because removing an arrangement name would make the proposal suggest nothing again and
removing a collection term would make a term the archivist refused come back into the subject axis.

The guard stays **pure and deterministic**: it is handed a `CollectionVocabulary` value object
instead of reading a constant, and an installation whose catalogue is empty refuses nothing of its
own. There is deliberately **no fallback to the reference collection** — a fallback would make
every other institution's installation silently Curitiba.

The migration seeds the reference collection, so the deployment's behaviour is unchanged: 38
arrangement terms and 71 collection terms (55 places and 16 person names). The seed is duplicated
in the migration on purpose — a migration must keep describing the state it produced — and pinned
against the domain mirror by a test, the pattern the NOBRADE ladder and the subject drawers already
follow.

### 3. The origin is a parameter

`SourceConfig` (`domains/ingestion/ports.py`) carries what a scraping adapter needs to reach its
origin, and `PMCScraperAdapter` takes it as a parameter. `build_scraper_adapter()` in the ingestion
worker is the only place that reads `PUBLIC_SCRAPE_*`, and it fails fast on a missing URL.

**The selectors and the Portuguese field names scraped from the page stay inside the adapter.**
They are the contract with *that* site; no configuration value abstracts an HTML layout. This is
the line between "the adapter declares what it needs" and "the adapter is generic", and only the
first was the goal.

### 4. Dead configuration is removed, not deprecated

`ARQDOC_BASE_URL` and `ARQDOC_VIEW_ENDPOINT` existed in `config.py`, were read by nothing but the
health panel, and are gone — along with `arqdoc_configured` from `ProcessHealthDTO`, which took the
OpenAPI document and the generated client with it.

## Rationale

- **The owner decides the split, and the split follows the owner.** The archivist owns the names of
  their collection and must edit them without a deploy; nobody owns the Portuguese plural rules, and
  a curator editing them would be changing what the software means by a word.
- **A language is not a row.** A profile is a constant of the process, testable in isolation, and a
  second language is a module — the alternative is a database that must be populated correctly
  before the parser works at all.
- **The database gives the catalogue the same properties as the three that exist**: no deploy to
  change a name, retirement instead of deletion, and one place the read model comes from.
- **The system is single-institution by construction, and the ADR says so rather than inventing a
  tenant.** Measured across all 30 tables, there is no `institution_id`, `collection_id` or
  `organization_id` anywhere; the deployment *is* the institution. The catalogues are therefore
  global, and plural institutions in one installation is a separate decision that would need a
  scope column on every reader — not something to smuggle in through the vocabulary.

## Consequences

Positive:

- Another institution replaces the names it disagrees with through the screen, and the software
  carries no Curitiba constant that reaches a worker.
- The Portuguese data has one home, which is what makes a second language a module instead of an
  audit.
- The guard is more testable than before: `testing/unit/archive/domain/test_vocabulary.py` pins the
  language's verdicts, `test_collection_vocabulary.py` pins the seed mirror and the lookup rule, and
  `testing/unit/core/test_language.py` proves the rules *read* the profile by swapping it for a fake
  one.
- `ACERVO_LANGUAGE` is a real seam: the FTS dictionary and the NER model come from the profile, so a
  language change surfaces as `alembic check` drift instead of a silently mixed installation.

Negative, and accepted:

- **Changing the language is a schema change, not a reboot.** The generated `search_vector` is built
  with the profile's dictionary, so a new language needs a migration that rebuilds it. This is
  stated in `config.py`, in `.env.example` and here, because it is the one place where the profile
  reaches stored data.
- **The seed mirror is a second copy of the reference vocabulary**, kept honest only by a test. That
  is the same trade the three existing catalogues made, and the alternative — importing application
  code into a migration — would make replaying history depend on the current constants.
- **The language pack does not make the product multilingual.** Prompts written to reason about
  Portuguese text, the ISAD(G) keys that must match the external payload, and the ~334 Portuguese
  strings in the SPA are untouched. The first two are deliberate (`AGENTS.md`); the third is the
  i18n item in the post-1.0 backlog, and `routeMessage()` remains the seam where it lands.
- **`domain_stopwords` is not the language's stopword list and must never become it.**
  `domain_stopwords` is a curator's decision about the *subject axis*, scoped by `word_scope`;
  `PT_BR.stopwords` is what the clustering engines discard before vectorising. Collapsing them would
  let a NER veto silence a tag the curator kept.
- **The database name `memoriacuritibana` still carries the city.** It is data identity, and ADR
  0007 already decided it stays.

## Alternatives considered

- **Everything in the database** — one settings table for the language, one for the collection. The
  consistency argument was real, and it was rejected on two grounds: the FTS dictionary cannot be a
  row without the schema following it, and a parser that needs a populated table to work is a
  bootstrap problem the project does not have today.
- **Everything in a versioned configuration file** (TOML/YAML per institution). Simpler to audit and
  version, and rejected because it moves the edit the archivist most needs — a name their collection
  carries — behind a deploy, which is exactly the property the three existing catalogues were built
  to avoid.
- **A hybrid: defaults in code plus a database override**, like `archive_worker_settings`. Rejected
  because the default would then be the reference collection, and "the default is Curitiba" is the
  defect this ADR exists to remove.
- **Keeping the constants and documenting them as the reference profile.** Rejected: the reference
  collection is data, and the code would still be the only way to change it.
- **A `SourceConfig` that also carries the selectors**, so the adapter becomes fully generic.
  Rejected as a fiction: an HTML layout is not configuration, and a config file that pretends to
  describe one would break on the first redesign of the site.

## Revisit trigger

Revisit if a single installation ever has to serve **two institutions or two collections at once**.
The catalogues are global precisely because the deployment is the institution, and the first real
requirement for plural collections invalidates that premise everywhere — not only in the vocabulary,
but in every reader that today assumes one collection. Also revisit if a second language is added:
that is the moment to check whether the profile contract is complete, and the first profile written
after `pt_BR` is the only honest test of it.
