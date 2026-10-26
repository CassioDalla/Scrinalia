"""The vocabulary of a record a person typed.

The manual origin has no site and no HTML: its *payload keys* are the ISAD(G) field names the form
sends. They still live in a ``SourceSchema`` beside the adapter, and not in the staging transform,
for the same reason every other origin's labels do: a source's vocabulary is that source's, and the
transform must not learn it. The fact that these labels read like the staging attributes is a
property of this form, not a shortcut the transform takes.

``title`` and ``document_date`` are consumed through the schema's own keys (``title_key`` and
``date_keys``) instead of through ``field_map``; the rest of the form maps one-to-one.
"""

from scrinalia.domains.ingestion.ports import SourceSchema

#: Every field the manual form may send, in the order the dossier shows the record.
#:
#: It is the request model's field set minus the three the service handles itself — ``title`` and
#: ``document_date`` (consumed through the schema's own keys) and ``description_id`` (the record's
#: identity, outside the payload). A test pins the equality, because ``_manual_payload`` iterates
#: this tuple: a field added to the model and forgotten here would be dropped in silence.
#:
#: ``hierarchy_path`` is absent: the arrangement is the parent's code, and the path is the archive's
#: to derive. ``attachment_link`` is absent: nothing reads it until the digital object exists (#198).
MANUAL_FIELDS: tuple[str, ...] = (
    "reference_code",
    "level",
    "parent_reference_code",
    "dimension_support",
    "producers",
    "admin_bio_history",
    "admin_archival_history",
    "provenance",
    "scope_content",
    "appraisal_destruction",
    "accruals",
    "arrangement",
    "access_conditions",
    "reproduction_conditions",
    "language_name",
    "physical_characteristics",
    "finding_aids",
    "originals_location",
    "copies_location",
    "related_units",
    "publication_notes",
    "conservation_notes",
    "general_notes",
    "archivist_notes",
    "rules_conventions",
    "indexing_points",
    "original_url",
    "thumb_down_link",
)

MANUAL_SOURCE_SCHEMA = SourceSchema(
    code="manual",
    field_map={field: field for field in MANUAL_FIELDS},
    title_key="title",
    # The manual adapter does not write a source URL under the scraper's private key: the form's
    # ``original_url`` is an ordinary mapped field above. The attachment key is unused — the manual
    # origin has nothing to attach until the digital object exists (#198).
    url_key="_manual_url",
    attachment_key="_manual_attachment",
    date_keys=("document_date",),
)
