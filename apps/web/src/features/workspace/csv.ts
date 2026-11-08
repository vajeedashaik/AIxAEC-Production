/** A spreadsheet runs cells starting with these; room names come from uploaded drawings, so neutralise them. */
const FORMULA = /^[=+\-@\t\r]/;

function cell(value: string | number): string {
  if (typeof value === "number") return String(value);
  const safe = FORMULA.test(value) ? `'${value}` : value;
  return /[",\n\r]/.test(safe) ? `"${safe.replace(/"/g, '""')}"` : safe;
}

export const toCsv = (rows: readonly (readonly (string | number)[])[]) => rows.map((r) => r.map(cell).join(",")).join("\r\n") + "\r\n";

export function downloadCsv(filename: string, rows: readonly (readonly (string | number)[])[]) {
  const url = URL.createObjectURL(new Blob([toCsv(rows)], { type: "text/csv;charset=utf-8" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
