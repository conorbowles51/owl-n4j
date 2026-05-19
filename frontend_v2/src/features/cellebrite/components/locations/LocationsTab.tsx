import { useMemo, useState, type ReactNode } from "react"
import { Loader2, Play, Route } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { cn } from "@/lib/cn"

import {
  useEventTracks,
  useEvents,
  useLocationSuggestionValues,
  useLocationTiles,
} from "../../hooks/use-cellebrite"
import type {
  LocationSuggestionValuesResponse,
  PhoneReport,
  RailSelection,
  TimelineItem,
} from "../../types"
import { matchCellebriteItem, parseCellebriteQuery } from "../../lib/search"
import {
  compactNumber,
  readNumber,
  readText,
} from "../shared/cellebrite-format"
import { SmallEmpty } from "../shared/SmallEmpty"
import { EventDateScrubber } from "../events/EventDateScrubber"
import { EventMapPanel } from "../events/EventMapPanel"
import { EventPlaybackBar } from "../events/EventPlaybackBar"
import {
  clampPlayhead,
  dateRangeFromEvents,
  locationOf,
  reportKeyOf,
  reportMaps,
} from "../events/eventUtils"
import { LocationsTable } from "./LocationsTable"
import {
  locationId,
  locationTitle,
  tileCellDeg,
  tileToLocationEvent,
  type LocationTableView,
  type LocationRenderMode,
} from "./locationUtils"

const TILE_ZOOM = 6

