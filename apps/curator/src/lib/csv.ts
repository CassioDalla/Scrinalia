/**
 * A small CSV parser for the import card.
 *
 * The file is read in the browser; nothing is uploaded to the bucket and no multipart route exists
 * (#191). The format is the one a spreadsheet exports: comma or semicolon, quoted fields with `""`
 * as the escape, newlines inside quotes, CRLF, and a UTF-8 BOM — plus a Windows-1252 fallback for
 * the files Brazilian Excel still produces.
 *
 * It is deliberately a parser and not a table reader: it returns the header and the rows **as
 * cells**, with the physical line each row starts on, and leaves the mapping to the origin's
 * declared labels (`lib/csvImport.ts`). The one rule it enforces is the file's shape: unbalanced
 * quotes, an empty header or a file with no header are refusals, because no column mapping can fix
 * them.
 */

export type CsvDelimiter = "," | ";";

export interface ParsedCsvRow {
  /** 1-based physical line of the file, header included, for the per-row report. */
  line: number;
  cells: string[];
}

export interface ParsedCsv {
  headers: string[];
  rows: ParsedCsvRow[];
  delimiter: CsvDelimiter;
}

export class CsvParseError extends Error {
  constructor(
    message: string,
    readonly line?: number,
  ) {
    super(message);
    this.name = "CsvParseError";
  }
}

const BOM = "\uFEFF";

/** The header record, up to the first line break outside quotes. */
function headerRecord(text: string): string {
  let inQuotes = false;
  for (let index = 0; index < text.length; index += 1) {
    const char = text.charAt(index);
    if (char === '"') {
      if (inQuotes && text.charAt(index + 1) === '"') {
        index += 1;
      } else {
        inQuotes = !inQuotes;
      }
    } else if (!inQuotes && (char === "\n" || char === "\r")) {
      return text.slice(0, index);
    }
  }
  return text;
}

function countOutsideQuotes(text: string, delimiter: string): number {
  let inQuotes = false;
  let count = 0;
  for (let index = 0; index < text.length; index += 1) {
    const char = text.charAt(index);
    if (char === '"') {
      if (inQuotes && text.charAt(index + 1) === '"') {
        index += 1;
      } else {
        inQuotes = !inQuotes;
      }
    } else if (!inQuotes && char === delimiter) {
      count += 1;
    }
  }
  return count;
}

/**
 * The delimiter the header uses most, outside quotes.
 *
 * Brazilian spreadsheets default to `;` while the rest of the world writes `,`; a file with one
 * column and no delimiter falls back to the comma, which parses it as a single-column file either
 * way. The screen lets the archivist override the guess.
 */
export function detectDelimiter(text: string): CsvDelimiter {
  const body = text.startsWith(BOM) ? text.slice(1) : text;
  const header = headerRecord(body);
  return countOutsideQuotes(header, ";") > countOutsideQuotes(header, ",") ? ";" : ",";
}

/** Decodes the file as UTF-8, falling back to Windows-1252 when the bytes are not valid UTF-8. */
export function decodeCsv(buffer: ArrayBuffer): { text: string; encoding: "UTF-8" | "Windows-1252" } {
  try {
    return { text: new TextDecoder("utf-8", { fatal: true }).decode(buffer), encoding: "UTF-8" };
  } catch {
    return { text: new TextDecoder("windows-1252").decode(buffer), encoding: "Windows-1252" };
  }
}

/**
 * Parses the file into its header and its records.
 *
 * Blank lines are skipped — a spreadsheet exports them and they are not a row of data. A row whose
 * cells are fewer or more than the header's is **not** rejected here: the mapper reports the line,
 * because only it knows how many columns the origin's map expects.
 */
export function parseCsv(text: string, options: { delimiter?: CsvDelimiter } = {}): ParsedCsv {
  const body = text.startsWith(BOM) ? text.slice(1) : text;
  const delimiter = options.delimiter ?? detectDelimiter(body);

  const records: ParsedCsvRow[] = [];
  let cells: string[] = [];
  let current = "";
  let inQuotes = false;
  let line = 1;
  let recordLine = 1;

  const pushRecord = () => {
    cells.push(current);
    current = "";
    const hasContent = cells.some((cell) => cell.trim() !== "");
    if (hasContent) {
      records.push({ line: recordLine, cells });
    }
    cells = [];
  };

  for (let index = 0; index < body.length; index += 1) {
    const char = body.charAt(index);
    if (inQuotes) {
      if (char === '"') {
        if (body.charAt(index + 1) === '"') {
          current += '"';
          index += 1;
        } else {
          inQuotes = false;
        }
      } else {
        if (char === "\n") {
          line += 1;
        }
        current += char;
      }
      continue;
    }

    if (char === '"' && current === "") {
      inQuotes = true;
      continue;
    }
    if (char === delimiter) {
      cells.push(current);
      current = "";
      continue;
    }
    if (char === "\r" || char === "\n") {
      if (char === "\r" && body.charAt(index + 1) === "\n") {
        index += 1;
      }
      pushRecord();
      line += 1;
      recordLine = line;
      continue;
    }
    current += char;
  }

  if (inQuotes) {
    throw new CsvParseError("As aspas de um dos campos não foram fechadas.", recordLine);
  }
  if (current !== "" || cells.length > 0) {
    pushRecord();
  }
  if (records.length === 0) {
    throw new CsvParseError("O arquivo não tem nada para importar.");
  }

  const header = records[0];
  if (!header) {
    throw new CsvParseError("O arquivo não tem nada para importar.");
  }
  const headers = header.cells.map((cell) => cell.trim());
  if (headers.some((value) => value === "")) {
    throw new CsvParseError("Uma das colunas do cabeçalho está sem nome.", header.line);
  }

  return { headers, rows: records.slice(1), delimiter };
}

function escapeCell(value: string): string {
  return /[",;\n\r]/.test(value) ? `"${value.replaceAll('"', '""')}"` : value;
}

/** The template's writer: the labels as the header and nothing else, in the interchange spelling. */
export function toCsv(headers: string[], rows: string[][] = []): string {
  return [headers, ...rows].map((row) => row.map(escapeCell).join(",")).join("\r\n") + "\r\n";
}
