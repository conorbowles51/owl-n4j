import { useCallback, useMemo, useRef, useState } from "react"
import { Activity, Loader2 } from "lucide-react"

import { Progress } from "@/components/ui/progress"
import { cn } from "@/lib/cn"

import { useEventTypes } from "../../hooks/use-cellebrite"
import type { CellebriteRecord, PhoneReport, RailSelection, TimelineItem } from "../../types"
import { compactNumber, isRecord, readText } from "../shared/cellebrite-format"
import { SmallEmpty } from "../shared/SmallEmpty"
import { EventTypeFilter } from "../events/EventTypeFilter"
import { eventKey, eventLabel, toDateInput } from "../events/eventUtils"
import { TimelineRow } from "./TimelineRow"
import { TimelineScrubber } from "./TimelineScrubber"
import { TimelineSearchInput } from "./TimelineSearchInput"
import { useTimelineEvents } from "./useTimelineEvents"
import { formatDayHeader, groupTimelineEvents, matchTimelineEvent, parseTimelineQuery } from "./timelineUtils"

export function TimelineTab({
  active,
  caseId,
  reportKeys,
  reports,
  query,
  dateFilters,
  onSelect,
}: {
  active: boolean
  caseId: string
  reportKeys: string[] | null
  reports: PhoneReport[]
  query: string
  dateFilters: { startDate: string; endDate: string }
  onSelect: (selection: RailSelection) => void
}) {
  const [activeTypeOverride, setActiveTypeOverride] = useState<Set<string> | null>(null)
  const [windowStart, setWindowStart] = useState<Date | null>(null)
  const [windowEnd, setWindowEnd] = useState<Date | null>(null)
  const [search, setSearch] = useState("")
  const [selectedEventKey, setSelectedEventKey] = useState<string | null>(null)
  const bodyRef = useRef<HTMLDivElement | null>(null)

  const eventTypesQuery = useEventTypes(caseId, reportKeys, active)
  const typeRows = useMemo(
    () => ((eventTypesQuery.data?.types ?? []) as CellebriteRecord[]).filter(isRecord),
    [eventTypesQuery.data?.types]
  )
  const typeKeys = useMemo(
    () => typeRows.map((row) => readText(row, ["event_type", "type"], "event")),
    [typeRows]
  )
  const activeTypes = useMemo(() => activeTypeOverride ?? new Set(typeKeys), [activeTypeOverride, typeKeys])
  const activeTypeList = useMemo(() => [...activeTypes], [activeTypes])
  const startDate = toDateInput(windowStart) || dateFilters.startDate || null
  const endDate = toDateInput(windowEnd) || dateFilters.endDate || null
  const timelineQuery = useTimelineEvents({
    caseId,
    reportKeys,
    eventTypes: activeTypeList,
    startDate,
    endDate,
    enabled: active && !eventTypesQuery.isLoading && activeTypeList.length > 0,
  })
  const effectiveSearch = search || query
  const parsedQuery = useMemo(() => parseTimelineQuery(effectiveSearch), [effectiveSearch])
  const { filteredEvents, highlights } = useMemo(() => {
    if (!effectiveSearch.trim()) return { filteredEvents: timelineQuery.events, highlights: [] as string[] }
    const terms = new Set<string>()
    const rows = timelineQuery.events.filter((event) => {
      const match = matchTimelineEvent(event, parsedQuery, reports)
      match.highlights.forEach((highlight) => terms.add(highlight))
      return match.matches
    })
    return { filteredEvents: rows, highlights: [...terms] }
  }, [effectiveSearch, parsedQuery, reports, timelineQuery.events])
  const groups = useMemo(() => groupTimelineEvents(filteredEvents), [filteredEvents])
  const loadedCount = timelineQuery.events.length
  const loading = eventTypesQuery.isLoading || timelineQuery.loading

  const scrollToDate = useCallback((bucketStart: Date) => {
    const day = toDateInput(bucketStart)
    const root = bodyRef.current
    if (!root || !day) return
    const headers = root.querySelectorAll<HTMLElement>("[data-day]")
    let target: HTMLElement | null = null
    for (const header of headers) {
      const headerDay = header.dataset.day
      if (!headerDay || headerDay === "-") continue
      if (headerDay <= day) {
        target = header
        break
      }
    }
    target?.scrollIntoView({ behavior: "smooth", block: "start" })
  }, [])

  function selectEvent(event: TimelineItem) {
    const key = eventKey(event)
    setSelectedEventKey(key)
    onSelect({
      id: key,
      kind: "event",
      title: eventLabel(event),
      payload: event,
    })
  }

  return (
    <section className="flex h-full min-h-0 flex-col overflow-hidden bg-background">
      <div className="shrink-0 overflow-x-auto border-b border-border bg-muted/30 px-3 py-2">
        <EventTypeFilter
          types={typeRows}
          activeTypes={activeTypes}
          onlyGeolocated={false}
          onTypesChange={setActiveTypeOverride}
          onOnlyGeolocatedChange={() => undefined}
        />
      </div>
      <TimelineScrubber
        items={timelineQuery.events}
        windowStart={windowStart}
        windowEnd={windowEnd}
        onWindowChange={(start, end) => {
          setWindowStart(start)
          setWindowEnd(end)
        }}
        onBarClick={scrollToDate}
      />
      <div className="shrink-0 border-b border-border bg-card px-3 py-2">
        <TimelineSearchInput
          value={search}
          onChange={setSearch}
          matchCount={filteredEvents.length}
          totalCount={loadedCount}
        />
      </div>
      <div className="flex shrink-0 items-center gap-2 border-b border-border bg-muted/20 px-3 py-1.5 text-[11px] text-muted-foreground">
        <Activity className="size-3.5" />
        <span>
          {compactNumber(filteredEvents.length)} visible from {compactNumber(loadedCount)} loaded phone events
        </span>
        {startDate || endDate ? (
          <span className="ml-auto">
            Window: <span className="text-foreground">{startDate ?? "start"}</span> to{" "}
            <span className="text-foreground">{endDate ?? "end"}</span>
          </span>
        ) : null}
      </div>
      <div ref={bodyRef} className="min-h-0 flex-1 overflow-y-auto">
        {loading && loadedCount === 0 ? (
          <TimelineLoading progress={timelineQuery.progress} stage={timelineQuery.stage || "Loading timeline events"} />
        ) : groups.length === 0 ? (
          <SmallEmpty
            label={
              loadedCount === 0
                ? "No phone events match the current filters."
                : `No timeline events match "${effectiveSearch}".`
            }
          />
        ) : (
          <div className="px-4 py-3">
            {groups.map((group) => (
              <section key={group.day} className="mb-4" data-day={group.day}>
                <div className="sticky top-0 z-10 mb-2 flex items-center gap-2 border-b border-border bg-background pb-1">
                  <span className="text-[11px] font-semibold uppercase text-foreground">{formatDayHeader(group.day)}</span>
                  <span className="text-[10px] text-muted-foreground">
                    {compactNumber(group.events.length)} event{group.events.length === 1 ? "" : "s"}
                  </span>
                </div>
                <ul className="space-y-1">
                  {group.events.map((event, index) => {
                    const key = eventKey(event, `${group.day}-${index}`)
                    return (
                      <TimelineRow
                        key={key}
                        event={event}
                        reports={reports}
                        selected={selectedEventKey === key}
                        highlights={highlights}
                        onClick={() => selectEvent(event)}
                      />
                    )
                  })}
                </ul>
              </section>
            ))}
          </div>
        )}
      </div>
    </section>
  )
}

function TimelineLoading({ progress, stage }: { progress: number; stage: string }) {
  return (
    <div className="flex h-full items-center justify-center">
      <div className="w-full max-w-sm rounded-md border border-border bg-card p-4 shadow-sm">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <Loader2 className="size-4 animate-spin text-amber-500" />
          Loading timeline events
        </div>
        <Progress value={progress} className={cn("mt-3 h-2", progress === 0 && "opacity-60")} />
        <div className="mt-2 text-xs text-muted-foreground">{stage}</div>
      </div>
    </div>
  )
}
