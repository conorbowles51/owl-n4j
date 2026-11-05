import { htmlEscape } from "@/lib/copy-text"
import type { StreamRow } from "../schemas"
import { forwardWords, replyWords } from "./reply-words"

/**
 * Copy formats for phone rows (03 section 3.7, test A13). Pure functions; the click handler writes both flavours
 * through lib/copy-text.ts, which works on the plain http address (no async clipboard API there).
 *
 * text/plain, one line per event:
 *   Tue, Mar 14, 2023, 3:07:12 PM EDT | C3 | WhatsApp | Name (number) -> Name (number) | full body
 * Multi-line bodies keep their line breaks, indented by two spaces. Attachments as [attachment: filename,
 * category]; flags as [Deleted]. The copy ends with the filter and zone it came from.
 * text/html: a table with the same columns, so pasting into Word or Outlook keeps columns.
 */

function what(row: StreamRow): string {
  if (row.kind === "call") return row.call?.words ?? "Call"
  if (row.kind === "email" && row.subject) return row.body ? `${row.subject}\n${row.body}` : row.subject
  if (row.kind === "record") return row.body ? `${row.subject ?? "Record"}: ${row.body}` : row.subject ?? "Record"
  return row.body ?? ""
}

function extras(row: StreamRow): string[] {
  const out: string[] = []
  const words = forwardWords(row)
  if (words) out.push(`[${words}]`)
  for (const r of row.replies ?? []) out.push(`[${replyWords(r)}]`)
  for (const a of row.attachments) out.push(`[attachment: ${a.filename ?? "file name not recorded"}${a.category ? `, ${a.category}` : ""}]`)
  for (const f of row.flags) out.push(`[${f}]`)
  if (row.copies.count > 1) out.push(`[Found ${row.copies.count} times]`)
  return out
}

export function rowText(row: StreamRow): string {
  const body = what(row)
  const [first, ...rest] = body.split("\n")
  // a Timeline lens record (a location, a web visit) has no app or parties: its kind stands in their place
  const head = (row.kind === "record" ? [row.time.full, row.phone.label, first] : [row.time.full, row.phone.label, row.app ?? "app not recorded", row.line, first]).join(" | ")
  const tail = rest.map((l) => `  ${l}`)
  const ex = extras(row)
  return [head + (ex.length ? ` ${ex.join(" ")}` : ""), ...tail].join("\n")
}

export function footer(caseName: string, filterWords: string, zoneName: string): string {
  return `Copied from Loupe, case ${caseName}, filter: ${filterWords || "none"}, times in ${zoneName}.`
}

export function rowsText(rows: StreamRow[], caseName: string, filterWords: string, zoneName: string): string {
  return [...rows.map(rowText), "", footer(caseName, filterWords, zoneName)].join("\n")
}

export function rowsHtml(rows: StreamRow[], caseName: string, filterWords: string, zoneName: string): string {
  const cells = (r: StreamRow) =>
    [r.time.full, r.phone.label, r.kind === "record" ? "" : r.app ?? "app not recorded", r.line, what(r), extras(r).join(" ")]
      .map((c) => `<td>${htmlEscape(c).replace(/\n/g, "<br>")}</td>`)
      .join("")
  return (
    "<table><thead><tr><th>Time</th><th>Phone</th><th>App</th><th>From and to</th><th>Text</th><th>Notes</th></tr></thead><tbody>" +
    rows.map((r) => `<tr>${cells(r)}</tr>`).join("") +
    `</tbody></table><p>${htmlEscape(footer(caseName, filterWords, zoneName))}</p>`
  )
}
