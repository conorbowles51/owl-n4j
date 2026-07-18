import { Popup } from "react-map-gl/maplibre"
import { Crosshair, ExternalLink, MapPin } from "lucide-react"
import { Button } from "@/components/ui/button"
import { NodeBadge } from "@/components/ui/node-badge"
import { Badge } from "@/components/ui/badge"
import { markdownToPlainText } from "@/lib/markdown-text"
import type { MapLocation } from "../hooks/use-map-data"
import type { EntityType } from "@/lib/theme"

interface EntityPopupProps {
  location: MapLocation
  onClose: () => void
  onSetProximityAnchor: (key: string) => void
  onMouseEnter?: () => void
  onMouseLeave?: () => void
}

interface GeocodingCandidate {
  latitude?: number
  longitude?: number
  formatted_address?: string
  precision?: string
  confidence?: string
}

function textValue(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value : undefined
}

function numberValue(value: unknown): number | undefined {
  if (typeof value === "number" && Number.isFinite(value)) return value
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value)
    if (Number.isFinite(parsed)) return parsed
  }
  return undefined
}

function parseCandidate(value: unknown): GeocodingCandidate | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null
  const candidate = value as Record<string, unknown>
  const parsed = {
    latitude: numberValue(candidate.latitude),
    longitude: numberValue(candidate.longitude),
    formatted_address: textValue(candidate.formatted_address),
    precision: textValue(candidate.precision),
    confidence: textValue(candidate.confidence),
  }
  return parsed.formatted_address || parsed.latitude !== undefined || parsed.longitude !== undefined ? parsed : null
}

export function parseGeocodingCandidates(value: MapLocation["geocoding_candidates"]): GeocodingCandidate[] {
  let rawCandidates: unknown
  if (Array.isArray(value)) {
    rawCandidates = value
  } else if (typeof value === "string" && value.trim()) {
    try {
      rawCandidates = JSON.parse(value)
    } catch {
      return []
    }
  } else {
    return []
  }

  if (!Array.isArray(rawCandidates)) return []
  return rawCandidates.map(parseCandidate).filter((candidate): candidate is GeocodingCandidate => candidate !== null)
}

function formatCandidateCoordinates(candidate: GeocodingCandidate): string | null {
  if (candidate.latitude === undefined || candidate.longitude === undefined) return null
  return `${candidate.latitude.toFixed(4)}, ${candidate.longitude.toFixed(4)}`
}

function formatCandidateMeta(candidate: GeocodingCandidate): string | null {
  const coordinates = formatCandidateCoordinates(candidate)
  const parts = [candidate.precision, candidate.confidence, coordinates].filter(Boolean)
  return parts.length > 0 ? parts.join(" / ") : null
}

export function EntityPopup({
  location,
  onClose,
  onSetProximityAnchor,
  onMouseEnter,
  onMouseLeave,
}: EntityPopupProps) {
  const summaryText = location.summary ? markdownToPlainText(location.summary) : null
  const candidates = parseGeocodingCandidates(location.geocoding_candidates)
  const candidateCount = candidates.length

  return (
    <Popup
      longitude={location.longitude}
      latitude={location.latitude}
      onClose={onClose}
      closeOnClick={false}
      offset={12}
      className="map-entity-popup"
      maxWidth="340px"
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
            {location.latitude.toFixed(4)}, {location.longitude.toFixed(4)}
          </span>
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

        {(location.geocoding_provider || location.geocoding_query || location.geocoding_precision || candidateCount > 1) && (
          <div className="grid gap-0.5 text-[10px] text-muted-foreground">
            {location.geocoding_provider && <span>Geocoder: {location.geocoding_provider}</span>}
            {location.geocoding_query && <span>Query: {location.geocoding_query}</span>}
            {location.geocoding_precision && <span>Precision: {location.geocoding_precision}</span>}
            {candidateCount > 1 && <span>Candidates: {candidateCount}</span>}
          </div>
        )}

        {candidateCount > 1 && (
          <div className="grid gap-1 border-t border-border pt-1.5 text-[10px] text-muted-foreground">
            <span className="font-semibold text-foreground">Candidate details</span>
            <ol className="grid gap-1">
              {candidates.map((candidate, index) => {
                const meta = formatCandidateMeta(candidate)
                return (
                  <li key={`${candidate.formatted_address ?? "candidate"}-${index}`} className="grid gap-0.5">
                    <span className="line-clamp-2">
                      {index + 1}. {candidate.formatted_address ?? "Unnamed candidate"}
                    </span>
                    {meta && <span>{meta}</span>}
                  </li>
                )
              })}
            </ol>
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
