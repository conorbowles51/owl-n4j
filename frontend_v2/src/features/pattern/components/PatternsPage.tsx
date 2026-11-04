import { useMemo, useState } from "react"
import { useParams, useSearchParams } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { PageHeader } from "@/components/ui/page-header"
import { patternAPI, type Snapshot, type Subject, type SubjectList } from "../api"
import { Lanes } from "./Lanes"
import { errorWords, laneRowsOf, setApartWords, snapshotView, usualLast } from "../lanes-lib"
import { StatementCheckPanel } from "./StatementCheckPanel"
import { KeepResult } from "./CollectBar"
import { KeyDatesBar } from "./KeyDates"
import { TextPlaces } from "./TextPlaces"
import { PlacesView, TogetherView } from "./PlacesViews"

export { PlacesView }

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

function phonesOf(list: SubjectList | undefined, s: Subject | null) {
  if (!list || !s) return []
  if (s.kind === "extraction") return list.extractions.filter((e) => e.extraction_id === s.extraction_id)
  const ids = list.dossiers.find((d) => d.dossier_id === s.dossier_id)?.extraction_ids || []
  return list.extractions.filter((e) => ids.includes(e.extraction_id))
}

function lastDay(list: SubjectList | undefined, s: Subject | null): string {
  const mine = phonesOf(list, s)
  const days = (mine.length ? mine : list?.extractions || []).map(usualLast).filter((d): d is string => !!d).sort()
  return days.pop() || new Date().toISOString().slice(0, 10)
}

function snapshotSubject(s: Snapshot | undefined): Subject | null {
  const subj = s?.snapshot.subject
  return subj && (subj.kind === "extraction" || subj.kind === "dossier") ? subj : null
}

export function PatternsPage() {
  const { id: caseId = "" } = useParams()
  const [params, setParams] = useSearchParams()
  const subjects = useQuery({ queryKey: ["pattern-subjects", caseId], queryFn: () => patternAPI.subjects(caseId) })
  // Saved links (lx-collect phone-links.ts): ?check=<evaluation id> opens that statement check; ?analysis=<kind>&
  // snapshot=<id> opens that frozen result. The subject and view come from what was saved unless the address names them.
  const checkId = params.get("check")
  const snapshotId = params.get("snapshot")
  const savedCheck = useQuery({ queryKey: ["pattern-saved-check", caseId, checkId], queryFn: () => patternAPI.check(caseId, checkId!),
    enabled: !!caseId && !!checkId, retry: false })
  const savedSnap = useQuery({ queryKey: ["pattern-snapshot", caseId, snapshotId], queryFn: () => patternAPI.snapshot(caseId, snapshotId!),
    enabled: !!caseId && !!snapshotId, retry: false })
  const snapOpen = savedSnap.data ? snapshotView(savedSnap.data) : null
  // The subject and view live in state first and are mirrored to the address, so a view chosen straight after a
  // subject can never write the address from a copy that predates the subject (POL-1).
  const [picked, setPicked] = useState(() => ({ view: params.get("view"), subject: params.get("subject") }))
  const view = (VIEWS.find((v) => v.id === picked.view)?.id || (checkId ? "check" : snapOpen?.view) || "day") as ViewId
  const chosen = parseSubject(picked.subject) || (checkId ? savedCheck.data?.subject : null) || snapshotSubject(savedSnap.data)
  const opening = (!!checkId && savedCheck.isLoading) || (!!snapshotId && savedSnap.isLoading)
  const last = (s: Subject | null) => (snapOpen && s && snapshotSubject(savedSnap.data) && subjectKey(s) === subjectKey(snapshotSubject(savedSnap.data)!)
    ? snapOpen.last : lastDay(subjects.data, s))
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
      {phonesOf(subjects.data, subject).map((e) => setApartWords(e.label, e.usual_span)).filter(Boolean).map((w) => (
        <p key={w} className="text-xs text-muted-foreground">{w}</p>
      ))}
      <KeyDatesBar caseId={caseId} />
      <nav aria-label="Pattern views" className="flex flex-wrap gap-1">
        {VIEWS.map((v) => (
          <Button key={v.id} size="sm" variant={view === v.id ? "primary" : "outline"} aria-pressed={view === v.id}
            onClick={() => set("view", v.id)}>{v.label}</Button>
        ))}
      </nav>
      {subjects.isError && <p role="alert" className="text-sm text-destructive">{errorWords(subjects.error)}</p>}
      {opening && <p className="text-sm text-muted-foreground">Opening the saved {checkId ? "statement check" : "result"}…</p>}
      {checkId && savedCheck.isError && (
        <p role="alert" className="text-sm text-destructive">The saved statement check could not be opened: {errorWords(savedCheck.error)}</p>
      )}
      {snapshotId && savedSnap.isError && (
        <p role="alert" className="text-sm text-destructive">The saved result could not be opened: {errorWords(savedSnap.error)}</p>
      )}
      {savedSnap.data && <SavedResult snap={savedSnap.data} last={snapOpen!.last} />}
      {subjects.data && !subject && <p className="text-sm">This case has no phones to show yet.</p>}
      {!opening && subject && view === "day" && (
        // ?day=YYYY-MM-DD opens that day (a payment's day from the ledger, 07 XF-1); else the subject's last day
        <DayView key={`${subjectKey(subject)}|${params.get("day") ?? ""}`} caseId={caseId} subject={subject}
          initial={/^\d{4}-\d{2}-\d{2}$/.test(params.get("day") ?? "") ? params.get("day")! : last(subject)} />
      )}
      {!opening && subject && view === "grid" && <GridView caseId={caseId} subject={subject} last={last(subject)} />}
      {!opening && subject && view === "places" && <PlacesView caseId={caseId} subject={subject} last={last(subject)} />}
      {!opening && subject && view === "places" && <TextPlaces caseId={caseId} extractionIds={phonesOf(subjects.data, subject).map((e) => e.extraction_id)} />}
      {!opening && subject && view === "together" && subjects.data && <TogetherView caseId={caseId} subject={subject} list={subjects.data} />}
      {!opening && subject && view === "check" && <StatementCheckPanel caseId={caseId} subject={subject}
        saved={savedCheck.data && subjectKey(savedCheck.data.subject) === subjectKey(subject) ? savedCheck.data : undefined} />}
    </div>
  )
}

