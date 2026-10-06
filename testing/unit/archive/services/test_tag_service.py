import pytest
from pytest_mock import MockerFixture

from memoria_curitibana.domains.archive.exceptions import (
    InvalidMergeError,
    InvalidParam,
    MacroCategoryNotFoundError,
    TagMergeProposalNotFoundError,
)
from memoria_curitibana.domains.archive.repository.document_repo import DocumentRepository
from memoria_curitibana.domains.archive.repository.tag_repo import TagRepository
from memoria_curitibana.domains.archive.schemas import (
    ArchiveMacroCategoryEntityDTO,
    ArchiveTagDTO,
    BatchMergeResponse,
    CreateMacroCategoryCommand,
    MergeBatchApplied,
    MergeBatchCommand,
    MergePlan,
    MergePreviewCommand,
    MergeTagsCommand,
    TagMergeDecisionCommand,
    TagMergeImpact,
    TagMergeMember,
    TagMergeSuggestion,
    UpdateMacroCategoryCommand,
)
from memoria_curitibana.domains.archive.schemas.tag_schema import (
    MergeResponse,
    TagIdentity,
    TagMergeProposalDTO,
)
from memoria_curitibana.domains.archive.services.tag_service import TagService

# ==========================================
# TESTS: extract_and_clean_tags
# ==========================================


def test_extract_and_clean_tags_success(mocker: MockerFixture) -> None:
    """Happy Path: Removes the stopwords using the compiled regex and cleans the string correctly."""
    mock_tag_repo = mocker.Mock(spec=TagRepository)
    mock_doc_repo = mocker.Mock(spec=DocumentRepository)

    # We teach the fake repo to return a pure Set
    mock_tag_repo.get_stopwords.return_value = {"lixo", "ignorar"}

    service = TagService(mock_tag_repo, mock_doc_repo)
    raw_text = "Tag Válida, Lixo, Ignorar, Outra   Tag   Boa"

    result = service.extract_and_clean_tags(raw_text)

    assert len(result) == 2
    extracted_names = {tag.name for tag in result}
    assert "tag válida" in extracted_names
    assert "outra tag boa" in extracted_names
    mock_tag_repo.get_stopwords.assert_called_once()


def test_extract_and_clean_tags_null_or_empty(mocker: MockerFixture) -> None:
    """Bad Path: Guarantees the early return if the string is None or empty."""
    mock_tag_repo = mocker.Mock(spec=TagRepository)
    mock_doc_repo = mocker.Mock(spec=DocumentRepository)

    service = TagService(mock_tag_repo, mock_doc_repo)

    assert service.extract_and_clean_tags(None) == []
    assert service.extract_and_clean_tags("") == []
    # The repository must not even be queried
    mock_tag_repo.get_stopwords.assert_not_called()


def test_extract_and_clean_tags_only_stopwords(mocker: MockerFixture) -> None:
    """Bad Path: The string contained only junk and was 100% cleaned."""
    mock_tag_repo = mocker.Mock(spec=TagRepository)
    mock_doc_repo = mocker.Mock(spec=DocumentRepository)
    mock_tag_repo.get_stopwords.return_value = {"teste", "vazio"}

    service = TagService(mock_tag_repo, mock_doc_repo)
    result = service.extract_and_clean_tags("Teste, Vazio, Teste")

    assert result == []


def test_extract_and_clean_tags_data_quality(mocker: MockerFixture) -> None:
    """Edge Limits: Guarantees that anomalous tags (1 to 2 letters or >100) are discarded."""
    mock_tag_repo = mocker.Mock(spec=TagRepository)
    mock_doc_repo = mocker.Mock(spec=DocumentRepository)
    mock_tag_repo.get_stopwords.return_value = set()  # No stopwords in the database

    service = TagService(mock_tag_repo, mock_doc_repo)
    raw_text = "A, Oi, Tag Normal, " + ("X" * 105)

    result = service.extract_and_clean_tags(raw_text)

    # 'A' and 'Oi' are shorter than or equal to 2 characters. 'X'*105 is longer than 100.
    assert len(result) == 1
    assert result[0].name == "tag normal"


