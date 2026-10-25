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

#: Every field the manual form may send. It is also the vocabulary the manual service validates the
#: body against; a new form field is a line here and a line in the request model.
MANUAL_FIELDS: tuple[str, ...] = (
    "reference_code",
    "level",
    "parent_reference_code",
    "hierarchy_path",
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
    "description_dates",
    "indexing_points",
    "original_url",
    "attachment_link",
    "thumb_down_link",
)

MANUAL_SOURCE_SCHEMA = SourceSchema(
    code="manual",
    field_map={field: field for field in MANUAL_FIELDS},
    title_key="title",
    # The manual adapter does not write a source URL or an attachment under the scraper's private
    # keys: the form's ``original_url`` and ``attachment_link`` are ordinary mapped fields above.
    url_key="_manual_url",
    attachment_key="_manual_attachment",
    date_keys=("document_date",),
)
