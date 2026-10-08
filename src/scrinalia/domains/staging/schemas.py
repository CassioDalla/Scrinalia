import re
from datetime import date
from typing import Any

from pydantic import BaseModel, Field, ValidationInfo, field_validator, model_validator

from scrinalia.core.language import get_language
from scrinalia.domains.ingestion.ports import SourceSchema
from scrinalia.domains.staging.dates import parse_document_date

#: The context key the origin's vocabulary travels under. Named once so the transform and its
#: callers cannot disagree about it.
SOURCE_SCHEMA_CONTEXT_KEY = "source_schema"


class RawRecord(BaseModel):
    """
    Raw record delivered by the Ingestion layer and consumed by the staging transform.

    Input-port DTO: it carries exactly the columns the staging use case needs from
    ``RawData`` (the original payload plus the CDC content hash), so the application
    layer never imports the ingestion ORM.
    """

    description_id: str
    content_hash: str
    payload: dict[str, Any]
    raw_title: str | None = None


class StagingDocumentDTO(BaseModel):
    """
    Staging layer validation and transformation contract (Schema/DTO).

    Acts as the "Transform" engine of the ETL process. It intercepts the raw,
    unpredictable dictionary extracted from the source (RawData) and converts
    it into a rigorous relational entity aligned with the ISAD(G) archival standard.

    Responsibilities:
        - Dynamic Parser: maps the **origin's** field labels to fixed attributes, using the
          ``SourceSchema`` handed in as validation context. The labels are the site's and are never
          translated; they live with the adapter that reads them, not here.
        - Sanitization: cleans up double spaces and converts "false nulls" (e.g., "n/a") to native
          ``None``, reading the spellings from the active language profile.
        - Type Extraction: applies Regex to infer and convert dates into `datetime.date` objects.
        - Preservation (Data Lake Approach): any unmapped or unknown key is
        safely isolated within the `raw_metadata` dictionary, ensuring zero data loss.

    The schema is **required**: without it the transform has no idea which label fills which column,
    so it refuses to run rather than filing everything as unknown. The pipeline always passes one
    (see ``run_staging_pipeline``); a missing context is a wiring defect, not a data problem.
    """

    description_id: str
    raw_content_hash: str

    # --- First-Class Columns ---
    title: str
    document_date: date | None = None
    original_url: str | None = None
    attachment_link: str | None = None
    thumb_down_link: str | None = None

    # --- ISAD(G) Standard Metadata (Treated as Flexible Strings) ---
    reference_code: str | None = None  # Reference Code
    parent_reference_code: str | None = None  # Reference code of the superior unit
    hierarchy_path: str | None = None  # Full path of codes, root first
    level: str | None = None  # Level
    dimension_support: str | None = None  # Extent and Medium
    producers: str | None = None  # Name of the Producer(s)
    admin_bio_history: str | None = None  # Administrative/Biographical History
    admin_archival_history: str | None = None  # Archival History
    provenance: str | None = None  # Provenance
    scope_content: str | None = None  # Scope and Content (Former Summary)
    appraisal_destruction: str | None = None  # Appraisal, Destruction and Scheduling
    accruals: str | None = None  # Accruals
    arrangement: str | None = None  # System of Arrangement
    access_conditions: str | None = None  # Public Access / Conditions of Access
    reproduction_conditions: str | None = None  # Conditions of Reproduction
    language_name: str | None = None  # Language
    physical_characteristics: str | None = None  # Physical Characteristics and Technical Requirements
    finding_aids: str | None = None  # Finding Aids
    originals_location: str | None = None  # Existence and Location of Originals
    copies_location: str | None = None  # Existence and Location of Copies
    related_units: str | None = None  # Related Units of Description
    publication_notes: str | None = None  # Notes on Publication
    conservation_notes: str | None = None  # Notes on Conservation
    general_notes: str | None = None  # General Notes
    archivist_notes: str | None = None  # Archivist's Notes
    rules_conventions: str | None = None  # Rules or Conventions
    description_dates: str | None = None  # Date(s) of the Description(s)
    indexing_points: str | None = None  # Access Points and Subject Indexing

    # Anything not mapped above falls here
    raw_metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("indexing_points", mode="before")
    @classmethod
    def standardize_tags_delimiter(cls, v: str | None) -> str | None:
        """
        Ensures that all tags are separated by clean commas,
        regardless of whether the archivist used semicolons or multiple spaces.
        """
        if not v:
            return None

        text = str(v).replace(";", ",")
        tags_list = [tag.strip() for tag in text.split(",") if tag.strip()]

        return ", ".join(tags_list) if tags_list else None

    @field_validator(
        "reference_code",
        "parent_reference_code",
        "hierarchy_path",
        "level",
        "dimension_support",
        "producers",
        "admin_bio_history",
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
        "admin_archival_history",
        mode="before",
    )
    @classmethod
    def clean_text_fields(cls, v: Any) -> str | None:
        """
        Collapses whitespace and turns the language's false nulls into ``None``.

        The spellings come from the active language profile, not from a list here: ``não informado``
        used to be declared in three places (this one, the date parser and the subject guard), so a
        fourth spelling added in one of them was silently not a false null in the others.

        ``title`` is deliberately **not** in this list. It is a required field, so a placeholder
        title would fail validation and the whole document would be dropped — measured: a payload
        with ``"não informado"`` as the title was rejected by staging. The title has its own rule in
        the mapping, where the language's placeholder is the fallback.
        """
        if not v:
            return None

        clean_text = re.sub(r"\s+", " ", str(v)).strip()

        if clean_text.lower() in get_language().false_null_values:
            return None

        return clean_text

    @model_validator(mode="before")
    @classmethod
    def map_raw_to_staging(cls, data: dict[str, Any], info: ValidationInfo) -> dict[str, Any]:
        """
        Pre-processor executed before Pydantic's strict validation (mode="before").

        Inspects the dictionary received from the database (RawData), accesses the 'payload'
        field, and maps the origin's own labels to the class's strongly typed attributes using the
        ``SourceSchema`` carried in the validation context. Concatenates values in the event of
        duplicate keys in the source and isolates extraneous data or unexpected fields in
        'raw_metadata'.

        Nothing here knows which site it is reading: the labels, the adapter's private keys and the
        date fields all come from the schema. That is what lets a second origin be a second schema
        instead of an edit to this method.
        """
        if "payload" not in data:
            return data

        schema: SourceSchema | None = (info.context or {}).get(SOURCE_SCHEMA_CONTEXT_KEY)
        if schema is None:
            raise ValueError(
                "The staging transform needs the origin's SourceSchema to know which label fills "
                "which column. Pass it as validation context: "
                f"StagingDocumentDTO.model_validate(data, context={{'{SOURCE_SCHEMA_CONTEXT_KEY}': schema}})."
            )

        payload = data.get("payload", {})

        staging_data: dict[str, Any] = {
            "description_id": data.get("description_id"),
            "raw_content_hash": data.get("content_hash"),
            "title": _title_or_placeholder(data.get("raw_title") or payload.get(schema.title_key)),
            "original_url": payload.get(schema.url_key),
            "attachment_link": payload.get(schema.attachment_key),
            "raw_metadata": {},
        }

        raw_date = next((payload[key] for key in schema.date_keys if payload.get(key)), None)
        if raw_date:
            parsed_date = parse_document_date(raw_date)
            if parsed_date:
                staging_data["document_date"] = parsed_date

        # The keys the adapter itself wrote are consumed, not "unknown": leaving the title or the
        # page URL in ``raw_metadata`` would duplicate every record's own identity.
        mapped_keys = {schema.url_key, schema.attachment_key, schema.title_key, *schema.date_keys}

        for source_key, value in payload.items():
            attribute = schema.field_map.get(source_key)
            if attribute is None:
                continue
            if staging_data.get(attribute):
                staging_data[attribute] += f"{schema.join_separator}{value}"
            else:
                staging_data[attribute] = value
            mapped_keys.add(source_key)

        # The Unknown "Trash" (Ensures we never lose data)
        for source_key, value in payload.items():
            if source_key not in mapped_keys:
                staging_data["raw_metadata"][source_key] = value

        return staging_data


def _title_or_placeholder(raw: Any) -> str:
    """
    The record's title, or the language's placeholder when the origin declared none.

    A title is required, and the origin uses the same "no information" spellings for it as for any
    other field. Turning those into ``None`` used to make Pydantic reject the whole document — a
    silent loss of a record whose only defect was a placeholder title.
    """
    language = get_language()
    if raw is None:
        return language.untitled_title

    cleaned = re.sub(r"\s+", " ", str(raw)).strip()
    if not cleaned or cleaned.lower() in language.false_null_values:
        return language.untitled_title
    return cleaned
