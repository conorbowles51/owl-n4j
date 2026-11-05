import type { RelationshipVolume } from "./analysis-api"

/** The records behind a count of the volume chart: exactly what the server counted, in the zone it counted in (UTC). */
export function weekRecordsPath(caseId: string, v: Pick<RelationshipVolume, "identity_keys" | "extraction_id">, weekStart?: string): string {
  const q = new URLSearchParams({ tab: "people", people: v.identity_keys.join(","), phones: v.extraction_id, kinds: "message,call,email", copies: "all", zone: "utc", notime: "0" })
  if (weekStart) {
    const end = new Date(`${weekStart}T00:00:00Z`)
    end.setUTCDate(end.getUTCDate() + 6)
    q.set("from", weekStart)
    q.set("to", end.toISOString().slice(0, 10))
  }
  return `/cases/${encodeURIComponent(caseId)}/conversations?${q.toString()}`
}

export const countWords = (n: number) => `${n.toLocaleString("en-US")} ${n === 1 ? "call, message or email" : "calls, messages and emails"}`

const rate = (x: number) => Number(x.toFixed(1)).toLocaleString("en-US")

export const changeWords = (c: { direction: string; week_start: string; rate_before: number; rate_after: number }) =>
  `${c.direction === "rise" ? "Rose" : "Fell"} from the week of ${c.week_start}: about ${rate(c.rate_before)} a week, then about ${rate(c.rate_after)} a week`
