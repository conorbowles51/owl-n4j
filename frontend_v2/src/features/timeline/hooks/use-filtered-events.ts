import { useMemo } from "react"
import { markdownToPlainText } from "@/lib/markdown-text"
import type { TimelineEvent } from "../api"
import type { DateGroup } from "../lib/timeline-utils"
import {
  compareTimelineEvents,
  getEventTimestamp,
  groupEventsByDate,
} from "../lib/timeline-utils"

export type StreamItem =
  | { kind: "header"; date: string; label: string; count: number }
  | { kind: "event"; event: TimelineEvent }

interface UseFilteredEventsParams {
  events: TimelineEvent[]
  selectedTypes: Set<string>
  selectedEntityKeys: Set<string>
  dateRange: { start: string | null; end: string | null }
  visibleWindow: { start: string; end: string } | null
  searchTerm: string
  includedEventKeys?: Set<string> | null
}

interface UseFilteredEventsResult {
  items: StreamItem[]
  filteredEvents: TimelineEvent[]
  filteredCount: number
  totalCount: number
  entityFilterCounts: Map<string, number>
}

export function useFilteredEvents({
  events,
  selectedTypes,
  selectedEntityKeys,
  dateRange,
  visibleWindow,
  searchTerm,
  includedEventKeys,
}: UseFilteredEventsParams): UseFilteredEventsResult {
  return useMemo(() => {
    let filtered = events

    if (includedEventKeys) {
      filtered = filtered.filter((event) => includedEventKeys.has(event.key))
    }

    const totalCount = filtered.length

    // 1. Type filter: empty means show all
    if (selectedTypes.size > 0) {
      filtered = filtered.filter((e) => selectedTypes.has(e.type))
    }

    // Compute entity counts BEFORE entity filtering (so sidebar shows accurate counts)
    const entityFilterCounts = new Map<string, number>()
    for (const event of filtered) {
      for (const conn of event.connections) {
        entityFilterCounts.set(
          conn.key,
          (entityFilterCounts.get(conn.key) ?? 0) + 1
        )
      }
    }

    // 2. Entity filter: empty means no entity filter (show all)
    if (selectedEntityKeys.size > 0) {
      filtered = filtered.filter((e) =>
        e.connections.some((c) => selectedEntityKeys.has(c.key))
      )
    }

    // 3. Visible window filter (from overview bar brush)
    if (visibleWindow) {
      const windowStart = new Date(visibleWindow.start).getTime()
      const windowEnd = new Date(visibleWindow.end).getTime()
      filtered = filtered.filter((e) => {
        const ts = getEventTimestamp(e, true)
        return ts >= windowStart && ts <= windowEnd
      })
    }

    // 4. Date range filter (from sidebar date picker)
    if (dateRange.start || dateRange.end) {
      const start = dateRange.start
        ? new Date(dateRange.start).getTime()
        : -Infinity
      const end = dateRange.end
        ? new Date(dateRange.end).getTime() + 86400000
        : Infinity
      filtered = filtered.filter((e) => {
        const ts = getEventTimestamp(e, true)
        return ts >= start && ts < end
      })
    }

    // 5. Search filter
    if (searchTerm.trim()) {
      const term = searchTerm.toLowerCase()
      filtered = filtered.filter(
        (e) =>
          e.name.toLowerCase().includes(term) ||
          e.type.toLowerCase().includes(term) ||
          (e.summary &&
            markdownToPlainText(e.summary).toLowerCase().includes(term)) ||
          (e.notes && e.notes.toLowerCase().includes(term)) ||
          (e.amount && e.amount.toLowerCase().includes(term)) ||
          e.connections.some((c) => c.name.toLowerCase().includes(term))
      )
    }

    // 6. Group by date for the stream
    const sortedFiltered = [...filtered].sort(compareTimelineEvents)
    const groups: DateGroup[] = groupEventsByDate(sortedFiltered)
    const items: StreamItem[] = []
    for (const group of groups) {
      items.push({
        kind: "header",
        date: group.date,
        label: group.label,
        count: group.events.length,
      })
      for (const event of group.events) {
        items.push({ kind: "event", event })
      }
    }

    return {
      items,
      filteredEvents: sortedFiltered,
      filteredCount: sortedFiltered.length,
      totalCount,
      entityFilterCounts,
    }
  }, [
    events,
    selectedTypes,
    selectedEntityKeys,
    dateRange,
    visibleWindow,
    searchTerm,
    includedEventKeys,
  ])
}
