import { useQuery } from "@tanstack/react-query"
import { useEffect, useMemo, useState } from "react"
import { Link } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { ExportDialog } from "@/features/conversations/ExportDialog"
import { Lanes, type LaneRow } from "@/features/pattern/components/Lanes"
import { StreamList } from "@/features/phones/components/StreamList"
import { useStream } from "@/features/phones/hooks/use-stream"
import { instantWords } from "@/features/phones/lib/time-words"
import { recordPath } from "@/lib/record-links"
import { DEFAULT_LENS_KINDS, LENS_KINDS, LENS_SOURCE, lensBuckets, lensIndex, lensLocateRecord, lensMoney, lensMoneyItems, type LaneBy, type LensMoney, type LensFilter, type LensKind } from "./lens-api"
import { SignificantNote } from "@/features/phones/ui/SignificantNote"
import { DEFAULT_VIEW, viewToFilter } from "@/features/phones/lib/filter-url"
import { phoneSettingsQuery } from "@/features/phones/phone-queries"
import { ScopeBar } from "@/features/phones/ui/ScopeBar"
import { ScopeCrossings } from "@/features/phones/ui/ScopeCrossings"
import { scopeToSearch } from "@/features/phones/ui/scope"
import { useUrlScope } from "@/features/phones/ui/use-phone-scope"

const n = (x: number) => x.toLocaleString("en-US")
const KIND_LABELS: Record<LensKind, string> = {
  messages: "Messages", calls: "Calls", emails: "Emails", media: "Photos and media", locations: "Locations",
  web: "Web and searches", apps: "Apps", accounts: "Accounts", device: "Device activity", sensor: "Sensor readings", other: "Other records",
}
const LANE_BY: { id: LaneBy; label: string }[] = [
  { id: "phone", label: "Phone" },
  { id: "person", label: "Person" },
  { id: "activity_class", label: "Activity class" },
  { id: "kind", label: "Kind of record" },
]

export function PhoneLensToggle({ on, onChange, phones }: { on: boolean; onChange: (v: boolean) => void; phones: number }) {
  return (
    <Button size="sm" variant={on ? "primary" : "outline"} aria-pressed={on} onClick={() => onChange(!on)}>
      Phones ({n(phones)})
    </Button>
  )
}

const SPANS = [
  { id: "day", label: "Day", days: 1 },
  { id: "week", label: "Week", days: 7 },
  { id: "month", label: "Month", days: 31 },
  { id: "all", label: "All", days: 0 },
] as const

/** The server's limit for daily lanes (timeline_lens.DAY_BUCKET_MAX_DAYS). */
const DAY_BUCKET_MAX_DAYS = 3700

function addDays(iso: string, d: number) {
  return new Date(new Date(iso).getTime() + d * 86400000).toISOString()
}

/** Lanes mode (03 section 9.6): counts per lane per hour, day or week from the server, "No data" drawn apart from "No
 * matching entries", and a bucket's rows shown in the same phone list below. */
