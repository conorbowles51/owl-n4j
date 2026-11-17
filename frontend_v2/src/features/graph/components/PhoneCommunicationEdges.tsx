import { useEffect, useMemo, useState } from "react"
import { LearnMore } from "@/components/ui/learn-more"
import { ChevronDown, ChevronRight } from "lucide-react"
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
import { edgeKey, useEdgeWindow } from "@/features/graph/stores/edge-window.store"
import { usePairHighlight } from "@/features/graph/stores/pair-highlight.store"
import { contactSummary, contactWords } from "@/features/graph/lib/contact-words"
import { PhoneFlowView } from "./PhoneFlowView"

const PREFIX = "phone-identity:"
const SHOWN = 8
const fmt = (n: number) => n.toLocaleString("en-US")

function PairRow({ caseId, a, b, aName, bName, picked, onPick, missing }: {
  caseId: string; a: string; b: string; aName: string; bName: string; picked: boolean; onPick: (on: boolean) => void
  /** Names of the two people the graph does not draw now (a filter or the type list hides them). */
  missing: string[]
}) {
  const navigate = useNavigate()
  const win = useEdgeWindow((s) => s.window)
  const setCount = useEdgeWindow((s) => s.setCount)
  const setHover = usePairHighlight((s) => s.setHover)
  const q = useQuery({
    queryKey: ["graph-pair-edge", caseId, a, b, win?.from ?? null, win?.to ?? null],
    queryFn: () => (win
      ? getLinkEdges(caseId, [{ identity_key: a }, { identity_key: b }], { fromInstant: win.from, toInstant: win.to })
      : getLinkEdges(caseId, [{ identity_key: a }, { identity_key: b }])),
    staleTime: 60_000,
  })
  const edge = q.data?.edges[0]
  const c = edge?.communication
  const messages = c ? c.messages_ab + c.messages_ba : null
  const calls = c ? c.calls_ab + c.calls_ba : 0
  const emails = c ? c.emails_ab + c.emails_ba : 0
  useEffect(() => {
    if (win && messages !== null) setCount(edgeKey(a, b), messages + calls + emails)
    else if (win && q.data && !edge) setCount(edgeKey(a, b), 0)
  }, [win, messages, calls, emails, a, b, q.data, edge, setCount])
  const A = edge?.a.label || aName
  const B = edge?.b.label || bName
  const words = q.isError
    ? "Could not be counted just now"
    : messages === null
      ? (q.data ? (win ? "No contact in these dates" : "No contact") : "Counting")
      : `${contactWords(messages, calls, emails)}${win ? " in these dates" : ""}`
  const k = edgeKey(a, b)
  return (
    <tr className="border-t border-border align-top hover:bg-muted/50" data-testid="contact-pair"
      onMouseEnter={() => setHover(k)} onMouseLeave={() => setHover(null)}
      onFocus={() => setHover(k)} onBlur={() => setHover(null)}>
      <td className="w-12 py-0.5 pr-2">
        <input type="checkbox" checked={picked} onChange={(e) => onPick(e.target.checked)} aria-label={`Choose ${A} and ${B}`} />
      </td>
      <td className="py-0.5 pr-2">
        <span className="whitespace-nowrap font-medium">{A}</span> and <span className="whitespace-nowrap font-medium">{B}</span>
        {/* narrow screens: the count sits under the names instead of in its own column */}
        <span className="block sm:hidden">{words}</span>
        {missing.length > 0 && (
          <span className="block text-muted-foreground">
            {missing.length === 2 ? "Neither is drawn on the graph now." : `${missing[0]} is not drawn on the graph now.`}
          </span>
        )}
      </td>
      <td className="hidden py-0.5 pr-2 whitespace-nowrap sm:table-cell" role={q.isError ? "alert" : undefined}>{words}</td>
      <td className="py-0.5 text-right">
        <Button size="sm" variant="outline" className="h-auto min-h-5 whitespace-normal px-2 text-xs" disabled={q.isError}
          aria-label={`Show the messages between ${A} and ${B}`}
          onClick={() => navigate(pairConversationsHref(caseId, a, b, win))}>
          Show their messages
        </Button>
      </td>
    </tr>
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
      const kept = out.length ? ` ${fmt(out.length)} of ${fmt(pairs.length)} were saved; nothing was added.` : ""
      setErr(`The pairs could not all be saved just now.${kept} ${e instanceof Error ? e.message : ""}`.trim())
    } finally {
      setBusy(null)
    }
  }
  const n = pairs.length
  return (
    <div className="mt-1 flex flex-wrap items-center gap-2 text-xs" aria-label="Add the chosen pairs">
      {!current && (
        <Button size="sm" variant="outline" className="h-auto min-h-7 min-w-0 shrink whitespace-normal text-left" disabled={!!busy || !settings.isSuccess} onClick={keep}>
          {busy ? `Saving ${fmt(busy.done)} of ${fmt(busy.total)}…` : `Add the ${n === 1 ? "chosen pair's" : `${fmt(n)} chosen pairs'`} messages to a dossier, theory or note`}
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

/** The Graph time slider (03 14.3): a window of whole days (UTC) that recounts every listed pair and restyles the
 * canvas lines from those counts; "Clear dates" goes back to all dates. Nodes are not reloaded. */
function DateRange() {
  const win = useEdgeWindow((s) => s.window)
  const setWindow = useEdgeWindow((s) => s.setWindow)
  const [from, setFrom] = useState(win?.from.slice(0, 10) ?? "")
  const [to, setTo] = useState(win?.to.slice(0, 10) ?? "")
  useEffect(() => () => setWindow(null), [setWindow])  // leaving the Graph clears the dates
  const valid = /^\d{4}-\d{2}-\d{2}$/.test(from) && /^\d{4}-\d{2}-\d{2}$/.test(to) && from <= to
  const apply = () => {
    const end = new Date(`${to}T00:00:00Z`); end.setUTCDate(end.getUTCDate() + 1)
    setWindow({ from: `${from}T00:00:00Z`, to: new Date(end.getTime() - 1000).toISOString().replace(".000Z", "Z") })
  }
  return (
    <div className="mt-1.5 flex flex-wrap items-center gap-2" role="group" aria-label="Dates to count">
      <label htmlFor="contact-from">Count only between</label>
      <input id="contact-from" type="date" value={from} onChange={(e) => setFrom(e.target.value)} className="rounded border bg-background px-1" />
      <label htmlFor="contact-to">and</label>
      <input id="contact-to" type="date" value={to} onChange={(e) => setTo(e.target.value)} className="rounded border bg-background px-1" />
      <Button size="sm" variant="outline" className="h-6 px-2 text-xs" disabled={!valid} onClick={apply}>Count</Button>
      {win && <Button size="sm" variant="ghost" className="h-6 px-2 text-xs" onClick={() => { setWindow(null); setFrom(""); setTo("") }}>Clear dates</Button>}
      <span className="text-muted-foreground">{win
        ? `Counts cover ${win.from.slice(0, 10)} to ${win.to.slice(0, 10)} (UTC). On the graph, a dashed line means no contact in those dates.`
        : "Counts cover all dates."}</span>
    </div>
  )
}

const openKey = (caseId: string) => `loupe.graph.people-in-contact.${caseId}`
function readOpen(caseId: string): boolean {
  try { return localStorage.getItem(openKey(caseId)) === "open" } catch { return false }
}

/**
 * People in contact (lx-graphclarity B; was "Messages and calls between people", 03-11, 07 J-3): one row per pair of
 * phone identities that wrote to, called or emailed each other, busiest first, with the count Conversations shows for
 * Between A and B. Closed by default to one line; open or closed is remembered per case. Pointing at or choosing a
 * row highlights the two people and their line on the graph.
 */
export function PhoneCommunicationEdges({ caseId, nodes, edges, shownKeys }: {
  caseId: string; nodes: GraphNode[]; edges: GraphEdge[]
  /** Keys of the nodes the graph draws now; a pair with someone missing says so. Defaults to every node. */
  shownKeys?: Set<string>
}) {
  const [open, setOpen] = useState(() => readOpen(caseId))
  const [all, setAll] = useState(false)
  const [picked, setPicked] = useState<string[]>([])
  const [flow, setFlow] = useState(false)
  const setChosen = usePairHighlight((s) => s.setChosen)
  const setHover = usePairHighlight((s) => s.setHover)
  const presence = useFinancialPresence(caseId)
  useEffect(() => { setOpen(readOpen(caseId)); setPicked([]) }, [caseId])
  useEffect(() => { setChosen(open ? picked.map((k) => { const [a, b] = k.split("|"); return edgeKey(a, b) }) : []) }, [open, picked, setChosen])
  useEffect(() => () => { setChosen([]); setHover(null) }, [setChosen, setHover])
  const pairs = useMemo(() => edges
    .filter((e) => e.type === "COMMUNICATED" && e.source.startsWith(PREFIX) && e.target.startsWith(PREFIX))
    .map((e, i) => ({ e, i }))
    // busiest first by the count the link stores; ties and uncounted links keep the graph's order
    .sort((x, y) => (y.e.contact ?? -1) - (x.e.contact ?? -1) || x.i - y.i)
    .map(({ e }) => e), [edges])
  if (!pairs.length) return null
  const name = new Map(nodes.map((n) => [n.key, n.label]))
  const shown = all ? pairs : pairs.slice(0, SHOWN)
  const asPair = (e: GraphEdge): Pair => {
    const a = e.source.slice(PREFIX.length)
    const b = e.target.slice(PREFIX.length)
    return { a, b, aName: name.get(e.source) || a, bName: name.get(e.target) || b }
  }
  const chosen = pairs.map(asPair).filter((p) => picked.includes(pairKey(p)))
  const toggle = () => {
    const next = !open
    setOpen(next)
    try { localStorage.setItem(openKey(caseId), next ? "open" : "closed") } catch { /* private mode: not remembered */ }
    if (!next) setHover(null)
  }
  const Chevron = open ? ChevronDown : ChevronRight
  return (
    <section aria-label="People in contact" data-guide="graph-people-in-contact" className="border-b border-border bg-card px-4 py-1.5 text-xs">
      <button type="button" aria-expanded={open} aria-controls="people-in-contact-body" onClick={toggle}
        className="flex w-full items-start gap-1 text-left hover:text-foreground">
        <Chevron className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
        <span><span className="font-medium">People in contact:</span> {contactSummary(pairs.length)}</span>
      </button>
      {open && (
        <div id="people-in-contact-body" className="mt-1 max-h-[32vh] overflow-auto pl-4.5">
          <p className="text-muted-foreground">
            Each row is two people on the phones. The numbers count their messages, calls and emails, busiest first.
            Point at a row to see the two people on the graph; Show their messages opens the messages themselves.
            <LearnMore term="People in contact" />
          </p>
          {presence.data && !presence.data.has_financial_evidence && presence.data.phone_sentence && (
            // 07 section 8, SA-3 and SA-4: the pairs carry no money words; the absence is said once
            <p className="text-muted-foreground">{presence.data.phone_sentence}</p>
          )}
          <div className="flex flex-wrap items-center gap-x-4">
            <DateRange />
            <Button size="sm" variant="outline" className="mt-1.5 h-auto min-h-6 min-w-0 shrink whitespace-normal px-2 text-left text-xs" aria-pressed={flow} onClick={() => setFlow(!flow)}>
              {flow ? "Show the list of pairs" : "Show one person's contacts, each direction apart"}
            </Button>
          </div>
          {flow ? (
            <PhoneFlowView caseId={caseId} pairs={pairs.map(asPair)} />
          ) : (
            <>
              {/* what to do with the chosen pairs sits above the list, in sight of the boxes */}
              <GraphEdgeCollect caseId={caseId} pairs={chosen} />
              <table className="mt-1.5 w-full max-w-4xl border-collapse">
                <thead>
                  <tr className="text-left text-muted-foreground">
                    <th scope="col" className="pr-2 font-normal">Choose</th>
                    <th scope="col" className="pr-2 font-normal">People</th>
                    <th scope="col" className="hidden pr-2 font-normal sm:table-cell">Contact</th>
                    <th scope="col" className="font-normal"><span className="sr-only">Messages</span></th>
                  </tr>
                </thead>
                <tbody>
                  {shown.map((e) => {
                    const p = asPair(e)
                    const k = pairKey(p)
                    const missing = shownKeys ? [e.source, e.target].filter((key) => !shownKeys.has(key)).map((key) => name.get(key) || key.slice(PREFIX.length)) : []
                    return <PairRow key={k} caseId={caseId} {...p} picked={picked.includes(k)} missing={missing}
                      onPick={(on) => setPicked((was) => (on ? [...was.filter((x) => x !== k), k] : was.filter((x) => x !== k)))} />
                  })}
                </tbody>
              </table>
              {pairs.length > SHOWN && (
                <Button size="sm" variant="ghost" className="mt-1 h-6 px-2 text-xs" onClick={() => setAll(!all)}>
                  {all ? `Show the ${SHOWN} busiest` : `Show all ${fmt(pairs.length)} pairs`}
                </Button>
              )}
            </>
          )}
        </div>
      )}
    </section>
  )
}
