import { Suspense, lazy, useEffect, useMemo, useRef, useState } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { PLACE_LABEL } from "@/features/map/lib/place-label"
import { placeName, positionFeatures, routineAreas, togetherLines, trajectory, type PlacePoint } from "@/features/map/lib/places-geo"
import { patternAPI, type PlaceObservation, type RoutinePlaceRow, type Subject, type SubjectList, type TogetherResponse } from "../api"
import { errorWords, usualLast } from "../lanes-lib"
import { evidenceWords, towerMccWords } from "../together-words"
import { KeepResult } from "./CollectBar"

// The map code loads only when a map view opens (the Patterns route's other views and the layouts never pull it).
const LazyPlacesMap = lazy(() => import("@/features/map/components/PlacesMap").then((m) => ({ default: m.PlacesMap })))

function PlacesMap(props: React.ComponentProps<typeof LazyPlacesMap>) {
  return (
    <Suspense fallback={<p className="text-xs text-muted-foreground">Loading the map…</p>}>
      <LazyPlacesMap {...props} />
    </Suspense>
  )
}

function subjectKey(s: Subject) {
  return s.kind === "extraction" ? `e:${s.extraction_id}` : `d:${s.dossier_id}`
}

function addDays(day: string, n: number) {
  const d = new Date(`${day}T00:00:00Z`); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10)
}

const KIND_WORDS: Record<string, string> = {
  presence: "Presence", media: "Photo, not shown taken on this phone", searched: "Searched for", planned: "Planned",
  declared: "Declared (check-in)", transaction: "Payment place",
}

/** The window chooser shared by Places over time and Together: two dates, inclusive, in UTC. */
function WindowPicker({ start, end, onChange, idPrefix }: { start: string; end: string; idPrefix: string; onChange: (s: string, e: string) => void }) {
  return (
    <div className="flex flex-wrap items-center gap-2 text-sm">
      <label htmlFor={`${idPrefix}-from`}>From</label>
      <input id={`${idPrefix}-from`} type="date" value={start} max={end} onChange={(e) => e.target.value && onChange(e.target.value, end)}
        className="rounded border bg-background px-2 py-1" />
      <label htmlFor={`${idPrefix}-to`}>to</label>
      <input id={`${idPrefix}-to`} type="date" value={end} min={start} onChange={(e) => e.target.value && onChange(start, e.target.value)}
        className="rounded border bg-background px-2 py-1" />
      <span className="text-xs text-muted-foreground">(whole days, UTC)</span>
    </div>
  )
}

/**
 * Places over time (04 section 8.3): the phone's positions in a chosen window on the map with their radii, the
 * trajectory with moves over 2 hours apart left as gaps, the routine places (named by a person through the decision
 * log, else numbered), and the days that break the routine in words.
 */
