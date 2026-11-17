import type { Incident, Scope } from "./api"

export type Span = "hour" | "day" | "week"
export const SPAN_WORDS: Record<Span, string> = { hour: "1 hour", day: "1 day", week: "1 week" }

const DAY_MS = 86_400_000
const iso = (ms: number) => new Date(ms).toISOString()

/**
 * The scope for "the incident ± a span". Days and weeks are whole days round the date. An hour needs a time stated
 * with the date; without one it returns null, and the screen says so rather than guessing a time. Times are read as UTC
 * and the scope names that zone.
 */
export function presetScope(incident: Incident, span: Span): Scope | null {
  const label = `the incident of ${incident.date}${incident.time ? ` ${incident.time}` : ""}, ± ${SPAN_WORDS[span]}`
  if (span === "hour") {
    if (!incident.time) return null
    const at = Date.parse(`${incident.date}T${incident.time}:00Z`)
    if (Number.isNaN(at)) return null
    return { zone: "UTC", window: { from_at: iso(at - 3_600_000), to_at: iso(at + 3_600_000), label } }
  }
  const mid = Date.parse(`${incident.date}T00:00:00Z`)
  if (Number.isNaN(mid)) return null
  const n = span === "day" ? 1 : 7
  return { zone: "UTC", from: iso(mid - n * DAY_MS).slice(0, 10), to: iso(mid + n * DAY_MS).slice(0, 10) }
}
