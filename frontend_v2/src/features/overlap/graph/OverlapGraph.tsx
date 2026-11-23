import { LearnMore } from "@/components/ui/learn-more"
import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { openCorroborate } from "@/features/leads/open"
import { Button } from "@/components/ui/button"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { isRefused, memberOf, overlapsAPI, type GoBetweenPanel, type Overlaps } from "../people/api"
import { H, W, layout, lineWidth } from "./layout"

export function OverlapGraph({ caseId }: { caseId: string }) {
  const q = useQuery({ queryKey: ["corroborate-overlaps", caseId, false], queryFn: () => overlapsAPI.get(caseId), staleTime: 60_000 })
  const [picked, setPicked] = useState<string | null>(null)
  if (q.isLoading) {
    return <div role="status" className="flex items-center gap-2 p-6 text-sm text-muted-foreground"><LoadingSpinner /> Reading who reaches whom…</div>
  }
  if (q.isError || !q.data) return <p role="alert" className="p-6 text-sm">The people graph could not be read. Try again in a minute.</p>
  if (isRefused(q.data)) return <p role="status" className="p-6 text-sm">{q.data.words}</p>
  const data = q.data
  const g = data.graph
  const pos = layout(g.nodes.map((n) => n.key))
  const label = new Map(g.nodes.map((n) => [n.key, n.label]))
  const most = Math.max(1, ...g.lines.map((l) => l.records))
  const first = picked ?? g.nodes.find((n) => n.key.startsWith("phone:"))?.key ?? null
  const panel = first ? data.go_betweens[first] : null
  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-y-auto lg:flex-row" data-testid="overlap-graph">
      <div className="min-w-0 flex-1 p-3">
        <p className="text-xs text-muted-foreground">
          Line width = records between the two. Dashed = through a go-between. Square = documents naming both.
        </p>
        <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full max-w-3xl" role="img" aria-label="People, go-betweens and documents">
          {g.dashed.map((d) => {
            const a = pos.get(d.a), b = pos.get(d.b)
            if (!a || !b) return null
            return (
              <g key={`d:${d.a}:${d.b}`}>
                <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="currentColor" strokeOpacity={0.45} strokeWidth={1.5} strokeDasharray="6 5" />
                <title>{`${label.get(d.a)} and ${label.get(d.b)}: no direct contact${d.via_label ? `; route through ${d.via_label}` : ""}${d.money ? `; ${d.money} payment${d.money === 1 ? "" : "s"}` : ""}`}</title>
                {d.money > 0 && (
                  <text x={(a.x + b.x) / 2} y={(a.y + b.y) / 2 + 12} textAnchor="middle" paintOrder="stroke" style={{ stroke: "hsl(var(--background))" }} strokeWidth={4}
                    className="fill-muted-foreground text-[10px]">no direct contact; {d.money} payment{d.money === 1 ? "" : "s"}</text>
                )}
              </g>
            )
          })}
          {g.lines.map((l) => {
            const a = pos.get(l.a), b = pos.get(l.b)
            if (!a || !b) return null
            return (
              <g key={`l:${l.a}:${l.b}`}>
                <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="hsl(215 60% 45%)" strokeOpacity={0.7} strokeWidth={lineWidth(l.records, most)} />
                <text x={a.x + (b.x - a.x) * 0.42} y={a.y + (b.y - a.y) * 0.42 - 4} textAnchor="middle" paintOrder="stroke"
                  style={{ stroke: "hsl(var(--background))" }} strokeWidth={4} className="fill-foreground text-[11px]">{l.records}</text>
              </g>
            )
          })}
          {g.squares.map((s, i) => {
            const pts = s.people.map((k) => pos.get(k)).filter(Boolean) as { x: number; y: number }[]
            if (pts.length < 2) return null
            const cx = pts.reduce((t, p) => t + p.x, 0) / pts.length + ((i % 3) - 1) * 14
            const cy = pts.reduce((t, p) => t + p.y, 0) / pts.length + 18 + (i % 2) * 12
            return (
              <g key={`s:${s.people.join(",")}`}>
                <rect x={cx - 11} y={cy - 11} width={22} height={22} rx={3} className="fill-amber-200 stroke-amber-700" />
                <text x={cx} y={cy + 4} textAnchor="middle" className="fill-amber-900 text-[11px] font-semibold">{s.documents.length}</text>
                <title>{`${s.documents.length} document${s.documents.length === 1 ? "" : "s"} naming ${s.people.map((k) => label.get(k)).join(", ")}`}</title>
              </g>
            )
          })}
          {g.nodes.map((n) => {
            const p = pos.get(n.key)!
            const on = first === n.key
            return (
              <g key={n.key} role="button" tabIndex={0} aria-pressed={on} aria-label={`${n.label}: show who it reaches`}
                onClick={() => setPicked(n.key)} onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && setPicked(n.key)} className="cursor-pointer">
                <circle cx={p.x} cy={p.y} r={on ? 26 : 22} className={on ? "fill-brand-500 stroke-brand-700" : "fill-card stroke-foreground/50"} strokeWidth={2} />
                <text x={p.x} y={p.y + 40} textAnchor="middle" paintOrder="stroke" style={{ stroke: "hsl(var(--background))" }} strokeWidth={4}
                  className="fill-foreground text-[12px] font-medium">{n.label}</text>
                {!n.phones && <text x={p.x} y={p.y + 54} textAnchor="middle" className="fill-muted-foreground text-[10px]">no phone</text>}
              </g>
            )
          })}
        </svg>
        <Documents data={data} />
      </div>
      {panel && <GoBetween caseId={caseId} data={data} panel={panel} />}
    </div>
  )
}

