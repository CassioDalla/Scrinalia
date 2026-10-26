"""The CSV import's vocabulary, its bounds and the pure per-row validation.

The CSV origin has no site to read: its labels are the headers of the file a person exports from a
spreadsheet, and they are declared here, next to the ``SourceSchema`` that maps them to staging
columns. The map is the **single definition** of what the import accepts: the API publishes it
(``GET /api/v1/ingestion/csv/spec``), the screen validates against it, and the staging transform
consumes the same labels through ``CSV_SOURCE_SCHEMA``. A label the transform does not know is a
test failure, not a column quietly filed as unknown.

Two boundaries are deliberate:

* **The file never leaves the browser.** Only rows cross the wire; the limits below bound the
  list and the bytes it carries, and they are declared in one place so the spec, the SPA and the
  route cannot disagree about them.
* **The API is the authority.** ``validate_csv_row`` is a plan, not a write: it runs the same
  ``StagingDocumentDTO`` the staging transform will run, with the origin's schema as context. The
  screen's copy of the checks is a convenience, and the staging pipeline validates again.

What makes a row invalid is a business decision, not a parser accident: a missing title, a value
the staging model refuses, a field the map does not know, a value over the limit, or a date the
active language profile cannot read. A fuzzy date the profile *does* read (``Década de 1980``,
``1951-1953``) is a legitimate date — the grammar stays in one place.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal

from pydantic import ValidationError

from scrinalia.core.language import get_language
from scrinalia.domains.staging.dates import parse_document_date
from scrinalia.domains.staging.schemas import SOURCE_SCHEMA_CONTEXT_KEY, StagingDocumentDTO

#: How many rows one request may carry. A row is one description, and the route stages the whole
#: list before enqueuing one transfer; 500 keeps the request and the staging batch bounded.
MAX_CSV_ROWS = 500

#: The bytes one request may carry, **and** the size the screen refuses to read from disk. The
#: server cannot see the file, so this is the bound it can enforce: the serialized rows.
MAX_CSV_BYTES = 8 * 1024 * 1024

#: The bytes one row may carry. A single cell bigger than this is not a description.
MAX_CSV_ROW_BYTES = 64 * 1024

#: The characters one field may carry when the field itself declares no tighter cap. The title,
#: the reference code and the level do declare one, inherited from the manual contract.
MAX_CSV_FIELD_CHARS = 20_000

#: The control a field needs in the preview.
CsvFieldKind = Literal["text", "long_text", "date", "tags", "url"]


class CsvRowStatus(StrEnum):
    """The outcome of one row of the import, as the screen reports it."""

    ACCEPTED = "ACCEPTED"
    DUPLICATED = "DUPLICATED"
    INVALID = "INVALID"


class CsvRowIssueCode(StrEnum):
    """
    Why one row did not enter, as a stable identifier rather than a sentence.

    The codes are additive and shared by the rows that produce the same outcome; the sentence
    beside it is Portuguese and can be translated later without renaming the code.
    """

    MISSING_REQUIRED = "MISSING_REQUIRED"
    UNKNOWN_FIELD = "UNKNOWN_FIELD"
    TOO_LONG = "TOO_LONG"
    ROW_TOO_LARGE = "ROW_TOO_LARGE"
    INVALID_DATE = "INVALID_DATE"
    INVALID_VALUE = "INVALID_VALUE"
    INVALID_IDENTIFIER = "INVALID_IDENTIFIER"
    #: The id repeats an earlier line of the same file; the first occurrence is the one written.
    DUPLICATE_IN_BATCH = "DUPLICATE_IN_BATCH"
    #: The id already belongs to a raw record, a queue row or an archived description.
    ALREADY_EXISTS = "ALREADY_EXISTS"
    #: The row was written but the staging transform could not structure it.
    STAGING_FAILED = "STAGING_FAILED"


@dataclass(frozen=True)
class CsvField:
    """One column of the import: the file's label, the staging attribute and how to show it."""

    label: str
    attribute: str
    help: str
    kind: CsvFieldKind = "text"
    required: bool = False
    max_length: int | None = None


