import { Popup } from "react-map-gl/maplibre"
import { Crosshair, ExternalLink, History, MapPin, Search } from "lucide-react"
import { Button } from "@/components/ui/button"
import { NodeBadge } from "@/components/ui/node-badge"
import { Badge } from "@/components/ui/badge"
import { markdownToPlainText } from "@/lib/markdown-text"
import {
  coordinatePrecisionForLocation,
  formatDisplayCoordinates,
  isApproximateLocation,
  type ManualCorrection,
  type MapLocation,
} from "../hooks/use-map-data"
import type { EntityType } from "@/lib/theme"

interface EntityPopupProps {
  location: MapLocation
  onClose: () => void
  onSetProximityAnchor: (key: string) => void
  onMouseEnter?: () => void
  onMouseLeave?: () => void
}

function formatValue(value: number | string | null | undefined, precision: number) {
  if (value === null || value === undefined || value === "") return "unset"
  const numeric = Number(value)
  if (Number.isFinite(numeric)) return numeric.toFixed(precision)
  return String(value)
}

function formatCorrectionCoordinates(correction: ManualCorrection, prefix: "from" | "to", precision: number) {
  const lat = correction[`${prefix}_latitude`]
  const lon = correction[`${prefix}_longitude`]
  return `${formatValue(lat, precision)}, ${formatValue(lon, precision)}`
}

function formatCorrectionDate(value: string | null | undefined) {
  if (!value) return "unknown time"
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}

export function EntityPopup({
  location,
  onClose,
  onSetProximityAnchor,
  onMouseEnter,
  onMouseLeave,
}: EntityPopupProps) {
  const summaryText = location.summary ? markdownToPlainText(location.summary) : null
  const approximate = isApproximateLocation(location)
  const displayPrecision = coordinatePrecisionForLocation(location)
  const hasProvenance =
    location.geocoding_provider ||
    location.geocoding_query ||
    location.geocoding_formatted_address

  return (
    <Popup
      longitude={location.longitude}
      latitude={location.latitude}
      onClose={onClose}
      closeOnClick={false}
      offset={12}
      className="map-entity-popup"
      maxWidth="320px"
    >
      <div className="flex flex-col gap-2 p-1" onMouseEnter={onMouseEnter} onMouseLeave={onMouseLeave}>
        {/* Header */}
        <div className="flex items-center gap-2">
          <NodeBadge type={location.type as EntityType} />
          <span className="text-xs font-semibold">{location.name}</span>
        </div>

        {/* Coordinates */}
        <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
          <MapPin className="size-3" />
          <span>
            {formatDisplayCoordinates(location)}
          </span>
          {approximate && (
            <Badge variant="secondary" className="ml-1 text-[9px]">
              approximate
            </Badge>
          )}
          {location.geocoding_confidence && (
            <Badge variant="outline" className="ml-1 text-[9px]">
              {location.geocoding_confidence}
            </Badge>
          )}
        </div>

        {/* Location info */}
        {location.location_formatted && (
          <p className="text-[10px] text-muted-foreground">
            {location.location_formatted}
          </p>
        )}

        {/* Geocoding provenance */}
        {hasProvenance && (
          <div className="space-y-1 border-t border-border pt-1.5 text-[10px] text-muted-foreground">
            <div className="flex items-center gap-1.5 font-medium text-foreground">
              <Search className="size-3" />
              Geocoding
            </div>
            {location.geocoding_provider && (
              <p>Provider: {location.geocoding_provider}</p>
            )}
            {location.geocoding_query && (
              <p>Query: {location.geocoding_query}</p>
            )}
            {location.geocoding_formatted_address && (
              <p>Resolved: {location.geocoding_formatted_address}</p>
            )}
          </div>
        )}

        {/* Manual correction history */}
        {location.manual_correction_history.length > 0 && (
          <div className="space-y-1 border-t border-border pt-1.5 text-[10px] text-muted-foreground">
            <div className="flex items-center gap-1.5 font-medium text-foreground">
              <History className="size-3" />
              Manual corrections
            </div>
            {location.manual_correction_history.map((correction, index) => (
              <p key={`${correction.moved_at ?? "correction"}-${index}`}>
                {(correction.moved_by_name || correction.moved_by || "Unknown")} moved it from{" "}
                {formatCorrectionCoordinates(correction, "from", displayPrecision)} to{" "}
                {formatCorrectionCoordinates(correction, "to", displayPrecision)} on{" "}
                {formatCorrectionDate(correction.moved_at)}
              </p>
            ))}
          </div>
        )}

        {/* Summary */}
        {summaryText && (
          <p className="text-[10px] leading-relaxed text-muted-foreground line-clamp-2">
            {summaryText}
          </p>
        )}

        {/* Date */}
        {location.date && (
          <p className="text-[10px] text-muted-foreground">
            Date: {location.date}
          </p>
        )}

        {/* Connections */}
        {location.connections && location.connections.length > 0 && (
          <p className="text-[10px] text-muted-foreground">
            {location.connections.length} connection{location.connections.length !== 1 ? "s" : ""}
          </p>
        )}

        {/* Actions */}
        <div className="flex items-center gap-1 border-t border-border pt-1.5">
          <Button
            variant="ghost"
            size="sm"
            className="h-6 text-[10px]"
            onClick={() => onSetProximityAnchor(location.key)}
          >
            <Crosshair className="mr-1 size-3" />
            Set as anchor
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="h-6 text-[10px]"
            asChild
          >
            <a href={`#graph?highlight=${location.key}`}>
              <ExternalLink className="mr-1 size-3" />
              View in graph
            </a>
          </Button>
        </div>
      </div>
    </Popup>
  )
}
