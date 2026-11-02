import { useState, type ReactNode } from "react"
import { Button } from "@/components/ui/button"
import { zoneWords } from "@/features/phones/lib/time-words"

/**
 * The one shared Lanes component (04 section 8.6; 07 J-5): the Case Timeline's window, the Day view and the incident
 * window all draw with it. One lane per phone (or per kind of item), a Case events lane and a money lane. Each lane
 * shows its availability bands, so "No data" is drawn apart from "Phone recording, no use seen", and every lane says
 * how many items it holds. Money sits on its day, never at a time of day.
 */
export interface LaneBand {
  start: string
  end: string
  state: string
  words: string
}

export interface LaneMark {
  key: string
  at: string
  end?: string | null
  label: string
  detail?: string
  tone?: "strong" | "moderate" | "weak" | "none" | "case" | "money"
  href?: string | null
}

export interface LaneRow {
  id: string
  label: string
  bands?: LaneBand[]
  marks: LaneMark[]
  total?: number
  note?: string
  allDay?: { key: string; label: string; detail?: string }[]
  /** Device events and sensor readings: hidden by default and counted (07 section 5), one click away. */
  collapsible?: boolean
}

export const SPANS = [
  { id: "1h", label: "±1 h" },
  { id: "6h", label: "±6 h" },
  { id: "24h", label: "±24 h" },
] as const

const BAND_CLASS: Record<string, string> = {
  no_data: "bg-muted/60",
  data_no_interaction: "bg-sky-100 dark:bg-sky-950",
  observed: "bg-sky-100 dark:bg-sky-950",
  interaction: "bg-emerald-100 dark:bg-emerald-950",
  powered_off: "bg-zinc-300 dark:bg-zinc-700",
  powered_off_inferred: "bg-zinc-200 dark:bg-zinc-800",
  after_extraction: "bg-amber-100 dark:bg-amber-950",
}
const TONE_CLASS: Record<string, string> = {
  strong: "bg-emerald-700", moderate: "bg-emerald-500", weak: "bg-emerald-300", none: "bg-zinc-400",
  case: "bg-violet-600", money: "bg-amber-600",
}

function pct(t: string, start: number, span: number) {
  return Math.min(100, Math.max(0, ((new Date(t).getTime() - start) / span) * 100))
}

export function Lanes({ start, end, zone, zoneBasis, rows, span, onSpan, header }: {
  start: string
  end: string
  zone: string
  /** Why this zone (03 section 4.6): case_setting, phones_device_zone, utc_default, device_zone or chosen. */
  zoneBasis?: string
  rows: LaneRow[]
  span?: string
  onSpan?: (span: string) => void
  header?: ReactNode
}) {
  const [showAll, setShowAll] = useState(false)
  const hiddenRows = rows.filter((r) => r.collapsible)
  const hiddenCount = hiddenRows.reduce((n, r) => n + (r.total ?? r.marks.length), 0)
  const shown = showAll ? rows : rows.filter((r) => !r.collapsible)
  const s = new Date(start).getTime()
  const width = Math.max(1, new Date(end).getTime() - s)
  const basisWords: Record<string, string> = { case_setting: "case zone", phones_device_zone: "case zone, the phones' own", device_zone: "the phone's zone", chosen: "chosen" }
  const zoneLabel = zone === "UTC" ? "UTC" : `${zoneWords(start, zone)} (${basisWords[zoneBasis || "device_zone"] || "case zone"})`
  const fmt = (t: string) => new Intl.DateTimeFormat("en-US", { timeZone: zone, hour: "numeric", minute: "2-digit" }).format(new Date(t))
  return (
    <section aria-label="Lanes" data-lanes-component="shared" className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        {onSpan && SPANS.map((x) => (
          <Button key={x.id} size="sm" variant={span === x.id ? "primary" : "outline"} onClick={() => onSpan(x.id)}>
            {x.label}
          </Button>
        ))}
        <span className="text-muted-foreground">Times in {zoneLabel}. {fmt(start)} to {fmt(end)}.</span>
        {header}
      </div>
      {hiddenRows.length > 0 && (
        <p className="flex items-center gap-2 text-xs text-muted-foreground">
          {showAll ? `Showing ${hiddenCount.toLocaleString("en-US")} device events and sensor readings.`
            : `${hiddenCount.toLocaleString("en-US")} device events and sensor readings hidden.`}
          <Button size="sm" variant="link" onClick={() => setShowAll(!showAll)}>{showAll ? "Hide" : "Show"}</Button>
        </p>
      )}
      {shown.map((row) => (
        <div key={row.id} role="region" aria-label={`Lane: ${row.label}`} className="rounded border p-2">
          <div className="mb-1 flex items-baseline justify-between text-sm">
            <span className="font-medium">{row.label}</span>
            <span className="text-xs text-muted-foreground">
              {(row.total ?? row.marks.length).toLocaleString()} item{(row.total ?? row.marks.length) === 1 ? "" : "s"}
              {row.note ? ` · ${row.note}` : ""}
            </span>
          </div>
          {row.allDay && row.allDay.length > 0 && (
            <ul className="mb-1 flex flex-wrap gap-1 text-xs" aria-label="All day">
              {row.allDay.map((m) => (
                <li key={m.key} className="rounded bg-amber-100 px-1.5 py-0.5 dark:bg-amber-950" title={m.detail}>{m.label} (all day)</li>
              ))}
            </ul>
          )}
          <div className="relative h-8 w-full overflow-hidden rounded bg-background">
            {(row.bands || []).map((b, i) => (
              <div key={i} className={`absolute top-0 h-full ${BAND_CLASS[b.state] || "bg-muted/40"}`} title={b.words}
                style={{ left: `${pct(b.start, s, width)}%`, width: `${Math.max(0.2, pct(b.end, s, width) - pct(b.start, s, width))}%` }} />
            ))}
            {row.marks.map((m) => {
              const left = pct(m.at, s, width)
              const cls = `absolute top-1 h-6 w-1.5 rounded ${TONE_CLASS[m.tone || "none"]}`
              const title = `${fmt(m.at)} · ${m.label}${m.detail ? ` · ${m.detail}` : ""}`
              return m.href
                ? <a key={m.key} href={m.href} className={cls} style={{ left: `${left}%` }} title={title} aria-label={title} />
                : <span key={m.key} className={cls} style={{ left: `${left}%` }} title={title} />
            })}
          </div>
          {row.bands && row.bands.length > 0 && (
            <p className="mt-1 flex flex-wrap gap-2 text-xs text-muted-foreground">
              {Array.from(new Set(row.bands.map((b) => b.words))).map((w) => <span key={w}>{w}</span>)}
            </p>
          )}
        </div>
      ))}
    </section>
  )
}
