import re
from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.sql.elements import ColumnElement

from scrinalia.core.database import get_db
from scrinalia.core.logger import logger
from scrinalia.core.runner_config import NerRunnerConfig
from scrinalia.core.unit_of_work import UnitOfWork
from scrinalia.domains.archive.engines.base import EntityExtractionEngine
from scrinalia.domains.archive.engines.NER.registry import EngineName as ExtractEngineName
from scrinalia.domains.archive.engines.NER.registry import PresetName, describe_config, get_engine
from scrinalia.domains.archive.models import (
    ArchiveDocument,
    DomainNerExclusion,
    DomainStopwords,
    StopwordMatch,
    StopwordsScope,
)
from scrinalia.domains.archive.repository import EntityRepository
from scrinalia.domains.archive.repository.governance import ai_writable_documents
from scrinalia.domains.archive.repository.text_quality_repo import (
    TextQualityRepository,
    composed_text_sql,
)
from scrinalia.domains.archive.schemas.command_schema import EntityLinkCommand
from scrinalia.domains.archive.worker_stamp import NER, identity_stamp_conditions, producer_fingerprint
from scrinalia.domains.archive.workers.cancellation import RunControl, checkpoint
from scrinalia.domains.archive.workers.run_budget import RunBudget


@dataclass(frozen=True)
class EntityBlacklist:
    """
    The banned spellings, split by how each one matches an extracted name.

    ``exact`` holds what was banned as a **spelling**: every ``DomainNerExclusion`` — a person's
    decision that the term belongs to the subject axis — and the stopwords marked ``EXACT``.
    ``token`` holds the noise words that must also swallow the merged spans they start.

    The split is the fix for #160. Measured on the reference collection, one token rule over the
    union rejected 47 names for ``casa`` (among them ``casa da memória``), 23 for ``alameda`` (every
    ``Alameda …`` street), 10 for ``patrimônio``, 7 for ``caixa`` — 115 names over 1.288 links and
    1.170 documents. An exclusion is a decision about a spelling, and a generic word that merely
    starts a proper name is not a reason to drop the name.
    """

    exact: frozenset[str]
    token: frozenset[str]


def load_entity_blacklist(db_session: Session) -> EntityBlacklist:
    """
    Loads every spelling the NER must not extract, with the way each one matches.

    Two independent sources, because they answer different questions:

    * ``DomainStopwords`` (scope ENTITY/ALL): generic noise ("lixo", "ofício"), dropped from every
      extraction. Its ``match_mode`` decides whether the word also blocks the names that contain it:
      ``iptu`` has to (the engine returns ``IPTU do Exemplo``), ``alameda`` must not.
    * ``DomainNerExclusion``: a curation decision that the spelling belongs to the subject axis (a
      tag), recorded when the LLM judge or a human settled a tag x entity clash. It is *not* noise —
      the term is a legitimate subject — so it matches the spelling alone and never a name that
      contains it: the conflict was about ``casa``, not about ``casa da memória``.
    """
    stopwords = db_session.execute(
        select(DomainStopwords.word, DomainStopwords.match_mode).where(
            DomainStopwords.word_scope.in_([StopwordsScope.ENTITY, StopwordsScope.ALL])
        )
    ).all()
    excluded = db_session.scalars(select(DomainNerExclusion.term)).all()

    exact = {term.lower() for term in excluded}
    token: set[str] = set()
    for word, mode in stopwords:
        if mode == StopwordMatch.EXACT:
            exact.add(word.lower())
        else:
            token.add(word.lower())
    return EntityBlacklist(exact=frozenset(exact), token=frozenset(token))


def is_blocked_entity_name(name: str, blacklist: EntityBlacklist) -> bool:
    """
    True when the extracted spelling is banned, or contains a token a ban must swallow.

    The exact check alone is not enough for a **token-mode** stopword, and the real engine shows why:
    spaCy merges neighbouring tokens, so with "iptu" excluded the model still returns the single
    entity ``"IPTU do Exemplo"``. Matching on token boundaries blocks that merged form while leaving
    legitimate names that merely contain the letters untouched (``"iptu"`` blocks
    ``"iptu do exemplo"``, but never ``"iptuana"``).

    An **exact** ban is the opposite: it blocks ``"casa"`` and lets ``"casa da memória"`` through,
    because the decision was about the spelling. The token intersection reads only ``blacklist.token``
    — an exclusion must never reject a name that merely contains the word.
    """
    normalized = name.strip().lower()

    if normalized in blacklist.exact or normalized in blacklist.token:
        return True

    tokens = {token for token in re.split(r"\W+", normalized) if token}
    return bool(tokens & blacklist.token)


