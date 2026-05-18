import { useMemo, useState } from "react"
import { ArrowDown, ArrowUp, MapPin } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/cn"

import type { PhoneReport, TimelineItem } from "../../types"
import { compactNumber, readText, truncate } from "../shared/cellebrite-format"
import {
  eventColor,
  eventKey,
  eventLabel,
  eventTimestamp,
  eventType,
  formatTs,
  locationOf,
  parseTs,
  reportLabel,
  reportMaps,
} from "./eventUtils"

type SortKey = "timestamp" | "event_type" | "device" | "label" | "source_app"
type SortState = { key: SortKey; dir: "asc" | "desc" }

const COLUMNS: { key: SortKey | "geo"; label: string; className?: string }[] = [
  { key: "timestamp", label: "Time", className: "w-[170px]" },
  { key: "event_type", label: "Type", className: "w-[130px]" },
  { key: "device", label: "Device", className: "w-[170px]" },
  { key: "label", label: "Label", className: "w-[220px]" },
  { key: "source_app", label: "App", className: "w-[140px]" },
  { key: "geo", label: "Geo", className: "w-[80px] text-right" },
]

export function EventsTable({
  events,
  reports,
  playheadTime,
  isPlaying,
  selectedEventKey,
  onEventSelect,
}: {
  events: TimelineItem[]
  reports: PhoneReport[]
  playheadTime: Date | null
  isPlaying: boolean
  selectedEventKey: string | null
  onEventSelect: (event: TimelineItem) => void
}) {
  const [sort, setSort] = useState<SortState>({ key: "timestamp", dir: "desc" })
  const { labelByKey, colorByKey } = useMemo(() => reportMaps(reports), [reports])
  const sortedEvents = useMemo(() => {
    const rows = [...events]
    const factor = sort.dir === "asc" ? 1 : -1
    rows.sort((a, b) => {
      const av = sortValue(a, sort.key, labelByKey)
      const bv = sortValue(b, sort.key, labelByKey)
      return av.localeCompare(bv) * factor
    })
    return rows
  }, [events, labelByKey, sort])
  const playheadMs = playheadTime?.getTime() ?? null

  function toggleSort(key: SortKey) {
    setSort((current) =>
      current.key === key
        ? { key, dir: current.dir === "asc" ? "desc" : "asc" }
        : { key, dir: key === "timestamp" ? "desc" : "asc" }
    )
  }

  return (
    <div className="flex h-full min-h-0 flex-col bg-card">
      <div className="min-h-0 flex-1 overflow-auto">
        <table className="w-full min-w-[1080px] table-fixed text-left text-xs">
          <thead className="sticky top-0 z-10 bg-muted text-[11px] uppercase tracking-wide text-muted-foreground">
            <tr>
              {COLUMNS.map((column) => {
                const sortable = column.key !== "geo"
                const active = sortable && sort.key === column.key
                const Icon = sort.dir === "asc" ? ArrowUp : ArrowDown
                return (
                  <th key={column.key} className={cn("border-b border-border px-3 py-2 font-semibold", column.className)}>
                    {sortable ? (
                      <button
                        type="button"
                        onClick={() => toggleSort(column.key as SortKey)}
                        className={cn("inline-flex items-center gap-1", active && "text-amber-600")}
                      >
                        {column.label}
                        {active && <Icon className="size-3" />}
                      </button>
                    ) : (
                      column.label
                    )}
                  </th>
                )
              })}
              <th className="border-b border-border px-3 py-2 font-semibold">Summary</th>
            </tr>
          </thead>
          <tbody>
            {sortedEvents.map((event, index) => {
              const key = eventKey(event, `event-${index}`)
              const selected = selectedEventKey === key
              const timestamp = parseTs(eventTimestamp(event))
              const future = playheadMs != null && timestamp != null && timestamp.getTime() > playheadMs
              const reportKey = readText(event, ["device_report_key", "report_key", "cellebrite_report_key"])
              const location = locationOf(event)
              return (
                <tr
                  key={`${key}-${index}`}
                  onClick={() => onEventSelect(event)}
                  className={cn(
                    "cursor-pointer border-b border-border/70 transition-colors hover:bg-muted/50",
                    selected && "bg-amber-500/10",
                    isPlaying && future && "opacity-45"
                  )}
                >
                  <td className="truncate px-3 py-2 tabular-nums">{formatTs(eventTimestamp(event))}</td>
                  <td className="truncate px-3 py-2">
                    <span
                      className="inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium text-white"
                      style={{ backgroundColor: eventColor(eventType(event)) }}
                    >
                      {eventType(event)}
                    </span>
                  </td>
                  <td className="truncate px-3 py-2">
                    <span className="inline-flex max-w-full items-center gap-1">
                      <span
                        className="size-2.5 shrink-0 rounded-full"
                        style={{ backgroundColor: colorByKey.get(reportKey) ?? "#64748b" }}
                      />
                      <span className="truncate">{reportLabel(event, labelByKey) || "-"}</span>
                    </span>
                  </td>
                  <td className="truncate px-3 py-2 font-medium">{eventLabel(event)}</td>
                  <td className="truncate px-3 py-2 text-muted-foreground">{readText(event, ["source_app", "app"], "-")}</td>
                  <td className="px-3 py-2 text-right">
                    {location ? (
                      <Badge variant="success" className="ml-auto">
                        <MapPin className="mr-1 size-3" />
                        Yes
                      </Badge>
                    ) : (
                      <span className="text-muted-foreground">-</span>
                    )}
                  </td>
                  <td className="truncate px-3 py-2 text-muted-foreground">
                    {truncate(readText(event, ["summary", "body", "description"], "-"), 160)}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <div className="flex h-8 shrink-0 items-center border-t border-border bg-muted/20 px-3 text-[11px] text-muted-foreground">
        Showing {compactNumber(sortedEvents.length)} events
        <span className="ml-auto">Sorted by {sort.key} {sort.dir === "asc" ? "up" : "down"}</span>
      </div>
    </div>
  )
}

function sortValue(event: TimelineItem, key: SortKey, reportLabels: Map<string, string>): string {
  if (key === "timestamp") return eventTimestamp(event)
  if (key === "event_type") return eventType(event)
  if (key === "device") return reportLabel(event, reportLabels)
  if (key === "label") return eventLabel(event)
  return readText(event, ["source_app", "app"])
}
