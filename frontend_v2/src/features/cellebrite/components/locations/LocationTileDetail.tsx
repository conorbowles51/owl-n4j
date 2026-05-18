import { Loader2 } from "lucide-react"

import { Badge } from "@/components/ui/badge"

import { useLocationsInTile } from "../../hooks/use-cellebrite"
import type { CellebriteRecord, PhoneReport, TimelineItem } from "../../types"
import { compactNumber, isRecord, readList, readNumber, readText } from "../shared/cellebrite-format"
import { SmallEmpty } from "../shared/SmallEmpty"
import { LocationsTable } from "./LocationsTable"

export function LocationTileDetail({
  caseId,
  payload,
  reports,
  onSelectLocation,
}: {
  caseId: string
  payload: CellebriteRecord
  reports: PhoneReport[]
  onSelectLocation: (location: TimelineItem) => void
}) {
  const cellX = readNumber(payload, ["cell_x"], Number.NaN)
  const cellY = readNumber(payload, ["cell_y"], Number.NaN)
  const cellDeg = readNumber(payload, ["cell_deg"], Number.NaN)
  const reportKeys = readList(payload, ["report_keys"])
  const startDate = readText(payload, ["start_date"]) || null
  const endDate = readText(payload, ["end_date"]) || null
  const enabled = Number.isFinite(cellX) && Number.isFinite(cellY) && Number.isFinite(cellDeg) && cellDeg > 0
  const tileQuery = useLocationsInTile(
    caseId,
    enabled
      ? {
          cellX,
          cellY,
          cellDeg,
          reportKeys: reportKeys.length ? reportKeys : null,
          startDate,
          endDate,
          limit: 300,
        }
      : null,
    enabled
  )
  const data = tileQuery.data
  const rows = Array.isArray(data?.items)
    ? data.items
    : Array.isArray(data?.locations)
      ? data.locations
      : Array.isArray(data?.rows)
        ? data.rows
        : []
  const locations = rows.filter(isRecord) as TimelineItem[]

  return (
    <div className="space-y-3">
      <div className="rounded-md border border-border bg-card p-3">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold">{readText(payload, ["label"], "Location tile")}</span>
          <Badge variant="slate" className="ml-auto">
            {compactNumber(readNumber(payload, ["count"]))}
          </Badge>
        </div>
        {readText(payload, ["summary"]) && (
          <p className="mt-1 text-xs text-muted-foreground">{readText(payload, ["summary"])}</p>
        )}
        <div className="mt-2 grid grid-cols-2 gap-2 text-[11px] text-muted-foreground">
          <span>Cell X: {Number.isFinite(cellX) ? cellX : "-"}</span>
          <span>Cell Y: {Number.isFinite(cellY) ? cellY : "-"}</span>
          <span>Cell size: {Number.isFinite(cellDeg) ? cellDeg.toFixed(5) : "-"}</span>
          <span>Rows loaded: {compactNumber(locations.length)}</span>
        </div>
      </div>

      <div className="h-96 overflow-hidden rounded-md border border-border">
        {tileQuery.isLoading ? (
          <div className="flex h-full items-center justify-center gap-2 text-xs text-muted-foreground">
            <Loader2 className="size-4 animate-spin" />
            Loading tile locations
          </div>
        ) : locations.length === 0 ? (
          <SmallEmpty label="No rows returned for this tile." />
        ) : (
          <LocationsTable
            locations={locations}
            selectedId={null}
            reports={reports}
            onRowClick={onSelectLocation}
          />
        )}
      </div>
    </div>
  )
}
