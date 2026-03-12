import { useMemo } from "react"
import { useQuery } from "@tanstack/react-query"
import { fetchAPI } from "@/lib/api-client"
import type { EntityType } from "@/lib/theme"

export interface MapLocation {
  key: string
  name: string
  type: EntityType
  latitude: number
  longitude: number
  location_raw?: string
  location_formatted?: string
  geocoding_confidence?: string
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
  summary?: string
  date?: string
  connections?: { key: string; name: string; type: string; relationship: string }[]
}

export function useMapData(caseId: string | undefined) {
  return useQuery({
    queryKey: ["map", caseId],
    queryFn: async () => {
      const raw = await fetchAPI<RawMapLocation[]>(
        `/api/graph/locations?case_id=${caseId}`
      )
      return raw.map(
        (loc): MapLocation => ({
          ...loc,
          name: loc.name ?? loc.label ?? loc.key,
          type: loc.type.toLowerCase() as EntityType,
        })
      )
    },
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
