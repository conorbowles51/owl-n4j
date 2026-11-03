import { instantWords } from "@/features/phones/lib/time-words"
import type { ApproachResult } from "./analysis-api"

export const TABS = [{ kind: "switch_candidate", label: "Possible number changes" }]

const MARKER: Record<string, string> = { saved_together: "one saved contact entry holds both", same_name: "named the same on a phone", never_same_day: "never active on the same day" }
type M = { from_display: string; to_display: string; last_of_first: string; first_of_second: string; gap_days: number; similarity: number; shared: number; first_counterparts: number; second_counterparts: number; markers: string[] }

export function switchWords(r: ApproachResult) {
  const m = r.measures as unknown as M
  const markers = (m.markers || []).map((k) => MARKER[k] || k)
  return {
    title: `${m.from_display} stops, ${m.to_display} starts ${m.gap_days} ${m.gap_days === 1 ? "day" : "days"} later`,
    line: `${m.shared} shared counterparts (${m.first_counterparts} before, ${m.second_counterparts} after; similarity ${m.similarity}). Last contact of the first ${instantWords(m.last_of_first, "UTC")}; first of the second ${instantWords(m.first_of_second, "UTC")}.${markers.length ? ` Also: ${markers.join("; ")}.` : ""} Nothing is joined; joining them is your decision on the people.`,
  }
}
