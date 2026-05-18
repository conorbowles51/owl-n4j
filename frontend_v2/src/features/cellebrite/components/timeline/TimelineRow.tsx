import { MapPin } from "lucide-react"

import { cn } from "@/lib/cn"

import type { PhoneReport, TimelineItem } from "../../types"
import { compactNumber, readText } from "../shared/cellebrite-format"
import { EVENT_ICONS, EVENT_LABELS, eventColor, eventKey, eventLabel, eventType, reportKeyOf, reportMaps } from "../events/eventUtils"
import { HighlightedText } from "./HighlightedText"
import { formatTimelineTime, timelineDirection, timelineSummary } from "./timelineUtils"

export function TimelineRow({
  event,
  reports,
  selected,
  highlights,
  onClick,
}: {
  event: TimelineItem
  reports: PhoneReport[]
  selected: boolean
  highlights: string[]
  onClick: () => void
}) {
  const type = eventType(event)
  const Icon = EVENT_ICONS[type as keyof typeof EVENT_ICONS] ?? MapPin
  const color = eventColor(type)
  const direction = timelineDirection(event)
  const summary = timelineSummary(event)
  const sourceApp = readText(event, ["source_app", "app", "app_name"])
  const duration = readText(event, ["duration", "duration_text"])
  const reportKey = reportKeyOf(event)
  const { labelByKey, colorByKey } = reportMaps(reports)
  const reportLabel = labelByKey.get(reportKey) ?? reportKey
  const reportColor = colorByKey.get(reportKey) ?? "#64748b"
  const showPhoneChip = reports.length > 1 && reportKey
  const title = EVENT_LABELS[type] ?? eventLabel(event)
  const count = readText(event, ["attachment_count", "file_count"])

  return (
    <li>
      <button
        type="button"
        onClick={onClick}
        className={cn(
          "grid w-full grid-cols-[82px_18px_minmax(0,1fr)] items-start gap-2 rounded-md py-1.5 pl-2 pr-2 text-left transition-colors hover:bg-muted",
          selected && "bg-amber-500/10 ring-1 ring-amber-500/40"
        )}
        style={showPhoneChip ? { borderLeft: `4px solid ${reportColor}` } : undefined}
      >
        <span className="pt-0.5 text-[11px] tabular-nums text-muted-foreground">{formatTimelineTime(event)}</span>
        <span className="mt-1 size-3 rounded-full" style={{ backgroundColor: color }} />
        <span className="min-w-0">
          <span className="flex min-w-0 flex-wrap items-center gap-1.5">
            <Icon className="size-3 shrink-0" style={{ color }} />
            <span className="text-[11px] font-semibold text-foreground">{title}</span>
            {sourceApp ? (
              <span className="text-[10px] text-muted-foreground">
                - <HighlightedText text={sourceApp} highlights={highlights} />
              </span>
            ) : null}
            {readText(event, ["direction"]) ? <span className="text-[10px] text-muted-foreground">- {readText(event, ["direction"])}</span> : null}
            {duration ? <span className="text-[10px] text-muted-foreground">- {duration}</span> : null}
            {count ? <span className="text-[10px] text-muted-foreground">- {compactNumber(Number(count))} files</span> : null}
            {showPhoneChip ? (
              <span className="ml-auto max-w-48 truncate rounded-full border border-border bg-card px-2 py-0.5 text-[10px] text-muted-foreground">
                {reportLabel}
              </span>
            ) : null}
          </span>
          {direction ? (
            <span className="block truncate text-xs text-foreground">
              <HighlightedText text={direction} highlights={highlights} />
            </span>
          ) : null}
          {summary ? (
            <span className="block truncate text-xs text-muted-foreground" title={summary}>
              <HighlightedText text={summary} highlights={highlights} />
            </span>
          ) : null}
          <span className="sr-only">{eventKey(event)}</span>
        </span>
      </button>
    </li>
  )
}