def test_extract_and_clean_tags_keeps_multiple_word_tags(mocker: MockerFixture) -> None:
    """Regression: a stopword must only drop the WHOLE tag, never a substring of it."""
    mock_tag_repo = mocker.Mock(spec=TagRepository)
    mock_doc_repo = mocker.Mock(spec=DocumentRepository)
    mock_tag_repo.get_stopwords.return_value = {"lixo", "rio"}

    service = TagService(mock_tag_repo, mock_doc_repo)
    result = service.extract_and_clean_tags("Rio Branco, Lixo, Rio")
    names = {tag.name for tag in result}

    # "Rio Branco" survives; only the exact tags "lixo" and "rio" are removed.
    assert "rio branco" in names
    assert "lixo" not in names
    assert "rio" not in names


def test_extract_and_clean_tags_splits_pipe_separator(mocker: MockerFixture) -> None:
    """Regression: staging joins duplicate keys with ' | ', which is also a separator."""
    mock_tag_repo = mocker.Mock(spec=TagRepository)
    mock_doc_repo = mocker.Mock(spec=DocumentRepository)
    mock_tag_repo.get_stopwords.return_value = set()

    service = TagService(mock_tag_repo, mock_doc_repo)
    result = service.extract_and_clean_tags("Obras | Urbanismo, Saneamento")
    names = {tag.name for tag in result}

    assert names == {"obras", "urbanismo", "saneamento"}


# ==========================================
# TESTS: purge_stopwords
# ==========================================


def test_purge_stopwords_removes_tags_success(mocker: MockerFixture) -> None:
    """Happy Path: Coordinates the stopword lookup and the bulk deletion."""
    mock_tag_repo = mocker.Mock(spec=TagRepository)
    mock_doc_repo = mocker.Mock(spec=DocumentRepository)

    mock_tag_repo.get_stopwords.return_value = {"lixo"}
    mock_tag_repo.purge_tags_by_stopwords.return_value = 1  # Pretend it deleted 1 tag

    service = TagService(mock_tag_repo, mock_doc_repo)
    deleted_count = service.purge_stopwords()

    assert deleted_count == 1
    mock_tag_repo.get_stopwords.assert_called_once()
    mock_tag_repo.purge_tags_by_stopwords.assert_called_once_with({"lixo"})


def test_purge_stopwords_empty_stopwords_table(mocker: MockerFixture) -> None:
    """Bad Path: The stopword table is empty. The service must abort quickly."""
    mock_tag_repo = mocker.Mock(spec=TagRepository)
    mock_doc_repo = mocker.Mock(spec=DocumentRepository)

    mock_tag_repo.get_stopwords.return_value = set()

    service = TagService(mock_tag_repo, mock_doc_repo)
    deleted_count = service.purge_stopwords()

    assert deleted_count == 0
    mock_tag_repo.purge_tags_by_stopwords.assert_not_called()


# ==========================================
# TESTS: merge_tags
# ==========================================


def test_merge_tags_validates_then_plans_and_applies(mocker: MockerFixture) -> None:
    """
    The service validates the rules and delegates to the shared plan/apply pair.

    Planning and applying are separate on purpose: the dry-run calls only the first half, so
    what the preview promises is what the merge does.
    """
    mock_tag_repo = mocker.Mock(spec=TagRepository)
    mock_doc_repo = mocker.Mock(spec=DocumentRepository)
    mock_tag_repo.get_by_id.return_value = TagIdentity(tag_id=1, name="prefeitura")

    plan = MergePlan(
        canonical_id=1,
        canonical_name="prefeitura",
        ids_to_merge=[2],
        document_ids=["doc-1", "doc-2"],
    )
    mock_tag_repo.plan_merge.return_value = plan
    mock_tag_repo.apply_merge.return_value = MergeResponse(documents_updated=2, tags_deleted=1)

    service = TagService(mock_tag_repo, mock_doc_repo)
    res: MergeResponse = service.merge(MergeTagsCommand(canonical_id=1, ids_to_merge=[2]))

    assert res.documents_updated == 2
    assert res.tags_deleted == 1
    mock_tag_repo.plan_merge.assert_called_once_with(1, [2])
    mock_tag_repo.apply_merge.assert_called_once_with(plan, changed_by=None)


def test_merge_passes_the_author_to_the_ledger(mocker: MockerFixture) -> None:
    """Without the author the ledger would not answer 'who merged this'."""
    mock_tag_repo = mocker.Mock(spec=TagRepository)
    mock_doc_repo = mocker.Mock(spec=DocumentRepository)
    mock_tag_repo.get_by_id.return_value = TagIdentity(tag_id=1, name="casa")
    plan = MergePlan(canonical_id=1, canonical_name="casa", ids_to_merge=[2])
    mock_tag_repo.plan_merge.return_value = plan
    mock_tag_repo.apply_merge.return_value = MergeResponse(documents_updated=0, tags_deleted=1, merge_ids=[9])

    service = TagService(mock_tag_repo, mock_doc_repo)
    response = service.merge(MergeTagsCommand(canonical_id=1, ids_to_merge=[2], changed_by="arquivista"))

    assert response.merge_ids == [9]
    mock_tag_repo.apply_merge.assert_called_once_with(plan, changed_by="arquivista")


