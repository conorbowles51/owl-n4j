import { useMemo, useState } from "react"

import type { PhoneReport, TimelineItem } from "../../types"
import { compactNumber } from "../shared/cellebrite-format"
import {
  dateRangeFromEvents,
  eventColor,
  eventKey,
  eventLabel,
  eventTimestamp,
  eventType,
  formatTs,
  parseTs,
  reportMaps,
  reportKeyOf,
} from "./eventUtils"

export function EventTimelinePanel({
  events,
  reports,
  selectedReportKeys,
  playheadTime,
  onPlayheadChange,
  onEventSelect,
}: {
  events: TimelineItem[]
  reports: PhoneReport[]
  selectedReportKeys: Set<string>
  playheadTime: Date | null
  onPlayheadChange: (date: Date) => void
  onEventSelect: (event: TimelineItem) => void
}) {
  const [hover, setHover] = useState<{ event: TimelineItem; x: number; y: number } | null>(null)
  const { labelByKey, colorByKey } = useMemo(() => reportMaps(reports), [reports])
  const range = useMemo(() => dateRangeFromEvents(events), [events])
  const lanes = useMemo(
    () =>
      reports
        .filter((report) => selectedReportKeys.size === 0 || selectedReportKeys.has(report.report_key))
        .map((report) => ({
          key: report.report_key,
          label: labelByKey.get(report.report_key) ?? report.report_key,
          color: colorByKey.get(report.report_key) ?? "#2563eb",
        })),
    [colorByKey, labelByKey, reports, selectedReportKeys]
  )
  const eventsByLane = useMemo(() => {
    const map = new Map<string, TimelineItem[]>()
    events.forEach((event) => {
      const key = reportKeyOf(event) || "unknown"
      const rows = map.get(key) ?? []
      rows.push(event)
      map.set(key, rows)
    })
    return map
  }, [events])

  if (!range.min || !range.max || lanes.length === 0) {
    return (
      <div className="flex h-full items-center justify-center bg-muted/20 text-sm text-muted-foreground">
        No timestamped events to plot.
      </div>
    )
  }

  const labelWidth = 170
  const laneHeight = 34
  const plotWidth = 940
  const totalMs = Math.max(1, range.max.getTime() - range.min.getTime())
  const height = lanes.length * laneHeight + 42
  const xOf = (date: Date) => labelWidth + ((date.getTime() - range.min!.getTime()) / totalMs) * plotWidth
  const playheadX = playheadTime ? xOf(playheadTime) : null

  function handleScrub(clientX: number, left: number) {
    const x = Math.max(labelWidth, Math.min(labelWidth + plotWidth, clientX - left))
    const ratio = (x - labelWidth) / plotWidth
    onPlayheadChange(new Date(range.min!.getTime() + ratio * totalMs))
  }

  return (
    <div
      className="relative h-full w-full overflow-auto bg-muted/20"
      onMouseDown={(event) => {
        const rect = event.currentTarget.getBoundingClientRect()
        handleScrub(event.clientX, rect.left)
      }}
      onMouseMove={(event) => {
        if (event.buttons !== 1) return
        const rect = event.currentTarget.getBoundingClientRect()
        handleScrub(event.clientX, rect.left)
      }}
    >
      <svg width={labelWidth + plotWidth + 24} height={height} className="block min-w-full">
        <text x={labelWidth} y={14} fontSize="10" fill="currentColor" className="text-muted-foreground">
          {formatTs(range.min)}
        </text>
        <text x={labelWidth + plotWidth} y={14} fontSize="10" fill="currentColor" textAnchor="end" className="text-muted-foreground">
          {formatTs(range.max)}
        </text>
        {lanes.map((lane, index) => {
          const y = 26 + index * laneHeight
          const laneEvents = eventsByLane.get(lane.key) ?? []
          return (
            <g key={lane.key}>
              <text x={labelWidth - 8} y={y + 17} fontSize="11" fill="currentColor" textAnchor="end" className="text-foreground">
                {lane.label.length > 24 ? `${lane.label.slice(0, 23)}...` : lane.label}
              </text>
              <rect x={labelWidth} y={y} width={plotWidth} height={laneHeight - 5} fill={index % 2 ? "rgba(148,163,184,0.08)" : "rgba(148,163,184,0.14)"} />
              <rect x={labelWidth} y={y} width={3} height={laneHeight - 5} fill={lane.color} />
              {laneEvents.map((event, eventIndex) => {
                const ts = parseTs(eventTimestamp(event))
                if (!ts) return null
                const x = xOf(ts)
                return (
                  <circle
                    key={`${eventKey(event)}-${eventIndex}`}
                    cx={x}
                    cy={y + 14}
                    r={eventType(event) === "location" ? 4 : 3}
                    fill={eventColor(eventType(event))}
                    opacity={0.9}
                    onMouseEnter={() => setHover({ event, x, y: y + 14 })}
                    onMouseLeave={() => setHover(null)}
                    onClick={(mouseEvent) => {
                      mouseEvent.stopPropagation()
                      onEventSelect(event)
                    }}
                    className="cursor-pointer"
                  />
                )
              })}
            </g>
          )
        })}
        {playheadX != null && (
          <line x1={playheadX} x2={playheadX} y1={20} y2={height - 8} stroke="#f59e0b" strokeWidth="2" />
        )}
      </svg>
      {hover && (
        <div
          className="pointer-events-none absolute z-10 max-w-[280px] rounded-md border border-border bg-popover px-2 py-1 text-[11px] text-popover-foreground shadow-lg"
          style={{ left: hover.x + 8, top: hover.y - 10 }}
        >
          <div className="font-semibold">{eventLabel(hover.event)}</div>
          <div className="text-muted-foreground">{formatTs(eventTimestamp(hover.event))}</div>
          <div className="text-muted-foreground">{eventType(hover.event)} · {compactNumber(1)} event</div>
        </div>
      )}
    </div>
  )
}

