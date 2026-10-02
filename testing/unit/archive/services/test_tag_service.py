import pytest
from pytest_mock import MockerFixture

from memoria_curitibana.domains.archive.exceptions import InvalidMergeError, InvalidParam
from memoria_curitibana.domains.archive.repository.document_repo import DocumentRepository
from memoria_curitibana.domains.archive.repository.tag_repo import TagRepository
from memoria_curitibana.domains.archive.schemas import ArchiveTagDTO, MergeTagsCommand
from memoria_curitibana.domains.archive.schemas.tag_schema import MergeResponse, TagIdentity
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


def test_merge_tags_transfers_and_deletes_success(mocker: MockerFixture) -> None:
    """Happy Path: Transfers the documents, saves synonyms and deletes the old tags."""
    mock_tag_repo = mocker.Mock(spec=TagRepository)
    mock_doc_repo = mocker.Mock(spec=DocumentRepository)

    # 1. Simulate the canonical validation and the lookup of the tags that will be killed
    mock_tag_repo.get_by_id.return_value = TagIdentity(tag_id=1, name="prefeitura")
    mock_tag_repo.get_by_ids.return_value = [TagIdentity(tag_id=2, name="prefeituta")]

    # 2. Simulate the lookup of documents that had the old tag
    mock_tag_repo.get_document_ids_by_tags.return_value = ["doc-1", "doc-2"]

    # 3. Simulate the final delete return
    mock_tag_repo.delete_tags.return_value = 1

    service = TagService(mock_tag_repo, mock_doc_repo)
    res: MergeResponse = service.merge(MergeTagsCommand(canonical_id=1, ids_to_merge=[2]))

    assert res.documents_updated == 2
    assert res.tags_deleted == 1

    # Checks the Service coordination
    mock_tag_repo.link_documents_to_tag.assert_called_once_with({"doc-1", "doc-2"}, 1)
    mock_tag_repo.create_synonyms.assert_called_once()
    mock_tag_repo.delete_tags.assert_called_once_with([2])


def test_merge_tags_empty_list(mocker: MockerFixture) -> None:
    """Bad Path: The array of IDs to be merged is empty."""
    mock_tag_repo = mocker.Mock(spec=TagRepository)
    mock_doc_repo = mocker.Mock(spec=DocumentRepository)
    service = TagService(mock_tag_repo, mock_doc_repo)

    with pytest.raises(InvalidParam) as exc_info:
        service.merge(MergeTagsCommand(canonical_id=1, ids_to_merge=[]))

    assert "A lista de tags para mesclar não pode estar vazia." in str(exc_info.value)
    mock_tag_repo.get_by_id.assert_not_called()


def test_merge_tags_canonical_id_in_ids_to_merge(mocker: MockerFixture) -> None:
    """Bad Path: The array of IDs to be merged contains the canonical id."""
    mock_tag_repo = mocker.Mock(spec=TagRepository)
    mock_doc_repo = mocker.Mock(spec=DocumentRepository)
    service = TagService(mock_tag_repo, mock_doc_repo)

    with pytest.raises(InvalidMergeError) as exc_info:
        service.merge(MergeTagsCommand(canonical_id=1, ids_to_merge=[1]))

    assert "O ID da tag canônica não pode estar na lista de exclusão." in str(exc_info.value)
    mock_tag_repo.get_by_id.assert_not_called()


def test_merge_tags_no_documents_affected(mocker: MockerFixture) -> None:
    """
    Partial Path: The tag exists, but no document uses it.
    It must skip the document transfer, but STILL create the synonym and delete it.
    """
    mock_tag_repo = mocker.Mock(spec=TagRepository)
    mock_doc_repo = mocker.Mock(spec=DocumentRepository)

    mock_tag_repo.get_by_id.return_value = TagIdentity(tag_id=1, name="oficial")
    mock_tag_repo.get_by_ids.return_value = [TagIdentity(tag_id=2, name="tag_sem_uso")]

    # No document uses the tag
    mock_tag_repo.get_document_ids_by_tags.return_value = []
    mock_tag_repo.delete_tags.return_value = 1

    service = TagService(mock_tag_repo, mock_doc_repo)
    res = service.merge(MergeTagsCommand(canonical_id=1, ids_to_merge=[2]))

    assert res.documents_updated == 0
    assert res.tags_deleted == 1

    # Since there are no documents, the transfer INSERT is skipped!
    mock_tag_repo.link_documents_to_tag.assert_not_called()
    mock_tag_repo.create_synonyms.assert_called_once()
    mock_tag_repo.delete_tags.assert_called_once_with([2])


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
