import type { PerceptualPage } from "../api"

const n = (v: number) => v.toLocaleString("en-US")

/** The hashing counts and the thin-data line: true counts by strength, the earlier rule, and the rule-of-thumb label. */
export function hashingWords(p: PerceptualPage): string {
  const h = p.hashing
  if (h.not_hashed_words) return h.not_hashed_words
  const failed = Object.entries(h.failed_by_reason).map(([k, c]) => `${n(c)} ${h.failed_words[k] ?? k}`).join(" ")
  return `${n(h.hashed)} of ${n(h.pictures)} pictures compared${h.waiting ? `, ${n(h.waiting)} waiting to be read` : ""}${h.failed ? `; ${n(h.failed)} could not be read: ${failed}` : "."}`
}