def test_merge_tags_empty_list(mocker: MockerFixture) -> None:
    """Bad Path: The array of IDs to be merged is empty."""
    mock_tag_repo = mocker.Mock(spec=TagRepository)
    mock_doc_repo = mocker.Mock(spec=DocumentRepository)
    service = TagService(mock_tag_repo, mock_doc_repo)

    with pytest.raises(InvalidParam) as exc_info:
        service.merge(MergeTagsCommand(canonical_id=1, ids_to_merge=[]))

    assert "A lista de tags para mesclar não pode estar vazia." in str(exc_info.value)
    mock_tag_repo.get_by_id.assert_not_called()
    mock_tag_repo.plan_merge.assert_not_called()


def test_merge_tags_canonical_id_in_ids_to_merge(mocker: MockerFixture) -> None:
    """Bad Path: The array of IDs to be merged contains the canonical id."""
    mock_tag_repo = mocker.Mock(spec=TagRepository)
    mock_doc_repo = mocker.Mock(spec=DocumentRepository)
    service = TagService(mock_tag_repo, mock_doc_repo)

    with pytest.raises(InvalidMergeError) as exc_info:
        service.merge(MergeTagsCommand(canonical_id=1, ids_to_merge=[1]))

    assert "O ID da tag canônica não pode estar na lista de exclusão." in str(exc_info.value)
    mock_tag_repo.get_by_id.assert_not_called()
    mock_tag_repo.plan_merge.assert_not_called()


def test_merge_tags_missing_canonical(mocker: MockerFixture) -> None:
    """Bad Path: the canonical tag does not exist, so nothing is planned or written."""
    mock_tag_repo = mocker.Mock(spec=TagRepository)
    mock_doc_repo = mocker.Mock(spec=DocumentRepository)
    mock_tag_repo.get_by_id.return_value = None

    service = TagService(mock_tag_repo, mock_doc_repo)

    with pytest.raises(InvalidParam, match="não existe no acervo"):
        service.merge(MergeTagsCommand(canonical_id=1, ids_to_merge=[2]))

    mock_tag_repo.plan_merge.assert_not_called()
    mock_tag_repo.apply_merge.assert_not_called()


# ==========================================
# TESTS: dry-run and merge proposals
# ==========================================


def test_preview_merge_is_read_only(mocker: MockerFixture) -> None:
    """The dry-run computes the plan and never applies it."""
    mock_tag_repo = mocker.Mock(spec=TagRepository)
    mock_doc_repo = mocker.Mock(spec=DocumentRepository)
    mock_tag_repo.get_by_id.return_value = TagIdentity(tag_id=1, name="rua")

    mock_tag_repo.plan_merge.return_value = MergePlan(
        canonical_id=1,
        canonical_name="rua",
        ids_to_merge=[2, 3],
        impacted=[
            TagMergeImpact(tag_id=2, name="ruas", document_count=8),
            TagMergeImpact(tag_id=3, name="rua 7", document_count=3),
        ],
        document_ids=["doc-1", "doc-2"],
        synonym_names=["ruas", "rua 7"],
        review_flags=["MEMBER_WITH_DIGITS"],
    )

    service = TagService(mock_tag_repo, mock_doc_repo)
    preview = service.preview_merge(MergePreviewCommand(canonical_id=1, ids_to_merge=[2, 3]))

    assert preview.documents_updated == 2
    assert preview.links_rewritten == 11
    assert {member.name for member in preview.tags_deleted} == {"ruas", "rua 7"}
    assert preview.review_flags == ["MEMBER_WITH_DIGITS"]
    mock_tag_repo.apply_merge.assert_not_called()


