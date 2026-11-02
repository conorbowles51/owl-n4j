import { useEffect, useMemo, useRef, useState } from "react"
import { useParams, useSearchParams } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { PageHeader } from "@/components/ui/page-header"
import { patternAPI, type Subject, type SubjectList, type TogetherResponse } from "../api"
import { Lanes } from "./Lanes"
import { errorWords, laneRowsOf } from "../lanes-lib"
import { StatementCheckPanel } from "./StatementCheckPanel"
import { KeepResult } from "./CollectBar"

/**
 * The Patterns screen (04 section 8.6): Day view, Pattern grid, Places over time, Together and Statement check, with
 * one subject picker that the views share. The subject and the view are kept in the address, so switching view keeps
 * the subject (POL-1).
 */
export const VIEWS = [
  { id: "day", label: "Day view" },
  { id: "grid", label: "Pattern grid" },
  { id: "places", label: "Places over time" },
  { id: "together", label: "Together" },
  { id: "check", label: "Check a statement" },
] as const
type ViewId = (typeof VIEWS)[number]["id"]

function nextDay(d: string) {
  const x = new Date(`${d}T00:00:00Z`); x.setUTCDate(x.getUTCDate() + 1); return x.toISOString()
}

function subjectKey(s: Subject) {
  return s.kind === "extraction" ? `e:${s.extraction_id}` : `d:${s.dossier_id}`
}

function parseSubject(raw: string | null): Subject | null {
  if (!raw) return null
  const [k, id] = raw.split(":")
  if (k === "e" && id) return { kind: "extraction", extraction_id: id }
  if (k === "d" && id) return { kind: "dossier", dossier_id: id }
  return null
}

function lastDay(list: SubjectList | undefined, s: Subject | null): string {
  const phone = list?.extractions.find((e) => s?.kind === "extraction" && e.extraction_id === s.extraction_id)
  const last = phone?.last || list?.extractions.map((e) => e.last).filter(Boolean).sort().pop()
  return (last || new Date().toISOString()).slice(0, 10)
}

export function PatternsPage() {
  const { id: caseId = "" } = useParams()
  const [params, setParams] = useSearchParams()
  const subjects = useQuery({ queryKey: ["pattern-subjects", caseId], queryFn: () => patternAPI.subjects(caseId) })
  // The subject and view live in state first and are mirrored to the address, so a view chosen straight after a
  // subject can never write the address from a copy that predates the subject (POL-1).
  const [picked, setPicked] = useState(() => ({ view: params.get("view"), subject: params.get("subject") }))
  const view = (VIEWS.find((v) => v.id === picked.view)?.id || "day") as ViewId
  const chosen = parseSubject(picked.subject)
  const subject: Subject | null = chosen || (subjects.data?.extractions[0]
    ? { kind: "extraction", extraction_id: subjects.data.extractions[0].extraction_id } : null)
  const set = (k: "view" | "subject", v: string) => {
    const next = { ...picked, [k]: v }
    setPicked(next)
    const p = new URLSearchParams(window.location.search)
    if (next.view) p.set("view", next.view)
    if (next.subject) p.set("subject", next.subject)
    setParams(p, { replace: true })
  }
  return (
    <div className="flex h-full flex-col gap-3 overflow-auto p-4">
      <PageHeader title="Phone patterns" description="Day view, pattern grid, places, together and statement checks for one phone or person." />
      <div className="flex flex-wrap items-center gap-2">
        <label className="text-sm" htmlFor="pattern-subject">Phone or person</label>
        <select id="pattern-subject" className="rounded border bg-background px-2 py-1 text-sm"
          value={subject ? subjectKey(subject) : ""} onChange={(e) => set("subject", e.target.value)}>
          {subjects.data?.extractions.map((e) => <option key={e.extraction_id} value={`e:${e.extraction_id}`}>{e.label}</option>)}
          {subjects.data?.dossiers.map((d) => <option key={d.dossier_id} value={`d:${d.dossier_id}`}>{d.name} (person)</option>)}
        </select>
        {subjects.data && (
          <span className="text-xs text-muted-foreground">
            {subjects.data.total_extractions.toLocaleString()} phones, {subjects.data.total_dossiers.toLocaleString()} people linked to phones
          </span>
        )}
      </div>
      <nav aria-label="Pattern views" className="flex flex-wrap gap-1">
        {VIEWS.map((v) => (
          <Button key={v.id} size="sm" variant={view === v.id ? "primary" : "outline"} aria-pressed={view === v.id}
            onClick={() => set("view", v.id)}>{v.label}</Button>
        ))}
      </nav>
      {subjects.isError && <p role="alert" className="text-sm text-destructive">{errorWords(subjects.error)}</p>}
      {subjects.data && !subject && <p className="text-sm">This case has no phones to show yet.</p>}
      {subject && view === "day" && <DayView caseId={caseId} subject={subject} initial={lastDay(subjects.data, subject)} />}
      {subject && view === "grid" && <GridView caseId={caseId} subject={subject} last={lastDay(subjects.data, subject)} />}
      {subject && view === "places" && <PlacesView caseId={caseId} subject={subject} last={lastDay(subjects.data, subject)} />}
      {subject && view === "together" && subjects.data && <TogetherView caseId={caseId} subject={subject} list={subjects.data} />}
      {subject && view === "check" && <StatementCheckPanel caseId={caseId} subject={subject} />}
    </div>
  )
}

