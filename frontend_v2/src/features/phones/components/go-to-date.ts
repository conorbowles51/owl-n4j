import { fmt } from "../ui/count-sentence"

export interface DayCount {
  day: string
  count: number
}

export type DateLanding =
  | { kind: "day"; day: string }
  | { kind: "none"; words: string; before: DayCount | null; after: DayCount | null }

export const short = (day: string) =>
  new Date(`${day}T12:00:00Z`).toLocaleDateString("en-US", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" })

/**
 * Where Go to date lands (03 section 6.7, 07 J-4): the day itself when it has messages in the list, else the
 * wording "No messages on March 12, 2023 in this thread. Nearest: March 10, 2023 (14) and March 15, 2023 (3)."
 * with the nearest day before and after, each counted. Days are the index's own days, so the counts are the
 * ones the day headers show.
 */
export function landing(days: DayCount[], want: string, where: string, noun = "messages"): DateLanding {
  const sorted = [...days].filter((d) => d.count > 0).sort((a, b) => a.day.localeCompare(b.day))
  if (sorted.some((d) => d.day === want)) return { kind: "day", day: want }
  const before = [...sorted].reverse().find((d) => d.day < want) ?? null
  const after = sorted.find((d) => d.day > want) ?? null
  const near = [before, after].filter((d): d is DayCount => !!d).map((d) => `${short(d.day)} (${fmt(d.count)})`)
  const words = `No ${noun} on ${short(want)} ${where}.${near.length ? ` Nearest: ${near.join(" and ")}.` : ""}`
  return { kind: "none", words, before, after }
}