def test_preview_merge_by_proposal_uses_its_members(mocker: MockerFixture) -> None:
    """A persisted proposal is enough to ask for the dry-run; its members become the ids."""
    mock_tag_repo = mocker.Mock(spec=TagRepository)
    mock_doc_repo = mocker.Mock(spec=DocumentRepository)
    mock_tag_repo.get_merge_proposal.return_value = TagMergeProposalDTO(
        proposal_id=7,
        fingerprint="abc",
        canonical_id=1,
        canonical_name="casa",
        reason="PLURAL",
        total_documents=4,
        status="SUGGESTED",
        members=[
            TagMergeMember(tag_id=1, name="casa", document_count=3),
            TagMergeMember(tag_id=2, name="casas", document_count=1),
        ],
    )
    mock_tag_repo.get_by_id.return_value = TagIdentity(tag_id=1, name="casa")
    mock_tag_repo.plan_merge.return_value = MergePlan(canonical_id=1, canonical_name="casa", ids_to_merge=[2])

    service = TagService(mock_tag_repo, mock_doc_repo)
    service.preview_merge(MergePreviewCommand(proposal_id=7))

    mock_tag_repo.plan_merge.assert_called_once_with(1, [2])


def test_decide_merge_proposal_records_the_author(mocker: MockerFixture) -> None:
    """The verdict carries who decided and when, so the approval is auditable."""
    mock_tag_repo = mocker.Mock(spec=TagRepository)
    mock_doc_repo = mocker.Mock(spec=DocumentRepository)
    mock_tag_repo.decide_merge_proposal.return_value = TagMergeProposalDTO(
        proposal_id=7,
        fingerprint="abc",
        canonical_name="casa",
        reason="PLURAL",
        total_documents=4,
        status="APPROVED",
        decided_by="arquivista",
    )

    service = TagService(mock_tag_repo, mock_doc_repo)
    result = service.decide_merge_proposal(
        7, TagMergeDecisionCommand(status="APPROVED", decided_by="arquivista", note="mesmo conceito")
    )

    assert result.status == "APPROVED"
    mock_tag_repo.decide_merge_proposal.assert_called_once_with(
        7, status="APPROVED", decided_by="arquivista", note="mesmo conceito"
    )
    # The decision is not the merge: nothing was applied.
    mock_tag_repo.apply_merge.assert_not_called()


def test_decide_unknown_proposal_raises_not_found(mocker: MockerFixture) -> None:
    """A PATCH on a proposal that does not exist becomes a domain 404, not a silent success."""
    mock_tag_repo = mocker.Mock(spec=TagRepository)
    mock_doc_repo = mocker.Mock(spec=DocumentRepository)
    mock_tag_repo.decide_merge_proposal.return_value = None

    service = TagService(mock_tag_repo, mock_doc_repo)

    with pytest.raises(TagMergeProposalNotFoundError):
        service.decide_merge_proposal(999, TagMergeDecisionCommand(status="REJECTED"))


def test_list_merge_proposals_rejects_a_page_beyond_the_cap(mocker: MockerFixture) -> None:
    """A client cannot ask the whole catalog in one request."""
    mock_tag_repo = mocker.Mock(spec=TagRepository)
    mock_doc_repo = mocker.Mock(spec=DocumentRepository)
    service = TagService(mock_tag_repo, mock_doc_repo)

    with pytest.raises(InvalidParam, match="limit"):
        service.list_merge_proposals(limit=10_000)

    mock_tag_repo.list_merge_proposals.assert_not_called()


def test_list_merge_proposals_reports_the_total_with_the_page(mocker: MockerFixture) -> None:
    """The total matches the filters, so the caller knows how much is left outside the page."""
    mock_tag_repo = mocker.Mock(spec=TagRepository)
    mock_doc_repo = mocker.Mock(spec=DocumentRepository)
    mock_tag_repo.count_merge_proposals.return_value = 411
    mock_tag_repo.list_merge_proposals.return_value = []

    service = TagService(mock_tag_repo, mock_doc_repo)
    page = service.list_merge_proposals(status="SUGGESTED", limit=10, offset=20)

    assert page.total == 411
    assert page.limit == 10
    assert page.offset == 20
    mock_tag_repo.list_merge_proposals.assert_called_once_with(
        status="SUGGESTED", reason=None, min_documents=0, flagged_only=False, limit=10, offset=20
    )


