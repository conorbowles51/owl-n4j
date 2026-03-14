import { useMemo } from "react"
import { useQuery } from "@tanstack/react-query"
import { timelineAPI } from "../api"
import { getDateRange, deriveEntities, isValidDate } from "../lib/timeline-utils"

import type { DateRange, DerivedEntity } from "../lib/timeline-utils"
import type { TimelineEvent } from "../api"

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
}

export function useTimelineData({ caseId }: UseTimelineDataParams): UseTimelineDataResult {
  const eventsQuery = useQuery({
    queryKey: ["timeline", caseId],
    queryFn: () => timelineAPI.getEvents({ caseId: caseId! }),
    enabled: !!caseId,
  })

  const rawEvents = eventsQuery.data?.events ?? []
  const events = useMemo(() => {
    const valid = rawEvents.filter((e) => isValidDate(e.date))
    if (valid.length < rawEvents.length) {
      console.warn(
        `Timeline: skipped ${rawEvents.length - valid.length} event(s) with invalid dates`
      )
    }
    return valid
  }, [rawEvents])

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
  }
}
