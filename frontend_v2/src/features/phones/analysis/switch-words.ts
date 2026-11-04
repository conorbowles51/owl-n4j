import { instantWords } from "@/features/phones/lib/time-words"
import type { ApproachResult } from "./analysis-api"

export const TABS = [
  { kind: "switch_candidate", label: "Possible number changes" },
  { kind: "switch_possible", label: "Under the defaults (weak and faint)" },
]

const MARKER: Record<string, string> = { saved_together: "one saved contact entry holds both", same_name: "named the same on a phone", never_same_day: "never active on the same day" }
type M = { from_display: string; to_display: string; last_of_first: string; first_of_second: string; gap_days: number; similarity: number; shared: number; first_counterparts: number; second_counterparts: number; markers: string[]
  level?: string; shared_besides_owners?: number; strength_reasons?: { match: string[]; substantiation: string[] } }

export function switchWords(r: ApproachResult) {
  const m = r.measures as unknown as M
  const markers = (m.markers || []).map((k) => MARKER[k] || k)
  return {
    title: `${m.from_display} stops, ${m.to_display} starts ${m.gap_days} ${m.gap_days === 1 ? "day" : "days"} later`,
    line: `${m.level ? `${m.level[0].toUpperCase()}${m.level.slice(1)}: ${(m.strength_reasons?.match || []).join("; ")}. ` : ""}${m.shared} shared counterparts (${m.first_counterparts} before, ${m.second_counterparts} after; similarity ${m.similarity}). Last contact of the first ${instantWords(m.last_of_first, "UTC")}; first of the second ${instantWords(m.first_of_second, "UTC")}.${markers.length ? ` Also: ${markers.join("; ")}.` : ""} Nothing is joined; joining them is your decision on the people.`,
  }
}

/** The pairs the run counted but does not list, with their reason (Neil 2026-11-04: nothing hidden by a cutoff). */
export function switchLeftOutWords(counts: Record<string, unknown> | null | undefined) {
  const n = (k: string) => Number(counts?.[k] || 0)
  const pairs = (v: number, verb: string) => `${v.toLocaleString("en-US")} more ${v === 1 ? `pair ${verb}s` : `pairs ${verb}`}`
  const parts: string[] = []
  if (n("share_only_owners")) parts.push(`${pairs(n("share_only_owners"), "share")} only a phone's owner (every number on a phone does)`)
  if (n("share_nothing")) parts.push(`${pairs(n("share_nothing"), "share")} no counterpart`)
  return parts.length ? `Counted, not listed: ${parts.join("; ")}.` : ""
}