#: The record's identity, outside the payload: a row carries it, the file may name it, and the
#: screen generates one when the file does not.
CSV_ID_FIELD = CsvField(
    label="Identificador",
    attribute="description_id",
    help="Identificador único do registro. Vazio: a tela gera um a partir do arquivo.",
    max_length=50,
)

#: Every field the CSV accepts, in the template's order: the ISAD(G) areas, then the two extras
#: (the access points, which become tags, and the image the thumbnail worker copies).
#:
#: The set is the manual contract's (``ManualIngestionRequest``) minus the identity column, and a
#: test pins the equality — a field added to the form without a column here would make the file
#: unable to carry it, and a column here without a field would be refused by the API.
CSV_FIELDS: tuple[CsvField, ...] = (
    CsvField(
        label="Título",
        attribute="title",
        help="Título da descrição. Obrigatório.",
        required=True,
        max_length=500,
    ),
    CsvField(
        label="Código de referência",
        attribute="reference_code",
        help="Código de referência da unidade de descrição.",
        max_length=500,
    ),
    CsvField(
        label="Nível de descrição",
        attribute="level",
        help="Nível de descrição (por exemplo, Série ou Item).",
        max_length=200,
    ),
    CsvField(
        label="Data de produção",
        attribute="document_date",
        help="Data de produção, quando conhecida. A gramática do perfil de idioma é aplicada.",
        kind="date",
        max_length=MAX_CSV_FIELD_CHARS,
    ),
    CsvField(
        label="Dimensão e suporte",
        attribute="dimension_support",
        help="Quanto é e em que material: 2 folhas; 1 fotografia em papel.",
        max_length=MAX_CSV_FIELD_CHARS,
    ),
    CsvField(
        label="Código da unidade superior",
        attribute="parent_reference_code",
        help="Código da unidade de descrição superior, quando houver.",
        max_length=500,
    ),
    CsvField(
        label="Produtores",
        attribute="producers",
        help="Nome do produtor ou dos produtores.",
        max_length=MAX_CSV_FIELD_CHARS,
    ),
    CsvField(
        label="História administrativa / biográfica",
        attribute="admin_bio_history",
        help="História administrativa ou biográfica do produtor.",
        kind="long_text",
        max_length=MAX_CSV_FIELD_CHARS,
    ),
    CsvField(
        label="História arquivística",
        attribute="admin_archival_history",
        help="História arquivística da unidade de descrição.",
        kind="long_text",
        max_length=MAX_CSV_FIELD_CHARS,
    ),
    CsvField(
        label="Procedência",
        attribute="provenance",
        help="Procedência da unidade de descrição.",
        kind="long_text",
        max_length=MAX_CSV_FIELD_CHARS,
    ),
    CsvField(
        label="URL do original",
        attribute="original_url",
        help="URL da página de onde o registro foi lido.",
        kind="url",
        max_length=MAX_CSV_FIELD_CHARS,
    ),
    CsvField(
        label="Âmbito e conteúdo",
        attribute="scope_content",
        help="Âmbito e conteúdo da descrição.",
        kind="long_text",
        max_length=MAX_CSV_FIELD_CHARS,
    ),
    CsvField(
        label="Avaliação e temporalidade",
        attribute="appraisal_destruction",
        help="Prazo de guarda e decisão de eliminação, quando houver.",
        kind="long_text",
        max_length=MAX_CSV_FIELD_CHARS,
    ),
    CsvField(
        label="Incorporações",
        attribute="accruals",
        help="Se ainda se esperam acréscimos ao conjunto.",
        max_length=MAX_CSV_FIELD_CHARS,
    ),
    CsvField(
        label="Sistema de arranjo",
        attribute="arrangement",
        help="Como o conjunto está organizado internamente.",
        kind="long_text",
        max_length=MAX_CSV_FIELD_CHARS,
    ),
    CsvField(
        label="Condições de acesso",
        attribute="access_conditions",
        help="Condições de acesso ou acesso público.",
        kind="long_text",
        max_length=MAX_CSV_FIELD_CHARS,
    ),
    CsvField(
        label="Condições de reprodução",
        attribute="reproduction_conditions",
        help="O que é preciso para copiar ou publicar o documento.",
        kind="long_text",
        max_length=MAX_CSV_FIELD_CHARS,
    ),
    CsvField(
        label="Idioma",
        attribute="language_name",
        help="Idioma predominante do documento.",
        max_length=MAX_CSV_FIELD_CHARS,
    ),
    CsvField(
        label="Características físicas",
        attribute="physical_characteristics",
        help="Estado material e requisitos técnicos para a consulta.",
        kind="long_text",
        max_length=MAX_CSV_FIELD_CHARS,
    ),
    CsvField(
        label="Instrumentos de pesquisa",
        attribute="finding_aids",
        help="Índices, inventários ou listagens que descrevem este conjunto.",
        kind="long_text",
        max_length=MAX_CSV_FIELD_CHARS,
    ),
    CsvField(
        label="Localização dos originais",
        attribute="originals_location",
        help="Onde está o original, quando esta descrição descreve uma cópia.",
        max_length=MAX_CSV_FIELD_CHARS,
    ),
    CsvField(
        label="Localização das cópias",
        attribute="copies_location",
        help="Onde estão as cópias: microfilme, digital, outro acervo.",
        max_length=MAX_CSV_FIELD_CHARS,
    ),
    CsvField(
        label="Unidades de descrição relacionadas",
        attribute="related_units",
        help="Códigos ou títulos de outras descrições relacionadas com esta.",
        max_length=MAX_CSV_FIELD_CHARS,
    ),
    CsvField(
        label="Notas de publicação",
        attribute="publication_notes",
        help="Onde este documento já foi publicado ou citado.",
        kind="long_text",
        max_length=MAX_CSV_FIELD_CHARS,
    ),
    CsvField(
        label="Notas gerais",
        attribute="general_notes",
        help="O que não cabe em nenhum outro campo.",
        kind="long_text",
        max_length=MAX_CSV_FIELD_CHARS,
    ),
    CsvField(
        label="Notas de conservação",
        attribute="conservation_notes",
        help="Estado de conservação e o que já foi feito ou precisa ser feito.",
        kind="long_text",
        max_length=MAX_CSV_FIELD_CHARS,
    ),
    CsvField(
        label="Notas do arquivista",
        attribute="archivist_notes",
        help="Observações técnicas de quem descreveu.",
        kind="long_text",
        max_length=MAX_CSV_FIELD_CHARS,
    ),
    CsvField(
        label="Regras ou convenções",
        attribute="rules_conventions",
        help="As normas seguidas na descrição: ISAD(G), NOBRADE, normas internas.",
        max_length=MAX_CSV_FIELD_CHARS,
    ),
    CsvField(
        label="Pontos de acesso",
        attribute="indexing_points",
        help="Pontos de acesso, separados por vírgula. Viram tags no acervo.",
        kind="tags",
        max_length=MAX_CSV_FIELD_CHARS,
    ),
    CsvField(
        label="Link da imagem",
        attribute="thumb_down_link",
        help="URL da imagem que o worker de miniatura baixa.",
        kind="url",
        max_length=MAX_CSV_FIELD_CHARS,
    ),
)

