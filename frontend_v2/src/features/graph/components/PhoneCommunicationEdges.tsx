import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { useNavigate } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { getLinkEdges } from "@/features/phones/api"
import type { GraphEdge, GraphNode } from "@/types/graph.types"

const PREFIX = "phone-identity:"
const SHOWN = 8
const fmt = (n: number) => n.toLocaleString("en-US")
const plural = (n: number, one: string, many: string) => `${fmt(n)} ${n === 1 ? one : many}`

/** Where a pair's edge opens: Conversations, Between A and B, with the same direct, copies-collapsed scope the edge
 * is counted with (07 J-3, a Graph edge start). */
export function pairConversationsHref(caseId: string, a: string, b: string): string {
  const q = new URLSearchParams({ tab: "people", people: `${a},${b}`, mode: "between" })
  return `/cases/${encodeURIComponent(caseId)}/conversations?${q.toString()}`
}

function PairEdge({ caseId, a, b, aName, bName }: { caseId: string; a: string; b: string; aName: string; bName: string }) {
  const navigate = useNavigate()
  const q = useQuery({
    queryKey: ["graph-pair-edge", caseId, a, b],
    queryFn: () => getLinkEdges(caseId, [{ identity_key: a }, { identity_key: b }]),
    staleTime: 60_000,
  })
  const edge = q.data?.edges[0]
  const c = edge?.communication
  const messages = c ? c.messages_ab + c.messages_ba : null
  const calls = c ? c.calls_ab + c.calls_ba : 0
  const A = edge?.a.label || aName
  const B = edge?.b.label || bName
  const words = messages === null
    ? `Counting messages between ${A} and ${B}`
    : `${plural(messages, "message", "messages")}${calls ? ` and ${plural(calls, "call", "calls")}` : ""} between ${A} and ${B}`
  return (
    <li>
      <Button size="sm" variant="outline" className="h-auto whitespace-normal text-left text-xs" disabled={q.isError}
        onClick={() => navigate(pairConversationsHref(caseId, a, b))}>
        {q.isError ? `Could not count the messages between ${A} and ${B}` : words}
      </Button>
    </li>
  )
}

/**
 * Communication edges on the Graph (03-11, 07 J-3 Graph start): one entry per pair of phone identities that wrote to
 * or called each other, with the count Conversations shows for Between A and B, opening that list.
 */
export function PhoneCommunicationEdges({ caseId, nodes, edges }: { caseId: string; nodes: GraphNode[]; edges: GraphEdge[] }) {
  const [all, setAll] = useState(false)
  const pairs = edges.filter((e) => e.type === "COMMUNICATED" && e.source.startsWith(PREFIX) && e.target.startsWith(PREFIX))
  if (!pairs.length) return null
  const name = new Map(nodes.map((n) => [n.key, n.label]))
  const shown = all ? pairs : pairs.slice(0, SHOWN)
  return (
    <section aria-label="Messages and calls between people" className="border-b border-border bg-card px-4 py-2">
      <h2 className="text-xs font-medium">Messages and calls between people on the phones ({fmt(pairs.length)} {pairs.length === 1 ? "pair" : "pairs"})</h2>
      <ul className="mt-1 flex flex-wrap gap-1.5">
        {shown.map((e) => {
          const a = e.source.slice(PREFIX.length)
          const b = e.target.slice(PREFIX.length)
          return <PairEdge key={`${a}|${b}`} caseId={caseId} a={a} b={b} aName={name.get(e.source) || a} bName={name.get(e.target) || b} />
        })}
      </ul>
      {pairs.length > SHOWN && (
        <Button size="sm" variant="ghost" className="mt-1 text-xs" onClick={() => setAll(!all)}>
          {all ? `Show the first ${SHOWN}` : `Show all ${fmt(pairs.length)} pairs`}
        </Button>
      )}
    </section>
  )
}
