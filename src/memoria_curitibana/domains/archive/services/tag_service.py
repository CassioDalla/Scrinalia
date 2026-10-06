import re
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Literal

from memoria_curitibana.core.logger import logger
from memoria_curitibana.domains.archive.domain.normalization import normalize_stopword, normalize_tag
from memoria_curitibana.domains.archive.exceptions import (
    DomainException,
    InvalidMergeError,
    InvalidParam,
    MacroCategoryNotFoundError,
    TagMergeProposalNotFoundError,
    TagNotFoundError,
)
from memoria_curitibana.domains.archive.models.enums import StopwordsScope
from memoria_curitibana.domains.archive.ports.document import DocumentRepositoryPort
from memoria_curitibana.domains.archive.ports.taxonomy import SubjectExclusionSource, TagRepositoryPort
from memoria_curitibana.domains.archive.schemas import (
    ArchiveMacroCategoryEntityDTO,
    ArchiveTagDTO,
    BatchMergeResponse,
    CreateMacroCategoryCommand,
    MergeBatchCommand,
    MergeBatchEntry,
    MergeBatchFailure,
    MergeLogEntryDTO,
    MergeLogListResponse,
    MergePreviewCommand,
    MergePreviewResponse,
    MergeResponse,
    MergeSuggestionRunResponse,
    MergeTagsCommand,
    StopwordDTO,
    StopwordPurgePreview,
    SubjectExclusionSuggestionResponse,
    TagCurationCommand,
    TagCurationResult,
    TagMergeDecisionCommand,
    TagMergeProposalDTO,
    TagMergeProposalListResponse,
    TagPairSimilarity,
    TagRelevanceCount,
    TagRelevanceIdf,
    TagSearchResult,
    TagSimilarity,
    UpdateMacroCategoryCommand,
)

#: Upper bound of one page of proposals. The real collection produced hundreds of clusters,
#: so paging is the default and a client cannot ask for the whole catalog in one request.
MAX_MERGE_PROPOSALS_PAGE = 200

#: Upper bound of one batch. Each cluster is applied in its own savepoint, but the request is
#: still a single transaction, so it has to stay bounded.
MAX_MERGE_BATCH_CLUSTERS = 200

#: Upper bound of one page of the merge ledger.
MAX_MERGE_LOG_PAGE = 200

#: How many characters a tag search needs before it is answered. One letter matches thousands of
#: the tags in the catalogue, and the box exists to *choose* a spelling, not to browse one.
MIN_SEARCH_TERM = 2


