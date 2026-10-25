"""The CSV import's catalogue and its plan: the labels, the bounds and the per-row refusals.

The route is the authority, but the rules it applies are pure and testable without a database. This
file pins the three places that can silently disagree: the field set against the manual contract,
the values of the map against ``StagingDocumentDTO``, and the row's checks against the sentences the
screen shows.
"""

from __future__ import annotations

from datetime import date

from scrinalia.domains.ingestion.adapters.csv import CSV_SOURCE_SCHEMA
from scrinalia.domains.ingestion.csv_import import (
    CSV_FIELDS,
    CSV_ID_FIELD,
    MAX_CSV_BYTES,
    MAX_CSV_FIELD_CHARS,
    MAX_CSV_ROW_BYTES,
    MAX_CSV_ROWS,
    CsvRowIssueCode,
    field_limit,
    payload_of,
    row_bytes,
    validate_csv_row,
)
from scrinalia.domains.ingestion.schemas import build_csv_import_spec
from scrinalia.domains.staging.schemas import SOURCE_SCHEMA_CONTEXT_KEY, StagingDocumentDTO


def test_the_spec_publishes_the_one_catalogue_and_its_bounds() -> None:
    spec = build_csv_import_spec()

    assert spec.origin_code == "csv"
    assert spec.id.label == CSV_ID_FIELD.label
    assert [field.label for field in spec.fields] == [field.label for field in CSV_FIELDS]
    assert (spec.max_rows, spec.max_bytes, spec.max_row_bytes, spec.max_field_chars) == (
        MAX_CSV_ROWS,
        MAX_CSV_BYTES,
        MAX_CSV_ROW_BYTES,
        MAX_CSV_FIELD_CHARS,
    )
    assert spec.fields[0].label == "Título" and spec.fields[0].required is True


def test_the_field_limit_falls_back_to_the_general_cap() -> None:
    assert field_limit(CSV_FIELDS[0]) == 500
    assert field_limit(CSV_FIELDS[5]) == MAX_CSV_FIELD_CHARS


def test_payload_drops_empty_cells_and_keeps_the_rest() -> None:
    assert payload_of({"Título": "Ofício", "Produtores": "", "Nível de descrição": "Item"}) == {
        "Título": "Ofício",
        "Nível de descrição": "Item",
    }


def test_row_bytes_counts_utf8() -> None:
    assert row_bytes({"Título": "Ofício"}) > len("Ofício")


def test_a_valid_row_has_no_issue() -> None:
    assert validate_csv_row("csv-1", {"Título": "Ofício do prefeito", "Data de produção": "05/07/1929"}) == []


def test_a_missing_title_is_refused() -> None:
    issues = validate_csv_row("csv-1", {"Título": "  "})
    assert [issue.code for issue in issues] == [CsvRowIssueCode.MISSING_REQUIRED]
    assert issues[0].field == "Título"


def test_an_unreadable_date_is_refused() -> None:
    issues = validate_csv_row("csv-1", {"Título": "Ofício", "Data de produção": "banana"})
    assert CsvRowIssueCode.INVALID_DATE in {issue.code for issue in issues}


def test_a_fuzzy_date_the_profile_reads_is_a_date() -> None:
    """The grammar is the staging one; a decade is a legitimate date, not a typo."""
    assert validate_csv_row("csv-1", {"Título": "Ofício", "Data de produção": "Década de 1980"}) == []


def test_an_unknown_field_is_refused() -> None:
    issues = validate_csv_row("csv-1", {"Título": "Ofício", "coluna_extra": "x"})
    assert [(issue.field, issue.code) for issue in issues] == [("coluna_extra", CsvRowIssueCode.UNKNOWN_FIELD)]


def test_a_value_over_the_limit_is_refused() -> None:
    issues = validate_csv_row("csv-1", {"Título": "x" * 501})
    assert CsvRowIssueCode.TOO_LONG in {issue.code for issue in issues}


def test_an_invalid_identifier_is_refused() -> None:
    issues = validate_csv_row("", {"Título": "Ofício"})
    assert issues and issues[0].code is CsvRowIssueCode.INVALID_IDENTIFIER


def test_the_transform_reads_the_same_row() -> None:
    """The plan and the write path agree: the model, the schema and the date grammar are the same."""
    row = {
        "Título": "Ofício do prefeito",
        "Código de referência": "BR PR MAN 001",
        "Data de produção": "05/07/1929",
        "Pontos de acesso": "ofício; prefeitura",
        "Produtores": "Prefeitura",
    }
    assert validate_csv_row("csv-1", row) == []

    staged = StagingDocumentDTO.model_validate(
        {
            "description_id": "csv-1",
            "origin_code": "csv",
            "content_hash": "0" * 64,
            "payload": payload_of(row),
            "raw_title": row["Título"],
        },
        context={SOURCE_SCHEMA_CONTEXT_KEY: CSV_SOURCE_SCHEMA},
    )

    assert staged.title == "Ofício do prefeito"
    assert staged.reference_code == "BR PR MAN 001"
    assert staged.document_date == date(1929, 7, 5)
    assert staged.indexing_points == "ofício, prefeitura"
    assert staged.producers == "Prefeitura"
    assert staged.raw_metadata == {}


def test_the_title_is_not_mapped_twice() -> None:
    """The title lives in ``title_key``; putting it in the map would duplicate it (ADR 0008 defect)."""
    staged = StagingDocumentDTO.model_validate(
        {
            "description_id": "csv-1",
            "origin_code": "csv",
            "content_hash": "0" * 64,
            "payload": {"Título": "Ofício"},
            "raw_title": None,
        },
        context={SOURCE_SCHEMA_CONTEXT_KEY: CSV_SOURCE_SCHEMA},
    )
    assert staged.title == "Ofício"