export function PlacesView({ caseId, subject, last }: { caseId: string; subject: Subject; last: string }) {
  const [win, setWin] = useState({ start: addDays(last, -6), end: last })
  const startIso = `${win.start}T00:00:00Z`
  const endIso = `${addDays(win.end, 1)}T00:00:00Z`
  const [pages, setPages] = useState(1)
  const q = useQuery({
    queryKey: ["pattern-places", caseId, subjectKey(subject), win.start, win.end, pages],
    queryFn: async () => {
      const first = await patternAPI.places(caseId, subject, startIso, endIso, 0)
      const obs = [...first.observations]
      let next = first.next_cursor
      for (let p = 1; p < pages && next !== null; p++) {
        const more = await patternAPI.places(caseId, subject, startIso, endIso, next)
        obs.push(...more.observations); next = more.next_cursor
      }
      return { ...first, observations: obs, returned: obs.length, next_cursor: next }
    },
  })
  const drawn = useMemo(() => {
    const pts = (q.data?.observations ?? []).filter((o) => Number.isFinite(o.lat) && Number.isFinite(o.lon)) as (PlaceObservation & PlacePoint)[]
    const presence = pts.filter((o) => o.kind === "presence")
    return { pts, traj: trajectory(presence), pos: positionFeatures(pts) }
  }, [q.data])
  const routine = useQuery({ queryKey: ["pattern-routine", caseId, subjectKey(subject)], queryFn: () => patternAPI.routine(caseId, subject) })
  const deviations = useQuery({ queryKey: ["pattern-deviations", caseId, subjectKey(subject)], queryFn: () => patternAPI.deviations(caseId, subject) })
  const routinePlaces = (routine.data?.places ?? []).filter((p) => p.routine)
  return (
    <section aria-label="Places over time" className="flex flex-col gap-2 text-sm">
      <WindowPicker idPrefix="places" start={win.start} end={win.end} onChange={(s, e) => { setWin({ start: s, end: e }); setPages(1) }} />
      {q.isLoading && <p className="text-muted-foreground">Loading the positions…</p>}
      {q.isError && <p role="alert" className="text-destructive">{errorWords(q.error)}</p>}
      {q.data && (
        <>
          <p>Showing {q.data.returned.toLocaleString()} of {q.data.total.toLocaleString()} positioned records, {win.start} to {win.end}.
            {q.data.towers_not_placed.length > 0 ? ` ${q.data.towers_not_placed.length.toLocaleString()} cell tower sightings cannot be placed: ${q.data.towers_not_placed[0].words}` : ""}
            {towerMccWords(q.data.towers_not_placed, q.data.mcc_inferred_words) ? ` ${towerMccWords(q.data.towers_not_placed, q.data.mcc_inferred_words)}` : ""}</p>
          {q.data.next_cursor !== null && (
            <p>The map and list show the first {q.data.returned.toLocaleString()}; the rest are on later pages.{" "}
              <Button size="sm" variant="outline" onClick={() => setPages((n) => n + 1)}>Load the next {q.data.page_size.toLocaleString()}</Button></p>
          )}
          <PlacesMap layers={{ dots: drawn.pos.dots, areas: drawn.pos.areas, lines: drawn.traj.lines,
            places: routineAreas(routinePlaces.map((p) => ({ ...p }))) }} />
          <p className="text-xs text-muted-foreground">
            Circles are each position's radius as used in comparisons; a faint dot has no accuracy recorded. Lines join
            presence positions in time order: {drawn.traj.segments.toLocaleString()} moves drawn,{" "}
            {drawn.traj.gaps.toLocaleString()} {drawn.traj.gaps === 1 ? "gap" : "gaps"} of over 2 hours left undrawn (whereabouts unknown).
          </p>
          <KeepResult caseId={caseId} origin="Added from Phone patterns, Places over time"
            request={{ kind: "places", subject: JSON.stringify(subject), start: startIso, end: endIso, zone: "UTC" }} />
          <details>
            <summary className="cursor-pointer">The positions ({q.data.returned.toLocaleString()} listed)</summary>
            <table className="text-xs"><thead><tr><th className="text-left">Time</th><th className="text-left">Kind</th><th className="text-left">Source</th><th className="text-left">Radius</th></tr></thead>
              <tbody>{q.data.observations.map((o) => (
                <tr key={o.id}><td>{o.start_utc}</td><td>{KIND_WORDS[o.kind] || o.kind}</td><td>{o.source_kind}{o.attribution_flags?.includes("mcc_inferred") ? " (country code from the SIM card)" : ""}</td><td>{o.radius_m ? `${Math.round(o.radius_m)} m` : "Accuracy not recorded"}</td></tr>))}</tbody>
            </table>
          </details>
        </>
      )}
      <RoutinePanel caseId={caseId} subject={subject} places={routine.data?.places ?? []} loading={routine.isLoading}
        error={routine.isError ? errorWords(routine.error) : null}
        stays={routine.data?.stays_total ?? 0} days={routine.data?.presence_days ?? 0} />
      <section aria-label="Days that break the routine" className="flex flex-col gap-1">
        <h3 className="font-medium">Days that break the routine ({(deviations.data?.flagged.length ?? 0).toLocaleString()})</h3>
        {deviations.isError && <p role="alert" className="text-destructive">{errorWords(deviations.error)}</p>}
        {deviations.data && (
          <>
            <p className="text-xs text-muted-foreground">{deviations.data.days_scored.toLocaleString()} days had enough positions to score
              (at least 3 hours with stays). A flagged day is unusual for this phone's positions, not evidence of where the person was or why.</p>
            <ul>{deviations.data.flagged.map((f) => (
              <li key={f.date}><span className="font-medium">{f.date}</span>: {f.expectation} On this day{" "}
                {f.hours.length.toLocaleString()} {f.hours.length === 1 ? "hour was" : "hours were"} somewhere else.</li>))}</ul>
          </>
        )}
      </section>
      <p className="text-xs font-medium">{PLACE_LABEL}.</p>
    </section>
  )
}