class TagService:
    """
    Domain service responsible for auditing, sanitizing and unifying
    the taxonomy and tags in the Archive layer.
    """

    def __init__(self, repo: TagRepositoryPort, document_repo: DocumentRepositoryPort):
        self.repo = repo
        self.document_repo = document_repo
        self._stopwords: frozenset[str] | None = None

    def _get_stopwords(self) -> frozenset[str]:
        """
        Fetches the stopwords from the database only once and caches them as a set.

        A set is used (instead of a compiled regex) because matching whole entries is
        the only safe rule: a substring regex would corrupt legitimate multi-word tags
        (e.g. the stopword "rio" would turn "Rio Branco" into "Branco").
        """
        if self._stopwords is None:
            self._stopwords = frozenset(normalize_stopword(word) for word in self.repo.get_stopwords() if word.strip())

        return self._stopwords

    def extract_and_clean_tags(self, indexing_points: str | None) -> list[ArchiveTagDTO]:
        """
        Reads the raw indexing points (comma-separated), applies
        the stopwords dictionary from the database and returns the validated contracts.
        """
        if not indexing_points:
            return []

        # Fetches the active stopwords directly from the database
        stopwords = self._get_stopwords()

        # The staging layer may join duplicate source keys with " | ", so both "|" and
        # "," are treated as tag separators.
        raw_tags = re.split(r"[,|]", indexing_points)
        clean_tags = set()

        for tag in raw_tags:
            tag = tag.strip().lower()

            # A stopword only removes the tag when it is the WHOLE tag. Removing it as a
            # substring would destroy valid multi-word tags ("Rio Branco" -> "Branco").
            if tag in stopwords:
                continue

            tag = re.sub(r"\s+", " ", tag)

            if 2 < len(tag) <= 100:
                clean_tags.add(tag)
            elif len(tag) > 100:
                logger.warning(f"⚠️ Tag ignored for being too long: '{tag[:50]}...'")

        return [
            ArchiveTagDTO(name=tag_name, macro_category_id=None, ai_confidence_score=None) for tag_name in clean_tags
        ]

    def process_worker_tags(self, dtos_from_worker: list[ArchiveTagDTO]) -> list[int]:
        """
        Business pipeline: Checks synonyms and routes for persistence.
        Returns the final list of IDs (canonical or newly created) to link to the document.
        """
        if not dtos_from_worker:
            return []

        # 1. Extracts only the lowercase names to check the synonyms in the database
        names_to_search = [normalize_tag(dto.name) for dto in dtos_from_worker]

        # 2. Fetches the mapping from the Repository (Returns something like: {"prefeiruta": 45, "parques": 12})
        synonyms_map = self.repo.get_synonyms_mapping(names_to_search)

        final_ids_for_document = []
        dtos_to_create = []

        # 3. The Business Rule Routing (The fine mesh)
        for dto in dtos_from_worker:
            normalized_name = normalize_tag(dto.name)

            if normalized_name in synonyms_map:
                # It is a known synonym! We discard the DTO and use the Canonical Tag ID
                canonical_id = synonyms_map[normalized_name]
                final_ids_for_document.append(canonical_id)
            else:
                # It is a new or legitimate tag. It goes to the persistence queue.
                dtos_to_create.append(dto)

        # 4. Sends to the creation repository ONLY the tags that were not synonyms
        if dtos_to_create:
            new_or_existing_ids = self.repo.get_or_create_tags(dtos_to_create)
            final_ids_for_document.extend(new_or_existing_ids)

        # 5. Returns a set converted to a list to ensure the same document
        # does not receive the same tag ID twice (e.g. if "park" and "parks" come in the same document)
        return list(set(final_ids_for_document))

    def save_new_stopwords(self, word_list: list[str], scope: StopwordsScope = StopwordsScope.TAG) -> int:
        """Bans terms from one axis. ``TAG`` by default: it is the axis this catalog governs."""
        return self.repo.save_stopwords(word_list, scope)

    def list_stopwords(self, scope: StopwordsScope | None = None) -> list[StopwordDTO]:
        """
        The banned terms, with the axis each one was banned from.

        The scope travels with the word because the two axes are different mechanisms: a ``TAG`` ban
        feeds the subject purge, an ``ENTITY`` ban keeps a term out of the NER extraction, and
        ``get_stopwords()`` deliberately reads only ``TAG``/``ALL`` so the first can never delete a
        tag because of the second.
        """
        return self.repo.list_stopwords(scope)

    def remove_stopwords(self, word_list: list[str], scope: StopwordsScope | None = None) -> int:
        """
        Un-bans terms. This is the only way back from a purge decision, because the purge deletes the
        tags themselves and has no ledger to restore them from.
        """
        return self.repo.remove_stopwords(word_list, scope)

    def preview_stopword_purge(self) -> StopwordPurgePreview:
        """
        What the purge would delete, computed with the same list the purge itself reads.

        The list is ``get_stopwords()`` — ``TAG``/``ALL`` only — so the preview and the write cannot
        disagree about which words are in play. Same rule as the merge dry run.
        """
        stopwords = self.repo.get_stopwords()
        tags = self.repo.find_tags_by_stopwords(stopwords)
        return StopwordPurgePreview(
            stopwords=sorted(stopwords),
            tags=tags,
            total_tags=len(tags),
            total_documents=sum(tag.document_count for tag in tags),
            reversible=False,
        )

    def purge_stopwords(self) -> int:
        """
        Deletes every tag whose name is a banned term, and **this one has no undo**.

        The merge keeps a ledger and restores the tag, its links and its classification; here the row
        goes and the links cascade. The route offers a preview first and the screen says so out loud,
        because a destructive write with no reversal is exactly the case the project's rule — every
        write is reversible or announced — is about.
        """

        clean_stopwords = self.repo.get_stopwords()
        if not clean_stopwords:
            return 0

        return self.repo.purge_tags_by_stopwords(clean_stopwords)

    def get_tag_relevance_count(self, limit: int = 30) -> Sequence[TagRelevanceCount]:
        """
        Counts how many times each tag appears associated with a document in the collection.
        """
        return list(self.repo.get_relevance_count(limit))

    def get_tag_relevance_tfidf(self, limit: int = 30) -> Sequence[TagRelevanceIdf]:
        """
        Calculates the global relevance of tags using the native TF-IDF formula in PostgreSQL.
        Penalizes generic tags that appear throughout the collection and highlights specific terms.
        """
        return list(self.repo.get_relevance_tfidf(limit))

    def find_similar_tags(self, target_tag: str, threshold: float = 0.5) -> Sequence[TagSimilarity]:
        """
        Searches for tags with typos or high similarity using the pg_trgm extension.
        """
        if not target_tag:
            raise InvalidParam("O parametro 'target_tag' é obrigatório")

        # Business rule: always search in lowercase
        target_lower = target_tag.strip().lower()
        return list(self.repo.find_similar(target_lower, threshold))

    def search_tags(self, term: str, limit: int = 20) -> list[TagSearchResult]:
        """
        Tags matching what the curator is typing, for the type-ahead of the dossier.

        Two characters is the floor: one letter matches thousands of the 8.349 tags and the list
        would be a lottery, while the whole point of the box is to *choose* a spelling. The floor
        lives here and not in the route so any other caller inherits it.
        """
        if len(term.strip()) < MIN_SEARCH_TERM:
            return []
        return list(self.repo.search_tags(term, limit))

    def curate_tag_macro_category(self, tag_id: int, command: TagCurationCommand) -> TagCurationResult:
        """
        Records the archivist's verdict on which drawer one tag belongs to.

        This is a **global** decision, not a local one: it changes the badge of every description
        that carries the tag. The two halves of the verdict are both accepted — moving the tag into
        a drawer, or declaring that it is not a subject at all — and the second is what
        ``macro_category_id=None`` means, which is why the field is required and nullable.

        The stamp written into the tag's ledger carries who and when, because tags have no revision
        table and this is the only trace the decision leaves.
        """
        if command.macro_category_id is not None and self.repo.get_macro_category(command.macro_category_id) is None:
            raise MacroCategoryNotFoundError(f"Categoria macro {command.macro_category_id} não existe no catálogo.")

        stamp = f"{command.macro_category_id if command.macro_category_id is not None else 'NONE'}|{command.changed_by or ''}|{datetime.now(UTC).isoformat(timespec='seconds')}"
        updated = self.repo.update_tag_macro_category(tag_id, command.macro_category_id, stamp)
        if updated is None:
            raise TagNotFoundError(f"Tag {tag_id} não existe no vocabulário.")

        return TagCurationResult(
            tag_id=updated.tag_id,
            name=updated.name,
            macro_category_id=updated.macro_category_id,
            macro_category_name=updated.macro_category_name,
            human_classified=True,
        )

    def suggest_merges(self, threshold: float = 0.65, limit: int = 50) -> MergeSuggestionRunResponse:
        """
        Computes the probable duplicate clusters and registers them as proposals.

        Suggestion only, like every other curation flow of this phase: nothing is merged and
        no decision is taken. Persisting them is what makes the review finite — the same
        cluster is not re-proposed after a human rejected it.
        """
        if not 0 < threshold <= 1:
            raise InvalidParam("O parâmetro 'threshold' deve estar entre 0 e 1.")

        suggestions = self.repo.find_merge_suggestions(threshold=threshold, limit=limit)
        persisted = self.repo.upsert_merge_proposals(suggestions)

        return MergeSuggestionRunResponse(
            clusters_found=len(suggestions),
            persisted=persisted,
            pending=self.repo.count_merge_proposals(status="SUGGESTED"),
            flagged=self.repo.count_merge_proposals(status="SUGGESTED", flagged_only=True),
        )

    def find_all_similar_tag_pairs(self, threshold: float = 0.65) -> Sequence[TagPairSimilarity]:
        """
        Scans the collection and cross-references all tags with each other to find
        pairs that are very similar (potential duplicates).
        """
        return list(self.repo.find_all_similar_pairs(threshold))

    # ==========================================
    # MERGE PROPOSALS (the curation flow)
    # ==========================================

    def list_merge_proposals(
        self,
        status: str | None = None,
        reason: str | None = None,
        min_documents: int = 0,
        flagged_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> TagMergeProposalListResponse:
        """One page of proposals with the total matching the same filters (no silent truncation)."""
        if limit <= 0 or limit > MAX_MERGE_PROPOSALS_PAGE:
            raise InvalidParam(f"O parâmetro 'limit' deve estar entre 1 e {MAX_MERGE_PROPOSALS_PAGE}.")
        if offset < 0:
            raise InvalidParam("O parâmetro 'offset' não pode ser negativo.")

        total = self.repo.count_merge_proposals(
            status=status, reason=reason, min_documents=min_documents, flagged_only=flagged_only
        )
        items = self.repo.list_merge_proposals(
            status=status,
            reason=reason,
            min_documents=min_documents,
            flagged_only=flagged_only,
            limit=limit,
            offset=offset,
        )
        return TagMergeProposalListResponse(total=total, limit=limit, offset=offset, items=items)

    def decide_merge_proposal(self, proposal_id: int, command: TagMergeDecisionCommand) -> TagMergeProposalDTO:
        """
        Records the archivist's verdict on a proposal.

        Approval means "this cluster should be unified"; the merge itself is applied later,
        with the ledger that makes it reversible. A click on a listing never writes to the
        collection on its own.
        """
        updated = self.repo.decide_merge_proposal(
            proposal_id, status=command.status, decided_by=command.decided_by, note=command.note
        )
        if updated is None:
            raise TagMergeProposalNotFoundError(
                f"Proposta de mesclagem {proposal_id} não encontrada no catálogo de curadoria."
            )
        return updated

    def merge(self, command: MergeTagsCommand) -> MergeResponse:
        """
        Merges tags: computes the plan and applies it.

        The plan is the single definition of the operation, shared with the dry-run, so the
        preview cannot diverge from what the merge really does. The apply writes the ledger,
        which is what lets the same operation be undone later.
        """
        self._validate_merge_inputs(command.canonical_id, command.ids_to_merge)
        plan = self.repo.plan_merge(command.canonical_id, command.ids_to_merge)
        return self.repo.apply_merge(plan, changed_by=command.changed_by)

    def merge_batch(self, command: MergeBatchCommand) -> BatchMergeResponse:
        """
        Applies several approved clusters, one savepoint each.

        Including a pending proposal in the batch **is** the archivist's decision, so it is
        recorded as approved; a rejected one is never applied, because rejecting is a decision
        too. A cluster that fails is reported and the others are committed — the unit of work
        still owns the single final commit.
        """
        proposal_ids = list(dict.fromkeys(command.proposal_ids))
        if len(proposal_ids) > MAX_MERGE_BATCH_CLUSTERS:
            raise InvalidParam(f"O lote aceita no máximo {MAX_MERGE_BATCH_CLUSTERS} clusters por requisição.")

        entries: list[MergeBatchEntry] = []
        failures: list[MergeBatchFailure] = []
        skipped: list[MergeBatchFailure] = []

        for proposal_id in proposal_ids:
            proposal = self.repo.get_merge_proposal(proposal_id)
            if proposal is None:
                failures.append(MergeBatchFailure(proposal_id=proposal_id, error="Proposta não encontrada."))
                continue
            if proposal.status == "REJECTED":
                failures.append(MergeBatchFailure(proposal_id=proposal_id, error="Proposta rejeitada pelo curador."))
                continue
            if proposal.canonical_id is None:
                failures.append(MergeBatchFailure(proposal_id=proposal_id, error="A proposta não tem tag canônica."))
                continue
            if not proposal.applicable:
                # Nothing to absorb: the members this cluster named are already gone, which means an
                # earlier merge (or a purge) did the work. It is not a failure — and calling it one
                # is what turned a finished batch into twenty red lines.
                skipped.append(
                    MergeBatchFailure(
                        proposal_id=proposal_id,
                        error="Os membros já foram absorvidos por uma mesclagem anterior — não há o que aplicar.",
                    )
                )
                continue

            ids_to_merge = [member.tag_id for member in proposal.members if member.tag_id != proposal.canonical_id]
            try:
                plan = self.repo.plan_merge(proposal.canonical_id, ids_to_merge)
            except DomainException as exc:
                failures.append(MergeBatchFailure(proposal_id=proposal_id, error=str(exc)))
                continue

            if not plan.ids_to_merge:
                failures.append(
                    MergeBatchFailure(
                        proposal_id=proposal_id,
                        error="Os membros já não existem no acervo (a mesclagem já foi aplicada?).",
                    )
                )
                continue

            if proposal.status == "SUGGESTED":
                self.repo.decide_merge_proposal(
                    proposal_id, status="APPROVED", decided_by=command.changed_by, note=command.note
                )

            entries.append(
                MergeBatchEntry(proposal_id=proposal_id, cluster_fingerprint=proposal.fingerprint, plan=plan)
            )

        result = self.repo.apply_merge_batch(entries, changed_by=command.changed_by, note=command.note)

        if result.failed:
            logger.warning(f"⚠️ {len(result.failed)} clusters do lote não foram aplicados: {result.failed}")
        if skipped:
            logger.info(f"{len(skipped)} clusters do lote já estavam aplicados e foram ignorados.")

        return BatchMergeResponse(applied=result.applied, failed=[*failures, *result.failed], skipped=skipped)

    def undo_merge(self, merge_id: int, undone_by: str | None = None) -> MergeLogEntryDTO:
        """
        Reverses one merge from the ledger, restoring the tag, its links and its spellings.

        The repository raises ``MergeLogNotFoundError`` (404) or ``MergeAlreadyUndoneError``
        (409); the service does not translate them, the API handler owns that mapping.
        """
        entry = self.repo.undo_merge(merge_id, undone_by=undone_by)
        logger.info(f"↩️ Mesclagem {merge_id} desfeita: '{entry.absorbed_name}' restaurada.")
        return entry

    def list_merge_log(
        self,
        canonical_id: int | None = None,
        changed_by: str | None = None,
        include_undone: bool = True,
        term: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> MergeLogListResponse:
        """The audit trail of the merges, with the total matching the same filters."""
        if limit <= 0 or limit > MAX_MERGE_LOG_PAGE:
            raise InvalidParam(f"O parâmetro 'limit' deve estar entre 1 e {MAX_MERGE_LOG_PAGE}.")
        if offset < 0:
            raise InvalidParam("O parâmetro 'offset' não pode ser negativo.")

        total = self.repo.count_merge_log(
            canonical_id=canonical_id, changed_by=changed_by, include_undone=include_undone, term=term
        )
        items = self.repo.list_merge_log(
            canonical_id=canonical_id,
            changed_by=changed_by,
            include_undone=include_undone,
            term=term,
            limit=limit,
            offset=offset,
        )
        return MergeLogListResponse(total=total, limit=limit, offset=offset, items=items)

    def preview_merge(self, command: MergePreviewCommand) -> MergePreviewResponse:
        """
        Dry-run of a merge: what changes, what is lost and why to look twice.

        Read-only by construction (it only calls ``plan_merge``), which is the point: the
        archivist decides with a number, not with the hope that the merge is harmless.
        """
        canonical_id, ids_to_merge = self._resolve_merge_source(command)
        self._validate_merge_inputs(canonical_id, ids_to_merge)
        plan = self.repo.plan_merge(canonical_id, ids_to_merge)

        return MergePreviewResponse(
            canonical_id=plan.canonical_id,
            canonical_name=plan.canonical_name,
            documents_updated=plan.documents_updated,
            links_rewritten=plan.links_rewritten,
            tags_deleted=plan.impacted,
            synonyms_created=plan.synonym_names,
            synonyms_repointed=plan.repointed_synonyms,
            review_flags=plan.review_flags,
            category_would_be_lost=plan.category_would_be_lost,
        )

    def _resolve_merge_source(self, command: MergePreviewCommand) -> tuple[int, list[int]]:
        """Turns either a persisted proposal or an ad-hoc pair into ``(canonical, ids)``."""
        if command.proposal_id is not None:
            proposal = self.repo.get_merge_proposal(command.proposal_id)
            if proposal is None:
                raise TagMergeProposalNotFoundError(
                    f"Proposta de mesclagem {command.proposal_id} não encontrada no catálogo de curadoria."
                )
            if proposal.canonical_id is None:
                raise InvalidParam("A proposta não tem mais uma tag canônica válida para simular.")

            ids = [member.tag_id for member in proposal.members if member.tag_id != proposal.canonical_id]
            return proposal.canonical_id, ids

        if command.canonical_id is None:
            raise InvalidParam("Informe 'proposal_id' ou 'canonical_id' com 'ids_to_merge'.")
        return command.canonical_id, list(command.ids_to_merge)

    def _validate_merge_inputs(self, canonical_id: int, ids_to_merge: Sequence[int]) -> None:
        """The business rules a merge (and its dry-run, identically) has to respect."""
        if not ids_to_merge:
            raise InvalidParam("A lista de tags para mesclar não pode estar vazia.")

        if canonical_id in ids_to_merge:
            raise InvalidMergeError("O ID da tag canônica não pode estar na lista de exclusão.")

        canonical_exists = self.repo.get_by_id(canonical_id)
        if not canonical_exists:
            raise InvalidParam(f"A tag canônica informada (ID {canonical_id}) não existe no acervo.")

    def get_text_to_suggest_macro_category(
        self,
        source_type: Literal["tags", "documents"] = "tags",
        columns_to_extract: list[str] | None = None,
    ) -> list[str]:
        """
        Extracts all tags from the collection and uses Artificial Intelligence
        (Clustering) to suggest semantic groupings (Macro Categories).
        """
        logger.info(f"🔍 Starting topic discovery using source_type:{source_type}...")

        if source_type not in ["tags", "documents"]:
            raise InvalidParam("O parâmetro 'source_type' deve ser obrigatoriamente 'tags' ou 'documents'.")

        if source_type == "tags":
            texts_to_analyze = self.repo.fetch_tags_for_clustering()
        elif source_type == "documents":
            # Hack that will be refactored
            texts_to_analyze = self.document_repo.fetch_documents_for_clustering(columns_to_extract=columns_to_extract)

        return texts_to_analyze

    # ==========================================
    # MACRO CATEGORIES (SUBJECT AXIS)
    # ==========================================

    def list_subject_exclusions(self) -> list[str]:
        """Lists the terms the curation decided are not a subject."""
        return sorted(self.repo.get_subject_exclusions())

    def suggest_subject_exclusions(
        self, limit: int = 50, offset: int = 0, include_excluded: bool = False
    ) -> SubjectExclusionSuggestionResponse:
        """
        The terms the deterministic guard already refuses, with the evidence around each.

        Suggestion only, and deliberately not a model: the guard is a pure function of the spelling,
        so its verdict cannot hallucinate and costs no inference. What the route adds is visibility —
        the guard has been skipping these terms inside ``worker_macro_category`` while the
        ``source='RULE'`` value the schema anticipated was never written by anything.
        """
        return self.repo.find_subject_exclusion_candidates(
            limit=limit, offset=offset, include_excluded=include_excluded
        )

    def exclude_terms_from_subjects(
        self, words: list[str], reason: str | None = None, source: SubjectExclusionSource = "HUMAN"
    ) -> int:
        """
        Records that a term is not a subject, so the classifier stops guessing at it.

        This is the curated half of the NENHUMA class. The deterministic guard in
        ``domain.vocabulary`` matches a form; the terms that reach here have none — a generic
        ``pessoas``, a photographic ``vista aérea``, an unknown proper noun — and the model,
        unable to abstain, answers them confidently and wrongly.

        Unlike the NER exclusion this does **not** purge anything: the term stays a tag of the
        collection and stays reachable by search. Only the subject classifier is silenced.
        """
        clean_words = [normalize_tag(word) for word in words if word.strip()]
        if not clean_words:
            raise InvalidParam("Nenhum termo válido foi informado.")

        logger.info(f"🚫 Marking {len(clean_words)} term(s) as not-a-subject...")
        # The provenance is the point of the column: a term the guard refused and the archivist
        # confirmed is a ``RULE`` decision, and one they typed is ``HUMAN``. Both are reversible.
        return self.repo.add_subject_exclusions(clean_words, source=source, reason=reason)

    def remove_subject_exclusions(self, words: list[str]) -> int:
        """Undoes the decision and puts the terms back in the classification queue."""
        clean_words = [normalize_tag(word) for word in words if word.strip()]
        if not clean_words:
            return 0

        return self.repo.remove_subject_exclusions(clean_words)

    def list_macro_categories(self, only_active: bool = False) -> list[ArchiveMacroCategoryEntityDTO]:
        """Lists the official macro categories of the collection."""
        return self.repo.get_macro_categories(only_active=only_active)

    def create_macro_category(self, command: CreateMacroCategoryCommand) -> ArchiveMacroCategoryEntityDTO:
        """
        Turns a curated cluster suggestion into an official macro category.

        Uniqueness of the name is enforced by the schema, so a duplicate surfaces as an
        ``IntegrityError`` and is translated to 409 by the API, not silently swallowed.
        """
        name = command.name.strip()
        if not name:
            raise InvalidParam("O nome da macro categoria não pode ser vazio.")

        logger.info(f"🏷️ Registering macro category '{name}'...")
        label = command.classifier_label.strip() if command.classifier_label else None
        return self.repo.create_macro_category(name=name, description=command.description, classifier_label=label)

    def update_macro_category(
        self, category_id: int, command: UpdateMacroCategoryCommand
    ) -> ArchiveMacroCategoryEntityDTO:
        """Partially updates a macro category. Only the fields sent by the client are touched."""
        changes = command.model_dump(exclude_unset=True)

        if "name" in changes and changes["name"] is not None:
            changes["name"] = changes["name"].strip()
            if not changes["name"]:
                raise InvalidParam("O nome da macro categoria não pode ser vazio.")

        # Blanking the label is how the curator falls back to the bare name; storing "" would
        # send the model an empty hypothesis, which is worse than the name it replaced.
        if "classifier_label" in changes:
            label = changes["classifier_label"]
            changes["classifier_label"] = label.strip() if label and label.strip() else None

        updated = self.repo.update_macro_category(category_id, changes)
        if updated is None:
            raise MacroCategoryNotFoundError(f"Macro categoria {category_id} não encontrada no acervo.")

        return updated