def test_suggest_merges_persists_and_reports_the_pending_backlog(mocker: MockerFixture) -> None:
    """The run registers the clusters and reports what is still waiting for a human."""
    mock_tag_repo = mocker.Mock(spec=TagRepository)
    mock_doc_repo = mocker.Mock(spec=DocumentRepository)
    mock_tag_repo.find_merge_suggestions.return_value = [
        TagMergeSuggestion(
            canonical_id=1,
            canonical_name="casa",
            total_documents=4,
            reason="PLURAL",
            members=[
                TagMergeMember(tag_id=1, name="casa", document_count=3),
                TagMergeMember(tag_id=2, name="casas", document_count=1),
            ],
        )
    ]
    mock_tag_repo.upsert_merge_proposals.return_value = 1
    mock_tag_repo.count_merge_proposals.side_effect = [411, 60]

    service = TagService(mock_tag_repo, mock_doc_repo)
    run = service.suggest_merges(threshold=0.7, limit=100)

    assert run.clusters_found == 1
    assert run.persisted == 1
    assert run.pending == 411
    assert run.flagged == 60
    mock_tag_repo.find_merge_suggestions.assert_called_once_with(threshold=0.7, limit=100)


def test_suggest_merges_rejects_an_out_of_range_threshold(mocker: MockerFixture) -> None:
    """An impossible threshold is a domain error, not an empty result."""
    mock_tag_repo = mocker.Mock(spec=TagRepository)
    mock_doc_repo = mocker.Mock(spec=DocumentRepository)
    service = TagService(mock_tag_repo, mock_doc_repo)

    with pytest.raises(InvalidParam, match="threshold"):
        service.suggest_merges(threshold=1.5)

    mock_tag_repo.find_merge_suggestions.assert_not_called()


# ==========================================
# TESTS: batch application and audit trail
# ==========================================


def _proposal(
    proposal_id: int, *, status: str, canonical_id: int, canonical_name: str, members: list
) -> TagMergeProposalDTO:
    return TagMergeProposalDTO(
        proposal_id=proposal_id,
        fingerprint=f"fp-{proposal_id}",
        canonical_id=canonical_id,
        canonical_name=canonical_name,
        reason="PLURAL",
        total_documents=2,
        status=status,
        members=members,
        # The aliveness is computed on read from the collection, so a fixture has to state it:
        # the DTO defaults to "nothing left to absorb", which is the safe side for a screen.
        members_alive=len(members),
        canonical_alive=True,
        applicable=len(members) > 1,
    )


def test_merge_batch_approves_pending_clusters_and_reports_the_rejected(mocker: MockerFixture) -> None:
    """The batch is the decision for the pending ones; a rejected cluster is refused, not applied."""
    mock_tag_repo = mocker.Mock(spec=TagRepository)
    mock_doc_repo = mocker.Mock(spec=DocumentRepository)

    pending = _proposal(
        1,
        status="SUGGESTED",
        canonical_id=10,
        canonical_name="casa",
        members=[
            TagMergeMember(tag_id=10, name="casa", document_count=1),
            TagMergeMember(tag_id=11, name="casas", document_count=1),
        ],
    )
    rejected = _proposal(
        2,
        status="REJECTED",
        canonical_id=20,
        canonical_name="lote",
        members=[
            TagMergeMember(tag_id=20, name="lote", document_count=1),
            TagMergeMember(tag_id=21, name="lotes", document_count=1),
        ],
    )
    mock_tag_repo.get_merge_proposal.side_effect = lambda proposal_id: {1: pending, 2: rejected}.get(proposal_id)
    mock_tag_repo.plan_merge.return_value = MergePlan(
        canonical_id=10, canonical_name="casa", ids_to_merge=[11], document_ids=["doc-1"]
    )
    mock_tag_repo.apply_merge_batch.return_value = BatchMergeResponse(
        applied=[MergeBatchApplied(proposal_id=1, merge_ids=[7], documents_updated=1, tags_deleted=1)],
        failed=[],
    )

    service = TagService(mock_tag_repo, mock_doc_repo)
    result = service.merge_batch(MergeBatchCommand(proposal_ids=[1, 2], changed_by="arquivista", note="lote"))

    assert [entry.proposal_id for entry in result.applied] == [1]
    assert len(result.failed) == 1
    assert result.failed[0].proposal_id == 2
    assert "rejeitada" in result.failed[0].error

    # Including a pending cluster approves it, with the author of the batch.
    mock_tag_repo.decide_merge_proposal.assert_called_once_with(
        1, status="APPROVED", decided_by="arquivista", note="lote"
    )

    entries = mock_tag_repo.apply_merge_batch.call_args[0][0]
    assert [entry.proposal_id for entry in entries] == [1]
    assert entries[0].cluster_fingerprint == "fp-1"


