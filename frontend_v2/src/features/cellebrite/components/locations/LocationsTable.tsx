import { Layers, MapPin } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/cn"

import type { PhoneReport, TimelineItem } from "../../types"
import { readList, readText } from "../shared/cellebrite-format"
import { PhoneReportChip } from "../shared/PhoneReportChip"
import { SmallEmpty } from "../shared/SmallEmpty"
import {
  formatTs,
  locationOf,
  reportKeyOf,
  reportMaps,
} from "../events/eventUtils"
import { locationCoordinateLabel, locationId } from "./locationUtils"

export function LocationsTable({
  locations,
  selectedId,
  reports,
  onRowClick,
  viewMode = "rows",
  playheadTime = null,
  trailWindowMs = 30 * 60 * 1000,
}: {
  locations: TimelineItem[]
  selectedId: string | null
  reports: PhoneReport[]
  onRowClick: (row: TimelineItem) => void
  viewMode?: "rows" | "tiles" | "byPhoneDay"
  playheadTime?: Date | null
  trailWindowMs?: number
}) {
  const { colorByKey } = reportMaps(reports)
  const showPhoneChip = reports.length > 1

  if (locations.length === 0) {
    return (
      <div className="flex h-full items-center justify-center">
        <SmallEmpty label="No locations match the current filters." />
      </div>
    )
  }

  if (viewMode === "tiles") {
    return (
      <TilesTable
        locations={locations}
        selectedId={selectedId}
        onRowClick={onRowClick}
      />
    )
  }

  if (viewMode === "byPhoneDay") {
    return (
      <ByPhoneDayTable
        locations={locations}
        selectedId={selectedId}
        reports={reports}
        onRowClick={onRowClick}
      />
    )
  }

  return (
    <div className="h-full overflow-y-auto">
      <table className="w-full table-fixed text-left text-xs">
        <thead className="sticky top-0 z-10 border-b border-border bg-muted text-muted-foreground">
          <tr>
            <th className="w-40 px-3 py-2 font-medium">Time</th>
            <th className="w-40 px-3 py-2 font-medium">Type</th>
            <th className="w-36 px-3 py-2 font-medium">Source app</th>
            <th className="w-40 px-3 py-2 font-medium">Lat / Lon</th>
            <th
              className="w-20 px-3 py-2 font-medium"
              title="GPS accuracy in metres"
            >
              +/-m
            </th>
            <th
              className="w-20 px-3 py-2 font-medium"
              title="Cellebrite confidence"
            >
              Conf.
            </th>
            {showPhoneChip && (
              <th className="w-44 px-3 py-2 font-medium">Device</th>
            )}
            <th className="w-64 px-3 py-2 font-medium">Place</th>
            <th className="w-36 px-3 py-2 font-medium">Region</th>
            <th className="w-32 px-3 py-2 font-medium">Country</th>
          </tr>
        </thead>
        <tbody>
          {locations.map((location, index) => {
            const id = locationId(location, `location-${index}`)
            const selected = selectedId === id
            const reportKey = reportKeyOf(location)
            const apps = readList(location, ["top_apps"])
            return (
              <tr
                key={`${id}-${index}`}
                onClick={() => onRowClick(location)}
                className={cn(
                  "cursor-pointer border-b border-border/70 transition-colors",
                  playbackRowClass(location, playheadTime, trailWindowMs),
                  selected
                    ? "bg-amber-500/10 ring-1 ring-inset ring-amber-400/50"
                    : "hover:bg-muted/50"
                )}
              >
                <td className="whitespace-nowrap px-3 py-1.5 tabular-nums">
                  {readText(location, ["timestamp"])
                    ? formatTs(location.timestamp)
                    : "-"}
                </td>
                <td className="truncate px-3 py-1.5">
                  {readText(
                    location,
                    ["location_type", "label", "event_type"],
                    "-"
                  )}
                </td>
                <td className="truncate px-3 py-1.5">
                  {readText(
                    location,
                    ["source_app", "app"],
                    apps.join(", ") || "-"
                  )}
                </td>
                <td className="whitespace-nowrap px-3 py-1.5 font-mono text-[11px]">
                  <span className="inline-flex items-center gap-1">
                    <MapPin className="size-3 text-cyan-500" />
                    {locationCoordinateLabel(location)}
                  </span>
                </td>
                <td className="whitespace-nowrap px-3 py-1.5 tabular-nums text-muted-foreground">
                  <Accuracy location={location} />
                </td>
                <td className="whitespace-nowrap px-3 py-1.5 text-muted-foreground">
                  {readText(location, ["confidence_score"]) || "-"}
                </td>
                {showPhoneChip && (
                  <td className="px-3 py-1.5">
                    {reportKey ? (
                      <PhoneReportChip
                        reportKey={reportKey}
                        reports={reports}
                        color={colorByKey.get(reportKey)}
                        compact
                      />
                    ) : (
                      <span className="text-muted-foreground">-</span>
                    )}
                  </td>
                )}
                <td className="truncate px-3 py-1.5 text-muted-foreground">
                  <LocationAddress location={location} />
                </td>
                <td className="truncate px-3 py-1.5 text-muted-foreground">
                  {readText(location, ["admin1"]) || "-"}
                </td>
                <td className="truncate px-3 py-1.5 text-muted-foreground">
                  {readText(location, ["country"]) || "-"}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function TilesTable({
  locations,
  selectedId,
  onRowClick,
}: {
  locations: TimelineItem[]
  selectedId: string | null
  onRowClick: (row: TimelineItem) => void
}) {
  return (
    <div className="h-full overflow-y-auto">
      <table className="w-full table-fixed text-left text-xs">
        <thead className="sticky top-0 z-10 border-b border-border bg-muted text-muted-foreground">
          <tr>
            <th className="w-56 px-3 py-2 font-medium">Tile</th>
            <th className="w-24 px-3 py-2 font-medium">Hits</th>
            <th className="px-3 py-2 font-medium">Top apps</th>
            <th className="w-48 px-3 py-2 font-medium">Lat / Lon</th>
          </tr>
        </thead>
        <tbody>
          {locations.map((location, index) => {
            const id = locationId(location, `tile-${index}`)
            const selected = selectedId === id
            const apps = readList(location, ["top_apps"])
            return (
              <tr
                key={`${id}-${index}`}
                onClick={() => onRowClick(location)}
                className={cn(
                  "cursor-pointer border-b border-border/70 transition-colors",
                  selected
                    ? "bg-amber-500/10 ring-1 ring-inset ring-amber-400/50"
                    : "hover:bg-muted/50"
                )}
              >
                <td className="truncate px-3 py-1.5 font-medium">
                  <span className="inline-flex items-center gap-1">
                    <Layers className="size-3 text-cyan-500" />
                    {readText(location, ["label"], "Tile")}
                  </span>
                </td>
                <td className="whitespace-nowrap px-3 py-1.5 tabular-nums font-semibold">
                  {Number(location.count ?? 0).toLocaleString()}
                </td>
                <td className="truncate px-3 py-1.5 text-muted-foreground">
                  {apps.length ? apps.join(", ") : "-"}
                </td>
                <td className="whitespace-nowrap px-3 py-1.5 font-mono text-[11px]">
                  <span className="inline-flex items-center gap-1">
                    <MapPin className="size-3 text-cyan-500" />
                    {locationCoordinateLabel(location)}
                  </span>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function ByPhoneDayTable({
  locations,
  selectedId,
  reports,
  onRowClick,
}: {
  locations: TimelineItem[]
  selectedId: string | null
  reports: PhoneReport[]
  onRowClick: (row: TimelineItem) => void
}) {
  const rows = locationsByPhoneDay(locations)
  const showPhoneChip = reports.length > 1

  if (rows.length === 0) {
    return (
      <div className="flex h-full items-center justify-center">
        <SmallEmpty label="Nothing to group by phone and day." />
      </div>
    )
  }

  return (
    <div className="h-full overflow-y-auto">
      <table className="w-full table-fixed text-left text-xs">
        <thead className="sticky top-0 z-10 border-b border-border bg-muted text-muted-foreground">
          <tr>
            <th className="w-32 px-3 py-2 font-medium">Day</th>
            {showPhoneChip && (
              <th className="w-44 px-3 py-2 font-medium">Device</th>
            )}
            <th className="w-40 px-3 py-2 font-medium">Source app</th>
            <th className="w-20 px-3 py-2 font-medium">Hits</th>
            <th className="w-56 px-3 py-2 font-medium">First / Last</th>
            <th className="w-48 px-3 py-2 font-medium">Centroid</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const selected = selectedId === locationId(row.sampleRow)
            return (
              <tr
                key={row.key}
                onClick={() => onRowClick(row.sampleRow)}
                className={cn(
                  "cursor-pointer border-b border-border/70 transition-colors",
                  selected
                    ? "bg-amber-500/10 ring-1 ring-inset ring-amber-400/50"
                    : "hover:bg-muted/50"
                )}
              >
                <td className="whitespace-nowrap px-3 py-1.5 tabular-nums">
                  {row.day}
                </td>
                {showPhoneChip && (
                  <td className="px-3 py-1.5">
                    {row.reportKey !== "unknown" ? (
                      <PhoneReportChip
                        reportKey={row.reportKey}
                        reports={reports}
                        compact
                      />
                    ) : (
                      <span className="text-muted-foreground">-</span>
                    )}
                  </td>
                )}
                <td className="truncate px-3 py-1.5">{row.sourceApp}</td>
                <td className="whitespace-nowrap px-3 py-1.5 tabular-nums font-semibold">
                  {row.count.toLocaleString()}
                </td>
                <td className="whitespace-nowrap px-3 py-1.5 tabular-nums text-muted-foreground">
                  {row.first && row.last
                    ? row.first === row.last
                      ? formatTs(row.first)
                      : `${formatTs(row.first)} / ${formatTs(row.last)}`
                    : "-"}
                </td>
                <td className="whitespace-nowrap px-3 py-1.5 font-mono text-[11px]">
                  <span className="inline-flex items-center gap-1">
                    <MapPin className="size-3 text-cyan-500" />
                    {row.latitude.toFixed(4)}, {row.longitude.toFixed(4)}
                  </span>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function LocationAddress({ location }: { location: TimelineItem }) {
  const address = readText(location, ["address", "place_name"])
  const geocodeSource = readText(location, ["geocode_source"])
  const fallback = [
    readText(location, ["admin1"]),
    readText(location, ["country"]),
  ]
    .filter(Boolean)
    .join(", ")

  return (
    <span className="inline-flex max-w-full items-center gap-1">
      <span className="truncate">{address || fallback || "-"}</span>
      {geocodeSource &&
        geocodeSource !== "cellebrite" &&
        geocodeSource !== "none" && (
          <Badge
            variant="slate"
            className="shrink-0 rounded-sm px-1 py-0 text-[9px] uppercase"
          >
            via {geocodeSource}
          </Badge>
        )}
    </span>
  )
}

function Accuracy({ location }: { location: TimelineItem }) {
  const accuracy = readText(location, ["accuracy_meters"])
  const parsed = Number(accuracy)
  if (!Number.isFinite(parsed)) return <>-</>
  return <>{Math.round(parsed).toLocaleString()}</>
}

function playbackRowClass(
  location: TimelineItem,
  playheadTime: Date | null,
  trailWindowMs: number
) {
  if (!playheadTime || !location.timestamp) return ""
  const timestamp = new Date(String(location.timestamp)).getTime()
  if (!Number.isFinite(timestamp)) return ""
  const head = playheadTime.getTime()
  if (timestamp > head) return "opacity-30"
  if (timestamp >= head - trailWindowMs) return "border-l-4 border-l-amber-500"
  return ""
}

function locationsByPhoneDay(locations: TimelineItem[]) {
  type Bucket = {
    key: string
    reportKey: string
    day: string
    sourceApp: string
    count: number
    first: string | null
    last: string | null
    latSum: number
    lonSum: number
    sampleRow: TimelineItem
  }
  const buckets = new Map<string, Bucket>()
  locations.forEach((location) => {
    const loc = locationOf(location)
    if (!loc) return
    const day = String(location.timestamp ?? "").slice(0, 10) || "-"
    const reportKey = reportKeyOf(location) || "unknown"
    const sourceApp = readText(location, ["source_app", "app"], "-")
    const key = `${reportKey}|${day}|${sourceApp}`
    const current = buckets.get(key) ?? {
      key,
      reportKey,
      day,
      sourceApp,
      count: 0,
      first: null,
      last: null,
      latSum: 0,
      lonSum: 0,
      sampleRow: location,
    }
    current.count += 1
    current.latSum += loc.latitude
    current.lonSum += loc.longitude
    const timestamp = String(location.timestamp ?? "")
    if (timestamp && (!current.first || timestamp < current.first))
      current.first = timestamp
    if (timestamp && (!current.last || timestamp > current.last)) {
      current.last = timestamp
      current.sampleRow = location
    }
    buckets.set(key, current)
  })
  return [...buckets.values()]
    .map((bucket) => ({
      ...bucket,
      latitude: bucket.latSum / bucket.count,
      longitude: bucket.lonSum / bucket.count,
    }))
    .sort((a, b) => String(b.last ?? "").localeCompare(String(a.last ?? "")))
}
