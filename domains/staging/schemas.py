import re
from datetime import date
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


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
    reference_code: str | None = None  # Código Referência
    level: str | None = None  # Nível
    dimension_support: str | None = None  # Dimensão e Suporte
    producers: str | None = None  # Nome do(s) Produtor(es)
    admin_bio_history: str | None = None  # História Administrativa/Biográfia
    admin_archival_history: str | None = None  # História Arquivística
    provenance: str | None = None  # Procedência
    scope_content: str | None = None  # Âmbito e Conteúdo (Antigo Resumo)
    appraisal_destruction: str | None = None  # Avaliação, Eliminação e Temporalidade
    accruals: str | None = None  # Incorporações
    arrangement: str | None = None  # Sistema de Arranjo
    access_conditions: str | None = None  # Acesso Público / Condições de Acesso
    reproduction_conditions: str | None = None  # Condições de Reprodução
    language_name: str | None = None  # Idioma
    physical_characteristics: str | None = None  # Características físicas e requisitos técnicos
    finding_aids: str | None = None  # Instrumentos de pesquisa
    originals_location: str | None = None  # Existência e localização dos originais
    copies_location: str | None = None  # Existência e localização de cópias
    related_units: str | None = None  # Unidades de Descrição relacionadas
    publication_notes: str | None = None  # Notas sobre publicação
    conservation_notes: str | None = None  # Notas sobre conservação
    general_notes: str | None = None  # Notas gerais
    archivist_notes: str | None = None  # Notas do Arquivista
    rules_conventions: str | None = None  # Regras ou convenções
    description_dates: str | None = None  # Data(s) da(s) descrição(ões)
    indexing_points: str | None = None  # Pontos de Acesso e Indexação de Assuntos

    # Anything not mapped above falls here
    raw_metadata: dict[str, Any] = Field(default_factory=dict)

    # TODO adicionar limpeza de " -  : ;" como separadores de tags

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
            data_str = str(raw_date).strip()

            # Padrão 1: ISO 8601 ou YYYY-MM-DD (ex: 1929-07-05T03:00:00Z)
            match_iso = re.search(r"(\d{4})-(\d{2})-(\d{2})", data_str)
            # Padrão 2: Brasileiro DD/MM/YYYY (ex: 05/07/1929)
            match_br = re.search(r"(\d{2})/(\d{2})/(\d{4})", data_str)
            # Padrão 3: Apenas o Ano (ex: 1924)
            match_ano = re.search(r"^(\d{4})$", data_str)

            try:
                if match_iso:
                    ano, mes, dia = map(int, match_iso.groups())
                    staging_data["document_date"] = date(ano, mes, dia)
                elif match_br:
                    dia, mes, ano = map(int, match_br.groups())
                    staging_data["document_date"] = date(ano, mes, dia)
                elif match_ano:
                    ano = int(match_ano.group(1))
                    staging_data["document_date"] = date(ano, 1, 1)  # Define como 1º de Janeiro do ano
            except ValueError:
                pass

        # From -> To Mapping (ISAD-G)
        # If the key on the left exists in the JSON, assign it to the attribute on the right
        keys_map = {
            "Código de Referência": "reference_code",
            "Nível de Descrição": "level",
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
                name_attribute_pydantic = keys_map[html_key]
                if staging_data.get(name_attribute_pydantic):
                    staging_data[name_attribute_pydantic] += f" | {value}"
                else:
                    staging_data[name_attribute_pydantic] = value
                mapped_keys.append(html_key) 

        # The Unknown "Trash" (Ensures we never lose data
        for html_key, value in payload.items():
            if html_key not in mapped_keys:
                staging_data["raw_metadata"][html_key] = value

        return staging_data
