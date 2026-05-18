import { useEffect, useState } from "react"

import { cellebriteEventsAPI } from "../../api"
import type { TimelineItem } from "../../types"
import { eventKey } from "../events/eventUtils"

export function useTimelineEvents({
  caseId,
  reportKeys,
  eventTypes,
  startDate,
  endDate,
  enabled,
}: {
  caseId: string
  reportKeys: string[] | null
  eventTypes: string[]
  startDate: string | null
  endDate: string | null
  enabled: boolean
}) {
  const [events, setEvents] = useState<TimelineItem[]>([])
  const [loading, setLoading] = useState(false)
  const [progress, setProgress] = useState(0)
  const [stage, setStage] = useState("")
  const disabled = !enabled || eventTypes.length === 0

  useEffect(() => {
    if (disabled) return

    let cancelled = false
    const timer = window.setTimeout(() => {
      void (async () => {
        const aggregated: TimelineItem[] = []
        const seen = new Set<string>()
        setLoading(true)
        setProgress(0)
        setStage("")
        setEvents([])

        for (let index = 0; index < eventTypes.length; index += 1) {
          if (cancelled) return
          const type = eventTypes[index]
          setStage(`Loading ${type.replace(/_/g, " ")} events`)
          try {
            const data = await cellebriteEventsAPI.getEvents(caseId, {
              reportKeys,
              eventTypes: [type],
              startDate,
              endDate,
              onlyGeolocated: false,
              limit: 5000,
            })
            if (cancelled) return
            ;(data.events ?? []).forEach((event, eventIndex) => {
              const key = eventKey(event, `${type}-${eventIndex}`)
              if (seen.has(key)) return
              seen.add(key)
              aggregated.push(event)
            })
          } catch {
            // Keep Neil's resilient phased behavior: one bad event type should not blank the whole timeline.
          }
          setProgress(Math.round(((index + 1) / eventTypes.length) * 100))
        }

        if (!cancelled) {
          setEvents(aggregated)
          setLoading(false)
          setStage("")
        }
      })()
    }, 250)

    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [caseId, disabled, endDate, eventTypes, reportKeys, startDate])

  return disabled ? { events: [] as TimelineItem[], loading: false, progress: 0, stage: "" } : { events, loading, progress, stage }
}
