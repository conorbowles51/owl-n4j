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

// The answer a key's wrong words are read in: without its labelled other version. The final-answer checklist asks
// for the strongest other version in one paragraph that starts "Other version"; naming it there is not stating it.
// Measured 15 Nov 2026 (lx-citeproof gate, demo Q2 run 3): an answer placing Mateo Ruiz at the hospital with its
// discharge note scored wrong because its "Other version for 3 May" paragraph named the Brightwater theft nights.
// A heading line alone ("**Other version**") leaves out the paragraph under it as well. Mirrored by
// backend/scripts/financial_agent_fit_replay.py (without_other_version); demo-key-score-cases.json "wrong_cases".
const OTHER_VERSION = /^[\s#*_>]*other version\b/iu
export function withoutOtherVersion(text) {
  const kept = []
  let skipNext = false
  for (const para of String(text || "").split(/\n\s*\n/u)) {
    if (skipNext) { skipNext = false; continue }
    if (OTHER_VERSION.test(para)) {
      const plain = para.replace(/[#*_>]/gu, "").trim()
      skipNext = !plain.includes("\n") && !/[.!?]$/u.test(plain) && plain.length <= 80
      continue
    }
    kept.push(para)
  }
  return kept.join("\n\n")
}

export function wrongWords(mustNot, text) {
  const body = withoutOtherVersion(text).toLowerCase()
  return (mustNot || []).filter((w) => body.includes(String(w).toLowerCase()))
}
