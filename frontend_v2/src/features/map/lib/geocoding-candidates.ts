import type { MapLocation } from "../hooks/use-map-data"

export interface GeocodingCandidate {
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

export function formatCandidateMeta(candidate: GeocodingCandidate): string | null {
  const coordinates = formatCandidateCoordinates(candidate)
  const parts = [candidate.precision, candidate.confidence, coordinates].filter(Boolean)
  return parts.length > 0 ? parts.join(" / ") : null
}