export function LocationsTab({
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
  const [renderMode, setRenderMode] = useState<LocationRenderMode>("tiles")
  const [windowStart, setWindowStart] = useState("")
  const [windowEnd, setWindowEnd] = useState("")
  const [localSearch, setLocalSearch] = useState("")
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [tableView, setTableView] = useState<LocationTableView>("auto")
  const [trajectoryOn, setTrajectoryOn] = useState(false)
  const [playheadTime, setPlayheadTime] = useState<Date | null>(null)
  const [isPlaying, setIsPlaying] = useState(false)
  const [playbackSpeed, setPlaybackSpeed] = useStoredNumber(
    `cb.locations.playbackSpeed.${caseId}`,
    16
  )
  const startDate = windowStart || dateFilters.startDate
  const endDate = windowEnd || dateFilters.endDate
  const search = localSearch || query
  const parsedSearch = useMemo(() => parseCellebriteQuery(search), [search])
  const suggestionsId = `location-search-suggestions-${caseId}`
  const forceRaw = Boolean(trajectoryOn || playheadTime || search.trim())
  const effectiveRenderMode: LocationRenderMode = forceRaw ? "raw" : renderMode

  const tilesQuery = useLocationTiles(
    caseId,
    {
      reportKeys,
      startDate: startDate || null,
      endDate: endDate || null,
      zoom: TILE_ZOOM,
    },
    active && effectiveRenderMode === "tiles"
  )
  const rawQuery = useEvents(
    caseId,
    {
      reportKeys,
      startDate: startDate || null,
      endDate: endDate || null,
      eventTypes: ["location"],
      onlyGeolocated: true,
      limit: 5000,
    },
    active && effectiveRenderMode === "raw"
  )
  const tracksQuery = useEventTracks(
    caseId,
    { reportKeys, startDate: startDate || null, endDate: endDate || null },
    active && effectiveRenderMode === "raw"
  )
  const suggestionsQuery = useLocationSuggestionValues(
    caseId,
    { reportKeys },
    active
  )

  const cellDeg = tileCellDeg(tilesQuery.data?.cell_deg)
  const tileMarkers = useMemo(
    () =>
      (tilesQuery.data?.tiles ?? []).map((tile) =>
        tileToLocationEvent(tile, cellDeg)
      ),
    [cellDeg, tilesQuery.data?.tiles]
  )
  const rawLocations = useMemo(
    () =>
      (rawQuery.data?.events ?? []).filter((row) => Boolean(locationOf(row))),
    [rawQuery.data?.events]
  )
  const searchOptions = useMemo(
    () =>
      buildLocationSearchOptions(suggestionsQuery.data, reports, rawLocations),
    [rawLocations, reports, suggestionsQuery.data]
  )
  const visibleLocations = useMemo(() => {
    const rows = effectiveRenderMode === "tiles" ? tileMarkers : rawLocations
    if (!search.trim() || effectiveRenderMode === "tiles") return rows
    return rows.filter(
      (row) => matchCellebriteItem(row, parsedSearch, "event", reports).matches
    )
  }, [
    effectiveRenderMode,
    parsedSearch,
    rawLocations,
    reports,
    search,
    tileMarkers,
  ])
  const { colorByKey } = useMemo(() => reportMaps(reports), [reports])
  const trajectoryTracks = useMemo(() => {
    if (!trajectoryOn || effectiveRenderMode !== "raw") return []
    const byReport = new Map<
      string,
      { latitude: number; longitude: number; timestamp?: string | null }[]
    >()
    visibleLocations.forEach((location) => {
      const point = locationOf(location)
      const timestamp = String(location.timestamp ?? "")
      if (!point || !timestamp) return
      const key = reportKeyOf(location) || "unknown"
      if (!byReport.has(key)) byReport.set(key, [])
      byReport.get(key)!.push({ ...point, timestamp })
    })
    return [...byReport.entries()]
      .map(([key, points]) => ({
        report_key: key,
        points: points.sort((a, b) =>
          String(a.timestamp ?? "").localeCompare(String(b.timestamp ?? ""))
        ),
      }))
      .filter((track) => track.points.length > 1)
  }, [effectiveRenderMode, trajectoryOn, visibleLocations])
  const loading =
    effectiveRenderMode === "tiles" ? tilesQuery.isLoading : rawQuery.isLoading
  const totalLocationCount =
    effectiveRenderMode === "tiles"
      ? readNumber(tilesQuery.data ?? {}, ["total"], 0)
      : rawLocations.length
  const effectivePlayhead = useMemo(
    () => (playheadTime ? clampPlayhead(playheadTime, visibleLocations) : null),
    [playheadTime, visibleLocations]
  )
  const resolvedTableView =
    tableView === "auto"
      ? effectiveRenderMode === "tiles"
        ? "tiles"
        : "rows"
      : tableView === "byPhoneDay" && effectiveRenderMode === "tiles"
        ? "tiles"
        : tableView

  function togglePlayback() {
    if (playheadTime) {
      setPlayheadTime(null)
      setIsPlaying(false)
      return
    }
    if (effectiveRenderMode === "tiles") {
      setRenderMode("raw")
      return
    }
    const range = dateRangeFromEvents(visibleLocations)
    if (range.min) setPlayheadTime(range.min)
  }

  function selectLocation(row: TimelineItem) {
    const id = locationId(row)
    setSelectedId(id)
    if (readText(row, ["event_type", "type"]) === "location_tile") {
      onSelect({
        id,
        kind: "tile",
        title: locationTitle(row),
        payload: {
          ...row,
          cell_x: readNumber(row, ["cell_x"]),
          cell_y: readNumber(row, ["cell_y"]),
          cell_deg: cellDeg,
          count: readNumber(row, ["count"]),
          report_keys: reportKeys ?? reports.map((report) => report.report_key),
          start_date: startDate || null,
          end_date: endDate || null,
        },
      })
      return
    }
    onSelect({
      id,
      kind: "event",
      title: locationTitle(row),
      payload: { ...row, event_type: "location" },
    })
  }

  return (
    <section className="flex h-full min-h-0 flex-col overflow-hidden bg-background">
      <div className="flex min-h-11 shrink-0 items-center gap-2 border-b border-border bg-muted/20 px-3 py-1.5 text-xs">
        <span className="text-muted-foreground">View:</span>
        <ModeButton
          current={effectiveRenderMode}
          mode="tiles"
          onClick={setRenderMode}
        >
          Aggregated tiles
        </ModeButton>
        <ModeButton
          current={effectiveRenderMode}
          mode="raw"
          onClick={setRenderMode}
        >
          Raw points
        </ModeButton>
        <Button
          type="button"
          variant={trajectoryOn ? "secondary" : "outline"}
          size="sm"
          className="ml-2 h-7 gap-1 px-2 text-xs"
          onClick={() => setTrajectoryOn((current) => !current)}
          title="Draw a chronological line through raw location points"
        >
          <Route className="size-3.5" />
          {trajectoryOn ? "Trajectory ON" : "Show trajectory"}
        </Button>
        <Button
          type="button"
          variant={playheadTime ? "secondary" : "outline"}
          size="sm"
          className="h-7 gap-1 px-2 text-xs"
          onClick={togglePlayback}
          title="Scrub through raw location points over time"
        >
          <Play className="size-3.5" />
          {playheadTime ? "Playback ON" : "Playback"}
        </Button>
        <span className="ml-2 text-muted-foreground">
          {effectiveRenderMode === "tiles"
            ? "Cheap server-side aggregation. Click a tile for the rows it contains."
            : "Capped at 5,000 points. Narrow with date/search to focus."}
        </span>
        <span className="ml-auto text-muted-foreground">
          {effectiveRenderMode === "tiles"
            ? `${compactNumber(tileMarkers.length)} tiles / ${compactNumber(totalLocationCount)} locations`
            : `${compactNumber(visibleLocations.length)} of ${compactNumber(rawLocations.length)} points`}
        </span>
        {(tilesQuery.isLoading ||
          rawQuery.isLoading ||
          tracksQuery.isLoading) && (
          <Loader2 className="size-4 animate-spin text-muted-foreground" />
        )}
      </div>
      <div className="flex min-h-10 shrink-0 items-center gap-1 border-b border-border bg-card px-3 text-xs">
        <span className="text-muted-foreground">Table:</span>
        <TableViewButton current={tableView} mode="auto" onClick={setTableView}>
          Auto
        </TableViewButton>
        <TableViewButton current={tableView} mode="rows" onClick={setTableView}>
          Rows
        </TableViewButton>
        <TableViewButton
          current={tableView}
          mode="byPhoneDay"
          onClick={setTableView}
        >
          Phone x day
        </TableViewButton>
        {tableView === "byPhoneDay" && effectiveRenderMode === "tiles" && (
          <span className="ml-2 text-muted-foreground">
            Switch to raw points to group by phone and day.
          </span>
        )}
      </div>

      <div className="shrink-0 border-b border-border bg-card px-3 py-2">
        <Input
          value={localSearch}
          onChange={(event) => setLocalSearch(event.target.value)}
          list={suggestionsId}
          placeholder={
            query
              ? `Global search active: ${query}`
              : "Search - try place:Dublin, near:53.35,-6.26,1km, app:WhatsApp"
          }
          className="h-8 text-xs"
        />
        <datalist id={suggestionsId}>
          {searchOptions.map((option) => (
            <option key={option} value={option} />
          ))}
        </datalist>
      </div>

      {effectiveRenderMode === "raw" && (
        <EventDateScrubber
          events={rawLocations}
          startDate={startDate}
          endDate={endDate}
          onWindowChange={(nextStart, nextEnd) => {
            setWindowStart(nextStart)
            setWindowEnd(nextEnd)
          }}
        />
      )}

      <div className="min-h-0 flex-1">
        {loading && visibleLocations.length === 0 ? (
          <div className="flex h-full items-center justify-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="size-5 animate-spin" />
            Loading locations
          </div>
        ) : visibleLocations.length === 0 ? (
          <SmallEmpty label="No locations match the current filters." />
        ) : (
          <EventMapPanel
            events={visibleLocations}
            tracks={
              trajectoryOn
                ? trajectoryTracks
                : effectiveRenderMode === "raw"
                  ? (tracksQuery.data?.tracks ?? [])
                  : []
            }
            playheadTime={effectivePlayhead}
            trailWindowMs={30 * 60 * 1000}
            isPlaying={Boolean(effectivePlayhead)}
            selectedEventKey={selectedId}
            colorByReport={colorByKey}
            active={active}
            onEventSelect={selectLocation}
          />
        )}
      </div>

      {effectivePlayhead && (
        <EventPlaybackBar
          events={visibleLocations}
          playheadTime={effectivePlayhead}
          isPlaying={isPlaying}
          playbackSpeed={playbackSpeed}
          onPlayheadChange={setPlayheadTime}
          onPlayingChange={setIsPlaying}
          onPlaybackSpeedChange={setPlaybackSpeed}
        />
      )}

      <div className="h-64 shrink-0 overflow-hidden border-t border-border">
        <LocationsTable
          locations={visibleLocations}
          selectedId={selectedId}
          reports={reports}
          viewMode={resolvedTableView}
          playheadTime={effectivePlayhead}
          trailWindowMs={30 * 60 * 1000}
          onRowClick={selectLocation}
        />
      </div>
    </section>
  )
}

function ModeButton({
  current,
  mode,
  onClick,
  children,
}: {
  current: LocationRenderMode
  mode: LocationRenderMode
  onClick: (mode: LocationRenderMode) => void
  children: ReactNode
}) {
  const active = current === mode
  return (
    <Button
      type="button"
      variant={active ? "secondary" : "ghost"}
      size="sm"
      className={cn("h-7 px-2 text-xs", !active && "text-muted-foreground")}
      onClick={() => onClick(mode)}
    >
      {children}
    </Button>
  )
}

function TableViewButton({
  current,
  mode,
  onClick,
  children,
}: {
  current: LocationTableView
  mode: LocationTableView
  onClick: (mode: LocationTableView) => void
  children: ReactNode
}) {
  const active = current === mode
  return (
    <Button
      type="button"
      variant={active ? "secondary" : "ghost"}
      size="sm"
      className={cn("h-7 px-2 text-xs", !active && "text-muted-foreground")}
      onClick={() => onClick(mode)}
    >
      {children}
    </Button>
  )
}

function useStoredNumber(
  key: string,
  fallback: number
): [number, (value: number) => void] {
  const [value, setValue] = useState<number>(() => {
    if (typeof window === "undefined") return fallback
    const stored = Number(window.localStorage.getItem(key))
    return Number.isFinite(stored) && stored > 0 ? stored : fallback
  })
  function update(next: number) {
    setValue(next)
    if (typeof window !== "undefined")
      window.localStorage.setItem(key, String(next))
  }
  return [value, update]
}

function buildLocationSearchOptions(
  suggestions: LocationSuggestionValuesResponse | undefined,
  reports: PhoneReport[],
  rows: TimelineItem[]
) {
  const options = new Map<string, number>()
  const add = (operator: string, value: unknown, count = 0) => {
    if (typeof value !== "string" || !value.trim()) return
    const token = `${operator}:${quoteSearchValue(value.trim())}`
    options.set(token, Math.max(options.get(token) ?? 0, count))
  }

  suggestions?.location_type?.forEach((row) =>
    add("type", row.value, row.count)
  )
  suggestions?.source_app?.forEach((row) => add("app", row.value, row.count))
  suggestions?.place_name?.forEach((row) => add("place", row.value, row.count))
  suggestions?.admin1?.forEach((row) => add("place", row.value, row.count))
  suggestions?.country?.forEach((row) => add("place", row.value, row.count))

  rows.slice(0, 500).forEach((row) => {
    add("type", readText(row, ["location_type"]))
    add("app", readText(row, ["source_app", "app"]))
    add("place", readText(row, ["place_name", "address", "admin1", "country"]))
  })

  reports.forEach((report) => {
    add(
      "phone",
      report.device_name_override ||
        report.device_name ||
        report.phone_owner_name ||
        report.report_key
    )
  })

  return [...options.entries()]
    .sort(
      (left, right) => right[1] - left[1] || left[0].localeCompare(right[0])
    )
    .slice(0, 120)
    .map(([value]) => value)
}

function quoteSearchValue(value: string) {
  return /\s/.test(value) ? `"${value.replace(/"/g, "")}"` : value
}
