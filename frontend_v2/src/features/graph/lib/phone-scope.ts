import type { Scope } from "@/features/phones/ui/ScopeBar"
import type { GraphEdge, GraphNode } from "@/types/graph.types"

const IDENTITY = "phone-identity:"
const PHONE = "phone-extraction:"
const fmt = (n: number) => n.toLocaleString("en-US")

/** The Graph nodes of a phone scope: its people, else its phones and whoever appears on them, else the phone layer. */
export function graphScopeKeys(scope: Scope, nodes: GraphNode[], edges: GraphEdge[]): string[] {
  const loaded = new Set(nodes.map((n) => n.key))
  const phones = scope.phones.map((p) => `${PHONE}${p.id}`)
  if (scope.people.length) return [...scope.people.map((p) => `${IDENTITY}${p.key}`), ...phones].filter((k) => loaded.has(k))
  if (!phones.length) return nodes.filter((n) => n.key.startsWith(IDENTITY) || n.key.startsWith(PHONE)).map((n) => n.key)
  const on = new Set(phones)
  const seen = edges.filter((e) => e.type === "APPEARS_ON" && on.has(e.target)).map((e) => e.source)
  return [...new Set([...phones, ...seen])].filter((k) => loaded.has(k))
}

/** What the Graph cannot show of a scope, in words and numbers; `inScope` is null while it is being counted. */
export function graphScopeLimits(scope: Scope, shown: number, inScope: number | null): string[] {
  const out: string[] = []
  if (inScope === null) out.push(`Showing ${fmt(shown)} people and phones.`)
  else if (shown >= inScope) out.push(`Showing all ${fmt(inScope)} people and phones in this scope.`)
  else {
    out.push(`Showing ${fmt(shown)} of ${fmt(inScope)} people and phones in this scope. The other ${fmt(inScope - shown)} are not drawn: the Graph holds phones, their owners, linked people and those who took part in a message or call, not numbers found only in an address book.`)
  }
  if (scope.people.length && scope.mode !== "involving") out.push("The Graph shows who is connected, not who sent what, so the direction chosen is not applied.")
  if (scope.kinds.length) out.push("The Graph does not narrow by kind of record.")
  if (scope.labels.length) out.push("The Graph does not narrow by label.")
  if (scope.window) out.push("The dates apply to the counts on communication edges; the people and phones drawn are not narrowed by them.")
  return out
}
