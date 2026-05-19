import { Loader2, Smartphone } from "lucide-react"

import { Badge } from "@/components/ui/badge"

import { useLocationsInTile } from "../../hooks/use-cellebrite"
import type {
  CellebriteRecord,
  LocationTilePhoneBreakdown,
  PhoneReport,
  TimelineItem,
} from "../../types"
import {
  compactNumber,
  isRecord,
  readList,
  readNumber,
  readText,
} from "../shared/cellebrite-format"
import { PhoneReportChip } from "../shared/PhoneReportChip"
import { SmallEmpty } from "../shared/SmallEmpty"
import { formatTs } from "../events/eventUtils"
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
  const enabled =
    Number.isFinite(cellX) &&
    Number.isFinite(cellY) &&
    Number.isFinite(cellDeg) &&
    cellDeg > 0
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
  const perPhone = Array.isArray(data?.per_phone)
    ? data.per_phone.filter(isRecord)
    : []
  const truncated = Boolean(data?.truncated)

  return (
    <div className="space-y-3">
      <div className="rounded-md border border-border bg-card p-3">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold">
            {readText(payload, ["label"], "Location tile")}
          </span>
          <Badge variant="slate" className="ml-auto">
            {compactNumber(readNumber(payload, ["count"]))}
          </Badge>
        </div>
        {readText(payload, ["summary"]) && (
          <p className="mt-1 text-xs text-muted-foreground">
            {readText(payload, ["summary"])}
          </p>
        )}
        <div className="mt-2 grid grid-cols-2 gap-2 text-[11px] text-muted-foreground">
          <span>Cell X: {Number.isFinite(cellX) ? cellX : "-"}</span>
          <span>Cell Y: {Number.isFinite(cellY) ? cellY : "-"}</span>
          <span>
            Cell size: {Number.isFinite(cellDeg) ? cellDeg.toFixed(5) : "-"}
          </span>
          <span>Rows loaded: {compactNumber(locations.length)}</span>
        </div>
      </div>

      {perPhone.length > 0 && (
        <PerPhoneBreakdown
          rows={perPhone as LocationTilePhoneBreakdown[]}
          reports={reports}
          truncated={truncated}
        />
      )}

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

function PerPhoneBreakdown({
  rows,
  reports,
  truncated,
}: {
  rows: LocationTilePhoneBreakdown[]
  reports: PhoneReport[]
  truncated: boolean
}) {
  return (
    <div className="rounded-md border border-border bg-card p-3">
      <div className="mb-2 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
        <Smartphone className="size-3.5" />
        Per Phone
        {truncated && (
          <span className="normal-case tracking-normal text-amber-600">
            counts based on loaded rows
          </span>
        )}
      </div>
      <div className="space-y-1.5">
        {rows.map((row) => (
          <div
            key={row.device_report_key || "_unknown"}
            className="rounded border border-border bg-muted/20 px-2 py-1.5 text-[11px]"
          >
            <div className="flex items-center gap-2">
              {row.device_report_key ? (
                <PhoneReportChip
                  reportKey={row.device_report_key}
                  reports={reports}
                  compact
                />
              ) : (
                <span className="text-muted-foreground">Unknown device</span>
              )}
              <span className="font-semibold tabular-nums">
                {compactNumber(row.count)} hit{row.count === 1 ? "" : "s"}
              </span>
              {row.last_seen && (
                <span className="ml-auto whitespace-nowrap text-muted-foreground">
                  last {formatTs(row.last_seen)}
                </span>
              )}
            </div>
            {row.apps?.length ? (
              <div className="mt-1 flex flex-wrap gap-1">
                {row.apps.slice(0, 8).map((app) => (
                  <Badge
                    key={app.app}
                    variant="slate"
                    className="rounded-sm px-1 py-0 text-[10px]"
                    title={`${app.count} hits via ${app.app}`}
                  >
                    {app.app} {compactNumber(app.count)}
                  </Badge>
                ))}
                {row.apps.length > 8 && (
                  <span className="text-[10px] text-muted-foreground">
                    +{row.apps.length - 8} more
                  </span>
                )}
              </div>
            ) : null}
            {row.first_seen &&
              row.last_seen &&
              row.first_seen !== row.last_seen && (
                <div className="mt-0.5 text-[10px] text-muted-foreground">
                  {formatTs(row.first_seen)} / {formatTs(row.last_seen)}
                </div>
              )}
          </div>
        ))}
      </div>
    </div>
  )
}