function DayView({ caseId, subject, initial }: { caseId: string; subject: Subject; initial: string }) {
  const [date, setDate] = useState(initial)
  const q = useQuery({ queryKey: ["pattern-day", caseId, subjectKey(subject), date], queryFn: () => patternAPI.day(caseId, subject, date) })
  return (
    <section aria-label="Day view" className="flex flex-col gap-2">
      <label className="flex items-center gap-2 text-sm">Day <input type="date" value={date} onChange={(e) => setDate(e.target.value)} className="rounded border bg-background px-2 py-1" /></label>
      {q.isLoading && <p className="text-sm text-muted-foreground">Loading the day…</p>}
      {q.isError && <p role="alert" className="text-sm text-destructive">{errorWords(q.error)}</p>}
      {q.data && <Lanes start={q.data.start} end={q.data.end} zone={q.data.zone} rows={laneRowsOf(caseId, q.data)}
        header={<KeepResult caseId={caseId} origin="Added from Phone patterns, Day view"
          request={{ kind: "day", subject: JSON.stringify(subject), date, zone: q.data.zone }} />} />}
    </section>
  )
}

const STATE_CLASS: Record<string, string> = {
  interaction: "bg-emerald-600", data_no_interaction: "bg-sky-200 dark:bg-sky-900", no_data: "bg-muted",
  powered_off: "bg-zinc-400", powered_off_inferred: "bg-zinc-300", after_extraction: "bg-amber-200",
}
const STATE_WORDS: Record<string, string> = {
  interaction: "Use seen", data_no_interaction: "Phone recording, no use seen", no_data: "No data",
  powered_off: "Switched off", powered_off_inferred: "Appears switched off", after_extraction: "After extraction",
}

