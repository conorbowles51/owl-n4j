import { instantWords } from "@/features/phones/lib/time-words"
import type { ApproachResult } from "./analysis-api"

export const TABS = [
  { kind: "typed_not_in_extraction", label: "Not found elsewhere on the phone" },
  { kind: "typed_and_present", label: "Also in messages or notes" },
]

export const TERM_WORDS: Record<string, string> = {
  contact_name: "a name the phones hold for a contact",
  phone_number: "a phone number in the case",
  account_ending: "an account ending in the financial records",
  financial_name: "an account holder or counterparty in the financial records",
  investigator_term: "a case term or a keyword list term",
  case_entity: "a name or alias of a person, organisation or other entity in the case",
  ledger_amount: "an amount in the case's ledger",
  place: "an address or place name in the case",
}

/** The kinds of term in the order the screens list them (05 10.3 step 1). */
export const TERM_KINDS = Object.keys(TERM_WORDS)

/**
 * Hits by kind of term from a completed run's counts (``hits_<kind>``), every kind listed with its count, and what
 * the vocabulary of that run could not read (``vocabulary_not_included``); nothing missing says so.
 */
export function kindCountWords(counts: Record<string, unknown> | null | undefined): { items: { kind: string; words: string; count: number }[]; missing: string } {
  const c = counts || {}
  if (!Array.isArray(c.vocabulary_not_included)) {
    // a run made before every kind was compared: it carries no per-kind counts and left kinds out
    return { items: [], missing: "This run was made before the case's entities, ledger amounts and places were compared, so they are not in it. Run it again to compare them." }
  }
  const items = TERM_KINDS.map((k) => ({ kind: k, words: TERM_WORDS[k], count: Number(c["hits_" + k] ?? 0) }))
  const left = c.vocabulary_not_included as string[]
  const missing = left.length ? `This run could not compare: ${left.join(", ")}.` : "Nothing in the case's vocabulary was left out of this run."
  return { items, missing }
}

type M = Record<string, unknown>
const n = (v: unknown) => Number(v ?? 0).toLocaleString("en-US")

export function typedWords(r: ApproachResult) {
  const m = r.measures as M
  const what = m.record_type === "Autofill" ? "Autofill value" : "Keyboard learned word"
  const terms = ((m.term_kinds as string[]) || []).map((k) => TERM_WORDS[k] || k).join(" and ")
  const where = r.kind === "typed_not_in_extraction"
    ? "Not found in any message, email, note, search or calendar entry this extraction holds."
    : `Also found in ${n(m.elsewhere_records)} ${Number(m.elsewhere_records) === 1 ? "message, email, note, search or calendar entry" : "messages, emails, notes, searches or calendar entries"} on this phone.`
  const extra = [
    m.record_type === "Autofill" && m.autofill_key ? `Autofill field: ${m.autofill_key}.` : "",
    m.frequency != null ? `The keyboard's own use count: ${m.frequency}.` : "",
  ].filter(Boolean).join(" ")
  const when = m.first_time
    ? (m.last_time && m.last_time !== m.first_time ? `${instantWords(String(m.first_time), "UTC")} to ${instantWords(String(m.last_time), "UTC")}` : instantWords(String(m.first_time), "UTC"))
    : "No time recorded"
  return {
    title: `${what} on ${m.phone_label} matches ${terms}`,
    line: `${where} ${extra} The value is hidden here: open the record behind it and press Reveal to see it (each reveal is logged).`.replace(/\s+/g, " ").trim(),
    when,
  }
}
