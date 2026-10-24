# Changelog

All notable changes to this project are documented here. The format is
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project follows
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

`1.0.0` was the first release; the newest one is at the top. Entries describe **behaviour**, not
commits — the history is the detail.

## [1.4.0] - 2026-10-24

### Added

- **A document-entity link says who wrote it, and a person can confirm one** (issue #135):
  `archive_document_entities` gains an `origin` (`AI`, `HUMAN` or `UNKNOWN`) and a nullable
  `created_at`. `UNKNOWN` is what the 64,504 links that predate the column carry — the database cannot
  prove which producer wrote them, and the migration does not guess. A link a person writes through
  `POST /api/v1/documents/{description_id}/entities` records `HUMAN`, and associating an entity the
  extractor already proposed is the **confirmation** the schema could not express: the link stays, its
  origin changes, and the description becomes `HUMAN_APPROVED`. The screen shows each entity's origin
  and offers `Confirmar` on the ones nobody has vouched for. The extraction inserts with
  `ON CONFLICT DO NOTHING`, so it cannot rewrite a human link, and the NER bench excludes a human link
  from the model's proposal instead of scoring the correction as its own hit.

- **The typology screen lists the descriptions the classifier refused** (issue #129):
  `GET /api/v1/typologies/refusals` returns one page of the descriptions whose best score stayed
  below the floor — one row per description, the latest refusal, nearest miss first, with the label
  the run guessed and the score it saw. The page, the count and the inbox card compose the same
  `_open_evidence()` predicate, so the total cannot drift from the rows, and a description a curator
  has already filed leaves the list even though its queue row remains. Filing from the screen is the
  dossier's own `PATCH /api/v1/documents/{id}` with a `typology_id`, which records the revision and
  marks the description `HUMAN_APPROVED`; the empty state says no refusal is open, not that the
  catalogue covers the collection.

### Changed

- **A banned spelling says how it matches, and the extraction stops losing names that contain it**
  (issue #160). `domain_stopwords` gains `match_mode` (`TOKEN`/`EXACT`) and a
  `PATCH /api/v1/taxonomy/tags/stopwords` route changes it without re-banning, which would overwrite
  the origin the conflict or the "não é assunto" screen recorded. Every `domain_ner_exclusions` entry
  now matches the **exact spelling**: the token rule over the union of both catalogues was rejecting
  115 entity names over 1,288 links in 1,170 documents — `casa da memória` for `casa`, `Alameda
  Cabral` for `alameda`, `Caixa Econômica` for `caixa`. On the #138 set, the live measurement went
  from **P 0.909 / R 0.920 / F1 0.915** with 13 blocked gold terms to **P 0.917 / R 0.956 / F1
  0.936** with none; ORG recall 0.568 → 0.611 and the boundary cases 27 → 12. The token rule stays
  where it was written for: a `TOKEN` stopword still rejects the merged span `IPTU do Exemplo`.

### Fixed

- **The typology picker no longer proposes a plan as a Câmara petition** (issue #163). The
  `Requerimento à Câmara Municipal` stratum's pattern carried a second alternative,
  `|c[âa]mara municipal`, that matched any title naming the Câmara, including a plan whose title says
  it is *for* the Câmara. Only the qualified `requerimento … câmara` form stays, so a plan falls
  through to `Planta Arquitetônica`. Two synthetic titles pin both sides of the rule; no collection
  data enters the test.

## [1.3.0] - 2026-10-23

### Added

- **A third ranking mode: the lexical and the semantic orders fused by Reciprocal Rank Fusion**
  (issue #38): `mode=hybrid` on `GET /api/v1/documents` and on the public surface. The two rankings
  are built independently — `ts_rank` over the generated `search_vector` with the taxonomy boost, and
  the cosine similarity to the embedded term — and meet in `reciprocal_rank_fusion`
  (`domains/archive/domain/search.py`, `RRF_K = 60`), so nothing normalises a `ts_rank` against a
  cosine. The fusion reads the **window** of each arm (`RRF_DEPTH = 100`); `total` is the count of the
  union of the full-text matches with the semantic window, and not every document that has an
  embedding, which would be the whole collection. The page is the fused window first and the rest of
  the matches after it in full-text order, and `rank` follows the same split: the fusion's score
  inside the window, the relevance of the ordering that placed the document outside it. The full-text
  mode stays the default on both surfaces, so a lexical request still never loads the model.

  **Measured on the labelled set, per query stratum, through the product path** (16 queries whose gold
  is derived from the title term, on the 4,831-description collection):

  | stratum | mode | Hit@10 | Recall@10 | MRR | found in top-50 |
  | --- | --- | ---: | ---: | ---: | ---: |
  | the sentence a person types | lexical | 0.438 | 0.212 | 0.258 | 0.500 |
  | | semantic | 0.562 | 0.221 | 0.293 | 0.750 |
  | | hybrid | **0.625** | **0.358** | **0.296** | **0.812** |
  | the title term alone | lexical | 0.875 | **0.650** | **0.703** | 0.938 |
  | | semantic | 0.562 | 0.225 | 0.338 | 0.688 |
  | | hybrid | **0.938** | 0.608 | 0.679 | 0.938 |

  The fusion wins on the sentence and on the term; it is the mode that removes the choice. It is **not**
  a free win: on the term stratum it puts one more query inside the top ten and still ends 0.024 below
  the full-text ranking on MRR, because agreement demotes a confidently-ranked full-text hit when the
  semantic arm disagrees — the set is small (one query is worth 0.0625 of Hit@10) and its gold is a
  proxy, so the report prints that limit next to every number. The fusion is also not a dominance order:
  a first place plus a third beats a second place twice by 8·10⁻⁶. Latency is the full-text one plus
  about 7% (6.4 s against 5.5 s per query on the slowest stratum, which is dominated by the pre-existing
  cost of a broad term, not by the fusion).

- **A bench for the retrieval modes** (issue #38): `testing/evaluation/retrieval_modes.py` scores the
  three rankings **through the product path** — `DocumentService` and the repository, the same objects
  the route uses — where `retrieval_quality.py` embeds and ranks on its own because there the embedded
  text is the variable. It reports Hit@k, recall@k, MRR and coverage per mode and per stratum, with the
  position of the first expected description for each query, and the shared ranking arithmetic is
  defined once in `testing/evaluation/ranking_metrics.py`.

- **The operations panel opens a worker's stamp into what it actually names** (issue #137):
  `GET /api/v1/system/workers` now carries `stamp_breakdown` per worker — units the stamp attributes to
  a producer, units it leaves without a known one, units recorded as failed and units with no record at
  all — and `/sistema/workers` shows those counts on the card. It exists because one "processed" number
  used to stand for all of them, and for NER that number was 1,650 legacy values reading as success. The
  four numbers come from one aggregate, and `processed`/`failed` are derived from it, so the panel pays
  one scan where it used to pay two.



### Changed


- **The thumbnail's failure mark is `ERROR`, not the boolean `"True"`** (issue #149). `StampStatus`
  carried a third value only because the thumbnail worker wrote `"True"` into `thumbnail_failed` — a
  boolean serialised into a status vocabulary. The mark now uses `ERROR` like every other failure;
  a data-only migration renames the old rows, and the thumbnail queue and its `failed` count are
  unchanged because both read the presence of the `thumbnail_failed` key, not its value.

- **An identity-keyed stamp accepts a producer fingerprint and nothing else** (issue #137). The
  vocabulary had one type carrying both `mark` (a status) and `mark_value` (an identity), so `"DONE"` —
  a legal `StampStatus` — was a legal write into a slot that promises a producer, which is how 1,691 NER
  rows came to name no extractor while reading as a success. `IdentityStamp` has no `mark`: `mark_value`
  raises `ValueError` for any value the slot's own `fingerprint_pattern` does not accept, `mark_failed`
  is the only failure writer, and "a run happened and its producer is unknown" has the name
  `PRODUCER_UNKNOWN` instead of borrowing a status. `WorkerStamp` stays for the ledgers that really do
  hold a status or a free text: the thumbnail's failure mark, the declared parent, a curator's own
  decision.

  **A migration makes the existing rows honest without inventing a producer**
  (`a7c1e5b9d3f2_make_the_legacy_identity_stamps_read_as_unknown.py`): every `"DONE"` in an identity
  slot — the current key or a retired one — becomes `PRODUCER_UNKNOWN`, the 3,100-odd documents with no
  NER slot keep having none, and the embedding's bare text hashes are left alone, because that hash is
  a fact. Those rows were pending before the rename and are pending after it — the queue is unchanged,
  and the next run heals them by writing a real fingerprint — so the fix is attribution and reporting,
  and `testing/unit/quality/test_identity_stamp_writes.py` fails a worker that writes a status into an
  identity slot at all.

- **The semantic mode's note no longer cites a Hit@10 that belonged to another experiment.** The
  screen and the curation guide used to say the semantic ranking was measured as weak and quote
  `Hit@10 0.625` — a number produced by the excerpt experiment on the embedded text, on a
  3,608-description collection, and never a comparison with the full-text ranking. The three modes are
  now named where the archivist reads them, with the rule that decides between them and the limit of
  the evidence, and the numbers themselves live in `docs/log.md` and in the bench that produced them:
  a page that stores a number which is expected to move lies on the next run.

- **A bench for the NER extractor, at term level** (issue #113): `testing/evaluation/ner_quality.py`
  scores an extraction against a labelled set at the unit that matters — a span is right or wrong by its
  boundaries, so a document-level agreement would call an extraction perfect when one of five terms was
  found. Term-level P/R/F1 per type and overall, exact match only, with a relaxed recall that counts a
  boundary as found printed beside it and never replacing it; the misses are partitioned into four
  buckets that sum to the support — **hits, boundary, type confusion, missing** — plus spurious.

  **The gold is a correction of the stored run**, because there is no human NER gabarito in this
  collection: `ner_pairs.json` does not exist, the exclusion catalogue has three rows and the merge log
  none, while `archive_document_entities` holds 64,504 links over 4,811 documents written by the worker
  itself. `--propose` transcribes that output and writes a sheet where a curator marks what is wrong or
  missing, and the anchoring bias of pre-annotation is declared rather than hidden.

  **Two facts about the extractor came out of building it.** The engine returns `ArchiveEntityDTO` with
  only `name` and `entity_type` — **there are no offsets anywhere**, so the boundary breakdown is a
  token-containment measure that counts the defect without saying where it happened, and the issue's
  wording had to be corrected. And the collection's NER output is **unattributable in full**: 1,650
  documents carry `worker_ner_v2 = "DONE"`, 41 carry `worker_ner_v1 = "DONE"`, 3,142 carry no NER stamp
  at all, and not one carries a producer fingerprint — the legacy `"DONE"` is the stamp's default status
  and not an identity, which is why the stored mode prints the producers it finds instead of claiming a
  configuration.

- **The typology bench simulates a catalogue edit before it is written** (issue #111): a catalogue
  change is the producer identity's business — the label set is part of it since #117 — so retiring or
  adding a form re-reads the whole collection, about 2.9 hours of CPU at the measured 2.2 seconds per
  document. `--drop-typology NOME` and `--add-typology NOME` measure the edit **by name** first, and
  nothing reaches the database: the decision, the write and the read stay separate (principle VI). Names
  are all it needs, because the worker maps an answer back to an id to write it while the bench compares
  against a gabarito written in names, and the engine only echoes the label it was handed. A name the
  active catalogue does not have is refused rather than added, and the report names the candidate set it
  ran against so two runs with different catalogues cannot look identical.

  What it measured on the 111 labelled rows, at the shipping configuration:

  | catalogue | agreement | macro-F1 | misses | Fotografia F1 | Processo Administrativo F1 |
  | --- | ---: | ---: | ---: | ---: | ---: |
  | as it is | 0.775 | 0.484 | 25 | 1.00 | 0.00 |
  | without "Ofício / Memorando" | **0.856** | **0.558** | **16** | 1.00 | **0.33** |
  | + 3 forms, "Livro de Registro" | 0.378 | 0.272 | 69 | **0.18** | — |
  | + 3 forms, "Livro de Sepultamento" | 0.703 | 0.476 | 33 | 1.00 | 0.00 |

  Retiring one form the collection has **zero** of is the largest gain measured on this axis — +8.1
  points of agreement, better than any of the three label formats #112 compared — and it unbreaks a real
  form: "Processo Administrativo" goes from F1 0.000 to 0.333 because the phantom was eating all four of
  its answers. Adding the three forms the collection does have works **if the names are discriminative**:
  "Livro de Registro" collapses the axis because the photographic fonds is called "Registros
  Fotográficos" (48 answers, 40 stolen from Fotografia), while "Livro de Sepultamento" takes exactly the
  8 burial registers and leaves the covered rows alone. On this axis **the name is the taxonomy** — a
  definition documents, the name decides, because #30 keeps the definition out of the prompt.

- **The typology records the refusal it saw, instead of leaving it to be inferred** (issue #110):
  `archive_documents.typology_id` is NULL both when the classifier looked at a description and
  declined to place it and when the run never reached it, and the column cannot say which — so the
  score that justified the refusal was lost with it, which is the one number a floor decision needs.
  There is now `AnomalyType.TYPOLOGY_LOW_CONFIDENCE`, and the worker writes a row in
  `archive_ai_review_queue` per refusal carrying **the score it saw**, the label it guessed and the
  description's context.

  The issue's own Definition of Done proposed a distinct **stamp value** for the refusal. #117 broke
  that in both directions: `identity_stamp_conditions` computes pending as "the stamp is not this
  identity", so a `REFUSED:<identity>` value puts the description back in the queue on the next run
  and it is refused again forever — while adding the value to `FAILURE_STAMP_VALUES` excludes it
  permanently and a floor change would never reach it. The stamp means *this producer read it*; the
  refusal is evidence, and evidence lives in the queue, which is the shape the subject axis already
  had. It is a vocabulary addition and an additive migration (`ALTER TYPE ... ADD VALUE`, the
  `SUBJECT_LOW_CONFIDENCE` pattern, with a downgrade that keeps the value).

  `repository/typology_queue.py` owns the read the way `subject_queue.py` owns it for the tags: the
  predicate asks for the row **and** the absence of a drawer, because nothing deletes the classifier's
  evidence when a curator files the description — reading the row alone would count a description that
  already has an answer — and the count collapses a description's rows so a run repeated with `force`
  cannot inflate it. That is what lets the typology bench's `stored` mode drop its blanket caveat for a
  measured **split**: `bare`'s 5.4% abstention on the labelled set is now reportable as "how many the
  queue accounts for" against "how many no run has reached".

  **Scale, measured:** the #109 run on the real pending queue gave **0.000** abstention on the title at
  0.40 and **0.020** with the archival history, so the rows this writes are tens and not thousands. The
  real number for the 608 descriptions the old queue never sampled is what the first run after #117
  measures.

- **The quality validator has a bench, and the installation it would measure has no rule to score**
  (issue #115): `testing/evaluation/quality_validator_quality.py` grades the cleaning rules one by one
  instead of grading documents, because the validator's output is a **set of flags per document** and a
  validator that flags the right document for the wrong reason is not doing the job. For each active
  `VALIDATE`/`LLM_CHECK` rule it prints support, firings, precision, recall and F1 — the two halves are
  not derivable from one another, and **recall is why the set is human**: a review queue can only ever
  measure precision, since the documents nobody flagged are exactly the ones absent from it.

  `--pick` proposes rows by the flags the last run stored — one stratum per rule, plus the documents no
  scorable rule touched (where a miss lives) and the ones with no anomaly at all (where a false positive
  would be) — and a curator writes which rules should have fired. The rules come from the catalogue, and
  whether one fires is decided by the worker's own functions: `matched_rule_labels` and
  `llm_check_reason`, so the graded flag and the written flag are one definition, pinned by an
  integration test that runs the real worker and asks the bench what fired. A rule below five labelled
  positives is printed **não medida**, the same floor the typology bench uses.

  **Measured on 2026-10-16 against `memoriacuritibana`:** the catalogue holds **one** rule — inactive,
  `REWRITE`, named `aaaaa` — so there are **zero active `VALIDATE`/`LLM_CHECK` rules** and no flag to
  score; `--pick` and the scorer both refuse with that sentence instead of printing an empty table. What
  the validator does flag is almost entirely structural and almost entirely everything: **4,583 of 4,831
  documents (94.9%)**, of which NO_TYPOLOGY 4,455, SCOPE_ONLY_BOILERPLATE 3,163, MISSING_DATE 2,160,
  REPEATED_TITLE 2,079, NO_ENTITIES 2, ALL_CAPS_TITLE 1 — and `RULE_MATCH`/`LLM_SUSPECT`: **zero**. The
  bench therefore lands measure-*able*, with its own evidence coming from an integration test against a
  fixture rule, and the axis stays unmeasured until the installation writes one.

  The load-bearing definitions moved into one place on the way: `matched_rule_labels`,
  `llm_check_reason` and `rule_flag_label` are now the worker's, read by the bench, and the
  `CODE:payload` format of `anomaly_reasons` is a named constant in `models/enums.py` instead of a
  literal in the writer, the facet and now the scorer.
- **The conflict judge has a bench, and on the ledger that exists it does not beat a constant**
  (issue #114): `testing/evaluation/conflict_judge_quality.py` scores the tag x entity judge against
  the resolutions a **human** took, read from `archive_conflict_resolution_log` at run time — so it
  needs no labelled file, because the gabarito is already in the database and a human verdict is
  durable intent no later suggestion run overwrites. Four rules make the read a measurement rather
  than the model scoring itself: `source='JUDGE'` rows are counted and kept **out** of the score
  (scoring the judge against its own auto-resolutions measures nothing), an `undone_at` decision is
  out (the institution already withdrew the answer), the pairs come from the ledger's **own
  snapshots** and never from the live catalogues the resolution deleted, and a failed call is **not a
  verdict** — the decision schema has no error state, so a transport failure returns `winner="TAG"`
  with `confidence=0.0`, and those rows are counted as engine failures and printed instead of being
  read as a judge that answers `TAG` to everything. `FAILURE_REASON_PREFIX` is now defined once, in
  the engine that writes it, with a test on each side pinning the pair.

  Two columns sit next to the agreement. The **constant baseline** is what a judge answering only the
  most frequent verdict would score, and `Δ` is agreement minus it: on a ledger skewed by a curator
  working through a backlog, agreement alone flatters. The **auto-resolve split** applies the worker's
  own `auto_resolve_threshold` (read from its signature) to the verdicts.

  **Measured on 2026-10-16 against `memoriacuritibana`, on the ledger's 49 human resolutions, CPU:**

  | configuration | scored | agreement | constant | Δ | auto-resolved | engine failures | s/pair |
  | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
  | `ollama_judge:gemma_4b_local` (the default) | 49 | 0.918 | ENTITY 1.000 | **−0.082** | 49 | 0 | 5.13 |
  | `ollama_judge:granite_local` | 0 | — | — | — | 0 | **49** | 1.26 |

  The four misses are all the same mistake in the same direction — `ENTITY→TAG`, each at confidence
  0.900 — and the agreement by entity type is LOC 0.976 (42), PER 0.800 (5), ORG **0.000** (2). Every
  one of the 49 was confident enough to be auto-resolved, so on this ledger the judge's errors reach
  the archive without a person seeing them. The gabarito is **single-class** (ENTITY 49/49), which is
  a property of the ledger and not of the judge: a curator resolving a run of abbreviated street
  spellings against their canonical entities only ever decides ENTITY, so this set cannot measure the
  TAG direction at all, and the bench prints that instead of a flattering number. The second line is
  the other kind of finding: **`granite4.1:3b` fails every single call** (`500 Server Error`, the
  llama runner crashing on this Ollama build), so the preset the registry declares cannot judge
  anything — separated from a verdict by the failure rule above rather than scored as 49 `TAG`s.
- **The classification axis can run a second model, and the registry is where it is declared**
  (issue #116): `xlm_roberta_local` (`joeddav/xlm-roberta-large-xnli`) joins `cpu_local` and
  `gpu_cloud` in `engines/classification/registry.py`. The engine of that axis is a
  `zero-shot-classification` pipeline whose model is a parameter, so a second model is a **preset**
  and not an engine — and because the registry is the axis's single definition of what can be run,
  the option reaches both of its workers, the typology classifier and the subject categoriser, not
  only the bench that needed it. It exists because the subject bench compares two models and, since
  this change, the bench names no model of its own.

- **The typology bench prices a configuration on the collection's own mix, and the price says no**
  (issue #109): `--collection` samples the **pending queue** — through the worker's own
  `pending_conditions`, with its size compared against `count_pending`, the number the panel shows —
  and prints seconds per document, the projection for that queue, the abstention rate and the label
  distribution, per configuration and per stratum. It writes nothing and scores nothing: these rows
  have no gabarito, and a wrong label there is invisible. Three rules make its number a number about
  the collection: it does **not** deduplicate by text (the picker does, and the worker pays for a
  repeated title every time it appears), it allocates the sample proportionally across the picker's
  strata **with no floor** (a floor of one row per stratum would give 6% of a 100-row sample to the
  forms that are 0.85% of the collection — the ones with the longest texts), and it measures every
  configuration on the documents pending under **all** of them, so the comparison isolates the
  columns from the collection.

  **Measured on 2026-10-16 against `memoriacuritibana`, 100 documents of the 4.205 pending, CPU,
  10 active typologies:**

  | configuration | queue | s/doc | projection (1 worker) | abstention | largest drawer |
  | --- | ---: | ---: | ---: | ---: | --- |
  | `original_title` @ 0.40 (the shipping one) | 4,205 | 2.20 | 2.6 h | 0.0% | Fotografia 69% |
  | `original_title,admin_bio_history` @ 0.40 | 4,205 | 5.76 | 6.7 h | 2.0% | Fotografia 66% |

  The ratio is 2.62x and not the 3.1x of the balanced sample, and the cost sits in the photographic
  fonds (6.33 s/doc at 416 characters against 4.57 s/doc at 332 for the plans), which is 69.2% of the
  queue; the queue is 69.2% Fotografia, 29.5% Planta and **0.4% descriptions no typology covers**,
  the control bucket the gabarito weighs at 9.8%. Decomposing the numbers #69 published (±1 row from
  rounding): on the 111 scored rows, the shipping configuration gets 83 of the 100 rows the
  catalogue covers right, and so does the archival-history one, which also abstains on 9 more of
  them — the whole 7-point gain is the control rows it stops mislabelling. **The default is not
  changed.** The price would be paid on 100% of the queue to fix the 0.4% the catalogue does not
  cover, and what that 0.4% needs is a recorded abstention (issue #110) and a catalogue decision
  (issue #111), not a longer input. The configuration stays reachable through the panel's options
  box, and a re-measurement is one command.

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

### Changed

- **The typology picker's strata are the catalogue's mirror** (issue #111): `run_pick` refuses to
  propose by a name the active catalogue does not carry, so the strata had to move with the catalogue —
  the forms that retired left the list, the forms the collection gained entered it **before** the control
  bucket (the bucket's pattern matched the very titles they now own), and the bucket keeps only what the
  catalogue deliberately leaves out.

  Two consequences the round measured, and both are reported rather than papered over. **The control
  bucket has no material left in this collection**: with registers, petitions and printed publications
  covered, `NENHUMA` proposes 1 of 1 candidate, so keeping a false-positive control needs the curator to
  name what stays out of scope. And **31 descriptions match no stratum at all**, overwhelmingly
  photographic records whose titles describe the subject and not the medium ("Concerto na Pedreira do
  Pilarzinho", "Obras de construção do Palácio 29 de Março") — a gap in `PHOTO_STRATUM`'s pattern, 0.6%
  of the collection, and not a form the catalogue lacks.

- **The typology bench compares label formats, and no proposition beats the bare name** (issue #112):
  `--formats bare sentence trata_de`, all three in one invocation, applied to the same signed labelled
  set. The format is a **separate** dimension and not a fifth field of `--config`, because
  `producer_identity` does not sign it today — folding it into the configuration string would make the
  bench name a producer the worker cannot be told to run. The templates are the bench's instrument and
  not a product string: the product's home for a proposition is a field per catalogue row
  (`archive_macro_categories.classifier_label`, composed by `domain.vocabulary.classifier_labels`),
  and a wording hand-written for one catalogue's typologies would be collection data inside versioned
  code. `sentence` is gender-invariant by construction (`um documento do tipo …`) because Portuguese
  forces the article to agree with the typology — "uma fotografia" against "um relatório técnico" — the
  catalogue stores no gender, and no code template can be right for a mixed catalogue.

  The candidate list and the way back are **one** dictionary, `{label: catalogue name}`, which is what
  the engine's echo requires: it answers with the label it was handed, so a bench that skipped the
  translation would compare a proposition against a gabarito written in catalogue names and score every
  row of every formatted run as a miss — a `0.000` that reads like a finding. Two unit tests and an
  integration test pin each side of that pair.

  **Measured on 2026-10-17 against `memoriacuritibana`, 111 of the 112 labelled rows, CPU,
  `deberta_typology:cpu_local:original_title:0.40`:**

  | format | agreement | macro-F1 | abstention | Planta Arquitetônica recall | answers "Ofício / Memorando" | `NENHUMA` → "Ofício / Memorando" |
  | --- | ---: | ---: | ---: | ---: | ---: | ---: |
  | `bare` (the shipping one) | **0.775** | **0.484** | **0.054** | **0.956** | 18 | 8 |
  | `trata_de` | 0.784 | 0.478 | 0.072 | 0.978 | 12 | 8 |
  | `sentence` | 0.604 | 0.414 | 0.297 | **0.511** | 12 | 8 |

  **The dustbin is not a wording problem.** "Ofício / Memorando" swallows exactly 8 of the 11
  descriptions no typology covers, under all three formats — the count does not move. A label shape
  cannot make an uncovered form covered, and #112's hypothesis ("either a sentence fixes the dustbin,
  or it reproduces the collapse #30 measured") is answered by neither branch: the format changes how
  many *other* rows the drawer also takes. `sentence` is decisively worse — agreement down 0.171,
  abstention up 5.5×, and the plans collapse (recall 0.956 → 0.511, 20 of them abstaining), which is
  #30's lost entailment reappearing exactly where `classifier_labels` warns it does. `trata_de` ties
  `bare` within one row of 111 and is not a reason to change a documented decision.

  **`bare` wins, so the default is not changed and nothing moves in the worker.** #30's decision gets
  the measurement it never had. Adopting a proposition would have cost a full re-queue under the
  identity #117 just made meaningful, for no measurable gain.

- **The typology queue is gated on the stamp, and the stamp signs the catalogue** (issue #117): the
  predicate of `worker_typology` no longer reads `typology_id IS NULL`. That clause was ANDed into the
  queue and made the producer identity inert: a description that already carried a typology never went
  back to the classifier, so **nothing** the identity signs — the floor, the model, the columns or the
  label set — reached the documents the last run had classified. Measured on 2026-10-17 against
  `memoriacuritibana`, `count_pending` answered **4,205** under floor 0.40, floor 0.90, two column sets
  and two presets: 4,813 ai-writable descriptions minus the 608 that carried a typology, exactly. The
  clause also duplicated the two gates that remain — a human verdict is `ai_writable_documents()`
  (principle VII) and "do not redo the work" is the stamp.

  `producer_identity` now composes the active label set through `label_set_fingerprint`, the same hash
  the subject axis signs; without it, adding, renaming or retiring a typology changed no stamp at all.
  And a run that **declines** a description clears the answer it found: with the stamp as the only
  gate, a refusal that left the old label standing would make raising the floor re-run the collection
  and change no label — a no-op on exactly the documents the change exists to reach. The score it saw
  is still not recorded; that is #110.

  **What it costs, declared:** the same four configurations answer **4,813** after the change — the
  whole ai-writable collection, once. From the first run onward the identity separates them, and only
  a catalogue, model, column or floor change moves the number again. Of the 608 re-read, **473 carry a
  typology with no stamp at all**: none is `HUMAN_APPROVED`, so the governance gate does not cover
  them, but they may be a curator's work from before that status existed.

- **The subject bench takes its models from the engine registry** (issue #116): the two hardcoded
  adapters and the `MODELS` dictionary inside `testing/evaluation/macro_category_quality.py` are gone.
  `--config ENGINE[:PRESET]` resolves through `engines.classification.registry` — the same registry
  both workers of the axis read — the default is the configuration the macro-category worker declares
  in its own signature, and `--device` is the only engine parameter the bench overrides. A model the
  registry does not declare is not reachable from here: adding one is a registry entry, which is what
  makes a configuration the bench measures one the worker can also be told to run.

  The change is a refactor and not a new measurement, and it is measured as one: on the first 8
  labelled tags, mDeBERTa's 9 (label format, arrangement) combinations reproduce the pre-refactor
  report field by field — accuracy, distribution, largest share, both mean confidences and the full
  per-tag miss list — with **zero differences**. The second model, `xlm-roberta-large-xnli`, is
  verified at the code level only (the registry resolves to the same model string and device the
  deleted adapter hardcoded, and `DebertaEngine`'s pipeline defaults are the ones it passed): the
  model is not in this machine's Hugging Face cache and the cache is read-only, so it was not
  executed here.

### Fixed


- **An `LLM_CHECK` rule can no longer be saved with an engine the registry does not have** (issue
  #124). The rule's engine and preset were free text all the way down to a `String(50)` column, the
  form's only hint was the placeholder `ex.: ollama` — not a registered engine — and nothing validated
  the pair: the registry's `ValueError` escaped `worker_quality_validator.execute`, so the run was
  recorded `FAILED` and the validator validated nothing while the rule stayed active. The write now
  validates the pair through the registry's own `describe_config` and refuses it as a
  `DomainException` (`422`, with the sentence naming the options), whether or not the rule kind
  carries an engine; an empty engine keeps meaning `ollama_title_check`. The form's two fields became
  selects fed by `GET /api/v1/quality/cleaning-rules/engines` — the title-quality axis's catalogue,
  the same names `get_engine` reads, shared with the operations panel through one definition. A rule
  written before the door existed degrades instead of failing the run: the validator logs the reason,
  still runs the deterministic stage, and its producer identity becomes the "no model" one, so the
  queue and the panel's counter describe the run that actually happened.

- **The conflict judge no longer writes a transport failure as a verdict** (issue #122).
  `EntityTagDecisionSchema` has no "I could not answer" state, so `OllamaJudgeEngine.decide_conflict`
  turned every failed call into `winner="TAG"` with confidence `0.0` and a `Falha: ...` reason — a
  decision the model never took, written into `archive_ai_review_queue` and shown by the curation
  inbox, marked only by a prefix inside a free-text `reason`. The engine now raises
  `EngineExecutionError`, the worker writes no `llm_decision` for that pair (it is still pending, and
  the next run asks again), and the panel's "already judged" counter does not count it. The type is
  what tells a failure from an opinion, so the bench's `FAILURE_REASON_PREFIX` string matching is
  deleted: a failure is a `Failed`, never a `Judged`.

- **A search filtered the term after joining the link tables, so a selective term took 18 seconds**
  (issue #140). The full-text arm reached the page, the count and every facet as an `OR` of correlated
  `EXISTS`, which the planner cannot answer with an index: the predicate was re-evaluated once per row
  of whatever it was joined to — 64,504 entity links to find 12 descriptions — and the `OR` alone kept
  it away from the generated `search_vector` GIN index. The arm is now a **set of description ids**
  (the union of the text match, the tag match and the entity match) that the page, the count and every
  facet filter on, and the taxonomy boost is membership in that set instead of a correlated `EXISTS` per
  candidate row. The fused mode's candidate clause is one union of two id sets rather than an `OR` of
  the two, which the planner *also* could not turn into a semi-join. The count no longer computes the
  rank expression it does not read.

  Measured on the live collection, 18 query/mode/filter cases, **results identical** — same ids, same
  order, same ranks to ten decimals, same `total`, same five facet counts: a selective term went from
  **17.5 s to 0.21 s** (83×), a broad one from 6.4 s to 0.41 s, and the hybrid mode from 18.0 s to
  0.31 s (58×). The semantic mode is unchanged at 0.15 s. One case got slower: a term combined with a
  highly selective facet filter, 0.19 s → 0.29 s, because the term set is now built before the filter
  is applied — the cost of the term is the floor for any query that has one. A structural test
  (`testing/integration/archive/repository/test_search_predicate_shape.py`) fails if a facet is built
  over a link join without the document predicate first; it was verified to fail against the code
  before the fix.

### Changed

- **A search filters the documents before it joins the link tables** (issue #140): the term is one set
  of `description_id`s, computed once per query, and the page, the count and the facets all read it.
  Nothing a caller sends or receives changes.

### Removed

- **The `granite_local` preset is retired, in both Ollama axes** (issue #122): the model it named,
  `granite4.1:3b`, does not run on the Ollama the install guide documents. Measured on 2026-10-18, on
  Ollama 0.24.0: it terminates the llama runner with `signal arrived during cgo execution` and
  answers `500` to every prompt, while `gemma4:e4b` answers normally on the same server. The name
  leaves `PRESETS` — the panel stops offering it and `GET /api/v1/system/health` stops requiring the
  model — but the record stays in `RETIRED_PRESETS`: writing it is refused with the reason and with
  `gemma_4b_local` as what to use instead, and a row or `LLM_CHECK` rule written before the
  retirement resolves to `gemma_4b_local` with the reason on the screen, so a stale row cannot take
  the operations panel down.

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

[Unreleased]: https://github.com/CassioDalla/Scrinalia/compare/v1.4.0...HEAD
[1.4.0]: https://github.com/CassioDalla/Scrinalia/releases/tag/v1.4.0
[1.3.0]: https://github.com/CassioDalla/Scrinalia/releases/tag/v1.3.0
[1.2.0]: https://github.com/CassioDalla/Scrinalia/releases/tag/v1.2.0
[1.1.0]: https://github.com/CassioDalla/Scrinalia/releases/tag/v1.1.0
[1.0.0]: https://github.com/CassioDalla/Scrinalia/releases/tag/v1.0.0
