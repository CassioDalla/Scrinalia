import re
from datetime import date
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from memoria_curitibana.domains.staging.dates import parse_document_date


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
        - Dynamic Parser: Maps variable collection keys to fixed attributes.
        - Sanitization: Cleans up double spaces and converts "false nulls" (e.g., "n/a") to native `None`.
        - Type Extraction: Applies Regex to infer and convert dates into `datetime.date` objects.
        - Preservation (Data Lake Approach): Any unmapped or unknown key is
        safely isolated within the `raw_metadata` dictionary, ensuring zero data loss.
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

    # TODO add cleaning of " -  : ;" as tag separators

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
        "title",
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
        if not v:
            return None

        clean_text = re.sub(r"\s+", " ", str(v)).strip()

        if clean_text.lower() in ["", "não informado", "n/a", "-", "nenhum"]:
            return None

        return clean_text

    @model_validator(mode="before")
    @classmethod
    def map_raw_to_staging(cls, data: dict[str, Any]) -> dict[str, Any]:
        """
        Pre-processor executed before Pydantic's strict validation (mode="before").

        Inspects the dictionary received from the database (RawData), accesses the 'payload'
        field, and maps keys extracted from the HTML to the class's strongly typed attributes.
        Concatenates values ​​in the event of duplicate keys in the source and isolates extraneous
        data or unexpected fields in 'raw_metadata'.
        """

        if "payload" not in data:
            return data

        payload = data.get("payload", {})

        staging_data = {
            "description_id": data.get("description_id"),
            "raw_content_hash": data.get("content_hash"),
            "title": data.get("raw_title") or payload.get("title") or "SEM TÍTULO",
            "original_url": payload.get("_url_origem"),
            "attachment_link": payload.get("attch_down_link"),
            "raw_metadata": {},
        }

        raw_date = payload.get("Data de Produção") or payload.get("Data")
        if raw_date:
            parsed_date = parse_document_date(raw_date)
            if parsed_date:
                staging_data["document_date"] = parsed_date

        # From -> To Mapping (ISAD-G)
        # If the key on the left exists in the JSON, assign it to the attribute on the right
        keys_map = {
            "Código de Referência": "reference_code",
            "Nível de Descrição": "level",
            "Unidade de Descrição Superior": "parent_reference_code",
            "Unidade de Descrição Pai": "parent_reference_code",
            "Nível Superior": "parent_reference_code",
            "Código da Unidade Superior": "parent_reference_code",
            "Caminho Hierárquico": "hierarchy_path",
            "Dimensão e Suporte": "dimension_support",
            "Produtor": "producers",
            "História Administrativa": "admin_bio_history",
            "História Arquivística": "admin_archival_history",
            "Procedência": "provenance",
            "Âmbito e Conteúdo": "scope_content",
            "Avaliação e Temporalidade": "appraisal_destruction",
            "Incorporações": "accruals",
            "Sistema de Arranjo": "arrangement",
            "Acesso Público": "access_conditions",
            "Condições de Acesso": "access_conditions",
            "Condições de Reprodução": "reproduction_conditions",
            "Idioma": "language_name",
            "Características Físicas": "physical_characteristics",
            "Instrumentos de Pesquisa": "finding_aids",
            "Localização dos Originais": "originals_location",
            "Localização das Cópias": "copies_location",
            "Unidades de Descrição Relacionadas": "related_units",
            "Notas de Publicação": "publication_notes",
            "Notas de Conservação": "conservation_notes",
            "Notas Gerais": "general_notes",
            "Notas do Arquivista": "archivist_notes",
            "Regras ou Convenções": "rules_conventions",
            "Datas da Descrição": "description_dates",
            "Pontos de Acesso": "indexing_points",
            "thumb_down_link": "thumb_down_link",
        }

        mapped_keys = ["_url_origem", "attch_down_link", "Data", "Data de Produção", "title"]

        for html_key, value in payload.items():
            if html_key in keys_map:
                pydantic_attribute_name = keys_map[html_key]
                if staging_data.get(pydantic_attribute_name):
                    staging_data[pydantic_attribute_name] += f" | {value}"
                else:
                    staging_data[pydantic_attribute_name] = value
                mapped_keys.append(html_key)

        # The Unknown "Trash" (Ensures we never lose data
        for html_key, value in payload.items():
            if html_key not in mapped_keys:
                staging_data["raw_metadata"][html_key] = value

        return staging_data
