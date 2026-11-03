import { instantWords } from "@/features/phones/lib/time-words"
import type { ApproachResult } from "./analysis-api"

export const TABS = [
  { kind: "common_contact", label: "In contact with both" },
  { kind: "saved_no_contact", label: "Saved, no contact seen" },
]

type Side = { total: number; on_own_phones: number; seen_on_other_phone: number; first: string | null; last: string | null; saved: number }
type M = { owner_a: string; owner_b: string; contact_display: string; a: Side; b: Side }
const n = (v: number) => v.toLocaleString("en-US")

function side(owner: string, s: Side) {
  if (!s.total) return `${owner}: saved as a contact, no call, message or email seen`
  const span = s.first ? ` from ${instantWords(s.first, "UTC")}${s.last && s.last !== s.first ? ` to ${instantWords(s.last, "UTC")}` : ""}` : ""
  const other = s.seen_on_other_phone ? ` (${n(s.seen_on_other_phone)} of them on the contact's own phone)` : ""
  return `${owner}: ${n(s.total)} ${s.total === 1 ? "call, message or email" : "calls, messages or emails"}${other}${span}`
}

export function commonWords(r: ApproachResult) {
  const m = r.measures as unknown as M
  return {
    title: `${m.contact_display}: linked to ${m.owner_a} and ${m.owner_b}`,
    line: `${side(m.owner_a, m.a)}. ${side(m.owner_b, m.b)}.`,
  }
}
