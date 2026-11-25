import { instantWords } from "../lib/time-words"
import type { ExampleKind } from "../review/readings.api"

const at = (iso: string | null | undefined, zone: string) => (iso ? instantWords(iso, zone) : null)

/** The record as the report gives it: its type, then each field the example carries, by the report's own names. */
export function reportLines(k: ExampleKind): string[] {
  const x = k.example
  const lines: string[] = [x.report_type ?? x.type_words ?? "Record"]
  for (const t of x.times) lines.push(`${t.report_field ?? t.field}  ${t.original_text ?? "(empty)"}`)
  for (const p of x.parties) lines.push(`${p.report_line || "Party"}  ${[p.name, p.identifier].filter(Boolean).join(" ") || "(empty)"}`)
  if (x.app) lines.push(`Source  ${x.app}`)
  if (x.subject) lines.push(`Subject  ${x.subject}`)
  if (x.text) lines.push(`Body  ${x.text.length > 140 ? `${x.text.slice(0, 140)}…` : x.text}`)
  if (x.deleted_state && x.deleted_state !== "Intact") lines.push(`Deleted state  ${x.deleted_state}`)
  return lines
}

/** What Loupe shows for that record, in words. */
export function loupeShows(k: ExampleKind, zone: string): string {
  const x = k.example
  const who = x.parties.map((p) => {
    const name = p.implicit_owner ? "the phone's owner" : p.name || p.identifier || "someone with no name or number"
    return p.role ? `${name} as ${p.role.replace(/_/g, " ")}` : `${name}, side not known`
  })
  const parts: string[] = []
  const when = at(x.instant, zone)
  parts.push(when ? `Placed at ${when}, and shown at that time on the timeline.` : "Time not recorded: listed at the end, never placed on the timeline.")
  if (who.length) parts.push(`People: ${who.join("; ")}.`)
  if (x.title && !x.kind) parts.push(`Listed as “${x.title}”.`)
  if (x.app) parts.push(`Through ${x.app}.`)
  if (x.direction) parts.push(x.direction === "incoming" ? "Came in to the phone." : x.direction === "outgoing" ? "Went out from the phone." : "Direction not known.")
  if (x.kind === "message" || x.kind === "email") parts.push(x.text ? "Its words are searchable." : "It has no words to search.")
  for (const t of x.times.filter((t) => t.mapped_by_this && !t.is_event_time)) {
    const w = at(t.instant, zone)
    parts.push(w ? `Also keeps ${w} as one of its times.` : "One of its times is empty and is not used.")
  }
  return parts.join(" ")
}