#: What a URL may carry, from RFC 3986: the unreserved characters, the gen-delims, the sub-delims
#: and ``%``.
#:
#: Spelled out character by character on purpose. What this replaced was ``[$-_@.&+]``, which Python
#: reads as the **range** ``$`` to ``_``: it swallowed every digit, every uppercase letter and
#: ``[ \ ] ^``, while ``#`` and ``~`` — which a URL really carries — stopped the match. The class
#: beside it, ``[!*\\(\\),]``, listed ``\`` twice. CodeQL flagged both (``py/overly-large-range``
#: and ``py/regex/duplicate-in-character-class``).
_URL_PATTERN = re.compile(r"https?://[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]+")


def _clean_raw_text(text: str) -> str:
    """Helper to clean basic noise before sending it to the AI."""

    if not text:
        return ""

    # 1. Removes URLs (http, https, www)
    text_no_urls = _URL_PATTERN.sub("", text)
    text_no_urls = re.sub(r"www\.\S+", "", text_no_urls)

    # 2. Removes e-mails
    text_no_urls = re.sub(r"[\w\.-]+@[\w\.-]+", "", text_no_urls)

    return text_no_urls.strip()


def resolved_columns(config: NerRunnerConfig | None, columns_to_extract: list[str] | None) -> list[str]:
    """The columns a run really reads, resolved once for ``execute`` and the panel."""
    resolved = config or NerRunnerConfig()
    return list(columns_to_extract or resolved.columns_to_extract)


def effective_options(columns_to_extract: list[str] | None = None, **_options: Any) -> dict[str, Any]:
    """
    The option values a run really uses, through the same helper ``execute`` calls.

    Named by the catalogue (``option_resolver``) so the run ledger records the columns the run read
    and not only the ones somebody typed (#120). ``config`` never reaches here — it is a runner
    dataclass and the write path refuses it — so the resolution is the code default.
    """
    return {"columns_to_extract": resolved_columns(None, columns_to_extract)}


def producer_identity(
    *,
    engine_name: ExtractEngineName,
    preset: PresetName | None,
    columns_to_extract: list[str],
    engine_kwargs: dict,
) -> str:
    """
    Identity of the extractor that produced the entities of a document.

    The configuration comes from ``describe_config``, the read-only twin of ``get_engine``, and the
    columns are part of it because changing which text is read changes which entities are found —
    the axis also carries the installed ``spacy`` version, whose bump rewrites every extraction
    without touching the preset.
    """
    config = describe_config(engine_name, preset, **engine_kwargs)
    return producer_fingerprint(
        axis="NER",
        engine_name=engine_name,
        preset=preset,
        engine_config=config,
        worker_options={"columns_to_extract": columns_to_extract},
    )


def pending_conditions(
    columns_to_extract: list[str],
    producer: str,
    force: bool = False,
) -> list[ColumnElement[bool]]:
    """
    Predicate of the NER queue, shared by ``execute`` and the operations panel.

    HUMAN_APPROVED documents are shielded: the AI must not overwrite human curation. A document
    with no text in any of the extracted columns is skipped because there is nothing to read. A
    document stamped by **another producer** is pending again — which is what makes an extraction
    re-runnable after a model change — and ``force`` widens the queue to everything ai-writable.
    """
    filters_columns = [getattr(ArchiveDocument, col).is_not(None) for col in columns_to_extract]
    conditions: list[ColumnElement[bool]] = [
        ai_writable_documents(),
        or_(*filters_columns),
    ]
    conditions.extend(identity_stamp_conditions(ArchiveDocument.execution_log, NER, producer, force=force))
    return conditions


def count_pending(
    db: Session,
    columns_to_extract: list[str] | None = None,
    config: NerRunnerConfig | None = None,
    force: bool = False,
    engine_name: ExtractEngineName = "spacy_ner",
    preset: PresetName | None = "gpu",
    **engine_kwargs: Any,
) -> int:
    """Documents the next NER run would read, under the identity it would write."""
    columns = resolved_columns(config, columns_to_extract)
    identity = producer_identity(
        engine_name=engine_name,
        preset=preset,
        columns_to_extract=columns,
        engine_kwargs=engine_kwargs,
    )
    stmt = select(func.count()).select_from(ArchiveDocument).where(*pending_conditions(columns, identity, force=force))
    return int(db.scalar(stmt) or 0)