const SNAP_KIND_WORDS: Record<Snapshot["kind"], string> = {
  day: "Day view", window: "Window", grid: "Pattern grid", places: "Places over time",
}

function utcText(t: string) {
  return `${new Date(t).toISOString().replace("T", " ").slice(0, 16)} UTC`
}

/** A frozen result opened from a saved link: what was kept, exactly as it was, apart from the live view below it. */
export function SavedResult({ snap, last }: { snap: Snapshot; last: string }) {
  const counts = Object.entries(snap.snapshot.summary_counts || {})
  return (
    <section aria-label="Saved result" className="flex flex-col gap-1 rounded border p-3 text-sm">
      <p className="font-medium">Saved result: {snap.label}</p>
      <p className="text-xs text-muted-foreground">
        {SNAP_KIND_WORDS[snap.kind]}, {utcText(snap.snapshot.window.start)} to {utcText(snap.snapshot.window.end)} (times
        shown in {snap.snapshot.window.zone}). {snap.record_count.toLocaleString()} records kept
        {snap.created_by_name ? `, saved by ${snap.created_by_name}` : ""}{snap.created_at ? ` on ${utcText(snap.created_at)}` : ""}.
      </p>
      {counts.length > 0 && (
        <p className="text-xs">{counts.map(([k, n]) => `${k.replace(/_/g, " ")}: ${n.toLocaleString()}`).join("; ")}</p>
      )}
      {snap.stale_words && <p className="text-xs text-amber-700 dark:text-amber-400">{snap.stale_words}</p>}
      <p className="text-xs text-muted-foreground">The saved result does not change. Below is the same view as the phones read now, ending on {last}.</p>
    </section>
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
            request={{ kind: "grid", subject: JSON.stringify(subject), start_date: start, end_date: last, zone: q.data.zone,
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
