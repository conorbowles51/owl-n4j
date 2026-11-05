import { fetchAPI } from "@/lib/api-client"

/**
 * What one person has already seen of the phone screens (07 section 9). Saved per person on the server, so it follows
 * them to any browser. This file stays small: the sidebar imports it into the app shell.
 */
export type Mark = "phones_new_hidden" | "first_phone_card_seen"
export interface Marks {
  marks: Partial<Record<Mark, string>>
}

/** The day the phone screens reached people. */
export const PHONES_FEATURE_DATE = "2026-11-05T00:00:00Z"
export const NEW_MARK_DAYS = 7
const DAY_MS = 86_400_000

/** ?help=phones on the Phones page reopens the first-phone card (the Help entry in the sidebar). */
export const HELP_PARAM = "help"

export const marksQuery = {
  queryKey: ["phone-my-marks"],
  queryFn: () => fetchAPI<Marks>("/api/phones/my-marks"),
  staleTime: 5 * 60_000,
}

export const saveMark = (mark: Mark) => fetchAPI<Marks>(`/api/phones/my-marks/${mark}`, { method: "PUT" })
export const hideNewMarks = () => saveMark("phones_new_hidden")

/**
 * When the "New" mark ends: 7 days from the feature date, or from the case's first phone when that came later, since
 * the section is about the first phone in a case. Days are counted from the moment itself.
 */
export function newMarksUntil(ingestedAt: (string | null)[]): number {
  const firsts = ingestedAt.flatMap((at) => (at ? [Date.parse(at)] : []))
  const start = Math.max(Date.parse(PHONES_FEATURE_DATE), firsts.length ? Math.min(...firsts) : 0)
  return start + NEW_MARK_DAYS * DAY_MS
}
