/**
 * Synthetic phone cases for the kit stories and the prototype: the builder's ui-fixture.json
 * (evidence-engine/tests/phone/fixture_builder.py), committed as is and checked byte for byte by the builder's
 * tests. Invented data only.
 */
import phonesOnly from "./phones-only.json"
import training from "./training.json"
import type { PhoneRecordView } from "../types"
import type { StripDay } from "../ui/TimeStrip"

export interface FixturePerson { key: string; name: string; numbers: string[]; email: string }
export interface FixturePhone {
  label: string
  owner: string | null
  zone: string | null
  extraction_date: string
  period_start: string
  period_end: string
  no_data_days: number[] | null
  messages: number
  calls: number
  contacts: number
  files: number
  records: number
}
export interface FixtureThread { id: string; phone: string; app: string; group: boolean; participants: string[]; count: number }
export interface FixtureMessage {
  id: string
  thread: string
  phone: string
  app: string
  time: string | null
  from: string
  to: string[]
  direction: "incoming" | "outgoing"
  body: string
  deleted: string
}
export interface FixtureCall { phone: string; time: string; other: string; direction: string; status: string; seconds: number }
export interface FixtureCase {
  case: string
  synthetic: true
  people: FixturePerson[]
  phones: FixturePhone[]
  threads: FixtureThread[]
  messages: FixtureMessage[]
  calls: FixtureCall[]
}

export const TRAINING = training as unknown as FixtureCase
export const PHONES_ONLY = phonesOnly as unknown as FixtureCase

export const CASE_ZONE = "America/New_York"

export function phoneIndex(fx: FixtureCase, label: string): number {
  return fx.phones.findIndex((p) => p.label === label)
}

export function personName(fx: FixtureCase, key: string): { name: string | null; identifier: string | null; isOwner?: boolean } {
  const p = fx.people.find((x) => x.key === key)
  return p ? { name: p.name, identifier: p.numbers[0] } : { name: null, identifier: null, isOwner: key === "owner" }
}

/** A fixture message as the record panel's view. Every reading is "not yet confirmed" (nothing is reviewed). */
export function messageView(fx: FixtureCase, m: FixtureMessage): PhoneRecordView {
  const phone = fx.phones.find((p) => p.label === m.phone)!
  const owner = phone.owner
  const party = (key: string) => {
    const v = personName(fx, key)
    return { ...v, key, isOwner: key === owner || key === "owner" }
  }
  const badges: PhoneRecordView["badges"] = ["unconfirmed"]
  if (m.deleted === "Deleted") badges.push("deleted")
  if (m.deleted === "Trash") badges.push("trash")
  return {
    id: m.id,
    kind: "message",
    typeWords: "Message",
    phone: { id: phone.label, label: phone.label, index: phoneIndex(fx, phone.label), extractionDate: phone.extraction_date },
    app: m.app,
    time: m.time,
    zone: phone.zone ?? CASE_ZONE,
    direction: m.direction,
    from: party(m.from),
    to: m.to.map(party),
    body: m.body,
    origin: { state: "unconfirmed", rule: "The From field is read as the sender, and the To field as the recipients." },
    badges,
  }
}

/** Messages per day for the time strip, with the phone's no-data gap kept apart. */
export function stripDays(fx: FixtureCase, phoneLabel: string, threadId?: string): StripDay[] {
  const phone = fx.phones.find((p) => p.label === phoneLabel)!
  const zone = phone.zone ?? CASE_ZONE
  const start = new Date(phone.period_start)
  const end = new Date(phone.period_end)
  const counts = new Map<string, number>()
  const key = (iso: string) => new Intl.DateTimeFormat("en-CA", { timeZone: zone, year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(iso))
  for (const m of fx.messages) {
    if (m.phone !== phoneLabel || !m.time || (threadId && m.thread !== threadId)) continue
    const k = key(m.time)
    counts.set(k, (counts.get(k) ?? 0) + 1)
  }
  const days: StripDay[] = []
  const gap = phone.no_data_days
  for (let i = 0, t = start.getTime(); t <= end.getTime(); i++, t += 86_400_000) {
    const k = key(new Date(t).toISOString())
    days.push({ date: k, count: gap && i >= gap[0] && i < gap[1] ? null : counts.get(k) ?? 0 })
  }
  return days
}
