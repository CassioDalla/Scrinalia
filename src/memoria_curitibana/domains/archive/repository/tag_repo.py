from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import (
    CursorResult,
    Float,
    Text,
    case,
    column,
    delete,
    desc,
    func,
    select,
    text,
    update,
    values,
)
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, aliased

from memoria_curitibana.domains.archive.domain.normalization import (
    normalize_stopword,
    normalize_synonym,
    normalize_tag,
    singular_candidates,
)
from memoria_curitibana.domains.archive.domain.tag_merge import (
    REVIEW_CATEGORY_WOULD_BE_LOST,
    REVIEW_MEMBER_IS_SYNONYM,
    REVIEW_MEMBER_WITH_DIGITS,
    REVIEW_WEAK_MEMBER,
    WEAK_MEMBER_SIMILARITY,
    cluster_fingerprint,
    has_digits,
)
from memoria_curitibana.domains.archive.domain.vocabulary import classifier_labels
from memoria_curitibana.domains.archive.exceptions import (
    InvalidParam,
    MergeAlreadyUndoneError,
    MergeLogNotFoundError,
)
from memoria_curitibana.domains.archive.models import (
    ArchiveDocument,
    ArchiveDocumentTag,
    ArchiveMacroCategory,
    ArchiveTag,
    ArchiveTagMergeProposal,
    ArchiveTaxonomyMergeLog,
    DomainStopwords,
    DomainSynonyms,
    StopwordsScope,
)
from memoria_curitibana.domains.archive.schemas import (
    ArchiveMacroCategoryEntityDTO,
    ArchiveTagDTO,
    BatchMergeResponse,
    MergeBatchApplied,
    MergeBatchEntry,
    MergeBatchFailure,
    MergeLogEntryDTO,
    MergePlan,
    MergeResponse,
    SynonymCommand,
    TagCount,
    TagIdentity,
    TagLinkCommand,
    TagMergeImpact,
    TagMergeMember,
    TagMergeProposalDTO,
    TagMergeSuggestion,
    TagPairSimilarity,
    TagRelevanceCount,
    TagRelevanceIdf,
    TagSimilarity,
)


class TagRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def fetch_tags_for_clustering(self) -> list[str]:
        """Fetches only unique tags that do not yet have a Macro Category."""
        stmt = select(ArchiveTag.name).where(ArchiveTag.macro_category_id.is_(None)).distinct()
        results = self.db.scalars(stmt).all()

        texts = [t for t in results if t and not t.replace(".", "").isdigit()]
        return texts

    def get_synonyms_mapping(self, words: list[str]) -> dict[str, int]:
        """
        Checks in the database whether any of the provided words is a known synonym.
        Returns a dictionary mapping: { 'synonym_name': ID_of_Canonical_Tag }
        """
        if not words:
            return {}

        words_clean = [normalize_tag(w) for w in words]

        stmt = select(DomainSynonyms.synonym_name, DomainSynonyms.canonical_tag_id).where(
            DomainSynonyms.category == "TAG", DomainSynonyms.synonym_name.in_(words_clean)
        )

        results = self.db.execute(stmt).all()
        return {row.synonym_name: row.canonical_tag_id for row in results}

    def get_or_create_tags(self, tags_list: list[ArchiveTagDTO]) -> list[int]:
        """
        Manages the dimension of tags and taxonomies of mDeBERTa.
        Ensures that identical terms (in lowercase) share the same ID in the database.
        """

        if not tags_list:
            return []

        insert_data = []
        names_to_search = []

        for t in tags_list:
            name_clean = normalize_tag(t.name)
            names_to_search.append(name_clean)
            insert_data.append(
                {
                    "name": name_clean,
                    "macro_category_id": t.macro_category_id,
                    "ai_confidence_score": t.ai_confidence_score,
                }
            )

        # 2. Performs the mass INSERT ignoring tags that already exist (thanks to the unique index on the 'name' column)
        stmt_insert = insert(ArchiveTag).values(insert_data).on_conflict_do_nothing(index_elements=["name"])
        self.db.execute(stmt_insert)

        # 3. In a SINGLE select, fetches all IDs (both the newly created and the already existing ones)
        stmt_select = select(ArchiveTag.tag_id).where(ArchiveTag.name.in_(names_to_search))

        return list(self.db.scalars(stmt_select).all())

    def save_stopwords(self, words_list: list[str]) -> int:
        """
        Inserts a list of words into the stopwords table in batch.
        Returns the exact number of new stopwords inserted.
        """
        if not words_list:
            return 0

        clean_words = [{"word": normalize_stopword(w)} for w in words_list if w.strip()]

        if not clean_words:
            return 0

        stmt = insert(DomainStopwords).values(clean_words).on_conflict_do_nothing()

        result = cast(CursorResult, self.db.execute(stmt))
        return result.rowcount

    def get_stopwords(self) -> set[str]:
        """
        Retrieves the stopwords that apply to the TAG axis, in lowercase.

        Only ``TAG`` and ``ALL`` scopes are returned. An ``ENTITY``-scoped word is a
        ban on NER extraction, not a statement about the subject axis, and reading it
        here made the curation purge delete tags that the curator had deliberately
        kept — the exact opposite of the recorded decision.

        Returns:
            set[str]: Set containing the stopwords in lowercase letters.
        """
        stmt = select(DomainStopwords.word).where(
            DomainStopwords.word_scope.in_([StopwordsScope.TAG, StopwordsScope.ALL])
        )
        results = self.db.scalars(stmt).all()
        return set(results)

    def get_macro_categories(self, only_active: bool = False) -> list[ArchiveMacroCategoryEntityDTO]:
        """
        Lists the macro categories of the collection.

        Args:
            only_active: When ``True``, hides the categories a curator deactivated.
        """

        stmt = select(
            ArchiveMacroCategory.category_id,
            ArchiveMacroCategory.name,
            ArchiveMacroCategory.description,
            ArchiveMacroCategory.classifier_label,
            ArchiveMacroCategory.is_active,
        )

        if only_active:
            stmt = stmt.where(ArchiveMacroCategory.is_active.is_(True))

        stmt = stmt.order_by(ArchiveMacroCategory.name)

        results = self.db.execute(stmt).mappings().all()
        return [ArchiveMacroCategoryEntityDTO.model_validate(r) for r in results]

    def get_active_macro_categories(self) -> dict[str, int]:
        """
        Builds the label -> id map the classification engine reads.

        The label is ``classifier_label`` when the curator wrote one and the bare ``name``
        otherwise (see :func:`domain.vocabulary.classifier_labels`). The **description is
        never used**: concatenating it (``"Name: description"``) makes the model
        progressively lose the entailment as the label grows, until it collapses every input
        onto a single drawer — measured on ``mDeBERTa-v3-base-mnli-xnli``, ``"epidemia de
        dengue"`` is correctly labelled "Saúde" (0.99) with bare names but flips to
        "Urbanismo" once the descriptions are appended, with 0.98 confidence on the wrong
        label, so a threshold cannot catch it. The description stays in the schema as
        curator-facing documentation and is deliberately kept out of the prompt.

        Returns:
            dict[str, int]: e.g. ``{"Urbanismo e Arquitetura": 3}``.
        """
        stmt = select(
            ArchiveMacroCategory.category_id,
            ArchiveMacroCategory.name,
            ArchiveMacroCategory.classifier_label,
        ).where(ArchiveMacroCategory.is_active.is_(True))

        rows = self.db.execute(stmt).all()
        categories = {name: category_id for category_id, name, _label in rows}
        labels = {name: label for _category_id, name, label in rows}
        return classifier_labels(categories, labels)

    def create_macro_category(
        self, name: str, description: str | None, classifier_label: str | None = None
    ) -> ArchiveMacroCategoryEntityDTO:
        """Inserts an official macro category. Uniqueness of ``name`` is enforced by the schema."""
        category = ArchiveMacroCategory(name=name, description=description, classifier_label=classifier_label)
        self.db.add(category)
        self.db.flush()
        return ArchiveMacroCategoryEntityDTO.model_validate(category)

    def update_macro_category(self, category_id: int, changes: dict[str, Any]) -> ArchiveMacroCategoryEntityDTO | None:
        """Applies a partial update. Returns ``None`` when the category does not exist."""
        category = self.db.get(ArchiveMacroCategory, category_id)
        if category is None:
            return None

        for field, value in changes.items():
            setattr(category, field, value)

        self.db.flush()
        return ArchiveMacroCategoryEntityDTO.model_validate(category)

    def purge_tags_by_stopwords(self, stopwords: set[str]) -> int:
        """Mass deletes all tags that match the stopwords list."""
        stmt = delete(ArchiveTag).where(func.lower(ArchiveTag.name).in_(stopwords))
        result = self.db.execute(stmt)
        return cast(CursorResult, result).rowcount

    def get_relevance_count(self, limit: int) -> Sequence[TagRelevanceCount]:
        stmt = (
            select(ArchiveTag.name, func.count(ArchiveDocumentTag.description_id).label("total_usage"))
            .join(ArchiveDocumentTag, ArchiveTag.tag_id == ArchiveDocumentTag.tag_id)
            .group_by(ArchiveTag.tag_id, ArchiveTag.name)
            .order_by(text("total_usage DESC"))
            .limit(limit)
        )
        return [TagRelevanceCount.model_validate(row) for row in self.db.execute(stmt).all()]

    def get_relevance_tfidf(self, limit: int) -> Sequence[TagRelevanceIdf]:
        total_docs = self.db.scalar(select(func.count(ArchiveDocument.description_id)))
        if not total_docs or total_docs == 0:
            return []

        df = func.count(ArchiveDocumentTag.description_id)
        idf = func.ln(total_docs / func.cast(df, Float))
        tfidf_score = df * idf

        stmt = (
            select(ArchiveTag.name, df.label("frequency"), idf.label("weight_idf"), tfidf_score.label("score_tfidf"))
            .join(ArchiveDocumentTag, ArchiveTag.tag_id == ArchiveDocumentTag.tag_id)
            .group_by(ArchiveTag.tag_id, ArchiveTag.name)
            .order_by(desc("score_tfidf"))
            .limit(limit)
        )
        return [TagRelevanceIdf.model_validate(row) for row in self.db.execute(stmt).all()]

    def find_similar(self, target_lower: str, threshold: float) -> Sequence[TagSimilarity]:
        self.db.execute(text("SET LOCAL pg_trgm.similarity_threshold = :threshold"), {"threshold": threshold})
        similarity = func.similarity(ArchiveTag.name, target_lower)
        stmt = (
            select(ArchiveTag.tag_id, ArchiveTag.name, similarity.label("similarity"))
            .where(ArchiveTag.name.op("%")(target_lower))
            .where(func.lower(ArchiveTag.name) != target_lower)
            .order_by(desc("similarity"))
            .limit(15)
        )
        return [TagSimilarity.model_validate(row) for row in self.db.execute(stmt).all()]

    def find_all_similar_pairs(self, threshold: float) -> Sequence[TagPairSimilarity]:
        self.db.execute(text("SET LOCAL pg_trgm.similarity_threshold = :threshold"), {"threshold": threshold})
        Tag1 = aliased(ArchiveTag)
        Tag2 = aliased(ArchiveTag)
        similarity = func.similarity(Tag1.name, Tag2.name)
        stmt = (
            select(
                Tag1.tag_id.label("id_1"),
                Tag1.name.label("name_1"),
                Tag2.tag_id.label("id_2"),
                Tag2.name.label("name_2"),
                similarity.label("sim_score"),
            )
            # The Join ensuring that only unique combinations are tested and it ignores itself
            .join(Tag2, Tag1.tag_id < Tag2.tag_id)
            # Only compares tags that have up to 3 letters of difference in length
            .where(func.abs(func.length(Tag1.name) - func.length(Tag2.name)) <= 3)
            .where(Tag1.name.op("%")(Tag2.name))
            .order_by(desc("sim_score"), Tag1.name)
        )
        return [TagPairSimilarity.model_validate(row) for row in self.db.execute(stmt).all()]

    def get_all_tags_with_counts(self) -> Sequence[TagCount]:
        """
        Every tag with how many documents link to it, and its own classification.

        One grouped join instead of a count per cluster: the merge suggestions compare the
        whole taxonomy at once. The macro category and the confidence score travel with the
        row because ``CATEGORY_WOULD_BE_LOST`` is a warning the curator must see before
        approving a merge, and asking per tag would be an N+1.
        """
        stmt = (
            select(
                ArchiveTag.tag_id,
                ArchiveTag.name,
                ArchiveTag.macro_category_id,
                ArchiveTag.ai_confidence_score,
                func.count(ArchiveDocumentTag.description_id).label("document_count"),
            )
            .outerjoin(ArchiveDocumentTag, ArchiveDocumentTag.tag_id == ArchiveTag.tag_id)
            .group_by(
                ArchiveTag.tag_id,
                ArchiveTag.name,
                ArchiveTag.macro_category_id,
                ArchiveTag.ai_confidence_score,
            )
        )
        return [TagCount.model_validate(row) for row in self.db.execute(stmt).all()]

    def find_merge_suggestions(self, threshold: float = 0.65, limit: int = 50) -> list[TagMergeSuggestion]:
        """
        Groups tags that probably mean the same thing, without merging anything.

        Two independent pieces of evidence, because each one alone misses the measured
        cases: ``pg_trgm`` catches typos ("prefeiruta") and the plural rules catch
        "livros"/"livro", which are far apart for a trigram. Both only ever *propose*:
        the archivist approves through the existing merge route.

        The canonical member is the tag attached to the most documents, so approving the
        suggestion keeps the spelling the collection already uses the most.
        """
        catalog = {row.tag_id: row for row in self.get_all_tags_with_counts()}
        if not catalog:
            return []

        by_name = {row.name: row.tag_id for row in catalog.values()}
        parent: dict[int, int] = {tag_id: tag_id for tag_id in catalog}
        reasons: dict[frozenset[int], set[str]] = {}

        def find(tag_id: int) -> int:
            while parent[tag_id] != tag_id:
                parent[tag_id] = parent[parent[tag_id]]
                tag_id = parent[tag_id]
            return tag_id

        def union(left: int, right: int, reason: str) -> None:
            root_left, root_right = find(left), find(right)
            if root_left != root_right:
                parent[root_right] = root_left
            reasons.setdefault(frozenset((left, right)), set()).add(reason)

        for pair in self.find_all_similar_pairs(threshold):
            union(pair.id_1, pair.id_2, "TRIGRAM")

        for row in catalog.values():
            for candidate in singular_candidates(row.name):
                singular_id = by_name.get(candidate)
                if singular_id is not None and singular_id != row.tag_id:
                    union(row.tag_id, singular_id, "PLURAL")

        clusters: dict[int, list[int]] = {}
        for tag_id in catalog:
            clusters.setdefault(find(tag_id), []).append(tag_id)

        # The union of documents, not the sum of the members: a document linked to both
        # "livro" and "livros" is one document, and summing would inflate the evidence.
        grouped_members = [members for members in clusters.values() if len(members) > 1]
        documents_by_tag: dict[int, set[str]] = defaultdict(set)
        if grouped_members:
            rows = self.db.execute(
                select(ArchiveDocumentTag.tag_id, ArchiveDocumentTag.description_id).where(
                    ArchiveDocumentTag.tag_id.in_([tag_id for members in grouped_members for tag_id in members])
                )
            ).all()
            for tag_id, description_id in rows:
                documents_by_tag[tag_id].add(description_id)

        suggestions: list[TagMergeSuggestion] = []
        for members in grouped_members:
            ordered = sorted(members, key=lambda tag_id: (-catalog[tag_id].document_count, catalog[tag_id].name))
            canonical = catalog[ordered[0]]
            cluster_reasons = {
                reason
                for index, member in enumerate(members)
                for other in members[index + 1 :]
                for reason in reasons.get(frozenset((member, other)), set())
            }
            suggestions.append(
                TagMergeSuggestion(
                    canonical_id=canonical.tag_id,
                    canonical_name=canonical.name,
                    total_documents=len(set().union(*(documents_by_tag[tag_id] for tag_id in members))),
                    reason=cluster_reasons.pop() if len(cluster_reasons) == 1 else "MIXED",
                    members=[
                        TagMergeMember(
                            tag_id=catalog[tag_id].tag_id,
                            name=catalog[tag_id].name,
                            document_count=catalog[tag_id].document_count,
                        )
                        for tag_id in ordered
                    ],
                )
            )

        suggestions.sort(key=lambda suggestion: (-suggestion.total_documents, suggestion.canonical_name))
        return suggestions[:limit]

    # ==========================================
    # MERGE PROPOSALS (the curation catalog)
    # ==========================================

    def get_tag_synonym_names(self) -> set[str]:
        """Every spelling already redirected to a canonical tag."""
        stmt = select(DomainSynonyms.synonym_name).where(DomainSynonyms.category == "TAG")
        return set(self.db.scalars(stmt).all())

    def get_synonym_names_pointing_to(self, tag_ids: Sequence[int]) -> list[str]:
        """The spellings that would be orphaned by deleting ``tag_ids`` (the cascade target)."""
        if not tag_ids:
            return []

        stmt = select(DomainSynonyms.synonym_name).where(
            DomainSynonyms.category == "TAG", DomainSynonyms.canonical_tag_id.in_(list(tag_ids))
        )
        return list(self.db.scalars(stmt).all())

    def _find_weak_members(self, pairs: Sequence[tuple[str, str]]) -> set[str]:
        """
        Members whose similarity to their canonical is below the warning threshold.

        One query over a ``VALUES`` list instead of a round trip per member: the flag is
        evidence for the curator, and N+1 in a suggestion run over the whole catalog would
        be paid on every call.
        """
        if not pairs:
            return set()

        candidate = values(column("canonical", Text), column("member", Text), name="candidate").data(list(pairs))
        score = func.similarity(candidate.c.canonical, candidate.c.member)
        stmt = select(candidate.c.member).where(score < WEAK_MEMBER_SIMILARITY)
        return set(self.db.scalars(stmt).all())

    def upsert_merge_proposals(self, suggestions: Sequence[TagMergeSuggestion]) -> int:
        """
        Persists the suggested clusters, refreshing evidence and never a human decision.

        The ``WHERE`` on the conflict target is the whole point (same rule as the excerpt
        catalog): re-running the suggester refreshes a cluster that is still pending and
        leaves an approved or rejected one exactly as the archivist left it. Returns how many
        rows were actually written, so a re-run over decided clusters reports zero.
        """
        if not suggestions:
            return 0

        catalog = {row.tag_id: row for row in self.get_all_tags_with_counts()}
        synonym_names = self.get_tag_synonym_names()
        weak_members = self._find_weak_members(
            [
                (suggestion.canonical_name, member.name)
                for suggestion in suggestions
                for member in suggestion.members[1:]
            ]
        )

        rows = []
        for suggestion in suggestions:
            absorbed = suggestion.members[1:]
            canonical = catalog.get(suggestion.canonical_id)
            canonical_is_orphan = canonical is None or canonical.macro_category_id is None
            loses_category = canonical_is_orphan and any(
                catalog.get(member.tag_id) is not None and catalog[member.tag_id].macro_category_id is not None
                for member in absorbed
            )

            flags: list[str] = []
            if any(has_digits(member.name) for member in absorbed):
                flags.append(REVIEW_MEMBER_WITH_DIGITS)
            if any(member.name in weak_members for member in absorbed):
                flags.append(REVIEW_WEAK_MEMBER)
            if loses_category:
                flags.append(REVIEW_CATEGORY_WOULD_BE_LOST)
            if any(member.name in synonym_names for member in absorbed):
                flags.append(REVIEW_MEMBER_IS_SYNONYM)

            rows.append(
                {
                    "fingerprint": cluster_fingerprint(
                        suggestion.canonical_name, [member.name for member in suggestion.members]
                    ),
                    "canonical_id": suggestion.canonical_id,
                    "canonical_name": suggestion.canonical_name,
                    "members": [
                        {"tag_id": member.tag_id, "name": member.name, "document_count": member.document_count}
                        for member in suggestion.members
                    ],
                    "reason": suggestion.reason,
                    "review_flags": flags,
                    "total_documents": suggestion.total_documents,
                    "status": "SUGGESTED",
                }
            )

        base = insert(ArchiveTagMergeProposal)
        stmt = (
            base.values(rows)
            .on_conflict_do_update(
                index_elements=["fingerprint"],
                set_={
                    "canonical_id": base.excluded.canonical_id,
                    "canonical_name": base.excluded.canonical_name,
                    "members": base.excluded.members,
                    "reason": base.excluded.reason,
                    "review_flags": base.excluded.review_flags,
                    "total_documents": base.excluded.total_documents,
                    "updated_at": func.now(),
                },
                where=(ArchiveTagMergeProposal.status == "SUGGESTED"),
            )
            .returning(ArchiveTagMergeProposal.proposal_id)
        )
        return len(self.db.execute(stmt).all())

    def _merge_proposal_filters(
        self,
        status: str | None,
        reason: str | None,
        min_documents: int,
        flagged_only: bool,
    ) -> list[Any]:
        filters: list[Any] = []
        if status is not None:
            filters.append(ArchiveTagMergeProposal.status == status)
        if reason is not None:
            filters.append(ArchiveTagMergeProposal.reason == reason)
        if min_documents:
            filters.append(ArchiveTagMergeProposal.total_documents >= min_documents)
        if flagged_only:
            # ``array_length`` is NULL for the empty array, so an unflagged row never passes.
            filters.append(func.array_length(ArchiveTagMergeProposal.review_flags, 1) > 0)
        return filters

    def count_merge_proposals(
        self,
        status: str | None = None,
        reason: str | None = None,
        min_documents: int = 0,
        flagged_only: bool = False,
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(ArchiveTagMergeProposal)
            .where(*self._merge_proposal_filters(status, reason, min_documents, flagged_only))
        )
        return self.db.scalar(stmt) or 0

    def list_merge_proposals(
        self,
        status: str | None = None,
        reason: str | None = None,
        min_documents: int = 0,
        flagged_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[TagMergeProposalDTO]:
        """
        One page of proposals, pending work first.

        The order is not cosmetic: with hundreds of clusters the archivist walks the list, so
        what is still undecided comes before what was already decided, and inside each group
        the clusters that move the most documents come first.
        """
        pending_first = case(
            (ArchiveTagMergeProposal.status == "SUGGESTED", 0),
            (ArchiveTagMergeProposal.status == "APPROVED", 1),
            else_=2,
        )
        stmt = (
            select(ArchiveTagMergeProposal)
            .where(*self._merge_proposal_filters(status, reason, min_documents, flagged_only))
            .order_by(
                pending_first,
                ArchiveTagMergeProposal.total_documents.desc(),
                ArchiveTagMergeProposal.canonical_name,
            )
            .limit(limit)
            .offset(offset)
        )
        return [TagMergeProposalDTO.model_validate(row) for row in self.db.scalars(stmt).all()]

    def get_merge_proposal(self, proposal_id: int) -> TagMergeProposalDTO | None:
        row = self.db.get(ArchiveTagMergeProposal, proposal_id)
        return TagMergeProposalDTO.model_validate(row) if row else None

    def decide_merge_proposal(
        self,
        proposal_id: int,
        status: str,
        decided_by: str | None,
        note: str | None,
    ) -> TagMergeProposalDTO | None:
        """
        Records the human verdict. Approving states the intent; it does not merge anything.

        Keeping decision and execution apart is what lets the merge be applied later with the
        reversible ledger, instead of turning a click in a listing into an irreversible write.
        """
        row = self.db.get(ArchiveTagMergeProposal, proposal_id)
        if row is None:
            return None

        row.status = status
        row.decided_by = decided_by
        row.decided_at = datetime.now(UTC)
        row.decision_note = note
        self.db.flush()
        return TagMergeProposalDTO.model_validate(row)

    # --- Auxiliary Methods for the Tag Merge ---

    def plan_merge(self, canonical_id: int, ids_to_merge: Sequence[int]) -> MergePlan:
        """
        Everything the merge would change, computed without writing anything.

        Single definition of the operation: the dry-run returns this plan (trimmed) and
        ``apply_merge`` executes it, so the preview cannot promise something different from
        what the merge does. Same reasoning as the AI text composition living in one SQL
        expression instead of two implementations.
        """
        catalog = {row.tag_id: row for row in self.get_all_tags_with_counts()}
        canonical = catalog.get(canonical_id)
        if canonical is None:
            raise InvalidParam(f"A tag canônica informada (ID {canonical_id}) não existe no acervo.")

        dead_ids = [tag_id for tag_id in dict.fromkeys(ids_to_merge) if tag_id != canonical_id and tag_id in catalog]
        impacted = [
            TagMergeImpact(
                tag_id=catalog[tag_id].tag_id,
                name=catalog[tag_id].name,
                document_count=catalog[tag_id].document_count,
                macro_category_id=catalog[tag_id].macro_category_id,
                ai_confidence_score=catalog[tag_id].ai_confidence_score,
            )
            for tag_id in dead_ids
        ]

        documents_by_tag = self.get_document_ids_grouped_by_tags(dead_ids)
        document_ids = sorted({document_id for ids in documents_by_tag.values() for document_id in ids})
        synonym_names = [normalize_tag(member.name) for member in impacted]
        repointed = sorted(set(self.get_synonym_names_pointing_to(dead_ids)))

        weak_members = self._find_weak_members([(canonical.name, member.name) for member in impacted])
        category_would_be_lost = canonical.macro_category_id is None and any(
            member.macro_category_id is not None for member in impacted
        )

        flags: list[str] = []
        if any(has_digits(member.name) for member in impacted):
            flags.append(REVIEW_MEMBER_WITH_DIGITS)
        if weak_members:
            flags.append(REVIEW_WEAK_MEMBER)
        if category_would_be_lost:
            flags.append(REVIEW_CATEGORY_WOULD_BE_LOST)
        if set(synonym_names) & self.get_tag_synonym_names():
            flags.append(REVIEW_MEMBER_IS_SYNONYM)

        return MergePlan(
            canonical_id=canonical_id,
            canonical_name=canonical.name,
            canonical_document_count=canonical.document_count,
            ids_to_merge=dead_ids,
            impacted=impacted,
            document_ids=document_ids,
            documents_by_tag=documents_by_tag,
            synonym_names=synonym_names,
            repointed_synonyms=repointed,
            review_flags=flags,
            category_would_be_lost=category_would_be_lost,
        )

    def apply_merge(
        self,
        plan: MergePlan,
        cluster_fingerprint: str | None = None,
        changed_by: str | None = None,
        note: str | None = None,
    ) -> MergeResponse:
        """
        Executes exactly what ``plan_merge`` described, after writing the undo ledger.

        The order matters twice. The ledger is written **before** anything changes, because
        what it snapshots (the spelling state) is exactly what the merge is about to modify.
        And the spellings already absorbed by the tags being deleted are moved to the canonical
        *before* the delete, because the synonym FK cascades and deleting first would forget
        the earlier curation (the Fase 0 fix).
        """
        merge_ids = self.write_merge_log(
            plan, cluster_fingerprint=cluster_fingerprint, changed_by=changed_by, note=note
        )

        if plan.document_ids:
            self.link_documents_to_tag(set(plan.document_ids), plan.canonical_id)

        self.repoint_synonyms(list(plan.ids_to_merge), plan.canonical_id)

        if plan.synonym_names:
            self.create_synonyms(
                [
                    SynonymCommand(
                        synonym_name=name,
                        category="TAG",
                        canonical_tag_id=plan.canonical_id,
                        canonical_entity_id=None,
                    )
                    for name in plan.synonym_names
                ]
            )

        tags_deleted = self.delete_tags(list(plan.ids_to_merge))
        return MergeResponse(documents_updated=len(plan.document_ids), tags_deleted=tags_deleted, merge_ids=merge_ids)

    # --- The ledger: what a merge would have to restore ---

    def write_merge_log(
        self,
        plan: MergePlan,
        cluster_fingerprint: str | None = None,
        changed_by: str | None = None,
        note: str | None = None,
    ) -> list[int]:
        """
        Snapshots every tag the plan absorbs. Returns the ledger ids, oldest first.

        Reads the current rows instead of trusting the plan for the fields the dry-run does not
        carry (``execution_log``, ``created_at``) and captures the spelling state before the
        merge touches it — an undo that guesses either of those is not a lossless undo.
        """
        if not plan.ids_to_merge:
            return []

        tags = {
            tag.tag_id: tag
            for tag in self.db.scalars(select(ArchiveTag).where(ArchiveTag.tag_id.in_(plan.ids_to_merge))).all()
        }
        spellings_of_dead = self._synonym_names_by_canonical(plan.ids_to_merge)
        mapped_spellings = self._synonym_targets_by_name(plan.synonym_names)
        # Documents that already carried the canonical: the merge does not create those links,
        # so undo must not remove them either.
        already_canonical = set(self.get_document_ids_grouped_by_tags([plan.canonical_id]).get(plan.canonical_id, []))

        rows = []
        for tag_id in plan.ids_to_merge:
            tag = tags.get(tag_id)
            if tag is None:
                continue

            name = normalize_tag(tag.name)
            previous_target = mapped_spellings.get(name)
            documents = plan.documents_by_tag.get(tag_id, [])
            rows.append(
                {
                    "cluster_fingerprint": cluster_fingerprint,
                    "canonical_id": plan.canonical_id,
                    "canonical_name": plan.canonical_name,
                    "absorbed_tag_id": tag.tag_id,
                    "absorbed_name": name,
                    "absorbed_snapshot": {
                        "name": tag.name,
                        "macro_category_id": tag.macro_category_id,
                        "ai_confidence_score": tag.ai_confidence_score,
                        "execution_log": tag.execution_log,
                        "created_at": tag.created_at.isoformat() if tag.created_at else None,
                    },
                    # Only for the restore path: the live links are the ones in the plan.
                    "document_ids": documents,
                    "created_link_ids": [doc for doc in documents if doc not in already_canonical],
                    "synonym_created": previous_target is None,
                    "synonym_previous_tag_id": previous_target,
                    "repointed_synonym_names": spellings_of_dead.get(tag_id, []),
                    "changed_by": changed_by,
                    "note": note,
                }
            )

        if not rows:
            return []

        stmt = insert(ArchiveTaxonomyMergeLog).values(rows).returning(ArchiveTaxonomyMergeLog.merge_id)
        return list(self.db.scalars(stmt).all())

    def _synonym_names_by_canonical(self, tag_ids: Sequence[int]) -> dict[int, list[str]]:
        """Spellings each tag absorbs today, keyed by the tag they point at."""
        if not tag_ids:
            return {}

        stmt = select(DomainSynonyms.canonical_tag_id, DomainSynonyms.synonym_name).where(
            DomainSynonyms.category == "TAG", DomainSynonyms.canonical_tag_id.in_(list(tag_ids))
        )
        grouped: dict[int, list[str]] = defaultdict(list)
        for canonical_tag_id, synonym_name in self.db.execute(stmt).all():
            if canonical_tag_id is not None:
                grouped[canonical_tag_id].append(synonym_name)
        return grouped

    def _synonym_targets_by_name(self, names: Sequence[str]) -> dict[str, int]:
        """Where each spelling points today, so the undo can restore (or drop) that mapping."""
        if not names:
            return {}

        stmt = select(DomainSynonyms.synonym_name, DomainSynonyms.canonical_tag_id).where(
            DomainSynonyms.category == "TAG", DomainSynonyms.synonym_name.in_(list(names))
        )
        return {
            synonym_name: canonical_tag_id
            for synonym_name, canonical_tag_id in self.db.execute(stmt).all()
            if canonical_tag_id is not None
        }

    def undo_merge(self, merge_id: int, undone_by: str | None = None) -> MergeLogEntryDTO:
        """
        Reverses one merge: restores the tag, its links, its classification and its spellings.

        Exact by construction — the id and the row come from the snapshot, the links from the
        per-tag list, and the spelling state from what was captured before the merge. Only
        documents that still exist are re-linked: a document deleted after the merge must not
        make the undo impossible.
        """
        row = self.db.get(ArchiveTaxonomyMergeLog, merge_id)
        if row is None:
            raise MergeLogNotFoundError(f"Registro de mesclagem {merge_id} não encontrado no ledger.")
        if row.undone_at is not None:
            raise MergeAlreadyUndoneError(
                f"A mesclagem {merge_id} já foi desfeita em {row.undone_at:%Y-%m-%d %H:%M:%S}."
            )

        snapshot = row.absorbed_snapshot or {}
        restored = ArchiveTag(
            tag_id=row.absorbed_tag_id,
            name=snapshot.get("name") or row.absorbed_name,
            macro_category_id=snapshot.get("macro_category_id"),
            ai_confidence_score=snapshot.get("ai_confidence_score"),
            execution_log=snapshot.get("execution_log"),
        )
        created_at = snapshot.get("created_at")
        if created_at:
            restored.created_at = datetime.fromisoformat(created_at)
        self.db.add(restored)
        self.db.flush()

        # The sequence already allocated this id once, so re-using it cannot collide with the
        # next insert (unlike a hand-written seed, which is the known pitfall with explicit ids).
        self._remove_created_links(row)
        self._relink_documents(row.absorbed_tag_id, row.document_ids or [])
        self._restore_spellings(row)

        row.undone_at = datetime.now(UTC)
        row.undone_by = undone_by
        self.db.flush()
        return self._to_merge_log_dto(row)

    def _relink_documents(self, tag_id: int, document_ids: Sequence[str]) -> int:
        """Re-links the recorded documents that still exist, ignoring the ones that do not."""
        if not document_ids:
            return 0

        existing = self.db.scalars(
            select(ArchiveDocument.description_id).where(ArchiveDocument.description_id.in_(list(document_ids)))
        ).all()
        if existing:
            self.link_documents_to_tag(set(existing), tag_id)
        return len(existing)

    def _remove_created_links(self, row: ArchiveTaxonomyMergeLog) -> int:
        """
        Drops the canonical links the merge created, so undo restores the pre-merge state.

        Only the recorded subset: a document that already carried the canonical before the
        merge keeps it, and a link somebody added afterwards is not touched because it is not
        in the ledger.
        """
        created = row.created_link_ids or []
        if not created or row.canonical_id is None:
            return 0

        stmt = delete(ArchiveDocumentTag).where(
            ArchiveDocumentTag.tag_id == row.canonical_id,
            ArchiveDocumentTag.description_id.in_(list(created)),
        )
        return cast(CursorResult, self.db.execute(stmt)).rowcount

    def _restore_spellings(self, row: ArchiveTaxonomyMergeLog) -> None:
        """
        Puts the spelling state back the way it was before the merge.

        Three cases, all captured at merge time: the spelling equal to the absorbed name was
        created by the merge (drop it), it already existed (point it back), and spellings that
        pointed at the absorbed tag were moved to the canonical (move them back). A mapping
        someone changed later is left alone — the undo restores this merge, not the next one.
        """
        created_synonym = self.db.scalars(
            select(DomainSynonyms).where(
                DomainSynonyms.category == "TAG",
                DomainSynonyms.synonym_name == row.absorbed_name,
            )
        ).one_or_none()

        if created_synonym is not None:
            if row.synonym_created and created_synonym.canonical_tag_id == row.canonical_id:
                self.db.delete(created_synonym)
            elif not row.synonym_created and created_synonym.canonical_tag_id == row.canonical_id:
                created_synonym.canonical_tag_id = row.synonym_previous_tag_id
            elif row.synonym_created and created_synonym.canonical_tag_id != row.canonical_id:
                # Somebody re-pointed it after the merge: not this undo's business.
                pass

        if row.repointed_synonym_names:
            self.db.execute(
                update(DomainSynonyms)
                .where(
                    DomainSynonyms.category == "TAG",
                    DomainSynonyms.canonical_tag_id == row.canonical_id,
                    DomainSynonyms.synonym_name.in_(row.repointed_synonym_names),
                )
                .values(canonical_tag_id=row.absorbed_tag_id)
            )

    def apply_merge_batch(
        self,
        entries: Sequence[MergeBatchEntry],
        changed_by: str | None = None,
        note: str | None = None,
    ) -> BatchMergeResponse:
        """
        Applies several clusters, isolating each one in a SAVEPOINT.

        One bad cluster must not roll back the good ones (the archivist sees exactly what
        failed and retries it), while the request still ends in a single commit owned by the
        unit of work — so a process crash leaves nothing half-applied either.
        """
        applied: list[MergeBatchApplied] = []
        failed: list[MergeBatchFailure] = []

        for entry in entries:
            try:
                with self.db.begin_nested():
                    response = self.apply_merge(
                        entry.plan,
                        cluster_fingerprint=entry.cluster_fingerprint,
                        changed_by=changed_by,
                        note=note,
                    )
            except Exception as exc:
                failed.append(MergeBatchFailure(proposal_id=entry.proposal_id, error=str(exc)))
            else:
                applied.append(
                    MergeBatchApplied(
                        proposal_id=entry.proposal_id,
                        merge_ids=response.merge_ids,
                        documents_updated=response.documents_updated,
                        tags_deleted=response.tags_deleted,
                    )
                )

        return BatchMergeResponse(applied=applied, failed=failed)

    def _tag_merge_log_filters(
        self, canonical_id: int | None, changed_by: str | None, include_undone: bool
    ) -> list[Any]:
        filters: list[Any] = []
        if canonical_id is not None:
            filters.append(ArchiveTaxonomyMergeLog.canonical_id == canonical_id)
        if changed_by is not None:
            filters.append(ArchiveTaxonomyMergeLog.changed_by == changed_by)
        if not include_undone:
            filters.append(ArchiveTaxonomyMergeLog.undone_at.is_(None))
        return filters

    def count_merge_log(
        self, canonical_id: int | None = None, changed_by: str | None = None, include_undone: bool = True
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(ArchiveTaxonomyMergeLog)
            .where(*self._tag_merge_log_filters(canonical_id, changed_by, include_undone))
        )
        return self.db.scalar(stmt) or 0

    def list_merge_log(
        self,
        canonical_id: int | None = None,
        changed_by: str | None = None,
        include_undone: bool = True,
        limit: int = 50,
        offset: int = 0,
    ) -> list[MergeLogEntryDTO]:
        """The audit trail: most recent first, undone entries included unless filtered out."""
        stmt = (
            select(ArchiveTaxonomyMergeLog)
            .where(*self._tag_merge_log_filters(canonical_id, changed_by, include_undone))
            .order_by(ArchiveTaxonomyMergeLog.merge_id.desc())
            .limit(limit)
            .offset(offset)
        )
        return [self._to_merge_log_dto(row) for row in self.db.scalars(stmt).all()]

    def get_merge_log_entry(self, merge_id: int) -> MergeLogEntryDTO | None:
        row = self.db.get(ArchiveTaxonomyMergeLog, merge_id)
        return self._to_merge_log_dto(row) if row else None

    def _to_merge_log_dto(self, row: ArchiveTaxonomyMergeLog) -> MergeLogEntryDTO:
        """Maps the row to the read contract, exposing the document *count* and not the ids."""
        return MergeLogEntryDTO(
            merge_id=row.merge_id,
            cluster_fingerprint=row.cluster_fingerprint,
            canonical_id=row.canonical_id,
            canonical_name=row.canonical_name,
            absorbed_tag_id=row.absorbed_tag_id,
            absorbed_name=row.absorbed_name,
            document_count=len(row.document_ids or []),
            repointed_synonym_names=list(row.repointed_synonym_names or []),
            synonym_created=row.synonym_created,
            changed_by=row.changed_by,
            changed_at=row.changed_at,
            note=row.note,
            undone_at=row.undone_at,
            undone_by=row.undone_by,
        )

    def get_by_id(self, tag_id: int) -> TagIdentity | None:
        obj = self.db.scalar(select(ArchiveTag).where(ArchiveTag.tag_id == tag_id))
        return TagIdentity.model_validate(obj) if obj else None

    def get_document_ids_grouped_by_tags(self, tag_ids: Sequence[int]) -> dict[int, list[str]]:
        """Which documents carry each tag, in one query (the ledger needs the per-tag links)."""
        if not tag_ids:
            return {}

        stmt = select(ArchiveDocumentTag.tag_id, ArchiveDocumentTag.description_id).where(
            ArchiveDocumentTag.tag_id.in_(list(tag_ids))
        )
        grouped: dict[int, list[str]] = defaultdict(list)
        for tag_id, description_id in self.db.execute(stmt).all():
            grouped[tag_id].append(description_id)
        return {tag_id: sorted(ids) for tag_id, ids in grouped.items()}

    def link_documents_to_tag(self, doc_ids: set[str], target_tag_id: int) -> None:
        new_links = [{"description_id": doc_id, "tag_id": target_tag_id} for doc_id in doc_ids]
        stmt = insert(ArchiveDocumentTag).values(new_links).on_conflict_do_nothing()
        self.db.execute(stmt)

    def link_tags_to_document(self, description_id: str, tag_ids: list[int]) -> None:
        """Links multiple tags to a single document (Used occasionally)."""
        if not tag_ids:
            return

        new_links = [{"description_id": description_id, "tag_id": t_id} for t_id in set(tag_ids)]
        stmt = insert(ArchiveDocumentTag).values(new_links).on_conflict_do_nothing()
        self.db.execute(stmt)

    def bulk_link_tags(self, links: Sequence[TagLinkCommand]) -> None:
        """
        Optimization for Batch Ingestion (Workers).
        Inserts thousands of N:N links in a single transaction, deduplicating
        identical commands so the database does not take unnecessary locks.
        """
        if not links:
            return

        unique_links = {(link.description_id, link.tag_id) for link in links}
        rows = [{"description_id": description_id, "tag_id": tag_id} for description_id, tag_id in unique_links]

        stmt = insert(ArchiveDocumentTag).values(rows).on_conflict_do_nothing()
        self.db.execute(stmt)

    def create_synonyms(self, synonyms_data: list[SynonymCommand]) -> None:
        """
        Registers the spellings the ingestion must redirect to a canonical label.

        The upsert (instead of ``on_conflict_do_nothing``) matters when a canonical is
        absorbed into a new one: the spelling already had a mapping and it has to *move*.
        Silently keeping the old target made a re-merge look successful while changing
        nothing, and left the ingestion pointing at a tag that no longer exists.
        """
        if not synonyms_data:
            return

        rows = [
            {
                "synonym_name": normalize_synonym(item.synonym_name),
                "category": item.category,
                "canonical_tag_id": item.canonical_tag_id,
                "canonical_entity_id": item.canonical_entity_id,
            }
            for item in synonyms_data
        ]
        stmt = insert(DomainSynonyms).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["synonym_name", "category"],
            set_={
                "canonical_tag_id": stmt.excluded.canonical_tag_id,
                "canonical_entity_id": stmt.excluded.canonical_entity_id,
            },
        )
        self.db.execute(stmt)

    def repoint_synonyms(self, from_tag_ids: list[int], to_tag_id: int) -> int:
        """
        Moves every synonym that pointed at a tag being merged onto the surviving canonical.

        ``domain_synonyms.canonical_tag_id`` is ``ON DELETE CASCADE``: without this step,
        deleting the absorbed tag destroys the spellings that had already been absorbed into
        it, and the next ingestion recreates them as brand-new tags. The curation is undone
        by the very merge that was supposed to make it durable.
        """
        if not from_tag_ids or to_tag_id in from_tag_ids:
            return 0

        stmt = (
            update(DomainSynonyms)
            .where(DomainSynonyms.category == "TAG", DomainSynonyms.canonical_tag_id.in_(from_tag_ids))
            .values(canonical_tag_id=to_tag_id)
        )
        return cast(CursorResult, self.db.execute(stmt)).rowcount

    def delete_tags(self, tag_ids: list[int]) -> int:
        self.db.execute(delete(ArchiveDocumentTag).where(ArchiveDocumentTag.tag_id.in_(tag_ids)))
        result = self.db.execute(delete(ArchiveTag).where(ArchiveTag.tag_id.in_(tag_ids)))
        return cast(CursorResult, result).rowcount
