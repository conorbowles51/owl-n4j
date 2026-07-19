import { useMemo } from "react"
import { useQuery } from "@tanstack/react-query"
import { fetchAPI } from "@/lib/api-client"
import type { EntityType } from "@/lib/theme"
import { useCaseLayer } from "@/features/significant/stores/case-layer.store"

export interface ManualCorrection {
  moved_by?: string | null
  moved_by_name?: string | null
  moved_at?: string | null
  from_latitude?: number | string | null
  from_longitude?: number | string | null
  to_latitude?: number | string | null
  to_longitude?: number | string | null
  query?: string | null
  provider?: string | null
  formatted_address?: string | null
}

export interface MapLocation {
  key: string
  name: string
  type: EntityType
  latitude: number
  longitude: number
  location_raw?: string
  location_formatted?: string
  geocoding_confidence?: string
  geocoding_confidence_score?: number
  geocoding_provider?: string | null
  geocoding_query?: string | null
  geocoding_formatted_address?: string | null
  location_granularity?: string | null
  coordinate_precision?: number | string | null
  accuracy_meters?: number | string | null
  manual_correction_history: ManualCorrection[]
  geocoding_status?: string
  location_specificity?: string
  manual_fields?: string[]
  summary?: string
  date?: string
  connections?: { key: string; name: string; type: string; relationship: string }[]
}

interface RawMapLocation {
  key: string
  label?: string
  name?: string
  type: EntityType
  latitude: number
  longitude: number
  location_raw?: string
  location_formatted?: string
  geocoding_confidence?: string
  geocoding_confidence_score?: number
  geocoding_provider?: string | null
  geocoding_query?: string | null
  geocoding_formatted_address?: string | null
  location_granularity?: string | null
  specificity?: string | null
  coordinate_precision?: number | string | null
  accuracy_meters?: number | string | null
  manual_correction_history?: unknown
  geocoding_status?: string
  location_specificity?: string
  manual_fields?: string[]
  summary?: string
  date?: string
  connections?: { key: string; name: string; type: string; relationship: string }[]
}

const APPROXIMATE_GRANULARITIES = new Set(["city", "neighborhood", "neighbourhood"])

function normalizeGranularity(value: string | null | undefined) {
  return value?.trim().toLowerCase().replace(/-/g, "_") ?? null
}

function normalizeCorrectionHistory(value: unknown): ManualCorrection[] {
  if (Array.isArray(value)) {
    return value.filter((item): item is ManualCorrection => item !== null && typeof item === "object")
  }
  if (typeof value === "string" && value.trim()) {
    try {
      const parsed = JSON.parse(value)
      return normalizeCorrectionHistory(parsed)
    } catch {
      return []
    }
  }
  return []
}

export function isApproximateLocation(location: Pick<MapLocation, "location_granularity">) {
  const granularity = normalizeGranularity(location.location_granularity)
  return granularity ? APPROXIMATE_GRANULARITIES.has(granularity) : false
}

export function coordinatePrecisionForLocation(
  location: Pick<MapLocation, "accuracy_meters" | "coordinate_precision" | "location_granularity">
) {
  const explicitPrecision = Number(location.coordinate_precision)
  if (Number.isFinite(explicitPrecision) && explicitPrecision >= 0) {
    return Math.min(6, Math.floor(explicitPrecision))
  }

  const accuracyMeters = Number(location.accuracy_meters)
  if (Number.isFinite(accuracyMeters) && accuracyMeters > 0) {
    if (accuracyMeters >= 50000) return 0
    if (accuracyMeters >= 10000) return 1
    if (accuracyMeters >= 1000) return 2
    if (accuracyMeters >= 100) return 3
    if (accuracyMeters >= 10) return 4
    return 5
  }

  switch (normalizeGranularity(location.location_granularity)) {
    case "country":
    case "region":
    case "state":
      return 1
    case "city":
      return 2
    case "neighborhood":
    case "neighbourhood":
      return 3
    case "street":
      return 4
    case "address":
    case "building":
    case "coordinate":
    case "exact":
    case "exact_address":
    case "parcel":
      return 5
    default:
      return 4
  }
}

