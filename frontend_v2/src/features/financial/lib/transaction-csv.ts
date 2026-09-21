import type { LedgerTransaction } from "../api"
import { formatLedgerAmount } from "./ledger-format"
import { party } from "./transaction-analysis"

/** RFC 4180 quoting, including embedded newlines and escaped quotes. */
export function parseNotesCsv(text: string) {
  if (new TextEncoder().encode(text).length > 2 * 1024 * 1024)
    throw Error("Use a CSV smaller than 2 MB.")
  const records: string[][] = []
  let record: string[] = [],
    value = "",
    quoted = false,
    closed = false
  const input = text.replace(/^\uFEFF/, "")
  const cell = () => {
    record.push(value)
    value = ""
    closed = false
  }
  const line = () => {
    cell()
    if (record.some((v) => v.trim())) records.push(record)
    record = []
  }
  for (let i = 0; i < input.length; i++) {
    const char = input[i]
    if (quoted) {
      if (char === '"') {
        if (input[i + 1] === '"') {
          value += '"'
          i++
        } else {
          quoted = false
          closed = true
        }
      } else value += char
    } else if (char === '"') {
      if (value || closed) throw Error("Invalid CSV quotation.")
      quoted = true
    } else if (char === ",") cell()
    else if (char === "\n" || char === "\r") {
      if (char === "\r" && input[i + 1] === "\n") i++
      line()
    } else {
      if (closed && char.trim())
        throw Error("Unexpected text after a quoted CSV field.")
      if (!closed) value += char
    }
  }
  if (quoted) throw Error("A quoted CSV field is not closed.")
  if (value || record.length || closed) line()
  if (records.length < 2) throw Error("Add a header and at least one note.")
  if (records.length > 2001) throw Error("Import up to 2,000 notes at a time.")
  const headers = records.shift()!.map((h) => h.trim().toLowerCase())
  const ref = headers.findIndex((h) =>
    ["ref_id", "ref", "reference"].includes(h)
  )
  const note = headers.findIndex((h) =>
    ["notes", "note", "comment"].includes(h)
  )
  if (ref < 0 || note < 0)
    throw Error("The CSV needs ref_id and notes columns.")
  return records.map((r, i) => {
    const refId = r[ref]?.trim(),
      notes = r[note]?.trim()
    if (!refId || !notes)
      throw Error(`Row ${i + 2} needs both a reference and a note.`)
    if (notes.length > 6000)
      throw Error(`Row ${i + 2}: notes must be 6,000 characters or fewer.`)
    return { refId, notes }
  })
}
export const csvCell = (value: string) =>
  `"${(/^[\s]*[=+@-]/.test(value) ? "'" + value : value).replace(/"/g, '""')}"`
export function transactionCsv(rows: LedgerTransaction[]) {
  const headers = [
    "ref_id",
    "date",
    "description",
    "from",
    "to",
    "category",
    "from_basis",
    "to_basis",
    "category_basis",
    "account",
    "direction",
    "amount",
    "currency",
    "printed_balance",
    "printed_balance_status",
    "notes",
  ]
  const contents = rows.map((r) => [
    r.ref_id || r.key,
    r.ordering_date_context === "statement_end_ordering_only"
      ? ""
      : r.ordering_date,
    r.description || "",
    party(r, "from").name,
    party(r, "to").name,
    r.category || "Uncategorized",
    r.label_sources?.from_name?.source ||
      (party(r, "from").key.startsWith("unknown:")
        ? "not identified"
        : "recorded"),
    r.label_sources?.to_name?.source ||
      (party(r, "to").key.startsWith("unknown:")
        ? "not identified"
        : "recorded"),
    r.label_sources?.category?.source ||
      (r.category ? "recorded" : "not categorized"),
    r.account_label || r.account_id,
    r.direction,
    formatLedgerAmount(r.amount_minor, r.currency).text,
    r.currency,
    r.running_balance_minor == null
      ? ""
      : formatLedgerAmount(r.running_balance_minor, r.currency).text,
    r.balance_status ||
      (r.running_balance_minor == null ? "unavailable" : "recorded"),
    "",
  ])
  return (
    "\uFEFF" +
    [headers, ...contents]
      .map((cells) => cells.map(csvCell).join(","))
      .join("\r\n")
  )
}
export function downloadCsv(contents: string, filename: string) {
  const url = URL.createObjectURL(
      new Blob([contents], { type: "text/csv;charset=utf-8" })
    ),
    link = document.createElement("a")
  link.href = url
  link.download = filename
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