function RoutinePanel({ caseId, subject, places, loading, error, stays, days }: {
  caseId: string; subject: Subject; places: RoutinePlaceRow[]; loading: boolean; error: string | null; stays: number; days: number
}) {
  const routine = places.filter((p) => p.routine)
  return (
    <section aria-label="Routine places" className="flex flex-col gap-1">
      <h3 className="font-medium">Routine places ({routine.length.toLocaleString()} of {places.length.toLocaleString()} places)</h3>
      {loading && <p className="text-muted-foreground">Finding stays and places…</p>}
      {error && <p role="alert" className="text-destructive">{error}</p>}
      {!loading && !error && (
        <p className="text-xs text-muted-foreground">From all of the phone's positions: {stays.toLocaleString()} stays of 10 minutes or more
          on {days.toLocaleString()} days with positions. A place is routine with stays on at least 4 days. Places are unnamed until a person names them.</p>
      )}
      <ul className="flex flex-col gap-1">{places.map((p) => <PlaceRow key={p.cluster_id} caseId={caseId} subject={subject} place={p} />)}</ul>
    </section>
  )
}

function PlaceRow({ caseId, subject, place }: { caseId: string; subject: Subject; place: RoutinePlaceRow }) {
  const qc = useQueryClient()
  const [open, setOpen] = useState(false)
  const [label, setLabel] = useState(place.label ?? "")
  const [reason, setReason] = useState("")
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const save = async () => {
    setBusy(true); setErr(null)
    try {
      await patternAPI.namePlace(caseId, subject, place.cluster_id, label.trim(), reason.trim())
      setOpen(false); setReason("")
      await qc.invalidateQueries({ queryKey: ["pattern-routine", caseId] })
      await qc.invalidateQueries({ queryKey: ["pattern-deviations", caseId] })
    } catch (e) {
      setErr((e as { status?: number })?.status === 403 ? "You can view this case but not change it." : errorWords(e))
    } finally { setBusy(false) }
  }
  return (
    <li className="rounded border p-2">
      <span className="font-medium">{placeName(place)}</span>{place.routine ? " (routine)" : ""}: {place.stay_count.toLocaleString()} stays on{" "}
      {place.day_count.toLocaleString()} days, within {Math.round(place.radius_m).toLocaleString()} m.
      {place.label && place.label_by && <span className="text-xs text-muted-foreground"> Named by {place.label_by}.</span>}{" "}
      {!open && <button type="button" className="underline" onClick={() => setOpen(true)}>{place.label ? "Rename" : "Name this place"}</button>}
      {open && (
        <form className="mt-1 flex flex-wrap items-end gap-2" onSubmit={(e) => { e.preventDefault(); void save() }}>
          <label className="flex flex-col text-xs">Name<input aria-label="Place name" className="rounded border bg-background px-2 py-1" value={label}
            onChange={(e) => setLabel(e.target.value)} maxLength={200} /></label>
          <label className="flex flex-col text-xs">Why<input aria-label="Why this name" className="rounded border bg-background px-2 py-1" value={reason}
            onChange={(e) => setReason(e.target.value)} /></label>
          <Button size="sm" type="submit" disabled={busy || !reason.trim() || label.trim() === (place.label ?? "")}>{label.trim() ? "Save the name" : "Clear the name"}</Button>
          <Button size="sm" variant="outline" type="button" onClick={() => setOpen(false)}>Cancel</Button>
          <span className="text-xs text-muted-foreground">Recorded in the case decision log under your name.</span>
          {err && <span role="alert" className="text-xs text-destructive">{err}</span>}
        </form>
      )}
    </li>
  )
}

function subjectOf(raw: string): Subject {
  const [k, id] = raw.split(":")
  return k === "d" ? { kind: "dossier", dossier_id: id } : { kind: "extraction", extraction_id: id }
}

function lastOf(list: SubjectList, s: Subject): string | null {
  const ids = s.kind === "extraction" ? [s.extraction_id] : list.dossiers.find((d) => d.dossier_id === s.dossier_id)?.extraction_ids || []
  const days = list.extractions.filter((e) => ids.includes(e.extraction_id)).map(usualLast).filter((d): d is string => !!d).sort()
  return days.pop() ?? null
}

/**
 * Together and apart (04 section 8.4) for the screen's subject and a second phone or person, over a chosen window,
 * with every compared pair drawn on the map by verdict. A broad overlap is never called together.
 */
