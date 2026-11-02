/**
 * Continue reading (03 section 7.3, 07 J-15): the threads a person opened in Conversations on this browser, newest
 * first, with where they were. Kept per case in local storage (works on plain http); nothing leaves the browser.
 */
export interface ReadingSpot {
  thread: string
  title: string
  phone: string
  extraction: string
  at: string
}

const KEY = (caseId: string) => `loupe.continue-reading.${caseId}`
const KEEP = 8

export function readingSpots(caseId: string): ReadingSpot[] {
  try {
    const raw = JSON.parse(localStorage.getItem(KEY(caseId)) ?? "[]")
    return Array.isArray(raw) ? raw.filter((x) => x && typeof x.thread === "string") : []
  } catch {
    return []
  }
}

export function rememberSpot(caseId: string, spot: ReadingSpot) {
  try {
    const rest = readingSpots(caseId).filter((s) => s.thread !== spot.thread)
    localStorage.setItem(KEY(caseId), JSON.stringify([spot, ...rest].slice(0, KEEP)))
  } catch {
    // storage full or blocked: the list is a convenience, reading is unaffected
  }
}
