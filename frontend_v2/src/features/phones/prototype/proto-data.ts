import { PHONES_ONLY, TRAINING, type FixtureCase, type FixtureMessage } from "../fixtures"

/** Counts the prototype screens show, computed from the synthetic case so every number equals its linked list. */
export function pickCase(search: string): FixtureCase {
  return new URLSearchParams(search).get("shape") === "phones-only" ? PHONES_ONLY : TRAINING
}

export function topPeople(fx: FixtureCase, phone: string, n = 10) {
  const owner = fx.phones.find((p) => p.label === phone)?.owner
  const counts = new Map<string, { messages: number; calls: number }>()
  const bump = (k: string, field: "messages" | "calls") => {
    if (!k || k === owner || k === "owner") return
    const c = counts.get(k) ?? { messages: 0, calls: 0 }
    c[field] += 1
    counts.set(k, c)
  }
  for (const m of fx.messages) if (m.phone === phone) for (const k of [m.from, ...m.to]) bump(k, "messages")
  for (const c of fx.calls) if (c.phone === phone) bump(c.other, "calls")
  return [...counts.entries()]
    .map(([key, c]) => ({ key, ...c, person: fx.people.find((p) => p.key === key)! }))
    .filter((x) => x.person)
    .sort((a, b) => b.messages + b.calls - (a.messages + a.calls) || a.person.name.localeCompare(b.person.name))
    .slice(0, n)
}

export function monthBands(fx: FixtureCase, phone: string) {
  const p = fx.phones.find((x) => x.label === phone)!
  const start = new Date(p.period_start)
  const end = new Date(p.period_end)
  const gapStart = p.no_data_days ? new Date(start.getTime() + p.no_data_days[0] * 86_400_000) : null
  const gapEnd = p.no_data_days ? new Date(start.getTime() + p.no_data_days[1] * 86_400_000) : null
  const months: { month: string; count: number; noDataDays: number }[] = []
  const cur = new Date(Date.UTC(start.getUTCFullYear(), start.getUTCMonth(), 1))
  while (cur <= end) {
    const next = new Date(Date.UTC(cur.getUTCFullYear(), cur.getUTCMonth() + 1, 1))
    const count = fx.messages.filter((m) => m.phone === phone && m.time && new Date(m.time) >= cur && new Date(m.time) < next).length
    let noDataDays = 0
    if (gapStart && gapEnd) {
      const a = Math.max(cur.getTime(), gapStart.getTime())
      const b = Math.min(next.getTime(), gapEnd.getTime())
      noDataDays = Math.max(0, Math.round((b - a) / 86_400_000))
    }
    months.push({ month: cur.toLocaleDateString("en-US", { month: "short", year: "numeric", timeZone: "UTC" }), count, noDataDays })
    cur.setUTCMonth(cur.getUTCMonth() + 1)
  }
  return months
}

export function phoneMessages(fx: FixtureCase, phone: string): FixtureMessage[] {
  return fx.messages.filter((m) => m.phone === phone)
}

export function apps(fx: FixtureCase, phone: string) {
  const c = new Map<string, number>()
  for (const m of phoneMessages(fx, phone)) c.set(m.app, (c.get(m.app) ?? 0) + 1)
  return [...c.entries()].sort((a, b) => b[1] - a[1])
}
