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
