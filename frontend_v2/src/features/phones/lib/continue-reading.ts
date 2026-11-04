/**
 * Continue reading (03 section 7.3, 07 J-15, UXD-36): the threads a person opened in Conversations on this browser,
 * newest first. Kept per case in local storage (works on plain http) as record ids only: no title, name or message
 * leaves the server's answer for storage. The titles shown are asked for by id (features/phones/ContinueReading).
 */
export interface ReadingSpot {
  thread: string
  extraction: string
  record: string | null
  at: string
}

const KEY = (caseId: string) => `loupe.continue-reading.${caseId}`
const KEEP = 8

export function readingSpots(caseId: string): ReadingSpot[] {
  try {
    const raw: unknown = JSON.parse(localStorage.getItem(KEY(caseId)) ?? "[]")
    if (!Array.isArray(raw)) return []
    const spots = raw.filter((x) => x && typeof x.thread === "string")
    // Spots saved by an earlier build held the thread's title and the phone's label: those are dropped here.
    const clean: ReadingSpot[] = spots.map((x) => ({ thread: x.thread, extraction: typeof x.extraction === "string" ? x.extraction : "", record: typeof x.record === "string" ? x.record : null, at: typeof x.at === "string" ? x.at : "" }))
    if (spots.some((x) => "title" in x || "phone" in x)) localStorage.setItem(KEY(caseId), JSON.stringify(clean))
    return clean
  } catch {
    return []
  }
}

export function rememberSpot(caseId: string, spot: { thread: string; extraction: string; record?: string | null; at: string }) {
  try {
    const all = readingSpots(caseId)
    const was = all.find((s) => s.thread === spot.thread)
    const rest = all.filter((s) => s.thread !== spot.thread)
    const next: ReadingSpot = { thread: spot.thread, extraction: spot.extraction, record: spot.record ?? was?.record ?? null, at: spot.at }
    localStorage.setItem(KEY(caseId), JSON.stringify([next, ...rest].slice(0, KEEP)))
  } catch {
    // storage full or blocked: the list is a convenience, reading is unaffected
  }
}
