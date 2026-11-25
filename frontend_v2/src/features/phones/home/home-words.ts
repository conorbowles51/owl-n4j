/** Words and small rules of the Phones page (screen 1), apart from its components. */
import { recordPath } from "@/lib/record-links"
import { citationHref as judgedCitationHref } from "@/features/financial/lib/judgements"
import { labelText } from "../lib/labels"
import type { StreamRow } from "../schemas"
import type { ElsewhereItem } from "./HomeRecordPanel"

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

/** "1 Jan to 20 May 2024" from two days. */
export function spanWords(a: string, b: string): string {
  const d = (s: string) => ({ day: Number(s.slice(8, 10)), mon: MONTHS[Number(s.slice(5, 7)) - 1], year: s.slice(0, 4) })
  const x = d(a)
  const y = d(b)
  return x.year === y.year ? `${x.day} ${x.mon} to ${y.day} ${y.mon} ${y.year}` : `${x.day} ${x.mon} ${x.year} to ${y.day} ${y.mon} ${y.year}`
}

/** A message or call's copy key: the same kind, minute and text (a call, the same length), the server's rule. */
export function copyKey(row: StreamRow): string | null {
  if (row.kind === "record" || !row.time.instant) return null
  const minute = row.time.instant.slice(0, 16)
  if (row.kind === "call" || row.kind === "voicemail") return `call|${minute}|${row.call?.duration_s ?? ""}`
  const body = row.body?.trim()
  return body ? `${row.kind}|${minute}|${body}` : null
}

/** Phones holding each copy key among the loaded rows. */
export function phonesByCopy(rows: StreamRow[]): Map<string, Map<string, string>> {
  const out = new Map<string, Map<string, string>>()
  for (const r of rows) {
    const k = copyKey(r)
    if (!k) continue
    if (!out.has(k)) out.set(k, new Map())
    out.get(k)!.set(r.phone.extraction_id, r.phone.label)
  }
  return out
}

export function weekWords(wall: string): string {
  const d = new Date(`${wall.slice(0, 10)}T00:00:00Z`)
  return `week of ${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`
}

/** Month labels under the strip: the first week of each month, with the year on the first and last label. */
export function monthTicks(walls: string[]): { i: number; label: string }[] {
  const out: { i: number; label: string }[] = []
  let last = ""
  walls.forEach((w, i) => {
    const m = w.slice(0, 7)
    if (m !== last) {
      out.push({ i, label: MONTHS[Number(m.slice(5, 7)) - 1] + (out.length === 0 ? ` ${m.slice(0, 4)}` : m.endsWith("-01") ? ` ${m.slice(0, 4)}` : "") })
      last = m
    }
  })
  // too many to read: keep about twelve
  const step = Math.ceil(out.length / 12)
  return step > 1 ? out.filter((_, k) => k % step === 0) : out
}

export function citationHref(caseId: string, c: NonNullable<ElsewhereItem["citation"]>): string | null {
  if (c.href) return judgedCitationHref(caseId, c.href)
  const base = `/cases/${encodeURIComponent(caseId)}`
  const id = encodeURIComponent(c.id ?? "")
  if (!c.id) return null
  if (c.kind === "phone_record") return recordPath(caseId, c.id)
  if (c.kind === "transaction") return judgedCitationHref(caseId, `txn://${c.id}`)
  if (c.kind === "document") return judgedCitationHref(caseId, `doc://${c.id}${c.page ? `/${c.page}` : ""}`)
  if (c.kind === "timeline_event" || c.kind === "timeline_entry") return `${base}/timeline?event=${id}`
  return null
}

export function rowTitle(row: StreamRow): string {
  if (row.kind === "call" || row.kind === "voicemail") return "Selected call"
  if (row.kind === "email") return "Selected email"
  if (row.kind === "record") return "Selected record"
  return "Selected message"
}

export function rowText(row: StreamRow): string {
  if (row.call?.words) return row.call.words
  return row.body?.trim() || row.subject?.trim() || (row.attachments.length ? `${row.attachments.length} attachment${row.attachments.length === 1 ? "" : "s"}` : "No text recorded")
}

/** "Copy with source": the words exactly as the phone holds them, then where they come from and a link back. */
export function copyWithSource(row: StreamRow, link: string): string {
  const where = [row.from ? `From ${labelText(row.from)}` : null, row.to.length ? `To ${row.to.map(labelText).join(", ")}` : null,
    row.time.full, row.app, `${row.phone.label} report, record ${row.record_uid}`].filter(Boolean).join(". ")
  return [row.kind === "record" ? rowText(row) : `"${rowText(row)}"`, where, link].join("\n")
}
