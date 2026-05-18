import { useMemo, useState, type ReactNode } from "react"
import { Loader2 } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { cn } from "@/lib/cn"

import { useEventTracks, useEvents, useLocationTiles } from "../../hooks/use-cellebrite"
import type { PhoneReport, RailSelection, TimelineItem } from "../../types"
import { compactNumber, readNumber, readText } from "../shared/cellebrite-format"
import { SmallEmpty } from "../shared/SmallEmpty"
import { EventDateScrubber } from "../events/EventDateScrubber"
import { EventMapPanel } from "../events/EventMapPanel"
import { locationOf, reportMaps } from "../events/eventUtils"
import { LocationsTable } from "./LocationsTable"
import {
  locationId,
  locationSearchText,
  locationTitle,
  tileCellDeg,
  tileToLocationEvent,
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
  const startDate = windowStart || dateFilters.startDate
  const endDate = windowEnd || dateFilters.endDate
  const search = localSearch || query

  const tilesQuery = useLocationTiles(
    caseId,
    { reportKeys, startDate: startDate || null, endDate: endDate || null, zoom: TILE_ZOOM },
    active && renderMode === "tiles"
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
    active && renderMode === "raw"
  )
  const tracksQuery = useEventTracks(
    caseId,
    { reportKeys, startDate: startDate || null, endDate: endDate || null },
    active && renderMode === "raw"
  )

  const cellDeg = tileCellDeg(tilesQuery.data?.cell_deg)
  const tileMarkers = useMemo(
    () => (tilesQuery.data?.tiles ?? []).map((tile) => tileToLocationEvent(tile, cellDeg)),
    [cellDeg, tilesQuery.data?.tiles]
  )
  const rawLocations = useMemo(
    () => (rawQuery.data?.events ?? []).filter((row) => Boolean(locationOf(row))),
    [rawQuery.data?.events]
  )
  const visibleLocations = useMemo(() => {
    const rows = renderMode === "tiles" ? tileMarkers : rawLocations
    const term = search.trim().toLowerCase()
    if (!term || renderMode === "tiles") return rows
    return rows.filter((row) => locationSearchText(row, reports).toLowerCase().includes(term))
  }, [rawLocations, renderMode, reports, search, tileMarkers])
  const { colorByKey } = useMemo(() => reportMaps(reports), [reports])
  const loading = renderMode === "tiles" ? tilesQuery.isLoading : rawQuery.isLoading
  const totalLocationCount = renderMode === "tiles"
    ? readNumber(tilesQuery.data ?? {}, ["total"], 0)
    : rawLocations.length

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
        <ModeButton current={renderMode} mode="tiles" onClick={setRenderMode}>
          Aggregated tiles
        </ModeButton>
        <ModeButton current={renderMode} mode="raw" onClick={setRenderMode}>
          Raw points
        </ModeButton>
        <span className="ml-2 text-muted-foreground">
          {renderMode === "tiles"
            ? "Cheap server-side aggregation. Click a tile for the rows it contains."
            : "Capped at 5,000 points. Narrow with date/search to focus."}
        </span>
        <span className="ml-auto text-muted-foreground">
          {renderMode === "tiles"
            ? `${compactNumber(tileMarkers.length)} tiles / ${compactNumber(totalLocationCount)} locations`
            : `${compactNumber(visibleLocations.length)} of ${compactNumber(rawLocations.length)} points`}
        </span>
        {(tilesQuery.isLoading || rawQuery.isLoading || tracksQuery.isLoading) && (
          <Loader2 className="size-4 animate-spin text-muted-foreground" />
        )}
      </div>

      {renderMode === "raw" && (
        <>
          <EventDateScrubber
            events={rawLocations}
            startDate={startDate}
            endDate={endDate}
            onWindowChange={(nextStart, nextEnd) => {
              setWindowStart(nextStart)
              setWindowEnd(nextEnd)
            }}
          />
          <div className="shrink-0 border-b border-border bg-card px-3 py-2">
            <Input
              value={localSearch}
              onChange={(event) => setLocalSearch(event.target.value)}
              placeholder={query ? `Global search active: ${query}` : "Search locations, apps, places, coordinates"}
              className="h-8 text-xs"
            />
          </div>
        </>
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
            tracks={renderMode === "raw" ? tracksQuery.data?.tracks ?? [] : []}
            playheadTime={null}
            trailWindowMs={30 * 60 * 1000}
            isPlaying={false}
            selectedEventKey={selectedId}
            colorByReport={colorByKey}
            active={active}
            onEventSelect={selectLocation}
          />
        )}
      </div>

      <div className="h-64 shrink-0 overflow-hidden border-t border-border">
        <LocationsTable
          locations={visibleLocations}
          selectedId={selectedId}
          reports={reports}
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
