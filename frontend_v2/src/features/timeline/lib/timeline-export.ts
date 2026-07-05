import type { TimelineEvent, TimelineExportRequest, TimelineView } from "../api"

export type TimelineExportDetailLevel = "compact" | "standard" | "detailed"
export type TimelineExportFormat = "pdf" | "csv"
export type TimelineExportSource = "view" | "selection" | "filtered"

export const TIMELINE_EXPORT_FIELDS = [
  { key: "date", label: "Date" },
  { key: "time", label: "Time" },
  { key: "type", label: "Type" },
  { key: "title", label: "Event title" },
  { key: "amount", label: "Amount" },
  { key: "location", label: "Location" },
  { key: "linked_entities", label: "Linked entities" },
  { key: "summary", label: "Summary" },
  { key: "notes", label: "Notes" },
  { key: "source_references", label: "Source appendix" },
  { key: "notebook_notes", label: "Notebook notes" },
] as const

export type TimelineExportFieldKey = (typeof TIMELINE_EXPORT_FIELDS)[number]["key"]
export type TimelineExportFields = Record<TimelineExportFieldKey, boolean>

export function defaultTimelineExportFields(
  detailLevel: TimelineExportDetailLevel
): TimelineExportFields {
  return {
    date: true,
    time: true,
    type: true,
    title: true,
    amount: true,
    location: true,
    linked_entities: detailLevel !== "compact",
    summary: detailLevel !== "compact",
    notes: detailLevel === "detailed",
    source_references: true,
    notebook_notes: false,
  }
}

export function timelineDateSpan(events: TimelineEvent[]) {
  const dates = events
    .map((event) => event.date?.slice(0, 10))
    .filter((date): date is string => Boolean(date))
  if (dates.length === 0) return "No dated events"
  dates.sort()
  return dates[0] === dates[dates.length - 1]
    ? dates[0]
    : `${dates[0]} to ${dates[dates.length - 1]}`
}

export function buildTimelineExportPayload({
  caseId,
  source,
  format,
  detailLevel,
  fields,
  activeView,
  filteredEvents,
  selectedKeys,
  title,
}: {
  caseId: string
  source: TimelineExportSource
  format: TimelineExportFormat
  detailLevel: TimelineExportDetailLevel
  fields: TimelineExportFields
  activeView: TimelineView | null
  filteredEvents: TimelineEvent[]
  selectedKeys: Set<string>
  title?: string | null
}): TimelineExportRequest {
  const selectedEventKeys = Array.from(selectedKeys)
  const filteredEventKeys = filteredEvents.map((event) => event.key)
  return {
    case_id: caseId,
    source,
    format,
    detail_level: detailLevel,
    fields,
    footer_label: "Confidential",
    title: title?.trim() || activeView?.title || "Timeline Export",
    view_id: source === "view" ? activeView?.id ?? null : null,
    event_keys:
      source === "selection"
        ? selectedEventKeys
        : source === "filtered"
          ? filteredEventKeys
          : [],
  }
}
