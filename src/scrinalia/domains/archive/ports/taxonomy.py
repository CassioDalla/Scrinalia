from collections.abc import Sequence
from typing import Any, Literal, Protocol

from scrinalia.core.author import Author
from scrinalia.domains.archive.models.enums import StopwordMatch, StopwordsScope, TagCatalogState
from scrinalia.domains.archive.schemas import (
    ArchiveMacroCategoryEntityDTO,
    ArchiveTagDTO,
    BatchMergeResponse,
    MergeBatchEntry,
    MergeLogEntryDTO,
    MergePlan,
    MergeResponse,
    StopwordDTO,
    StopwordPurgeLogEntryDTO,
    StopwordPurgePlan,
    StopwordPurgeResult,
    SubjectExclusionApplyResult,
    SubjectExclusionPlan,
    SubjectExclusionRemovalResult,
    SubjectExclusionSuggestionResponse,
    SynonymCommand,
    TagCatalogRow,
    TagCount,
    TagIdentity,
    TagMergeProposalDTO,
    TagMergeSuggestion,
    TagPairSimilarity,
    TagRelevanceCount,
    TagRelevanceIdf,
    TagSearchResult,
    TagSimilarity,
)

#: Who recorded a subject exclusion: an archivist, or the deterministic guard whose verdict the
#: archivist confirmed. Both are reversible, and the column exists to tell them apart.
SubjectExclusionSource = Literal["HUMAN", "RULE"]

#: Who planted a ban. ``HUMAN`` typed it on the Stopwords tab, ``CONFLICT`` came from a tag x entity
#: resolution and ``EXCLUSION`` from confirming a term as not-a-subject — one of the three is a
#: consequence and the purge preview has to say which.
StopwordSource = Literal["HUMAN", "CONFLICT", "EXCLUSION"]