export function formatDisplayCoordinates(location: MapLocation) {
  const precision = coordinatePrecisionForLocation(location)
  return `${location.latitude.toFixed(precision)}, ${location.longitude.toFixed(precision)}`
}

export function useMapData(caseId: string | undefined) {
  const scope = useCaseLayer(caseId)
  return useQuery({
    queryKey: ["map", caseId, scope],
    queryFn: async () => {
      const raw = await fetchAPI<RawMapLocation[]>(
        `/api/graph/locations?case_id=${caseId}&scope=${scope}`
      )
      return raw.map(
        (loc): MapLocation => ({
          ...loc,
          name: loc.name ?? loc.label ?? loc.key,
          type: loc.type.toLowerCase() as EntityType,
          geocoding_provider: loc.geocoding_provider ?? null,
          geocoding_query: loc.geocoding_query ?? loc.location_raw ?? null,
          geocoding_formatted_address: loc.geocoding_formatted_address ?? loc.location_formatted ?? null,
          location_granularity: normalizeGranularity(loc.location_granularity ?? loc.specificity),
          coordinate_precision: loc.coordinate_precision ?? null,
          accuracy_meters: loc.accuracy_meters ?? null,
          manual_correction_history: normalizeCorrectionHistory(loc.manual_correction_history),
        })
      )
    },
    enabled: !!caseId,
  })
}

export interface ReviewQueueItem {
  key: string
  name: string
  type: string
  location_raw?: string
  geocoding_status?: string
  geocoding_confidence?: string
  location_specificity?: string
  manual_fields?: string[]
}

/** Locations flagged at ingestion (no coordinates, so no pin). */
export function useMapReviewQueue(caseId: string | undefined) {
  const scope = useCaseLayer(caseId)
  return useQuery({
    queryKey: ["map", "needs-review", caseId, scope],
    queryFn: () =>
      fetchAPI<ReviewQueueItem[]>(
        `/api/graph/locations/needs-review?case_id=${caseId}&scope=${scope}`
      ),
    enabled: !!caseId,
  })
}

export function useMapAnalysis(locations: MapLocation[]) {
  const bounds = useMemo(() => {
    if (locations.length === 0) return null
    let minLat = Infinity, maxLat = -Infinity
    let minLng = Infinity, maxLng = -Infinity
    for (const loc of locations) {
      if (loc.latitude < minLat) minLat = loc.latitude
      if (loc.latitude > maxLat) maxLat = loc.latitude
      if (loc.longitude < minLng) minLng = loc.longitude
      if (loc.longitude > maxLng) maxLng = loc.longitude
    }
    return { minLat, maxLat, minLng, maxLng }
  }, [locations])

  const center = useMemo(() => {
    if (!bounds) return { latitude: 0, longitude: 0 }
    return {
      latitude: (bounds.minLat + bounds.maxLat) / 2,
      longitude: (bounds.minLng + bounds.maxLng) / 2,
    }
  }, [bounds])

  const typeGroups = useMemo(() => {
    const groups = new Map<EntityType, MapLocation[]>()
    for (const loc of locations) {
      if (!groups.has(loc.type)) groups.set(loc.type, [])
      groups.get(loc.type)!.push(loc)
    }
    return groups
  }, [locations])

  return { bounds, center, typeGroups }
}

/** Haversine distance in km */
export function haversineDistance(
  lat1: number, lon1: number,
  lat2: number, lon2: number
): number {
  const R = 6371
  const dLat = ((lat2 - lat1) * Math.PI) / 180
  const dLon = ((lon2 - lon1) * Math.PI) / 180
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos((lat1 * Math.PI) / 180) *
      Math.cos((lat2 * Math.PI) / 180) *
      Math.sin(dLon / 2) *
      Math.sin(dLon / 2)
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a))
}
