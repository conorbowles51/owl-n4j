import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { useNavigate } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { freezeSelection, getLinkEdges, getSettings } from "@/features/phones/api"
import { liveCollectClient, type CollectLink } from "@/features/phones/collect.api"
import { useCollectTargets } from "@/features/phones/collect-targets"
import { viewFromSearch, viewToFilter } from "@/features/phones/lib/filter-url"
import { AddToMenu } from "@/features/phones/ui/AddToMenu"
import { useFinancialPresence } from "@/features/phones/financial-presence"
import type { GraphEdge, GraphNode } from "@/types/graph.types"
import { pairConversationsHref } from "@/features/graph/lib/pair-href"

const PREFIX = "phone-identity:"
const SHOWN = 8
const fmt = (n: number) => n.toLocaleString("en-US")
const plural = (n: number, one: string, many: string) => `${fmt(n)} ${n === 1 ? one : many}`

function PairEdge({ caseId, a, b, aName, bName, picked, onPick }: {
  caseId: string; a: string; b: string; aName: string; bName: string; picked: boolean; onPick: (on: boolean) => void
}) {
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
  const emails = c ? c.emails_ab + c.emails_ba : 0
  const A = edge?.a.label || aName
  const B = edge?.b.label || bName
  const words = messages === null
    ? `Counting messages between ${A} and ${B}`
    : `${plural(messages, "message", "messages")}${calls ? ` and ${plural(calls, "call", "calls")}` : ""}${emails ? ` and ${plural(emails, "email", "emails")}` : ""} between ${A} and ${B}`
  return (
    <li className="flex items-center gap-1">
      <input type="checkbox" checked={picked} onChange={(e) => onPick(e.target.checked)} aria-label={`Choose ${A} and ${B} to add`} />
      <Button size="sm" variant="outline" className="h-auto whitespace-normal text-left text-xs" disabled={q.isError}
        onClick={() => navigate(pairConversationsHref(caseId, a, b))}>
        {q.isError ? `Could not count the messages between ${A} and ${B}` : words}
      </Button>
    </li>
  )
}

type Pair = { a: string; b: string; aName: string; bName: string }
const pairKey = (p: { a: string; b: string }) => `${p.a}|${p.b}`

/**
 * CO-1 cell "Graph edges" (07 section 6.5): Add to… for one chosen pair or several. Each pair is kept as a saved
 * selection of exactly what its edge opens in Conversations (Between A and B, direct, copies collapsed), so the item
 * added opens back to those messages and its count is the edge's count. Pairs are kept only when the person asks,
 * never on a tick, so nothing is stored for a pair that is not added.
 */
export function GraphEdgeCollect({ caseId, pairs }: { caseId: string; pairs: Pair[] }) {
  // the targets and zone are read only once a pair is chosen, so an unused Graph asks for nothing more
  return pairs.length ? <ChosenPairs caseId={caseId} pairs={pairs} /> : null
}