def test_merge_batch_refuses_more_clusters_than_the_cap(mocker: MockerFixture) -> None:
    """Each cluster is a savepoint inside one transaction, so the request has to stay bounded."""
    mock_tag_repo = mocker.Mock(spec=TagRepository)
    mock_doc_repo = mocker.Mock(spec=DocumentRepository)
    service = TagService(mock_tag_repo, mock_doc_repo)

    with pytest.raises(InvalidParam, match="lote aceita"):
        service.merge_batch(MergeBatchCommand(proposal_ids=list(range(1, 500))))

    mock_tag_repo.apply_merge_batch.assert_not_called()


def test_merge_batch_reports_a_proposal_without_a_canonical(mocker: MockerFixture) -> None:
    """A stale proposal is a named failure, not a crash that takes the batch down."""
    mock_tag_repo = mocker.Mock(spec=TagRepository)
    mock_doc_repo = mocker.Mock(spec=DocumentRepository)
    mock_tag_repo.get_merge_proposal.return_value = _proposal(
        3, status="SUGGESTED", canonical_id=30, canonical_name="obra", members=[]
    ).model_copy(update={"canonical_id": None})
    mock_tag_repo.apply_merge_batch.return_value = BatchMergeResponse()

    service = TagService(mock_tag_repo, mock_doc_repo)
    result = service.merge_batch(MergeBatchCommand(proposal_ids=[3]))

    assert result.applied == []
    assert "canônica" in result.failed[0].error


def test_list_merge_log_rejects_a_page_beyond_the_cap(mocker: MockerFixture) -> None:
    """The audit trail is paged like every other listing."""
    mock_tag_repo = mocker.Mock(spec=TagRepository)
    mock_doc_repo = mocker.Mock(spec=DocumentRepository)
    service = TagService(mock_tag_repo, mock_doc_repo)

    with pytest.raises(InvalidParam, match="limit"):
        service.list_merge_log(limit=10_000)

    mock_tag_repo.list_merge_log.assert_not_called()


def test_list_merge_log_reports_the_total_with_the_page(mocker: MockerFixture) -> None:
    """The total matches the filters, so the caller knows how much is left outside the page."""
    mock_tag_repo = mocker.Mock(spec=TagRepository)
    mock_doc_repo = mocker.Mock(spec=DocumentRepository)
    mock_tag_repo.count_merge_log.return_value = 12
    mock_tag_repo.list_merge_log.return_value = []

    service = TagService(mock_tag_repo, mock_doc_repo)
    page = service.list_merge_log(
        canonical_id=4, changed_by="arquivista", include_undone=False, term="alameda", limit=5, offset=5
    )

    assert page.total == 12
    assert page.limit == 5
    assert page.offset == 5
    # The search reaches both halves of the ledger — the count and the page — or the footer lies.
    mock_tag_repo.count_merge_log.assert_called_once_with(
        canonical_id=4, changed_by="arquivista", include_undone=False, term="alameda"
    )
    mock_tag_repo.list_merge_log.assert_called_once_with(
        canonical_id=4, changed_by="arquivista", include_undone=False, term="alameda", limit=5, offset=5
    )


# ==========================================
# TESTS: get_text_to_suggest_macro_category
# ==========================================


def test_get_text_to_suggest_macro_category_tags(mocker: MockerFixture):
    """Guarantees that the service fetches tags from the Tags repository."""
    mock_tag_repo = mocker.Mock(spec=TagRepository)
    mock_doc_repo = mocker.Mock(spec=DocumentRepository)

    mock_tag_repo.fetch_tags_for_clustering.return_value = ["tag1", "tag2"]

    service = TagService(mock_tag_repo, mock_doc_repo)
    result = service.get_text_to_suggest_macro_category(source_type="tags")

    mock_tag_repo.fetch_tags_for_clustering.assert_called_once()
    assert result == ["tag1", "tag2"]


def test_get_text_to_suggest_macro_category_documents(mocker: MockerFixture):
    """Guarantees that the service correctly delegates the document lookup to DocumentRepository."""
    mock_tag_repo = mocker.Mock(spec=TagRepository)
    mock_doc_repo = mocker.Mock(spec=DocumentRepository)

    mock_doc_repo.fetch_documents_for_clustering.return_value = ["doc1", "doc2"]

    service = TagService(mock_tag_repo, mock_doc_repo)
    columns = ["scope_content"]

    result = service.get_text_to_suggest_macro_category(source_type="documents", columns_to_extract=columns)

    mock_doc_repo.fetch_documents_for_clustering.assert_called_once_with(columns_to_extract=columns)
    assert result == ["doc1", "doc2"]


