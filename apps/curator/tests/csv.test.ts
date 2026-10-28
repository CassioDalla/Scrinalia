/**
 * The CSV parser and the header mapper: the two pieces the browser runs before the API sees a row.
 *
 * The suite has no browser and no JS test runner of its own; `bun test` is the one the frontend job
 * already has, and it runs this file against the same source `tsc` and Vite build. The cases are the
 * ones a spreadsheet produces: quoted commas and newlines, the semicolon of Brazilian Excel, a BOM,
 * CRLF, and the header typos the mapper's folding is meant to absorb.
 */

import { describe, expect, it } from "bun:test";

import { CsvParseError, detectDelimiter, parseCsv, toCsv } from "../src/lib/csv";
import { buildTemplate, mapCsv, normalizeHeader, toRequestBody, type CsvSpec } from "../src/lib/csvImport";

const SPEC: CsvSpec = {
  origin_code: "csv",
  id: {
    label: "Identificador",
    attribute: "description_id",
    help: "",
    kind: "text",
    required: false,
    max_length: 50,
  },
  fields: [
    { label: "Título", attribute: "title", help: "", kind: "text", required: true, max_length: 500 },
    {
      label: "Código de referência",
      attribute: "reference_code",
      help: "",
      kind: "text",
      required: false,
      max_length: 500,
    },
    { label: "Data de produção", attribute: "document_date", help: "", kind: "date", required: false, max_length: null },
    { label: "Pontos de acesso", attribute: "indexing_points", help: "", kind: "tags", required: false, max_length: null },
  ],
  max_rows: 500,
  max_bytes: 8 * 1024 * 1024,
  max_row_bytes: 64 * 1024,
  max_field_chars: 20_000,
};

function ids(): () => string {
  let next = 0;
  return () => {
    next += 1;
    return `csv-${next}`;
  };
}

describe("parseCsv", () => {
  it("reads a comma file and keeps the physical line of each row", () => {
    const parsed = parseCsv("Título,Código\nOfício,BR 1\nPlanta,BR 2\n");
    expect(parsed.headers).toEqual(["Título", "Código"]);
    expect(parsed.rows).toEqual([
      { line: 2, cells: ["Ofício", "BR 1"] },
      { line: 3, cells: ["Planta", "BR 2"] },
    ]);
    expect(parsed.delimiter).toBe(",");
  });

  it("detects the semicolon of a Brazilian spreadsheet", () => {
    const parsed = parseCsv("Título;Código\nOfício;BR 1\n");
    expect(parsed.delimiter).toBe(";");
    expect(parsed.rows[0]?.cells).toEqual(["Ofício", "BR 1"]);
  });

  it("keeps commas, newlines and quotes inside a quoted cell", () => {
    const parsed = parseCsv('Título,Resumo\n"Ofício, do prefeito","linha 1\nlinha 2"\n"Ele disse ""oi""",x\n');
    expect(parsed.rows[0]?.cells).toEqual(["Ofício, do prefeito", "linha 1\nlinha 2"]);
    expect(parsed.rows[1]?.cells).toEqual(['Ele disse "oi"', "x"]);
  });

  it("handles a UTF-8 BOM and CRLF", () => {
    const parsed = parseCsv("\uFEFFTítulo,Código\r\nOfício,BR 1\r\n");
    expect(parsed.headers).toEqual(["Título", "Código"]);
    expect(parsed.rows[0]?.cells).toEqual(["Ofício", "BR 1"]);
  });

  it("skips blank lines without losing the line numbers", () => {
    const parsed = parseCsv("Título\n\nOfício\n");
    expect(parsed.rows).toEqual([{ line: 3, cells: ["Ofício"] }]);
  });

  it("refuses unbalanced quotes", () => {
    expect(() => parseCsv('Título\n"Ofício\n')).toThrow(CsvParseError);
  });

  it("refuses an empty header", () => {
    expect(() => parseCsv("Título,\nOfício,x\n")).toThrow(CsvParseError);
  });
});

