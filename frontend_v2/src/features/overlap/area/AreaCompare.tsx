import { useQuery } from "@tanstack/react-query"
import { useMemo, useState } from "react"
import { Link } from "react-router-dom"
import { X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { overlapAPI, type AreaCompare as Result, type AreaResult } from "../api"
import { askCorroborate } from "../corroborate"
import { useAreaCompare } from "./store"

const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
const letter = (i: number) => String.fromCharCode(65 + i)
const n = (v: number) => v.toLocaleString("en-US")
const plural = (v: number, one: string, many = `${one}s`) => `${n(v)} ${v === 1 ? one : many}`

function localTime(iso: string, zone: string) {
  return new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: zone, hour12: false }).format(new Date(iso))
}

/**
 * Drawn areas compared over one window (lx-overlapviews-b A, design screen 3): who is in each area and in what order
 * on the nights asked about, everything inside by kind, night by night, against the other nights of the same weekday.
 * A photo's place is shown as "photo place, not a position" and never counts as being there.
 */
export function AreaCompare({ caseId, areas }: { caseId: string; areas: number[][][] }) {
  const close = useAreaCompare((s) => s.close)
  const [names, setNames] = useState<string[]>(() => areas.map((_, i) => `Area ${letter(i)}`))
  const [committed, setCommitted] = useState<string[]>(names)
  const [weekday, setWeekday] = useState(4)
  const [start, setStart] = useState("22:00")
  const [end, setEnd] = useState("12:00")
  const [nights, setNights] = useState<string[] | null>(null)
  const [docs, setDocs] = useState<Record<number, string[]> | null>(null)
  const body = useMemo(() => ({
    areas: areas.map((ring, i) => ({ label: committed[i] || `Area ${letter(i)}`, ring })), weekday, start, end, nights, documents: docs,
  }), [areas, committed, weekday, start, end, nights, docs])
  const q = useQuery({
    queryKey: ["area-compare", caseId, body],
    queryFn: () => overlapAPI.areaCompare(caseId, body),
    enabled: areas.length > 0 && /^\d\d:\d\d$/.test(start) && /^\d\d:\d\d$/.test(end),
    staleTime: 60_000,
  })
  const r = q.data
  return (
    <section
      aria-label="Compare areas"
      data-testid="area-compare"
      className="absolute inset-x-2 bottom-2 top-14 z-20 flex flex-col overflow-hidden rounded-lg border border-border bg-card/95 text-xs shadow-lg backdrop-blur md:left-auto md:right-3 md:w-[44rem]"
    >
      <header className="flex items-center gap-2 border-b border-border px-3 py-2">
        <h2 className="text-sm font-semibold">Compare the drawn areas</h2>
        <button type="button" aria-label="Close the comparison" className="ml-auto rounded p-1 hover:bg-muted" onClick={close}>
          <X className="size-4" />
        </button>
      </header>
      <div className="min-h-0 flex-1 space-y-3 overflow-auto p-3">
        <fieldset className="flex flex-wrap items-end gap-2">
          <legend className="mb-1 text-[11px] font-medium text-muted-foreground">Looking at</legend>
          {areas.map((_, i) => (
            <label key={i} className="flex flex-col gap-0.5">
              <span className="text-[10px] text-muted-foreground">Name of area {letter(i)}</span>
              <input
                className="h-7 w-44 rounded border border-border bg-background px-2"
                value={names[i] ?? ""}
                onChange={(e) => setNames((v) => Object.assign([...v], { [i]: e.target.value }))}
                onBlur={() => { setCommitted(names); setDocs(null) }}
                onKeyDown={(e) => { if (e.key === "Enter") { setCommitted(names); setDocs(null) } }}
              />
            </label>
          ))}
          <label className="flex flex-col gap-0.5">
            <span className="text-[10px] text-muted-foreground">From</span>
            <select className="h-7 rounded border border-border bg-background px-1" value={weekday} onChange={(e) => { setWeekday(Number(e.target.value)); setNights(null) }}>
              {DAYS.map((d, i) => <option key={d} value={i}>{d}s</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-0.5">
            <span className="text-[10px] text-muted-foreground">at</span>
            <input type="time" className="h-7 rounded border border-border bg-background px-1" value={start} onChange={(e) => setStart(e.target.value)} />
          </label>
          <label className="flex flex-col gap-0.5">
            <span className="text-[10px] text-muted-foreground">to</span>
            <input type="time" className="h-7 rounded border border-border bg-background px-1" value={end} onChange={(e) => setEnd(e.target.value)} />
          </label>
        </fieldset>
        {q.isLoading && <p role="status">Reading every {DAYS[weekday]} in the case…</p>}
        {q.isError && (
          <div role="alert" className="space-y-1">
            <p>The areas could not be compared: {q.error instanceof Error ? q.error.message : "the server did not answer"}.</p>
            <Button size="sm" variant="outline" onClick={() => void q.refetch()}>Try again</Button>
          </div>
        )}
        {r && <Body caseId={caseId} r={r} nights={nights} setNights={setNights} docs={docs} setDocs={setDocs} />}
      </div>
    </section>
  )
}

function Body({ caseId, r, nights, setNights, docs, setDocs }: {
  caseId: string; r: Result; nights: string[] | null; setNights: (v: string[] | null) => void
  docs: Record<number, string[]> | null; setDocs: (v: Record<number, string[]> | null) => void
}) {
  const asked = r.asked.nights
  const toggleNight = (d: string) => {
    const cur = nights ?? asked
    setNights(cur.includes(d) ? cur.filter((x) => x !== d) : [...cur, d].sort())
  }
  const chosenDocs = (i: number) => docs?.[i] ?? r.areas[i].documents.map((d) => d.id)
  const toggleDoc = (i: number, id: string) => {
    const all = Object.fromEntries(r.areas.map((a) => [a.index, chosenDocs(a.index)]))
    all[i] = all[i].includes(id) ? all[i].filter((x) => x !== id) : [...all[i], id]
    setDocs(all)
  }
  const period = asked.length ? { from: asked[0], to: asked[asked.length - 1] } : undefined
  return (
    <>
      <p className="flex flex-wrap gap-1" data-testid="area-compare-chips">
        {r.areas.map((a) => <span key={a.index} className="rounded-full border border-border px-2 py-0.5">{letter(a.index)} · {a.label}</span>)}
        <span className="rounded-full border border-border px-2 py-0.5">{r.window.words} ({r.zone})</span>
        <span className="rounded-full border border-border px-2 py-0.5">Asked about: {plural(asked.length, "night")}, {r.asked.basis}</span>
        <span className="rounded-full border border-border px-2 py-0.5">Compared with: {r.compared_with.words}</span>
      </p>

      <Strip r={r} toggleNight={toggleNight} />

      {r.areas.length > 1 && <WhoInBoth r={r} />}

      {r.areas.map((a) => <Inside key={a.index} a={a} r={r} chosen={chosenDocs(a.index)} onToggleDoc={(id) => toggleDoc(a.index, id)} />)}

      <div className="flex flex-wrap gap-2 border-t border-border pt-2">
        <Button
          size="sm"
          disabled={r.members.length === 0}
          onClick={() => askCorroborate({
            caseId, screen: "the map", members: r.members, period,
            label: `${r.areas.map((a) => a.label).join(" and ")}, ${r.window.words}, ${plural(asked.length, "night")}`,
          })}
        >
          Corroborate this
        </Button>
        {asked.length > 0 && (
          <Button size="sm" variant="outline" asChild>
            <Link to={`/cases/${caseId}/financial/around-event?dates=${asked.join(",")}`}>Money around these nights</Link>
          </Button>
        )}
        {nights && <Button size="sm" variant="ghost" onClick={() => setNights(null)}>Go back to the nights with something inside</Button>}
      </div>
    </>
  )
}

function Strip({ r, toggleNight }: { r: Result; toggleNight: (d: string) => void }) {
  const asked = r.strip.filter((s) => s.asked)
  const other = r.strip.filter((s) => !s.asked)
  return (
    <section aria-label="Night by night" className="space-y-1">
      <h3 className="text-[11px] font-semibold">Night by night</h3>
      <ol className="space-y-1">
        {asked.map((s) => (
          <li key={s.night} className="rounded border border-border p-1.5">
            <div className="flex items-center gap-2">
              <span className="font-medium">{s.label}</span>
              <button type="button" className="ml-auto text-[10px] text-muted-foreground underline" onClick={() => toggleNight(s.night)}>Leave this night out</button>
            </div>
            {r.areas.map((a) => {
              const items = s.areas.filter((x) => x.area === a.index)
              return (
                <p key={a.index} className="text-[11px]">
                  <span className="font-medium">{letter(a.index)}:</span>{" "}
                  {items.length === 0 ? "nothing" : items.map((x) => `${localTime(x.at, r.zone)} ${x.who}${x.what === "access_row" ? ` badge${x.door ? ` at ${x.door}` : ""}` : x.what === "photo_place" ? " (photo place, not a position)" : x.what === "not_position" ? " (place named, not a position)" : ""}`).join(" · ")}
                </p>
              )
            })}
          </li>
        ))}
      </ol>
      <p data-testid="area-compare-baseline">
        Other {plural(other.length, r.window.words.split(" ")[0].replace(/s$/, ""))}:{" "}
        {r.areas.map((a) => a.baseline.nights_with_any === 0
          ? `nobody in ${letter(a.index)} in these hours`
          : `${letter(a.index)} has ${plural(a.baseline.positions, "position")} and ${plural(a.baseline.access_rows, "access row")} on ${plural(a.baseline.nights_with_any, "night")}`).join("; ")}.
      </p>
      {other.some((s) => s.areas.length > 0) && (
        <details>
          <summary className="cursor-pointer text-[11px] text-muted-foreground">Add one of those nights</summary>
          <ul className="flex flex-wrap gap-1 pt-1">
            {other.filter((s) => s.areas.length > 0).map((s) => (
              <li key={s.night}><button type="button" className="rounded border border-border px-1.5" onClick={() => toggleNight(s.night)}>{s.label} ({plural(s.areas.length, "record")})</button></li>
            ))}
          </ul>
        </details>
      )}
    </section>
  )
}

function cellWords(a: AreaResult, phone: string, who: string, of: number): string {
  const row = a.phones.find((p) => p.phone === phone)
  const access = a.access.find((x) => x.who === who)
  const parts: string[] = []
  if (row) parts.push(row.times.map((t) => `${t.time} · ${t.nights.length} of ${of} nights${t.stay_min > 0 ? ` · ${t.stay_min} min` : ""}`).join("; "))
  if (access) parts.push(`${row ? "" : "phone not there; "}badge ${access.times.map((t) => `${t.door ? `at ${t.door} ` : ""}${t.time}`).join(" and ")}`)
  if (!row && !access && a.photo_only.some((p) => p.phone === phone)) parts.push("only as places of photos received, not positions")
  return parts.join("; ") || "never"
}

function WhoInBoth({ r }: { r: Result }) {
  const people = new Map<string, string>()
  for (const a of r.areas) {
    for (const p of a.phones) people.set(p.phone, p.who)
    for (const p of a.photo_only) people.set(p.phone, p.who)
  }
  const accessOnly = r.areas.flatMap((a) => a.access.map((x) => x.who)).filter((w) => ![...people.values()].includes(w))
  const of = r.asked.nights.length
  return (
    <section aria-label="Who is in both, and in what order" className="space-y-1">
      <h3 className="text-[11px] font-semibold">Who is in both, and in what order</h3>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-[11px]">
          <thead>
            <tr className="text-left text-muted-foreground">
              <th className="p-1 font-medium">Phone</th>
              {r.areas.map((a) => <th key={a.index} className="p-1 font-medium">In {letter(a.index)} ({a.label})</th>)}
            </tr>
          </thead>
          <tbody>
            {[...people.entries()].map(([phone, who]) => (
              <tr key={phone} className="border-t border-border align-top">
                <td className="p-1 font-medium">{who}</td>
                {r.areas.map((a) => <td key={a.index} className="p-1">{cellWords(a, phone, who, of)}</td>)}
              </tr>
            ))}
            {[...new Set(accessOnly)].map((who) => (
              <tr key={who} className="border-t border-border align-top">
                <td className="p-1 font-medium">{who}</td>
                {r.areas.map((a) => <td key={a.index} className="p-1">{cellWords(a, "", who, of)}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {r.order.length > 0 && (
        <ul className="list-disc pl-4" data-testid="area-compare-order">
          {r.order.map((o) => (
            <li key={`${o.phone}-${o.sequence.join("")}`}>{o.who}: {o.sequence.map(letter).join(" then ")} on {o.nights} of {o.of} nights.</li>
          ))}
        </ul>
      )}
    </section>
  )
}

function Inside({ a, r, chosen, onToggleDoc }: { a: AreaResult; r: Result; chosen: string[]; onToggleDoc: (id: string) => void }) {
  const doors = Object.keys(a.inside.doors)
  return (
    <section aria-label={`Everything inside ${letter(a.index)}`} className="space-y-1" data-testid={`area-inside-${a.index}`}>
      <h3 className="text-[11px] font-semibold">Everything inside {letter(a.index)} in this window</h3>
      <dl className="grid grid-cols-[1fr_auto] gap-x-3">
        <dt>Phone positions, {plural(a.inside.position_phones, "phone")}</dt><dd className="text-right font-medium">{n(a.inside.positions)}</dd>
        <dt>Access rows{doors.length ? `, ${doors.join(" and ")}` : ""}</dt><dd className="text-right font-medium">{n(a.inside.access_rows)}</dd>
        <dt>Places of photos, {plural(a.inside.photo_phones, "phone")} (photo place, not a position)</dt><dd className="text-right font-medium">{n(a.inside.photo_places)}</dd>
        {a.inside.not_positions > 0 && (<><dt>Places searched or named, not positions</dt><dd className="text-right font-medium">{n(a.inside.not_positions)}</dd></>)}
      </dl>
      {a.outside_window.map((o) => (
        <p key={o.phone} className="text-muted-foreground">
          Outside the window: {o.who}'s phone is in {letter(a.index)} on {plural(o.days, "day")}, mostly {o.usual_hour}, {o.from} to {o.to}.
        </p>
      ))}
      <details>
        <summary className="cursor-pointer text-[11px] text-muted-foreground">Access logs counted in {letter(a.index)} ({chosen.length})</summary>
        <ul className="space-y-0.5 pt-1">
          {r.documents_available.map((d) => {
            const why = a.suggested_documents.find((s) => s.id === d.id)?.why
            return (
              <li key={d.id}>
                <label className="flex items-start gap-1">
                  <input type="checkbox" checked={chosen.includes(d.id)} onChange={() => onToggleDoc(d.id)} />
                  <span>{d.name}{why ? <span className="block text-[10px] text-muted-foreground">{why}</span> : null}</span>
                </label>
              </li>
            )
          })}
        </ul>
      </details>
    </section>
  )
}

export default AreaCompare
