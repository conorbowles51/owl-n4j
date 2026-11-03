import { useQuery } from "@tanstack/react-query"
import { useEffect, useMemo, useState } from "react"
import { Button } from "@/components/ui/button"
import { Lanes, type LaneRow } from "@/features/pattern/components/Lanes"
import { StreamList } from "@/features/phones/components/StreamList"
import { useStream } from "@/features/phones/hooks/use-stream"
import { DEFAULT_LENS_KINDS, LENS_KINDS, LENS_SOURCE, lensBuckets, type LaneBy, type LensFilter, type LensKind } from "./lens-api"

const n = (x: number) => x.toLocaleString("en-US")
const KEY = (caseId: string) => `loupe.timeline.phones.${caseId}`
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

type Stored = { on: boolean; emptyAtFirstUse: boolean }

function readStored(caseId: string): Stored | null {
  try {
    const v = JSON.parse(localStorage.getItem(KEY(caseId)) ?? "null")
    return v && typeof v.on === "boolean" ? { on: v.on, emptyAtFirstUse: !!v.emptyAtFirstUse } : null
  } catch {
    return null
  }
}

function writeStored(caseId: string, v: Stored) {
  try {
    localStorage.setItem(KEY(caseId), JSON.stringify(v))
  } catch {
    /* storage refused: the choice lasts for this page only */
  }
}

/**
 * The Phones lens switch (03 section 9.5; 07 section 4.12): on at first use when the case has no other dated events,
 * off otherwise. That choice is stored for this case at first use and never recomputed from the case's contents;
 * when the case later gains other events the screen says so.
 */
export function usePhoneLens(caseId: string, hasOtherEvents: boolean, hasPhones: boolean) {
  const [state, setState] = useState<Stored | null>(() => (caseId ? readStored(caseId) : null))
  const first = !state && caseId && hasPhones ? { on: !hasOtherEvents, emptyAtFirstUse: !hasOtherEvents } : null
  const current = state ?? first
  useEffect(() => {
    if (!first) return
    writeStored(caseId, first) // stored once, at first use, never recomputed from the case's contents
    setState(first)
  }, [caseId, first?.on]) // eslint-disable-line react-hooks/exhaustive-deps
  const on = hasPhones && !!current?.on
  const note = on && current?.emptyAtFirstUse && hasOtherEvents ? "Phone entries are shown. This case now also has documents." : null
  const setOn = (v: boolean) => {
    const next = { on: v, emptyAtFirstUse: current?.emptyAtFirstUse ?? false }
    writeStored(caseId, next)
    setState(next)
  }
  return { on, setOn, note }
}

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

function addDays(iso: string, d: number) {
  return new Date(new Date(iso).getTime() + d * 86400000).toISOString()
}

/** Lanes mode (03 section 9.6): counts per lane per hour or day from the server, "No data" drawn apart from "No
 * matching entries", and a bucket's rows shown in the same phone list below. */
function LensLanes({ caseId, caseName, filter, snapshot, firstDay, lastDay, filterWords }: {
  caseId: string; caseName: string; filter: LensFilter; snapshot: string; firstDay: string; lastDay: string; filterWords: string
}) {
  const [span, setSpan] = useState<(typeof SPANS)[number]["id"]>("all")
  const [anchor, setAnchor] = useState(`${firstDay}T00:00:00Z`)
  const [picked, setPicked] = useState<{ start: string; end: string } | null>(null)
  const spanDays = SPANS.find((s) => s.id === span)!.days
  const allEnd = addDays(`${lastDay}T00:00:00Z`, 2)
  const start = span === "all" ? addDays(`${firstDay}T00:00:00Z`, -1) : anchor
  const end = span === "all" ? allEnd : addDays(anchor, spanDays)
  const bucket = new Date(end).getTime() - new Date(start).getTime() <= 2 * 86400000 ? "hour" : "day"
  const q = useQuery({
    queryKey: ["timeline-lens-buckets", filter, snapshot, start, end, bucket],
    queryFn: () => lensBuckets(filter, snapshot, start, end, bucket),
  })
  const step = bucket === "hour" ? 3600000 : 86400000
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
  const pickedFilter = useMemo<LensFilter | null>(
    () => (picked ? { ...filter, from_instant: picked.start, to_instant: new Date(new Date(picked.end).getTime() - 1).toISOString(), include_no_time: false } : null),
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
      {pickedFilter ? <LensList caseId={caseId} caseName={caseName} filter={pickedFilter} filterWords={`${filterWords}; one ${bucket} from the lanes`} /> : <p className="text-sm text-muted-foreground">Choose a mark in a lane to list its entries here.</p>}
    </div>
  )
}

function LensList({ caseId, caseName, filter, filterWords }: { caseId: string; caseName: string; filter: LensFilter; filterWords: string }) {
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
export function PhoneLens({ caseId, caseName, note }: { caseId: string; caseName: string; note?: string | null }) {
  const [kinds, setKinds] = useState<LensKind[]>(DEFAULT_LENS_KINDS)
  const [laneBy, setLaneBy] = useState<LaneBy>("phone")
  const [mode, setMode] = useState<"stream" | "lanes">("stream")
  const filter = useMemo<LensFilter>(() => ({ case_id: caseId, lens_kinds: kinds, lane_by: laneBy }), [caseId, kinds, laneBy])
  const stream = useStream(filter, { source: LENS_SOURCE })
  const idx = stream.index as (typeof stream.index & { total?: number; hidden?: { count: number; words: string | null } }) | null
  const hiddenShown = kinds.includes("device") || kinds.includes("sensor")
  const toggleKind = (k: LensKind) => setKinds((ks) => (ks.includes(k) ? ks.filter((x) => x !== k) : [...ks, k]))
  const kindWords = kinds.map((k) => KIND_LABELS[k]).join(", ")
  const days = stream.index?.items ?? []
  return (
    <section aria-label="Phone entries" className="flex min-h-0 flex-1 flex-col gap-2 p-3">
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <h2 className="font-semibold">Phone entries</h2>
        {idx && <span role="status">{n(idx.total ?? idx.counts.events ?? 0)} phone {(idx.total ?? 0) === 1 ? "entry" : "entries"}</span>}
        <div role="group" aria-label="View" className="flex gap-1">
          <Button size="sm" variant={mode === "stream" ? "primary" : "outline"} aria-pressed={mode === "stream"} onClick={() => setMode("stream")}>Stream</Button>
          <Button size="sm" variant={mode === "lanes" ? "primary" : "outline"} aria-pressed={mode === "lanes"} onClick={() => setMode("lanes")}>Lanes</Button>
        </div>
        <label className="flex items-center gap-1 text-xs">
          Lanes by
          <select value={laneBy} onChange={(e) => setLaneBy(e.target.value as LaneBy)} className="rounded border bg-background px-1 py-0.5">
            {LANE_BY.map((l) => <option key={l.id} value={l.id}>{l.label}</option>)}
          </select>
        </label>
      </div>
      {note && <p role="note" className="text-xs">{note}</p>}
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
        />
      ) : stream.index && days.length ? (
        <LensLanes caseId={caseId} caseName={caseName} filter={filter} snapshot={stream.index.snapshot} firstDay={days[0].day < days[days.length - 1].day ? days[0].day : days[days.length - 1].day}
          lastDay={days[0].day < days[days.length - 1].day ? days[days.length - 1].day : days[0].day} filterWords={`phone lens: ${kindWords}`} />
      ) : stream.index ? (
        <p className="text-sm">No dated phone entries match; the lanes have nothing to draw.</p>
      ) : null}
    </section>
  )
}
