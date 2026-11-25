import type { Reading } from "../review/readings.api"
import type { Profile } from "../schemas"
import { fmt } from "../ui/count-sentence"

/** Words and counts behind Phones › Set up (screen 6). Pure, so the tests read them without a page. */

export type PhoneStatus = { word: string; tone: "ready" | "todo" | "busy" | "held" }

/** How the phone arrived, in one line: whole, still reading, or with differences. */
export function arrivalWords(p: Profile): string {
  const v = p.verdict
  if (v.word === "Still reading") return `Still reading: ${fmt(v.records)} records so far.`
  if (v.word === "Failed") return "The report could not be read. Add it again from the evidence page."
  if (p.completeness.reconciliation === "exact") return `Arrived whole: ${fmt(v.records)} records, every one accounted for.`
  if (p.completeness.reconciliation === "failed") return `Arrived with differences from what the report lists: ${fmt(v.records)} records read.`
  return `Read: ${fmt(v.records)} records. The report gave no totals to check them against.`
}

export function phoneStatus(p: Profile): PhoneStatus {
  if (p.verdict.word === "Still reading") return { word: "Reading", tone: "busy" }
  if (p.verdict.word === "Failed") return { word: "Not read", tone: "held" }
  const n = p.needs.length
  return n === 0 ? { word: "Ready", tone: "ready" } : { word: `${fmt(n)} to settle`, tone: "todo" }
}

/** "3 things to settle" / "nothing to settle". */
export function settleTitle(label: string, n: number): string {
  if (n === 0) return `${label}: nothing to settle`
  return `${label}: ${n === 1 ? "one thing" : `${fmt(n)} things`} to settle`
}

/** Readings checked and the share of the records they affect (each reading counts by its records). */
export function coverage(items: Reading[]) {
  const total = items.reduce((s, r) => s + r.records, 0)
  const done = items.filter((r) => r.status !== "open")
  const covered = done.reduce((s, r) => s + r.records, 0)
  return { readings: items.length, checked: done.length, percent: total ? Math.floor((100 * covered) / total) : 100 }
}

/** The plain mark an investigator sees on a phone instead of the queue. */
export function readingsMark(items: Reading[]): { words: string; checked: boolean } {
  const open = items.filter((r) => r.status === "open").length
  if (items.length === 0) return { words: "No readings to check on this phone.", checked: true }
  if (open === 0) return { words: "Every reading of this phone has been checked by a person.", checked: true }
  return {
    words: `${fmt(open)} of ${fmt(items.length)} readings of this phone are not checked yet, so its records carry the mark “Read by Loupe · not checked”. Whoever owns the case checks them on Set up.`,
    checked: false,
  }
}

const TITLE: Record<string, string> = {
  owner: "Whose phone is this?",
  zone: "Which time zone was the phone in?",
  offsetless: "Times written with no offset",
  reconciliation: "The report and what was read differ",
  readings: "Readings to check",
}
export const needTitle = (kind: string) => TITLE[kind] ?? "Something to settle"

/** Where each kind of decision sits on this page: the setting's own control opens on its anchor. */
export const NEED_ANCHOR: Record<string, string> = {
  owner: "set-owner",
  zone: "set-zone",
  offsetless: "set-offsetless",
  readings: "check-readings",
}
export const NEED_ACTION: Record<string, string> = {
  owner: "Set the owner",
  zone: "Choose a zone",
  offsetless: "Apply a zone",
  readings: "Start checking",
}
