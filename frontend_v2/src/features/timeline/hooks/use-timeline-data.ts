import { useMemo } from "react"
import { useQuery } from "@tanstack/react-query"
import { timelineAPI } from "../api"
import type { EntityType } from "@/lib/theme"

interface UseTimelineDataParams {
  caseId: string | undefined
  startDate?: string
  endDate?: string
  types?: string[]
}

interface EntityInfo {
  key: string
  name: string
  type: EntityType
  eventCount: number
}

export function useTimelineData({ caseId, startDate, endDate, types }: UseTimelineDataParams) {
  const eventsQuery = useQuery({
    queryKey: ["timeline", caseId, startDate, endDate, types],
    queryFn: () =>
      timelineAPI.getEvents({
        caseId: caseId!,
        startDate,
        endDate,
        types,
      }),
    enabled: !!caseId,
  })

  const eventTypesQuery = useQuery({
    queryKey: ["timeline", "types"],
    queryFn: () => timelineAPI.getEventTypes(),
  })

  const events = eventsQuery.data?.events ?? []

  const entities = useMemo<EntityInfo[]>(() => {
    const map = new Map<string, EntityInfo>()
    for (const event of events) {
      const key = event.entity_key || "__unknown__"
      if (!map.has(key)) {
        map.set(key, {
          key,
          name: event.entity_name || "Unknown",
          type: (event.entity_type || "Unknown") as EntityType,
          eventCount: 0,
        })
      }
      map.get(key)!.eventCount++
    }
    return Array.from(map.values()).sort((a, b) => b.eventCount - a.eventCount)
  }, [events])

  const dateRange = useMemo(() => {
    if (events.length === 0) return { min: "", max: "" }
    const dates = events.map((e) => new Date(e.date).getTime())
    return {
      min: new Date(Math.min(...dates)).toISOString().split("T")[0],
      max: new Date(Math.max(...dates)).toISOString().split("T")[0],
    }
  }, [events])

  return {
    events,
    entities,
    eventTypes: eventTypesQuery.data ?? [],
    dateRange,
    isLoading: eventsQuery.isLoading,
    totalCount: eventsQuery.data?.total ?? 0,
  }
}
