import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { phoneLinkHref } from "@/features/phones/phone-links"
import { patternAPI, type LaneItem } from "../api"
import { Lanes, type LaneRow } from "./Lanes"
import { bandsFromHours } from "../lanes-lib"
import { errorWords } from "../lanes-lib"

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

export function WindowPanel({ caseId, at, caseEvents, zone = "device", onClose }: {
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
    rows = q.data.phones.map((p) => {
      const items: LaneItem[] = ["interaction", "device_state", "communications", "places", "others"].flatMap((k) => p.lanes[k] || [])
      const counted = (p.totals.device_state || 0) + (p.totals.passive || 0)
      return {
        id: p.extraction_id, label: p.label || "Phone", bands: bandsFromHours(p.availability[0]?.hours || []),
        total: (p.totals.interaction || 0) + (p.totals.communications || 0) + (p.totals.places || 0) + (p.totals.others || 0),
        note: `${counted.toLocaleString()} device events and samples counted`,
        marks: items.map((i) => ({ key: `${i.ref_kind}:${i.id}`, at: i.at, label: i.ref_kind === "comm_event" ? `${i.kind} ${i.direction}` : `${i.record_type} · ${i.field}`,
          tone: (i.strength as never) || "none", href: i.record_uid ? phoneLinkHref(caseId, { target_type: "phone_record", target_id: i.record_uid }) : null })),
      }
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
        {onClose && <Button size="sm" variant="ghost" onClick={onClose}>Close</Button>}
      </div>
      {q.isLoading && <p className="text-sm text-muted-foreground">Opening the window…</p>}
      {q.isError && <p role="alert" className="text-sm text-destructive">{errorWords(q.error)}</p>}
      {q.data && <Lanes start={q.data.start} end={q.data.end} zone={q.data.zone} rows={rows} span={span} onSpan={setSpan} />}
    </section>
  )
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
      </div>
      {open && <WindowPanel caseId={caseId} at={open} caseEvents={events} onClose={() => setOpen(null)} />}
    </div>
  )
}
