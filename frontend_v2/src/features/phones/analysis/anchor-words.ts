/**
 * Where a result's period sits against a key date (05 section 6.3 step 6): wholly before, wholly after, or "could
 * have occurred before or after" when the period spans it. A result with no period says nothing.
 */
export function anchorWords(start: string | null, end: string | null, anchorIso: string, anchorLabel: string): string | null {
  if (!start && !end) return null
  const a = Date.parse(anchorIso)
  const s = Date.parse(start ?? end!)
  const e = Date.parse(end ?? start!)
  if (Number.isNaN(a) || Number.isNaN(s) || Number.isNaN(e)) return null
  if (e < a) return `Before ${anchorLabel}`
  if (s > a) return `After ${anchorLabel}`
  if (s === e) return `At ${anchorLabel}`
  return `Could have occurred before or after ${anchorLabel}`
}
