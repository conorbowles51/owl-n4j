import { useMemo } from "react"
import { useQuery } from "@tanstack/react-query"
import { timelineAPI } from "../api"
import { getDateRange, deriveEntities } from "../lib/timeline-utils"
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

  const eventTypesQuery = useQuery({
    queryKey: ["timeline", "types"],
    queryFn: () => timelineAPI.getEventTypes(),
  })

  const events = eventsQuery.data?.events ?? []

  const entities = useMemo(() => deriveEntities(events), [events])
  const dateRange = useMemo(() => getDateRange(events), [events])

  return {
    events,
    eventTypes: eventTypesQuery.data ?? [],
    entities,
    dateRange,
    isLoading: eventsQuery.isLoading,
    totalCount: eventsQuery.data?.total ?? 0,
  }
}