class TagRepositoryPort(Protocol):
    """
    Output port for the Tag taxonomy.

    Read methods that feed analytics/UI return DTOs (see ``TagRelevanceCount``,
    ``TagSimilarity``, ...). Write methods still operate on primitives/ORM
    identities; returning domain DTOs for the write side is a known debt
    (see ``.analysis/adr-arquitetura-alvo.md``).
    """

    # --- Read (analytics / curation) ---
    def fetch_tags_for_clustering(self) -> list[str]:
        raise NotImplementedError

    def get_synonyms_mapping(self, words: list[str]) -> dict[str, int]:
        raise NotImplementedError

    def get_stopwords(self) -> set[str]:
        raise NotImplementedError

    def get_relevance_count(self, limit: int) -> Sequence[TagRelevanceCount]:
        raise NotImplementedError

    def get_relevance_tfidf(self, limit: int) -> Sequence[TagRelevanceIdf]:
        raise NotImplementedError

    def find_similar(self, target_lower: str, threshold: float) -> Sequence[TagSimilarity]:
        raise NotImplementedError

    def find_all_similar_pairs(self, threshold: float) -> Sequence[TagPairSimilarity]:
        raise NotImplementedError

    def get_all_tags_with_counts(self) -> Sequence[TagCount]:
        raise NotImplementedError

    def search_tags(self, term: str, limit: int) -> Sequence[TagSearchResult]:
        raise NotImplementedError

    def read_tag_result(self, tag_id: int) -> TagSearchResult | None:
        raise NotImplementedError

    def count_catalog(
        self, state: TagCatalogState, macro_category_id: int | None = None, term: str | None = None
    ) -> int:
        raise NotImplementedError

    def list_catalog(
        self,
        state: TagCatalogState,
        macro_category_id: int | None = None,
        term: str | None = None,
        limit: int = 25,
        offset: int = 0,
    ) -> list[TagCatalogRow]:
        raise NotImplementedError

    def find_merge_suggestions(self, threshold: float, limit: int) -> list[TagMergeSuggestion]:
        raise NotImplementedError

    def count_merge_proposals(
        self,
        status: str | None = None,
        reason: str | None = None,
        min_documents: int = 0,
        flagged_only: bool = False,
    ) -> int:
        raise NotImplementedError

    def list_merge_proposals(
        self,
        status: str | None = None,
        reason: str | None = None,
        min_documents: int = 0,
        flagged_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[TagMergeProposalDTO]:
        raise NotImplementedError

    def get_merge_proposal(self, proposal_id: int) -> TagMergeProposalDTO | None:
        raise NotImplementedError

    def get_tag_synonym_names(self) -> set[str]:
        raise NotImplementedError

    def get_synonym_names_pointing_to(self, tag_ids: Sequence[int]) -> list[str]:
        raise NotImplementedError

    def plan_merge(self, canonical_id: int, ids_to_merge: Sequence[int]) -> MergePlan:
        raise NotImplementedError

    def get_macro_categories(self, only_active: bool = False) -> list[ArchiveMacroCategoryEntityDTO]:
        raise NotImplementedError

    def get_macro_category(self, category_id: int) -> ArchiveMacroCategoryEntityDTO | None:
        raise NotImplementedError

    def get_active_macro_categories(self) -> dict[str, int]:
        raise NotImplementedError

    # --- Write ---
    def get_or_create_tags(self, tags_list: list[ArchiveTagDTO]) -> list[int]:
        raise NotImplementedError

    def save_stopwords(
        self,
        words_list: list[str],
        scope: StopwordsScope = StopwordsScope.TAG,
        source: StopwordSource = "HUMAN",
        match_mode: StopwordMatch = StopwordMatch.TOKEN,
    ) -> int:
        raise NotImplementedError

    def update_stopword_match(self, words: list[str], match_mode: StopwordMatch) -> int:
        raise NotImplementedError

    def ensure_tag_ban(self, words: Sequence[str], source: StopwordSource = "HUMAN") -> set[str]:
        raise NotImplementedError

    def get_stopwords_with_source(self) -> dict[str, str]:
        raise NotImplementedError

    def plan_stopword_purge(self) -> StopwordPurgePlan:
        raise NotImplementedError

    def apply_stopword_purge(self, plan: StopwordPurgePlan, changed_by: Author | None = None) -> StopwordPurgeResult:
        raise NotImplementedError

    def undo_stopword_purge(self, purge_id: int, undone_by: Author | None = None) -> StopwordPurgeLogEntryDTO:
        raise NotImplementedError

    def count_stopword_purge_log(self, include_undone: bool = True, term: str | None = None) -> int:
        raise NotImplementedError

    def list_stopword_purge_log(
        self,
        include_undone: bool = True,
        term: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[StopwordPurgeLogEntryDTO]:
        raise NotImplementedError

    def create_synonyms(self, synonyms_data: list[SynonymCommand]) -> None:
        raise NotImplementedError

    def repoint_synonyms(self, from_tag_ids: list[int], to_tag_id: int) -> int:
        raise NotImplementedError

    def create_macro_category(
        self, name: str, description: str | None, classifier_label: str | None = None
    ) -> ArchiveMacroCategoryEntityDTO:
        raise NotImplementedError

    def update_macro_category(self, category_id: int, changes: dict[str, Any]) -> ArchiveMacroCategoryEntityDTO | None:
        raise NotImplementedError

    def get_subject_exclusions(self) -> set[str]:
        raise NotImplementedError

    def find_subject_exclusion_candidates(
        self, limit: int = 50, offset: int = 0, include_excluded: bool = False
    ) -> SubjectExclusionSuggestionResponse:
        raise NotImplementedError

    def list_stopwords(self, scope: StopwordsScope | None = None) -> list[StopwordDTO]:
        raise NotImplementedError

    def remove_stopwords(self, words: list[str], scope: StopwordsScope | None = None) -> int:
        raise NotImplementedError

    def update_tag_macro_category(
        self, tag_id: int, macro_category_id: int | None, stamp: str
    ) -> TagSearchResult | None:
        raise NotImplementedError

    def add_subject_exclusions(
        self, terms: Sequence[str], *, source: Literal["HUMAN", "RULE"] = "HUMAN", reason: str | None = None
    ) -> int:
        raise NotImplementedError

    def plan_subject_exclusions(self, terms: Sequence[str]) -> SubjectExclusionPlan:
        raise NotImplementedError

    def apply_subject_exclusions(
        self,
        plan: SubjectExclusionPlan,
        *,
        source: SubjectExclusionSource = "HUMAN",
        reason: str | None = None,
    ) -> SubjectExclusionApplyResult:
        raise NotImplementedError

    def remove_subject_exclusions(self, terms: Sequence[str]) -> SubjectExclusionRemovalResult:
        raise NotImplementedError

    def get_by_id(self, tag_id: int) -> TagIdentity | None:
        raise NotImplementedError

    def get_tag_identities_by_names(self, names: Sequence[str]) -> dict[str, TagIdentity]:
        raise NotImplementedError

    def get_tag_identities_by_ids(self, tag_ids: Sequence[int]) -> dict[int, TagIdentity]:
        raise NotImplementedError

    def get_document_ids_grouped_by_tags(self, tag_ids: Sequence[int]) -> dict[int, list[str]]:
        raise NotImplementedError

    def link_documents_to_tag(self, doc_ids: set[str], target_tag_id: int) -> None:
        raise NotImplementedError

    def delete_tags(self, tag_ids: list[int]) -> int:
        raise NotImplementedError

    def upsert_merge_proposals(self, suggestions: Sequence[TagMergeSuggestion]) -> int:
        raise NotImplementedError

    def decide_merge_proposal(
        self, proposal_id: int, status: str, decided_by: Author | None, note: str | None
    ) -> TagMergeProposalDTO | None:
        raise NotImplementedError

    def apply_merge(
        self,
        plan: MergePlan,
        cluster_fingerprint: str | None = None,
        changed_by: Author | None = None,
        note: str | None = None,
    ) -> MergeResponse:
        raise NotImplementedError

    def apply_merge_batch(
        self, entries: Sequence[MergeBatchEntry], changed_by: Author | None = None, note: str | None = None
    ) -> BatchMergeResponse:
        raise NotImplementedError

    def undo_merge(self, merge_id: int, undone_by: Author | None = None) -> MergeLogEntryDTO:
        raise NotImplementedError

    def count_merge_log(
        self,
        canonical_id: int | None = None,
        changed_by_name: str | None = None,
        include_undone: bool = True,
        term: str | None = None,
    ) -> int:
        raise NotImplementedError

    def list_merge_log(
        self,
        canonical_id: int | None = None,
        changed_by_name: str | None = None,
        include_undone: bool = True,
        term: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[MergeLogEntryDTO]:
        raise NotImplementedError

    def get_merge_log_entry(self, merge_id: int) -> MergeLogEntryDTO | None:
        raise NotImplementedError