def test_get_text_to_suggest_macro_category_invalid(mocker: MockerFixture):
    """Guarantees the block if an unsupported source_type is passed."""
    mock_tag_repo = mocker.Mock(spec=TagRepository)
    mock_doc_repo = mocker.Mock(spec=DocumentRepository)

    service = TagService(mock_tag_repo, mock_doc_repo)

    with pytest.raises(InvalidParam) as exc_info:
        service.get_text_to_suggest_macro_category(source_type="invalido")  # type: ignore

    assert "O parâmetro 'source_type' deve ser obrigatoriamente 'tags' ou 'documents'." in str(exc_info.value)


# ==========================================
# TESTS: process_worker_tags
# ==========================================


def test_process_worker_tags_empty_list(mocker: MockerFixture) -> None:
    """Bad Path: The worker sent an empty list, returns quickly without hitting the repository."""
    mock_tag_repo = mocker.Mock(spec=TagRepository)
    mock_doc_repo = mocker.Mock(spec=DocumentRepository)

    service = TagService(mock_tag_repo, mock_doc_repo)
    result = service.process_worker_tags([])

    assert result == []
    mock_tag_repo.get_synonyms_mapping.assert_not_called()
    mock_tag_repo.get_or_create_tags.assert_not_called()


def test_process_worker_tags_only_new_tags_happy_path(mocker: MockerFixture) -> None:
    """Happy Path: No tag is a synonym, all are sent for creation."""
    mock_tag_repo = mocker.Mock(spec=TagRepository)
    mock_doc_repo = mocker.Mock(spec=DocumentRepository)

    # Mocks: The database returns that there are no synonyms, and creation generated IDs 10 and 11
    mock_tag_repo.get_synonyms_mapping.return_value = {}
    mock_tag_repo.get_or_create_tags.return_value = [10, 11]

    dtos = [
        ArchiveTagDTO(name="Urbanismo", macro_category_id=None, ai_confidence_score=None),
        ArchiveTagDTO(name="Asfalto", macro_category_id=None, ai_confidence_score=None),
    ]

    service = TagService(mock_tag_repo, mock_doc_repo)
    result = service.process_worker_tags(dtos)

    assert set(result) == {10, 11}
    mock_tag_repo.get_synonyms_mapping.assert_called_once()
    mock_tag_repo.get_or_create_tags.assert_called_once_with(dtos)


def test_process_worker_tags_only_synonyms(mocker: MockerFixture) -> None:
    """Replacement Path: The worker sent ONLY synonyms, skipping creation in the repository."""
    mock_tag_repo = mocker.Mock(spec=TagRepository)
    mock_doc_repo = mocker.Mock(spec=DocumentRepository)

    # Mocks: Both words are already known synonyms mapped to IDs 99 and 100
    mock_tag_repo.get_synonyms_mapping.return_value = {"prefeiruta": 99, "parques": 100}

    dtos = [
        ArchiveTagDTO(name="Prefeiruta", macro_category_id=None, ai_confidence_score=None),
        ArchiveTagDTO(name="Parques", macro_category_id=None, ai_confidence_score=None),
    ]

    service = TagService(mock_tag_repo, mock_doc_repo)
    result = service.process_worker_tags(dtos)

    assert set(result) == {99, 100}
    mock_tag_repo.get_synonyms_mapping.assert_called_once()
    # Skips creation, since no new tag was left!
    mock_tag_repo.get_or_create_tags.assert_not_called()


def test_process_worker_tags_mixed_synonyms_and_new(mocker: MockerFixture) -> None:
    """Realistic Path: The fine sieve intercepts synonyms and sends only the legitimate tags to the database."""
    mock_tag_repo = mocker.Mock(spec=TagRepository)
    mock_doc_repo = mocker.Mock(spec=DocumentRepository)

    # Mocks: "leis" is a synonym of the canonical tag (ID 5). The "IPTU" tag has no synonym and will receive ID 88
    mock_tag_repo.get_synonyms_mapping.return_value = {"leis": 5}
    mock_tag_repo.get_or_create_tags.return_value = [88]

    synonym_dto = ArchiveTagDTO(name="Leis", macro_category_id=None, ai_confidence_score=None)
    new_dto = ArchiveTagDTO(name="IPTU", macro_category_id=None, ai_confidence_score=None)

    service = TagService(mock_tag_repo, mock_doc_repo)
    result = service.process_worker_tags([synonym_dto, new_dto])

    assert set(result) == {5, 88}

    # Checks whether the service sent ONLY the new dto ("IPTU") for persistence
    mock_tag_repo.get_or_create_tags.assert_called_once()
    dtos_sent_for_creation = mock_tag_repo.get_or_create_tags.call_args[0][0]

    assert len(dtos_sent_for_creation) == 1
    assert dtos_sent_for_creation[0].name == "iptu"


