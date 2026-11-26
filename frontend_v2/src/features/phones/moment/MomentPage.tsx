import { useMutation, useQuery } from "@tanstack/react-query"
import { lazy, Suspense, useMemo } from "react"
import { Link, useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom"
import type { FeatureCollection, Point } from "geojson"
import { Button } from "@/components/ui/button"
import { openCorroborate } from "@/features/leads/open"
import { failureText, saveView } from "../api"
import { phoneMark } from "../lib/phone-palette"
import { NextSteps, PhoneTag } from "../person/parts"
import { clock, fmt, phoneFill, usePhoneIndex } from "../person/screen-lib"
import { momentHref, momentQuery, type Moment, type MomentRecord, type NextStep, type StripState } from "../person/person-api"

const PlacesMap = lazy(() => import("@/features/map/components/PlacesMap").then((m) => ({ default: m.PlacesMap })))

const HOUR = 3600e3
const DAY = 24 * HOUR
const MAX = 7 * DAY
const STRIP_CLASS: Record<StripState, string> = {
  together: "bg-emerald-700 dark:bg-emerald-600",
  maybe: "bg-emerald-700/40 dark:bg-emerald-600/40",
  apart: "bg-slate-500 dark:bg-slate-400",
  unknown: "bg-muted",
}
const KIND_WORDS: Record<MomentRecord["kind"], string> = { message: "Message", call: "Call", place: "Place", not_recording: "Not recording" }
const HATCH = { backgroundImage: "repeating-linear-gradient(135deg, hsl(var(--muted-foreground) / 0.35) 0 2px, transparent 2px 7px)" }

function long(iso: string) {
  return new Date(iso).toLocaleString("en-GB", { weekday: "long", day: "numeric", month: "long", year: "numeric", hour: "2-digit", minute: "2-digit", timeZone: "UTC" })
}

function span(ms: number) {
  if (ms % DAY === 0) return ms === DAY ? "day" : `${ms / DAY} days`
  if (ms % HOUR === 0) return ms === HOUR ? "hour" : `${ms / HOUR} hours`
  return `${Math.round(ms / 60e3)} minutes`
}

/** Phones redesign screen 4: a window around a moment with one lane per phone in scope. */
export function MomentPage() {
  const { id: caseId = "" } = useParams()
  const [params] = useSearchParams()
  const location = useLocation()
  const navigate = useNavigate()
  const from = params.get("from") ?? ""
  const to = params.get("to") ?? ""
  const phones = (params.get("phones") ?? "").split(",").filter(Boolean)
  const valid = !!from && !!to && !Number.isNaN(Date.parse(from)) && !Number.isNaN(Date.parse(to)) && Date.parse(to) > Date.parse(from)
  const q = useQuery({ ...momentQuery(caseId, from, to, phones), enabled: !!caseId && valid, retry: false })
  const indexOf = usePhoneIndex(caseId)
  const save = useMutation({
    mutationFn: (d: Moment) => saveView({ case_id: caseId, phones: d.phones.map((p) => p.extraction_id), from_instant: d.from, to_instant: d.to },
      `${location.pathname}${location.search}`, `Key moment: ${long(d.from)} to ${long(d.to)} (UTC) on ${d.phones.length} ${d.phones.length === 1 ? "phone" : "phones"}`),
  })

  if (!valid)
    return <p role="alert" className="p-6 text-sm">This window has no clear start and end. Open a moment from a record, the Timeline or a person's contact.</p>
  if (q.isLoading) return <p role="status" className="p-6 text-sm">Reading every phone around this moment</p>
  if (q.isError || !q.data) return <p role="alert" className="p-6 text-sm">{failureText(q.error, "This window could not be read. Reload the page, or choose a shorter window.")}</p>
  const d = q.data
  const a = Date.parse(d.from)
  const b = Date.parse(d.to)
  const len = b - a
  const pct = (iso: string) => `${Math.min(100, Math.max(0, ((Date.parse(iso) - a) / len) * 100)).toFixed(2)}%`
  const label = (id: string) => d.phones.find((p) => p.extraction_id === id)?.label ?? "A phone"
  const ids = d.phones.map((p) => p.extraction_id)
  const go = (f: number, t: number) => navigate(momentHref(caseId, new Date(f).toISOString(), new Date(t).toISOString(), phones))
  const dayStart = Date.UTC(new Date(a).getUTCFullYear(), new Date(a).getUTCMonth(), new Date(a).getUTCDate())
  const wider = len < DAY ? [dayStart, dayStart + DAY] : [a - Math.min(len, (MAX - len) / 2), b + Math.min(len, (MAX - len) / 2)]
  const ticks = Array.from({ length: 7 }, (_, i) => a + (len * i) / 6)

  const act = (s: NextStep): { to?: string; onClick?: () => void } => {
    if (s.code === "wider" && s.from && s.to) return { to: momentHref(caseId, s.from, s.to, phones) }
    if (s.code === "search_gap" && s.from && s.to) return { to: `/cases/${encodeURIComponent(caseId)}/phone-analyses/incident-window?${new URLSearchParams({ start: s.from, end: s.to })}` }
    if (s.code === "open_deleted" && s.record_uid) return { to: `/cases/${encodeURIComponent(caseId)}/records/${encodeURIComponent(s.record_uid)}` }
    // Corroborate's "together" question takes both phones and tests them at the case's other key times
    if (s.code === "corroborate" && s.phones) {
      const both = s.phones
      return { onClick: () => openCorroborate({ caseId, screen: "Around a moment", kind: "together", label: both.map(label).join(" and "), members: both.map((id) => ({ type: "phone", id })) }) }
    }
    if (s.code === "compare") return { onClick: () => document.getElementById("moment-records")?.scrollIntoView({ block: "start" }) }
    return {}
  }

  return (
    <div className="flex min-h-full flex-col">
      <header className="border-b px-4 sm:px-7 py-5">
        <nav aria-label="Breadcrumb" className="text-xs text-muted-foreground">
          <Link className="underline-offset-2 hover:underline" to={`/cases/${encodeURIComponent(caseId)}/phones`}>Phones</Link> / Around a moment
        </nav>
        <div className="mt-2 flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold">{long(d.from)} to {new Date(b).toUTCString().slice(0, 16) === new Date(a).toUTCString().slice(0, 16) ? clock(d.to) : long(d.to)}</h1>
            <p className="mt-1 text-[13px] text-muted-foreground">
              Everything {d.phones.length === 1 ? "the phone" : `all ${d.phones.length} phones`} recorded in this {span(len)}, side by side. Times in UTC.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="outline" onClick={() => go(a - len, a)}>Earlier</Button>
            <Button size="sm" variant="outline" onClick={() => go(wider[0], wider[1])} disabled={len >= MAX} disabledReason="A window is at most 7 days.">
              {len < DAY ? "Wider: the whole day" : "Wider"}
            </Button>
            <Button size="sm" variant="outline" onClick={() => go(b, b + len)}>Later</Button>
            <Button size="sm" variant="outline" onClick={() => save.mutate(d)} disabled={save.isPending || save.isSuccess}>
              {save.isSuccess ? "Saved as a key moment" : "Save as a key moment"}
            </Button>
          </div>
        </div>
        {save.isSuccess && <p role="status" className="mt-2 text-[13px]">Saved to the case's Workspace as a note; opening it brings back this window on these phones.</p>}
        {save.isError && <p role="alert" className="mt-2 text-[13px]">{failureText(save.error, "This moment could not be saved. You need edit access to the case.")}</p>}
      </header>

      <section aria-label="Lanes" className="overflow-x-auto px-4 sm:px-7 py-5">
        <div className="sm:min-w-[640px]">
          <div className="flex justify-between text-xs text-muted-foreground sm:ml-[180px]" aria-hidden>
            {ticks.map((t) => <span key={t}>{clock(new Date(t).toISOString())}</span>)}
          </div>
          {d.phones.map((p) => (
            <div key={p.extraction_id} className="mt-2 flex flex-col gap-1 sm:flex-row sm:items-center sm:gap-3">
              <div className="shrink-0 sm:w-[168px]">
                <div className="text-[13px] font-semibold"><PhoneTag index={indexOf(p.extraction_id)} label={p.label} /></div>
                <div className="text-xs text-muted-foreground">{p.owner ?? "Owner not known"}</div>
              </div>
              <div className="relative h-14 w-full rounded-lg sm:flex-1 border bg-card" role="img"
                aria-label={`${p.label}: ${fmt(p.counts.messages)} messages, ${fmt(p.counts.calls)} calls, ${fmt(p.counts.places)} places, ${fmt(p.counts.use)} uses of the phone${p.not_recording.length ? `; not recording ${p.not_recording.map((g) => `${clock(g.start)} to ${clock(g.end)}`).join(", ")}` : ""}`}>
                {p.not_recording.map((g) => (
                  <span key={g.start} className="absolute inset-y-0 rounded" style={{ left: pct(g.start), width: `calc(${pct(g.end)} - ${pct(g.start)})`, ...HATCH }} title={`Not recording ${clock(g.start)} to ${clock(g.end)}`} />
                ))}
                {p.marks.map((m, i) => <Mark key={`${m.kind}:${m.at}:${i}`} kind={m.kind} left={pct(m.at)} index={indexOf(p.extraction_id)} />)}
              </div>
            </div>
          ))}
          {d.pairs.map((pr) => (
            <div key={pr.phones.join(",")} className="mt-2 flex flex-col gap-1 sm:flex-row sm:items-center sm:gap-3">
              <div className="shrink-0 text-xs text-muted-foreground sm:w-[168px]">{label(pr.phones[0])} and {label(pr.phones[1])}</div>
              <div className="grid h-3 w-full gap-0.5 sm:flex-1" style={{ gridTemplateColumns: `repeat(${pr.strip.length}, 1fr)` }} role="img" aria-label={pr.words}>
                {pr.strip.map((s) => <span key={s.start} className={`block rounded-sm ${STRIP_CLASS[s.state]}`} title={`${clock(s.start)} to ${clock(s.end)}: ${d.strip_words[s.state]}`} />)}
              </div>
            </div>
          ))}
          <ul aria-label="Key" className="mt-3 sm:ml-[180px] flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
            <li className="flex items-center gap-1.5"><span className="size-2.5 rounded-full bg-foreground/70" />Message</li>
            <li className="flex items-center gap-1.5"><span className="h-1.5 w-5 rounded bg-foreground/70" />Call</li>
            <li className="flex items-center gap-1.5"><span className="size-2 rotate-45 border-2 border-foreground/70" />Place</li>
            <li className="flex items-center gap-1.5"><span className="h-3 w-0.5 bg-muted-foreground" />Phone in use (unlock, app opened)</li>
            <li className="flex items-center gap-1.5"><span className="h-3 w-5 rounded" style={HATCH} />Not recording: no data, not no activity</li>
            {(["together", "maybe", "apart"] as const).map((s) => <li key={s} className="flex items-center gap-1.5"><span className={`h-2.5 w-4 rounded-sm ${STRIP_CLASS[s]}`} />{d.strip_words[s]}</li>)}
          </ul>
        </div>
      </section>

      <div className="flex flex-wrap border-t">
        <section id="moment-records" aria-label="Records in this window" className="min-w-0 flex-[999_1_520px]">
          <p className="border-b px-4 sm:px-6 py-3 text-[13px]">{d.summary}</p>
          {d.records.length === 0 && <p className="px-4 sm:px-6 py-4 text-sm">No phone in scope holds a record in this window. Try Wider, or add phones to the scope.</p>}
          <ol>
            {d.records.map((r, i) => {
              const c = r.on.length === 1 ? indexOf(r.on[0]) : null
              const inner = (
                <>
                  {r.kind === "not_recording" ? <span aria-hidden className="w-3 shrink-0 self-stretch rounded" style={HATCH} /> : <span aria-hidden {...(c != null ? phoneFill(c, "w-[3px] shrink-0 self-stretch rounded") : { className: "w-[3px] shrink-0 self-stretch rounded bg-muted-foreground" })} />}
                  <span className="w-[66px] shrink-0 text-xs text-muted-foreground">{clock(r.at)}</span>
                  <span className="min-w-0 flex-1 text-[13px]">
                    <span className="font-semibold">{r.on.map(label).join(" and ")}</span>{" "}
                    <span className="text-muted-foreground">{r.kind === "message" ? r.app ?? "Message" : KIND_WORDS[r.kind]}</span>
                    {" · "}
                    {r.who ? `${r.who}: ` : ""}
                    <span className="break-words">{r.text}</span>
                    {r.deleted_on.length > 0 && <span className="text-muted-foreground"> (deleted on {r.deleted_on.map(label).join(" and ")})</span>}
                  </span>
                </>
              )
              return (
                <li key={`${r.kind}:${r.at}:${i}`}>
                  {r.record_uids[0] ? (
                    <Link to={`/cases/${encodeURIComponent(caseId)}/records/${encodeURIComponent(r.record_uids[0])}`} className="flex gap-3 border-b px-4 sm:px-6 py-2 hover:bg-accent/50">{inner}</Link>
                  ) : (
                    <div className="flex gap-3 border-b px-4 py-2 italic text-muted-foreground sm:px-6">{inner}</div>
                  )}
                </li>
              )
            })}
          </ol>
        </section>
        <aside aria-label="Where the phones were" className="flex flex-[1_1_360px] flex-col gap-3 border-l p-5">
          <h2 className="text-sm font-semibold">Where the phones were</h2>
          <WindowMap d={d} indexOf={indexOf} />
          <ul className="flex flex-col gap-1 text-[13px]">
            {d.pairs.map((p) => <li key={p.phones.join(",")}>{p.words}</li>)}
          </ul>
          <p className="text-xs text-muted-foreground">{d.together_rule}</p>
          <div className="flex flex-wrap gap-2">
            <Button asChild size="sm" variant="outline">
              <Link to={`/cases/${encodeURIComponent(caseId)}/map`}>Open on the full map</Link>
            </Button>
          </div>
          {ids.length === 0 && <p className="text-sm">No phone is in scope.</p>}
        </aside>
      </div>

      <div className="border-t px-4 sm:px-7 py-5">
        <NextSteps steps={d.next_steps} intro="Most useful first, from the gaps and overlaps in this window." act={act} />
      </div>
    </div>
  )
}

function Mark({ kind, left, index }: { kind: string; left: string; index: number }) {
  if (kind === "message") return <span aria-hidden {...phoneFill(index, "absolute top-[21px] -ml-[5px] size-2.5 rounded-full", { left })} />
  if (kind === "call") return <span aria-hidden {...phoneFill(index, "absolute top-[23px] h-1.5 w-[22px] rounded", { left })} />
  if (kind === "place") {
    const m = phoneMark(index)
    return <span aria-hidden className="absolute top-2 -ml-1 size-[7px] rotate-45 border-2 border-[var(--phone-light)] dark:border-[var(--phone-dark)]" style={{ left, ["--phone-light" as string]: m.light, ["--phone-dark" as string]: m.dark }} />
  }
  return <span aria-hidden className="absolute top-[38px] h-3 w-0.5 bg-muted-foreground" style={{ left }} />
}

function WindowMap({ d, indexOf }: { d: Moment; indexOf: (id: string) => number }) {
  const dots = useMemo<FeatureCollection<Point>>(() => ({
    type: "FeatureCollection",
    features: d.places.map((p) => ({ type: "Feature", geometry: { type: "Point", coordinates: [p.lon, p.lat] }, properties: { colour: phoneMark(indexOf(p.extraction_id)).light, accuracy: p.radius_m == null ? "not recorded" : "recorded" } })),
  }), [d.places, indexOf])
  if (!d.places.length) return <p className="text-[13px]">No phone in scope recorded a place in this window.</p>
  return (
    <Suspense fallback={<p role="status" className="text-sm">Loading the map</p>}>
      <PlacesMap layers={{ dots }} height={260} />
    </Suspense>
  )
}