#: The labels the payload may carry, the required one included.
CSV_LABELS: frozenset[str] = frozenset(field.label for field in CSV_FIELDS)

#: The title's label is the schema's ``title_key``; it is not in the field map, or the transform
#: would append the title to itself. Found by attribute, not by position: the list grows, and a
#: positional constant silently becomes another column's label.
CSV_TITLE_LABEL = next(field.label for field in CSV_FIELDS if field.attribute == "title")
CSV_DATE_LABEL = next(field.label for field in CSV_FIELDS if field.attribute == "document_date")

#: Label -> staging attribute, for the fields the generic map consumes. The title and the date are
#: consumed through the schema's own keys, exactly like the manual origin.
CSV_FIELD_MAP: dict[str, str] = {
    field.label: field.attribute for field in CSV_FIELDS if field.attribute not in ("title", "document_date")
}


@dataclass(frozen=True)
class CsvRowIssue:
    """One reason a row did not enter; ``field`` is the file's label, or ``None`` for the row."""

    field: str | None
    code: CsvRowIssueCode
    message: str


def field_limit(field: CsvField) -> int:
    """The effective character cap of a field: its own, or the import's general one."""
    return field.max_length or MAX_CSV_FIELD_CHARS


def payload_of(fields: dict[str, str]) -> dict[str, str]:
    """The raw payload the staging transform will read: the row's cells, with empties dropped."""
    return {label: value for label, value in fields.items() if value != ""}


