import { MapPin } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/cn"

import type { PhoneReport, TimelineItem } from "../../types"
import { compactDate, readList, readText } from "../shared/cellebrite-format"
import { PhoneReportChip } from "../shared/PhoneReportChip"
import { SmallEmpty } from "../shared/SmallEmpty"
import { reportMaps, reportKeyOf } from "../events/eventUtils"
import { locationCoordinateLabel, locationId } from "./locationUtils"

export function LocationsTable({
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
  const { colorByKey } = reportMaps(reports)
  const showPhoneChip = reports.length > 1

  if (locations.length === 0) {
    return (
      <div className="flex h-full items-center justify-center">
        <SmallEmpty label="No locations match the current filters." />
      </div>
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
            {showPhoneChip && <th className="w-44 px-3 py-2 font-medium">Device</th>}
            <th className="px-3 py-2 font-medium">Address</th>
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
                  selected ? "bg-amber-500/10 ring-1 ring-inset ring-amber-400/50" : "hover:bg-muted/50"
                )}
              >
                <td className="whitespace-nowrap px-3 py-1.5 tabular-nums">
                  {readText(location, ["timestamp"]) ? compactDate(location.timestamp) : "-"}
                </td>
                <td className="truncate px-3 py-1.5">
                  {readText(location, ["location_type", "label", "event_type"], "-")}
                </td>
                <td className="truncate px-3 py-1.5">
                  {readText(location, ["source_app", "app"], apps.join(", ") || "-")}
                </td>
                <td className="whitespace-nowrap px-3 py-1.5 font-mono text-[11px]">
                  <span className="inline-flex items-center gap-1">
                    <MapPin className="size-3 text-cyan-500" />
                    {locationCoordinateLabel(location)}
                  </span>
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
  const fallback = [readText(location, ["admin1"]), readText(location, ["country"])].filter(Boolean).join(", ")

  return (
    <span className="inline-flex max-w-full items-center gap-1">
      <span className="truncate">{address || fallback || "-"}</span>
      {geocodeSource && geocodeSource !== "cellebrite" && geocodeSource !== "none" && (
        <Badge variant="slate" className="shrink-0 rounded-sm px-1 py-0 text-[9px] uppercase">
          via {geocodeSource}
        </Badge>
      )}
    </span>
  )
}
