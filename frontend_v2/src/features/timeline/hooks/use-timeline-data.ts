import { useMemo } from "react"
import { useQuery } from "@tanstack/react-query"
import { timelineAPI } from "../api"
import {
  compareTimelineEvents,
  deriveEntities,
  getDateRange,
  isValidDate,
} from "../lib/timeline-utils"

import type { DateRange, DerivedEntity } from "../lib/timeline-utils"
import type { TimelineEvent } from "../api"
import { useCaseLayer } from "@/features/significant/stores/case-layer.store"

interface UseTimelineDataParams {
  caseId: string | undefined
}

interface UseTimelineDataResult {
  events: TimelineEvent[]
  eventTypes: string[]
  entities: DerivedEntity[]
  dateRange: DateRange
  isLoading: boolean
  totalCount: number
  dataKey: string | null
}

export function useTimelineData({
  caseId,
}: UseTimelineDataParams): UseTimelineDataResult {
  const scope = useCaseLayer(caseId)
  const eventsQuery = useQuery({
    queryKey: ["timeline", caseId, scope],
    queryFn: async () => {
      const events: TimelineEvent[] = []
      let cursor: string | undefined
      let total = 0
      let pageCount = 0

      do {
        const page = await timelineAPI.getEvents({
          caseId: caseId!,
          limit: 2000,
          cursor,
          scope,
        })
        events.push(...page.events)
        total = page.total
        cursor = page.next_cursor ?? undefined
        pageCount += 1
      } while (cursor && pageCount < 100)

      return {
        events,
        count: events.length,
        total,
        next_cursor: cursor,
        dataKey: `${caseId}:${scope}`,
      }
    },
    enabled: !!caseId,
  })

  const events = useMemo(() => {
    const rawEvents = eventsQuery.data?.events ?? []
    const valid = rawEvents.filter((e) => isValidDate(e.date))
    if (valid.length < rawEvents.length) {
      console.warn(
        `Timeline: skipped ${rawEvents.length - valid.length} event(s) with invalid dates`
      )
    }
    return [...valid].sort(compareTimelineEvents)
  }, [eventsQuery.data?.events])

  const eventTypes = useMemo(() => {
    const counts: Record<string, number> = {}
    for (const e of events) {
      counts[e.type] = (counts[e.type] ?? 0) + 1
    }
    return Object.entries(counts)
      .sort((a, b) => b[1] - a[1])
      .map(([type]) => type)
  }, [events])

  const entities = useMemo(() => deriveEntities(events), [events])
  const dateRange = useMemo(() => getDateRange(events), [events])

  return {
    events,
    eventTypes,
    entities,
    dateRange,
    isLoading: eventsQuery.isLoading,
    totalCount: eventsQuery.data?.total ?? 0,
    dataKey: eventsQuery.data?.dataKey ?? null,
  }
}