def row_bytes(fields: dict[str, str]) -> int:
    """The UTF-8 bytes one row's cells occupy in the request, measured the way JSON carries them."""
    return len(json.dumps(fields, ensure_ascii=False).encode("utf-8"))


def validate_csv_row(description_id: str, fields: dict[str, str]) -> list[CsvRowIssue]:
    """
    The plan for one row: every reason it would not stage, in the order a person reads them.

    It runs ``StagingDocumentDTO`` with the CSV schema as context, so the date grammar, the false
    nulls, the whitespace collapsing and the type coercion are the **same** ones the pipeline will
    apply. The checks before it exist because the transform is deliberately forgiving in two
    places the import cannot be: a missing title becomes the language's placeholder and an
    unreadable date silently becomes ``None``. Here those are refusals, with a sentence.
    """
    issues: list[CsvRowIssue] = []

    identifier = description_id.strip()
    if not identifier or len(identifier) > (CSV_ID_FIELD.max_length or 50):
        issues.append(
            CsvRowIssue(
                field=CSV_ID_FIELD.label,
                code=CsvRowIssueCode.INVALID_IDENTIFIER,
                message="O identificador precisa ter entre 1 e 50 caracteres.",
            )
        )

    by_label = {field.label: field for field in CSV_FIELDS}
    for label in sorted(set(fields) - CSV_LABELS):
        issues.append(
            CsvRowIssue(
                field=label,
                code=CsvRowIssueCode.UNKNOWN_FIELD,
                message=f"A coluna '{label}' não faz parte do mapa da importação.",
            )
        )

    if not (fields.get(CSV_TITLE_LABEL) or "").strip():
        issues.append(
            CsvRowIssue(
                field=CSV_TITLE_LABEL,
                code=CsvRowIssueCode.MISSING_REQUIRED,
                message="O título é obrigatório.",
            )
        )

    for label, value in fields.items():
        field = by_label.get(label)
        if field is None:
            continue
        limit = field_limit(field)
        if len(value) > limit:
            issues.append(
                CsvRowIssue(
                    field=label,
                    code=CsvRowIssueCode.TOO_LONG,
                    message=f"O campo '{label}' aceita no máximo {limit} caracteres.",
                )
            )

    raw_date = (fields.get(CSV_DATE_LABEL) or "").strip()
    language = get_language()
    if raw_date and raw_date.lower() not in language.empty_date_values and parse_document_date(raw_date) is None:
        issues.append(
            CsvRowIssue(
                field=CSV_DATE_LABEL,
                code=CsvRowIssueCode.INVALID_DATE,
                message=f"A data '{raw_date[:40]}' não foi reconhecida.",
            )
        )

    payload = payload_of(fields)
    try:
        StagingDocumentDTO.model_validate(
            {
                "description_id": identifier,
                "origin_code": "csv",
                "content_hash": "0" * 64,
                "payload": payload,
                "raw_title": payload.get(CSV_TITLE_LABEL),
            },
            context={SOURCE_SCHEMA_CONTEXT_KEY: _schema()},
        )
    except ValidationError as exc:
        for error in exc.errors():
            attribute = str(error.get("loc", ("",))[0])
            label = _label_of(attribute)
            issue = CsvRowIssue(
                field=label,
                code=CsvRowIssueCode.INVALID_VALUE,
                message=f"O campo '{label or attribute}' tem um valor que a estrutura de staging recusou.",
            )
            if issue not in issues:
                issues.append(issue)

    return issues


def _schema() -> Any:
    """The CSV schema, imported lazily so this module stays cheap for the API's spec route."""
    from scrinalia.domains.ingestion.adapters.csv import CSV_SOURCE_SCHEMA

    return CSV_SOURCE_SCHEMA


def _label_of(attribute: str) -> str | None:
    """The file's label for a staging attribute, for a Pydantic error located at the attribute."""
    for field in (*CSV_FIELDS, CSV_ID_FIELD):
        if field.attribute == attribute:
            return field.label
    return None