export function TogetherView({ caseId, subject, list }: { caseId: string; subject: Subject; list: SubjectList }) {
  const me = subjectKey(subject)
  const options = [
    ...list.extractions.map((e) => ({ key: `e:${e.extraction_id}`, label: e.label })),
    ...list.dossiers.map((d) => ({ key: `d:${d.dossier_id}`, label: `${d.name} (person)` })),
  ].filter((o) => o.key !== me)
  const [other, setOther] = useState(options[0]?.key || "")
  const defaultWindow = () => {
    const days = [lastOf(list, subject), other ? lastOf(list, subjectOf(other)) : null].filter((d): d is string => !!d).sort()
    const end = days[0] ?? new Date().toISOString().slice(0, 10)
    return { start: addDays(end, -6), end }
  }
  const [win, setWin] = useState(defaultWindow)
  const [res, setRes] = useState<TogetherResponse | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const started = useRef("")
  useEffect(() => {
    const key = `${me}|${other}`
    if (!other || started.current === key) return
    started.current = key
    void run()
  })
  async function run() {
    setErr(null); setRes(null)
    setBusy("Comparing pairs of points…")
    try {
      let r = await patternAPI.together(caseId, subject, subjectOf(other), `${win.start}T00:00:00Z`, `${addDays(win.end, 1)}T00:00:00Z`)
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
  async function more() {
    if (!res?.id || res.next_cursor == null) return
    const page = await patternAPI.togetherRun(caseId, String(res.id), res.next_cursor)
    setRes({ ...res, items: [...(res.items ?? []), ...(page.items ?? [])], next_cursor: page.next_cursor, returned: (res.items?.length ?? 0) + (page.items?.length ?? 0) })
  }
  const c = res?.counts || {}
  const pairs = useMemo(() => togetherLines(res?.items ?? []), [res])
  return (
    <section aria-label="Together" className="flex flex-col gap-2 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <label htmlFor="together-other">Compare with</label>
        <select id="together-other" className="rounded border bg-background px-2 py-1" value={other} onChange={(e) => setOther(e.target.value)}>
          {options.map((o) => <option key={o.key} value={o.key}>{o.label}</option>)}
        </select>
      </div>
      <WindowPicker idPrefix="together" start={win.start} end={win.end} onChange={(s, e) => setWin({ start: s, end: e })} />
      <div><Button size="sm" onClick={run} disabled={!other || !!busy}>Compare {win.start} to {win.end}</Button></div>
      {options.length === 0 && <p>Together needs a second phone or person in the case.</p>}
      {busy && <p aria-live="polite">{busy}</p>}
      {err && <p role="alert" className="text-destructive">{err}</p>}
      {res && (
        <>
          <p>{(res.total ?? c.pairs ?? 0).toLocaleString()} pairs compared: {(c.compatible || 0).toLocaleString()} compatible, {(c.separated || 0).toLocaleString()} separated, {(c.undetermined || 0).toLocaleString()} undetermined.
            A position with no accuracy uses an assumed radius of 1,000 m and is marked. A broad overlap is never called together.</p>
          {evidenceWords(c).length > 0 && <ul aria-label="Kinds of evidence">{evidenceWords(c).map((w) => <li key={w}>{w}</li>)}</ul>}
          <PlacesMap layers={{ pairs: pairs.lines }} />
          <p className="text-xs text-muted-foreground">
            The map draws {pairs.lines.features.length.toLocaleString()} of {(res.total ?? 0).toLocaleString()} pairs: green compatible, red separated, amber undetermined
            {pairs.undrawn ? `; ${pairs.undrawn.toLocaleString()} listed pairs have no position held now (a phone was read again since)` : ""}.
            {res.next_cursor != null && <> <Button size="sm" variant="outline" onClick={() => void more()}>Load the next pairs</Button></>}
          </p>
          <h3 className="font-medium">Episodes ({(res.episodes || []).length.toLocaleString()})</h3>
          <ul>{(res.episodes || []).map((e, i) => <li key={i}>{e.kind === "together" ? `compatible (${e.breadth})` : "separated"}: {e.start} to {e.end}, {e.items.toLocaleString()} pairs</li>)}</ul>
          <p className="text-xs font-medium">{PLACE_LABEL}.</p>
        </>
      )}
    </section>
  )
}
