from pytest_mock import MockerFixture
from sqlalchemy.orm import Session

from scrinalia.domains.archive.schemas import ArchiveEntityDTO, EntityLinkCommand
from scrinalia.domains.archive.workers import worker_ner


class MockArchiveDocument:
    """Ultralean double simulating an SQLAlchemy document for the Unit Tests."""

    def __init__(self, description_id: str, title: str, content: str = ""):
        self.description_id = description_id
        self.original_title = title
        self.admin_bio_history = None
        self.provenance = None
        self.scope_content = content
        self.execution_log = None


# ==========================================
# 1. CLEANING HELPER TESTS
# ==========================================


def test_clean_raw_text_removes_urls_and_emails():
    """Guarantees that the helper function correctly cleans web noise."""
    dirty_text = "Visite http://site.com ou www.teste.com e mande email para admin@gov.br. Texto limpo."
    result = worker_ner._clean_raw_text(dirty_text)

    assert result == "Visite  ou  e mande email para  Texto limpo."


def test_clean_raw_text_reads_the_whole_url_and_nothing_else():
    """
    The URL alphabet is RFC 3986's, not the accidental range ``$`` to ``_``.

    Read as a range, that class swallowed ``[ \\ ] ^`` with the URL and stopped the match at ``#``
    and ``~``, which a URL really carries. Measured on these four inputs, the previous pattern left
    ``#frag~x`` behind and took the ``>`` that closes a bracketed URL with it.
    """
    assert worker_ner._clean_raw_text("http://site.com:8080/a/b?q=1&r=2#frag~x") == ""
    assert worker_ner._clean_raw_text("Veja <http://site.com/x> agora") == "Veja <> agora"
    assert worker_ner._clean_raw_text(r"http://site.com\^x y") == r"\^x y"
    assert worker_ner._clean_raw_text("http://site.com/100%25 done") == "done"


def test_clean_raw_text_empty():
    assert worker_ner._clean_raw_text(None) == ""  # type: ignore
    assert worker_ner._clean_raw_text("   ") == ""


# ==========================================
# 1b. BLOCKED-NAME MATCHING
# ==========================================


def _token(*words: str) -> worker_ner.EntityBlacklist:
    """A blacklist whose words match on token boundaries, the default for a stopword."""
    return worker_ner.EntityBlacklist(exact=frozenset(), token=frozenset(words))


def _exact(*words: str) -> worker_ner.EntityBlacklist:
    """A blacklist whose words match the spelling alone: an exclusion or an EXACT stopword."""
    return worker_ner.EntityBlacklist(exact=frozenset(words), token=frozenset())


def test_is_blocked_entity_name_matches_exactly():
    assert worker_ner.is_blocked_entity_name("IPTU", _token("iptu"))


def test_is_blocked_entity_name_matches_a_token_inside_a_merged_entity():
    """Regression, found with the real spaCy engine.

    Excluding "iptu" but matching the name exactly let the model's merged output
    ("IPTU do Batel") straight through — the false positive survived the exclusion.
    """
    assert worker_ner.is_blocked_entity_name("IPTU do Batel", _token("iptu"))


def test_is_blocked_entity_name_respects_token_boundaries():
    """A legitimate name that merely contains the letters must never be blocked."""
    assert not worker_ner.is_blocked_entity_name("Iptuana", _token("iptu"))
    assert not worker_ner.is_blocked_entity_name("Prefeitura de Curitiba", _token("iptu"))


def test_an_exclusion_blocks_the_spelling_and_not_the_names_that_contain_it():
    """
    #160: the conflict was about the tag ``casa``, not about ``casa da memória``.

    An exclusion is a person's decision that a spelling belongs to the subject axis; matching it by
    token rejected 47 entity names in the reference collection.
    """
    assert worker_ner.is_blocked_entity_name("casa", _exact("casa"))
    assert not worker_ner.is_blocked_entity_name("casa da memória", _exact("casa"))


