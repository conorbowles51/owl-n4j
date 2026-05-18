import { useMemo, useState } from "react"
import { Columns2, Loader2, Map as MapIcon, Rows3, Search } from "lucide-react"

import { Input } from "@/components/ui/input"
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable"
import { cn } from "@/lib/cn"

import { useEventTracks, useEventTypes, useEvents } from "../../hooks/use-cellebrite"
import type { CellebriteRecord, PhoneReport, RailSelection, TimelineItem } from "../../types"
import { compactNumber, isRecord, readText } from "../shared/cellebrite-format"
import { SmallEmpty } from "../shared/SmallEmpty"
import { EventDateScrubber } from "./EventDateScrubber"
import { EventMapPanel } from "./EventMapPanel"
import { EventPlaybackBar } from "./EventPlaybackBar"
import { EventTimelinePanel } from "./EventTimelinePanel"
import { EventTypeFilter } from "./EventTypeFilter"
import { EventsTable } from "./EventsTable"
import { IntersectionPanel } from "./IntersectionPanel"
import {
  clampPlayhead,
  eventKey,
  eventLabel,
  eventMatchesSearch,
  locationOf,
  reportMaps,
  type EventsViewMode,
} from "./eventUtils"

export function EventsTab({
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
  const [onlyGeolocated, setOnlyGeolocated] = useStoredBoolean(`cb.events.onlyGeo.${caseId}`, false)
  const [viewMode, setViewMode] = useStoredMode<EventsViewMode>(`cb.events.viewMode.${caseId}`, "map")
  const [windowStart, setWindowStart] = useState("")
  const [windowEnd, setWindowEnd] = useState("")
  const [localSearch, setLocalSearch] = useState("")
  const [selectedEventKey, setSelectedEventKey] = useState<string | null>(null)
  const [playheadTime, setPlayheadTime] = useState<Date | null>(null)
  const [isPlaying, setIsPlaying] = useState(false)
  const [playbackSpeed, setPlaybackSpeed] = useStoredNumber(`cb.events.playbackSpeed.${caseId}`, 60)
  const [intersectionResults, setIntersectionResults] = useState<Record<string, CellebriteRecord>>({})
  const [intersectionCollapsed, setIntersectionCollapsed] = useStoredBoolean(`cb.events.intersections.${caseId}`, false)

  const eventTypesQuery = useEventTypes(caseId, reportKeys, active)
  const typeRows = useMemo(
    () => ((eventTypesQuery.data?.types ?? []) as CellebriteRecord[]).filter(isRecord),
    [eventTypesQuery.data?.types]
  )
  const typeKeys = useMemo(
    () => typeRows.map((row) => readText(row, ["event_type", "type"], "event")),
    [typeRows]
  )
  const activeTypes = activeTypeOverride ?? new Set(typeKeys)
  const startDate = windowStart || dateFilters.startDate
  const endDate = windowEnd || dateFilters.endDate
  const activeTypeList = activeTypes.size === typeKeys.length ? null : [...activeTypes]
  const eventsQuery = useEvents(
    caseId,
    {
      reportKeys,
      startDate: startDate || null,
      endDate: endDate || null,
      eventTypes: activeTypeList,
      onlyGeolocated,
      limit: 5000,
    },
    active && activeTypes.size > 0
  )
  const tracksQuery = useEventTracks(
    caseId,
    { reportKeys, startDate: startDate || null, endDate: endDate || null },
    active
  )

  const events = useMemo(() => eventsQuery.data?.events ?? [], [eventsQuery.data?.events])
  const { labelByKey, colorByKey } = useMemo(() => reportMaps(reports), [reports])
  const search = localSearch || query
  const filteredEvents = useMemo(() => {
    const searched = events.filter((event) => eventMatchesSearch(event, search, labelByKey))
    return searched
  }, [events, labelByKey, search])
  const selectedReportKeys = useMemo(
    () => new Set(reportKeys ?? reports.map((report) => report.report_key)),
    [reportKeys, reports]
  )
  const tracks = tracksQuery.data?.tracks ?? []
  const geolocatedCount = useMemo(
    () => filteredEvents.reduce((count, event) => count + (locationOf(event) ? 1 : 0), 0),
    [filteredEvents]
  )
  const effectivePlayhead = useMemo(() => clampPlayhead(playheadTime, filteredEvents), [filteredEvents, playheadTime])

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

  function jumpToMatch(match: CellebriteRecord) {
    const evidence = Array.isArray(match.evidence) ? match.evidence.find(isRecord) : null
    const event = evidence ?? match
    const key = eventKey(event)
    setSelectedEventKey(key)
    if (readText(event, ["timestamp", "start_time"])) {
      const date = new Date(readText(event, ["timestamp", "start_time"]))
      if (!Number.isNaN(date.getTime())) setPlayheadTime(date)
    }
    onSelect({
      id: key,
      kind: "event",
      title: readText(event, ["label", "summary", "method"], "Intersection match"),
      payload: event,
    })
  }

  const mainPanel = (
    <div className="flex min-h-0 flex-1">
      <div className="min-w-0 flex-1">
        {eventsQuery.isLoading && filteredEvents.length === 0 ? (
          <div className="flex h-full items-center justify-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="size-5 animate-spin" />
            Loading phone events
          </div>
        ) : activeTypes.size === 0 ? (
          <SmallEmpty label="Select at least one event type" />
        ) : viewMode === "map" ? (
          <EventMapPanel
            events={filteredEvents}
            tracks={tracks}
            playheadTime={effectivePlayhead}
            trailWindowMs={30 * 60 * 1000}
            isPlaying={isPlaying}
            selectedEventKey={selectedEventKey}
            colorByReport={colorByKey}
            active={active}
            onEventSelect={selectEvent}
          />
        ) : viewMode === "split" ? (
          <ResizablePanelGroup orientation="vertical" className="h-full min-h-0">
            <ResizablePanel defaultSize={58} minSize={25}>
              <EventMapPanel
                events={filteredEvents}
                tracks={tracks}
                playheadTime={effectivePlayhead}
                trailWindowMs={30 * 60 * 1000}
                isPlaying={isPlaying}
                selectedEventKey={selectedEventKey}
                colorByReport={colorByKey}
                active={active}
                onEventSelect={selectEvent}
              />
            </ResizablePanel>
            <ResizableHandle withHandle />
            <ResizablePanel defaultSize={42} minSize={20}>
              <EventsTable
                events={filteredEvents}
                reports={reports}
                playheadTime={effectivePlayhead}
                isPlaying={isPlaying}
                selectedEventKey={selectedEventKey}
                onEventSelect={selectEvent}
              />
            </ResizablePanel>
          </ResizablePanelGroup>
        ) : (
          <EventsTable
            events={filteredEvents}
            reports={reports}
            playheadTime={effectivePlayhead}
            isPlaying={isPlaying}
            selectedEventKey={selectedEventKey}
            onEventSelect={selectEvent}
          />
        )}
      </div>
      <IntersectionPanel
        caseId={caseId}
        reportKeys={reportKeys}
        startDate={startDate}
        endDate={endDate}
        results={intersectionResults}
        collapsed={intersectionCollapsed}
        onCollapsedChange={setIntersectionCollapsed}
        onResult={(method, result) => setIntersectionResults((current) => ({ ...current, [method]: result }))}
        onJumpToMatch={jumpToMatch}
      />
    </div>
  )

  return (
    <section className="flex h-full min-h-0 flex-col overflow-hidden">
      <div className="flex min-h-12 shrink-0 items-center gap-3 overflow-x-auto border-b border-border bg-muted/20 px-3 py-2">
        <EventTypeFilter
          types={typeRows}
          activeTypes={activeTypes}
          onlyGeolocated={onlyGeolocated}
          onTypesChange={setActiveTypeOverride}
          onOnlyGeolocatedChange={setOnlyGeolocated}
        />
        <div className="ml-auto flex shrink-0 items-center gap-2">
          {(eventsQuery.isLoading || tracksQuery.isLoading) && <Loader2 className="size-4 animate-spin text-muted-foreground" />}
          <span className="text-xs text-muted-foreground">
            {compactNumber(filteredEvents.length)} of {compactNumber(events.length)} events
            <span className="ml-1 text-muted-foreground/80">· {compactNumber(geolocatedCount)} geolocated</span>
          </span>
          <ViewModeToggle mode={viewMode} onChange={setViewMode} />
        </div>
      </div>
      <EventDateScrubber
        events={events}
        startDate={startDate}
        endDate={endDate}
        onWindowChange={(nextStart, nextEnd) => {
          setWindowStart(nextStart)
          setWindowEnd(nextEnd)
        }}
      />
      <div className="shrink-0 border-b border-border bg-card px-3 py-2">
        <div className="relative">
          <Search className="absolute left-2 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={localSearch}
            onChange={(event) => setLocalSearch(event.target.value)}
            placeholder={query ? `Global search active: ${query}` : "Search events, apps, devices, participants"}
            className="h-8 pl-7 text-xs"
          />
        </div>
      </div>
      {mainPanel}
      <EventPlaybackBar
        events={filteredEvents}
        playheadTime={effectivePlayhead}
        isPlaying={isPlaying}
        playbackSpeed={playbackSpeed}
        onPlayheadChange={setPlayheadTime}
        onPlayingChange={setIsPlaying}
        onPlaybackSpeedChange={setPlaybackSpeed}
      />
      <div className="h-[30vh] min-h-[180px] shrink-0 border-t border-border">
        <EventTimelinePanel
          events={filteredEvents}
          reports={reports}
          selectedReportKeys={selectedReportKeys}
          playheadTime={effectivePlayhead}
          onPlayheadChange={setPlayheadTime}
          onEventSelect={selectEvent}
        />
      </div>
    </section>
  )
}

function ViewModeToggle({
  mode,
  onChange,
}: {
  mode: EventsViewMode
  onChange: (mode: EventsViewMode) => void
}) {
  const options = [
    { key: "map" as const, label: "Map", icon: MapIcon },
    { key: "split" as const, label: "Split", icon: Columns2 },
    { key: "table" as const, label: "Table", icon: Rows3 },
  ]
  return (
    <div className="inline-flex overflow-hidden rounded-md border border-border">
      {options.map((option) => {
        const Icon = option.icon
        return (
          <button
            key={option.key}
            type="button"
            onClick={() => onChange(option.key)}
            className={cn(
              "inline-flex h-8 items-center gap-1 border-r border-border px-2 text-xs last:border-r-0",
              mode === option.key ? "bg-secondary text-secondary-foreground" : "bg-card text-muted-foreground hover:bg-muted"
            )}
          >
            <Icon className="size-3.5" />
            {option.label}
          </button>
        )
      })}
    </div>
  )
}

function useStoredMode<T extends string>(key: string, fallback: T): [T, (value: T) => void] {
  const [value, setValue] = useState<T>(() => {
    if (typeof window === "undefined") return fallback
    const stored = window.localStorage.getItem(key)
    return (stored as T | null) ?? fallback
  })
  function update(next: T) {
    setValue(next)
    if (typeof window !== "undefined") window.localStorage.setItem(key, next)
  }
  return [value, update]
}

function useStoredBoolean(key: string, fallback: boolean): [boolean, (value: boolean) => void] {
  const [value, setValue] = useState<boolean>(() => {
    if (typeof window === "undefined") return fallback
    const stored = window.localStorage.getItem(key)
    return stored == null ? fallback : stored === "1"
  })
  function update(next: boolean) {
    setValue(next)
    if (typeof window !== "undefined") window.localStorage.setItem(key, next ? "1" : "0")
  }
  return [value, update]
}

function useStoredNumber(key: string, fallback: number): [number, (value: number) => void] {
  const [value, setValue] = useState<number>(() => {
    if (typeof window === "undefined") return fallback
    const stored = Number(window.localStorage.getItem(key))
    return Number.isFinite(stored) && stored > 0 ? stored : fallback
  })
  function update(next: number) {
    setValue(next)
    if (typeof window !== "undefined") window.localStorage.setItem(key, String(next))
  }
  return [value, update]
}
