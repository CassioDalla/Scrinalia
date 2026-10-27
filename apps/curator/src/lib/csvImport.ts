/**
 * The CSV file's headers mapped to the origin's declared vocabulary.
 *
 * The API publishes the map (`GET /ingestion/csv/spec`) and the card validates against it, but the
 * server re-validates every row: this module is a convenience, never the authority. It matches a
 * header by its label or by the staging attribute — "Código de referência" and `reference_code` both
 * reach the same column — after folding accents, case and the spaces around a slash, which is what
 * a spreadsheet's typo usually changes.
 *
 * The id is special: it is the row's identity, not a staging column. The file may carry it in the
 * `Identificador` column; when it does not, the card generates one per row and keeps it for the
 * lifetime of the parsed file, so a retried submit is the same batch.
 */

import type { components } from "@/api/schema";

import { toCsv, type ParsedCsv } from "./csv";

export type CsvSpec = components["schemas"]["CsvImportSpecResponse"];
export type CsvSpecField = components["schemas"]["CsvFieldDTO"];
export type CsvImportRowBody = components["schemas"]["CsvImportRow"];

export interface HeaderMapping {
  header: string;
  field: CsvSpecField | null;
  isId: boolean;
}

export interface CsvPreviewRow {
  line: number;
  descriptionId: string;
  /** Cells by the map's canonical label, ready for `POST /ingestion/csv`. */
  fields: Record<string, string>;
  title: string;
  issues: string[];
}

export interface CsvMapping {
  delimiter: string;
  headers: HeaderMapping[];
  unknownHeaders: string[];
  missingRequired: string[];
  duplicateFields: string[];
  /** Structural problems: they disable the submit, because a row the server cannot read is not a row. */
  blocking: string[];
  /** The data rows, valid or not; the server is the authority on the invalid ones. */
  rows: CsvPreviewRow[];
}

/** Folds what a person changes when typing a header: accents, case, extra spaces, `a / b`. */
export function normalizeHeader(value: string): string {
  return value
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .trim()
    .toLowerCase()
    .replace(/\s*\/\s*/g, "/")
    .replace(/\s+/g, " ");
}

function matches(header: string, field: CsvSpecField): boolean {
  const normalized = normalizeHeader(header);
  return normalized === normalizeHeader(field.label) || normalized === normalizeHeader(field.attribute);
}

function fieldLimit(field: CsvSpecField, spec: CsvSpec): number {
  return field.max_length ?? spec.max_field_chars;
}

export function mapCsv(parsed: ParsedCsv, spec: CsvSpec, idFactory: () => string): CsvMapping {
  const fields = spec.fields ?? [];
  const idLabel = spec.id.label;

  const headers: HeaderMapping[] = [];
  const unknownHeaders: string[] = [];
  const duplicateFields: string[] = [];
  const mappedLabels = new Set<string>();

  for (const header of parsed.headers) {
    if (normalizeHeader(header) === normalizeHeader(idLabel) || normalizeHeader(header) === "description_id") {
      headers.push({ header, field: null, isId: true });
      continue;
    }
    const field = fields.find((candidate) => matches(header, candidate)) ?? null;
    if (!field) {
      headers.push({ header, field: null, isId: false });
      unknownHeaders.push(header);
      continue;
    }
    if (mappedLabels.has(field.label)) {
      // Two columns for the same attribute: the row would have one silently win over the other.
      duplicateFields.push(field.label);
      headers.push({ header, field: null, isId: false });
      continue;
    }
    mappedLabels.add(field.label);
    headers.push({ header, field, isId: false });
  }

  const missingRequired = fields.filter((field) => field.required && !mappedLabels.has(field.label)).map((f) => f.label);
  const titleField = fields.find((field) => field.required) ?? fields[0];
  const idHeaderIndex = headers.findIndex((header) => header.isId);

  const blocking: string[] = [];
  if (parsed.rows.length === 0) {
    blocking.push("O arquivo tem só o cabeçalho e nenhuma linha de dados.");
  }
  if (parsed.rows.length > spec.max_rows) {
    blocking.push(`O arquivo tem ${parsed.rows.length} linhas e o limite é ${spec.max_rows}. Divida o arquivo em partes.`);
  }
  if (missingRequired.length > 0) {
    blocking.push(
      `Faltam colunas obrigatórias: ${missingRequired.join(", ")}. Baixe o modelo para conferir os nomes das colunas.`,
    );
  }
  if (duplicateFields.length > 0) {
    blocking.push(
      `Mais de uma coluna preenche o mesmo campo: ${duplicateFields.join(", ")}. Deixe só uma coluna para cada campo.`,
    );
  }

  const seenIds = new Map<string, number>();
  const rows: CsvPreviewRow[] = [];

  for (const row of parsed.rows) {
    if (row.cells.length !== parsed.headers.length) {
      blocking.push(
        `A linha ${row.line} tem ${row.cells.length} colunas, mas o cabeçalho tem ${parsed.headers.length}.`,
      );
      continue;
    }

    const values: Record<string, string> = {};
    for (const [index, header] of headers.entries()) {
      if (!header.field) continue;
      values[header.field.label] = row.cells[index] ?? "";
    }

    const rawId = idHeaderIndex >= 0 ? (row.cells[idHeaderIndex] ?? "").trim() : "";
    const descriptionId = rawId !== "" ? rawId : idFactory();
    const title = titleField ? (values[titleField.label] ?? "") : "";

    const issues: string[] = [];
    if (descriptionId.length > 50) {
      issues.push("O identificador aceita no máximo 50 caracteres.");
    }
    const firstSeen = seenIds.get(descriptionId);
    if (firstSeen !== undefined) {
      issues.push(`O identificador já aparece na linha ${firstSeen}. Use um identificador diferente.`);
    } else {
      seenIds.set(descriptionId, row.line);
    }
    for (const field of fields) {
      const value = values[field.label];
      if (value === undefined) continue;
      if (field.required && value.trim() === "") {
        issues.push(`O campo '${field.label}' é obrigatório e está em branco.`);
      }
      const limit = fieldLimit(field, spec);
      if (value.length > limit) {
        issues.push(`O campo '${field.label}' aceita no máximo ${limit} caracteres.`);
      }
    }

    rows.push({ line: row.line, descriptionId, fields: values, title, issues });
  }

  const payloadBytes = new TextEncoder().encode(JSON.stringify(rows.map((row) => row.fields))).length;
  if (payloadBytes > spec.max_bytes) {
    blocking.push(
      `A importação tem ${(payloadBytes / (1024 * 1024)).toFixed(1)} MB e o limite é ${spec.max_bytes / (1024 * 1024)} MB. Divida o arquivo em partes.`,
    );
  }

  return {
    delimiter: parsed.delimiter,
    headers,
    unknownHeaders,
    missingRequired,
    duplicateFields,
    blocking,
    rows,
  };
}

/** The body the client sends: only the mapped columns, keyed by the map's canonical labels. */
export function toRequestBody(mapping: CsvMapping): CsvImportRowBody[] {
  return mapping.rows.map((row) => ({
    line: row.line,
    description_id: row.descriptionId,
    fields: row.fields,
  }));
}

/** The template's header: the map's labels, with the identity column first. */
export function buildTemplate(spec: CsvSpec): string {
  return toCsv([spec.id.label, ...(spec.fields ?? []).map((field) => field.label)]);
}
