import enum


class ArchiveReviewStatus(enum.StrEnum):
    """
    Controls the lifecycle of human validation
    over the AI's work.
    """

    PENDING_AI = "PENDING_AI"  # Waiting for the AI pipelines to run
    AI_APPROVED = "AI_APPROVED"  # The AI corrected/classified with high confidence
    NEEDS_REVIEW = "NEEDS_REVIEW"  # The AI found an anomaly or had low confidence
    HUMAN_APPROVED = "HUMAN_APPROVED"  # The human validated or corrected manually (Blocks AI Editing)
    REJECTED = "REJECTED"  # The human decided the data is garbage


class ArchiveEntityOrigin(enum.StrEnum):
    """
    Who wrote a document-entity link.

    ``UNKNOWN`` is not a synonym for ``AI``: it is what the links written before this column existed
    carry, because the schema cannot prove which producer wrote them and a migration that guessed
    would invent the very fact the column exists to keep. A link created by a vocabulary operation —
    a merge, a restore, a conflict resolution — is also ``UNKNOWN``: it was not an extraction and not
    a person reading a description.
    """

    AI = "AI"
    HUMAN = "HUMAN"
    UNKNOWN = "UNKNOWN"


class StopwordsScope(enum.StrEnum):
    """Which axis a banned term leaves: TAG (the subject axis), ENTITY (NER) or ALL (both)."""

    # The scope is not decoration. ``domain_stopwords.word`` is unique, so a term lives on exactly
    # one axis, and ``TagRepository.get_stopwords()`` reads only TAG/ALL: an ENTITY-scoped veto must
    # never make the subject purge delete a tag the curator kept. The screen shows the scope because
    # otherwise the two mechanisms look like one list and the archivist stops trusting it.
    TAG = "TAG"  # Applied as a stopword only to tags
    ENTITY = "ENTITY"  # Vetoes the NER extraction only
    ALL = "ALL"  # Both axes


class AnomalyType(enum.StrEnum):
    CROSS_DOMAIN_COLLISION = "CROSS_DOMAIN_COLLISION"
    #: The subject classifier was not confident enough to give the tag a drawer, so it stays
    #: orphan and a curator decides. Measured on the labelled set, the confidence separates a
    #: right answer from a wrong one by ~0.25 (0.705 vs 0.455 on bare names), which is what
    #: makes routing on it meaningful instead of cosmetic. An empty badge beats a wrong badge
    #: in a UI that is about to amplify both.
    SUBJECT_LOW_CONFIDENCE = "SUBJECT_LOW_CONFIDENCE"
    #: The typology classifier looked at the description and refused to give it a drawer: the score
    #: stayed under the floor. The document keeps ``typology_id`` NULL, so without this row the
    #: refusal is indistinguishable from a description the run never reached — and the score that
    #: justified it is lost, which is the one number a floor decision needs.
    #:
    #: It is a row in the queue and not a stamp value on purpose. ``identity_stamp_conditions``
    #: computes pending as "the stamp is not this identity", so a distinct refusal value either puts
    #: the document back in the queue forever or — added to ``FAILURE_STAMP_VALUES`` — stops a floor
    #: change from reaching it at all. The stamp means "this producer read it"; the refusal is
    #: evidence, and evidence lives in the queue (#110).
    TYPOLOGY_LOW_CONFIDENCE = "TYPOLOGY_LOW_CONFIDENCE"


class TagCatalogState(enum.StrEnum):
    """
    Which slice of the tag catalogue one read asks for, by the state of its subject decision.

    The decision has three parts and they are a **partition**: a tag is in a drawer, declared not a
    subject, or nobody has decided yet. This filter names the two that are states of the *catalogue*
    — the drawer is reached with ``macro_category_id`` — and ``ALL`` is not a state at all but the
    absence of a filter. The predicates live in one module (``repository/subject_queue.py``) and the
    home screen's counters read the same ones, because the number a card promises has to be the number
    the list it opens reports.

    ``LOW_CONFIDENCE`` is the one that is not a state of the tag but of the *work*: the classifier
    ran, was not confident enough to file the tag, and left a row in ``archive_ai_review_queue``.
    It is a subset of ``PENDING`` on purpose — the archivist's two cards answer two questions about
    the same queue, and either one may take the decision.

    A place, a producer or a person is **not** a fourth state: it is a tag the subject axis does not
    answer for, so it is declared not a subject and its spelling is banned from coming back, while the
    entity axis carries what it is (ADR 0013). ``FACET`` used to express that distinction here, and the
    distinction had no reader beyond the chip itself — the entity already reaches the description with
    a type the search facet and the public projection both use.
    """

    #: Everything, paginated. The screen's default, and the only one that is not a filter.
    ALL = "ALL"
    #: No drawer and no verdict: the work the home screen counts.
    PENDING = "PENDING"
    #: A person declared the tag belongs to no subject drawer, and its spelling is banned from
    #: becoming a tag again.
    NOT_SUBJECT = "NOT_SUBJECT"
    #: Queued by the classifier below its confidence floor, still undecided.
    LOW_CONFIDENCE = "LOW_CONFIDENCE"


