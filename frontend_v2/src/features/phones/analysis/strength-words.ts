import type { AnalysisRun } from "./money-api"

/** The app's one strength scale (strong, moderate, weak, faint), set by a stated rule, never by a model. */
export const LEVELS = ["strong", "moderate", "weak", "faint"] as const
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