def execute(
    db: Session,
    engine_name: ExtractEngineName = "spacy_ner",
    preset: PresetName = "gpu",
    db_batch_size: int = 64,
    columns_to_extract: list[str] | None = None,
    config: NerRunnerConfig | None = None,
    force: bool = False,
    limit: int | None = None,
    run_control: RunControl | None = None,
    **engine_kwargs: Any,
) -> None:
    """
    Main orchestrator of the Named Entity Recognition (NER) pipeline.

    Implements an asynchronous batch processing pattern
    with memory protection. The worker fetches documents from the database that do not
    yet have the 'worker_ner_v2' key in the JSON column `execution_log`.

    For each batch, the orchestrator:
    1. Concatenates and sanitizes the configured text columns.
    2. Sends the texts to the injected AI engine (Strategy pattern via Registry)
       together with institutional rules loaded dynamically.
    3. Persists the found entities (UPSERT) and creates the N:N relationships.
    4. Applies a universal stamp on the document to guarantee that the queue advances,
       preventing infinite loops on inference failure. The stamp is the **identity of the
       extractor** (engine, preset, columns, installed spaCy), so a different model re-reads the
       document by itself instead of leaving the old extraction silently in place.

    The loop advances by a ``description_id`` cursor. The stamp is what leaves the queue in a
    plain run, but ``force`` ignores it, and without the cursor a forced run would refetch the
    same documents forever. The NER synonyms rules the curation edits are deliberately **not**
    part of the identity: they are a vocabulary table a hash cannot see, which is what ``force``
    is for.

    The database session is expunged (expunge_all) after each completed transaction to
    avoid memory leaks in long-running executions.

    Args:
        db (Session): Active SQLAlchemy session injected by the caller.
        engine_name (ExtractEngineName, optional): Registration key of the NLP
            processing engine to be instantiated. Default is "spacy_ner".
        preset (PresetName, optional): Predefined hardware/model configuration
            for the engine (e.g. "gpu", "cpu_local"). Default is "gpu".
        db_batch_size (int, optional): Limit of documents fetched and committed
            per transaction in the database. Default is 64.
        columns_to_extract (list[str] | None, optional): List of attributes of the model
            `ArchiveDocument` that will form the context analyzed by the AI. If `None`,
            it uses `["original_title", "admin_bio_history", "provenance", "scope_content"]`.
        force (bool, optional): When ``True``, ignores the producer identity and re-reads every
            ai-writable document once, which is the way back from a curation edit to the synonym
            rules that a hash cannot see. Default is ``False``.
        limit (int | None, optional): Cap on the documents this run touches, so a trial costs N
            documents instead of the collection. Not persisted. Default is ``None``.
        **engine_kwargs (Any): Extra keyword arguments forwarded directly to the
            AI engine constructor to override preset configurations.

    Raises:
        Exception: If there is a critical failure loading the NLP engine or the
            configured hardware dependencies.

    Returns:
        None. The pipeline processes batches continuously until the database queue
        is completely empty.

    """
    logger.info(f"🚀 Starting the NER Worker (Engine: {engine_name} | Preset: {preset} | Force: {force})")

    config = config or NerRunnerConfig()
    columns_to_extract = resolved_columns(config, columns_to_extract)
    repository = EntityRepository(db)
    uow = UnitOfWork(db)

    try:
        logger.info("Loading Extraction Engine and dynamic rules...")
        dynamic_rules = repository.get_ner_synonyms_rules()
        # The engine must be able to receive these rules in the constructor or via a setup() method
        engine: EntityExtractionEngine = get_engine(
            engine_name=engine_name, preset=preset, custom_rules=dynamic_rules, **engine_kwargs
        )

    except Exception as e:
        logger.error(f"❌ Error instantiating the NER engine: {e}")
        raise

    identity = producer_identity(
        engine_name=engine_name,
        preset=preset,
        columns_to_extract=columns_to_extract,
        engine_kwargs=engine_kwargs,
    )
    logger.info(f"🔖 Producer identity: {identity[:12]}")

    # 1. Filters (We look for docs that do NOT yet have the NER stamp of this producer).
    # HUMAN_APPROVED documents are shielded: the AI must not overwrite human curation.
    where_cond = pending_conditions(columns_to_extract, identity, force=force)

    # Pre-Query for the logs
    query_count = select(func.count()).select_from(ArchiveDocument).where(*where_cond)
    total_documents = db.scalar(query_count)

    if not total_documents:
        logger.info("✨ No pending documents for entity extraction.")
        return

    logger.info(f"🔍 Found {total_documents} documents to process.")

    blacklist = load_entity_blacklist(db)
    logger.info(
        f"🛡️ Loaded {len(blacklist.exact)} exact and {len(blacklist.token)} token blocked terms "
        "(stopwords + NER exclusions)."
    )

    # The approved excerpts are subtracted from the extracted text (and from the hash the
    # embedding stamp uses), so boilerplate stops feeding the entity extractor.
    rules = TextQualityRepository(db).get_active_rules("NER")
    text_expression = composed_text_sql(columns_to_extract, rules, separator=". ")
    logger.info(f"🧹 {len(rules)} approved excerpt(s) will be kept out of the extracted text.")

    processed_docs_count = 0
    last_id = ""
    budget = RunBudget(limit)
    while True:
        checkpoint(run_control)
        try:
            query = (
                select(ArchiveDocument, text_expression.label("effective_text"))
                .where(*where_cond, ArchiveDocument.description_id > last_id)
                .order_by(ArchiveDocument.description_id)
                .limit(budget.batch_size(db_batch_size))
            )
            batch_rows = db.execute(query).all()

            if not batch_rows:
                break

            last_id = batch_rows[-1][0].description_id
            budget.spend(len(batch_rows))

            texts_buffer = []
            valid_docs = []

            # 2. Preparation and Cleaning of the texts (already composed by PostgreSQL)
            for doc, raw_text in batch_rows:
                text_contextualized = _clean_raw_text(raw_text or "")

                if not text_contextualized:
                    # Stamps empty docs so they do not enter a loop
                    doc.execution_log = NER.mark_value(doc.execution_log, identity)
                    flag_modified(doc, "execution_log")
                    continue

                valid_docs.append(doc)
                texts_buffer.append(text_contextualized)

            batch_links_buffer = []
            if texts_buffer:
                logger.info(f"🧠 Extracting entities from {len(texts_buffer)} documents...")

                # 3. Batch inference isolated in the try/except
                try:
                    # The engine must receive a list of texts and return a list of results
                    # (where each result is a list of ArchiveEntityDTO)
                    ner_results = engine.extract(texts_buffer)
                except Exception as e:
                    logger.error(f"❌ Failure in the AI processing: {e}")
                    uow.rollback()
                    break

                # 4. Application of the Results and Persistence in the Database
                for doc, dtos_entities in zip(valid_docs, ner_results, strict=True):
                    failed = False
                    doc = cast(ArchiveDocument, doc)
                    try:
                        # If the AI found entities, we process the links
                        if dtos_entities:
                            filtered_dtos = [
                                ent for ent in dtos_entities if not is_blocked_entity_name(ent.name, blacklist)
                            ]

                            if filtered_dtos:
                                try:
                                    with db.begin_nested():
                                        entity_ids = repository.get_or_create_entities(filtered_dtos)

                                        for e_id in entity_ids:
                                            batch_links_buffer.append(
                                                EntityLinkCommand(description_id=doc.description_id, entity_id=e_id)
                                            )

                                        logger.debug(
                                            f"Doc {doc.description_id} ➡️ {len(entity_ids)} entities ready for linking."
                                        )
                                except Exception as e_nested:
                                    logger.error(f"❌ Transactional error in doc {doc.description_id}: {e_nested}")
                                    failed = True
                            else:
                                logger.debug(f"Doc {doc.description_id} ➡️ All entities blocked by the Blacklist.")
                        else:
                            logger.debug(f"Doc {doc.description_id} ➡️ No entity found.")

                        processed_docs_count += 1

                    except Exception as e:
                        logger.error(f"❌ Structural error saving entities for doc {doc.description_id}: {e}")
                        failed = True

                    # 5. The Universal Protection Stamp. A failure is written as a failure and never
                    # as the identity, or the document would look processed by this producer.
                    try:
                        doc.execution_log = (
                            NER.mark_failed(doc.execution_log)
                            if failed
                            else NER.mark_value(doc.execution_log, identity)
                        )
                        flag_modified(doc, "execution_log")
                    except Exception as e:
                        logger.critical(f"Critical failure stamping the error on doc {doc.description_id}: {e}")

            # 6. Batch Commit and Memory Cleanup
            try:
                if batch_links_buffer:
                    repository.bulk_link_entities(batch_links_buffer)

                uow.commit()
                logger.info(f"⏳ Partial progress: {processed_docs_count} documents enriched...")
            except Exception as e:
                uow.rollback()
                logger.error(f"💥 Failure committing to the database: {e}")
                break

            db.expunge_all()

        except Exception as e:
            logger.error(f"❌ Unexpected error in the main loop of the NER Worker: {e}")
            uow.rollback()
            break

    logger.success(f"✅ NER Worker finished! Total processed in this run: {processed_docs_count}")


if __name__ == "__main__":
    with get_db() as db:
        execute(db=db, db_batch_size=100)