function LensLanes({ caseId, caseName, filter, snapshot, firstDay, lastDay, filterWords }: {
  caseId: string; caseName: string; filter: LensFilter; snapshot: string; firstDay: string; lastDay: string; filterWords: string
}) {
  const [span, setSpan] = useState<(typeof SPANS)[number]["id"]>("all")
  const [anchor, setAnchor] = useState(`${firstDay}T00:00:00Z`)
  const [picked, setPicked] = useState<{ start: string; end: string; money?: boolean } | null>(null)
  const spanDays = SPANS.find((s) => s.id === span)!.days
  const allEnd = addDays(`${lastDay}T00:00:00Z`, 2)
  const start = span === "all" ? addDays(`${firstDay}T00:00:00Z`, -1) : anchor
  const end = span === "all" ? allEnd : addDays(anchor, spanDays)
  const spanMs = new Date(end).getTime() - new Date(start).getTime()
  // daily lanes stop at ten years on the server, so a longer "All" span (a calendar entry years ahead) is drawn in weeks
  const bucket = spanMs <= 2 * 86400000 ? "hour" : spanMs <= DAY_BUCKET_MAX_DAYS * 86400000 ? "day" : "week"
  const q = useQuery({
    queryKey: ["timeline-lens-buckets", filter, snapshot, start, end, bucket],
    queryFn: () => lensBuckets(filter, snapshot, start, end, bucket),
  })
  // its own request: the lanes above never wait for it, and a reading is in no lens total
  const money = useQuery({ queryKey: ["timeline-lens-money", filter, start, end, bucket], queryFn: () => lensMoney(filter, start, end, bucket) })
  const step = bucket === "hour" ? 3600000 : bucket === "day" ? 86400000 : 7 * 86400000
  const rows: LaneRow[] = (q.data?.lanes ?? []).map((l) => {
    const total = l.buckets.reduce((a, b) => a + b.count, 0)
    return {
      id: l.key,
      label: l.label,
      total,
      note: total === 0 ? (l.buckets.every((b) => b.no_data) ? q.data!.no_data_words : q.data!.empty_words) : undefined,
      bands: l.buckets.filter((b) => b.no_data).map((b) => ({ start: b.start, end: new Date(new Date(b.start).getTime() + step).toISOString(), state: "no_data", words: q.data!.no_data_words })),
      marks: l.buckets.filter((b) => b.count > 0).map((b) => ({
        key: `${l.key}-${b.start}`, at: b.start, label: `${n(b.count)} ${b.count === 1 ? "entry" : "entries"}`, tone: "moderate" as const,
        onClick: () => setPicked({ start: b.start, end: new Date(new Date(b.start).getTime() + step).toISOString() }),
      })),
    }
  })
  if (money.data && q.data) rows.push(moneyRow(money.data, setPicked))
  const pickedFilter = useMemo<LensFilter | null>(
    () => (picked && !picked.money ? { ...filter, from_instant: picked.start, to_instant: new Date(new Date(picked.end).getTime() - 1).toISOString(), include_no_time: false } : null),
    [filter, picked],
  )
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        {SPANS.map((s) => (
          <Button key={s.id} size="sm" variant={span === s.id ? "primary" : "outline"} onClick={() => setSpan(s.id)}>{s.label}</Button>
        ))}
        {span !== "all" && (
          <>
            <Button size="sm" variant="ghost" onClick={() => setAnchor(addDays(anchor, -spanDays))}>Earlier</Button>
            <Button size="sm" variant="ghost" onClick={() => setAnchor(addDays(anchor, spanDays))}>Later</Button>
          </>
        )}
      </div>
      {q.isError && <p role="alert" className="text-sm">The lanes could not be loaded. {q.error instanceof Error ? q.error.message : ""}</p>}
      {q.data && <Lanes start={start} end={end} zone={q.data.zone} rows={rows} />}
      {money.isError && <p role="alert" className="text-sm">The phone money readings could not be loaded; the lanes above are complete without them.</p>}
      {picked?.money ? <MoneyReadings caseId={caseId} filter={filter} start={picked.start} end={picked.end} /> : pickedFilter ? <LensList caseId={caseId} caseName={caseName} filter={pickedFilter} filterWords={`${filterWords}; one ${bucket} from the lanes`} /> : <p className="text-sm text-muted-foreground">Choose a mark in a lane to list its entries here.</p>}
    </div>
  )
}