function GoBetween({ caseId, data, panel }: { caseId: string; data: Overlaps; panel: GoBetweenPanel }) {
  const zero = panel.people.filter((p) => !p.contacts)
  const person = data.people.find((p) => p.key === panel.key)
  return (
    <aside className="border-t p-4 text-sm lg:w-[24rem] lg:shrink-0 lg:border-l lg:border-t-0" aria-label={`${panel.label}: who it reaches`} data-testid="go-between-panel">
      <p className="text-[10px] font-semibold uppercase tracking-[.18em] text-muted-foreground">Go-between</p>
      <h3 className="text-base font-semibold">{panel.label}</h3>
      <dl className="mt-3 grid grid-cols-2 gap-2">
        <div><dt className="text-2xl font-semibold">{panel.reaches.length}</dt><dd className="text-xs">people it reaches{panel.reaches.length ? `: ${panel.reaches.join(", ")}` : ""}</dd></div>
        <div><dt className="text-2xl font-semibold">{panel.records.toLocaleString("en-US")}</dt><dd className="text-xs">records with them</dd></div>
      </dl>
      <table className="mt-3 w-full text-xs">
        <thead><tr className="text-left text-muted-foreground"><th className="font-medium">Person</th><th className="font-medium">Contacts</th><th className="font-medium">Days beside</th></tr></thead>
        <tbody>
          {panel.people.map((p) => (
            <tr key={p.key}><td>{p.label}</td><td>{p.contacts.toLocaleString("en-US")}</td><td>{p.place_days} of {panel.position_days}</td></tr>
          ))}
        </tbody>
      </table>
      <p className="mt-1 text-xs text-muted-foreground">
        Days beside: days its phone and theirs were together by Loupe's rule, of the {panel.position_days} days its phone has a position. Places read from photos are not counted.
      </p>
      {zero.length > 0 && <p className="mt-2 text-xs">No contact at all with {zero.map((p) => p.label).join(", ")}.</p>}
      {panel.pattern ? (
        <div className="mt-3">
          <p className="font-medium">The same order on {panel.pattern.times} of its {panel.pattern.of} stretches of activity</p>
          <ol className="mt-1 flex flex-col gap-1 text-xs">
            {panel.pattern.steps.map((s) => (
              <li key={s.ref}>
                <span className="font-medium">{s.local}</span> to {s.with ?? "an unknown number"}: “{s.body}”
                {s.reply && <> · {s.reply.local} reply: “{s.reply.body}”</>}
              </li>
            ))}
          </ol>
          <p className="mt-1 text-xs text-muted-foreground">Times in {panel.pattern.zone}. On {panel.pattern.days.join(", ")}.</p>
        </div>
      ) : <p className="mt-3 text-xs text-muted-foreground">Its messages follow no repeated order.</p>}
      {person && (
        <Button className="mt-3" variant="primary" onClick={() => openCorroborate({
          caseId, screen: "the people graph", label: panel.label, members: [memberOf(person)], people: [person.key],
        })}>Corroborate who holds it</Button>
      )}
    </aside>
  )
}

function Documents({ data }: { data: Overlaps }) {
  const label = new Map(data.people.map((p) => [p.key, p.label]))
  const g = data.graph
  return (
    <section className="mt-3 max-w-3xl" aria-label="Documents naming two or more of them">
      <h3 className="text-sm font-semibold">
        Documents naming two or more of them · {g.documents.naming_two_phone_owners} of {g.documents.read} name two or more phone owners
      </h3>
      <ul className="mt-1 flex flex-col gap-1 text-xs">
        {g.squares.flatMap((s) => s.documents.map((d) => (
          <li key={`${s.people.join(",")}:${d.file_id}`}>
            <span className="font-medium">{d.file}</span> · {d.people.map((p) =>
              `${label.get(p.key) ?? p.key} (${p.by === "model" ? `read by a model${p.pages.length ? `, page ${p.pages.join(", ")}` : ""}` : "full name in the text"})`).join(", ")}
          </li>
        )))}
      </ul>
      <p className="mt-1 text-xs text-muted-foreground">Names are read from each document by a model and shown with their page; nothing is confirmed until a person checks it. <LearnMore term="Go-between" /></p>
    </section>
  )
}
