import type { ReactNode } from "react"
import { Clock, Loader2, MapPin, MessageSquare, Smartphone } from "lucide-react"

import { Badge } from "@/components/ui/badge"

import {
  useEventDetail,
  useEventRelated,
  useLocationVisitors,
} from "../../hooks/use-cellebrite"
import type { CellebriteRecord, PhoneReport, RailSelection } from "../../types"
import {
  compactNumber,
  isRecord,
  readNumber,
  readText,
} from "../shared/cellebrite-format"
import { PhoneReportChip } from "../shared/PhoneReportChip"
import { SmallEmpty } from "../shared/SmallEmpty"
import {
  eventLabel,
  eventTimestamp,
  eventType,
  formatTs,
  locationOf,
  reportKeyOf,
} from "./eventUtils"

export function EventSelectionDetail({
  caseId,
  selection,
  reports,
  renderRaw,
}: {
  caseId: string
  selection: RailSelection
  reports: PhoneReport[]
  renderRaw: (value: unknown) => ReactNode
}) {
  const payload = isRecord(selection.payload) ? selection.payload : {}
  const nodeKey = readText(payload, ["node_key", "id", "key"])
  const detailQuery = useEventDetail(caseId, nodeKey || null, Boolean(nodeKey))
  const detail = isRecord(detailQuery.data) ? detailQuery.data : null
  const event = { ...payload, ...(detail ?? {}) }
  const type = eventType(event)
  const isCommsAnchor = ["message", "call", "email"].includes(type)
  const relatedQuery = useEventRelated(caseId, nodeKey || null, isCommsAnchor)
  const point = locationOf(event) ?? nearestPoint(event)
  const visitorsQuery = useLocationVisitors(
    caseId,
    point ? { lat: point.latitude, lon: point.longitude, radiusM: 150 } : null,
    Boolean(point)
  )
  const reportKey = reportKeyOf(event)

  if (!nodeKey && Object.keys(event).length === 0) {
    return <SmallEmpty label="No event details available." />
  }

  return (
    <div className="space-y-3">
      <div className="rounded-md border border-border bg-card p-3">
        <div className="flex items-start gap-2">
          <div className="flex size-8 shrink-0 items-center justify-center rounded-md border border-border bg-muted">
            {type === "location" || point ? (
              <MapPin className="size-4 text-cyan-500" />
            ) : (
              <MessageSquare className="size-4 text-amber-500" />
            )}
          </div>
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-semibold">
              {eventLabel(event)}
            </div>
            <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[11px] text-muted-foreground">
              {type && <Badge variant="slate">{type}</Badge>}
              {readText(event, ["source_app", "app"]) && (
                <Badge variant="outline">
                  {readText(event, ["source_app", "app"])}
                </Badge>
              )}
              {eventTimestamp(event) && (
                <span className="inline-flex items-center gap-1">
                  <Clock className="size-3" />
                  {formatTs(eventTimestamp(event))}
                </span>
              )}
            </div>
          </div>
        </div>
        {reportKey && (
          <div className="mt-3">
            <PhoneReportChip reportKey={reportKey} reports={reports} compact />
          </div>
        )}
      </div>

      {detailQuery.isLoading && (
        <div className="flex items-center gap-2 rounded-md border border-border bg-card p-3 text-xs text-muted-foreground">
          <Loader2 className="size-4 animate-spin" />
          Loading full event detail
        </div>
      )}

      {point && (
        <LocationVisitorsBlock
          visitors={visitorsQuery.data?.visitors ?? []}
          loading={visitorsQuery.isLoading}
          reports={reports}
        />
      )}

      {isCommsAnchor && (
        <RelatedCommsBlock
          loading={relatedQuery.isLoading}
          related={isRecord(relatedQuery.data) ? relatedQuery.data : null}
        />
      )}

      <FieldTable event={event} />

      <details className="rounded-md border border-border bg-card">
        <summary className="cursor-pointer px-3 py-2 text-xs font-semibold">
          Raw properties
        </summary>
        <div className="border-t border-border p-2">{renderRaw(event)}</div>
      </details>
    </div>
  )
}