/** The money lane: readings counted, never amounts added (05 4.4). A reading with no time is stated, not placed. */
function moneyRow(m: LensMoney, pick: (p: { start: string; end: string; money: boolean }) => void): LaneRow {
  const apart = [
    m.no_time ? `${n(m.no_time)} with no time ${m.no_time === 1 ? "is" : "are"} not drawn.` : "",
    m.rejected ? `${n(m.rejected)} rejected by a person ${m.rejected === 1 ? "is" : "are"} left out.` : "",
  ].filter(Boolean).join(" ")
  return {
    id: "phone-money",
    label: m.label,
    ...(m.run ? { total: m.readings } : {}),
    absent: m.absent_words ?? undefined,
    note: m.run ? `${m.readings ? "" : "No readings in this span. "}${m.words} ${apart}`.trim() : undefined,
    marks: m.buckets.map((b) => ({
      key: `phone-money-${b.start}`, at: b.start, label: `${n(b.count)} p4 ${b.count === 1 ? "reading" : "readings"} from the phone`, tone: "money" as const,
      onClick: () => pick({ start: b.start, end: b.end, money: true }),
    })),
  }
}

/** One mark's readings: the words as the phone gave them, labelled, each opening its phone record. */
function MoneyReadings({ caseId, filter, start, end }: { caseId: string; filter: LensFilter; start: string; end: string }) {
  const q = useQuery({ queryKey: ["timeline-lens-money-items", filter, start, end], queryFn: () => lensMoneyItems(filter, start, end) })
  if (q.isError) return <p role="alert" className="text-sm">These readings could not be loaded.</p>
  if (!q.data) return <p role="status" className="text-sm">Loading the readings.</p>
  const d = q.data
  return (
    <section aria-label="Phone money readings" className="flex flex-col gap-1 overflow-auto text-sm">
      <p className="text-xs text-muted-foreground">{d.words}</p>
      {d.total > d.items.length && <p role="note" className="text-xs">Showing the first {n(d.items.length)} of {n(d.total)} readings in this mark; choose a shorter span to see the rest.</p>}
      <ul className="flex flex-col gap-1">
        {d.items.map((r) => (
          <li key={r.result_id} className="flex flex-wrap items-baseline gap-2">
            <span className="rounded bg-muted px-1 text-xs">p4 · from the phone</span>
            <Link className="underline" to={recordPath(caseId, r.record_uid)}>{r.amount_text ?? "Amount not read"}{r.direction ? ` · ${r.direction}` : ""}{r.institution ? ` · ${r.institution}` : ""}</Link>
            <span className="text-xs text-muted-foreground">{[r.source, r.phone_label, r.instant ? instantWords(r.instant, "UTC") : null].filter(Boolean).join(" · ")}</span>
          </li>
        ))}
      </ul>
    </section>
  )
}

export function LensList({ caseId, caseName, filter, filterWords }: { caseId: string; caseName: string; filter: LensFilter; filterWords: string }) {
  const stream = useStream(filter, { source: LENS_SOURCE })
  if (stream.status === "error") return <p role="alert" className="text-sm">{stream.error}</p>
  return (
    <StreamList
      key={JSON.stringify(filter)}
      stream={stream}
      caseId={caseId}
      caseName={caseName}
      filterWords={filterWords}
      zoneName={stream.index?.zone.label ?? "UTC"}
      zone={stream.index?.zone.name ?? "UTC"}
      zoneBasis={stream.index?.zone.basis}
      noun={{ one: "phone entry", many: "phone entries" }}
      className="min-h-0 flex-1"
    />
  )
}

/**
 * The Case Timeline phone lens (03 section 9): phone activity with the phone's names, numbers and badges on every
 * line, the whole result under filters (no "Load more"), and one Lanes view to compare phones, people or kinds.
 * The stream and the lanes list rows through the one phone list, so copy gives the same text in both (T-4).
 */
const hiddenEntries = (shown: number, all: number) => `${n(Math.max(0, all - shown))} of ${n(all)} entries are hidden.`

