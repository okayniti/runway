import type { TransactionRecord } from "@/lib/types";

/**
 * Minimal RFC4180-ish CSV parser: handles quoted fields, commas and
 * newlines inside quotes, and escaped `""` quotes. No external dependency
 * for something this small and used in exactly one place.
 */
export function parseCsv(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let field = "";
  let inQuotes = false;

  for (let i = 0; i < text.length; i++) {
    const char = text[i];

    if (inQuotes) {
      if (char === '"') {
        if (text[i + 1] === '"') {
          field += '"';
          i++;
        } else {
          inQuotes = false;
        }
      } else {
        field += char;
      }
      continue;
    }

    if (char === '"') {
      inQuotes = true;
    } else if (char === ",") {
      row.push(field);
      field = "";
    } else if (char === "\n" || char === "\r") {
      if (char === "\r" && text[i + 1] === "\n") i++;
      row.push(field);
      field = "";
      if (row.some((cell) => cell.length > 0) || row.length > 1) rows.push(row);
      row = [];
    } else {
      field += char;
    }
  }
  if (field.length > 0 || row.length > 0) {
    row.push(field);
    rows.push(row);
  }

  return rows;
}

export class CsvFormatError extends Error {}

/** Parses a ledger CSV (date,type,category,amount,invoice_date,note header)
 * into the shape POST /forecast expects. Throws CsvFormatError with a
 * message meant to be shown directly to the user on anything malformed,
 * rather than letting a cryptic parse exception surface. */
export function csvToTransactionRecords(text: string): TransactionRecord[] {
  const rows = parseCsv(text);
  if (rows.length < 2) {
    throw new CsvFormatError("That file doesn't have any data rows below the header.");
  }

  const header = rows[0].map((h) => h.trim().toLowerCase());
  const required = ["date", "type", "category", "amount"];
  for (const col of required) {
    if (!header.includes(col)) {
      throw new CsvFormatError(
        `Missing a "${col}" column. Expected: date, type, category, amount, invoice_date, note.`
      );
    }
  }

  const idx = Object.fromEntries(header.map((h, i) => [h, i]));

  return rows.slice(1).map((cells, rowNumber) => {
    const get = (col: string) => cells[idx[col]]?.trim() ?? "";

    const type = get("type");
    if (type !== "inflow" && type !== "outflow") {
      throw new CsvFormatError(
        `Row ${rowNumber + 2}: "type" must be "inflow" or "outflow", got "${type}".`
      );
    }

    const amount = Number(get("amount"));
    if (!Number.isFinite(amount)) {
      throw new CsvFormatError(`Row ${rowNumber + 2}: "amount" isn't a number.`);
    }

    return {
      date: get("date"),
      type,
      category: get("category") || "uncategorized",
      amount,
      invoice_date: idx["invoice_date"] !== undefined ? get("invoice_date") || null : null,
      note: idx["note"] !== undefined ? get("note") || null : null,
    };
  });
}
