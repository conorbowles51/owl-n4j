/** The Graph flow view's rules (03 14.3): who can sit at the centre, the words for a direction, and line width. */
export interface FlowPair {
  a: string
  b: string
  aName: string
  bName: string
}

const fmt = (n: number) => n.toLocaleString("en-US")
const plural = (n: number, one: string, many: string) => `${fmt(n)} ${n === 1 ? one : many}`

/** Everyone on a pair, the most connected first, so the view opens on the person with the most contacts. */
export function flowAnchors(pairs: FlowPair[]): { key: string; name: string; pairs: number }[] {
  const seen = new Map<string, { key: string; name: string; pairs: number }>()
  const add = (key: string, name: string) => {
    const was = seen.get(key)
    if (was) was.pairs += 1
    else seen.set(key, { key, name, pairs: 1 })
  }
  for (const p of pairs) {
    add(p.a, p.aName)
    add(p.b, p.bName)
  }
  return [...seen.values()].sort((x, y) => y.pairs - x.pairs || x.name.localeCompare(y.name))
}

export function flowWords(messages: number, calls: number, emails: number): { total: number; words: string } {
  const parts = [] as string[]
  if (messages) parts.push(plural(messages, "message", "messages"))
  if (calls) parts.push(plural(calls, "call", "calls"))
  if (emails) parts.push(plural(emails, "email", "emails"))
  return { total: messages + calls + emails, words: parts.length ? parts.join(", ") : "none" }
}

/** Line width by volume: on a log scale, so 1 and 10,000 both read on one screen. */
export function arrowWidth(count: number): number {
  return count <= 0 ? 1 : Math.min(10, 1 + 1.2 * Math.log2(1 + count))
}
