import { type FixtureCase, type FixtureMessage } from "../fixtures"
import { fmt } from "../ui/count-sentence"

/**
 * Prototype: Needs a decision, readings group (07 J-8): readings grouped by phone and type, ordered by records
 * affected, each a plain sentence; examples drawn from the whole set covering every kind present; Looks right
 * disabled until every kind has been shown; y / x / s; a standard reason is recorded and labelled as such.
 * Synthetic data; nothing is saved.
 */
interface Reading {
  id: string
  phone: string
  app: string
  sentence: string
  affected: FixtureMessage[]
  kinds: { kind: string; example: FixtureMessage }[]
}

function kindsOf(fx: FixtureCase, ms: FixtureMessage[]) {
  const groups = new Set(fx.threads.filter((t) => t.group).map((t) => t.id))
  const pick = (label: string, test: (m: FixtureMessage) => boolean) => {
    const found = ms.find(test)
    return found ? [{ kind: label, example: found }] : []
  }
  return [
    ...pick("Incoming, one to one", (m) => m.direction === "incoming" && !groups.has(m.thread) && !!m.body),
    ...pick("Outgoing, one to one", (m) => m.direction === "outgoing" && !groups.has(m.thread) && !!m.body),
    ...pick("Group message", (m) => groups.has(m.thread)),
    ...pick("Empty text", (m) => !m.body),
    ...pick("No time", (m) => !m.time),
  ]
}

export function readingsFor(fx: FixtureCase): Reading[] {
  const out: Reading[] = []
  for (const p of fx.phones) {
    const byApp = new Map<string, FixtureMessage[]>()
    for (const m of fx.messages) if (m.phone === p.label) byApp.set(m.app, [...(byApp.get(m.app) ?? []), m])
    for (const [app, ms] of byApp) {
      out.push({
        id: `${p.label}-${app}`,
        phone: p.label,
        app,
        sentence: `On ${p.label}, ${app} messages: the From field is read as the sender. Affects ${fmt(ms.length)} messages.`,
        affected: ms,
        kinds: kindsOf(fx, ms),
      })
    }
  }
  return out.sort((a, b) => b.affected.length - a.affected.length)
}