export function PhoneLens({ caseId, caseName, note, focusRecord }: { caseId: string; caseName: string; note?: string | null; focusRecord?: string | null }) {
  const [kinds, setKinds] = useState<LensKind[]>(DEFAULT_LENS_KINDS)
  const [laneBy, setLaneBy] = useState<LaneBy>("phone")
  const [mode, setMode] = useState<"stream" | "lanes">("stream")
  const [significant, setSignificant] = useState(false)
  // the phone scope carried in the address (07 4.5), read by the lens's own stream filter; its kinds are the lens's own
  const carried = useUrlScope(caseId, { people: true, window: true })
  const settings = useQuery({ ...phoneSettingsQuery(caseId), enabled: !!caseId })
  const zoneName = settings.data?.effective?.name ?? "UTC"
  const scopeSignature = scopeToSearch(carried.scope)
  const scoped = useMemo<Partial<LensFilter>>(() => {
    const { people, mode, phones, window: span } = carried.scope
    const f = viewToFilter(caseId, { ...DEFAULT_VIEW, people: people.map((p) => p.key), mode, phones: phones.map((p) => p.id), from: span?.from ?? null, to: span?.to ?? null }, zoneName)
    return { phones: f.phones, participants: f.participants, participant_mode: f.participant_mode, group_scope: f.group_scope, from_instant: f.from_instant, to_instant: f.to_instant }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- the signature is the scope
  }, [scopeSignature, caseId, zoneName])
  const filter = useMemo<LensFilter>(() => ({ case_id: caseId, lens_kinds: kinds, lane_by: laneBy, ...scoped, ...(significant ? { significant_only: true } : {}) }), [caseId, kinds, laneBy, significant, scoped])
  const everything = useQuery({
    queryKey: ["phone-lens-all", caseId, kinds, laneBy, scoped],
    queryFn: () => lensIndex({ case_id: caseId, lens_kinds: kinds, lane_by: laneBy, ...scoped }),
    enabled: significant,
  })
  const stream = useStream(filter, { source: LENS_SOURCE })
  const idx = stream.index as (typeof stream.index & { total?: number; hidden?: { count: number; words: string | null } }) | null
  const hiddenShown = kinds.includes("device") || kinds.includes("sensor")
  const toggleKind = (k: LensKind) => setKinds((ks) => (ks.includes(k) ? ks.filter((x) => x !== k) : [...ks, k]))
  const kindWords = kinds.map((k) => KIND_LABELS[k]).join(", ")
  const days = stream.index?.items ?? []
  const [exportOpen, setExportOpen] = useState(false)
  // Show on Timeline from a record panel: find the record's entry once the index is in, then open the list on it
  const [jump, setJump] = useState<{ day: string | null; seq: number; offset?: number } | null>(null)
  const [focusNote, setFocusNote] = useState<string | null>(null)
  const snapshot = stream.index?.snapshot
  useEffect(() => {
    if (!focusRecord || !snapshot) return
    let live = true
    lensLocateRecord(filter, snapshot, focusRecord)
      .then((loc) => {
        if (!live) return
        setMode("stream")
        setJump({ day: loc.day, offset: loc.offset, seq: Date.now() })
        setFocusNote("Showing the record you opened.")
      })
      .catch((e) => live && setFocusNote(e instanceof Error && e.message ? e.message : "The record you opened has no entry in the phone lens with the kinds shown."))
    return () => {
      live = false
    }
  }, [focusRecord, snapshot]) // eslint-disable-line react-hooks/exhaustive-deps -- once per record and result
  return (
    <section aria-label="Phone entries" className="flex min-h-0 flex-1 flex-col gap-2 p-3">
      <ScopeBar scope={carried.scope} onChange={carried.apply} presets={carried.presets} recent={carried.recent} restored={carried.restored} notApplied={carried.notApplied}
        count={idx ? { shown: idx.total ?? idx.counts.events ?? 0, total: idx.total ?? idx.counts.events ?? 0, noun: "phone entries" } : null}>
        <ScopeCrossings caseId={caseId} scope={carried.scope} here="timeline" />
      </ScopeBar>
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <h2 className="font-semibold">Phone entries</h2>
        {idx && <span role="status">{n(idx.total ?? idx.counts.events ?? 0)} phone {(idx.total ?? 0) === 1 ? "entry" : "entries"}</span>}
        <div role="group" aria-label="View" className="flex gap-1">
          <Button size="sm" variant={mode === "stream" ? "primary" : "outline"} aria-pressed={mode === "stream"} onClick={() => setMode("stream")}>Stream</Button>
          <Button size="sm" variant={mode === "lanes" ? "primary" : "outline"} aria-pressed={mode === "lanes"} onClick={() => setMode("lanes")}>Lanes</Button>
        </div>
        {/* the all-channel timeline for counsel: exactly the entries the lens lists, under its day headers (03 12.2) */}
        <Button size="sm" variant="outline" disabled={!idx} onClick={() => setExportOpen(true)}>Export</Button>
        <label className="flex items-center gap-1 text-xs">
          Lanes by
          <select value={laneBy} onChange={(e) => setLaneBy(e.target.value as LaneBy)} className="rounded border bg-background px-1 py-0.5">
            {LANE_BY.map((l) => <option key={l.id} value={l.id}>{l.label}</option>)}
          </select>
        </label>
      </div>
      <SignificantNote
        caseId={caseId}
        on={significant}
        onChange={setSignificant}
        hiddenWords={significant && idx && everything.data ? hiddenEntries((idx.total ?? idx.counts.events ?? 0), everything.data.total ?? everything.data.counts.events ?? 0) : null}
      />
      {note && <p role="note" className="text-xs">{note}</p>}
      {focusNote && <p role="status" className="text-xs">{focusNote}</p>}
      {idx?.hidden && (idx.hidden.count > 0 || hiddenShown) && (
        <p className="flex items-center gap-2 text-xs text-muted-foreground">
          {hiddenShown ? "Device events and sensor readings are shown." : idx.hidden.words}
          <Button size="sm" variant="link" onClick={() => setKinds((ks) => (hiddenShown ? ks.filter((k) => k !== "device" && k !== "sensor") : [...ks, "device", "sensor"]))}>
            {hiddenShown ? "Hide" : "Show"}
          </Button>
        </p>
      )}
      <details className="text-xs">
        <summary className="cursor-pointer">Kinds of entry: {kindWords || "none"}</summary>
        <div className="mt-1 flex flex-wrap gap-3">
          {LENS_KINDS.map((k) => (
            <label key={k} className="flex items-center gap-1">
              <input type="checkbox" checked={kinds.includes(k)} onChange={() => toggleKind(k)} />
              {KIND_LABELS[k]}
            </label>
          ))}
        </div>
      </details>
      {stream.index?.limits.map((l, i) => <p key={i} role="note" className="text-xs">{l.message}</p>)}
      {stream.status === "error" && <p role="alert" className="text-sm">{stream.error}</p>}
      {mode === "stream" ? (
        <StreamList
          key={JSON.stringify(filter)}
          stream={stream}
          caseId={caseId}
          caseName={caseName}
          filterWords={`phone lens: ${kindWords}`}
          zoneName={stream.index?.zone.label ?? "UTC"}
          zone={stream.index?.zone.name ?? "UTC"}
          zoneBasis={stream.index?.zone.basis}
          noun={{ one: "phone entry", many: "phone entries" }}
          className="min-h-0 flex-1"
          jumpTo={jump}
        />
      ) : stream.index && days.length ? (
        <LensLanes caseId={caseId} caseName={caseName} filter={filter} snapshot={stream.index.snapshot} firstDay={days[0].day < days[days.length - 1].day ? days[0].day : days[days.length - 1].day}
          lastDay={days[0].day < days[days.length - 1].day ? days[days.length - 1].day : days[0].day} filterWords={`phone lens: ${kindWords}`} />
      ) : stream.index ? (
        <p className="text-sm">No dated phone entries match; the lanes have nothing to draw.</p>
      ) : null}
      {exportOpen && (
        <ExportDialog caseId={caseId} filter={filter} words={`the Case Timeline phone lens (${kindWords || "no kinds"})`}
          open={exportOpen} onOpenChange={setExportOpen} source="timeline_lens" />
      )}
    </section>
  )
}
