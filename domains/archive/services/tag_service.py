import re
from collections.abc import Sequence
from typing import Literal

from core.logger import logger
from domains.archive.exceptions import InvalidMergeError, InvalidParam
from domains.archive.repository import DocumentRepository
from domains.archive.repository.tag_repo import TagRepository
from domains.archive.schemas import (
    ArchiveTagDTO,
    MergeResponse,
    TagPairSimilarity,
    TagRelevanceCount,
    TagRelevanceIdf,
    TagSimilarity,
)


class TagService:
    """
    Domain service responsible for auditing, sanitizing and unifying
    the taxonomy and tags in the Archive layer.
    """

    def __init__(self, repo: TagRepository, document_repo: DocumentRepository):
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
            self._stopwords = frozenset(word.strip().lower() for word in self.repo.get_stopwords() if word.strip())

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
        names_to_search = [dto.name.strip().lower() for dto in dtos_from_worker]

        # 2. Fetches the mapping from the Repository (Returns something like: {"prefeiruta": 45, "parques": 12})
        synonyms_map = self.repo.get_synonyms_mapping(names_to_search)

        final_ids_for_document = []
        dtos_to_create = []

        # 3. The Business Rule Routing (The fine mesh)
        for dto in dtos_from_worker:
            normalized_name = dto.name.strip().lower()

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

    def save_new_stopwords(self, word_list: list[str]) -> int:
        return self.repo.save_stopwords(word_list)

    def purge_stopwords(self) -> int:
        """
        Scans the tag table and gracefully deletes any tag that exactly
        matches the official stopwords list.
        """

        clean_stopwords = self.repo.get_stopwords()
        if not clean_stopwords:
            return 0

        return self.repo.purge_tags_by_stopwords(clean_stopwords)

    def get_tag_relevance_count(self, limit: int = 30) -> Sequence[TagRelevanceCount]:
        """
        Counts how many times each tag appears associated with a document in the collection.
        """
        results = self.repo.get_relevance_count(limit)
        return [TagRelevanceCount.model_validate(r) for r in results]

    def get_tag_relevance_tfidf(self, limit: int = 30) -> Sequence[TagRelevanceIdf]:
        """
        Calculates the global relevance of tags using the native TF-IDF formula in PostgreSQL.
        Penalizes generic tags that appear throughout the collection and highlights specific terms.
        """
        results = self.repo.get_relevance_tfidf(limit)
        return [TagRelevanceIdf.model_validate(r) for r in results]

    def find_similar_tags(self, target_tag: str, threshold: float = 0.5) -> Sequence[TagSimilarity]:
        """
        Searches for tags with typos or high similarity using the pg_trgm extension.
        """
        if not target_tag:
            raise InvalidParam("O parametro 'target_tag' é obrigatório")

        # Business rule: always search in lowercase
        target_lower = target_tag.strip().lower()
        results = self.repo.find_similar(target_lower, threshold)

        return [TagSimilarity.model_validate(r) for r in results]

    def find_all_similar_tag_pairs(self, threshold: float = 0.65) -> Sequence[TagPairSimilarity]:
        """
        Scans the collection and cross-references all tags with each other to find
        pairs that are very similar (potential duplicates).
        """
        results = self.repo.find_all_similar_pairs(threshold)
        return [TagPairSimilarity.model_validate(r) for r in results]

    def merge(self, canonical_id: int, ids_to_merge: list[int]) -> MergeResponse:
        """
        Orchestrates the merging of tags, normalizing synonyms and delegating persistence to the Repo.
        """
        if not ids_to_merge:
            raise InvalidParam("A lista de tags para mesclar não pode estar vazia.")

        if canonical_id in ids_to_merge:
            raise InvalidMergeError("O ID da tag canônica não pode estar na lista de exclusão.")

        canonical_exists = self.repo.get_by_id(canonical_id)
        if not canonical_exists:
            raise InvalidParam(f"A tag canônica informada (ID {canonical_id}) não existe no acervo.")

        # 1. Fetches the names of the dead ones and normalizes them so the Worker can find them later
        dead_tags = self.repo.get_by_ids(ids_to_merge)
        synonym_names = [t.name.strip().lower() for t in dead_tags]

        # 2. Transfers the links
        raw_docs = self.repo.get_document_ids_by_tags(ids_to_merge)
        unique_docs = set(raw_docs)

        if unique_docs:
            self.repo.link_documents_to_tag(unique_docs, canonical_id)

        # 3. Saves Synonyms
        if synonym_names:
            synonyms_data = [
                {
                    "synonym_name": name,
                    "category": "TAG",
                    "canonical_tag_id": canonical_id,
                    "canonical_entity_id": None,
                }
                for name in synonym_names
            ]
            self.repo.create_synonyms(synonyms_data)

        # 4. Deletes the garbage
        tags_deleted = self.repo.delete_tags(ids_to_merge)

        return MergeResponse(documents_updated=len(unique_docs), tags_deleted=tags_deleted)

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

    # TODO Think about how to do this. Remove the known entities from the tags or not. Tags need to be classified into subjects.
    def purge_entities_from_tags(self):
        pass