def test_an_exact_stopword_blocks_the_word_and_not_the_street():
    """`alameda` alone is noise; `Alameda Cabral` is a name — the mode is how the curator says which."""
    blacklist = _exact("alameda")
    assert worker_ner.is_blocked_entity_name("alameda", blacklist)
    assert not worker_ner.is_blocked_entity_name("Alameda Cabral", blacklist)


def test_is_blocked_entity_name_ignores_empty_blacklist():
    assert not worker_ner.is_blocked_entity_name(
        "IPTU", worker_ner.EntityBlacklist(exact=frozenset(), token=frozenset())
    )


# ==========================================
# 2. WORKER ORCHESTRATION TESTS
# ==========================================

# The blacklist is loaded from the database; we isolate it to avoid depending on a real session.
BLACKLIST_PATH = "scrinalia.domains.archive.workers.worker_ner.load_entity_blacklist"


def _mock_session(mocker: MockerFixture):
    mock_db = mocker.MagicMock(spec=Session)
    mock_db.scalar.return_value = 1
    # The approved-excerpt catalogue is read from the same session: the unit test owns an
    # empty one, so the composed text arrives exactly as the query returned it.
    mocker.patch(
        "scrinalia.domains.archive.workers.worker_ner.TextQualityRepository"
    ).return_value.get_active_rules.return_value = []
    return mock_db


def test_worker_ner_unit_ideal_flow(mocker: MockerFixture) -> None:
    """Good Scenario: Texts are concatenated, the AI extracts and the repository saves."""
    mock_db = _mock_session(mocker)

    mock_repo_class = mocker.patch("scrinalia.domains.archive.workers.worker_ner.EntityRepository")
    mock_get_engine = mocker.patch("scrinalia.domains.archive.workers.worker_ner.get_engine")
    mock_flag_modified = mocker.patch("scrinalia.domains.archive.workers.worker_ner.flag_modified")
    mocker.patch(BLACKLIST_PATH, return_value=worker_ner.EntityBlacklist(exact=frozenset(), token=frozenset()))

    mock_repo = mock_repo_class.return_value
    mock_repo.get_ner_synonyms_rules.return_value = []
    mock_repo.get_or_create_entities.return_value = [101]

    mock_ner_engine = mock_get_engine.return_value
    mock_ner_engine.extract.return_value = [[ArchiveEntityDTO(name="Prefeitura", entity_type="ORG")]]
    # The producer identity reads the engine configuration through ``describe_config``.
    mocker.patch(
        "scrinalia.domains.archive.workers.worker_ner.describe_config",
        return_value={"model": "falso", "device": "cpu"},
    )

    # 1 document on the first round, empty on the second to break the while
    test_doc = MockArchiveDocument("doc-1", "Ofício", "Conteúdo sobre obras.")
    mock_db.execute.return_value.all.side_effect = [[(test_doc, "Ofício. Conteúdo sobre obras.")], []]

    worker_ner.execute(db=mock_db, engine_name="spacy_ner")

    # AI verifications: contextualized and cleaned text
    mock_ner_engine.extract.assert_called_once()
    args, _ = mock_ner_engine.extract.call_args
    assert args[0] == ["Ofício. Conteúdo sobre obras."]

    # Persistence verifications
    mock_repo.get_or_create_entities.assert_called_once()
    mock_repo.bulk_link_entities.assert_called_once_with([EntityLinkCommand(description_id="doc-1", entity_id=101)])

    # Was the success stamp applied in the document's memory? It is the producer identity, not a
    # status: another extractor has to put the document back in the queue.
    stamp = test_doc.execution_log["worker_ner_v2"]  # type: ignore
    assert stamp != "DONE"
    assert len(stamp) == 64
    mock_flag_modified.assert_called_once_with(test_doc, "execution_log")
    mock_db.commit.assert_called_once()