class CollectionTermKind(enum.StrEnum):
    """
    What a term of the collection is, when it is not a subject.

    The subject guard refuses a term for one of five shapes. Three of them are properties of
    the *language* (a placeholder, a bare year, a measure) and two are properties of the
    *collection*: a toponym it carries as a place and a person name it carries as a name. The
    second family used to be a regex inside ``domain/vocabulary.py`` holding the city's bairros
    and fifteen names; they are rows now because another institution's collection
    carries other names, and a regex cannot be edited by the archivist.

    The kind is stored instead of a boolean "is a place" because the finest rung is the one
    the facet is asked about — a bairro and a country are both places, and only one of them is
    "where in the city". ``PERSON`` is deliberately not a place: the name goes nowhere, it is
    the producer.
    """

    #: A bairro: the finest place the collection declares.
    DISTRICT = "DISTRICT"
    #: A municipality (``cidade``, ``vila exemplo``), including a foreign city.
    MUNICIPALITY = "MUNICIPALITY"
    #: A state or province (``estado exemplo``, ``província exemplo``).
    STATE = "STATE"
    #: A region broader than a municipality (``região exemplo``).
    REGION = "REGION"
    #: A country the collection's records reach (``país exemplo``).
    COUNTRY = "COUNTRY"
    #: A person's name: a producer or the person depicted, never a subject.
    PERSON = "PERSON"


#: The kinds that claim the PLACE facet. ``PERSON`` is excluded on purpose: ``is_place_term``
#: answers "where does this go", and a name goes nowhere as a place.
PLACE_TERM_KINDS: tuple[CollectionTermKind, ...] = (
    CollectionTermKind.DISTRICT,
    CollectionTermKind.MUNICIPALITY,
    CollectionTermKind.STATE,
    CollectionTermKind.REGION,
    CollectionTermKind.COUNTRY,
)


class AnomalyReason(enum.StrEnum):
    """
    Why the structural validator marked a document.

    Stored as text inside ``ArchiveDocument.anomaly_reasons`` (an ARRAY), so these are
    stable codes rather than prose: the front-end and the API can group and translate them,
    and the archivist still sees the free reason attached to a matched rule.
    """

    MISSING_DATE = "MISSING_DATE"
    FUTURE_DATE = "FUTURE_DATE"
    EMPTY_TITLE = "EMPTY_TITLE"
    ALL_CAPS_TITLE = "ALL_CAPS_TITLE"
    REPEATED_TITLE = "REPEATED_TITLE"
    TITLE_ONLY_TEMPLATE = "TITLE_ONLY_TEMPLATE"
    SCOPE_ONLY_BOILERPLATE = "SCOPE_ONLY_BOILERPLATE"
    NO_TAGS = "NO_TAGS"
    NO_TYPOLOGY = "NO_TYPOLOGY"
    NO_ENTITIES = "NO_ENTITIES"
    #: A ``VALIDATE`` regex registered by an archivist matched; the rule name follows.
    RULE_MATCH = "RULE_MATCH"
    #: The optional language-model check considered the title suspicious.
    LLM_SUSPECT = "LLM_SUSPECT"


#: Separates an anomaly code from its payload inside ``ArchiveDocument.anomaly_reasons``:
#: ``RULE_MATCH:<rule label>`` names the rule that matched, ``LLM_SUSPECT:<free text>`` carries the
#: model's own words. Defined next to the codes because the column stores this format, and read by
#: the worker that writes it, the facet that groups by it and the bench that scores it, so the three
#: cannot disagree about where the code ends.
ANOMALY_REASON_SEPARATOR = ":"


def anomaly_reason_code(reason: str) -> str:
    """The stable code of a stored reason, without its payload."""
    return reason.partition(ANOMALY_REASON_SEPARATOR)[0]


def anomaly_reason_payload(reason: str) -> str:
    """What follows the code — the rule's label, or the model's free text. Empty when there is none."""
    return reason.partition(ANOMALY_REASON_SEPARATOR)[2]


class WorkerRunStatus(enum.StrEnum):
    """
    Lifecycle of one execution of an AI worker.

    ``QUEUED`` exists so the ledger does not lie about the start time: the executor accepts a
    single run at a time, so a submitted run may wait before it actually starts. ``INTERRUPTED`` is
    written by the next start-up for a row the previous process left behind — without it the row
    would stay ``RUNNING`` forever, and the partial unique index would block that worker for good.
    """

    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    INTERRUPTED = "INTERRUPTED"


class WorkerRunTrigger(enum.StrEnum):
    """Who asked for the run: the command line or the curator's panel."""

    CLI = "CLI"
    API = "API"


class FailureSource(enum.StrEnum):
    """
    Which ledger a failure came from.

    ``WORKER`` is one execution in ``archive_worker_runs``; ``API`` is an unexpected HTTP failure in
    ``archive_api_errors``. A group can carry **both**, because the fingerprint is the same function
    over both messages — a cause that broke a worker and a request is one root cause, and splitting
    it would send the reader to two screens to learn a single thing.
    """

    WORKER = "WORKER"
    API = "API"


#: Statuses that mean "this worker has a run in flight". The partial unique index on
#: ``archive_worker_runs`` uses exactly this set, so a second run cannot be queued for the same
#: worker — the guarantee is in the database, not in a process-local lock that a reload would drop.
ACTIVE_WORKER_RUN_STATUSES: tuple[WorkerRunStatus, ...] = (WorkerRunStatus.QUEUED, WorkerRunStatus.RUNNING)