function LocationVisitorsBlock({
  visitors,
  loading,
  reports,
}: {
  visitors: CellebriteRecord[]
  loading: boolean
  reports: PhoneReport[]
}) {
  if (loading && visitors.length === 0) {
    return (
      <div className="rounded-md border border-border bg-card p-3 text-xs text-muted-foreground">
        Checking for other devices...
      </div>
    )
  }
  if (visitors.length === 0) return null

  return (
    <div className="rounded-md border border-border bg-card p-3">
      <div className="mb-2 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
        <Smartphone className="size-3.5" />
        Devices that visited this place
        <span className="normal-case tracking-normal">(~150m)</span>
      </div>
      <div className="space-y-1">
        {visitors.map((visitor) => {
          const reportKey = readText(visitor, ["device_report_key"])
          const visits = readNumber(visitor, ["visit_count"])
          return (
            <div
              key={reportKey || JSON.stringify(visitor)}
              className="flex items-center gap-2 rounded border border-border bg-muted/20 px-2 py-1 text-[11px]"
            >
              {reportKey ? (
                <PhoneReportChip
                  reportKey={reportKey}
                  reports={reports}
                  compact
                />
              ) : (
                <span className="text-muted-foreground">Unknown device</span>
              )}
              <span className="ml-auto font-semibold tabular-nums">
                {compactNumber(visits)} visit{visits === 1 ? "" : "s"}
              </span>
              {readText(visitor, ["last_seen"]) && (
                <span className="whitespace-nowrap text-muted-foreground">
                  last {formatTs(readText(visitor, ["last_seen"]))}
                </span>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

function RelatedCommsBlock({
  loading,
  related,
}: {
  loading: boolean
  related: CellebriteRecord | null
}) {
  const thread = listRecords(related?.thread)
  const around = listRecords(related?.around)
  if (loading && thread.length === 0 && around.length === 0) {
    return (
      <div className="flex items-center gap-2 rounded-md border border-border bg-card p-3 text-xs text-muted-foreground">
        <Loader2 className="size-4 animate-spin" />
        Loading nearby communications
      </div>
    )
  }
  if (thread.length === 0 && around.length === 0) return null

  return (
    <div className="rounded-md border border-border bg-card p-3">
      <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
        Related communications
      </div>
      <RelatedList title="Conversation" rows={thread.slice(0, 5)} />
      <RelatedList title="Around this time" rows={around.slice(0, 5)} />
    </div>
  )
}

function RelatedList({
  title,
  rows,
}: {
  title: string
  rows: CellebriteRecord[]
}) {
  if (rows.length === 0) return null
  return (
    <div className="mb-2 last:mb-0">
      <div className="mb-1 text-[11px] font-medium">{title}</div>
      <div className="space-y-1">
        {rows.map((row, index) => (
          <div
            key={readText(row, ["node_key", "id", "key"], String(index))}
            className="rounded border border-border bg-muted/20 px-2 py-1 text-[11px]"
          >
            <div className="truncate font-medium">{eventLabel(row)}</div>
            <div className="truncate text-muted-foreground">
              {[
                eventTimestamp(row) ? formatTs(eventTimestamp(row)) : "",
                readText(row, ["body", "summary"]),
              ]
                .filter(Boolean)
                .join(" / ")}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function FieldTable({ event }: { event: CellebriteRecord }) {
  const fields = [
    ["Time", eventTimestamp(event) ? formatTs(eventTimestamp(event)) : ""],
    ["Direction", readText(event, ["direction"])],
    ["From", readText(event, ["sender_name", "from"])],
    ["To", readText(event, ["recipient_name", "to"])],
    ["Place", readText(event, ["address", "place_name", "location_formatted"])],
    ["Region", readText(event, ["admin1"])],
    ["Country", readText(event, ["country"])],
    ["Coordinates", coordinateLabel(event)],
    ["Summary", readText(event, ["summary", "body", "subject"])],
  ].filter(([, value]) => value)

  if (fields.length === 0) return null
  return (
    <div className="rounded-md border border-border bg-card">
      <table className="w-full text-left text-xs">
        <tbody>
          {fields.map(([label, value]) => (
            <tr key={label} className="border-b border-border last:border-0">
              <th className="w-24 px-3 py-2 font-medium text-muted-foreground">
                {label}
              </th>
              <td className="break-words px-3 py-2">{value}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function nearestPoint(row: CellebriteRecord) {
  const latitude = readNumber(row, ["nearest_location_lat"], Number.NaN)
  const longitude = readNumber(row, ["nearest_location_lon"], Number.NaN)
  if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) return null
  return { latitude, longitude }
}

function coordinateLabel(row: CellebriteRecord) {
  const point = locationOf(row) ?? nearestPoint(row)
  return point
    ? `${point.latitude.toFixed(5)}, ${point.longitude.toFixed(5)}`
    : ""
}

function listRecords(value: unknown) {
  return Array.isArray(value) ? value.filter(isRecord) : []
}
