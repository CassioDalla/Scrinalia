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


class StopwordsScope(enum.StrEnum):
    """
    Controls the scope of a domain stopword
    """

    TAG = "TAG"  # Applied as a stopword only to tags
    ENTITY = "ENTITY"
    ALL = "ALL"


class AnomalyType(enum.StrEnum):
    CROSS_DOMAIN_COLLISION = "CROSS_DOMAIN_COLLISION"
    #: The subject classifier was not confident enough to give the tag a drawer, so it stays
    #: orphan and a curator decides. Measured on the labelled set, the confidence separates a
    #: right answer from a wrong one by ~0.25 (0.705 vs 0.455 on bare names), which is what
    #: makes routing on it meaningful instead of cosmetic. An empty badge beats a wrong badge
    #: in a UI that is about to amplify both.
    SUBJECT_LOW_CONFIDENCE = "SUBJECT_LOW_CONFIDENCE"


class TagFacetType(enum.StrEnum):
    """
    Which non-subject axis a tag belongs to.

    ``ArchiveTag.macro_category_id`` answers "what is this about?". Some tags have no honest
    answer to that question but a very clear answer to a different one: ``ippuc`` is *who
    produced*, ``curitiba`` is *where*. Before this existed those terms competed with
    ``alvenaria`` for the same subject drawer, which is a measured cause of the systematic
    misclassification (``alvenaria`` landing in "Mobilidade e Transporte").

    Deliberately a separate table rather than a second column: a tag carries at most one
    subject but can carry a place *and* an institution at once.
    """

    #: The producer or the body the record is about (``ippuc``, ``pmc``, ``urbs``).
    INSTITUTION = "INSTITUTION"
    #: A toponym or a street address (``curitiba``, ``centro``, ``rua xv de novembro``).
    PLACE = "PLACE"


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


#: Statuses that mean "this worker has a run in flight". The partial unique index on
#: ``archive_worker_runs`` uses exactly this set, so a second run cannot be queued for the same
#: worker — the guarantee is in the database, not in a process-local lock that a reload would drop.
ACTIVE_WORKER_RUN_STATUSES: tuple[WorkerRunStatus, ...] = (WorkerRunStatus.QUEUED, WorkerRunStatus.RUNNING)