def test_process_worker_tags_deduplicates_ids(mocker: MockerFixture) -> None:
    """Edge Limits: Guarantees that multiple different tags do not generate the same duplicated ID on the document."""
    mock_tag_repo = mocker.Mock(spec=TagRepository)
    mock_doc_repo = mocker.Mock(spec=DocumentRepository)

    # Let's say "parques" and "pracinhas" are both synonyms for ID 12 ("parque").
    # And "parque" was also sent (it is not a synonym, it will go through creation and return ID 12).
    mock_tag_repo.get_synonyms_mapping.return_value = {"parques": 12, "pracinhas": 12}
    mock_tag_repo.get_or_create_tags.return_value = [12]

    dtos = [
        ArchiveTagDTO(name="Parque", macro_category_id=None, ai_confidence_score=None),
        ArchiveTagDTO(name="Parques", macro_category_id=None, ai_confidence_score=None),
        ArchiveTagDTO(name="Pracinhas", macro_category_id=None, ai_confidence_score=None),
    ]

    service = TagService(mock_tag_repo, mock_doc_repo)
    result = service.process_worker_tags(dtos)

    # The result must have only ONE record of ID 12. The use of set() in the service guarantees this.
    assert len(result) == 1
    assert result == [12]


# ==========================================
# TESTS: Macro Category CRUD
# ==========================================


def _macro_dto(name: str = "Urbanismo") -> ArchiveMacroCategoryEntityDTO:
    return ArchiveMacroCategoryEntityDTO(category_id=1, name=name, description=None, is_active=True)


def test_create_macro_category_strips_name(mocker: MockerFixture) -> None:
    """The curator's whitespace must not create a category distinct from the trimmed one."""
    mock_tag_repo = mocker.Mock(spec=TagRepository)
    mock_doc_repo = mocker.Mock(spec=DocumentRepository)
    mock_tag_repo.create_macro_category.return_value = _macro_dto()

    service = TagService(mock_tag_repo, mock_doc_repo)
    service.create_macro_category(CreateMacroCategoryCommand(name="  Urbanismo  ", description="obras"))

    mock_tag_repo.create_macro_category.assert_called_once_with(
        name="Urbanismo", description="obras", classifier_label=None
    )


def test_create_macro_category_rejects_blank_name(mocker: MockerFixture) -> None:
    """A name of spaces is rejected before touching the database."""
    mock_tag_repo = mocker.Mock(spec=TagRepository)
    mock_doc_repo = mocker.Mock(spec=DocumentRepository)

    service = TagService(mock_tag_repo, mock_doc_repo)

    with pytest.raises(InvalidParam, match="nome da macro categoria"):
        service.create_macro_category(CreateMacroCategoryCommand(name="   "))

    mock_tag_repo.create_macro_category.assert_not_called()


def test_update_macro_category_raises_when_missing(mocker: MockerFixture) -> None:
    """A patch on a non-existent category becomes a domain 404, not a silent success."""
    mock_tag_repo = mocker.Mock(spec=TagRepository)
    mock_doc_repo = mocker.Mock(spec=DocumentRepository)
    mock_tag_repo.update_macro_category.return_value = None

    service = TagService(mock_tag_repo, mock_doc_repo)

    with pytest.raises(MacroCategoryNotFoundError):
        service.update_macro_category(999, UpdateMacroCategoryCommand(is_active=False))

    mock_tag_repo.update_macro_category.assert_called_once_with(999, {"is_active": False})


def test_update_macro_category_only_sends_declared_fields(mocker: MockerFixture) -> None:
    """exclude_unset keeps an untouched description from being wiped by a rename."""
    mock_tag_repo = mocker.Mock(spec=TagRepository)
    mock_doc_repo = mocker.Mock(spec=DocumentRepository)
    mock_tag_repo.update_macro_category.return_value = _macro_dto("Novo Nome")

    service = TagService(mock_tag_repo, mock_doc_repo)
    service.update_macro_category(1, UpdateMacroCategoryCommand(name="  Novo Nome "))

    mock_tag_repo.update_macro_category.assert_called_once_with(1, {"name": "Novo Nome"})
