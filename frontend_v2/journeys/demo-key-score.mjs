// The demo key's expected-word match, shared by live-demo-key.mjs and mirrored by
// backend/scripts/financial_agent_fit_replay.py (expect_hit); demo-key-score-cases.json holds the cases both pass.
// An expected word counts as a whole word. An expected number never counts as a calendar day ("14 June",
// "June 14", "the 14th of June") or as part of a written date (2024-06-14, 14/06/2024). Measured 11 Nov 2026: plain
// word presence credited 4 of the 6 recorded Q1 answers, none of which names the key's place.
const MONTH = "(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\\.?"
const DATE = /\d{4}-\d{1,2}-\d{1,2}|\d{1,2}\/\d{1,2}\/\d{2,4}/gu
const escape = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")

export function expectHit(term, text) {
  const t = String(term).toLowerCase()
  const s = String(text || "").toLowerCase()
  if (/^\d+$/.test(t)) {
    const dates = [...s.matchAll(DATE)].map((m) => [m.index, m.index + m[0].length])
    for (const m of s.matchAll(new RegExp(`(?<![\\d]|\\d,)${escape(t)}(?![\\d]|,\\d)`, "gu"))) {
      const start = m.index, end = start + t.length
      if (dates.some(([a, b]) => start >= a && end <= b)) continue
      if (new RegExp(`${MONTH}\\s*$`, "u").test(s.slice(Math.max(0, start - 12), start))) continue
      if (new RegExp(`^\\s*(?:st|nd|rd|th)?\\s*(?:of\\s+)?${MONTH}`, "u").test(s.slice(end, end + 14))) continue
      return true
    }
    return false
  }
  const left = /^[\p{L}\p{N}_]/u.test(t) ? "(?<![\\p{L}\\p{N}_])" : ""
  const right = /[\p{L}\p{N}_]$/u.test(t) ? "(?![\\p{L}\\p{N}_])" : ""
  return new RegExp(left + escape(t) + right, "u").test(s)
}