def test_worker_ner_ignores_empty_texts(mocker: MockerFixture) -> None:
    """Good Scenario: If the document only has whitespace or URLs, it stamps it as DONE and skips the AI."""
    mock_db = _mock_session(mocker)

    mocker.patch("scrinalia.domains.archive.workers.worker_ner.EntityRepository")
    mock_get_engine = mocker.patch("scrinalia.domains.archive.workers.worker_ner.get_engine")
    mock_flag_modified = mocker.patch("scrinalia.domains.archive.workers.worker_ner.flag_modified")
    mocker.patch(BLACKLIST_PATH, return_value=worker_ner.EntityBlacklist(exact=frozenset(), token=frozenset()))

    # Document that, after removing the email, becomes empty
    empty_doc = MockArchiveDocument("doc-2", "   ", "contato@email.com")
    mock_db.execute.return_value.all.side_effect = [[(empty_doc, "contato@email.com")], []]

    worker_ner.execute(db=mock_db)

    # The AI must NOT have been triggered, to avoid wasting processing for nothing
    mock_get_engine.return_value.extract.assert_not_called()

    # But the document MUST be stamped so it does not loop forever in the queue
    assert len(empty_doc.execution_log["worker_ner_v2"]) == 64  # type: ignore
    mock_flag_modified.assert_called_once()


def test_worker_ner_ai_failure_rolls_back(mocker: MockerFixture) -> None:
    """Bad Scenario: If spaCy runs out of memory (Exception), the transaction aborts and the loop breaks."""
    mock_db = _mock_session(mocker)

    mocker.patch("scrinalia.domains.archive.workers.worker_ner.EntityRepository")
    mock_get_engine = mocker.patch("scrinalia.domains.archive.workers.worker_ner.get_engine")
    mocker.patch(BLACKLIST_PATH, return_value=worker_ner.EntityBlacklist(exact=frozenset(), token=frozenset()))

    test_doc = MockArchiveDocument("doc-3", "Texto válido para forçar a IA a rodar")
    mock_db.execute.return_value.all.side_effect = [[(test_doc, "Texto válido para forçar a IA a rodar")], []]

    # Force the NLP engine to explode
    mock_get_engine.return_value.extract.side_effect = Exception("Out of Memory")

    worker_ner.execute(db=mock_db)

    # The rollback must have been called to protect the database
    mock_db.rollback.assert_called()

    # The stamp must NOT be applied (remains None), since the whole batch failed at inference
    assert test_doc.execution_log is None


def test_worker_ner_repository_failure_stamps_error(mocker: MockerFixture) -> None:
    """Bad Scenario (Resilience): The AI works, but the database refuses the insert. Stamps with ERROR and moves on."""
    mock_db = _mock_session(mocker)

    mock_repo_class = mocker.patch("scrinalia.domains.archive.workers.worker_ner.EntityRepository")
    mock_get_engine = mocker.patch("scrinalia.domains.archive.workers.worker_ner.get_engine")
    mock_flag_modified = mocker.patch("scrinalia.domains.archive.workers.worker_ner.flag_modified")
    mocker.patch(BLACKLIST_PATH, return_value=worker_ner.EntityBlacklist(exact=frozenset(), token=frozenset()))

    # Simulate that the AI found 1 entity
    mock_get_engine.return_value.extract.return_value = [[ArchiveEntityDTO(name="Prefeitura", entity_type="ORG")]]

    test_doc = MockArchiveDocument("doc-4", "Texto válido")
    mock_db.execute.return_value.all.side_effect = [[(test_doc, "Texto válido")], []]

    # Force a structural failure (e.g., Foreign Key error) when saving the entity
    mock_repo_class.return_value.get_or_create_entities.side_effect = Exception("DB Constraints Failed")

    worker_ner.execute(db=mock_db)

    # Did the anti-infinite-loop shield work? The document MUST be stamped with ERROR.
    assert test_doc.execution_log["worker_ner_v2"] == "ERROR"  # type: ignore
    mock_flag_modified.assert_called_once()

    # The batch moves on and commits the others (or the error itself in the log)
    mock_db.commit.assert_called()