describe("detectDelimiter and toCsv", () => {
  it("prefers the delimiter with more occurrences in the header", () => {
    expect(detectDelimiter("a;b;c\n")).toBe(";");
    expect(detectDelimiter("a,b\n")).toBe(",");
  });

  it("round-trips a value with a comma, a quote and a newline", () => {
    const value = 'Ofício, "do prefeito"\nsegunda linha';
    const text = toCsv(["Título"], [[value]]);
    expect(parseCsv(text).rows[0]?.cells).toEqual([value]);
  });
});

describe("mapCsv", () => {
  it("maps a header by label, attribute, accent and slash spacing", () => {
    const parsed = parseCsv("titulo;codigo de referencia;Data de produção\nOfício;BR 1;05/07/1929\n");
    const mapping = mapCsv(parsed, SPEC, ids());

    expect(mapping.unknownHeaders).toEqual([]);
    expect(mapping.missingRequired).toEqual([]);
    expect(mapping.rows[0]?.fields).toEqual({
      Título: "Ofício",
      "Código de referência": "BR 1",
      "Data de produção": "05/07/1929",
    });
    expect(mapping.rows[0]?.title).toBe("Ofício");
  });

  it("reports an unknown column without sending it", () => {
    const parsed = parseCsv("Título,Observações\nOfício,x\n");
    const mapping = mapCsv(parsed, SPEC, ids());

    expect(mapping.unknownHeaders).toEqual(["Observações"]);
    expect(mapping.rows[0]?.fields).toEqual({ Título: "Ofício" });
  });

  it("blocks a file without the required column", () => {
    const parsed = parseCsv("Código de referência\nBR 1\n");
    const mapping = mapCsv(parsed, SPEC, ids());

    expect(mapping.missingRequired).toEqual(["Título"]);
    expect(mapping.blocking.some((message) => message.includes("obrigatórias"))).toBe(true);
  });

  it("blocks two columns that point at the same field", () => {
    const parsed = parseCsv("Título,Código de referência,codigo de referencia\nOfício,BR 1,BR 2\n");
    const mapping = mapCsv(parsed, SPEC, ids());

    expect(mapping.duplicateFields).toEqual(["Código de referência"]);
  });

  it("blocks a row whose cell count differs from the header", () => {
    const parsed = parseCsv("Título,Código\nOfício\n");
    const mapping = mapCsv(parsed, SPEC, ids());

    expect(mapping.blocking.some((message) => message.includes("A linha 2"))).toBe(true);
    expect(mapping.rows).toEqual([]);
  });

  it("uses the file's id when present and generates one when not", () => {
    const withId = mapCsv(parseCsv("Identificador,Título\ncsv-9,Ofício\n"), SPEC, ids());
    expect(withId.rows[0]?.descriptionId).toBe("csv-9");

    const withoutId = mapCsv(parseCsv("Título\nOfício\n"), SPEC, ids());
    expect(withoutId.rows[0]?.descriptionId).toBe("csv-1");
  });

  it("marks local issues but keeps the row for the API to judge", () => {
    const parsed = parseCsv("Título,Código de referência\n,BR 1\n");
    const mapping = mapCsv(parsed, SPEC, ids());

    expect(mapping.blocking).toEqual([]);
    expect(mapping.rows[0]?.issues.some((issue) => issue.includes("é obrigatório"))).toBe(true);
  });

  it("marks a repeated id in the file", () => {
    const parsed = parseCsv("Identificador,Título\ncsv-9,A\ncsv-9,B\n");
    const mapping = mapCsv(parsed, SPEC, ids());

    expect(mapping.rows[1]?.issues.some((issue) => issue.includes("linha 2"))).toBe(true);
  });

  it("builds the request body with the canonical labels", () => {
    const mapping = mapCsv(parseCsv("titulo\nOfício\n"), SPEC, ids());
    expect(toRequestBody(mapping)).toEqual([
      { line: 2, description_id: "csv-1", fields: { Título: "Ofício" } },
    ]);
  });

  it("builds the template from the map's labels", () => {
    expect(buildTemplate(SPEC)).toBe("Identificador,Título,Código de referência,Data de produção,Pontos de acesso\r\n");
  });

  it("folds accents, case and slashes in a header", () => {
    expect(normalizeHeader("  Código  de   Referência ")).toBe("codigo de referencia");
    expect(normalizeHeader("História administrativa / biográfica")).toBe("historia administrativa/biografica");
  });
});
