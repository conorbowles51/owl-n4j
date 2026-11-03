import { instantWords } from "@/features/phones/lib/time-words"
import type { ApproachResult } from "./analysis-api"
import { TERM_WORDS } from "./typed-words"
import { anchorWords } from "./anchor-words"

export const TABS = [
  { kind: "search_hit", label: "Searches" },
  { kind: "page_hit", label: "Pages visited" },
]

const PLACE: Record<string, string> = { search: "search text", title: "page title", address: "page address" }

type M = Record<string, unknown>

export function intentWords(r: ApproachResult) {
  const m = r.measures as M
  const terms = ((m.term_kinds as string[]) || []).map((k) => TERM_WORDS[k] || k).join(" and ")
  const inn = ((m.matched_in as string[]) || []).map((w) => PLACE[w] || w).join(" and ")
  const label = (m.text as string) || (m.url as string) || "No title recorded"
  const search = r.kind === "search_hit"
  let when = "Time not recorded"
  if (m.instant) when = search ? `Searched ${instantWords(String(m.instant), "UTC")}` : `Last visited ${instantWords(String(m.instant), "UTC")}; earlier visits not dated`
  const parts = [`On ${m.phone_label}. The ${inn} matches ${terms}.`]
  if (!search && m.visit_count != null) parts.push(`${m.visit_count} visits recorded in all.`)
  if (search && m.origin) parts.push(`Origin recorded: ${m.origin}.`)
  if (r.strength === "common_term") parts.push("Every matched word appears in 3 or more records in the case, so it may be a business or site name.")
  return { title: search ? `Search: ${label}` : `Page: ${label}`, line: parts.join(" "), when }
}

/**
 * 05 section 12.3 step 3: a search with a time is placed against a key date like any instant; a page's time is its last
 * visit only, so a page last visited after a key date is never shown as visited before it, and earlier visits are not
 * dated. A record with no time says nothing.
 */
export function intentAnchor(r: ApproachResult, anchorIso: string, anchorLabel: string): string | null {
  if (r.kind !== "page_hit" || !r.period_start) return anchorWords(r.period_start, r.period_end, anchorIso, anchorLabel)
  const t = Date.parse(r.period_start)
  const a = Date.parse(anchorIso)
  if (Number.isNaN(t) || Number.isNaN(a)) return null
  if (t < a) return `Every recorded visit was before ${anchorLabel}`
  if (t > a) return `Last visited after ${anchorLabel}; earlier visits are not dated`
  return `Last visited at ${anchorLabel}`
}