function ChosenPairs({ caseId, pairs }: { caseId: string; pairs: Pair[] }) {
  const t = useCollectTargets(caseId)
  const settings = useQuery({ queryKey: ["phone-settings", caseId], queryFn: () => getSettings(caseId), enabled: !!caseId })
  const [kept, setKept] = useState<{ key: string; links: CollectLink[] } | null>(null)
  const [busy, setBusy] = useState<{ done: number; total: number } | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const key = pairs.map(pairKey).join(",")
  const current = kept && kept.key === key ? kept.links : null
  async function keep() {
    setErr(null)
    const zone = settings.data?.effective.name ?? "UTC"
    const out: CollectLink[] = []
    setBusy({ done: 0, total: pairs.length })
    try {
      for (const p of pairs) {
        const search = new URL(pairConversationsHref(caseId, p.a, p.b), "http://x").search
        const filter = viewToFilter(caseId, viewFromSearch(search), zone, true)
        const words = `Messages and calls between ${p.aName} and ${p.bName}`
        const s = await freezeSelection(filter, words)
        out.push({ target_type: "phone_selection", target_id: s.id, label: s.words, source_anchor: { origin: "graph", pair: [p.a, p.b] } })
        setBusy({ done: out.length, total: pairs.length })
      }
      setKept({ key, links: out })
    } catch (e) {
      const kept = out.length ? ` ${fmt(out.length)} of ${fmt(pairs.length)} were kept; nothing was added.` : ""
      setErr(`The pairs could not all be kept just now.${kept} ${e instanceof Error ? e.message : ""}`.trim())
    } finally {
      setBusy(null)
    }
  }
  const n = pairs.length
  return (
    <div className="mt-1 flex flex-wrap items-center gap-2 text-xs" aria-label="Add the chosen pairs">
      {!current && (
        <Button size="sm" variant="outline" disabled={!!busy || !settings.isSuccess} onClick={keep}>
          {busy ? `Keeping ${fmt(busy.done)} of ${fmt(busy.total)}…` : `Add ${n === 1 ? "this pair's" : `these ${fmt(n)} pairs'`} messages to…`}
        </Button>
      )}
      {current && (
        <AddToMenu caseId={caseId} links={current} noun={n === 1 ? "pair" : "pairs"} origin="Added from the Graph"
          targets={t.targets} client={liveCollectClient} keys={false} />
      )}
      {t.note && <span className="text-muted-foreground">{t.note}</span>}
      {err && <span role="alert" className="text-destructive">{err}</span>}
    </div>
  )
}

/**
 * Communication edges on the Graph (03-11, 07 J-3 Graph start): one entry per pair of phone identities that wrote to
 * or called each other, with the count Conversations shows for Between A and B, opening that list.
 */
export function PhoneCommunicationEdges({ caseId, nodes, edges }: { caseId: string; nodes: GraphNode[]; edges: GraphEdge[] }) {
  const [all, setAll] = useState(false)
  const [picked, setPicked] = useState<string[]>([])
  const presence = useFinancialPresence(caseId)
  const pairs = edges.filter((e) => e.type === "COMMUNICATED" && e.source.startsWith(PREFIX) && e.target.startsWith(PREFIX))
  if (!pairs.length) return null
  const name = new Map(nodes.map((n) => [n.key, n.label]))
  const shown = all ? pairs : pairs.slice(0, SHOWN)
  const asPair = (e: GraphEdge): Pair => {
    const a = e.source.slice(PREFIX.length)
    const b = e.target.slice(PREFIX.length)
    return { a, b, aName: name.get(e.source) || a, bName: name.get(e.target) || b }
  }
  const chosen = pairs.map(asPair).filter((p) => picked.includes(pairKey(p)))
  return (
    <section aria-label="Messages and calls between people" className="border-b border-border bg-card px-4 py-2">
      <h2 className="text-xs font-medium">Messages and calls between people on the phones ({fmt(pairs.length)} {pairs.length === 1 ? "pair" : "pairs"})</h2>
      {presence.data && !presence.data.has_financial_evidence && presence.data.phone_sentence && (
        // 07 section 8, SA-3 and SA-4: the edges carry no money words; the absence is said once
        <p className="text-xs text-muted-foreground">{presence.data.phone_sentence}</p>
      )}
      <ul className="mt-1 flex flex-wrap gap-1.5">
        {shown.map((e) => {
          const p = asPair(e)
          const k = pairKey(p)
          return <PairEdge key={k} caseId={caseId} {...p} picked={picked.includes(k)}
            onPick={(on) => setPicked((was) => (on ? [...was.filter((x) => x !== k), k] : was.filter((x) => x !== k)))} />
        })}
      </ul>
      {pairs.length > SHOWN && (
        <Button size="sm" variant="ghost" className="mt-1 text-xs" onClick={() => setAll(!all)}>
          {all ? `Show the first ${SHOWN}` : `Show all ${fmt(pairs.length)} pairs`}
        </Button>
      )}
      <GraphEdgeCollect caseId={caseId} pairs={chosen} />
    </section>
  )
}
