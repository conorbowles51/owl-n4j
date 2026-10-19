import { fetchAPI } from "@/lib/api-client"
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
  error: Error | null
  retry: () => void
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

      if (cursor)
        throw Error(
          "The Timeline is too large to load completely. Narrow the case scope."
        )
      let offset: number | null = 0
      const additions: TimelineEvent[] = []
      do {
        const page: {
          case_id: string
          events: TimelineEvent[]
          next_offset: number | null
        } = await fetchAPI(
          `/api/timeline/entries?${new URLSearchParams({ case_id: caseId!, scope, offset: String(offset) })}`
        )
        if (
          page.case_id !== caseId ||
          (page.next_offset !== null &&
            (!Number.isSafeInteger(page.next_offset) ||
              page.next_offset <= offset))
        )
          throw Error(
            "Timeline additions did not match this case. Reload Timeline."
          )
        additions.push(...page.events)
        if (additions.length > 200000)
          throw Error(
            "There are too many Timeline additions to load completely."
          )
        offset = page.next_offset
      } while (offset !== null)
      const addedPaymentIds = new Set(
        additions
          .filter((event) => event.source?.kind === "transaction")
          .map((event) => event.source!.id)
      )
      const combined = [
        ...events.filter(
          (event) =>
            !event.ledger_transaction_id ||
            !addedPaymentIds.has(event.ledger_transaction_id)
        ),
        ...additions,
      ]
      return {
        events: combined,
        count: combined.length,
        total: total + combined.length - events.length,
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
    error: eventsQuery.error,
    retry: () => {
      void eventsQuery.refetch()
    },
    dataKey: eventsQuery.data?.dataKey ?? null,
  }
}
