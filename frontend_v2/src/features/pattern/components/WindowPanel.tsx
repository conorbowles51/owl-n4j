import { useState } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { phoneLinkHref } from "@/features/phones/phone-links"
import { patternAPI, type LaneItem } from "../api"
import { Lanes, type LaneRow } from "./Lanes"
import { bandsFromHours } from "../lanes-lib"
import { errorWords, keyDateWords } from "../lanes-lib"
import { KeepResult } from "./CollectBar"

/**
 * The window around a moment (07 J-5; 04 section 8.6): one lane per phone with its availability, a Case events lane
 * and a payments lane, drawn by the shared Lanes component. Used by the Case Timeline and the incident window.
 */
export interface CaseEventLike {
  key: string
  name: string
  type: string
  at: string | null
}

export function WindowPanel({ caseId, at, caseEvents, zone = "case", onClose }: {
  caseId: string
  at: string
  caseEvents: CaseEventLike[]
  zone?: string
  onClose?: () => void
}) {
  const [span, setSpan] = useState("1h")
  const q = useQuery({ queryKey: ["pattern-window", caseId, at, span, zone], queryFn: () => patternAPI.window(caseId, at, span, zone) })
  let rows: LaneRow[] = []
  if (q.data) {
    const a = new Date(q.data.start).getTime()
    const b = new Date(q.data.end).getTime()
    const mark = (i: LaneItem) => ({ key: `${i.ref_kind}:${i.id}`, at: i.at, label: i.ref_kind === "comm_event" ? `${i.kind} ${i.direction}` : `${i.record_type} · ${i.field}`,
      tone: (i.strength as never) || "none", href: i.record_uid ? phoneLinkHref(caseId, { target_type: "phone_record", target_id: i.record_uid }) : null })
    rows = q.data.phones.flatMap((p): LaneRow[] => {
      const items: LaneItem[] = ["interaction", "communications", "places", "others"].flatMap((k) => p.lanes[k] || [])
      const device: LaneItem[] = ["device_state", "passive"].flatMap((k) => p.lanes[k] || [])
      const counted = (p.totals.device_state || 0) + (p.totals.passive || 0)
      return [{
        id: p.extraction_id, label: p.label || "Phone", bands: bandsFromHours(p.availability[0]?.hours || []),
        total: (p.totals.interaction || 0) + (p.totals.communications || 0) + (p.totals.places || 0) + (p.totals.others || 0),
        marks: items.map(mark),
      }, {
        id: `${p.extraction_id}-device`, label: `${p.label || "Phone"}: device events and sensor readings`, total: counted, collapsible: true,
        note: p.passive_as_hourly_counts ? p.limit_words || undefined : undefined, marks: device.map(mark),
      }]
    })
    const inWindow = caseEvents.filter((e) => e.at && new Date(e.at).getTime() >= a && new Date(e.at).getTime() < b)
    rows.push({ id: "case", label: "Case events", total: inWindow.length,
      marks: inWindow.map((e) => ({ key: e.key, at: e.at as string, label: `${e.type} · ${e.name}`, tone: "case" })) })
    rows.push({ id: "money", label: "Payments", total: q.data.money_total, marks: [],
      allDay: q.data.money.map((m) => ({ key: m.transaction_id, label: `${(m.amount_minor / 100).toFixed(2)} ${m.currency}${m.counterparty ? ` · ${m.counterparty}` : ""}`, detail: m.date_words })) })
  }
  return (
    <section aria-label="Window around this moment" className="rounded border bg-card p-3">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-sm font-medium">Around {new Date(at).toISOString().replace("T", " ").slice(0, 16)} UTC</h3>
        <span className="flex items-center gap-1">
          <SaveMoment caseId={caseId} at={at} zone={q.data?.zone || "UTC"} />
          {onClose && <Button size="sm" variant="ghost" onClick={onClose}>Close</Button>}
        </span>
      </div>
      {q.isLoading && <p className="text-sm text-muted-foreground">Opening the window…</p>}
      {q.isError && <p role="alert" className="text-sm text-destructive">{errorWords(q.error)}</p>}
      {q.data?.zone_note && <p className="text-xs text-muted-foreground">{q.data.zone_note}</p>}
      {q.data && <Lanes start={q.data.start} end={q.data.end} zone={q.data.zone} zoneBasis={q.data.zone_basis} rows={rows} span={span} onSpan={setSpan}
        header={<KeepResult caseId={caseId} origin="Added from the window around a moment"
          request={{ kind: "window", start: q.data.start, end: q.data.end, zone: q.data.zone }} />} />}
    </section>
  )
}

/** Save the window's moment as a key date (07 J-5 "Save the anchor as a case key date"). */
function SaveMoment({ caseId, at, zone }: { caseId: string; at: string; zone: string }) {
  const qc = useQueryClient()
  const [said, setSaid] = useState<string | null>(null)
  async function save() {
    const label = window.prompt("Name this key date")
    if (!label || !label.trim()) return
    try {
      await patternAPI.createKeyDate(caseId, { kind: "date", label: label.trim(), instant: at, zone })
      setSaid("Saved as a key date in Workspace.")
      await qc.invalidateQueries({ queryKey: ["pattern-key-dates", caseId] })
    } catch (e) { setSaid(errorWords(e)) }
  }
  return said ? <span className="text-xs" aria-live="polite">{said}</span>
    : <Button size="sm" variant="ghost" onClick={save}>Save this moment as a key date</Button>
}

/**
 * The Timeline's entry to the window: "Open the window around this" opens the lanes around the chosen event, or the
 * latest timed event, or, when the case's timeline has no timed event, the latest moment on the case's phones.
 */
export function TimelineWindowBar({ caseId, events, selectedKey }: {
  caseId: string
  events: CaseEventLike[]
  selectedKey?: string | null
}) {
  const [open, setOpen] = useState<string | null>(null)
  const subjects = useQuery({ queryKey: ["pattern-subjects", caseId], queryFn: () => patternAPI.subjects(caseId) })
  const keys = useQuery({ queryKey: ["pattern-key-dates", caseId], queryFn: () => patternAPI.keyDates(caseId, "date") })
  const timed = events.filter((e) => e.at)
  const chosen = timed.find((e) => e.key === selectedKey) || timed[timed.length - 1]
  const phoneLast = subjects.data?.extractions.map((e) => e.last).filter(Boolean).sort().pop() || null
  const anchor = chosen?.at || phoneLast
  if (!anchor || (subjects.data && subjects.data.total_extractions === 0)) return null
  return (
    <div className="flex flex-col gap-2 border-b px-4 py-2">
      <div className="flex items-center gap-2 text-sm">
        <Button size="sm" variant="outline" onClick={() => setOpen(anchor)}>Open the window around this</Button>
        <span className="text-xs text-muted-foreground">{chosen ? `Around "${chosen.name}"` : "Around the latest moment on the case's phones"}</span>
        {(keys.data?.items || []).length > 0 && <span className="text-xs">Or a key date:</span>}
        {(keys.data?.items || []).map((k) => k.instant_utc && (
          <Button key={k.entry_id} size="sm" variant="ghost" onClick={() => setOpen(k.instant_utc)}>{keyDateWords(k)}</Button>
        ))}
      </div>
      {open && <WindowPanel caseId={caseId} at={open} caseEvents={events} onClose={() => setOpen(null)} />}
    </div>
  )
}
