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