function GridView({ caseId, subject, last }: { caseId: string; subject: Subject; last: string }) {
  const start = useMemo(() => { const d = new Date(`${last}T00:00:00Z`); d.setUTCDate(d.getUTCDate() - 27); return d.toISOString().slice(0, 10) }, [last])
  const q = useQuery({ queryKey: ["pattern-grid", caseId, subjectKey(subject), start, last], queryFn: () => patternAPI.grid(caseId, subject, start, last) })
  const quiet = q.data?.quiet_hours as { start: number | null; end: number | null; message?: string } | null | undefined
  return (
    <section aria-label="Pattern grid" className="flex flex-col gap-2 text-sm">
      {q.isLoading && <p className="text-muted-foreground">Loading the grid…</p>}
      {q.isError && <p role="alert" className="text-destructive">{errorWords(q.error)}</p>}
      {q.data && (
        <>
          <p>{quiet && quiet.start !== null ? `Usual quiet hours: ${quiet.start}:00 to ${quiet.end}:00 (${q.data.zone}).` : (quiet?.message || "No regular quiet period found")}</p>
          <KeepResult caseId={caseId} origin="Added from Phone patterns, Pattern grid"
            request={{ kind: "grid", subject: JSON.stringify(subject), start: `${start}T00:00:00Z`, end: nextDay(last), zone: q.data.zone,
              parameters: { min_strength: "moderate", classes: ["interaction"], include_physical: false } }} />
          <p className="text-xs text-muted-foreground">{q.data.days.length.toLocaleString()} days, {start} to {last}. Use counted: the user's own, strength at least moderate.</p>
          <table className="border-collapse text-xs" aria-label="Hours by day">
            <thead><tr><th className="pr-2 text-left">Date</th>{Array.from({ length: 24 }, (_, h) => <th key={h} className="w-5 font-normal">{h}</th>)}</tr></thead>
            <tbody>
              {q.data.days.map((d) => (
                <tr key={d.date}><td className="pr-2">{d.date}</td>
                  {d.hours.map((h, i) => <td key={i} title={`${STATE_WORDS[h.state] || h.state}${h.counts?.strong ? ` · ${h.counts.strong} strong` : ""}`}
                    className={`h-4 w-5 border border-background ${STATE_CLASS[h.state] || "bg-muted"}`} />)}
                </tr>
              ))}
            </tbody>
          </table>
          <p className="flex flex-wrap gap-3 text-xs">{Object.entries(STATE_WORDS).map(([k, w]) => <span key={k}><span className={`mr-1 inline-block h-3 w-3 ${STATE_CLASS[k]}`} />{w}</span>)}</p>
          <h3 className="font-medium">Nights that break it ({(q.data.breaks || []).length.toLocaleString()})</h3>
          <ul>{(q.data.breaks || []).map((b) => <li key={b.date}>{b.date}</li>)}</ul>
          <h3 className="font-medium">Not observed ({(q.data.not_observed || []).length.toLocaleString()})</h3>
        </>
      )}
    </section>
  )
}

export function PlacesView({ caseId, subject, last }: { caseId: string; subject: Subject; last: string }) {
  const end = `${last}T23:59:59Z`
  const startD = new Date(`${last}T00:00:00Z`); startD.setUTCDate(startD.getUTCDate() - 6)
  const q = useQuery({ queryKey: ["pattern-places", caseId, subjectKey(subject), last], queryFn: () => patternAPI.places(caseId, subject, startD.toISOString(), end) })
  return (
    <section aria-label="Places over time" className="flex flex-col gap-2 text-sm">
      {q.isError && <p role="alert" className="text-destructive">{errorWords(q.error)}</p>}
      {q.data && (
        <>
          <p>Showing {q.data.returned.toLocaleString()} of {q.data.total.toLocaleString()} positioned records, {startD.toISOString().slice(0, 10)} to {last}.
            {q.data.towers_not_placed.length > 0 ? ` ${q.data.towers_not_placed.length.toLocaleString()} cell tower sightings cannot be placed: ${q.data.towers_not_placed[0].words}` : ""}</p>
          <KeepResult caseId={caseId} origin="Added from Phone patterns, Places over time"
            request={{ kind: "places", subject: JSON.stringify(subject), start: startD.toISOString(), end: nextDay(last), zone: "UTC" }} />
          {q.data.next_cursor !== null && <span> The list shows the first {q.data.returned.toLocaleString()}; the rest are on later pages.</span>}
          <table className="text-xs"><thead><tr><th className="text-left">Time</th><th className="text-left">Source</th><th className="text-left">Radius</th></tr></thead>
            <tbody>{q.data.observations.map((o) => (
              <tr key={o.id}><td>{o.start_utc}</td><td>{o.source_kind}</td><td>{o.radius_m ? `${Math.round(o.radius_m)} m` : "Accuracy not recorded"}</td></tr>))}</tbody>
          </table>
        </>
      )}
    </section>
  )
}

