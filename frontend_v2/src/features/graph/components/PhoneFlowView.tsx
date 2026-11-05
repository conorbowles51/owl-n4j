import { useMemo, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Link } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { failureText, getFlowPartners, getLinkEdges } from "@/features/phones/api"
import { pairConversationsHref } from "@/features/graph/lib/pair-href"
import { useEdgeWindow } from "@/features/graph/stores/edge-window.store"
import { arrowWidth, flowAnchors, flowWords, type FlowPair } from "@/features/graph/lib/flow"

const SHOWN = 12
const fmt = (n: number) => n.toLocaleString("en-US")

function Arrow({ count, reverse }: { count: number; reverse?: boolean }) {
  const width = arrowWidth(count)
  const y = 8
  return (
    <svg width="72" height="16" viewBox="0 0 72 16" className="shrink-0 text-primary" aria-hidden="true">
      <line x1={reverse ? 12 : 0} y1={y} x2={reverse ? 72 : 60} y2={y} stroke="currentColor" strokeWidth={width} strokeDasharray={count ? undefined : "3 3"} opacity={count ? 1 : 0.4} />
      <polygon points={reverse ? `0,${y} 12,${y - 6} 12,${y + 6}` : `72,${y} 60,${y - 6} 60,${y + 6}`} fill="currentColor" opacity={count ? 1 : 0.4} />
    </svg>
  )
}

/** One person beside the anchor: each direction drawn and counted apart, from the pair edge Conversations matches. */
function FlowRow({ caseId, anchor, anchorName, other, otherName, onDrill }: {
  caseId: string; anchor: string; anchorName: string; other: string; otherName: string; onDrill: (key: string) => void
}) {
  const win = useEdgeWindow((s) => s.window)
  const q = useQuery({
    queryKey: ["graph-flow-edge", caseId, anchor, other, win?.from ?? null, win?.to ?? null],
    queryFn: () => (win
      ? getLinkEdges(caseId, [{ identity_key: anchor }, { identity_key: other }], { fromInstant: win.from, toInstant: win.to })
      : getLinkEdges(caseId, [{ identity_key: anchor }, { identity_key: other }])),
    staleTime: 60_000,
  })
  const c = q.data?.edges[0]?.communication
  const out = c ? flowWords(c.messages_ab, c.calls_ab, c.emails_ab) : null
  const back = c ? flowWords(c.messages_ba, c.calls_ba, c.emails_ba) : null
  return (
    <li className="grid grid-cols-[minmax(8rem,1fr)_auto_minmax(8rem,1fr)] items-center gap-x-2 border-t border-border/60 py-1">
      <Button size="sm" variant="link" className="h-auto justify-start whitespace-normal p-0 text-left text-xs" aria-label={`Follow from ${otherName}`} onClick={() => onDrill(other)}>
        {otherName}
      </Button>
      {q.isError ? (
        <p role="alert" className="col-span-2">Could not count the messages with {otherName}.</p>
      ) : !c ? (
        <p role="status" className="col-span-2 text-muted-foreground">Counting</p>
      ) : (
        <>
          <span className="flex flex-col">
            <span className="flex items-center gap-1" aria-hidden="true"><Arrow count={out!.total} reverse /></span>
            <span className="flex items-center gap-1" aria-hidden="true"><Arrow count={back!.total} /></span>
          </span>
          <span className="flex flex-col">
            <span>{anchorName} to {otherName}: {out!.words}</span>
            <span>{otherName} to {anchorName}: {back!.words}</span>
            <Link className="underline" to={pairConversationsHref(caseId, anchor, other, win)}>Open these messages</Link>
          </span>
        </>
      )}
    </li>
  )
}

/**
 * The Graph flow view (03 14.3, 16.2): one person at the centre, each person they were in contact with beside them,
 * and the two directions drawn apart, thicker with volume. Choosing a person re-anchors the view on them (drill); the
 * trail leads back. Counts are the pair edge's, so they match Conversations; the time window applies to them too.
 */
export function PhoneFlowView({ caseId, pairs }: { caseId: string; pairs: FlowPair[] }) {
  const anchors = useMemo(() => flowAnchors(pairs), [pairs])
  const names = useMemo(() => new Map(anchors.map((a) => [a.key, a.name])), [anchors])
  const [trail, setTrail] = useState<string[]>([])
  const [all, setAll] = useState(false)
  const anchor = trail[trail.length - 1] ?? anchors[0]?.key
  const q = useQuery({ queryKey: ["graph-flow-partners", caseId, anchor], queryFn: () => getFlowPartners(caseId, anchor!), enabled: !!anchor, staleTime: 60_000 })
  const partners = q.data?.partners ?? []
  const shown = all ? partners : partners.slice(0, SHOWN)
  const name = (key: string) => names.get(key) ?? key
  const drill = (key: string) => { setTrail((t) => [...t, key]); setAll(false) }
  if (!anchor) return null
  return (
    <section aria-label="Flow view" className="mt-1 max-h-80 overflow-auto text-xs">
      <div className="flex flex-wrap items-center gap-2">
        <label className="flex items-center gap-1">Person at the centre
          <select className="max-w-64 rounded border bg-background px-1" value={anchor} onChange={(e) => { setTrail([e.target.value]); setAll(false) }}>
            {anchors.map((a) => <option key={a.key} value={a.key}>{a.name} ({fmt(a.pairs)})</option>)}
          </select>
        </label>
        {trail.length > 1 && (
          <nav aria-label="Trail" className="flex flex-wrap items-center gap-1">
            {trail.slice(0, -1).map((key, i) => (
              <Button key={`${key}-${i}`} size="sm" variant="ghost" className="h-6 px-1 text-xs" onClick={() => setTrail(trail.slice(0, i + 1))}>Back to {name(key)}</Button>
            ))}
          </nav>
        )}
      </div>
      <p className="text-muted-foreground">
        Each line is one direction; a thicker line is more messages, calls and emails, and a dashed line is none. Pick a person to follow from them.
      </p>
      {q.isLoading && <p role="status">Finding who {name(anchor)} was in contact with</p>}
      {q.isError && <p role="alert">{failureText(q.error, "The people could not be read just now.")}</p>}
      {q.data && (
        <p role="status">{partners.length > shown.length ? `Showing the ${fmt(shown.length)} busiest of ${fmt(partners.length)} people ${name(anchor)} was in contact with.` : `${fmt(partners.length)} ${partners.length === 1 ? "person" : "people"} ${name(anchor)} was in contact with.`}</p>
      )}
      <ul>
        {shown.map((p) => (
          <FlowRow key={p.key} caseId={caseId} anchor={anchor} anchorName={name(anchor)} other={p.key} otherName={p.name ?? name(p.key)} onDrill={drill} />
        ))}
      </ul>
      {partners.length > SHOWN && (
        <Button size="sm" variant="ghost" className="mt-1 text-xs" onClick={() => setAll(!all)}>
          {all ? `Show the ${SHOWN} busiest` : `Show all ${fmt(partners.length)} people`}
        </Button>
      )}
    </section>
  )
}
