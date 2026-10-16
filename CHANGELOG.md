# Changelog

All notable changes to this project are documented here. The format is
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project follows
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

`1.0.0` was the first release; the newest one is at the top. Entries describe **behaviour**, not
commits — the history is the detail.

## [Unreleased]

### Added

- **The typology classifier has a bench, and the first measurement puts the failure somewhere other
  than where the issue expected it** (issue #69): `testing/evaluation/typology_quality.py` scores the
  classifier against a labelled set and prints agreement, per-typology precision/recall/F1, the
  confusion matrix, the label distribution (largest share, entropy, abstentions) and seconds per
  document — one line per configuration, `--config engine:preset:columns:threshold`, the four fields
  `worker_typology.producer_identity` signs. `--pick` proposes the labelled set, which is collection
  data and stays out of the repository, with its shape versioned in `testing/evaluation/README.md`.
  Nothing reaches the database: the session is opened, read and rolled back. An integration test pins
  the scored text to the text the worker hands the model, with an approved excerpt in the middle so
  the pin bites.

  **Measured on 2026-10-14 against `memoriacuritibana` (4.813 descriptions), on 111 labelled rows.**
  The gabarito was pre-labelled by an agent and then **reviewed row by row by the curator on
  2026-10-16, who confirmed all 112 rows unchanged**: the review moved the signature, not the
  numbers — the only field touched after the measurement was `confidence`, which no metric reads, and
  re-running the stored mode reproduces the recorded report exactly.

  | configuration | agreement | macro-F1 | abstention | s/doc |
  | --- | ---: | ---: | ---: | ---: |
  | `original_title,admin_bio_history` @ 0.40 | 0.847 | 0.701 | 0.207 | 6.36 |
  | `original_title` @ 0.40 (the shipping one) | 0.775 | 0.484 | 0.054 | 2.06 |
  | `original_title` @ 0.30 | 0.757 | 0.481 | 0.018 | 2.05 |
  | `original_title` @ 0.55 | 0.739 | 0.479 | 0.171 | 2.00 |
  | `original_title` @ 0.70 | 0.721 | 0.449 | 0.324 | 1.96 |

  Two readings the numbers force. **The columns matter more than the floor**: reading the archival
  history beside the title lifts agreement by 7 points and macro-F1 by 22, and turns the control
  bucket — 11 descriptions no typology covers — into 11 abstentions; with the title alone the model
  puts 8 of those 11 into "Ofício / Memorando", the label it uses as a dustbin (18 answers there, 0
  of them right). The price is 3.1x the seconds per document. **The confidence floor is a band, not a
  cliff**: 0.30/0.40/0.55/0.70 agree at 0.757/0.775/0.739/0.721, so the 0.40 has a measurement behind
  it for the first time and is the best of the four on this set — by four rows out of 111, which is
  not a decisive difference. The floor stays 0.40, and moving it is its own issue.

  On this sample the model does **not** collapse: the largest drawer holds 42% of the answers in a
  sample that is already 40% "Planta Arquitetônica". The sample is balanced by construction, so it
  cannot refute the collapse the issue measured on the unbalanced reference collection — the whole
  collection is what a collapse measurement needs, and the stored mode prints that distribution in
  one query (4.205 of 4.813 descriptions carry no typology at all).

## [1.2.0] - 2026-10-13

### Added

- **A whole category of tag × entity collisions decided in one call** (issue #35):
  `POST /api/v1/taxonomy/conflicts/resolve/batch` applies one verdict to the selection the
  collisions screen is showing — the same `pair_kind`, `entity_type` and `threshold` — because "a
  street is an entity" is a decision about a category, not about a pair, and the screen could only
  ask one pair at a time. The unit of the write stays the **pair**: each one is planned by the
  same planner the single preview uses, written inside its own savepoint with its own ledger row,
  and therefore undoable on its own. A pair an earlier pair of the same batch already finished is
  reported in `skipped` with its reason and never as a failure; `limit` bounds one request (the
  screen writes 50 at a time and the route accepts at most 200); and `remaining` is the same read
  the screen makes, taken again, so the number before the click and the number after it are one
  measurement. The live list gained the `entity_type` filter the batch selects with.

- **Unifying entities is reversible** (issue #34): the entity merge now goes through the same two
  halves as the tag merge. `POST /api/v1/taxonomy/entities/merge/preview` is the plan alone — how
  many descriptions gain the canonical, how many links are rewritten, which names are absorbed and
  which warnings to read — computed by the same planner the write executes, so the dry run cannot
  promise a different number from the merge. The write is logged **before** anything changes, one
  row per absorbed entity in `archive_entity_merge_log`, capturing the row, its links, its
  spellings and the canonical name the optional rename replaces;
  `DELETE /api/v1/taxonomy/entities/merge-log/{merge_id}` restores exactly that, and
  `GET /api/v1/taxonomy/entities/merge-log` is the trail, searchable by either spelling. The
  entities screen shows the impact before the click, offers the undo right where the merge was
  made, and keeps the ledger below. Entities still have no proposal catalogue.

- **A named entity can be renamed, with an undo of its own** (issue #85):
  `PATCH /api/v1/taxonomy/entities/{entity_id}` is the write the entity vocabulary was missing —
  the screen's only rename field lived inside the merge panel, so correcting a plain typo meant
  absorbing another entity. The previous spelling stays anchored as a synonym unless
  `keep_old_synonym` is turned off, and the write leaves one `RENAME` row in the merge's own
  ledger, so the ledger's *desfazer* reverses it: one ledger, one "put the name back". A spelling
  another entity already carries is refused before the write, with `DuplicateEntityNameError`
  (409) naming the twin and pointing at the merge rather than the generic structural conflict.

- **An entity expands into the descriptions that carry it** (issue #86): the entities screen
  showed the weight of a name and no way to see which descriptions carried it.
  `GET /api/v1/documents` accepts an `entity_id` — the same `EXISTS` predicate keyed by id that
  `entity_type` already used, written once as `document_repo._carries_entity` so "carrying this
  entity" cannot drift into a join that multiplies rows — and the card opens into those
  descriptions, paged ten at a time, with the badge above and the expansion's `total` one number
  counted twice, pinned by a test. A row opens the read-only preview the category screen already
  uses, and its *Editar* lands on the dossier's **Assuntos** tab, which is where a description's
  entities are added and removed. The row is restructured like the category card — the name and
  badges inside the toggle, the controls (checkbox, type, delete) outside it — because a control
  nested in a toggle is a click that means two things at once.

- **The entity merge has a third door, fed by the type-ahead** (issue #87): both existing doors
  into the merge panel are list-driven and the archivist controls neither — Relevância is ordered
  by weight and capped at fifty rows, and Similaridade answers by trigram, the one measure that
  fails on the pair the archivist is most sure about. Measured on the reference collection, `smu`
  carries 68 descriptions and `smcs secretaria municipal de comunicação social` carries 1, and
  their trigram similarity is 0.045, so neither list can show the pair. A *Mesclar pelo nome* card
  above the tabs takes the names through the type-ahead the dossier's Assuntos tab already uses,
  inheriting the API's own two-character floor instead of inventing one and showing each name's
  weight so the canonical is chosen with the numbers in view; with two members it renders the same
  merge panel, one panel with three doors. Its list is its own and does not consume the relevance
  checkboxes.

- **The tag catalogue can decide a subject** (issue #82): `GET /api/v1/taxonomy/tags/catalog`
  filters and pages by `subject_state` — `PENDING`, `NOT_SUBJECT`, `LOW_CONFIDENCE`, `ALL` — plus
  `macro_category_id`, and the fifth tab, *Classificar*, is where the decision is taken: file a
  tag in a drawer, or declare it **not a subject**, one row at a time or over a selection. The
  query key is `subject_state` and not `state`, which Litestar reserves for the ASGI state. The
  predicates live in one module (`repository/subject_queue.py`) because the home screen's counters
  read the same ones, so the number a card promises is the number the list it opens reports;
  `PATCH /api/v1/taxonomy/tags/{tag_id}` with `null` registers the term in
  `domain_subject_exclusions`, the half `worker_macro_category` obeys, so the verdict is not
  overwritten every time the label set changes. A row whose tag sits in a drawer cannot be
  excluded from the same screen: `POST /api/v1/taxonomy/tags/subject-exclusions` refuses it and
  answers the blocked terms with the drawer in the way, and
  `POST /api/v1/taxonomy/tags/subject-exclusions/preview` computes the same plan the write
  consumes.

- **A category expands into its descriptions** (issue #82): each card of `/assuntos/categorias`
  opens on two tabs — `Descrições`, paged ten at a time through the same
  `GET /api/v1/documents?macro_category_id=` the list screen already used, and `Editar` — and a
  row opens a read-only preview with Escape, backdrop and focus restore. The open category, its
  page and the previewed description live in the URL, so the back button closes the panel and a
  colleague can be sent the exact view. A gate drives both routes the screen uses and fails when
  the card's badge and the list's `total` stop agreeing.

- **The stopword purge keeps a ledger and an undo** (issue #36): the purge deleted the tag rows
  and let the links cascade, and nothing restored them.
  `POST /api/v1/taxonomy/tags/stopwords/purge/preview` is the plan alone, computed by the single
  `plan_stopword_purge` the write consumes; the purge snapshots every tag in
  `archive_stopword_purge_log` before the delete — the row, its document ids and the spellings
  that pointed at it, because `domain_synonyms.canonical_tag_id` is `ON DELETE CASCADE`, the same
  defect the merge fixed with `repoint_synonyms` — and
  `DELETE /api/v1/taxonomy/tags/stopwords/purge-log/{purge_id}` puts all three back. The undo
  deliberately does not lift the ban: the term is still a stopword, and the next purge lists the
  restored tag again.

- **The NER veto bans, and its purge keeps a ledger** (issue #94):
  `POST /api/v1/taxonomy/entities/ner-exclusions` recorded the exclusion **and** deleted every
  entity already extracted from that spelling, while the `DELETE` on the same path removed only
  the exclusion rows — a destructive write wearing a reversible toggle, with no preview and no
  ledger. The `POST` now bans only and deletes nothing; `.../purge/preview` lists the entities
  that would die, computed by the single `plan_ner_purge` the write consumes; `.../purge` writes
  `archive_ner_purge_log` — one row per entity, with its row snapshot, its documents and its
  spellings — before deleting; and `GET .../purge-log` with `DELETE .../purge-log/{id}` are the
  trail and the undo, which restores the row, its links and its spellings without lifting the
  veto. The conflict ledger gains `synonym_names`, so both undos restore the same things. **This
  changes the answer**: `NerExclusionBanResponse` replaces `entities_deleted` with `created`, and
  the deletion moved to the purge routes.

- **The scrape takes a batch and has a real CLI** (issue #47): `get_from_queue` returned the whole
  queue and `__main__` took no arguments, so a scrape was all-or-nothing.
  `get_from_queue(..., limit=None)` and `count_pending(...)` both read one
  `pending_conditions(...)` predicate, so the number a run reports cannot describe a queue the run
  did not touch, and the ordering (`NULLS FIRST`, `last_scraped_at` stamped on done as well as on
  failure) is what makes a bounded run resumable without starvation. `__main__` becomes
  `discover`, `scrape` and `run` — the verbs are the two ports, not one site's vocabulary — with
  `--limit`, `--pages`, `--audit-ttl-days`, `--force-retry-fatal`, `--ignore-sliding-window` and
  the three `IngestionRunnerConfig` windows, which the CLI now passes instead of letting every run
  fall back to the dataclass default. `--origin` resolves the origin through `get_adapters(code)`,
  where an explicit code wins over `ACERVO_SOURCE`.

- **The transform can be bounded per run** (issue #48):
  `next_batch(force=False, limit=None, after=None)` and `count_pending(...)` share
  `_with_pending(...)`, so the batch and the number the run reports cannot describe different
  sets. The limit is applied to the statement the CDC join already filtered, not inside the join,
  because a row the join excluded would never reach the hash comparison; the order is
  `description_id`, and `--after` is the keyset cursor. The CDC advances a bounded run by itself —
  whatever it wrote stops matching — but a `--force` re-parse bypasses the comparison and would
  re-read the same window on every run, which is the operation the bound exists for: a forced run
  bounded by `--limit` prints the cursor it stopped at, and the line appears only under
  `--force --limit`, because under the CDC a cursor would skip pending rows instead of advancing
  past processed ones. The pipeline's CLI gained `--limit`, `--after` and `--origin`.

- **`db:init` and `db:recreate` create and recreate the database from the host** (issue #81):
  `docker compose up -d` cannot recover a database dropped from a volume that already exists,
  because `POSTGRES_DB` is honoured when the volume is *initialised*. `bun run db:init` brings the
  container up, creates `DB_NAME` when it is missing and applies the schema, and repeating it
  changes nothing. `python -m scrinalia.core.database_cli create` is idempotent, reading host,
  port, credentials and the name from the same settings the API and Alembic read; `recreate` has
  no undo, so it prints what would die — size, Alembic revision, open sessions — and drops only
  when the database name is typed back at the prompt (`--yes` is the unattended form). `recreate`
  is database-scoped on purpose: it is the alternative to `docker compose down -v`, which destroys
  every sibling database in the volume.

- **The thumbnail worker runs against a local S3-compatible endpoint** (issue #33): the worker
  uploaded into a bucket that had to exist, and an endpoint does not always say "this bucket does
  not exist" — SeaweedFS answers `AccessDenied` to a `PutObject` into a bucket that was never
  created, so the per-document loop recorded 97 failures that read as a credential problem and
  stamped the whole backlog `thumbnail_failed`. The destination is now confirmed **once, before
  the first document**, and `S3_AUTO_CREATE_BUCKET` (off by default — object storage is
  infrastructure the operator brings) lets the worker create it; with the flag off the run is
  refused once, with the bucket and the `aws s3 mb` command named, and `GET /api/v1/system/health`
  reports the same distinction and never creates anything, because a probe that provisions is a
  write hiding in a read. The runner's `--batch` was accepted by every worker name and silently
  discarded by the ones without `db_batch_size`, so a run that asked for a small batch swept the
  whole queue: `--limit` caps the units of one run, honored by the workers that declare it
  (`thumbnail` today) and refused by the others, and a dropped flag is logged instead of ignored.
  `scrinalia.metadata.load_all_models` is now the one definition of the model packages, so a CLI
  run writes its own `archive_worker_runs` row — the ledger's foreign key into `auth_users` had
  made the CLI's insert fail silently while the panel's runs succeeded.

- **The similarity tab bans the marked tags**: the selection bar only offered the merge, so twenty
  spellings that all mean the same thing to ban were twenty trips to the Stopwords tab. The bar
  gains the axis and the button — the axis is chosen before the click because a word has exactly
  one scope, and the NER veto is not the subject veto — and the report names what was written and
  what banning does not do: the tags stay in the collection, and the step that removes them is the
  purge, in the Stopwords tab and behind its preview. The marks are not cleared, unlike after a
  merge, because this write took no row away and the merge it was made for is still possible.

### Changed

- **The tag axis is the subject axis** (ADR 0013, issues #83, #84). A tag is a subject or it is
  not one: `archive_tag_facets` held a third state — a producer or a place — and nothing consumed
  it (0 rows in the reference collection and 1 in the legacy one, its `value` written and read by
  no select), so the partition becomes **drawer | not-a-subject | pending**. What a place, a
  producer or a person *is* reaches the description through the entity axis (`LOC`/`PER`/`ORG`,
  754 links in the reference collection), a type the search facet and the public projection both
  read. Confirming a term as *not a subject* now **also bans its spelling at `TAG` scope**, so the
  next ingestion does not recreate it — measured, 113 of the 139 excluded terms match an existing
  tag and only 26 were banned, so the queue kept refilling. The ban deletes nothing and the purge
  stays a deliberate act behind its preview and ledger; the NER is untouched, because it reads
  document columns and its blacklist is `ENTITY`/`ALL` ∪ `DomainNerExclusion`, so a `TAG` ban
  never blinds it. `ensure_tag_ban` widens (`ENTITY` → `ALL`) and never narrows, because
  `save_stopwords` moves the scope on conflict and would have un-vetoed the extraction axis in
  silence. `domain_stopwords` gains `source` (backfilled by evidence: 83 `CONFLICT`, 5 `HUMAN` in
  the reference collection) and `domain_subject_exclusions` gains `ban_created`, so the undo lifts
  only the ban the exclusion planted; the Stopwords tab and its purge preview show each ban's
  origin.

### Removed

- **`archive_tag_facets` is dropped and its two routes are gone** (ADR 0013): a tag is a drawer or
  not-a-subject, and the third destination the table tried to persist — producer, place, person —
  already exists on the entity axis. `PUT` and
  `DELETE /api/v1/taxonomy/tags/{tag_id}/facets/{facet_type}` are removed, the `FACET` row leaves
  the *Classificar* state table and the row's `Decidir` column keeps only the category select.
  This is a **breaking** removal for any client that reached the facet routes: the table had been
  given a writer, but its `value` was read by no select beyond the state chip it fed.

### Fixed

- **The collection list can leave its first page** (issue #67): `/acervo/lista` folded the changes
  into the search and then wrote `offset: 0` after the spread, so *Próxima* built
  `{ …, offset: 25, offset: 0 }` and reloaded page 1 forever, while a hand-typed `?offset=25`
  worked — a client-side defect with `tsc`, ESLint and the Vite build all green.
  `offset: changes.offset` serves both intents: a filter sends no page and lands on the first, a
  page button keeps the page it just set. The same fold in `DeletionsRoute`, `SystemRunsRoute` and
  `DiagnosticsRoute` was normalized in the same change, and a gate fails on the next object that
  spreads its changes and then writes a literal `offset`.

- **The tag catalogue's offset is clamped** (issue #64): a negative `offset` travelled to
  PostgreSQL as `OFFSET -1` and came back a 500 — measured through the route,
  `GET /tags/catalog?offset=-1` answered `InternalError`. The clamp lives in the service and not
  only on the query parameter, because the service is the boundary every caller goes through.

- **A batch selection belongs to the page it was made on** (issue #64): marking tags and then
  paging — or changing the state filter or the search — left the marks on rows that were no longer
  on screen, so the batch bar would have written to tags the archivist could not see; the
  selection resets with the page now. A batch that stopped halfway also did not refetch the list,
  so decisions already written still read as pending: the invalidation moved to `onSettled`. The
  rest of the review closed three more findings: the search box could rewrite the URL the back
  button had just cleaned, the header and the pagination rendered the previous filter's counts
  while `placeholderData` held the old total, and the row's select offered only the active
  categories while the catalogue lists tags in retired ones.

- **One row per normalized entity and tag name** (issue #68): `normalize_entity` had always been
  `strip().lower()` and every write path stored the normalized spelling, but the uniqueness
  `archive_entities` enforced was case-sensitive — a Title Case row and the lowercase row for the
  same name were two rows, and `get_or_create_entities`, which inserts the lowercase spelling and
  looks the existing ids up with it, could never see the first. On the reference collection that
  produced 3 523 twin groups out of 8 322 entities. The migration reconciles each group (the row
  with the most document links survives, a tie goes to the already-normalized spelling and then to
  the lowest id), moves the links and the spellings to the survivor before deleting, then
  normalizes every remaining name and creates the unique index on `lower(btrim(name))`;
  `archive_tags` carries the same index. On a `pg_dump` copy the run matched its own prediction
  exactly: 8 322 entities with 3 523 twin groups and 82 317 links became 4 799 entities with 0
  twin groups and 64 504 links. The reconciliation is irreversible, which is what the curation
  guide already states for an entity merge.

- **The entity merge survives colliding synonym keys** (issue #68):
  `POST /api/v1/taxonomy/entities/merge` answered **500** (`CardinalityViolation`) when a cluster
  carried two absorbed names that differ only in case — they collapse to one
  `(synonym_name, category)` key through `normalize_synonym`, and PostgreSQL refuses one multi-row
  `INSERT … ON CONFLICT DO UPDATE` that touches the same conflict target twice, so the merge
  aborted and nothing was absorbed. The upsert existed twice, in `EntityRepository` and
  `TagRepository`; it now has one definition, `repository/synonym_upsert.upsert_synonyms`, which
  collapses the commands by key before the insert, and both repositories delegate to it — which
  closes the tag path too, since it only escaped the defect because its vocabulary has 0
  case-collision groups today.

- **The entity ruler is imported where it is added**: `EntityRuler` was imported under
  `if TYPE_CHECKING:` and used only inside a `cast("EntityRuler", …)`, so a scanner read the
  import as dead. It is now a local import in the branch that adds a ruler — real for the `cast`,
  which needs the class because `add_pipe` is typed `PipeCallable`, and loaded only when a ruler
  is actually added, which is what the class docstring promised.

- **The URL alphabet is read from the RFC, not from a range** (issue #78): the NER text cleaner
  removed URLs with `[$-_@.&+]`, which Python reads as the range `$` to `_` — 60 characters, every
  digit, every uppercase letter and `[ \ ] ^` — and the class beside it listed `\` twice. The
  replacement is RFC 3986's alphabet written out character by character. Measured against the old
  pattern, `http://site.com:8080/a?b=1#f~x` no longer leaves `#f~x` behind, `<http://x/a>` keeps
  its closing `>` instead of losing it to the URL, and `\`/`^` stop the match rather than being
  swallowed by it.

- **The clustering texts are bound on both branches**: `get_text_to_suggest_macro_category`
  refuses an unknown `source_type` and then bound `texts_to_analyze` in an `if`/`elif` with no
  `else`; the guard made the second branch the only alternative, but nothing in the code said so
  and the return read a name a reader had to prove could not be unbound. An `else` is the same
  behaviour with the proof in the shape.

- **The logging-once guarantee is held in `lru_cache`**: `configure_logging()` kept its promise in
  a module flag whose read and write sat in one function, so a scanner could not see the value
  read on the next call — a false positive, but the shape was the wrong one.
  `lru_cache(maxsize=1)` states the same guarantee without a mutable global, the idiom
  `get_settings()` already uses, and a test pins it: a sink added before the second call must
  survive it.

- **The SPA derives its query shapes from the contract**: `DocumentSearch` carried fourteen keys
  against the route's fifteen — it had lost `is_anomaly` — and nothing failed, because
  `CollectionRoute.toRequest` spreads a wider type into it: the extra key survives the return
  type, openapi-fetch sends it, and the screen filters through a field its own type denies. What
  that hides is silent in the worst direction — measured against the reference collection,
  `?is_anomaly=true` answers 28 and `?is_anomaly=false` 73, while a misspelled `?is_anomalyy=true`
  answers 101 with HTTP 200 and no warning, since an unknown query parameter is ignored and not
  refused. All nineteen query shapes now derive from the route they call, and a gate fails on the
  next shape typed out by hand.

- **The first-run plate follows the sign-in card**: the setup form still typed the tagline under
  the lockup and carried its own padding, which the sign-in card had already replaced with the
  larger lockup and a padded body. The two are the same plate, and the first screen of an
  installation is not the place to keep the older one.

### Security

- **The API enforces the temporary password** (issue #79): the sign-in section described the
  `must_change_password` refusal as the screen's promise while the guard read nothing, so a script
  holding the password the CLI printed kept the account's whole role. The API now refuses every
  operation but the change with `403` and `error_code: "PasswordChangeRequiredException"`
  (`code: "PASSWORD_CHANGE_REQUIRED"`), while `GET /auth/me` and `POST /auth/logout` still answer
  200; the same inbox answers 200 after `POST /auth/password`.

## [1.1.0] - 2026-10-10

### Added

- **First-run setup, without an open door** (ADR 0011): `GET /api/v1/setup/status` and
  `POST /api/v1/setup/admin` create the first `ADMIN` once, in a single transaction under
  `LOCK TABLE auth_users IN EXCLUSIVE MODE`, and answer 409 for ever after. The SPA draws the setup
  form while the installation has no account, accepting only a positive `needs_setup`, so an error
  can never open the form that creates an administrator. The password is the one the person chose,
  the role is not a request field, and the account does not carry `must_change_password`.
- **Password recovery has a front door**: the sign-in screen says what the path is — ask an
  administrator, who resets it on *Configurações › Usuários*; the reset ends every session of the
  account and lifts a lockout; and the host's `identity` CLI is the last resort when no administrator
  can get in. The accounts screen resets a password from the account's own row and warns, before the
  click, that resetting your own account signs you out.
- **The worker settings are a screen of their own** (`/configuracoes/workers`, issue #53): the
  persisted override of each worker, its revision history and the engine/preset choice, behind
  `GET /api/v1/system/workers/settings`. `/sistema/workers` keeps the machine — the queues, the
  pending and failed counters, and *Rodar agora* — and shows the effective configuration **read
  only**. The precedence is unchanged: explicit argument > persisted row > signature default.
- **`/configuracoes` is a card landing** (issue #22): the screens nobody opens in the middle of
  cataloguing — the arrangement plan, the catalogues, the worker surfaces, the run ledger, the
  diagnostics and the accounts — are cards on three tabs, and the menu goes from 23 entries to 16.
  `lib/settings.ts` is the single definition the page and the menu entry both read.
- **A generated contract that declares the system**: `info.title` is `Scrinalia API` and
  `info.version` is the installed distribution's version, instead of the framework default
  (`Litestar API`, `1.0.0`) that no version bump moved. A gate
  (`testing/unit/api/test_openapi_metadata.py`) fails when the contract, the distribution and
  `pyproject.toml` disagree.
- **The curator's visual identity**: the palette and the logomark in the rail, the header rule and
  the plates before a session, and the installation's version alone at the foot of every page —
  including the three screens that come before a session.
- **The shell is one window tall**: only the content column scrolls, the header is sticky, the menu
  folds into one open section plus the one you are standing in, and it collapses to an icon rail.
- **A constitutional `AGENTS.md`**: eight general principles with the rationale and the incident that
  produced each, and the topic-specific rules in fourteen rule files the session loads on demand.
  Its size, its footer and its rule-file index are held by
  `testing/unit/docs/test_agents_constitution.py`.
- **The documentation site is published by CI** (ADR 0012): a push to `main` uploads the strictly
  built site as the Pages artifact and deploys exactly that artifact, in the system's own identity —
  the curator's palette, the mark and the favicon the SPA serves, and PT Serif self-hosted.

### Changed

- **One name per screen and one verb per action**: `lib/screens.ts` holds the label the menu, the
  settings card and the page's own `<h1>` all read, and `lib/copy.ts` holds the action catalogue, so
  the three cannot disagree. The subject vocabulary follows the contract — `gaveta` became
  `Categoria` and `cluster` became `agrupamento` — and `apagar`, `unificar`, `rung`, `apply`,
  `dry-run` and `undo` are retired, held out by a gate over every string that can reach a screen.
- **One width for every screen**: the per-screen caps had drifted — `max-w-5xl` on most,
  `max-w-4xl` on five, `max-w-6xl` on one — so two screens side by side stopped growing at different
  points. The column has no maximum now, and what keeps a cap is the content's own measure.
- **`TODO.md` retired** into the issues, the guides and the milestones: the roadmap page was a second
  list of what is left, and it drifted from the one the work is tracked in.

### Fixed

- **The attribution now reaches the screens before a session.** `AttributionFooter` returned before
  the shell existed, so the four §7(b) elements — and the version — were invisible to anyone without
  an account, which the component's own docstring already called wrong.
- **The rail no longer scrolls the menu out of view**: `min-h-full` made the rail as tall as the
  *page*, so on a long screen the whole menu left the viewport and the nav's `overflow-y-auto` never
  engaged. Measured at 1440x900 at the foot of a long screen: a blank rail column and no menu.
- **A retired word inside a template literal or a JSX node the formatter wrapped was invisible** to
  the copy pass *and* to the first version of its gate. The extractor reads both, and its own tests
  run on synthetic input so they cannot pin the copy of the day.

### Security

- **The first-run route is atomic, not merely guarded.** Measured against PostgreSQL 15:
  `INSERT … SELECT … WHERE NOT EXISTS` lets both concurrent transactions insert, because `NOT EXISTS`
  is a predicate over a snapshot and not a lock. The table lock is what makes the second call wait,
  insert nothing and answer 409 — and the predicate is that the table is **empty**, so deactivating
  an account cannot reopen the door.
- **CodeQL scans the workflows** as well as the code, and every action stays pinned to a resolved
  commit.

## [1.0.0] - 2026-10-08

### Added

- **The three-layer pipeline**: ingestion (scraping queue) → staging (typed ISAD(G) columns) →
  archive (the enriched description), with a content-addressed change key so a re-parse reaches the
  archive and an unchanged record does not.
- **Nine AI workers** with a single runner: `transfer`, `cleaning`, `ner`, `typology`, `thumbnail`,
  `conflict-judge`, `macro-category`, `quality-validator`, `embedding`. Each stamps a versioned key
  in a JSONB `execution_log`, so a worker is idempotent and a text change puts a record back in the
  queue.
- **Human-in-the-loop governance**: `HUMAN_APPROVED` blocks AI rewrites, a review queue holds
  tag × entity collisions, and every human edit records its before/after in a revision ledger.
- **Curation API and UI**: 95 paths / 112 operations, and 24 screens covering the collection, the
  arrangement, the subject and entity vocabularies, quality, the operations panel and the accounts.
- **Lexical and semantic search** with facets: an accent-insensitive generated `search_vector` with
  GIN indexes, and pgvector embeddings with an HNSW cosine index.
- **A public diffusion surface** (`/api/v1/public/*`) with a field-by-field projection and an exact
  partition test, gated on `is_published` and answering 404 — never 403 — for an unpublished record.
- **Authentication and authorization** (ADR 0009): first-party session cookie with only the SHA-256
  of the token in the database, argon2id passwords, three roles, and **every operation declaring its
  permission** with a partition test that fails when one is left unclassified.
- **Account administration**: `/api/v1/users` and the `Configurações › Usuários` screen — create,
  edit, deactivate, reset a password, and list or revoke the sessions of an account.
- **Local observability** (ADR 0005): `/health/live` and `/health/ready` for an orchestrator, a
  request id on every answer, and `/api/v1/system/failures` grouping both failure ledgers by a root
  cause computed in a generated column.
- **A generated, committed API contract**: `bun run contract` dumps the OpenAPI document and
  regenerates the TypeScript client; CI fails when either is stale.
- **The documentation an installer, an operator and an archivist read** (ADR 0010): four guides in
  English and Portuguese, plus the index and the ADRs, held to the code by two rules — coverage is a
  gate (a worker, a setting, a screen, a table or an ADR missing from the page that owns it fails the
  suite) and freshness is a report whose verdict lands in a triage ledger.
- **A release flow that produces verifiable artifacts**: the `Release` workflow validates the
  version, builds the curator SPA, generates the Python SBOM and attests the build provenance before
  creating the tag and the release.

### Changed

- **The language is code; the collection vocabulary is data** (ADR 0008): the Portuguese profile
  lives in `core/language`, and the arrangement names and collection terms are rows the archivist
  edits from a screen. An installation declares its own origin and vocabulary instead of inheriting
  the reference collection.
- **The AI text composition moved into SQL**: one expression feeds the embedding text, its MD5 stamp,
  NER and the typology, so the four cannot disagree.
- **Object storage is not shipped.** `docker compose up -d` starts PostgreSQL only; the project needs
  an S3-compatible endpoint (`S3_ENDPOINT_URL`) and does not care which product serves it, so the
  storage is infrastructure the operator brings rather than a service this repository runs.

### Fixed

- A description whose title was a placeholder (`não informado`) was **dropped** by staging, because
  cleaning turned the required title into `None`. It now falls back to `SEM TÍTULO`.
- Two merge defects in both vocabularies: deleting a tag before repointing its synonyms destroyed the
  spellings earlier merges had absorbed, and an undo restored the row without the links it created.
- A `Field(description=…)` on a field typed with a shared enum rewrote the enum's schema for the whole
  document, so the committed contract depended on `PYTHONHASHSEED` and CI failed at random.

### Security

- **Lockout with backoff**: failed sign-ins are counted in a column and written through their own
  committed session (the request transaction rolls back on the failure it would have counted), and
  only a *correct* password on a locked account is told the reason.
- **Per-address rate limiting** on the login route, in front of the per-account lockout.
- **Cross-origin checking** on mutating requests, allowing a same-origin `Origin` or one declared in
  `AUTH_TRUSTED_ORIGINS`, and never checking a read.
- **Known advisories in the runtime dependencies resolved** by minimal version bumps — `torch`,
  `transformers`, `sentence-transformers`, `setuptools`, `urllib3`, `pillow`, `anyio`, `multidict`,
  `soupsieve` and `fsspec` — instead of jumping every package to its latest release. The CI audit now
  reads the **runtime** export and not the development environment: an advisory in a tool that never
  reaches an installation no longer hides the ones that do.

[Unreleased]: https://github.com/CassioDalla/Scrinalia/compare/v1.2.0...HEAD
[1.2.0]: https://github.com/CassioDalla/Scrinalia/releases/tag/v1.2.0
[1.1.0]: https://github.com/CassioDalla/Scrinalia/releases/tag/v1.1.0
[1.0.0]: https://github.com/CassioDalla/Scrinalia/releases/tag/v1.0.0
