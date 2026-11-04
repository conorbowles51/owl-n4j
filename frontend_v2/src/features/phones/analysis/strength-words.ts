import type { AnalysisRun } from "./money-api"

/**
 * The app's one strength scale (strong, moderate, weak, faint), set by a stated rule, never by a model. Where no
 * measurement set a level, the screen says so ("rule of thumb").
 */
export const LEVELS = ["strong", "moderate", "weak", "faint"] as const
export type Level = (typeof LEVELS)[number]
export const LEVEL_WORDS: Record<string, string> = { strong: "Strong", moderate: "Moderate", weak: "Weak", faint: "Faint" }

export function isLevel(s: string): boolean {
  return (LEVELS as readonly string[]).includes(s)
}

/**
 * "Reply times: 2 moderate, 5 weak" from a run's counts (keys "<kind>_<level>"), for the graded kinds given. A run
 * made before a kind was graded has results of that kind (``by_kind``) and no level counts: they are said to be not
 * graded in that run, never "none".
 */
export function strengthCounts(run: AnalysisRun, tabs: { kind: string; label: string }[]): string[] {
  const counts = (run.counts || {}) as Record<string, unknown>
  const byKind = (counts.by_kind || {}) as Record<string, unknown>
  const out: string[] = []
  for (const t of tabs) {
    const graded = LEVELS.some((lv) => `${t.kind}_${lv}` in counts)
    const listed = Number(byKind[t.kind] ?? 0)
    if (!graded && listed > 0) {
      out.push(`${t.label}: ${listed.toLocaleString("en-US")} not graded in this run (run it again to grade them)`)
      continue
    }
    const parts = LEVELS.map((lv) => [lv, Number(counts[`${t.kind}_${lv}`] ?? 0)] as const).filter(([, n]) => n > 0)
      .map(([lv, n]) => `${n.toLocaleString("en-US")} ${lv}`)
    out.push(`${t.label}: ${parts.length ? parts.join(", ") : "none"}`)
  }
  return out
}

const fmt = (v: number) => v.toLocaleString("en-US")

/** "12 in all: strong 2, moderate 5, weak 4, faint 1." from counts by level (every level named, zeros included). */
export function levelCountWords(counts: Record<string, number>, noun: [string, string]): string {
  const total = LEVELS.reduce((s, l) => s + (counts[l] ?? 0), 0)
  return `${fmt(total)} ${total === 1 ? noun[0] : noun[1]} in all: ${LEVELS.map((l) => `${l} ${fmt(counts[l] ?? 0)}`).join(", ")}.`
}

/** Counts by level from a run's counts under a key prefix (for example "shared_" or "by_strength_"). */
export function levelCounts(counts: Record<string, unknown> | null | undefined, prefix: string): Record<string, number> {
  const out: Record<string, number> = {}
  for (const l of LEVELS) out[l] = Number((counts || {})[prefix + l] ?? 0)
  return out
}

/** The reasons a graded result carries, in two parts: how well matched, how substantiated. */
export function reasonWords(m: Record<string, unknown>): string {
  const r = (m.reasons || {}) as { match?: string[]; substantiation?: string[] }
  return [...(r.match || []), ...(r.substantiation || [])].join(" ")
}