function TogetherView({ caseId, subject, list }: { caseId: string; subject: Subject; list: SubjectList }) {
  const others = list.extractions.filter((e) => !(subject.kind === "extraction" && e.extraction_id === subject.extraction_id))
  const [other, setOther] = useState(others[0]?.extraction_id || "")
  const [res, setRes] = useState<TogetherResponse | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [err, setErr] = useState<string | null>(null)
  // Opening Together starts the comparison with the first other phone; progress shows while it runs (J-10b).
  const started = useRef("")
  useEffect(() => {
    const key = `${subjectKey(subject)}|${other}`
    if (!other || started.current === key) return
    started.current = key
    void run()
  })
  async function run() {
    setErr(null); setRes(null)
    const a = list.extractions.find((e) => subject.kind === "extraction" && e.extraction_id === subject.extraction_id)
    const b = list.extractions.find((e) => e.extraction_id === other)
    const last = [a?.last, b?.last].filter(Boolean).sort()[0] || new Date().toISOString()
    const end = new Date(last); const start = new Date(end.getTime() - 7 * 86400_000)
    setBusy("Comparing pairs of points…")
    try {
      let r = await patternAPI.together(caseId, subject, { kind: "extraction", extraction_id: other }, start.toISOString(), end.toISOString())
      const runId = r.run_id
      if (runId && r.status !== "done") {
        setBusy(`Comparing ${(r.estimated_pairs || 0).toLocaleString()} pairs of points…`)
        for (let i = 0; i < 120 && r.status !== "done"; i++) {
          await new Promise((ok) => setTimeout(ok, 1000))
          r = await patternAPI.togetherRun(caseId, runId)
        }
        if (r.status !== "done") throw new Error("Still comparing after two minutes. The run continues; open Together again to see it.")
      }
      setRes(r)
    } catch (e) { setErr(errorWords(e)) } finally { setBusy(null) }
  }
  const c = res?.counts || {}
  return (
    <section aria-label="Together" className="flex flex-col gap-2 text-sm">
      <div className="flex items-center gap-2">
        <label htmlFor="together-other">Compare with</label>
        <select id="together-other" className="rounded border bg-background px-2 py-1" value={other} onChange={(e) => setOther(e.target.value)}>
          {others.map((e) => <option key={e.extraction_id} value={e.extraction_id}>{e.label}</option>)}
        </select>
        <Button size="sm" onClick={run} disabled={!other || !!busy}>Compare the last week</Button>
      </div>
      {others.length === 0 && <p>Together needs a second phone in the case.</p>}
      {busy && <p aria-live="polite">{busy}</p>}
      {err && <p role="alert" className="text-destructive">{err}</p>}
      {res && (
        <>
          <p>{(res.total ?? c.pairs ?? 0).toLocaleString()} pairs compared: {(c.compatible || 0).toLocaleString()} compatible, {(c.separated || 0).toLocaleString()} separated, {(c.undetermined || 0).toLocaleString()} undetermined.
            A position with no accuracy uses an assumed radius of 1,000 m and is marked. A broad overlap is never called together.</p>
          <h3 className="font-medium">Episodes ({(res.episodes || []).length.toLocaleString()})</h3>
          <ul>{(res.episodes || []).map((e, i) => <li key={i}>{e.kind === "together" ? `compatible (${e.breadth})` : "separated"}: {e.start} to {e.end}, {e.items.toLocaleString()} pairs</li>)}</ul>
        </>
      )}
    </section>
  )
}
