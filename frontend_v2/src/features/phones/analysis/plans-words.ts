import type { ApproachResult } from "./analysis-api"
import { LEVEL_WORDS, reasonWords } from "./strength-words"
import { formatFull, formatWall } from "@/lib/evidence-time"

export const TABS = [
  { kind: "inconsistent", label: "Elsewhere at the time" },
  { kind: "consistent", label: "Matches the phone's location" },
  { kind: "mixed", label: "Locations disagree" },
  { kind: "no_data", label: "Placed, no location to compare" },
  { kind: "place_as_text", label: "Place written as text" },
  { kind: "no_place", label: "No place" },
  { kind: "note", label: "Notes" },
]

type M = Record<string, unknown>
const n = (v: unknown) => Number(v ?? 0).toLocaleString("en-US")
const SOURCE: Record<string, string> = { calendar: "Calendar entry", checkin: "Check-in" }
/** Shown in UTC like the rest of the analysis pages; a time with no offset stays as the report wrote it. */
const whenWords = (start: unknown) => {
  const s = String(start)
  return /(Z|[+-]\d{2}:?\d{2})$/.test(s) ? formatFull(s, "UTC") : formatWall(s)
}

export function plansWords(r: ApproachResult) {
  const m = r.measures as M
  const lvl = LEVEL_WORDS[r.strength] ?? r.strength
  if (r.kind === "note") {
    return { title: `${lvl}: note on ${m.phone_label}${m.title ? `, ${m.title}` : ""}`, line: reasonWords(m) }
  }
  const what = `${SOURCE[m.source as string] ?? "Item"} on ${m.phone_label}${m.subject ? `: ${m.subject}` : m.title ? `: ${m.title}` : ""}`
  const occ = Number(m.occurrences ?? 0) > 1 ? ` Repeats ${m.repeat_rule ? String(m.repeat_rule).toLowerCase() : ""}: ${n(m.occurrences)} occurrences, the last ${whenWords(m.last_occurrence)}.` : ""
  const nth = Number(m.occurrence_count ?? 1) > 1 ? ` Occurrence ${n(m.occurrence_index)} of ${n(m.occurrence_count)}.` : ""
  const place = m.place_text ? ` Place as written: ${m.place_text}.` : ""
  return { title: `${lvl}: ${what}`, line: `${reasonWords(m)}${place}${occ}${nth}`, when: m.start ? whenWords(m.start) : undefined }
}
