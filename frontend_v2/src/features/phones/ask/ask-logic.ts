import type { Scope as CorroScope } from "@/features/corroborate/api"
import type { Answer, AskPhone } from "./api"

/** The line under the question: which phones are read, and which are left out by their Outside services decision. */
export function permissionLine(phones: AskPhone[]): string {
  const read = phones.filter((p) => p.allowed !== false)
  const out = phones.filter((p) => p.allowed === false)
  const n = read.length
  let s = `Reads ${n === phones.length && n > 1 ? "all " : ""}${n} ${n === 1 ? "phone" : "phones"} in scope, and checks what it finds against the financial records, the documents and the case timeline.`
  if (out.length) s += ` Left out: ${out.map((p) => p.label).join(", ")} (AI reading is not allowed in Case settings).`
  return s
}

/** What Corroborate starts from for one statement (or the whole answer): its cited records and its dates. */
export function corroborateStart(answer: Answer, which: number | "all") {
  const sts = which === "all" ? answer.statements : [answer.statements[which]].filter(Boolean)
  const members = sts.flatMap((s) => s.cite_labels.map((c) => ({ type: "phone_record", id: c.record, label: c.label })))
  const seen = new Set<string>()
  const unique = members.filter((m) => (seen.has(m.id) ? false : (seen.add(m.id), true)))
  const dates = sts.flatMap((s) => [s.date_from, s.date_to]).filter((d): d is string => !!d).sort()
  const people = [...new Set(sts.flatMap((s) => s.people))]
  const scope: CorroScope = dates.length ? { from: dates[0], to: dates[dates.length - 1] } : {}
  return { members: unique, scope, people }
}
